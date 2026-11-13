#!/usr/bin/env python3
"""
HW10 self-check. Writes reports/hw10/verification.json. No LLM and no Kafka are needed: every check reads the files the real
runs produced (spans, results, frozen cases) and recomputes the statistics from raw data.

    .venv/bin/python code/verify_hw10.py

A check whose artifact does not exist yet (e.g. the judge validation, which needs the hand labels committed first) is SKIPPED
with its reason, never silently passed.
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HW10, HW08 = REPO / "code" / "hw10", REPO / "code" / "hw08"
DATA, REPORT = REPO / "data" / "hw10", REPO / "reports" / "hw10"
RAW = REPORT / "raw"
SID4, SEED, VERIFY_SEED, PORT_BASE, PREFIX = 3170, 3170, 263170, 8470, "s3170"
for p in (HW10, HW08):
    sys.path.insert(0, str(p))

STAGES = {"cache_lookup", "inbox", "planner", "tasks", "writer", "drafts", "reviewer", "final", "evaluator"}
MISS_STAGES = {"cache_lookup", "inbox", "planner", "tasks", "writer", "drafts", "reviewer", "final"}
SPAN_KEYS = {"trace_id", "stage", "start", "end", "start_ms", "end_ms", "duration_ms", "status", "error"}
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

checks: list[dict] = []


class Skip(Exception):
    pass


def record(name: str, status: str, detail: str = "") -> None:
    checks.append({"check": name, "status": status, "detail": detail})
    print(f"[{status:<4}] {name}" + (f" -- {detail}" if detail else ""), flush=True)


def run(name: str, fn) -> None:
    try:
        ok, detail = fn()
        record(name, "PASS" if ok else "FAIL", detail)
    except Skip as s:
        record(name, "SKIP", str(s))
    except Exception as exc:  # noqa: BLE001
        record(name, "FAIL", f"{exc.__class__.__name__}: {exc}")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


def jload(p: Path):
    if not p.exists():
        raise Skip(f"{p.name} not generated yet")
    return json.loads(p.read_text())


def spans() -> list[dict]:
    import dash_data as dd
    s = dd.load_spans()
    if not s:
        raise Skip("no spans recorded yet")
    return s


def traces(ss: list[dict]) -> dict[str, dict[str, dict]]:
    d: dict[str, dict[str, dict]] = {}
    for s in ss:
        d.setdefault(s["trace_id"], {})[s["stage"]] = s
    return d


# ------------------------------------------------------------------------------------------------ static
def static_checks() -> None:
    need = ["code/hw08/tracing.py", "code/hw10/ingress.py", "code/hw10/messages.py", "code/hw10/judge.py", "code/hw10/evaluate_pipeline.py",
            "code/hw10/validate_judge.py", "code/hw10/build_eval_cases.py", "code/hw10/latency_experiment.py", "code/hw10/trace_examples.py",
            "code/hw10/latency_report.py", "code/hw10/dash_data.py", "code/hw10/dashboard.py", "code/hw10/agents.sh",
            "data/hw10/eval_cases.json", "data/hw10/human_labels.csv", "reports/hw10/raw/latency_runs.json", "reports/hw10/raw/trace_examples.json"]
    run("required HW10 files exist", lambda: ((m := [f for f in need if not (REPO / f).exists()]) == [], "all present" if not m else f"missing {m}"))

    def banner():
        scripts = [p for p in HW10.glob("*.py") if p.name not in ("common10.py", "dash_data.py", "dashboard.py", "judge.py", "messages.py")]
        bad = [p.name for p in scripts if "banner(" not in p.read_text()]
        return not bad, f"{len(scripts)} runnable scripts print the student name banner" if not bad else f"no banner in {bad}"

    run("student name banner in every runnable script", banner)

    def ruff():
        files_ = [str(p) for p in HW10.glob("*.py")] + [str(HW08 / n) for n in ("tracing.py", "planner.py", "writer.py", "reviewer.py")] + \
                 [str(REPO / "code/verify_hw10.py")]
        res = subprocess.run([str(REPO / ".venv/bin/ruff"), "check", *files_], cwd=REPO, capture_output=True, text=True)
        return res.returncode == 0, "ruff clean (default rules)" if res.returncode == 0 else res.stdout[-400:]

    run("ruff passes on HW10 code and the edited HW8 agents", ruff)

    def guard():
        t = (HW10 / "agents.sh").read_text()
        return "REFUSING to start" in t and "pkill -P" in t, "agents.sh refuses to start over stale agents and stops child processes"

    run("stale-agent guard present (the bug that produced stub drafts)", guard)


# ------------------------------------------------------------------------------------------------ Part 4
def tracing_checks() -> None:
    def schema():
        ss = spans()
        bad = [s for s in ss if not SPAN_KEYS <= set(s) or s["stage"] not in STAGES or s["status"] not in ("ok", "error")
               or s["end_ms"] < s["start_ms"] or abs((s["end_ms"] - s["start_ms"]) - s["duration_ms"]) > 0.01
               or not (UUID.match(s["trace_id"]) or s["trace_id"].startswith("warmup-"))]
        extra = {k for s in ss for k in s} & {"request_id", "span_id_other", "correlation_id"}
        return not bad and not extra, f"{len(ss)} spans over {len({s['trace_id'] for s in ss})} traces; every span has {sorted(SPAN_KEYS)}; trace_id is the correlation_id (UUID)"

    run("every span is structured JSON with trace_id, stage, start, end, status, error (and no second request id)", schema)

    def experiment():
        d = jload(RAW / "latency_runs.json")
        rq = d["requests"]
        t = traces(spans())
        ok_all = len(rq) == 50 and all(not r["is_cached"] for r in rq) and all(r["status"] == "approved" for r in rq)
        complete = sum(1 for r in rq if MISS_STAGES <= set(t.get(r["trace_id"], {})))
        miss_flag = sum(1 for r in rq if t.get(r["trace_id"], {}).get("cache_lookup", {}).get("is_cached") is False)
        fast = [round(r["e2e_ms"]) for r in rq if r["e2e_ms"] < 5000]
        return (ok_all and complete == 50 and miss_flag == 50 and not fast,
                f"{len(rq)} requests; cache_lookup is a MISS in {miss_flag}; {complete} complete 8-stage traces; min e2e {min(r['e2e_ms'] for r in rq) / 1000:.1f}s; "
                f"hits skipped during the run: {len(d['skipped_hits'])}" + (f"; SUSPICIOUSLY FAST (<5 s, stub agent?): {fast}" if fast else ""))

    run("4.3: 50 confirmed cache-miss requests, none served from the cache, all full real-agent traces", experiment)

    def table():
        import latency_report as lr
        fresh = lr.compute()
        saved = jload(RAW / "latency_stats.json")
        keys = ["Cache lookup", "Planner", "Writer", "Reviewer", "Queue wait (total)", "Evaluation"]
        same = all(fresh["stages"][k] == saved["stages"][k] for k in keys) and fresh["end_to_end_ms"] == saved["end_to_end_ms"]
        return same, "stage table in latency_stats.json == recomputed from spans.jsonl + latency_runs.json (p50/p95/% for all 6 rows)"

    run("4.3: p50/p95 and % table recomputed from the raw spans", table)

    def additive():
        rq = jload(RAW / "latency_runs.json")["requests"]
        t = traces(spans())
        worst = 0.0
        for r in rq:
            parts = sum(t[r["trace_id"]][s]["duration_ms"] for s in MISS_STAGES if s in t[r["trace_id"]])
            worst = max(worst, abs(parts - r["e2e_ms"]) / r["e2e_ms"])
        return worst < 0.02, f"for every request the 8 stage spans add up to end-to-end within {worst * 100:.2f}% (nothing unaccounted)"

    run("4.3: stage spans account for the end-to-end latency of each request", additive)

    def examples():
        ex = jload(RAW / "trace_examples.json")
        t = traces(spans())
        hit, miss, fail = (t[ex[k]["trace_id"]] for k in ("cache_hit", "cache_miss", "failed"))
        hit_ok = set(hit) == {"cache_lookup"} and hit["cache_lookup"]["is_cached"] is True
        miss_ok = MISS_STAGES <= set(miss) and miss["cache_lookup"]["is_cached"] is False and all(s["status"] == "ok" for s in miss.values() if s["stage"] != "evaluator")
        fail_ok = fail["writer"]["status"] == "error" and "no plan" in (fail["writer"]["error"] or "") and fail["final"]["status"] == "error"
        return hit_ok and miss_ok and fail_ok, (f"hit {ex['cache_hit']['trace_id'][:8]} (cache_lookup only, is_cached) · miss {ex['cache_miss']['trace_id'][:8]} (all 8 stages ok) · "
                                                f"failed {ex['failed']['trace_id'][:8]} (writer error: {fail['writer']['error']})")

    run("4.2: cache-hit, cache-miss and failed example traces are what they claim", examples)


# ------------------------------------------------------------------------------------------------ Parts 2 and 3
def eval_checks() -> None:
    def cases():
        cs = jload(DATA / "eval_cases.json")
        stub = [c["case_id"] for c in cs if "stub draft" in c["draft"]]
        ok = len(cs) == 20 and not stub and len({c["draft"] for c in cs}) == 20 and len({c["trace_id"] for c in cs}) == 20 \
            and all(c["final_status"] == "approved" for c in cs)
        return ok, f"{len(cs)} cases, {len({c['draft'] for c in cs})} distinct drafts, stub drafts: {len(stub)} {stub}, each with the Kafka metadata of its plan/draft/final"

    run("3.1: eval_cases.json holds 20 real Writer drafts (no stub output)", cases)

    def eval_scores():
        res = jload(RAW / "eval_results.json")
        ok = [v for v in res.values() if v["status"] == "ok"]
        if not ok:
            raise Skip("no evaluated requests yet")
        ss = spans()
        ev = {s["trace_id"] for s in ss if s["stage"] == "evaluator"}
        good = all(1 <= v[k]["score"] <= 5 for v in ok for k in ("plan_quality", "writer_helpfulness", "final_helpfulness"))
        diff = all(v["final_vs_draft"]["difference"] == v["final_helpfulness"]["score"] - v["writer_helpfulness"]["score"] for v in ok)
        orig = all({"plan", "draft", "final"} <= set(v["inputs"]) and v["inputs"]["draft"]["meta"]["offset"] is not None for v in ok)
        traced = all(v["trace_id"] in ev for v in ok)
        return good and diff and orig and traced, (f"{len(ok)} evaluated; scores all 1-5; difference == final - draft; original messages + Kafka offsets kept; "
                                                   f"evaluator span present for all")

    run("2: evaluator results (scale 1-5, difference arithmetic, originals kept, evaluator spans)", eval_scores)

    def frozen():
        runs_f = RAW / "judge_runs.json"
        if not runs_f.exists():
            raise Skip("judge has not been run yet")
        rows = []
        for f in ("data/hw10/eval_cases.json", "data/hw10/human_labels.csv"):
            first = git("log", "--diff-filter=A", "--format=%ct", "--", f).splitlines()
            if not first:
                return False, f"{f} was never committed"
            rows.append((f, int(first[-1]), git("status", "--porcelain", "--", f) == ""))
        t_judge = int(runs_f.stat().st_mtime)
        ok = all(t < t_judge and clean for _, t, clean in rows)
        return ok, "; ".join(f"{f.split('/')[-1]} committed {t_judge - t}s before the judge output, unmodified={c}" for f, t, c in rows)

    run("3.1: cases and human labels committed (and unmodified) BEFORE the judge scores existed", frozen)

    def labels():
        rows = list(csv.DictReader((DATA / "human_labels.csv").open()))
        vals = [r["human_score"].strip() for r in rows]
        if not any(vals):
            raise Skip("human labels not filled in yet (hand-assign 1-5 in data/hw10/human_labels.csv)")
        ok = len(rows) == 20 and all(v in ("1", "2", "3", "4", "5") for v in vals)
        return ok, f"{len(rows)} labels, all integers 1-5; distribution {dict(sorted((k, vals.count(k)) for k in set(vals)))}"

    run("3.1: 20 hand-assigned human labels, each 1-5", labels)

    def judge_stats():
        saved = jload(RAW / "judge_validation.json")
        from validate_judge import compute_stats, load_inputs
        cases_, human = load_inputs()
        runs_raw = jload(RAW / "judge_runs.json")["runs"]
        runs = [{k: v["score"] for k, v in r["cases"].items()} for r in runs_raw]
        fresh = compute_stats(cases_, human, runs)
        keys = ["part_3_2_run1_vs_human", "repeatability", "human_label_distribution", "n_cases", "n_runs"]
        same = all(fresh[k] == saved[k] for k in keys)
        p, r = fresh["part_3_2_run1_vs_human"], fresh["repeatability"]
        return same and len(runs) == 3, (f"recomputed from raw per-case scores: Spearman {p['spearman']}, MAD {p['mean_abs_diff']}, "
                                         f"{r['cases_whose_score_changed_across_runs']}/{r['cases_compared']} cases changed over 3 runs")

    run("3.2/3.3: Spearman, mean abs difference and repeatability recomputed from raw data", judge_stats)


def dashboard_check() -> None:
    def dash():
        from streamlit.testing.v1 import AppTest
        at = AppTest.from_file(str(HW10 / "dashboard.py"), default_timeout=90).run()
        errs = len(at.exception)
        for page in ("Evaluation", "Trace lookup"):
            at.sidebar.radio[0].set_value(page).run()
            errs += len(at.exception)
        ex = json.loads((RAW / "trace_examples.json").read_text())
        for k in ("cache_hit", "cache_miss", "failed"):
            at.sidebar.radio[0].set_value("Trace lookup").run()
            at.text_input[0].set_value(ex[k]["trace_id"]).run()
            errs += len(at.exception)
            if "HIT" not in at.subheader[0].value and "MISS" not in at.subheader[0].value:
                errs += 1
        return errs == 0, "Summary, Evaluation and Trace lookup pages render with no exception; the 3 example traces load and show a HIT/MISS badge"

    run("1: Streamlit dashboard renders all three pages and the three example traces", dash)


def main() -> int:
    static_checks()
    for fn in (tracing_checks, eval_checks, dashboard_check):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            record(fn.__name__, "FAIL", f"{exc.__class__.__name__}: {exc}")
    passed = sum(c["status"] == "PASS" for c in checks)
    failed = sum(c["status"] == "FAIL" for c in checks)
    skipped = sum(c["status"] == "SKIP" for c in checks)
    out = {"homework": 10, "SID4": SID4, "PORT_BASE": PORT_BASE, "PREFIX": PREFIX, "SEED": SEED, "VERIFY_SEED": VERIFY_SEED, "DOMAIN_ID": 2,
           "commit": git("rev-parse", "HEAD"), "working_tree_clean": git("status", "--porcelain", "--untracked-files=no") == "",
           "model_configuration": {"agents": "qwen3:8b via Ollama (CPU)", "judge": "qwen3:8b, DeepEval GEval, temperature 0, seed 3170, 1-5 rubric",
                                   "cache": "Redis Stack 7.4, threshold 0.95 (the HW9 shipped value)", "broker": "apache/kafka 3.8.0 (KRaft)"},
           "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "passed": passed, "failed": failed, "skipped": skipped, "total_checks": len(checks), "checks": checks}
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "verification.json").write_text(json.dumps(out, indent=2))
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped of {len(checks)} -> {REPORT / 'verification.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
