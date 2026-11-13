#!/usr/bin/env python3
# ruff: noqa: I001
"""
HW10 Part 4.3 - 50 CONFIRMED cache-miss requests through the full path (cache lookup -> Kafka agents -> final).

    HW10_TRACE=1 python latency_experiment.py [--n 50]

Questions come from a fixed pool of distinct transit-incident questions (seeded shuffle). Each request goes through the real
ingress. A request whose cache lookup comes back as a HIT is NOT counted (logged under skipped_hits) and the next question is
used, so the 50 reported requests are all verified misses. The cache namespace is reset first and is filled as the run goes
(every miss is stored), which is exactly what makes this a fair test of the shipped 0.95 threshold.

Writes reports/hw10/raw/latency_runs.json. Spans go to data/hw10/spans/spans.jsonl (agents must be running with HW10_TRACE=1).
"""
from __future__ import annotations

import json
import random
import sys
import time

import common10 as c
from ingress import Ingress

SUBJECTS = [
    "a commuter train stopped between stations", "a city bus that broke down on a highway", "a light rail line suspended by a signal fault",
    "a subway platform that is overcrowded during rush hour", "a tram that struck a parked car", "a ferry terminal with a cancelled sailing",
    "a station elevator that is out of service", "a bus stop with a broken shelter and a missing light", "a delayed airport shuttle service",
    "a cable car stopped by a power outage", "an icy bus route during a winter storm", "a train door that will not close",
    "a crowded bus with a medical emergency on board", "a rail crossing where a vehicle is stuck on the tracks",
    "a bus driver running far behind schedule", "a flooded subway entrance", "a station escalator that stops suddenly",
    "a paratransit van that arrives late for a pickup",
]
FRAMES = [
    "What should riders do when they encounter {s}?",
    "How should a transit agency communicate with passengers about {s}?",
    "What are the main safety risks of {s}?",
    "Who is responsible for resolving {s}, and how?",
    "How can {s} be prevented from happening again?",
]


def pool(seed: int = c.SEED) -> list[str]:
    qs = [f.format(s=s) for s in SUBJECTS for f in FRAMES]
    random.Random(seed).shuffle(qs)
    return qs


def main() -> int:
    c.banner("latency_experiment.py")
    n = int(sys.argv[sys.argv.index("--n") + 1]) if "--n" in sys.argv else 50
    ing = Ingress()
    ing.cache.reset()
    ing.cache.create_index()
    ing.ask("warm-up: what is the purpose of a transit incident report?", use_cache=False, trace_id="warmup-" + str(int(time.time())))
    print("warm-up done (model + cache index loaded; its trace id starts with 'warmup-' and is excluded)", flush=True)
    requests, skipped = [], []
    t_run = time.time()
    try:
        for q in pool():
            if len(requests) >= n:
                break
            r = ing.ask(q, timeout=300)
            row = {"trace_id": r["trace_id"], "question": q, "status": r["status"], "is_cached": r["is_cached"],
                   "similarity": r["similarity"], "e2e_ms": r["e2e_ms"]}
            if r["is_cached"]:
                skipped.append(row)
                print(f"   skipped (cache HIT, similarity {r['similarity']}): {q}", flush=True)
                continue
            requests.append(row)
            print(f"[{len(requests):02d}/{n}] {r['status']:<9} {r['e2e_ms'] / 1000:5.1f}s  sim={r['similarity']}  {q}", flush=True)
            (c.RAW / "latency_runs.json").write_text(json.dumps({"requests": requests, "skipped_hits": skipped,
                                                               "confirmed_misses": len(requests)}, indent=2))
    finally:
        ing.close()
    out = {"requests": requests, "skipped_hits": skipped, "confirmed_misses": len(requests),
           "all_confirmed_misses": all(not r["is_cached"] for r in requests), "threshold": c.SHIPPED_THRESHOLD,
           "wall_clock_s": round(time.time() - t_run, 1)}
    (c.RAW / "latency_runs.json").write_text(json.dumps(out, indent=2))
    print(f"done: {len(requests)} confirmed misses, {len(skipped)} skipped hits, {out['wall_clock_s']:.0f}s")
    return 0 if len(requests) >= n else 1


if __name__ == "__main__":
    sys.exit(main())
