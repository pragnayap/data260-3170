"""
HW6 Part 4 - file-based memory: AGENT.md (instructions) + MEMORY.md (learned facts).

    load_files()             read both Markdown files
    build_system_prompt()    AGENT.md + MEMORY.md folded into one system prompt
    consolidation_reason()   None, or why MEMORY.md must be consolidated now
    consolidate_memory()     merge duplicates, resolve contradictions, archive the rest
    compact_history()        collapse a chat history into one summary message

MEMORY.md format: one fact per line, "- [YYYY-MM-DD] text", under "##" headings.
A single HTML comment records when it was last consolidated:
    <!-- last_consolidated: 2026-10-14T20:00:00+00:00 -->
Comment lines and blank lines never count toward the 40-line threshold.

Consolidation never deletes silently. The model only *decides* (which ids are
duplicates, which contradict, which are obsolete); this module applies the
decisions, and every fact it removes is (a) written to MEMORY.archive.md with the
reason and (b) mentioned in an HTML comment left in MEMORY.md at the spot.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

AGENT_MD = ROOT / "AGENT.md"
MEMORY_MD = ROOT / "MEMORY.md"
ARCHIVE_MD = ROOT / "MEMORY.archive.md"

MAX_LINES = 40            # consolidate when MORE than this many non-empty, non-comment lines
MAX_AGE = timedelta(hours=24)
GUARD_MIN_FACTS = 10          # the guard is meaningless on tiny files
MAX_ARCHIVE_FRACTION = 0.45   # consolidation refuses to archive more than this share of facts
TS_RE = re.compile(r"<!--\s*last_consolidated:\s*(\S+?)\s*-->")
FACT_RE = re.compile(r"^-\s*(?:\[(\d{4}-\d{2}-\d{2})\]\s*)?(.+)$")

LlmFn = Callable[[list[dict]], str]
EmbedFn = Callable[[list[str]], list[list[float]]]


# --------------------------------------------------------------------------- #
# loading, counting, prompt
# --------------------------------------------------------------------------- #

def load_files(agent_path: Path = AGENT_MD, memory_path: Path = MEMORY_MD) -> dict[str, str]:
    """Return {'agent': ..., 'memory': ...}; a missing file loads as an empty string."""
    read = lambda p: p.read_text() if p.exists() else ""  # noqa: E731
    return {"agent": read(agent_path), "memory": read(memory_path)}


def is_content_line(line: str) -> bool:
    s = line.strip()
    return bool(s) and not (s.startswith("<!--") and s.endswith("-->"))


def count_memory_lines(memory_text: str) -> int:
    """Non-empty, non-comment lines (headings count; HTML comment lines do not)."""
    return sum(1 for ln in memory_text.splitlines() if is_content_line(ln))


def read_last_consolidated(memory_text: str) -> datetime | None:
    m = TS_RE.search(memory_text)
    if not m:
        return None
    try:
        ts = datetime.fromisoformat(m.group(1))
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def consolidation_reason(memory_text: str, now: datetime | None = None) -> str | None:
    """Why MEMORY.md needs consolidating, or None. Rule: >40 content lines OR >24 h since last."""
    now = now or datetime.now(timezone.utc)
    n = count_memory_lines(memory_text)
    if n > MAX_LINES:
        return f"{n} non-empty, non-comment lines (limit {MAX_LINES})"
    last = read_last_consolidated(memory_text)
    if last is None:
        return "no last_consolidated timestamp recorded"
    if now - last > MAX_AGE:
        hours = (now - last).total_seconds() / 3600
        return f"last consolidated {hours:.1f} h ago (limit 24 h)"
    return None


def strip_comments(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if is_content_line(ln))


def build_system_prompt(files: dict[str, str]) -> str:
    """AGENT.md first (instructions outrank memory), then MEMORY.md without bookkeeping comments."""
    parts = [files["agent"].strip()]
    mem = strip_comments(files["memory"])
    if mem:
        parts.append("# Durable memory (MEMORY.md)\nFacts from earlier conversations:\n" + mem)
    return "\n\n".join(p for p in parts if p)


# --------------------------------------------------------------------------- #
# consolidation
# --------------------------------------------------------------------------- #

@dataclass
class Fact:
    idx: int          # 1-based position among fact lines
    line_no: int      # index into the original line list
    date: str | None
    text: str

    def render(self) -> str:
        return f"- [{self.date}] {self.text}" if self.date else f"- {self.text}"


@dataclass
class ConsolidationResult:
    new_text: str
    lines_before: int
    lines_after: int
    archived: list[dict] = field(default_factory=list)   # {id, fact, reason}
    resolutions: list[dict] = field(default_factory=list)  # contradiction decisions as applied
    merges: list[dict] = field(default_factory=list)
    llm_ok: bool = True
    aborted: bool = False
    rewritten: list[dict] = field(default_factory=list)   # wording replaced when facts were merged
    proposed_archive: list[dict] = field(default_factory=list)   # what an aborted run would have removed
    pair_verdicts: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).strip()


def parse_facts(lines: list[str]) -> list[Fact]:
    facts = []
    for i, ln in enumerate(lines):
        m = FACT_RE.match(ln.strip())
        if m and not ln.lstrip().startswith("#"):
            facts.append(Fact(len(facts) + 1, i, m.group(1), m.group(2).strip()))
    return facts


DECIDE_PROMPT = """You maintain a project memory file. Below are its numbered facts.
Find (1) duplicates / near-duplicates, (2) contradictions, (3) obsolete one-off notes.

