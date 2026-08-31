"""
Part 3 - Measuring Non-Determinism.

Runs the agents_demo.py pipeline 20x at temperature 0.7 and 20x at
temperature 0.0 on one fixed input, then reports:
  - number of distinct tag sets produced
  - tags that appeared in all 20 runs
  - tags that appeared in exactly one run
  - latency p50 / p95 / p99

Usage:
  caffeinate -i python run_nondeterminism.py
"""

import json
import os
import time
from collections import Counter
from pathlib import Path

from agents_demo import make_llm, build_agents, run_pipeline

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
INPUT_PATH = REPO_ROOT / "reports" / "hw01" / "cases" / "nondeterminism_input.json"
RAW_DIR = REPO_ROOT / "reports" / "hw01" / "raw"

MODEL = os.environ.get("SMOL_MODEL", "qwen3:8b")
BASE_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
RUNS_PER_TEMP = 20
TEMPERATURES = [0.7, 0.0]


def percentile(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def run_temperature(temperature: float, title: str, content: str):
    llm = make_llm(MODEL, temperature, BASE_URL)
    planner, reviewer, finalizer = build_agents(llm)

    records = []
    for i in range(RUNS_PER_TEMP):
        t0 = time.time()
        result = run_pipeline(planner, reviewer, finalizer, title, content)
        latency_ms = int((time.time() - t0) * 1000)

        tags = tuple(sorted(result["final"]["data"]["tags"]))
        record = {
            "temperature": temperature,
            "run_index": i,
            "tags": list(tags),
            "summary": result["final"]["data"]["summary"],
            "latency_ms": latency_ms,
        }
        records.append(record)
        print(f"[temp={temperature}] run {i + 1}/{RUNS_PER_TEMP} -> {tags} ({latency_ms} ms)")

    return records


def summarize(records):
    tag_sets = [tuple(r["tags"]) for r in records]
    distinct_sets = len(set(tag_sets))

    tag_run_counts = Counter()
    for r in records:
        for t in set(r["tags"]):
            tag_run_counts[t] += 1

    in_all_runs = sorted([t for t, c in tag_run_counts.items() if c == len(records)])
    in_exactly_one = sorted([t for t, c in tag_run_counts.items() if c == 1])

    latencies = [r["latency_ms"] for r in records]

    return {
        "distinct_tag_sets": distinct_sets,
        "tags_in_all_runs": in_all_runs,
        "tags_in_exactly_one_run": in_exactly_one,
        "latency_p50_ms": round(percentile(latencies, 50), 1),
        "latency_p95_ms": round(percentile(latencies, 95), 1),
        "latency_p99_ms": round(percentile(latencies, 99), 1),
    }


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    with open(INPUT_PATH) as f:
        fixed_input = json.load(f)
    title, content = fixed_input["title"], fixed_input["content"]

    all_records = []
    summaries = {}

    for temp in TEMPERATURES:
        print(f"\n=== Running {RUNS_PER_TEMP} runs at temperature {temp} ===")
        records = run_temperature(temp, title, content)
        all_records.extend(records)
        summaries[str(temp)] = summarize(records)

    # Raw per-run results (all 40 runs), JSON + CSV
    with open(RAW_DIR / "nondeterminism_raw.json", "w") as f:
        json.dump(all_records, f, indent=2)

    import csv
    with open(RAW_DIR / "nondeterminism_raw.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["temperature", "run_index", "tags", "summary", "latency_ms"])
        for r in all_records:
            writer.writerow([r["temperature"], r["run_index"], " | ".join(r["tags"]), r["summary"], r["latency_ms"]])

    with open(RAW_DIR / "nondeterminism_summary.json", "w") as f:
        json.dump(summaries, f, indent=2)

    print("\n\n=== SUMMARY ===")
    print(json.dumps(summaries, indent=2))
    print(f"\nRaw results saved to: {RAW_DIR}")


if __name__ == "__main__":
    main()
