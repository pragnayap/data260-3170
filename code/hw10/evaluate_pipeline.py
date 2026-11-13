#!/usr/bin/env python3
# ruff: noqa: I001
"""
HW10 Part 2 - evaluate requests that already went through the Kafka pipeline.

    HW10_TRACE=1 python evaluate_pipeline.py --ids <trace_id> [<trace_id> ...]
    HW10_TRACE=1 python evaluate_pipeline.py --file ../../reports/hw10/raw/latency_runs.json [--limit N]

For each trace_id (= correlation_id) it
  1. collects the Planner plan (s3170_tasks), Writer draft (s3170_drafts) and Reviewer final (s3170_final) with messages.collect,
     keeping the original bodies and Kafka metadata;
  2. scores with DeepEval GEval on the local judge, all on the SAME 1-5 scale:
       Plan Quality (plan) | Writer Helpfulness (draft) | Final Answer Helpfulness (final answer)
  3. computes Final-vs-Draft Improvement = final score - draft score, with an interpretation;
  4. writes one `evaluator` span per trace (so evaluation latency shows up in the trace and in the p50/p95 table).
Results go to reports/hw10/raw/eval_results.json (keyed by trace_id; re-running updates, never duplicates).
Bounded: a missing message or an unavailable judge is recorded as an error for that trace and the run continues.
"""
from __future__ import annotations

import json
import sys
import time

import common10 as c
from judge import JudgeError, LocalJudge, make_metrics, score
from messages import collect
from tracing import now_ms, write_span

OUT = c.RAW / "eval_results.json"


def interpret(draft: str, final: str | None, status: str, d: int, f: int) -> str:
    if status != "approved" or final is None:
        return "The Reviewer rejected the draft, so there is no final answer to compare."
    diff = f - d
    if (draft or "").strip() == (final or "").strip():
        base = ("The final answer is word-for-word the Writer's draft: the Reviewer in this pipeline is rule-based "
                "(length and placeholder checks) and never edits text, so it cannot improve an answer.")
        return base + (" Both scored the same, as expected." if diff == 0 else
                       f" The score difference ({diff:+d}) is therefore judge noise on identical text, not an improvement.")
    return (f"The final answer differs from the draft; judge score changed by {diff:+d}."
            + (" Improved." if diff > 0 else " Not improved." if diff == 0 else " Got worse."))


def evaluate(trace_ids: list[str]) -> dict[str, dict]:
    msgs = collect(set(trace_ids), timeout=90)
    judge = LocalJudge()
    metrics = make_metrics(judge)
    results: dict[str, dict] = json.loads(OUT.read_text()) if OUT.exists() else {}
    for n, tid in enumerate(trace_ids, 1):
        t0 = now_ms()
        m = msgs.get(tid, {})
        res: dict = {"trace_id": tid, "status": "ok", "error": None}
        try:
            missing = [k for k in ("plan", "draft", "final") if k not in m]
            if missing:
                raise ValueError(f"missing {missing} message(s) for this correlation_id")
            question = m["plan"]["body"].get("question") or m["draft"]["body"].get("question")
            plan_text = "\n".join(f"{i}. {s}" for i, s in enumerate(m["plan"]["body"].get("plan") or [], 1))
            draft, final = m["draft"]["body"].get("draft", ""), m["final"]["body"].get("answer")
            fstatus = m["final"]["body"].get("status", "")
            plan_s, plan_r = score(metrics["plan_quality"], question, plan_text)
            draft_s, draft_r = score(metrics["writer_helpfulness"], question, draft)
            if final is None:
                final_s, final_r = None, "no final answer (draft rejected)"
            else:
                final_s, final_r = score(metrics["final_helpfulness"], question, final)
            res.update(question=question, plan=m["plan"]["body"].get("plan"), draft=draft, final_answer=final,
                       final_status=fstatus, plan_quality={"score": plan_s, "reason": plan_r},
                       writer_helpfulness={"score": draft_s, "reason": draft_r, "trace_id": tid},
                       final_helpfulness={"score": final_s, "reason": final_r, "final_answer": final},
                       final_vs_draft={"draft_score": draft_s, "final_score": final_s,
                                       "difference": None if final_s is None else final_s - draft_s,
                                       "interpretation": interpret(draft, final, fstatus, draft_s, final_s or draft_s)},
                       inputs={k: m[k] for k in ("plan", "draft", "final")},      # originals + Kafka metadata
                       judge=judge.get_model_name())
        except (JudgeError, ValueError, KeyError) as exc:
            res.update(status="error", error=f"{type(exc).__name__}: {exc}")
        end = now_ms()
        res["evaluation_ms"] = round(end - t0, 1)
        write_span(tid, "evaluator", t0, end, status=res["status"], error=res["error"])
        results[tid] = res
        OUT.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        ok = res["status"] == "ok"
        print(f"[{n}/{len(trace_ids)}] {tid[:8]}  {'plan=%s draft=%s final=%s' % (res['plan_quality']['score'], res['writer_helpfulness']['score'], res['final_helpfulness']['score']) if ok else res['error']}"
              f"  ({res['evaluation_ms'] / 1000:.1f}s)", flush=True)
    return results


def main() -> int:
    c.banner("evaluate_pipeline.py")
    args = sys.argv[1:]
    ids: list[str] = []
    if "--ids" in args:
        ids = [a for a in args[args.index("--ids") + 1:] if not a.startswith("--")]
    if "--file" in args:
        data = json.loads(open(args[args.index("--file") + 1]).read())
        ids = [r["trace_id"] for r in (data["requests"] if isinstance(data, dict) else data) if r.get("status") == "approved"]
    if "--limit" in args:
        ids = ids[: int(args[args.index("--limit") + 1])]
    if not ids:
        print("no trace ids given (use --ids ... or --file ...)")
        return 2
    t0 = time.time()
    res = evaluate(ids)
    bad = [t for t in ids if res[t]["status"] != "ok"]
    print(f"evaluated {len(ids) - len(bad)}/{len(ids)} in {time.time() - t0:.0f}s -> {OUT}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
