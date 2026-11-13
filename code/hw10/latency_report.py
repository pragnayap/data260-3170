#!/usr/bin/env python3
# ruff: noqa: I001
"""
HW10 Part 4.3 - stage-latency table from the REAL spans of the 50 confirmed cache-miss requests.

    python latency_report.py           -> prints the table, writes reports/hw10/raw/latency_stats.json

Definitions (so the numbers can be recomputed from spans.jsonl + latency_runs.json):
  * end-to-end (user-facing) latency of one request = cache_lookup start -> final answer received (e2e_ms in latency_runs.json)
  * Planner / Writer / Reviewer / Cache lookup  = duration of that stage's span
  * Queue wait (total) = inbox + tasks + drafts + final spans of the request (produce -> pick-up, summed over the 4 hops)
  * Evaluation = duration of the evaluator span (judge scoring). It runs AFTER the answer is returned, so it is reported
    against the same end-to-end figure but is not part of the user-facing latency.
  * % of end-to-end = sum(stage time over the 50 requests) / sum(end-to-end time over the 50 requests)
  * percentiles: numpy linear interpolation over the per-request values
Cache-hit latency is reported separately (never mixed into the miss table).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict

import common10 as c
import numpy as np
from tracing import read_spans

QUEUE = ("inbox", "tasks", "drafts", "final")
ROWS = [("Cache lookup", ("cache_lookup",)), ("Planner", ("planner",)), ("Writer", ("writer",)),
        ("Reviewer", ("reviewer",)), ("Queue wait (total)", QUEUE), ("Evaluation", ("evaluator",))]


def compute() -> dict:
    runs = json.loads((c.RAW / "latency_runs.json").read_text())["requests"]
    ids = [r["trace_id"] for r in runs]
    e2e = {r["trace_id"]: r["e2e_ms"] for r in runs}
    by: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    last_eval: dict[str, dict] = {}
    for s in read_spans():
        if s["trace_id"] in e2e and s["status"] == "ok":
            if s["stage"] == "evaluator":                  # a trace may be (re-)evaluated: keep only the LATEST evaluator span
                if s["trace_id"] not in last_eval or s["start_ms"] > last_eval[s["trace_id"]]["start_ms"]:
                    last_eval[s["trace_id"]] = s
            else:
                by[s["trace_id"]][s["stage"]] += s["duration_ms"]
    for tid, s in last_eval.items():
        by[tid]["evaluator"] = s["duration_ms"]
    total_e2e = sum(e2e.values())
    out: dict = {"n_requests": len(ids), "definition_end_to_end": "cache_lookup start -> final received (user-facing)",
                 "end_to_end_ms": {"p50": round(float(np.percentile(list(e2e.values()), 50)), 1),
                                   "p95": round(float(np.percentile(list(e2e.values()), 95)), 1),
                                   "mean": round(float(np.mean(list(e2e.values()))), 1)}, "stages": {}}
    covered = 0.0
    for name, stages in ROWS:
        vals = [sum(by[t].get(s, 0.0) for s in stages) for t in ids if any(s in by[t] for s in stages)]
        if not vals:
            out["stages"][name] = {"n": 0, "p50_ms": None, "p95_ms": None, "pct_of_end_to_end": None}
            continue
        share = 100.0 * sum(vals) / (total_e2e * len(vals) / len(ids))      # share over the requests that have this stage
        out["stages"][name] = {"n": len(vals), "p50_ms": round(float(np.percentile(vals, 50)), 1),
                               "p95_ms": round(float(np.percentile(vals, 95)), 1), "pct_of_end_to_end": round(share, 2)}
        if name != "Evaluation":
            covered += share
    out["request_path_stages_pct_total"] = round(covered, 2)
    out["unaccounted_pct"] = round(100.0 - covered, 2)
    # dominant contributor among the request-path stages
    dom = max((n for n, _ in ROWS if n != "Evaluation"), key=lambda n: out["stages"][n]["pct_of_end_to_end"] or 0)
    out["dominant_stage"] = dom
    # separate cache-hit latency
    try:
        hits = json.loads((c.RAW / "trace_examples.json").read_text())["hit_samples"]
        h = [x["e2e_ms"] for x in hits]
        out["cache_hit_latency_ms"] = {"n": len(h), "p50": round(float(np.percentile(h, 50)), 1),
                                       "p95": round(float(np.percentile(h, 95)), 1), "max": round(max(h), 1)}
    except OSError:
        out["cache_hit_latency_ms"] = None
    return out


def main() -> int:
    c.banner("latency_report.py")
    out = compute()
    (c.RAW / "latency_stats.json").write_text(json.dumps(out, indent=2))
    print(f"{'Stage':<20}{'n':>4}{'p50 (ms)':>12}{'p95 (ms)':>12}{'% of cache-miss e2e':>22}")
    for name, v in out["stages"].items():
        if v["n"] == 0:
            print(f"{name:<20}{0:>4}{'pending':>12}{'pending':>12}{'pending':>22}")
        else:
            print(f"{name:<20}{v['n']:>4}{v['p50_ms']:>12.1f}{v['p95_ms']:>12.1f}{v['pct_of_end_to_end']:>21.2f}%")
    e = out["end_to_end_ms"]
    print(f"\nend-to-end (user-facing, n={out['n_requests']}): p50 {e['p50']:.1f} ms, p95 {e['p95']:.1f} ms, mean {e['mean']:.1f} ms")
    print(f"request-path stages cover {out['request_path_stages_pct_total']}% of end-to-end (unaccounted {out['unaccounted_pct']}%)")
    print(f"dominant stage: {out['dominant_stage']}")
    if out["cache_hit_latency_ms"]:
        print(f"cache-hit latency (separate): {out['cache_hit_latency_ms']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