Rules:
- duplicate_groups: facts that say the same thing. Give ALL ids in the group and one
  "merged" sentence that keeps every detail; keep the most recent date.
- contradictions: two facts that cannot both be true. Say which id to keep and why.
  Prefer the more recent fact unless the older one is explicitly marked as fixed/assigned.
  If both are true in different contexts, use "keep": "both" and explain the scope.
- obsolete: one-off task notes or temporary states with no lasting value.
- Use only ids that appear below. Never put an id in more than one list.

Reply with ONLY this JSON (empty lists allowed):
{"duplicate_groups": [{"ids": [1, 2], "merged": "..."}],
 "contradictions": [{"ids": [3, 4], "keep": 4, "reason": "..."}],
 "obsolete": [{"id": 5, "reason": "..."}]}

FACTS:
"""


def _extract_json(raw: str) -> dict | None:
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S)
    m = re.search(r"\{.*\}", raw, flags=re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


PAIR_PROMPT = """Two facts from a project memory file. Decide how they relate.

A: {a}
B: {b}

Answer with exactly three lines:
VERDICT: SAME | CONFLICT | SCOPED | UNRELATED
KEEP: A | B | BOTH
REASON: one short sentence

SAME = both state the same thing in different words; one adds nothing. KEEP: B.
CONFLICT = they give different values for the SAME setting, so they cannot both be true.
  Keep the fact that says it is fixed / assigned / "do not change"; if neither does, keep the
  newer one (later date).
SCOPED = ONLY if each fact itself names a different situation (e.g. "in development" vs
  "in production"), so both are true. KEEP: BOTH. Never use SCOPED just because the facts differ.
UNRELATED = different topics, or compatible facts about the same topic.

Examples:
A: [2026-09-01] The API listens on port 9000. / B: [2026-09-02] The API port is 9000.
-> VERDICT: SAME, KEEP: B
A: [2026-09-01] The cache is Redis. / B: [2026-09-09] The cache is Memcached.
-> VERDICT: CONFLICT, KEEP: B (newer)
A: [2026-09-01] Debug logging is on in development. / B: [2026-09-02] Debug logging is off in production.
-> VERDICT: SCOPED, KEEP: BOTH
A: [2026-09-01] The team uses Python. / B: [2026-09-02] The database is MySQL.
-> VERDICT: UNRELATED, KEEP: BOTH"""

TEMP_PROMPT = """Decide whether this note from a project memory file is TEMPORARY or LASTING.

