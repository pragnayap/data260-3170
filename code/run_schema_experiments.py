"""
HW2 Part 4 - Schema validation and loop-safety experiments.

Three experiments, all against the graph in agents_graph.py:

  schema       (4.3)  30 runs on the frozen input, each classified as
                      valid first attempt / after 1 retry / after 2+ retries /
                      abandoned at the turn ceiling.
  ceiling      (4.4)  20 runs at turn_ceiling=2 and 20 at turn_ceiling=10 on the
                      same frozen input; completion rate and mean latency each.
  adversarial  (4.5)  5 runs on the adversarial input; reports the observed
                      ceiling-hit rate rather than assuming it is deterministic.

One ModelClient and one compiled graph are shared across every run so Ollama
keeps qwen3:8b resident. A cold call costs ~26s against ~9s warm, so rebuilding
per run would roughly quadruple the wall-clock time.

Every run is appended to raw/runs.jsonl as it finishes, so an interrupted batch
can be inspected (and the finished runs kept) instead of lost.

Usage:
  caffeinate -i python code/run_schema_experiments.py            # all three
  caffeinate -i python code/run_schema_experiments.py --only schema
  python code/run_schema_experiments.py --only schema --runs 3   # smoke test
"""

import argparse
import csv
import json
import os
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(HERE))

from agents_graph import build_graph, run_graph  # noqa: E402
from model_client import ModelClient  # noqa: E402

CASES_DIR = REPO_ROOT / "reports" / "hw02" / "cases"
RAW_DIR = REPO_ROOT / "reports" / "hw02" / "raw"

SCHEMA_RUNS = 30
CEILING_RUNS = 20
CEILINGS = [2, 10]
ADVERSARIAL_RUNS = 5
# One correction round costs four worker turns (planner, reviewer, planner,
# reviewer). A ceiling of 4 cuts off the confirming review and logs a good run
# as abandoned, so the 4.3 runs get headroom for two rounds.
SCHEMA_CEILING = 8

OUTCOMES = [
    "valid_first_attempt",
    "valid_after_1_retry",
    "valid_after_2plus_retries",
    "hit_turn_ceiling",
]


def classify(result: dict) -> str:
    """Map one run onto the four outcome buckets in the Part 4.3 table.

    The buckets count SCHEMA retries (Pydantic rejections fed back to the
    Planner), not total Planner calls. The Reviewer can also send a proposal
    back for content reasons; counting those here would make the table measure
    how picky the Reviewer is rather than how often the schema is satisfied.
    """
    if not result["valid"]:
        return "hit_turn_ceiling"  # ran out of turns still schema-invalid
    retries = result["schema_retries"]
    if retries == 0:
        return "valid_first_attempt"
    if retries == 1:
        return "valid_after_1_retry"
    return "valid_after_2plus_retries"


def load_case(name: str) -> dict:
    with open(CASES_DIR / f"{name}.json") as f:
        return json.load(f)


def append_raw(record: dict) -> None:
    with open(RAW_DIR / "runs.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")


def do_runs(experiment: str, case: dict, n: int, ceiling: int, llm, graph) -> list:
    """Run the graph n times on one case, recording and printing each result."""
    records = []
    for i in range(n):
        t0 = time.time()
        try:
            result = run_graph(
                case["title"],
                case["content"],
                case.get("email", "student@example.com"),
                turn_ceiling=ceiling,
                llm=llm,
                graph=graph,
            )
            error = ""
        except Exception as exc:  # a crashed run is data, not a reason to lose the batch
            result = {
                "valid": False,
                "reviewed_clean": False,
                "succeeded": False,
                "planner_attempts": 0,
                "schema_retries": 0,
                "turn_count": 0,
                "turn_ceiling": ceiling,
                "hit_ceiling": False,
                "tags": [],
                "summary": "",
                "validation_history": [],
                "reviewer_issues": [],
                "latency_ms": int((time.time() - t0) * 1000),
            }
            error = f"{type(exc).__name__}: {exc}"

        record = {
            "experiment": experiment,
            "case_id": case["case_id"],
            "run_index": i,
            "turn_ceiling": ceiling,
            "outcome": classify(result) if not error else "error",
            "error": error,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **result,
        }
        records.append(record)
        append_raw(record)

        print(
            f"[{experiment} ceiling={ceiling}] run {i + 1}/{n} -> "
            f"{record['outcome']} attempts={result['planner_attempts']} "
            f"({result['latency_ms']} ms)"
            + (f"  ERROR {error}" if error else "")
        )
    return records


def summarize_outcomes(records: list) -> dict:
    """Counts and mean latency per outcome bucket - the Part 4.3 table."""
    counts = Counter(r["outcome"] for r in records)
    table = {}
    for outcome in OUTCOMES:
        bucket = [r["latency_ms"] for r in records if r["outcome"] == outcome]
        table[outcome] = {
            "count": counts.get(outcome, 0),
            "mean_latency_ms": round(statistics.mean(bucket), 1) if bucket else None,
        }
    errors = counts.get("error", 0)
    if errors:
        table["error"] = {"count": errors, "mean_latency_ms": None}
    return table


def summarize_ceiling(records: list) -> dict:
    """Completion rate and mean latency - the Part 4.4 comparison."""
    completed = [r for r in records if r["succeeded"]]
    latencies = [r["latency_ms"] for r in records]
    return {
        "runs": len(records),
        "completed": len(completed),
        "completion_rate": round(len(completed) / len(records), 3) if records else 0.0,
        "mean_latency_ms": round(statistics.mean(latencies), 1) if latencies else None,
        "median_latency_ms": round(statistics.median(latencies), 1) if latencies else None,
        "mean_planner_attempts": (
            round(statistics.mean([r["planner_attempts"] for r in records]), 2) if records else None
        ),
    }


