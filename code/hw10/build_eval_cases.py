#!/usr/bin/env python3
# ruff: noqa: I001
"""
HW10 Part 3.1 - build the 20 frozen evaluation cases from the REAL pipeline.

Each question goes through the Kafka path (Planner -> Writer -> Reviewer) with the cache bypassed; the plan and the
Writer's draft are then read back from s3170_tasks / s3170_drafts by correlation_id (messages.collect).
Writes data/hw10/eval_cases.json (frozen once committed) and an empty human_labels.csv for YOU to fill in by hand.

The questions are fixed in this file BEFORE any judge exists. They deliberately mix: general rider/agency advice,
questions that need database facts the Writer cannot see (it has no DB access), and off-topic or vague prompts,
so that helpfulness genuinely varies across the 20 drafts.

Needs: Kafka up and the agents running with the real model:  code/hw10/agents.sh start
"""
from __future__ import annotations

import csv
import json
import sys
import time

import common10 as c
from ingress import Ingress
from messages import collect

QUESTIONS = [
    ("general",   "What should a rider do when their bus is cancelled and the next one is an hour away?"),
    ("general",   "How should a transit agency respond to a mechanical failure on a train stopped inside a tunnel?"),
    ("general",   "What information should a rider include when reporting a safety hazard at a bus stop?"),
    ("general",   "What are common causes of delays on light rail lines?"),
    ("general",   "Explain the difference between a delay incident and a mechanical failure incident."),
    ("general",   "What steps should a bus driver take after a minor collision with a car?"),
    ("general",   "How can a transit agency reduce the number of accident-collision incidents?"),
    ("needs-data", "What is the on-time performance of route R-0030 this month?"),
    ("needs-data", "Which agency operates route R-0045, and how many incidents has it had?"),
    ("needs-data", "How many safety hazard incidents were reported on the Caltrain line last month?"),
    ("off-topic", "What is the capital of France?"),
    ("off-topic", "Write a short poem about my cat."),
    ("vague",     "What should I do?"),
    ("general",   "Summarize the process for filing a complaint about a late train."),
    ("general",   "Why do buses bunch together, and what can riders do about it?"),
    ("general",   "What emergency safety equipment should every subway car have?"),
    ("general",   "How should riders who use wheelchairs be assisted when a station elevator is out of service?"),
    ("general",   "What does the incident category 'Accident-Collision' mean?"),
    ("general",   "Give three tips for staying safe at a transit station late at night."),
    ("general",   "How long does it usually take to investigate a transit accident?"),
]


def main() -> int:
    c.banner("build_eval_cases.py")
    raw_path = c.DATA / "eval_cases_raw.jsonl"        # progress file: a crash does not lose finished cases
    done = {}
    if raw_path.exists():
        for ln in raw_path.read_text().splitlines():
            r = json.loads(ln)
            if r.get("status") == "approved":                 # a failed or timed-out request is redone, never reused
                done[r["question"]] = r
    ing = Ingress()
    try:
        for i, (kind, q) in enumerate(QUESTIONS, 1):
            if q in done:
                print(f"[{i:02d}/20] cached  {q}")
                continue
            t0 = time.time()
            r = ing.ask(q, use_cache=False, timeout=300)
            row = {"kind": kind, "question": q, "trace_id": r["trace_id"], "status": r["status"],
                   "e2e_ms": r["e2e_ms"]}
            with raw_path.open("a") as fh:
                fh.write(json.dumps(row) + "\n")
            done[q] = row
            print(f"[{i:02d}/20] {r['status']:<9} {time.time() - t0:5.1f}s  {q}", flush=True)
    finally:
        ing.close()

    ids = {r["trace_id"] for r in done.values()}
    msgs = collect(ids, timeout=90)
    cases = []
    for i, (kind, q) in enumerate(QUESTIONS, 1):
        r = done[q]
        m = msgs.get(r["trace_id"], {})
        if not all(k in m for k in ("plan", "draft", "final")):
            print(f"WARNING: {r['trace_id']} is missing {[k for k in ('plan', 'draft', 'final') if k not in m]}")
            continue
        cases.append({"case_id": f"E{i:02d}", "kind": kind, "trace_id": r["trace_id"], "question": q,
                      "plan": m["plan"]["body"].get("plan"), "draft": m["draft"]["body"].get("draft"),
                      "writer": m["draft"]["body"].get("writer"), "final_status": m["final"]["body"].get("status"),
                      "model": "qwen3:8b (via Ollama, temperature 0)",
                      "kafka": {k: m[k]["meta"] for k in ("plan", "draft", "final")}})
    (c.DATA / "eval_cases.json").write_text(json.dumps(cases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    labels_path = c.DATA / "human_labels.csv"
    existing: dict[str, str] = {}
    if labels_path.exists():                              # NEVER wipe hand-assigned labels
        with labels_path.open(newline="") as fh:
            existing = {r["case_id"]: (r.get("human_score") or "") for r in csv.DictReader(fh)}
    with labels_path.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["case_id", "human_score"])
        for case in cases:
            w.writerow([case["case_id"], existing.get(case["case_id"], "")])
    print(f"\nwrote {len(cases)} cases -> data/hw10/eval_cases.json ; empty labels -> data/hw10/human_labels.csv")
    return 0 if len(cases) == 20 else 1


if __name__ == "__main__":
    sys.exit(main())
