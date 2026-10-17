"""
HW6 - rebuild reports/hw06/METRICS.md from reports/hw06/raw/ (no model calls).

    python code/hw6/summarize_hw6.py
"""

import csv
import json
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "reports" / "hw06" / "raw"
OUT = ROOT / "reports" / "hw06" / "METRICS.md"
LABELS = [("N4", "SHORT_TERM_N=4"), ("N12", "SHORT_TERM_N=12"), ("N30", "SHORT_TERM_N=30"),
          ("N30_evict", "Eviction policy (N=30 + evict_old_assistant)")]
IN_PRICE, OUT_PRICE = 1.0, 5.0      # USD per million tokens (assignment)
CONVERSATIONS = 10_000
QUALITY_TOLERANCE = 0.5              # "good enough": within this of the best probe score


def load(label: str):
    f = RAW / f"turns_{label}.csv"
    p = RAW / f"probe_scores_{label}.json"
    if not (f.exists() and p.exists()):
        return None
    rows = list(csv.DictReader(f.open()))
    for r in rows:
        for k, v in r.items():
            if k not in ("label", "phase"):
                r[k] = float(v)
    return rows, json.loads(p.read_text())


def summarize(label: str):
    data = load(label)
    if not data:
        return None
    rows, probes = data
    conv = [r for r in rows if r["phase"] == "conversation"]
    mean = lambda key, rs=conv: st.mean(r[key] for r in rs)  # noqa: E731
    total = lambda key: sum(r[key] for r in conv)  # noqa: E731
    in_chat, out_chat = total("prompt_tokens"), total("completion_tokens")
    in_over, out_over = total("extraction_in") + total("summary_in"), total("extraction_out") + total("summary_out")
    cost = lambda i, o: (i * IN_PRICE + o * OUT_PRICE) / 1e6 * CONVERSATIONS  # noqa: E731
    return {
        "label": label, "n_turns": len(conv),
        "mean_prompt": mean("prompt_tokens"), "mean_completion": mean("completion_tokens"),
        "mean_latency_ms": mean("latency_ms"), "mean_total_latency_ms": mean("total_latency_ms"),
        "probe": probes["mean_score"],
        "components": {c: mean(f"tok_{c}") for c in ("system_primer", "long_term_summary", "short_term_window", "episodic_facts", "current_message")},
        "in_chat": in_chat, "out_chat": out_chat, "in_over": in_over, "out_over": out_over,
        "cost_chat": cost(in_chat, out_chat), "cost_all": cost(in_chat + in_over, out_chat + out_over),
        "probe_detail": probes["probes"],
    }