def write_csv(records: list) -> None:
    fields = [
        "experiment", "case_id", "run_index", "turn_ceiling", "outcome",
        "valid", "succeeded", "schema_retries", "planner_attempts", "turn_count",
        "hit_ceiling", "latency_ms", "tags", "summary", "error",
    ]
    with open(RAW_DIR / "schema_runs.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for r in records:
            row = []
            for field in fields:
                v = r.get(field, "")
                row.append(" | ".join(v) if isinstance(v, list) else v)
            w.writerow(row)


def summarize_from_raw() -> dict:
    """Rebuild the whole summary from raw/runs.jsonl without running anything.

    Needed because --only writes a summary covering just the experiment it ran.
    Re-deriving from the raw records keeps one summary that reflects every run
    on disk, however many sessions produced them.
    """
    path = RAW_DIR / "runs.jsonl"
    records = [json.loads(line) for line in open(path)]

    summary = {
        "model": records[0].get("model", os.environ.get("SMOL_MODEL", "qwen3:8b")) if records else None,
        "rebuilt_from": str(path.relative_to(REPO_ROOT)),
        "rebuilt_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_runs": len(records),
    }

    schema = [r for r in records if r["experiment"] == "schema"]
    if schema:
        summary["schema_validation"] = {
            "runs": len(schema),
            "turn_ceiling": schema[0]["turn_ceiling"],
            "outcomes": summarize_outcomes(schema),
        }

    ceiling = [r for r in records if r["experiment"] == "ceiling"]
    if ceiling:
        summary["ceiling_comparison"] = {}
        for c in sorted({r["turn_ceiling"] for r in ceiling}):
            summary["ceiling_comparison"][str(c)] = summarize_ceiling(
                [r for r in ceiling if r["turn_ceiling"] == c]
            )

    adversarial = [r for r in records if r["experiment"] == "adversarial"]
    if adversarial:
        hit = sum(1 for r in adversarial if r["hit_ceiling"])
        summary["adversarial"] = {
            "case_id": adversarial[0]["case_id"],
            "runs": len(adversarial),
            "hit_ceiling_count": hit,
            "hit_ceiling_rate": round(hit / len(adversarial), 3),
            "outcomes": summarize_outcomes(adversarial),
        }

    write_csv(records)
    with open(RAW_DIR / "schema_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["schema", "ceiling", "adversarial"],
                    help="run a single experiment instead of all three")
    ap.add_argument("--runs", type=int,
                    help="override the run count (smoke-testing the harness)")
    ap.add_argument("--summarize-only", action="store_true",
                    help="rebuild the summary and CSV from raw/runs.jsonl; run nothing")
    args = ap.parse_args()

    if args.summarize_only:
        print(json.dumps(summarize_from_raw(), indent=2))
        return

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    frozen = load_case("schema_input")
    adversarial = load_case("adversarial_input")

    llm = ModelClient(temperature=0.0)
    graph = build_graph()

    all_records = []
    summary = {
        "model": llm.model_name,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "frozen_case": frozen["case_id"],
    }

    if args.only in (None, "schema"):
        n = args.runs or SCHEMA_RUNS
        print(f"\n=== Part 4.3 - {n} runs on the frozen input (ceiling={SCHEMA_CEILING}) ===")
        records = do_runs("schema", frozen, n, SCHEMA_CEILING, llm, graph)
        all_records += records
        summary["schema_validation"] = {
            "runs": len(records),
            "turn_ceiling": SCHEMA_CEILING,
            "outcomes": summarize_outcomes(records),
        }

    if args.only in (None, "ceiling"):
        n = args.runs or CEILING_RUNS
        summary["ceiling_comparison"] = {}
        for ceiling in CEILINGS:
            print(f"\n=== Part 4.4 - {n} runs at turn ceiling {ceiling} ===")
            records = do_runs("ceiling", frozen, n, ceiling, llm, graph)
            all_records += records
            summary["ceiling_comparison"][str(ceiling)] = summarize_ceiling(records)

    if args.only in (None, "adversarial"):
        n = args.runs or ADVERSARIAL_RUNS
        print(f"\n=== Part 4.5 - {n} runs on the adversarial input (ceiling={CEILINGS[-1]}) ===")
        records = do_runs("adversarial", adversarial, n, CEILINGS[-1], llm, graph)
        all_records += records
        # The outcome bucket only reports SCHEMA validity. A run can exhaust the
        # ceiling while holding a schema-valid proposal the Reviewer never cleared,
        # so ceiling exhaustion is read from hit_ceiling, not from the bucket.
        hit = sum(1 for r in records if r["hit_ceiling"])
        summary["adversarial"] = {
            "case_id": adversarial["case_id"],
            "runs": len(records),
            "hit_ceiling_count": hit,
            "hit_ceiling_rate": round(hit / len(records), 3) if records else 0.0,
            "outcomes": summarize_outcomes(records),
        }

    summary["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    summary["total_runs"] = len(all_records)

    write_csv(all_records)
    with open(RAW_DIR / "schema_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print("\n\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nRaw results: {RAW_DIR}")
    llm.print_exit_summary()


if __name__ == "__main__":
    main()