TEMPORARY only if it contains a time reference or to-do wording such as: today, tonight, this morning,
right now, currently waiting, pending, still running, remember to, ask someone, review later.
LASTING if it states a stable setting, version, port, name, rule, decision or historical fact.
A fact that merely "may change" is still LASTING.

Examples:
"Remember to restart the server after editing today." -> TEMPORARY
"The job is still running in the background right now." -> TEMPORARY
"The API listens on port 9000." -> LASTING
"The student is in the data science program." -> LASTING

Note: {t}

Answer on one line: TEMPORARY or LASTING, then " - " and a short reason."""

# 0.30 is low on purpose: a contradiction can be worded very differently from the fact it
# overturns (README password vs .env secrets scores only 0.32), and the model, not the
# embedding, is the judge. Cost: ~90 short pair calls for a 55-fact file.
# A model verdict of TEMPORARY only counts if the note also carries an explicit time or to-do cue.
# qwen3:8b alone flagged 39 of 48 lasting facts as temporary; requiring the cue makes the claim checkable.
TIME_CUES = re.compile(
    r"\b(today|tonight|this (morning|afternoon|evening|week)|right now|currently|pending|still running|"
    r"remember to|ask the|waiting for|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I)

PAIR_THRESHOLD = 0.30
SAME_MIN_COSINE = 0.6   # a SAME verdict also needs embedding closeness; same-topic != same-fact (0.39-0.53)
PAIR_CAP = 100          # hard cap on model calls for pairs


def _cos(u, v) -> float:
    import math
    d = sum(a * b for a, b in zip(u, v))
    return d / ((math.sqrt(sum(a * a for a in u)) * math.sqrt(sum(b * b for b in v))) or 1.0)


def decide_pairwise(live: list[Fact], llm: LlmFn, embed_fn: EmbedFn, notes: list[str]) -> dict:
    """Build the same decision dict as the single-prompt path, from many small model questions.

    1. embed every fact; candidate pairs = cosine >= PAIR_THRESHOLD (best first, capped)
    2. ask the model about each pair: SAME / CONFLICT / SCOPED / UNRELATED
    3. SAME pairs are unioned into groups; the group keeps its most detailed wording
    4. CONFLICT / SCOPED pairs become contradiction decisions, mapped onto group representatives
    5. ask once per fact whether it is a temporary note
    """
    vecs = embed_fn([f.text for f in live])
    pairs = sorted(((_cos(vecs[i], vecs[j]), live[i], live[j])
                    for i in range(len(live)) for j in range(i + 1, len(live))), key=lambda x: -x[0])
    pairs = [p for p in pairs if p[0] >= PAIR_THRESHOLD][:PAIR_CAP]
    notes.append(f"{len(pairs)} candidate pairs at cosine >= {PAIR_THRESHOLD}")

    verdicts, conflicts, same_pairs = [], [], []
    for sim, a, b in pairs:
        raw = re.sub(r"<think>.*?</think>", "", llm([{"role": "user", "content": PAIR_PROMPT.format(a=a.render()[2:], b=b.render()[2:])}]), flags=re.S)
        v = re.search(r"VERDICT:\s*(SAME|CONFLICT|SCOPED|UNRELATED)", raw, flags=re.I)
        k = re.search(r"KEEP:\s*(A|B|BOTH)", raw, flags=re.I)
        why = re.search(r"REASON:\s*(.+)", raw)
        verdict = v.group(1).upper() if v else "UNRELATED"
        verdicts.append({"a": a.idx, "b": b.idx, "cosine": round(sim, 3), "verdict": verdict,
                         "keep": k.group(1).upper() if k else None, "reason": why.group(1).strip() if why else ""})
        if verdict == "SAME" and sim >= SAME_MIN_COSINE:
            same_pairs.append((a.idx, b.idx))
        elif verdict == "SAME":
            verdicts[-1]["verdict"] = "SAME_REJECTED_LOW_COSINE"
        elif verdict in ("CONFLICT", "SCOPED"):
            conflicts.append((a, b, verdict, verdicts[-1]))
    notes.append(f"pair verdicts: " + ", ".join(f"{n}={sum(v['verdict'] == n for v in verdicts)}" for n in ("SAME", "CONFLICT", "SCOPED", "UNRELATED")))

    by = {f.idx: f for f in live}
    # Star grouping, not transitive closure: a fact joins a group only if it was directly judged SAME
    # as that group's representative, so one wrong SAME verdict cannot chain unrelated facts together.
    rep_of: dict[int, int] = {}
    groups: dict[int, list[int]] = {}
    for a_id, b_id in same_pairs:                      # already in descending-cosine order
        ra, rb = rep_of.get(a_id), rep_of.get(b_id)
        if ra is None and rb is None:
            rep_of[a_id] = rep_of[b_id] = a_id
            groups[a_id] = [a_id, b_id]
        elif ra is None and rb == b_id:
            rep_of[a_id] = b_id
            groups[b_id].append(a_id)
        elif rb is None and ra == a_id:
            rep_of[b_id] = a_id
            groups[a_id].append(b_id)
    dup_groups = []
    for rep, members in groups.items():
        best = max(members, key=lambda i: len(by[i].text))
        dup_groups.append({"ids": [rep] + sorted(m for m in members if m != rep), "merged": by[best].text})

    # One decision per fact: conflicts arrive best-match first; a later one that touches a fact
    # already decided is ignored (recorded in the verdict log) rather than letting it overturn the first.
    contradictions, touched = [], set()
    for a, b, verdict, info in conflicts:
        ra, rb = rep_of.get(a.idx, a.idx), rep_of.get(b.idx, b.idx)
        if ra == rb:
            continue
        keep = info["keep"]
        if verdict == "SCOPED" or keep == "BOTH":      # removes nothing, so it never blocks a real conflict
            contradictions.append({"ids": [ra, rb], "keep": "both", "reason": info["reason"]})
            continue
        if ra in touched or rb in touched:
            info["ignored"] = "a fact in this pair already has a higher-similarity decision"
            continue
        touched.update((ra, rb))
        if keep in ("A", "B"):
            contradictions.append({"ids": [ra, rb], "keep": ra if keep == "A" else rb, "reason": info["reason"]})
    obsolete = []
    for f in live:
        raw = re.sub(r"<think>.*?</think>", "", llm([{"role": "user", "content": TEMP_PROMPT.format(t=f.text)}]), flags=re.S).strip()
        if raw.upper().startswith("TEMPORARY") and TIME_CUES.search(f.text):
            obsolete.append({"id": f.idx, "reason": raw.split("-", 1)[-1].strip() if "-" in raw else "temporary note"})
    notes.append(f"{len(dup_groups)} duplicate groups, {len(contradictions)} contradiction decisions, {len(obsolete)} temporary notes")
    return {"duplicate_groups": dup_groups, "contradictions": contradictions, "obsolete": obsolete, "_pair_verdicts": verdicts}


def consolidate_memory(text: str, llm: LlmFn, now: datetime | None = None,
                       embed_fn: EmbedFn | None = None) -> ConsolidationResult:
    """Consolidate MEMORY text. With embed_fn, the model is asked small pairwise questions
    (decide_pairwise); without it, one whole-file prompt (decide_single_prompt)."""
    now = now or datetime.now(timezone.utc)
    lines = text.splitlines()
    facts = parse_facts(lines)
    by_idx = {f.idx: f for f in facts}
    before = count_memory_lines(text)
    res = ConsolidationResult(new_text=text, lines_before=before, lines_after=before)
    removed: dict[int, str] = {}          # idx -> reason
    notes_at: dict[int, list[str]] = {}   # line_no -> comment lines to insert after

    def archive(idx: int, reason: str) -> None:
        if idx in by_idx and idx not in removed:
            removed[idx] = reason
            res.archived.append({"id": idx, "fact": by_idx[idx].render(), "reason": reason})

    # Pass 1 (deterministic): exact duplicates after normalisation. Keep the latest-dated copy.
    seen: dict[str, Fact] = {}
    for f in facts:
        key = _norm(f.text)
        if key in seen:
            keep = seen[key]
            if (f.date or "") > (keep.date or ""):
                keep.date = f.date
            archive(f.idx, f"exact duplicate of F{keep.idx}")
            res.merges.append({"kept": keep.idx, "removed": [f.idx], "how": "exact"})
        else:
            seen[key] = f

    # Pass 2 (model): near-duplicates, contradictions, obsolete notes.
    live = [f for f in facts if f.idx not in removed]
    listing = "\n".join(f"F{f.idx}: {f.render()[2:]}" for f in live)
    if embed_fn is not None:
        decisions = decide_pairwise(live, llm, embed_fn, res.notes)
    else:
        decisions = None
        for attempt in (1, 2):
            decisions = _extract_json(llm([{"role": "user", "content": DECIDE_PROMPT + listing}]))
            if decisions is not None:
                break
            res.notes.append(f"model reply was not valid JSON (attempt {attempt})")
    if decisions is None:
        res.llm_ok = False
    else:
        res.pair_verdicts = decisions.pop("_pair_verdicts", [])
        ids = lambda xs: [int(x) for x in xs if isinstance(x, (int, str)) and str(x).lstrip("F").isdigit()]  # noqa: E731
        for g in decisions.get("duplicate_groups", []) or []:
            gid = [i for i in ids([str(x).lstrip("F") for x in g.get("ids", [])]) if i in by_idx and i not in removed]
            if len(gid) < 2:
                continue
            keep = by_idx[gid[0]]
            merged = str(g.get("merged") or keep.text).strip()
            newest = max((by_idx[i].date or "" for i in gid)) or keep.date
            if _norm(merged) != _norm(keep.text):      # never overwrite wording without keeping the old text
                res.rewritten.append({"id": keep.idx, "fact": keep.render(), "reason": f"wording replaced when merged with {', '.join('F%d' % i for i in gid[1:])}"})
            keep.text, keep.date = merged, newest or keep.date
            for i in gid[1:]:
                archive(i, f"near-duplicate merged into F{keep.idx}")
            res.merges.append({"kept": keep.idx, "removed": gid[1:], "how": "model", "merged_text": merged})
        for c in decisions.get("contradictions", []) or []:
            cid = [i for i in ids([str(x).lstrip("F") for x in c.get("ids", [])]) if i in by_idx and i not in removed]
            if len(cid) != 2:
                continue
            keep_raw = str(c.get("keep", "")).lstrip("F")
            reason = str(c.get("reason", "")).strip() or "no reason given"
            if keep_raw == "both":
                res.resolutions.append({"ids": cid, "kept": "both", "reason": reason})   # report only: most "scoped"
                continue                                                          # verdicts are just unrelated facts
            if not keep_raw.isdigit() or int(keep_raw) not in cid:
                continue
            keep = int(keep_raw)
            lose = cid[0] if cid[1] == keep else cid[1]
            res.resolutions.append({"ids": cid, "kept": keep, "dropped": lose, "reason": reason})
            archive(lose, f"lost contradiction to F{keep}: {reason}")
            notes_at.setdefault(by_idx[keep].line_no, []).append(
                f"<!-- resolved contradiction: kept \"{by_idx[keep].text}\" over "
                f"\"{by_idx[lose].text}\" ({reason}) -->")
        for o in decisions.get("obsolete", []) or []:
            try:
                oid = int(str(o.get("id")).lstrip("F"))
            except (TypeError, ValueError):
                continue
            archive(oid, f"obsolete: {str(o.get('reason', '')).strip() or 'one-off note'}")

    # Safety guard: a consolidation that archives most of the file is a model failure, not a
    # consolidation. Refuse to apply it; the original text is kept untouched.
    if len(facts) >= GUARD_MIN_FACTS and len(removed) > MAX_ARCHIVE_FRACTION * len(facts):
        res.notes.append(f"ABORTED: would archive {len(removed)} of {len(facts)} facts "
                         f"(> {int(MAX_ARCHIVE_FRACTION * 100)}%); file left unchanged")
        res.aborted = True
        res.proposed_archive = list(res.archived)
        removed.clear()
        res.archived.clear()
        res.rewritten.clear()
        res.resolutions.clear()
        res.merges.clear()
        notes_at.clear()
        for f, fresh in zip(facts, parse_facts(lines)):   # undo merged wording / dates
            f.text, f.date = fresh.text, fresh.date

    # Rebuild the file.
    removed_lines = {by_idx[i].line_no for i in removed}
    fact_by_line = {f.line_no: f for f in facts}
    out = []
    for i, ln in enumerate(lines):
        if TS_RE.search(ln):
            continue
        if i in removed_lines:
            continue
        out.append(fact_by_line[i].render() if i in fact_by_line else ln)
        out.extend(notes_at.get(i, []))
    # drop headings left with no facts under them
    cleaned: list[str] = []
    for j, ln in enumerate(out):
        if ln.lstrip().startswith("##"):
            nxt = next((x for x in out[j + 1:] if is_content_line(x)), "")
            if not nxt or nxt.lstrip().startswith("#"):
                continue
        cleaned.append(ln)
    stamp = f"<!-- last_consolidated: {now.isoformat(timespec='seconds')} -->"
    head = cleaned[0] if cleaned and cleaned[0].startswith("# ") else None
    body = cleaned[1:] if head else cleaned
    final = ([head] if head else []) + [stamp] + body
    res.new_text = "\n".join(final).rstrip() + "\n"
    res.lines_after = count_memory_lines(res.new_text)
    assert len(res.archived) == len(removed), "every removed fact must be archived"
    return res


def archive_markdown(result: ConsolidationResult, when: datetime | None = None) -> str:
    when = (when or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    rows = "\n".join(f"- ({a['reason']}) {a['fact'][2:]}" for a in result.archived + result.rewritten)
    return f"\n## Consolidation {when}\n{rows}\n"


# --------------------------------------------------------------------------- #
# /compact for the conversation, /dream for new facts
# --------------------------------------------------------------------------- #

COMPACT_PROMPT = (
    "Summarize this conversation in at most 6 bullet points, keeping every concrete "
    "fact, decision and open question. Output only the bullets.\n\n"
)
DREAM_PROMPT = (
    "From the conversation below, list durable facts about the user or project that "
    "will still matter in future sessions (preferences, decisions, constraints, names, "
    "ports). Skip small talk and anything temporary. Reply with ONLY a JSON array of "
    'short strings, e.g. ["The user prefers email over SMS"], or [] if nothing qualifies.\n\n'
)


def compact_history(history: list[dict], llm: LlmFn) -> list[dict]:
    """Replace the non-system messages with one summary message; system messages are kept."""
    system = [m for m in history if m["role"] == "system"]
    rest = [m for m in history if m["role"] != "system"]
    if not rest:
        return history
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in rest)
    summary = re.sub(r"<think>.*?</think>", "", llm([{"role": "user", "content": COMPACT_PROMPT + transcript}]), flags=re.S)
    return system + [{"role": "assistant", "content": "Summary of the conversation so far:\n" + summary.strip()}]


def dream_facts(history: list[dict], memory_text: str, llm: LlmFn) -> list[str]:
    """Durable facts from recent conversation that MEMORY.md does not already hold."""
    rest = [m for m in history if m["role"] != "system"][-20:]
    if not rest:
        return []
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in rest)
    raw = re.sub(r"<think>.*?</think>", "", llm([{"role": "user", "content": DREAM_PROMPT + transcript}]), flags=re.S)
    m = re.search(r"\[.*\]", raw, flags=re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    known = {_norm(f.text) for f in parse_facts(memory_text.splitlines())}
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, str) and it.strip() and _norm(it) not in known:
            out.append(it.strip())
            known.add(_norm(it))
    return out[:5]


def append_facts(memory_text: str, facts: list[str], today: str) -> str:
    """Append facts under a '## Learned' heading (created if absent)."""
    if not facts:
        return memory_text
    text = memory_text.rstrip("\n")
    if "## Learned" not in text:
        text += "\n\n## Learned"
    return text + "\n" + "\n".join(f"- [{today}] {f}" for f in facts) + "\n"
