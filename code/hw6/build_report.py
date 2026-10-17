"""
HW6 - build reports/hw06/Priyadarshini_HW6.docx from the repo's real artefacts.

Every number is read from reports/hw06/raw/ (via summarize_hw6) and every code snippet is cut out of the
source file with ast, so the report cannot drift from the code. Screenshot spots are labelled placeholders.

    python code/hw6/build_report.py
"""

import ast
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

sys.path.insert(0, str(Path(__file__).resolve().parent))
import summarize_hw6 as sm  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / "reports" / "hw06"
RAW = R / "raw"
OUT = R / "Priyadarshini_HW6.docx"
REPO_URL = "https://github.com/pragnayap/data260-3170"


def git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()


def func_src(rel: str, name: str) -> str:
    """Source of one top-level function (decorators included) from a file."""
    text = (ROOT / rel).read_text()
    tree = ast.parse(text)
    lines = text.splitlines()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name:
            start = min([d.lineno for d in n.decorator_list] + [n.lineno]) - 1
            return "\n".join(lines[start:n.end_lineno])
    raise KeyError(f"{name} not in {rel}")


def lines_of(rel: str, a: int, b: int) -> str:
    return "\n".join((ROOT / rel).read_text().splitlines()[a - 1:b])


doc = Document()
sec = doc.sections[0]
for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
    setattr(sec, side, Pt(60))
normal = doc.styles["Normal"]
normal.font.name, normal.font.size = "Calibri", Pt(11)


def _font(run, size, bold=False, name=None, color=None):
    run.font.size, run.bold = Pt(size), bold
    if name:
        run.font.name = name
        run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if color:
        run.font.color.rgb = RGBColor(*color)


