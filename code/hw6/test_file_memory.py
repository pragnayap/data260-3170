"""Offline tests for file_memory.py -- no model, no network. Run: pytest code/hw6/test_file_memory.py"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import file_memory as fm
import file_memory_cli as cli

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


def mem(n_facts: int, stamp: datetime | None) -> str:
    head = "# MEMORY.md\n" + (f"<!-- last_consolidated: {stamp.isoformat()} -->\n" if stamp else "")
    return head + "\n".join(f"- [2026-10-01] fact number {i}" for i in range(n_facts)) + "\n"


def test_count_ignores_blank_and_comment_lines():
    assert fm.count_memory_lines("# t\n\n<!-- c -->\n- a\n- b\n") == 3


def test_not_due_when_small_and_fresh():
    assert fm.consolidation_reason(mem(5, NOW - timedelta(hours=1)), NOW) is None


def test_due_when_over_40_lines():
    assert "limit 40" in fm.consolidation_reason(mem(45, NOW), NOW)


def test_exactly_40_lines_is_not_over_the_limit():
    assert fm.consolidation_reason(mem(39, NOW), NOW) is None  # 39 facts + 1 heading = 40


def test_due_when_older_than_24h():
    assert "24 h" in fm.consolidation_reason(mem(3, NOW - timedelta(hours=25)), NOW)


def test_due_when_never_consolidated():
    assert fm.consolidation_reason(mem(3, None), NOW) is not None


def test_prompt_puts_agent_before_memory_and_strips_comments():
    p = fm.build_system_prompt({"agent": "# A\n- rule", "memory": "<!-- hidden -->\n- [2026-10-01] fact"})
    assert p.index("# A") < p.index("fact") and "hidden" not in p


def test_exact_duplicates_merge_without_the_model():
    text = "# M\n- [2026-09-01] SID4 is 3170.\n- [2026-09-03] SID4 is 3170\n"
    r = fm.consolidate_memory(text, lambda m: "{}", NOW)
    assert r.lines_after == 2 and len(r.archived) == 1 and "[2026-09-03]" in r.new_text


def test_contradiction_loser_is_archived_and_noted_not_silently_deleted():
    text = "# M\n- [2026-09-01] port is 5173\n- [2026-09-02] port is 8471\n"
    decision = json.dumps({"contradictions": [{"ids": [1, 2], "keep": 2, "reason": "newer"}]})
    r = fm.consolidate_memory(text, lambda m: decision, NOW)
    assert "5173" not in "".join(l for l in r.new_text.splitlines() if not l.startswith("<!--"))
    assert "resolved contradiction" in r.new_text and "5173" in r.new_text  # recorded in a comment
    assert r.archived[0]["fact"].endswith("port is 5173") and "lost contradiction" in r.archived[0]["reason"]


def test_merge_that_rewrites_wording_archives_the_old_wording():
    text = "# M\n- [2026-09-01] db is s3170_doc\n- [2026-09-02] HW6 adds MongoDB documents and chat memory\n"
    decision = json.dumps({"duplicate_groups": [{"ids": [1, 2], "merged": "HW6 adds MongoDB documents and chat memory"}]})
    r = fm.consolidate_memory(text, lambda m: decision, NOW)
    assert "s3170_doc" in fm.archive_markdown(r) and r.rewritten[0]["id"] == 1


def test_keep_both_removes_nothing():
    text = "# M\n- [2026-09-01] dev: Secure off\n- [2026-09-02] prod: Secure on\n"
    decision = json.dumps({"contradictions": [{"ids": [1, 2], "keep": "both", "reason": "dev vs prod"}]})
    r = fm.consolidate_memory(text, lambda m: decision, NOW)
    assert r.archived == [] and r.lines_after == 3


def test_invalid_ids_and_garbage_are_ignored():
    text = "# M\n- [2026-09-01] a\n- [2026-09-02] b\n"
    decision = json.dumps({"contradictions": [{"ids": [1, 99], "keep": 1}], "obsolete": [{"id": 77}]})
    assert fm.consolidate_memory(text, lambda m: decision, NOW).archived == []
    r = fm.consolidate_memory(text, lambda m: "not json at all", NOW)
    assert r.llm_ok is False and r.archived == []


def test_consolidation_stamps_the_time_and_is_then_not_due():
    r = fm.consolidate_memory(mem(3, None), lambda m: "{}", NOW)
    assert fm.consolidation_reason(r.new_text, NOW) is None


def test_compact_reports_counts_and_keeps_system_message(tmp_path: Path):
    memf = tmp_path / "MEMORY.md"
    memf.write_text("# M\n- [2026-09-01] a\n- [2026-09-02] a\n")
    hist = [{"role": "system", "content": "S"}] + [{"role": "user" if i % 2 == 0 else "assistant", "content": str(i)} for i in range(6)]
    out, new = cli.handle_command("/compact", hist, lambda m: "{}" if "numbered facts" in m[0]["content"] else "- summary", memf, tmp_path / "A.md", tmp_path / "ARCH.md",
                           embed_fn=lambda ts: [[float(i == j) for j in range(len(ts))] for i in range(len(ts))])
    assert "6 -> 1" in out and "3 -> 2" in out and new[0]["content"] == "S" and len(new) == 2


def test_dream_adds_only_new_facts(tmp_path: Path):
    memf = tmp_path / "MEMORY.md"
    memf.write_text("# M\n- [2026-09-01] The user prefers email.\n")
    hist = [{"role": "user", "content": "x"}]
    out, _ = cli.handle_command("/dream", hist, lambda m: '["The user prefers email.", "The user uses port 8470."]', memf, tmp_path / "A.md")
    assert "port 8470" in memf.read_text() and memf.read_text().count("prefers email") == 1


def test_help_lists_all_commands():
    out, _ = cli.handle_command("/help", [], None)
    assert all(c in out for c in ("/memory", "/compact", "/dream", "/help"))


def test_pairwise_decider_merges_same_and_applies_conflict_and_scoped():
    text = ("# M\n- [2026-09-01] SID4 is 3170.\n- [2026-09-03] The SID4 value is 3170 for this student.\n"
            "- [2026-09-02] port is 5173\n- [2026-09-09] port is 8471\n- [2026-09-12] dev: Secure off\n- [2026-10-03] prod: Secure on\n")
    texts = ["SID4 is 3170.", "The SID4 value is 3170 for this student.", "port is 5173", "port is 8471", "dev: Secure off", "prod: Secure on"]
    groups = [[1, 0, 0], [1, 0, 0], [0, 1, 0], [0, 1, 0], [0, 0, 1], [0, 0, 1]]
    embed = lambda ts: [groups[texts.index(t)] for t in ts]

    def llm(msgs):
        c = msgs[0]["content"]
        if "TEMPORARY or LASTING" in c:
            return "LASTING - fine"
        pair = c[c.index("\nA: ") : c.index("Answer with exactly")]   # the real pair, before the few-shot examples
        if "SID4" in pair:
            return "VERDICT: SAME\nKEEP: B\nREASON: same fact"
        if "port is" in pair:
            return "VERDICT: CONFLICT\nKEEP: B\nREASON: newer"
        return "VERDICT: SCOPED\nKEEP: BOTH\nREASON: dev vs prod"

    r = fm.consolidate_memory(text, llm, NOW, embed_fn=embed)
    live = "\n".join(l for l in r.new_text.splitlines() if not l.startswith("<!--"))
    assert "5173" not in live and "8471" in live and "Secure off" in live and "Secure on" in live
    assert live.count("SID4") == 1 and len(r.archived) == 2 and len(r.pair_verdicts) == 3


def test_guard_refuses_a_consolidation_that_archives_most_of_the_file():
    text = "# M\n" + "\n".join(f"- [2026-09-{i:02d}] fact {i}" for i in range(1, 11)) + "\n"
    decision = json.dumps({"obsolete": [{"id": i, "reason": "x"} for i in range(1, 8)]})
    r = fm.consolidate_memory(text, lambda m: decision, NOW)
    assert r.aborted and r.archived == [] and r.lines_after == r.lines_before
    assert all(f"fact {i}" in r.new_text for i in range(1, 11))


def test_temporary_verdict_needs_a_time_cue_in_the_note():
    assert fm.TIME_CUES.search("Remember to restart uvicorn today.")
    assert fm.TIME_CUES.search("Lucky is currently waiting for the image.")
    assert not fm.TIME_CUES.search("The backend must listen on port 8470.")
    assert not fm.TIME_CUES.search("PyTorch is pinned to 2.2.2 and may change later.")
