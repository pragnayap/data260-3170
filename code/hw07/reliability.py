#!/usr/bin/env python3
"""
HW7 Part 2.III - tool-use reliability over 20 attempts of the fixed tasks A/B/C.

Same model settings for every attempt (qwen3:8b, temperature 0.7 - nonzero so repeats
can differ, otherwise 20 identical runs would measure nothing).

Unit of measure = one model "decision turn" (a tool call or the final answer):
    before repair : the turn's FIRST reply was well-formed
    after repair  : the turn ended well-formed, counting the reprompt path
A turn can fail first and still be repaired, so after >= before.

Attempt-level failure classes (an attempt that did not pass its task check):
    malformed_arguments | unknown_tool | text_instead_of_tool  - an invalid turn the
                          repair path could not fix (run stopped repair_exhausted)
    lost_chain          - every reply was well-formed but the required multi-step
                          chain / grounded answer was not produced
"""

from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import run_agent  # noqa: E402
from tasks import TASKS  # noqa: E402

from model_client import ModelClient  # noqa: E402

RAW = Path(__file__).resolve().parents[2] / "reports" / "hw07" / "raw"
PLAN = ["A"] * 7 + ["B"] * 7 + ["C"] * 6   # 20 attempts
TEMPERATURE = 0.7


def classify(run, ok: bool) -> str | None:
    if ok:
        return None
    unrepaired = [t for t in run.turns if not t["final_ok"]]
    if unrepaired:
        return unrepaired[0]["problem"]
    return "lost_chain"


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    model = ModelClient(temperature=TEMPERATURE)
    print(f"# HW7 reliability - {time.strftime('%Y-%m-%d %H:%M:%S')} - Pragnaya Priyadarshini "
          f"SID4 3170 - {model.model_name} temperature {TEMPERATURE}", flush=True)
    rows = []
    for i, label in enumerate(PLAN, 1):
        prompt, check = TASKS[label]
        print(f"\n=== attempt {i}/20 task {label}", flush=True)
        run = run_agent(prompt, model=model)
        ok, why = check(run)
        turns = run.turns
        rows.append({
            "attempt": i, "task": label, "passed": ok, "check": why,
            "stop_reason": run.stop_reason, "turns": len(turns),
            "turns_first_ok": sum(t["first_ok"] for t in turns),
            "turns_final_ok": sum(t["final_ok"] for t in turns),
            "repairs": sum(t["repairs"] for t in turns),
            "failure_class": classify(run, ok),
            "problems": [t["problem"] for t in turns if t["problem"]],
            "tool_calls": run.tool_calls, "tokens": run.tokens,
            "elapsed_ms": round(run.elapsed_ms),
        })
        print(f"  [check] {'PASS' if ok else 'FAIL'} - {why}", flush=True)

    (RAW / "reliability_attempts.json").write_text(json.dumps(rows, indent=2))
    with (RAW / "reliability_attempts.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows({**r, "problems": "|".join(r["problems"])} for r in rows)

    turns = sum(r["turns"] for r in rows)
    first, final = sum(r["turns_first_ok"] for r in rows), sum(r["turns_final_ok"] for r in rows)
    fails = Counter(r["failure_class"] for r in rows if r["failure_class"])
    problems = Counter(p for r in rows for p in r["problems"])
    summary = {
        "attempts": len(rows), "temperature": TEMPERATURE, "model": model.model_name,
        "turns": turns,
        "well_formed_before_repair": f"{first}/{turns} = {first / turns:.1%}",
        "well_formed_after_repair": f"{final}/{turns} = {final / turns:.1%}",
        "task_pass": f"{sum(r['passed'] for r in rows)}/{len(rows)}",
        "invalid_first_replies_by_type": dict(problems),
        "unrecovered_failures_by_class": dict(fails),
    }
    (RAW / "reliability_summary.json").write_text(json.dumps(summary, indent=2))
    print("\n" + json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
