"""
HW10 Part 1 - data layer for the Streamlit dashboard (and for verify_hw10.py, so both use ONE definition of every metric).

Data sources (all produced by this repo, nothing is hand-typed):
  data/hw10/spans/spans.jsonl            one JSON span per stage per request (code/hw08/tracing.py)
  reports/hw10/raw/eval_results.json     Part 2 evaluator output (GEval, local judge)
  reports/hw10/raw/judge_validation.json Part 3 judge validation (Spearman, MAD, repeatability)
  reports/hw10/raw/judge_runs.json       Part 3 raw per-case, per-run judge scores
  reports/hw10/raw/trace_examples.json   the three required example trace ids
  reports/hw10/raw/latency_stats.json    Part 4.3 stage table

Metric definitions
  request            a trace_id that has a cache_lookup span (trace ids starting "warmup-" are model warm-ups and are excluded)
  cache hit / miss   cache_lookup.is_cached True / False
  hit rate           hits / (hits + misses) over requests in the window
  error rate         requests with an error status in any REQUEST-PATH span (everything except `evaluator`) / requests
  end-to-end latency miss: cache_lookup start -> `final` span end (user-facing; failed requests have no final answer and are excluded)
                     hit : cache_lookup duration.  Hit and miss latency are always reported separately.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
SPANS = ROOT / "data" / "hw10" / "spans" / "spans.jsonl"
RAW = ROOT / "reports" / "hw10" / "raw"
STAGE_ORDER = ["cache_lookup", "inbox", "planner", "tasks", "writer", "drafts", "reviewer", "final", "evaluator"]


def load_spans(path: Path = SPANS) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return out


def load_json(name: str) -> Any:
    try:
        return json.loads((RAW / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def by_trace(spans: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    d: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in spans:
        d[s["trace_id"]].append(s)
    for v in d.values():
        v.sort(key=lambda s: (STAGE_ORDER.index(s["stage"]) if s["stage"] in STAGE_ORDER else 99, s["start_ms"]))
    return d


def requests(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for tid, ss in by_trace(spans).items():
        if tid.startswith("warmup-"):
            continue
        cl = next((s for s in ss if s["stage"] == "cache_lookup"), None)
        if cl is None:
            continue
        hit = bool(cl.get("is_cached"))
        fin = next((s for s in ss if s["stage"] == "final"), None)
        err = [s for s in ss if s["stage"] != "evaluator" and s["status"] == "error"]
        if hit:
            e2e = cl["duration_ms"]
        elif fin is not None and fin["status"] == "ok":
            e2e = fin["end_ms"] - cl["start_ms"]
        else:
            e2e = None
        rows.append({"trace_id": tid, "start_ms": cl["start_ms"], "path": "hit" if hit else "miss", "is_error": bool(err),
                     "failing_stage": err[0]["stage"] if err else None, "error": err[0]["error"] if err else None,
                     "e2e_ms": e2e, "similarity": cl.get("similarity"),
                     "evaluated": any(s["stage"] == "evaluator" for s in ss)})
    rows.sort(key=lambda r: r["start_ms"])
    return rows


def window(rows: list[dict[str, Any]], hours: float | None) -> tuple[list[dict[str, Any]], float | None, float | None]:
    """Requests whose cache_lookup started in the last `hours` of RECORDED activity (None = everything)."""
    if not rows:
        return [], None, None
    t_end = max(r["start_ms"] for r in rows)
    t_start = min(r["start_ms"] for r in rows) if hours is None else t_end - hours * 3_600_000
    sel = [r for r in rows if r["start_ms"] >= t_start]
    return sel, (min(r["start_ms"] for r in sel) if sel else None), t_end


def pct(vals: list[float], q: float) -> float | None:
    return round(float(np.percentile(vals, q)), 1) if vals else None


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    hits = [r for r in rows if r["path"] == "hit"]
    misses = [r for r in rows if r["path"] == "miss"]
    miss_e2e = [r["e2e_ms"] for r in misses if r["e2e_ms"] is not None]
    hit_e2e = [r["e2e_ms"] for r in hits if r["e2e_ms"] is not None]
    n = len(rows)
    return {"requests": n, "hits": len(hits), "misses": len(misses),
            "hit_rate_pct": round(100 * len(hits) / n, 1) if n else None,
            "miss_rate_pct": round(100 * len(misses) / n, 1) if n else None,
            "errors": sum(r["is_error"] for r in rows), "error_rate_pct": round(100 * sum(r["is_error"] for r in rows) / n, 2) if n else None,
            "miss_latency_ms": {"n": len(miss_e2e), "p50": pct(miss_e2e, 50), "p95": pct(miss_e2e, 95),
                                "mean": round(float(np.mean(miss_e2e)), 1) if miss_e2e else None,
                                "max": round(max(miss_e2e), 1) if miss_e2e else None},
            "hit_latency_ms": {"n": len(hit_e2e), "p50": pct(hit_e2e, 50), "p95": pct(hit_e2e, 95),
                               "mean": round(float(np.mean(hit_e2e)), 1) if hit_e2e else None,
                               "max": round(max(hit_e2e), 1) if hit_e2e else None}}


def trace_view(spans: list[dict[str, Any]], trace_id: str) -> dict[str, Any] | None:
    """Full journey of one request in stage order. Accepts a unique prefix of the trace id."""
    d = by_trace(spans)
    key = trace_id.strip()
    if key not in d:
        cand = [t for t in d if t.startswith(key)] if len(key) >= 6 else []
        if len(cand) != 1:
            return None
        key = cand[0]
    ss = d[key]
    ev = [s for s in ss if s["stage"] == "evaluator"]
    if len(ev) > 1:                                   # a trace re-evaluated: show only the latest evaluator span
        latest = max(ev, key=lambda s: s["start_ms"])
        ss = [s for s in ss if s["stage"] != "evaluator"] + [latest]
    cl = next((s for s in ss if s["stage"] == "cache_lookup"), None)
    path = "hit" if (cl and cl.get("is_cached")) else "miss"
    err = next((s for s in ss if s["stage"] != "evaluator" and s["status"] == "error"), None)
    return {"trace_id": key, "path": path, "spans": ss, "failed": err is not None,
            "failing_stage": err["stage"] if err else None, "error": err["error"] if err else None}
