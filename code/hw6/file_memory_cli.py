"""
HW6 Part 4 - chat CLI backed by AGENT.md + MEMORY.md.

Commands:
    /memory    show the current file-based memory
    /compact   consolidate MEMORY.md and compact the conversation; report counts before/after
    /dream     pull durable facts out of the recent conversation into MEMORY.md
    /help      list the commands
    /exit      quit

On start-up the files are loaded into the system prompt, and if consolidation is
due (more than 40 content lines, or last consolidated more than 24 h ago) it runs
before the first turn.

    python code/hw6/file_memory_cli.py                  # interactive
    python code/hw6/file_memory_cli.py --script f.txt   # run lines from a file, echoing them
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import file_memory as fm  # noqa: E402

HELP = """Commands:
  /memory   show the current file-based memory (AGENT.md summary + MEMORY.md)
  /compact  consolidate MEMORY.md (merge duplicates, resolve contradictions, archive the rest)
            and compact the conversation; reports message counts before and after
  /dream    identify durable facts in the recent conversation and add them to MEMORY.md
  /help     show this help
  /exit     quit"""


def default_llm(messages: list[dict]) -> str:
    """One model call through the HW1 adapter. If S3170_LLM_CACHE names a JSON file, replies are cached
    there by prompt hash (temperature 0), which makes demos and re-runs reproducible and fast."""
    import hashlib
    import json
    import os

    cache_path = os.environ.get("S3170_LLM_CACHE")
    key = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()
    cache = {}
    if cache_path and Path(cache_path).exists():
        cache = json.loads(Path(cache_path).read_text())
        if key in cache:
            return cache[key]
    from model_client import ModelClient

    out = ModelClient().complete(messages)
    if cache_path:
        cache[key] = out
        Path(cache_path).write_text(json.dumps(cache))
    return out


_embedder = None


def embed_texts(texts: list[str]) -> list[list[float]]:
    """MiniLM sentence embeddings (the same model HW3 and the MongoDB episodes use), unit length."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return [list(map(float, v)) for v in _embedder.encode(texts, normalize_embeddings=True)]


def do_consolidate(llm, memory_path: Path = fm.MEMORY_MD, archive_path: Path = fm.ARCHIVE_MD,
                   embed_fn=None) -> fm.ConsolidationResult:
    embed_fn = embed_fn or embed_texts
    text = memory_path.read_text() if memory_path.exists() else ""
    result = fm.consolidate_memory(text, llm, embed_fn=embed_fn)
    memory_path.write_text(result.new_text)
    if result.archived:
        prev = archive_path.read_text() if archive_path.exists() else "# MEMORY.archive.md\nFacts removed by consolidation, with the reason.\n"
        archive_path.write_text(prev.rstrip("\n") + "\n" + fm.archive_markdown(result))
    if result.aborted:
        print("[consolidate] guard refused: " + "; ".join(n for n in result.notes if n.startswith("ABORTED")))
    return result


def handle_command(cmd: str, history: list[dict], llm, memory_path: Path = fm.MEMORY_MD,
                   agent_path: Path = fm.AGENT_MD, archive_path: Path = fm.ARCHIVE_MD, embed_fn=None) -> tuple[str, list[dict]]:
    """Run one slash command. Returns (text to print, possibly-replaced history)."""
    cmd = cmd.strip().lower()
    if cmd == "/help":
        return HELP, history
    files = fm.load_files(agent_path, memory_path)
    if cmd == "/memory":
        n = fm.count_memory_lines(files["memory"])
        last = fm.read_last_consolidated(files["memory"])
        due = fm.consolidation_reason(files["memory"])
        head = (f"[MEMORY.md] {n} content lines, last consolidated "
                f"{last.isoformat(timespec='seconds') if last else 'never'}; "
                f"consolidation {'DUE: ' + due if due else 'not due'}")
        agent_n = sum(1 for ln in files["agent"].splitlines() if ln.lstrip().startswith("- "))
        return f"{head}\n[AGENT.md] {agent_n} instruction bullets\n\n{files['memory'].rstrip()}", history
    if cmd == "/compact":
        msgs_before = sum(1 for m in history if m["role"] != "system")
        lines_before = fm.count_memory_lines(files["memory"])
        result = do_consolidate(llm, memory_path, archive_path, embed_fn)
        new_history = fm.compact_history(history, llm)
        msgs_after = sum(1 for m in new_history if m["role"] != "system")
        return (
            f"[/compact] conversation messages: {msgs_before} -> {msgs_after}\n"
            f"[/compact] MEMORY.md content lines: {lines_before} -> {result.lines_after}\n"
            f"[/compact] merged groups: {len(result.merges)}, contradictions resolved: "
            f"{sum(r['kept'] != 'both' for r in result.resolutions)} "
            f"(+{sum(r['kept'] == 'both' for r in result.resolutions)} scoped pairs kept as-is), "
            f"archived facts: {len(result.archived)} (see {archive_path.name})"
            + ("" if result.llm_ok else "\n[/compact] WARNING: model decisions unavailable; only exact duplicates merged"),
            new_history,
        )
    if cmd == "/dream":
        new = fm.dream_facts(history, files["memory"], llm)
        if not new:
            return "[/dream] no new durable facts found", history
        today = datetime.now(timezone.utc).date().isoformat()
        memory_path.write_text(fm.append_facts(files["memory"], new, today))
        why = fm.consolidation_reason(memory_path.read_text())
        out = "[/dream] added to MEMORY.md:\n" + "\n".join(f"  + {f}" for f in new)
        return out + (f"\n[/dream] consolidation now due: {why} (run /compact)" if why else ""), history
    return f"Unknown command {cmd!r}. Type /help.", history


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--script", help="file of input lines to run instead of reading the keyboard")
    args = ap.parse_args()

    files = fm.load_files()
    history = [{"role": "system", "content": fm.build_system_prompt(files)}]
    why = fm.consolidation_reason(files["memory"])
    print(f"Loaded AGENT.md ({len(files['agent'])} chars) and MEMORY.md "
          f"({fm.count_memory_lines(files['memory'])} content lines).")
    if why:
        print(f"[startup] consolidation required: {why}")
        r = do_consolidate(default_llm)
        print(f"[startup] consolidated MEMORY.md: {r.lines_before} -> {r.lines_after} lines")
        history[0]["content"] = fm.build_system_prompt(fm.load_files())
    print("Type a message, or /help.\n")

    source = iter(Path(args.script).read_text().splitlines()) if args.script else None
    while True:
        try:
            line = next(source) if source is not None else input("You: ")
        except (StopIteration, EOFError, KeyboardInterrupt):
            break
        line = line.strip()
        if not line:
            continue
        if source is not None:
            print(f"You: {line}")
        if line == "/exit":
            break
        if line.startswith("/"):
            out, history = handle_command(line, history, default_llm)
            print(out + "\n")
            continue
        history.append({"role": "user", "content": line})
        reply = default_llm(history)
        history.append({"role": "assistant", "content": reply})
        print(f"Assistant: {reply}\n")


if __name__ == "__main__":
    main()