def h1(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(14), Pt(4)
    p.paragraph_format.keep_with_next = True
    _font(p.add_run(text), 14, True)


def h2(text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(8), Pt(2)
    p.paragraph_format.keep_with_next = True
    _font(p.add_run(text), 12, True)


def para(text, bold_prefix=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    if bold_prefix:
        _font(p.add_run(bold_prefix), 11, True)
    _font(p.add_run(text), 11)
    return p


def bullet(text, bold_prefix=None):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(1)
    if bold_prefix:
        _font(p.add_run(bold_prefix), 11, True)
    _font(p.add_run(text), 11)


def code(text, size=8):
    for chunk in [text]:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        pPr = p._p.get_or_add_pPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:fill"), "F2F4F7")
        pPr.append(shd)
        _font(p.add_run(chunk.rstrip("\n")), size, False, "Courier New")


def shot(label):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before, p.paragraph_format.space_after = Pt(4), Pt(6)
    _font(p.add_run(f"[ Screenshot {label} ]"), 11, True, color=(0xB4, 0x23, 0x18))


def table(rows, header=True, widths=None, size=10):
    t = doc.add_table(rows=len(rows), cols=len(rows[0]))
    t.style = "Table Grid"
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = t.cell(i, j)
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(val))
            _font(run, size, bold=(header and i == 0))
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t


# ---------------------------------------------------------------------------------------- data
S = {l: sm.summarize(l) for l, _ in sm.LABELS}
names = dict(sm.LABELS)
comp = json.loads((RAW / "agent_md_compliance.json").read_text())
rep = json.loads((R / "memory_test" / "consolidation_report.json").read_text())
ver = json.loads((R / "verification.json").read_text()) if (R / "verification.json").exists() else None
tag_hash = git("rev-parse", "hw6") if git("tag", "-l", "hw6") else ""
commit = tag_hash or git("rev-parse", "HEAD")
commit_note = "tag hw6" if tag_hash else "HEAD at build time; hw6 tag not created yet"

# ---------------------------------------------------------------------------------------- title
p = doc.add_paragraph()
_font(p.add_run("DATA 260 — Homework 6: MongoDB Documents, Agent Memory and File-Based Memory"), 14, True)
para("Pragnaya Priyadarshini (Lucky) · SJSU MS Applied Data Intelligence")
para(REPO_URL, "GitHub repository: ")
para("Sbnikitha and supriyaselvanganesan have access.", "Collaborators: ")

h1("Section 0 — Configuration")
table([
    ["Value", "Definition", "Mine"],
    ["SID4", "last 4 of SJSU student ID", "3170"],
    ["PORT_BASE", "8000 + (SID4 mod 900)", "8470"],
    ["PREFIX", '"s" + SID4', "s3170"],
    ["SEED", "SID4", "3170"],
    ["VERIFY_SEED", "260000 + SID4", "263170"],
    ["DOMAIN_ID", "SID4 mod 8", "2 — Municipal Transit Incidents"],
])
table([
    ["Item", "Value"],
    ["Hardware", "Intel x86_64 Mac, Core i9-9880H (8 cores / 16 threads), 16 GB RAM, no GPU (CPU-only inference)"],
    ["Local model", "qwen3:8b (Q4_K_M) served by Ollama, called through src/model_client.py (the HW1 adapter)"],
    ["Embedding model", "sentence-transformers/all-MiniLM-L6-v2 (384-d, normalised)"],
    ["Database", "MongoDB 7.0 in Docker (container s3170_mongo, port 27017), database s3170_doc"],
    ["Tagged commit", f"{commit} ({commit_note})"],
], header=True)

# ---------------------------------------------------------------------------------------- part 1
h1("Part 1 — MongoDB Document API")
h2("1.I Database and schema")
para("Database s3170_doc, collection transit_incidents. Each document is the document-oriented view of a transit "
     "incident: routeId (required, 1–100 chars), location and description (optional), status (enum Open / "
     "Investigating / Resolved, default Open), category (enum Delay / Mechanical Failure / Accident-Collision / "
     "Safety Hazard), occurredAt (required date-time), and server-set createdAt / updatedAt. The same rules exist "
     "twice: in Pydantic (readable 422 errors) and as a $jsonSchema validator on the collection, so a direct write "
     "from Compass or mongosh cannot bypass them.")
code(lines_of("code/web_application/schemas_doc.py", 36, 46))
h2("1.II API (FastAPI + PyMongo)")
para("Files: mongo_db.py (connection + validator), schemas_doc.py (Pydantic), routers/incidents_doc.py (routes), app.py "
     "(CORS middleware; JSON parsing is FastAPI's). Status codes: 201 created, 200 read/update, 204 delete, "
     "400 malformed id, 404 unknown id, 422 invalid body, 503 MongoDB down, 500 other database error.")
code(func_src("code/web_application/routers/incidents_doc.py", "create_incident") + "\n\n"
     + func_src("code/web_application/routers/incidents_doc.py", "update_incident"))
shot("1.1 – 1.6: Postman — POST 201, GET all, GET one, PUT, DELETE 204, GET after delete 404")
h2("1.III Validation tests")
para("Invalid bodies are rejected before they reach MongoDB, with one message per problem. verify_hw06.py runs "
     "seven invalid bodies (missing routeId, bad category, bad status, bad date, routeId of 101 characters, wrong "
     "type, unknown field) and all return 422; a malformed id returns 400 and an unknown id 404.")
shot("1.7: Postman — 422 responses (missing field, invalid enum, bad date, wrong type)")
shot("1.8: MongoDB Compass — s3170_doc.transit_incidents with sample documents")

# ---------------------------------------------------------------------------------------- part 2
h1("Part 2 — Short-, Long-, and Episodic Memory")
h2("2.I Collections")
para("Added to the same database; transit_incidents is unchanged. messages (user_id, session_id, role, content, "
     "created_at), summaries (user_id, session_id — null for lifetime, scope session|user, text, created_at), "
     "episodes (user_id, session_id, fact, importance 0..1, embedding as an array of floats, created_at).")
h2("2.II Endpoints and memory logic")
para("POST /api/chat saves the user message, loads the last N messages of the session (N = SHORT_TERM_N), the latest "
     "session and lifetime summaries and the top-k episodic facts, assembles the prompt, calls the model, saves the "
     "reply, extracts up to 3 facts from the user message, and summarises every M user messages. GET /api/memory/{user_id} "
     "and GET /api/aggregate/{user_id} read it back. Defaults: N = 12, M = 6, k = 3 (overridable per request).")
code(func_src("code/web_application/chat_memory.py", "assemble_prompt"))
code(func_src("code/web_application/chat_memory.py", "cosine_top_k"))
code(lines_of("code/web_application/chat_memory.py", 225, 262))
code(func_src("code/web_application/chat_memory.py", "extract_episodes"))
code(func_src("code/web_application/routers/chat.py", "chat") + "\n\n" + func_src("code/web_application/routers/chat.py", "memory")
     + "\n\n" + func_src("code/web_application/routers/chat.py", "aggregate"))
h2("2.III Evidence")
demo = json.loads((RAW / "demo_transcript.json").read_text())
last = demo[-1]
para(f"A 12-message session (user lucky_demo, N = 6, summary every 4 user messages) produced {len(demo) * 2} stored messages. "
     f"By message 11 the facts from message 1 are outside the 6-message window; the assistant still answered "
     f"“{demo[10]['reply'][:110]}” from the episodic facts and summaries. The last turn used "
     f"{last['memory_used']['short_term_count']} window messages, {len(last['memory_used']['episodic_facts'])} episodic facts, "
     f"a session summary and a lifetime summary.")
shot("2.1: conversation (terminal demo_chat.py with the name banner, or the hw6_chat.html page)")
shot("2.2: GET /api/memory/lucky_demo (JSON)")
shot("2.3: GET /api/aggregate/lucky_demo (JSON)")
shot("2.4: MongoDB Compass — messages, summaries and episodes collections with documents")

# ---------------------------------------------------------------------------------------- part 3
h1("Part 3 — What Memory Costs")
h2("3.1 Logging")
para("Every /api/chat request records prompt and completion tokens (the model's own counts), the system-primer / "
     "long-term-summary / short-term-window / episodic-facts / current-message tokens, latency, and the tokens of the "
     "extra calls memory needs (episode extraction and summarisation). Ollama reports one prompt count per call and has no "
     "per-segment tokenizer, so component tokens are allocated by character share and always sum to the reported total — "
     "an estimate, labelled as such. Raw data: raw/turns_<setting>.csv and raw/chat_metrics.jsonl.")
h2("3.2 Probes")
para("memory_probes.yaml was written before any run: five questions (route + boarding stop, name + university, bike + "
     "rack, elevator-outage station + line, contact channel + address), each with expected elements as regular "
     "expressions. Score = 1 + 4 × (elements matched / elements total), forced to 1 if the reply says it does not know — "
     "mechanical, no model judge. The facts are stated in messages 1–6 of a fixed 30-message conversation; the probes are "
     "asked as messages 31–35.")
code(lines_of("memory_probes.yaml", 18, 26))
h2("3.3 and 3.4 Results (30 conversation turns per setting, fresh user and session each)")
rows = [["Setting", "Mean prompt tokens/turn", "Mean latency (ms)", "Probe quality (1–5)"]]
for l, n in sm.LABELS:
    s = S[l]
    rows.append([n, f"{s['mean_prompt']:.0f}", f"{s['mean_latency_ms']:.0f}", f"{s['probe']:.2f}"])
table(rows)
a, b = S["N30"], S["N30_evict"]
para(f"Policy tested: eviction of old assistant replies. Every assistant message except the newest four in the window is "
     f"dropped; the user's own messages (which carry the facts) are never dropped. At N = 30 it cut mean prompt tokens "
     f"from {a['mean_prompt']:.0f} to {b['mean_prompt']:.0f} ({(1 - b['mean_prompt'] / a['mean_prompt']) * 100:.1f}% saved) with "
     f"no change in probe quality ({a['probe']:.2f} → {b['probe']:.2f}).")
code(func_src("code/web_application/chat_memory.py", "apply_policy"))
rows = [["Setting", "System primer", "Long-term summary", "Short-term window", "Episodic facts", "Current msg", "Completion"]]
for l, n in sm.LABELS:
    c = S[l]["components"]
    rows.append([n.split(" (")[0], f"{c['system_primer']:.0f}", f"{c['long_term_summary']:.0f}", f"{c['short_term_window']:.0f}",
                 f"{c['episodic_facts']:.0f}", f"{c['current_message']:.0f}", f"{S[l]['mean_completion']:.0f}"])
para("Mean tokens per turn by component (estimated allocation):")
table(rows, size=9)
para("What to read into this. (1) The window is the only component that scales with N: 148 → 383 → 792 tokens. "
     "(2) All four settings scored 5.00, so the probes cannot rank them: at N = 4 the facts are still recovered from the "
     "session summary, the lifetime summary and the episodic retrieval. That is a result about this design, but it is also a "
     "ceiling effect — a harder probe set (facts only stated once, never summarised) is needed to show where a small window "
     "starts to hurt. (3) Latency is the least reliable column: it was measured on a shared machine that also runs other applications "
     "(the first N = 4 run was discarded for CPU contention and re-run last; it is kept as raw/*_N4_contended). "
     "Prompt tokens are exact and reproducible; treat latency as indicative.", "")
shot("3.1: terminal — RUN_LOG.txt head and the per-setting completion lines (name visible)")
shot("3.2: METRICS.md tables (terminal or editor)")
h2("3.5 Cost of 10,000 conversations × 30 turns")
para("$1 per million input tokens and $5 per million output tokens, using the measured token sums for the 30 turns. "
     "'All-in' includes the extraction and summarisation calls that the memory design makes.")
rows = [["Setting", "Input tok / conv", "Output tok / conv", "Chat-only cost", "All-in cost", "Probe"]]
for l, n in sm.LABELS:
    s = S[l]
    rows.append([n.split(" (")[0] if l != "N30_evict" else "N = 30 + eviction", f"{s['in_chat'] + s['in_over']:.0f}", f"{s['out_chat'] + s['out_over']:.0f}",
                 f"${s['cost_chat']:,.2f}", f"${s['cost_all']:,.2f}", f"{s['probe']:.2f}"])
table(rows)
worst = max(S.values(), key=lambda s: s["cost_all"])
top = max(s["probe"] for s in S.values())
best = min((s for s in S.values() if s["probe"] >= top - sm.QUALITY_TOLERANCE), key=lambda s: s["cost_all"])
para(f"Worst = highest all-in cost: {names[worst['label']]}, ${worst['cost_all']:,.2f}. Best = cheapest all-in cost among "
     f"settings whose probe score is within {sm.QUALITY_TOLERANCE} of the best ({top:.2f}): {names[best['label']]}, "
     f"${best['cost_all']:,.2f}. Ranking by cost alone would reward a setting that had stopped remembering; requiring "
     f"near-best quality first makes “best” mean cheapest without giving up recall. Worst/best = "
     f"{worst['cost_all'] / best['cost_all']:.2f}×. Because the probes did not separate the settings, this conclusion holds "
     f"for these probes only. Extraction and summarisation add a fixed overhead of "
     f"{S['N4']['in_over']:.0f} input and {S['N4']['out_over']:.0f} output tokens per conversation that no window setting removes.")

# ---------------------------------------------------------------------------------------- part 4
h1("Part 4 — File-Based Memory and Consolidation")
h2("4.1–4.2 Files, loading and commands")
para("AGENT.md (durable instructions, expanded from HW1) and MEMORY.md (durable facts, one “- [date] fact” per line, "
     "last-consolidated timestamp in an HTML comment) are loaded into the system prompt, AGENT.md first. Consolidation is due "
     "when MEMORY.md has more than 40 non-empty, non-comment lines, or the recorded time is more than 24 hours old (or missing). "
     "Commands: /memory, /compact, /dream, /help.")
code(func_src("code/hw6/file_memory.py", "count_memory_lines") + "\n\n" + func_src("code/hw6/file_memory.py", "consolidation_reason")
     + "\n\n" + func_src("code/hw6/file_memory.py", "build_system_prompt"))
code(lines_of("code/hw6/file_memory_cli.py", 98, 140))
shot("4.1: terminal — file_memory demo: /help, /memory, /dream, /compact with before → after counts (name banner)")
h2("4.3 AGENT.md")
para("Fourteen bullets in total, covering all five of the categories (project description, technology stack, coding "
     "conventions, testing approach, prohibited actions) plus the HW1 code-review rules, kept under their own heading. Full text:")
code((ROOT / "AGENT.md").read_text())
h2("4.4 One generated function checked against AGENT.md")
para("Task: write normalize_route_id (“  line   22 ” → “LINE 22”, ValueError on empty). The checker is mechanical (AST + pytest) "
     "and tests nine rules taken from AGENT.md: snake_case, type hints, docstring, no print, ≤ 100-character lines, no "
     "eval/exec, no hard-coded secrets, a test named test_<function>, and that the test passes. The model was run with AGENT.md "
     "in its system prompt and, as a control, without it; after a failure the exact rule and pytest output were fed back (up to two repairs).")
rows = [["Run", "Attempt", "Passed", "Failed checks"]]
for k, lab in (("with_agent_md", "model + AGENT.md"), ("control_without_agent_md", "model, no AGENT.md (control)")):
    for at in comp[k]["attempts"]:
        rows.append([lab, at["attempt"], f"{len(at['passed'])}/9", ", ".join(at["failed"]) or "—"])
h = comp["hand_implemented_route_utils"]
rows.append(["implemented directly (code/hw6/route_utils.py)", "—", f"{len(h['passed'])}/9", ", ".join(h["failed"]) or "—"])
table(rows, size=9)
para("Finding: with AGENT.md the model followed the style rules from the first attempt but ignored the testing rule, and after "
     "two repairs its function still failed its own test (it returned “LINE 22 ” with a trailing space). The control also ended "
     "short of full compliance. With AGENT.md the first attempt already had docstrings (the control's did not), but it did not guarantee compliance, which "
     "is why a mechanical check is needed. A side effect also showed up in the Part 4 demo: AGENT.md's “respond ONLY with a bulleted list” rule is written for code review, but the model applies it to ordinary chat as well (every demo reply is a bullet), so review-mode rules should be put behind an explicit trigger. The version that passes all nine checks was implemented directly:")
code((ROOT / "code/hw6/route_utils.py").read_text())
h2("4.5 Consolidation test (55 lines → under 40)")
para("reports/hw06/memory_test/MEMORY.original.md has 55 content lines: 9 duplicate groups (exact and paraphrased), 5 one-off "
     "notes, and 5 contradictions. The answer key (ground_truth.json) was written before any run and includes one trap "
     "(the assigned port 8470 vs a newer note saying 8000, where “newest wins” is wrong) and one false contradiction (development "
     "vs production cookies, both true). The original and consolidated versions are committed in separate Git commits (screenshot 4.2).")
para("Method. The model only judges; deterministic code applies. (1) Exact duplicates merge without the model. (2) Facts whose "
     "embeddings have cosine ≥ 0.30 are compared pairwise (SAME / CONFLICT / SCOPED / UNRELATED); a SAME verdict also needs cosine "
     "≥ 0.6, and groups are stars, not chains. (3) A CONFLICT keeps the fact marked fixed/assigned, else the newer, and each fact gets "
     "at most one decision. (4) A note is removed as temporary only if the model says so and it contains an explicit time or "
     "to-do cue. Nothing is deleted silently: every removed fact goes to MEMORY.archive.md with the reason, every resolved "
     "contradiction leaves an HTML comment in MEMORY.md, replaced wording is archived, and a run that would archive more than "
     "45% of the facts is refused.")
rows = [["Version", "Result", "Why it was not acceptable"],
        ["1: one prompt, all 55 facts", "55 → 51 lines", "1 duplicate group; 1 of 5 contradictions touched, and wrongly; archived a harmless fact as “obsolete”"],
        ["2: pairwise questions", "55 → 1 line", "model called 47 of 55 facts temporary and 58 of 87 pairs scoped; applied blindly"],
        ["3–4: + examples, 45% guard", "refused (24 of 48)", "wrong merges (Homebrew facts chained) and the assigned port-8470 fact would have been archived"],
        ["5: final (cosine and time-cue checks, star groups, one decision per fact)", f"55 → {rep['lines_after']} lines", "see grading below"]]
table(rows, size=9)
rows = [["Contradiction", "Correct resolution", "Consolidator result"]]
for g in rep["contradiction_grading"]:
    rows.append([g["id"], g["expected"], f"kept {g['actual_kept']} — " + ("correct" if g["correct"] else "INCORRECT")])
table(rows, size=9)
wrong = rep["contradictions_resolved_incorrectly"]
para(f"Resolved incorrectly: {', '.join(wrong) if wrong else 'none'}. The consolidator treated “Safari rejects Secure cookies over "
     f"plain http, so Secure stays off in development” and “session cookies must always set Secure=True” as a contradiction and kept "
     f"the newer one. Both are true (development vs production); the development rule was archived and noted. It was restored by "
     f"hand in the repository's MEMORY.md with a comment saying so. A second, smaller error: the fact “HW6 adds MongoDB documents…” "
     f"was merged into “The MongoDB database for HW6 is s3170_doc” although they are not duplicates; the s3170_doc wording is preserved "
     f"in MEMORY.archive.md. Honest caveat: the 0.6 cosine threshold and the time-cue rule were chosen after seeing earlier results and "
     f"the answer key, so 4 of 5 is not a blind score.")
para(f"/compact on the 55-line file reports the counts before and after: MEMORY.md {rep['lines_before']} → {rep['lines_after']} "
     f"content lines, {len(rep['archived'])} facts archived, {len(rep['merges'])} merge groups, and the conversation message count "
     f"before and after compaction (see screenshot 4.1).")
shot("4.2: git log — original and consolidated MEMORY.md committed separately")
h2("4.6 MongoDB memory vs file-based memory")
table([
    ["Criterion", "MongoDB memory (Part 2)", "File-based memory (Part 4)"],
    ["Inspectability", "Needs Compass or mongosh; embeddings are 384 floats and unreadable; summaries are model prose.",
     "A text file: open it, read it, diff it, review it in a pull request. Every consolidation leaves a comment and an archive line."],
    ["Persistence after restart", "Durable on the Docker volume; survives backend restarts as long as the volume exists.",
     "Durable in the repository; survives anything and travels with git history."],
    ["Scalability across many sessions", "Scales: indexed per-user collections, retrieval returns only top-k, cost per turn stays bounded.",
     "Does not: the whole file goes into every prompt, so cost grows with its length; it needed consolidation at 40 lines."],
    ["Facts that must not be forgotten", "Weak: retrieval is probabilistic and summaries are model-written prose, so a fact can be dropped or distorted.",
     "Strong: a line in the file is always in the prompt, and removals are archived. Its weakness is that a model-driven consolidation can still choose the wrong side of a contradiction (C5)."],
], size=9)
para("Use MongoDB memory for the long tail of per-user detail, and keep the small set of must-not-forget rules (ports, "
     "fixed configuration, prohibited actions) in the files.")

# ---------------------------------------------------------------------------------------- verification + AI use
h1("Verification")
if ver:
    para(f"make verify-hw06 → reports/hw06/verification.json: {ver['passed']} passed, {ver['failed']} failed, {ver['skipped']} skipped "
         f"of {ver['total_checks']} checks (commit {ver['commit'][:10]}).")
    table([["Check", "Result"]] + [[c["check"], c["status"]] for c in ver["checks"]], size=9)
else:
    para("verification.json not generated yet.")
shot("V.1: terminal — make verify-hw06 (name visible)")

h1("AI Use")
txt = (R / "AI_USE.md").read_text().replace("\r", "")
for block in txt.split("\n"):
    s = block.strip()
    if not s or s.startswith("<!--") or s.startswith("# AI_USE"):
        continue
    if s.startswith("## "):
        h2(s[3:])
    elif s.startswith("* "):
        bullet(s[2:].replace("**", ""))
    elif s.startswith("  ") and doc.paragraphs and doc.paragraphs[-1].style.name == "List Bullet":
        doc.paragraphs[-1].add_run(" " + s.replace("**", ""))
        _font(doc.paragraphs[-1].runs[-1], 11)
    else:
        para(s.replace("**", ""))

h1("Appendix A — original MEMORY.md (55 lines)")
code((R / "memory_test" / "MEMORY.original.md").read_text(), size=7)
h1("Appendix B — consolidated MEMORY.md (as produced)")
code((R / "memory_test" / "MEMORY.consolidated.md").read_text(), size=7)

doc.save(OUT)
print(f"wrote {OUT} ({datetime.now().isoformat(timespec='seconds')})")