def main() -> None:
    S = {l: s for l, _ in LABELS if (s := summarize(l))}
    names = dict(LABELS)
    md = ["# HW6 METRICS", "",
          "Model: qwen3:8b via Ollama, CPU only (Intel Core i9-9880H). Same 30-message conversation + 5 probes per setting, "
          "fresh user/session each. Raw per-turn data: `raw/turns_<label>.csv`; probe replies and scores: `raw/probe_scores_<label>.json`. "
          "Means are over the 30 conversation turns (probe turns excluded). Latency is the user-facing chat call "
          "(embedding + retrieval + model); episode extraction and summarization run after the reply and are reported as overhead.", ""]
    md += ["## Part 3.3 / 3.4 - memory size and eviction policy", "",
           "| Setting | Mean prompt tokens/turn | Mean latency (ms) | Probe quality (1-5) |", "|---|---|---|---|"]
    for l, n in LABELS:
        s = S.get(l)
        md.append(f"| {n} | {s['mean_prompt']:.0f} | {s['mean_latency_ms']:.0f} | {s['probe']:.2f} |" if s else f"| {n} | not run | | |")
    if "N30" in S and "N30_evict" in S:
        a, b = S["N30"], S["N30_evict"]
        md += ["", f"Eviction vs plain N=30: prompt tokens/turn {a['mean_prompt']:.0f} -> {b['mean_prompt']:.0f} "
                   f"({(1 - b['mean_prompt'] / a['mean_prompt']) * 100:.1f}% saved); probe quality {a['probe']:.2f} -> {b['probe']:.2f} "
                   f"({b['probe'] - a['probe']:+.2f}); latency {a['mean_latency_ms']:.0f} -> {b['mean_latency_ms']:.0f} ms."]
    md += ["", "### Where the prompt tokens go (mean per turn; proportional estimate, sums to the reported prompt tokens)", "",
           "| Setting | System primer | Long-term summary | Short-term window | Episodic facts | Current msg | Completion |", "|---|---|---|---|---|---|---|"]
    for l, n in LABELS:
        if l in S:
            c = S[l]["components"]
            md.append(f"| {n} | {c['system_primer']:.0f} | {c['long_term_summary']:.0f} | {c['short_term_window']:.0f} | "
                      f"{c['episodic_facts']:.0f} | {c['current_message']:.0f} | {S[l]['mean_completion']:.0f} |")
    md += ["", "### Probe scores by question", "", "| Probe | " + " | ".join(names[l] for l, _ in LABELS if l in S) + " |", "|---|" + "---|" * len(S)]
    if S:
        for i, p in enumerate(next(iter(S.values()))["probe_detail"]):
            md.append(f"| {p['probe']} | " + " | ".join(f"{S[l]['probe_detail'][i]['score']:.1f}" for l, _ in LABELS if l in S) + " |")

    md += ["", "## Part 3.5 - memory cost, 10,000 conversations x 30 turns", "",
           f"Pricing: ${IN_PRICE:.0f}/M input tokens, ${OUT_PRICE:.0f}/M output tokens. Token counts are the measured sums over the 30 turns. "
           "'Chat only' counts the main reply call; 'All-in' also counts the extra model calls memory needs "
           "(episode extraction every turn, summaries every 6th user message).", "",
           "| Setting | Input tok/conv | Output tok/conv | Chat-only cost | All-in input tok | All-in output tok | **All-in cost (10,000 conv)** | Probe |", "|---|---|---|---|---|---|---|---|"]
    for l, n in LABELS:
        if l in S:
            s = S[l]
            md.append(f"| {n} | {s['in_chat']:.0f} | {s['out_chat']:.0f} | ${s['cost_chat']:,.2f} | {s['in_chat'] + s['in_over']:.0f} | "
                      f"{s['out_chat'] + s['out_over']:.0f} | **${s['cost_all']:,.2f}** | {s['probe']:.2f} |")
    if S:
        worst = max(S.values(), key=lambda s: s["cost_all"])
        top = max(s["probe"] for s in S.values())
        ok = [s for s in S.values() if s["probe"] >= top - QUALITY_TOLERANCE]
        best = min(ok, key=lambda s: s["cost_all"])
        md += ["", f"**Worst setting** = highest all-in cost: {names[worst['label']]} (${worst['cost_all']:,.2f}).",
               f"**Best setting** = cheapest all-in cost among settings whose probe quality is within {QUALITY_TOLERANCE} of the best score "
               f"({top:.2f}): {names[best['label']]} (${best['cost_all']:,.2f}).",
               f"Cost ratio worst/best: {worst['cost_all'] / best['cost_all']:.2f}x. Selecting by cost alone would ignore quality loss, "
               "so 'best' is the cheapest setting that has not given up recall."]
    rep = RAW.parent / "memory_test" / "consolidation_report.json"
    if rep.exists():
        r = json.loads(rep.read_text())
        md += ["", "## Part 4.5 - consolidation of the 55-line MEMORY.md", "",
               f"Lines before/after: {r['lines_before']} -> {r['lines_after']} (under 40: {r['under_40']}); archived facts: {len(r['archived'])}; "
               f"merge groups: {len(r['merges'])}; contradictions resolved: {len(r['resolutions'])}.", "",
               "| Contradiction | Expected | Consolidator kept | Correct? |", "|---|---|---|---|"]
        for g in r["contradiction_grading"]:
            md.append(f"| {g['id']} | {g['expected']} | {g['actual_kept']} | {'yes' if g['correct'] else '**NO**'} |")
        md += ["", f"Resolved incorrectly: {', '.join(r['contradictions_resolved_incorrectly']) or 'none'}."]
    comp = RAW / "agent_md_compliance.json"
    if comp.exists():
        c = json.loads(comp.read_text())
        md += ["", "## Part 4.4 - generated function vs AGENT.md", "", "| Run | Attempt | Passed | Failed checks |", "|---|---|---|---|"]
        for k in ("with_agent_md", "control_without_agent_md"):
            for at in c[k]["attempts"]:
                md.append(f"| {k} | {at['attempt']} | {len(at['passed'])}/{len(at['passed']) + len(at['failed'])} | {', '.join(at['failed']) or '-'} |")
        h = c.get("hand_implemented_route_utils")
        if h:
            md.append(f"| hand-implemented route_utils.py | - | {len(h['passed'])}/{len(h['passed']) + len(h['failed'])} | {', '.join(h['failed']) or '-'} |")
    OUT.write_text("\n".join(md) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
