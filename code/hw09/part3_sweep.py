#!/usr/bin/env python3
"""HW9 Part 3.2-3.4 - threshold sweep over the 40 labeled cases in cache_cases.yaml.

1. Seed the cache: each of the 20 seed questions goes through the REAL HW8 agent path once (agent latency recorded).
2. For every case and every threshold, run one real timed cache lookup (embed + RediSearch KNN-1).
3. hit = nearest similarity >= threshold. A hit on an expect=miss case is a FALSE HIT (labels never edited).
4. A miss costs the agent path; its latency is modelled as lookup + the mean MEASURED seed agent latency
   (re-running qwen3:8b for ~100 misses would only re-measure the same number).
"""
from __future__ import annotations

import json
import statistics
import sys

import common
import yaml
from common import banner
from qa_agent import ground_truth, run_agent
from semantic_cache import SemanticCache, embed

THRESHOLDS = [0.75, 0.80, 0.85, 0.90, 0.95]
COSTS = {"cache_miss_usd": 0.02, "false_hit_usd": 5.00}      # justified in reports/hw09/METRICS.md


def main() -> int:
    banner("part3_sweep.py")
    spec = yaml.safe_load((common.ROOT / "code" / "hw09" / "cache_cases.yaml").read_text())
    cache = SemanticCache("sweep")
    cache.create_index(reset=True)
    embed("warm up")

    # --- 1. seed through the real agent -------------------------------------------------------------
    seeds, agent_ms = {}, []
    for s in spec["seeds"]:
        out = run_agent(s["query"])
        cache.store(s["query"], out["answer"], out["data_version"], out["entities"])
        seeds[s["id"]] = {"query": s["query"], "answer": out["answer"], "agent_ms": out["agent_ms"],
                          "correct": ground_truth(s["key"])}
        agent_ms.append(out["agent_ms"])
        print(f"seed {s['id']}: {out['agent_ms']:>6} ms  {s['query']}  ->  {out['answer']}", flush=True)
    mean_agent = statistics.mean(agent_ms)
    print(f"\ncache holds {cache.size()} entries; mean measured agent latency = {mean_agent:.0f} ms", flush=True)

    # --- 2/3. every case x every threshold ---------------------------------------------------------------
    rows = []
    for c in spec["cases"]:
        for th in THRESHOLDS:
            look = cache.lookup(c["query"], th)
            near = look["neighbour"]
            lookup_ms = look["embed_ms"] + look["search_ms"]
            hit = look["hit"]
            rows.append({"case": c["id"], "group": c["group"], "expect": c["expect"], "threshold": th,
                         "query": c["query"], "similarity": near["similarity"] if near else None,
                         "nearest_cached_query": near["query"] if near else None,
                         "nearest_cached_answer": near["answer"] if near else None,
                         "hit": hit, "false_hit": hit and c["expect"] == "miss",
                         "missed_hit": (not hit) and c["expect"] == "hit",
                         "correct_answer": ground_truth(c["key"]) if "key" in c else None,
                         "lookup_ms": round(lookup_ms, 2),
                         "latency_ms": round(lookup_ms if hit else lookup_ms + mean_agent, 2)})
    # --- table -----------------------------------------------------------------------------------------------
    table = []
    for th in THRESHOLDS:
        r = [x for x in rows if x["threshold"] == th]
        hits = sum(x["hit"] for x in r)
        fh = sum(x["false_hit"] for x in r)
        missed = sum(x["missed_hit"] for x in r)
        misses = len(r) - hits
        cost = misses * COSTS["cache_miss_usd"] + fh * COSTS["false_hit_usd"]
        table.append({"threshold": th, "hits": hits, "hit_rate_pct": round(100 * hits / len(r), 1),
                      "false_hits": fh, "false_hit_rate_pct": round(100 * fh / 20, 1),     # of the 20 should-miss cases
                      "false_hit_share_of_hits_pct": round(100 * fh / hits, 1) if hits else 0.0,
                      "missed_hits": missed, "misses": misses,
                      "mean_latency_ms": round(statistics.mean(x["latency_ms"] for x in r), 1),
                      "mean_hit_latency_ms": round(statistics.mean([x["latency_ms"] for x in r if x["hit"]] or [0]), 1),
                      "total_cost_usd": round(cost, 2)})
    sens = {}
    for fh_cost in (1.0, 5.0, 25.0):
        sens[str(fh_cost)] = {str(t["threshold"]): round(t["misses"] * COSTS["cache_miss_usd"] + t["false_hits"] * fh_cost, 2)
                              for t in table}
    best = min(table, key=lambda t: (t["total_cost_usd"], -t["threshold"]))
    # --- 3.3 one false hit in full: highest-similarity false hit at 0.85 -------------------------------------
    fhs = sorted([x for x in rows if x["threshold"] == 0.85 and x["false_hit"]], key=lambda x: -x["similarity"])
    out = {"costs": COSTS, "mean_seed_agent_ms": round(mean_agent, 1), "seeds": seeds, "table": table,
           "sensitivity_total_cost_by_false_hit_cost": sens, "cheapest_threshold": best["threshold"],
           "example_false_hit_at_0.85": fhs[0] if fhs else None, "rows": rows}
    (common.RAW / "part3_sweep.json").write_text(json.dumps(out, indent=2))
    print("\nthreshold  hit%   FH%   missedHits  meanLat(ms)  totalCost($)")
    for t in table:
        print(f"{t['threshold']:.2f}      {t['hit_rate_pct']:>5}  {t['false_hit_rate_pct']:>5}  {t['missed_hits']:>5}      "
              f"{t['mean_latency_ms']:>9}  {t['total_cost_usd']:>8}")
    print(f"\ncheapest threshold at ${COSTS['false_hit_usd']} per false hit: {best['threshold']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
