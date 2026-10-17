"""
HW6 Part 4.5 - consolidate the deliberately messy 55-line MEMORY file with the real model,
then grade the contradiction decisions against ground_truth.json (written beforehand).

Reads  reports/hw06/memory_test/MEMORY.original.md   (never modified)
Writes reports/hw06/memory_test/MEMORY.consolidated.md, MEMORY.archive.md, consolidation_report.json
"""

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import file_memory as fm  # noqa: E402
from file_memory_cli import default_llm, embed_texts  # noqa: E402

D = Path(__file__).resolve().parents[2] / "reports" / "hw06" / "memory_test"


def live_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if fm.is_content_line(ln)]


def grade(truth: dict, new_text: str) -> list[dict]:
    live = "\n".join(live_lines(new_text))
    out = []
    for c in truth["contradictions"]:
        has_a, has_b = c["a_match"] in live, c["b_match"] in live
        kept = "both" if has_a and has_b else "a" if has_a else "b" if has_b else "neither"
        want = {"keep a": "a", "keep b": "b", "keep both (scoped)": "both"}[c["correct"]]
        out.append({"id": c["id"], "expected": want, "actual_kept": kept, "correct": kept == want, "why_expected": c["why"]})
    return out


def main() -> None:
    original = (D / "MEMORY.original.md").read_text()
    print(f"[{datetime.now().isoformat(timespec='seconds')}] original: {fm.count_memory_lines(original)} content lines; "
          f"due: {fm.consolidation_reason(original)}", flush=True)
    calls = []
    # Disk cache of model replies (temperature 0, so a repeated prompt gives the same reply). It makes
    # re-running the *logic* after a code change instant; delete llm_cache.json to force fresh model calls.
    cache_path = D / "llm_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}

    def llm(messages):
        key = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
        t = time.perf_counter()
        hit = key in cache
        if not hit:
            cache[key] = default_llm(messages)
            cache_path.write_text(json.dumps(cache))
        out = cache[key]
        calls.append({"seconds": round(time.perf_counter() - t, 1), "cached": hit, "reply": out})
        return out

    result = fm.consolidate_memory(original, llm, embed_fn=embed_texts)
    (D / "MEMORY.consolidated.md").write_text(result.new_text)
    (D / "MEMORY.archive.md").write_text("# MEMORY.archive.md\nFacts removed by consolidation, with the reason.\n" + fm.archive_markdown(result))
    truth = json.loads((D / "ground_truth.json").read_text())
    graded = grade(truth, result.new_text)
    report = {
        "lines_before": result.lines_before, "lines_after": result.lines_after,
        "under_40": result.lines_after < 40, "aborted_by_guard": result.aborted, "proposed_archive_if_aborted": result.proposed_archive, "llm_ok": result.llm_ok, "notes": result.notes,
        "pair_verdicts": result.pair_verdicts, "merges": result.merges, "resolutions": result.resolutions, "archived": result.archived, "rewritten_wording": result.rewritten,
        "contradiction_grading": graded,
        "contradictions_resolved_incorrectly": [g["id"] for g in graded if not g["correct"]],
        "model_calls": calls,
        "due_after": fm.consolidation_reason(result.new_text),
    }
    (D / "consolidation_report.json").write_text(json.dumps(report, indent=2))
    print(f"lines {result.lines_before} -> {result.lines_after}  (<40: {report['under_40']})")
    for g in graded:
        print(f"  {g['id']:<18} expected={g['expected']:<5} got={g['actual_kept']:<7} {'OK' if g['correct'] else 'WRONG'}")


if __name__ == "__main__":
    main()
