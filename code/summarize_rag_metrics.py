#!/usr/bin/env python3
"""
HW3 Part 2 - recompute the comparison tables from the raw retrieval output.

The assignment asks for the summary tables to be recomputable from the
machine-readable data rather than transcribed from console output, so this
script reads only reports/hw03/raw/ and writes reports/hw03/METRICS.md. It
never touches the corpus, the embedding model or the network: deleting
METRICS.md and re-running this reproduces it byte-for-byte from the same raw
files.

Definitions used (the handout names the columns but does not define them all):

  Chunks            number of nodes the chunker produced over the whole corpus
  Avg chunk length  mean characters per node, with a token estimate alongside
  Top-1 cosine      per question, the highest cosine among that question's
                    top-k; averaged over questions
  Mean@k cosine     per question, the mean cosine over all k retrieved chunks;
                    averaged over questions
  Recall@k          fraction of questions whose expected_source_file appears
                    anywhere in the top-k. This is the definition the handout
                    leaves open; it is stated here so the number is readable.
                    It is document-level recall, not passage-level -- a chunk
                    from the right file that happens to miss the answer still
                    counts as a hit, which is exactly why the confidently-wrong
                    retrievals in the last section are reported separately.
  Latency           wall-clock milliseconds for retriever.retrieve(), averaged
                    over questions. Embedding the query is included; building
                    the index is not.

Usage:
    python summarize_rag_metrics.py
    python summarize_rag_metrics.py --confident-threshold 0.45
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = REPO_ROOT / "reports" / "hw03"
RAW_DIR = REPORT_DIR / "raw"
ROWS_PATH = RAW_DIR / "retrieval_rows.jsonl"
STATS_PATH = RAW_DIR / "chunk_stats.json"
METRICS_PATH = REPORT_DIR / "METRICS.md"

TECHNIQUE_LABELS = {
    "token": "Token",
    "semantic": "Semantic",
    "sentence": "Sentence window",
}


def load_rows() -> list[dict]:
    if not ROWS_PATH.exists():
        raise SystemExit(
            f"{ROWS_PATH} not found.\nRun:  python code/run_rag_chunking.py"
        )
    return [json.loads(line) for line in ROWS_PATH.read_text().splitlines() if line.strip()]


def summarise(rows: list[dict], stats: dict) -> dict:
    """Per-technique aggregates, all derived from the raw rows."""
    by_technique: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        by_technique[row["technique"]][row["question_id"]].append(row)

    chunk_stats = {t["technique"]: t for t in stats["techniques"]}
    summary: dict[str, dict] = {}

    for technique, questions in by_technique.items():
        top1, meank, latencies, hits = [], [], [], 0

        for _question_id, question_rows in questions.items():
            ordered = sorted(question_rows, key=lambda r: r["rank"])
            cosines = [r["cosine_sim"] for r in ordered]
            top1.append(max(cosines))
            meank.append(statistics.fmean(cosines))
            latencies.append(ordered[0]["retrieval_latency_ms"])
            if any(r["is_expected_source"] for r in ordered):
                hits += 1

        info = chunk_stats.get(technique, {})
        summary[technique] = {
            "label": TECHNIQUE_LABELS.get(technique, technique),
            "n_questions": len(questions),
            "chunks": info.get("n_chunks"),
            "avg_chunk_len_chars": info.get("avg_chunk_len_chars"),
            "avg_chunk_len_tokens_est": info.get("avg_chunk_len_tokens_est"),
            "min_chunk_len_chars": info.get("min_chunk_len_chars"),
            "max_chunk_len_chars": info.get("max_chunk_len_chars"),
            "build_seconds": info.get("build_seconds"),
            "embed_seconds": info.get("embed_seconds"),
            "top1_cosine": round(statistics.fmean(top1), 4),
            "meank_cosine": round(statistics.fmean(meank), 4),
            "recall_at_k": round(hits / len(questions), 4),
            "hits": hits,
            "mean_latency_ms": round(statistics.fmean(latencies), 2),
            "median_latency_ms": round(statistics.median(latencies), 2),
        }
    return summary


def per_question_table(rows: list[dict]) -> dict:
    """Top-1 cosine and hit/miss for every (question, technique) pair."""
    grid: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in rows:
        cell = grid[row["question_id"]].setdefault(
            row["technique"], {"best_cosine": -1.0, "hit": False, "rank1_source": None}
        )
        cell["best_cosine"] = max(cell["best_cosine"], row["cosine_sim"])
        cell["hit"] = cell["hit"] or row["is_expected_source"]
        cell["expected"] = row["expected_source_file"]
        if row["rank"] == 1:
            cell["rank1_source"] = row["source_file"]
            cell["rank1_cosine"] = row["cosine_sim"]
            cell["rank1_correct"] = row["is_expected_source"]
    return grid


def confident_misses(rows: list[dict], threshold: float) -> list[dict]:
    """Chunks scored confidently that came from the wrong document.

    "Confident" is defined as a cosine at or above the threshold; the default
    is deliberately near the top of the observed range so this does not simply
    list every miss. Rank-1 misses are listed first because those are the ones
    a naive RAG system would actually feed to a generator.
    """
    misses = [
        r for r in rows
        if not r["is_expected_source"] and r["cosine_sim"] >= threshold
    ]
    misses.sort(key=lambda r: (r["rank"] != 1, -r["cosine_sim"]))
    return misses


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confident-threshold", type=float, default=0.45,
                        help="cosine at or above which a wrong-document hit counts "
                             "as 'confidently scored' (default 0.45)")
    args = parser.parse_args()

    rows = load_rows()
    stats = json.loads(STATS_PATH.read_text())
    summary = summarise(rows, stats)
    grid = per_question_table(rows)
    misses = confident_misses(rows, args.confident_threshold)

    order = [t for t in ("token", "semantic", "sentence") if t in summary]
    top_k = stats.get("top_k", 5)

    # A (question, technique) pair with fewer than top_k rows means the vector
    # store collapsed exact-duplicate chunks. Worth stating rather than hiding,
    # because mean@k is then an average over fewer than k values.
    short = sorted({
        (r["technique"], r["question_id"])
        for r in rows
        if sum(1 for x in rows
               if x["technique"] == r["technique"] and x["question_id"] == r["question_id"]) < top_k
    })


    lines: list[str] = [
        "# HW3 Part 2 - METRICS",
        "",
        "Municipal Transit Incidents corpus (DOMAIN_ID 2). Retrieval only - no LLM,",
        "no generation. Every number below is recomputed from",
        "`reports/hw03/raw/retrieval_rows.jsonl` by `code/summarize_rag_metrics.py`;",
        "nothing here is transcribed by hand.",
        "",
        f"- **Embedding model:** `{stats.get('embed_model')}`",
        f"- **top_k:** {top_k}",
        f"- **Questions scored:** {summary[order[0]]['n_questions']} (from `questions.yaml`, committed before this run)",
        f"- **SEED / VERIFY_SEED:** {stats.get('seed')} / {stats.get('verify_seed')}",
        f"- **Generated:** {stats.get('generated_at')}",
        "",
        "## 1. Retrieval quality",
        "",
    ]

    lines.append(markdown_table(
        ["Technique", "Chunks", "Avg chunk length",
         f"Top-1 cosine", f"Mean@{top_k} cosine", f"Recall@{top_k}",
         "Mean retrieval latency (ms)"],
        [[
            summary[t]["label"],
            f"{summary[t]['chunks']:,}",
            f"{summary[t]['avg_chunk_len_chars']:,.0f} chars (~{summary[t]['avg_chunk_len_tokens_est']:.0f} tok)",
            f"{summary[t]['top1_cosine']:.4f}",
            f"{summary[t]['meank_cosine']:.4f}",
            f"{summary[t]['recall_at_k']:.2f} ({summary[t]['hits']}/{summary[t]['n_questions']})",
            f"{summary[t]['mean_latency_ms']:.2f}",
        ] for t in order]
    ))

    lines += [
        "",
        "### Chunking cost and spread",
        "",
        markdown_table(
            ["Technique", "Min chunk", "Max chunk", "Chunking time (s)", "Embedding time (s)"],
            [[
                summary[t]["label"],
                f"{summary[t]['min_chunk_len_chars']:,}",
                f"{summary[t]['max_chunk_len_chars']:,}",
                f"{summary[t]['build_seconds']}",
                f"{summary[t]['embed_seconds']}",
            ] for t in order]
        ),
        "",
        "## 2. Per-question top-1 cosine and document hit",
        "",
        "`hit` means the expected source file appeared somewhere in the top-"
        f"{top_k}. `rank-1 from` is the file the single best-scoring chunk came from.",
        "",
    ]

    header = ["Question"] + [f"{summary[t]['label']} top-1" for t in order] + \
             [f"{summary[t]['label']} hit" for t in order]
    body = []
    for question_id in sorted(grid):
        cells = [f"`{question_id}`"]
        for t in order:
            cell = grid[question_id].get(t, {})
            cells.append(f"{cell.get('best_cosine', float('nan')):.4f}")
        for t in order:
            cell = grid[question_id].get(t, {})
            cells.append("yes" if cell.get("hit") else "**no**")
        body.append(cells)
    lines.append(markdown_table(header, body))

    lines += [
        "",
        "### Where the single best-scoring chunk actually came from",
        "",
        markdown_table(
            ["Question", "Technique", "Rank-1 cosine", "Rank-1 source file",
             "Expected file", "Rank-1 correct?"],
            [[
                f"`{question_id}`",
                summary[t]["label"],
                f"{grid[question_id][t].get('rank1_cosine', float('nan')):.4f}",
                f"`{grid[question_id][t].get('rank1_source')}`",
                f"`{grid[question_id][t].get('expected')}`",
                "yes" if grid[question_id][t].get("rank1_correct") else "**no**",
            ] for question_id in sorted(grid) for t in order if t in grid[question_id]]
        ),
        "",
        f"## 3. Confidently scored retrievals that do not contain the answer",
        "",
        f"Wrong-document chunks scoring at or above cosine {args.confident_threshold}. "
        "These are the failures the assignment asks to surface: the embedding was "
        "sure, and it was wrong.",
        "",
    ]

    if not misses:
        lines += [
            f"_None at threshold {args.confident_threshold}._ Lower it with "
            "`--confident-threshold`, or add a question to `questions.yaml` that "
            "targets a fact stated in near-identical language in two documents.",
            "",
        ]
    else:
        lines.append(markdown_table(
            ["Question", "Technique", "Rank", "Cosine", "Came from", "Should have been", "Preview"],
            [[
                f"`{m['question_id']}`",
                TECHNIQUE_LABELS.get(m["technique"], m["technique"]),
                m["rank"],
                f"{m['cosine_sim']:.4f}",
                f"`{m['source_file']}`",
                f"`{m['expected_source_file']}`",
                m["preview"][:110].replace("|", "\\|"),
            ] for m in misses[:20]]
        ))
        lines += [
            "",
            f"_{len(misses)} such retrievals in total; the {min(20, len(misses))} "
            "highest-scoring are shown._",
            "",
        ]

    lines += [
        *([
            "### Incomplete result sets",
            "",
            "These query/technique pairs returned fewer than "
            f"{top_k} chunks, because the in-memory store collapses chunks with "
            "identical embeddings. Their mean@k is an average over fewer values:",
            "",
            *[f"- `{q}` / {TECHNIQUE_LABELS.get(t, t)}" for t, q in short],
            "",
        ] if short else []),
        "## 4. Observations",
        "",
        "<!-- TO FILL IN after the run: 1-2 short paragraphs. Discuss WHY one",
        "     technique performed better on these queries - sentence coherence,",
        "     semantic boundary detection, token-budget alignment, or context",
        "     carried via the sentence window. If the best technique differs",
        "     across the optional extra queries, say so. -->",
        "",
        "## 5. Conclusion",
        "",
        "<!-- TO FILL IN: 2-5 sentences naming the technique you judge best for",
        "     THIS corpus and why, supported by the measurements above. -->",
        "",
        "---",
        "",
        "Regenerate with:",
        "",
        "```bash",
        "python code/run_rag_chunking.py        # writes reports/hw03/raw/",
        "python code/summarize_rag_metrics.py   # writes this file",
        "```",
    ]

    METRICS_PATH.write_text("\n".join(lines) + "\n")

    print(f"wrote {METRICS_PATH.relative_to(REPO_ROOT)}")
    print()
    for t in order:
        s = summary[t]
        print(f"  {s['label']:<16} chunks={s['chunks']:>6}  avg_len={s['avg_chunk_len_chars']:>8.0f}  "
              f"top1={s['top1_cosine']:.4f}  mean@k={s['meank_cosine']:.4f}  "
              f"recall@{top_k}={s['recall_at_k']:.2f}  latency={s['mean_latency_ms']:.2f}ms")
    print()
    print(f"  confidently-wrong retrievals at >= {args.confident_threshold}: {len(misses)}")
    if not misses:
        print("  !! the assignment requires at least one -- lower the threshold or add a question")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
