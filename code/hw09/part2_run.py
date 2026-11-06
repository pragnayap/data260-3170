#!/usr/bin/env python3
"""HW9 Part 2 - 14 queries through the semantic cache at threshold 0.85: new, exact duplicates, paraphrases,
a near-miss and a completely unrelated question. Misses really run the HW8 agent path (qwen3:8b, CPU)."""
from __future__ import annotations

import json
import statistics
import sys

import common
from common import banner
from semantic_cache import SemanticCache, embed

QUERIES = [
    ("new",             "What agency operates route R-0030?"),
    ("exact duplicate", "What agency operates route R-0030?"),
    ("paraphrase",      "Which transit agency is responsible for route R-0030?"),
    ("new",             "How many incidents are recorded for route R-0040?"),
    ("exact duplicate", "How many incidents are recorded for route R-0040?"),
    ("paraphrase",      "What is the total incident count for route R-0040?"),
    ("new",             "What type of route is R-0045?"),
    ("paraphrase",      "What kind of service does route R-0045 provide?"),
    ("new (unrelated)", "What is the capital of France?"),
    ("exact duplicate", "What is the capital of France?"),
    ("new",             "What is the name of route R-0052?"),
    ("near miss",       "What is the name of route R-0053?"),
    ("new",             "How many riders were affected in total on route R-0060?"),
    ("paraphrase",      "What is the total number of passengers impacted on route R-0060?"),
]


def main() -> int:
    banner("part2_run.py")
    cache = SemanticCache("sem", threshold=0.85)
    cache.create_index(reset=True)
    embed("warm up")                                    # load MiniLM once so the first query is not charged for it
    results = []
    for n, (kind, q) in enumerate(QUERIES, 1):
        print(f"\n--- Query {n}/{len(QUERIES)} [{kind}] {q}", flush=True)
        out = cache.handle(q)
        out["kind"] = kind
        results.append(out)
        sim = "n/a" if out["similarity"] is None else f"{out['similarity']:.4f}"
        print(f"    is_cached={out['is_cached']}  similarity={sim}  latency={out['latency_ms']:.1f} ms\n    answer: {out['answer']}",
              flush=True)
    hits = [r for r in results if r["is_cached"]]
    miss = [r for r in results if not r["is_cached"]]
    summary = {"queries": len(results), "hits": len(hits), "misses": len(miss),
               "hit_rate_pct": round(100 * len(hits) / len(results), 1),
               "avg_latency_cached_ms": round(statistics.mean(r["latency_ms"] for r in hits), 1) if hits else None,
               "avg_latency_not_cached_ms": round(statistics.mean(r["latency_ms"] for r in miss), 1) if miss else None,
               "threshold": 0.85}
    print("\n=== Part 2 summary ===\n" + json.dumps(summary, indent=2))
    (common.RAW / "part2_results.json").write_text(json.dumps({"summary": summary, "results": results}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
