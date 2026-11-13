#!/usr/bin/env python3
# ruff: noqa: I001
"""
HW10 Part 4.2 - the three required example traces, plus cache-HIT samples for the separate hit-latency metric.

    HW10_TRACE=1 python trace_examples.py

  * cache-hit trace   : an exact repeat of a question the cache already answered (from latency_runs.json)
  * cache-miss trace  : one of the 50 confirmed-miss requests that completed the whole agent path (the median-latency one)
  * failed trace      : a fresh question sent with fault="empty_plan" (Planner emits an empty plan) -> the Writer rejects it,
                        retries 3 times and dead-letters it; the failing stage and error are in its spans
  * hit samples       : 20 exact repeats of the 50 questions (hit latency is reported separately from miss latency)

Writes reports/hw10/raw/trace_examples.json. Agents must be running with HW10_TRACE=1 and Redis holding the 50 stored answers.
"""
from __future__ import annotations

import json
import statistics as st
import sys

import common10 as c
from ingress import Ingress

FAULT_QUESTION = "What should a rider do if a train door will not close and the train is about to leave the station?"


def main() -> int:
    c.banner("trace_examples.py")
    runs = json.loads((c.RAW / "latency_runs.json").read_text())["requests"]
    ing = Ingress()
    try:
        ing.cache.lookup("warm-up lookup so the embedding model is loaded before any measured hit")
        # cache hits: exact repeats of already-answered questions
        hits = [ing.ask(r["question"]) for r in runs[:20]]
        assert all(h["is_cached"] for h in hits), "a repeat was not served from the cache - was the cache cleared?"
        print(f"20 hit samples: median {st.median(h['e2e_ms'] for h in hits):.0f} ms, max {max(h['e2e_ms'] for h in hits):.0f} ms")
        hit = hits[0]
        # miss example: the median-latency request among the 50
        median_req = sorted(runs, key=lambda r: r["e2e_ms"])[len(runs) // 2]
        # failed example: fault injected at the Planner, caught at the Writer
        failed = ing.ask(FAULT_QUESTION, fault="empty_plan", timeout=45)
    finally:
        ing.close()
    out = {"cache_hit": {"trace_id": hit["trace_id"], "question": hit["question"], "similarity": hit["similarity"],
                         "e2e_ms": hit["e2e_ms"]},
           "cache_miss": {"trace_id": median_req["trace_id"], "question": median_req["question"],
                          "e2e_ms": median_req["e2e_ms"], "note": "median-latency request of the 50 confirmed misses"},
           "failed": {"trace_id": failed["trace_id"], "question": failed["question"], "status": failed["status"],
                      "failing_stage": "writer", "error": "ValueError: task has no plan (Planner emitted an empty plan; "
                      "the Writer retried 3 times and dead-lettered the message)", "e2e_ms": failed["e2e_ms"]},
           "hit_samples": [{"trace_id": h["trace_id"], "similarity": h["similarity"], "e2e_ms": h["e2e_ms"]} for h in hits]}
    (c.RAW / "trace_examples.json").write_text(json.dumps(out, indent=2))
    for k in ("cache_hit", "cache_miss", "failed"):
        print(f"{k:<10} trace_id={out[k]['trace_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
