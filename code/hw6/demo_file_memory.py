"""
HW6 Part 4 evidence run on a TEMPORARY copy of the files (the repo's MEMORY.md is never touched):
/help, /memory, three chat turns, /dream, /memory, /compact (55-line test file -> consolidated).
Prints a banner with the student's name (required in terminal screenshots) and saves the transcript
to reports/hw06/raw/demo_file_memory.txt.

    S3170_LLM_CACHE=reports/hw06/memory_test/llm_cache.json python -u code/hw6/demo_file_memory.py
"""

import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import file_memory as fm  # noqa: E402
import file_memory_cli as cli  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "hw06" / "raw" / "demo_file_memory.txt"
lines: list[str] = []


def say(text: str = "") -> None:
    print(text, flush=True)
    lines.append(text)


def main() -> None:
    td = Path(tempfile.mkdtemp(prefix="hw6_filemem_"))
    mem, agent, arch = td / "MEMORY.md", td / "AGENT.md", td / "MEMORY.archive.md"
    shutil.copy(ROOT / "reports/hw06/memory_test/MEMORY.original.md", mem)
    shutil.copy(ROOT / "AGENT.md", agent)
    say("=" * 72)
    say("DATA 260 HW6 - file-based memory demo     Student: Pragnaya Priyadarshini (Lucky)")
    say(f"{datetime.now().isoformat(timespec='seconds')}   working copy: {td}")
    say("=" * 72)
    files = fm.load_files(agent, mem)
    say(f"Loaded AGENT.md ({len(files['agent'])} chars) and MEMORY.md ({fm.count_memory_lines(files['memory'])} content lines).")
    say(f"[startup check] consolidation required: {fm.consolidation_reason(files['memory'])}")
    history = [{"role": "system", "content": fm.build_system_prompt(files)}]

    def cmd(c: str) -> None:
        nonlocal history
        say(f"\nYou: {c}")
        out, history = cli.handle_command(c, history, cli.default_llm, mem, agent, arch)
        say(out)

    cmd("/help")
    for q in ("I prefer short answers. My project uses the Transit Incident domain with routeId as the primary field.",
              "Remember that I always run the backend on port 8470 and the frontend on 8471.",
              "Which port do I use for the backend?"):
        say(f"\nYou: {q}")
        history.append({"role": "user", "content": q})
        reply = cli.default_llm(history)
        history.append({"role": "assistant", "content": reply})
        say(f"Assistant: {reply}")
    cmd("/dream")
    cmd("/compact")
    say("\n--- MEMORY.md after /compact (first 20 lines) ---")
    say("\n".join(mem.read_text().splitlines()[:20]))
    say(f"\n[post-check] consolidation required now: {fm.consolidation_reason(mem.read_text())}")
    OUT.write_text("\n".join(lines) + "\n")
    say(f"saved {OUT}")


if __name__ == "__main__":
    main()
