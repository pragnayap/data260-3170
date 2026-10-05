#!/usr/bin/env python3
"""
HW5 Part 3 - the seeded fault-injection experiment and the three retry demos.

Two modes.

    make retry-demo          the three behaviours the spec asks to see:
                             success first try, success after a retry, and a
                             clean error after all retries are spent.

    make fault-hw05          the measurement: 50 calls at each of 0%, 20% and
                             50% injected failure = 150 calls, driven by
                             VERIFY_SEED. Writes every call to
                             reports/hw05/raw/fault_injection.csv and prints
                             the results table for METRICS.md.

Reproducibility
    VERIFY_SEED = 260000 + SID4 = 263170. Each rate gets its own
    random.Random(VERIFY_SEED), so the three runs are independent of each
    other but each one is identical on every execution. Re-run the command and
    the CSV is byte-identical apart from the timing columns.

    Why timings differ: the success/failure sequence is seeded, but wall-clock
    latency is measured on a real machine against a real database. The
    attempts column reproduces exactly; the latency_ms column does not, and
    should not be expected to.

The operation under test is search_incidents -- a real tool against real
MySQL, with faults injected around it. Use --offline to swap in a stub if the
database is not running; the fault sequence is identical either way, only the
underlying latency changes.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import random
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(
    level=logging.WARNING,
    stream=sys.stderr,
    format="%(levelname)s %(name)s: %(message)s",
)

from envelope import Envelope, ok  # noqa: E402
from retry import (  # noqa: E402
    INTERACTIVE_POLICY,
    CallResult,
    FaultInjector,
    RetryPolicy,
    ScriptedFailures,
    call_with_retry,
    percentile,
)

SID4 = 3170
VERIFY_SEED = 260000 + SID4          # 263170, per the Section 0 table
FAILURE_RATES = (0.0, 0.20, 0.50)
CALLS_PER_RATE = 50

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "reports" / "hw05" / "raw"

QUERY = "Downtown"


# --- the operation under test ---------------------------------------------

def _real_search() -> Envelope:
    import transit_tools

    return transit_tools.search_incidents(QUERY, limit=5)


def _offline_search() -> Envelope:
    """Stand-in with a realistic fixed cost, for runs without MySQL."""
    time.sleep(0.004)
    return ok({"query": QUERY, "count": 2, "results": [], "offline": True})


# --- the three demonstrations ---------------------------------------------

def run_demos(target, policy: RetryPolicy) -> None:
    print("=" * 68)
    print("HW5 Part 3 - retry policy demonstrations")
    print(f"policy: max_attempts={policy.max_attempts}  "
          f"base_delay={policy.base_delay_s}s  max_delay={policy.max_delay_s}s  "
          f"timeout={policy.timeout_s}s")
    print("=" * 68)

    rng = random.Random(VERIFY_SEED)

    # 1 - success on the first attempt
    print("\n[1] Success on the first attempt")
    result = call_with_retry(ScriptedFailures(target, fail_on=[]), policy=policy, rng=rng)
    print(result.trace())
    print(f"    => ok={result.ok}  attempts={result.attempt_count}  "
          f"total={result.total_ms:.1f}ms")

    # 2 - fail once, then succeed
    print("\n[2] Failure on the first attempt, success after a retry")
    result = call_with_retry(ScriptedFailures(target, fail_on=[1]), policy=policy, rng=rng)
    print(result.trace())
    print(f"    => ok={result.ok}  attempts={result.attempt_count}  "
          f"total={result.total_ms:.1f}ms")

    # 3 - every attempt fails; a clean error, no crash
    print("\n[3] Failure after all allowed retries - clean error, no exception")
    always = ScriptedFailures(target, fail_on=list(range(1, policy.max_attempts + 1)))
    result = call_with_retry(always, policy=policy, rng=rng)
    print(result.trace())
    print(f"    => ok={result.ok}  attempts={result.attempt_count}  "
          f"total={result.total_ms:.1f}ms")
    print(f"    envelope: {json.dumps(result.envelope)}")

    # 4 - not required, but the design point worth showing: a rejected
    #     argument is NOT retried, because it cannot succeed later.
    print("\n[4] (bonus) A rejected argument is returned at once, not retried")
    import transit_tools

    bad = call_with_retry(
        transit_tools.search_incidents, "Downtown", policy=policy, rng=rng, limit=0
    )
    print(bad.trace())
    print(f"    => ok={bad.ok}  attempts={bad.attempt_count} "
          f"(retrying would re-reject identically)")
    print()


# --- the 150-call experiment ----------------------------------------------

def run_experiment(target, policy: RetryPolicy) -> list[dict]:
    rows: list[dict] = []

    for rate in FAILURE_RATES:
        # A fresh Random per rate, all from VERIFY_SEED: each rate is
        # reproducible on its own and independent of the others.
        injector = FaultInjector(target, failure_rate=rate, seed=VERIFY_SEED)
        jitter_rng = random.Random(VERIFY_SEED + 1)

        print(f"\n--- injected failure rate {rate:.0%} "
              f"({CALLS_PER_RATE} calls) ---", flush=True)

        for i in range(1, CALLS_PER_RATE + 1):
            result: CallResult = call_with_retry(
                injector, policy=policy, rng=jitter_rng
            )
            rows.append(
                {
                    "seed": VERIFY_SEED,
                    "failure_rate": rate,
                    "call_index": i,
                    "attempts": result.attempt_count,
                    "ok": int(result.ok),
                    "latency_ms": round(result.total_ms, 3),
                    "outcomes": "|".join(a.outcome for a in result.attempts),
                    "error": result.envelope["error"] or "",
                }
            )
            if i % 10 == 0:
                print(f"    {i}/{CALLS_PER_RATE}", flush=True)

    return rows


def summarize(rows: list[dict]) -> list[dict]:
    out = []
    for rate in FAILURE_RATES:
        group = [r for r in rows if r["failure_rate"] == rate]
        latencies = [r["latency_ms"] for r in group]
        successes = sum(r["ok"] for r in group)
        out.append(
            {
                "injected_failure_rate": rate,
                "calls": len(group),
                "successes": successes,
                "success_rate": successes / len(group),
                "mean_latency_ms": round(statistics.fmean(latencies), 2),
                "p99_latency_ms": round(percentile(latencies, 99), 2),
                "median_latency_ms": round(statistics.median(latencies), 2),
                "mean_attempts": round(statistics.fmean(r["attempts"] for r in group), 2),
                "total_attempts": sum(r["attempts"] for r in group),
            }
        )
    return out


def write_outputs(rows: list[dict], summary: list[dict], policy: RetryPolicy) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    csv_path = RAW_DIR / "fault_injection.csv"
    with csv_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    json_path = RAW_DIR / "fault_injection_summary.json"
    json_path.write_text(
        json.dumps(
            {
                "seed": VERIFY_SEED,
                "sid4": SID4,
                "calls_per_rate": CALLS_PER_RATE,
                "total_calls": len(rows),
                "policy": {
                    "max_attempts": policy.max_attempts,
                    "base_delay_s": policy.base_delay_s,
                    "max_delay_s": policy.max_delay_s,
                    "timeout_s": policy.timeout_s,
                    "jitter": policy.jitter,
                },
                "results": summary,
            },
            indent=2,
        )
        + "\n"
    )

    print(f"\nwrote {csv_path.relative_to(REPO_ROOT)}  ({len(rows)} rows)")
    print(f"wrote {json_path.relative_to(REPO_ROOT)}")


def print_table(summary: list[dict]) -> None:
    print("\n" + "=" * 74)
    print("HW5 Part 3 results table  (paste into METRICS.md and the report)")
    print("=" * 74)
    print(f"\nVERIFY_SEED = {VERIFY_SEED}   calls per rate = {CALLS_PER_RATE}   "
          f"total = {CALLS_PER_RATE * len(FAILURE_RATES)}\n")
    print("| Injected failure rate | Success rate | Mean latency (ms) | p99 latency (ms) |")
    print("|---|---|---|---|")
    for s in summary:
        print(
            f"| {s['injected_failure_rate']:.0%} "
            f"| {s['success_rate']:.0%} "
            f"| {s['mean_latency_ms']:.2f} "
            f"| {s['p99_latency_ms']:.2f} |"
        )
    print("\nSupporting detail (not required, but it explains the latency column):\n")
    print("| Rate | Median (ms) | Mean attempts | Total attempts for 50 calls |")
    print("|---|---|---|---|")
    for s in summary:
        print(
            f"| {s['injected_failure_rate']:.0%} "
            f"| {s['median_latency_ms']:.2f} "
            f"| {s['mean_attempts']:.2f} "
            f"| {s['total_attempts']} |"
        )
    print("\nNote: p99 over 50 samples is the nearest-rank 50th value, i.e. the")
    print("maximum. 50 calls cannot resolve a true 99th percentile; the number")
    print("is reported as the spec asks, with that caveat stated.")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="HW5 Part 3 fault injection")
    parser.add_argument("--demo", action="store_true",
                        help="run the three retry demonstrations instead")
    parser.add_argument("--offline", action="store_true",
                        help="use a stub instead of the real DB-backed tool")
    args = parser.parse_args()

    target = _offline_search if args.offline else _real_search
    policy = INTERACTIVE_POLICY

    if args.demo:
        run_demos(target, policy)
        return

    print(f"HW5 Part 3 - fault injection, VERIFY_SEED={VERIFY_SEED}")
    print(f"operation: search_incidents({QUERY!r}, limit=5)"
          f"{'  [offline stub]' if args.offline else ''}")
    started = time.perf_counter()

    rows = run_experiment(target, policy)
    summary = summarize(rows)
    write_outputs(rows, summary, policy)
    print_table(summary)

    print(f"done in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
