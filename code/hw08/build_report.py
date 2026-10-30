#!/usr/bin/env python3
"""
HW8 - build reports/hw08/Priyadarshini_HW8.docx: the report skeleton with every table, code block and
log excerpt generated from the real source and the saved evidence in reports/hw08/raw/, plus red
bracketed placeholders for the screenshots only the student can take and for AI_USE.

    .venv/bin/python code/hw08/build_report.py
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "reports" / "hw08" / "raw"
OUT = REPO / "reports" / "hw08" / "Priyadarshini_HW8.docx"
RED = RGBColor(0xB4, 0x23, 0x18)
sys.path.insert(0, str(REPO / "code" / "hw07"))
import _extract as E  # noqa: E402  (pulls functions out of the real source files)

# --- document helpers (same look as the HW6/HW7 reports) -----------------------------------
doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
    setattr(sec, side, Inches(0.8333))
doc.styles["Normal"].font.size = Pt(11)


def para(text="", size=11, bold=False, color=None, align=None, before=None, after=None, italic=False):
    p = doc.add_paragraph()
    if text:
        r = p.add_run(text)
        r.font.size, r.bold, r.italic = Pt(size), bold, italic
        if color is not None:
            r.font.color.rgb = color
    if align:
        p.alignment = align
    if before is not None:
        p.paragraph_format.space_before = Pt(before)
    if after is not None:
        p.paragraph_format.space_after = Pt(after)
    return p


def h1(t):
    return para(t, 14, True, before=12, after=4)


def h2(t):
    return para(t, 12, True, before=8, after=3)


def body(t, **kw):
    return para(t, 11, **kw)


def bullet(t):
    p = body("•  " + t, after=2)
    p.paragraph_format.left_indent = Inches(0.2)
    return p


def shot(label):
    return para(f"[ Screenshot {label} ]", 11, True, RED, WD_ALIGN_PARAGRAPH.CENTER, before=4, after=6)


def fill_in(label):
    return para(f"[ {label} ]", 11, True, RED, WD_ALIGN_PARAGRAPH.CENTER, before=4, after=6)


def code(text, size=8):
    p = doc.add_paragraph()
    r = p.add_run(text.rstrip("\n"))
    r.font.name, r.font.size, r.bold = "Courier New", Pt(size), False
    r._element.rPr.rFonts.set(qn("w:eastAsia"), "Courier New")
    p.paragraph_format.space_after = Pt(4)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), "F2F4F7")
    p._p.get_or_add_pPr().append(shd)


def table(header, rows, size=10, widths=None):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    for i, h in enumerate(header):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(str(h))
        r.bold, r.font.size = True, Pt(size)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            r = cells[i].paragraphs[0].add_run(str(v))
            r.bold, r.font.size = False, Pt(size)
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths):
                row.cells[i].width = Inches(w)
    para("", after=2)


def clip(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


# --- evidence helpers --------------------------------------------------------------------------
def section_of(text: str, start: str, end: str | None) -> list[str]:
    lines = text.splitlines()
    i = next(k for k, ln in enumerate(lines) if start in ln)
    j = next((k for k in range(i + 1, len(lines)) if end and end in lines[k]), len(lines))
    return lines[i:j]


def compact_group(ln: str) -> str:
    """kafka-consumer-groups row -> 'group topic partition committed log-end lag'."""
    f = ln.split()
    if f[:2] == ["GROUP", "TOPIC"]:
        return "  GROUP (from kafka-consumer-groups --describe)   TOPIC       PARTITION  COMMITTED  LOG-END  LAG"
    if len(f) >= 6 and f[2].isdigit() or (len(f) >= 6 and f[2] in "01"):
        return f"  {f[0]:<31} {f[1]:<11} partition={f[2]} committed={f[3]:<3} log-end={f[4]:<3} lag={f[5]}"
    return ln


def trim(lines: list[str], width: int = 165) -> str:
    return "\n".join(compact_group(ln)[:width].rstrip() for ln in lines if ln.strip())


fail_text = (RAW / "failure_tests_run_raw.txt").read_text()
fail = json.loads((RAW / "failure_tests_summary.json").read_text())["results"]
demo = (RAW / "part1_demo_run.txt").read_text()
journey = (RAW / "pipeline_journey.txt").read_text()
ver = json.loads((RAW.parent / "verification.json").read_text()) if (RAW.parent / "verification.json").exists() else None
short = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()

dup_sec = section_of(fail_text, "PART 3.I ", "PART 3.II")
death_sec = section_of(fail_text, "PART 3.II ", "PART 3.III")
poison_sec = section_of(fail_text, "PART 3.III", "PART 3.IV")
order_sec = section_of(fail_text, "PART 3.IV", "SUMMARY")

# =========================================================================================
para("DATA 260 — Homework 8: Kafka Request/Response, a Three-Agent Pipeline and Failure Behavior", 14, True)
body("Pragnaya Priyadarshini (Lucky) · SJSU MS Applied Data Intelligence")
para("GitHub repository: https://github.com/pragnayap/data260-3170", 11, True)
para("Collaborators: Sbnikitha and supriyaselvanganesan have access.", 11, True)

h1("Section 0 — Configuration")
table(["Value", "Definition", "Mine"], [
    ["SID4", "last 4 of SJSU student ID", "3170"], ["PORT_BASE", "8000 + (SID4 mod 900)", "8470"],
    ["PREFIX", "\"s\" + SID4", "s3170"], ["SEED", "SID4", "3170"], ["VERIFY_SEED", "260000 + SID4", "263170"],
    ["DOMAIN_ID", "SID4 mod 8", "2 — Municipal Transit Incidents (entity: Transit Incident)"],
    ["Hardware", "", "Intel Core i9-9880H (x86_64), 16 GB RAM, macOS 15, Docker Desktop"],
    ["Local model", "", "qwen3:8b via Ollama, CPU-only (Part 2 agents); Kafka: apache/kafka:3.8.0 (KRaft) + confluent-kafka 2.16.1"],
    ["Tagged commit hash", "tag hw8", "[ fill in after tagging: git rev-parse --short hw8 ]"],
])

h1("Overview — what I built")
table(["Part", "What I built", "Result"], [
    ["1", "Entity worker + FastAPI wrapper that talk only through two Kafka topics (CREATE_INCIDENT / GET_INCIDENT); "
          "homework_demo.py; Docker Compose with Kafka, worker and API.",
     "create → get round-trips; correlation_id preserved in every reply, including errors"],
    ["2", "Planner, Writer and Reviewer as separate processes over four topics; send_question.py.",
     "one question reached s3170_final, status approved, correlation_id unchanged"],
    ["3", "Duplicate replay, consumer killed mid-work, poison message, ordering — each run before and after its fix.",
     "4 of 4 scenarios reproduce the failure and show the fix working (2 consecutive full passes)"],
    ["—", "Self-check (make verify-hw08).", f"{ver['passed']}/{ver['total_checks']} checks pass" if ver else "run make verify-hw08"],
], size=9, widths=[0.4, 4.3, 2.1])

# =========================================================================================
h1("Part 1 — Backend Service Request/Response over Kafka")
h2("What I did")
bullet("Primary entity: Transit Incident (routeId, location, submitterEmail, description > 25 characters, category, agreeTerms). "
       "So the operations are CREATE_INCIDENT and GET_INCIDENT, and the id field is incident_id.")
bullet("Exactly two topics: s3170_entity_requests (client/API → worker) and s3170_entity_responses (worker → whoever sent the request).")
bullet("The client creates the correlation_id once; the worker copies it unchanged into every response, including errors "
       "(unknown operation, unknown id, validation failures, even a malformed request).")
bullet("The worker keeps entities in a plain dict, generates incident_id with uuid4, validates every field, and commits its Kafka "
       "offset only after the reply is delivered.")
bullet("FastAPI wrapper (port 8470): POST /incidents and GET /incidents/{id} become Kafka requests; the HTTP reply is the worker's "
       "response for the same correlation_id (also returned in an X-Correlation-Id header).")
bullet("Docker Compose runs Kafka (single-node KRaft), the worker and the API; homework_demo.py runs the 10-step flow and prints the "
       "worker container's own log lines for each request.")
h2("Topics and message schemas")
table(["Topic", "Direction", "Partitions"], [["s3170_entity_requests", "client / API → worker", "1"],
                                              ["s3170_entity_responses", "worker → client / API (named by reply_to)", "1"]], size=9)
code('''request : {"correlation_id": "unique-id", "reply_to": "s3170_entity_responses",
           "operation": "CREATE_INCIDENT" | "GET_INCIDENT", "data": { ... }}
success : {"correlation_id": "<same>", "success": true, "incident_id": "<uuid>", "message": "Incident created"}
          {"correlation_id": "<same>", "success": true, "incident": {"incident_id": "...", "routeId": "...", ...}}
failure : {"correlation_id": "<same>", "success": false, "error": "Incident not found" | "Unknown operation" | ...}''')
code('''correlation_id flow:  client creates id ─► s3170_entity_requests ─► worker (reads, validates, processes)
                      ◄─ s3170_entity_responses ◄─ worker replies to the topic in reply_to, SAME id''')
h2("Code")
code(E.get("code/hw08/worker.py", "validate", "handle"))
code(E.between("code/hw08/worker.py", "            if not correlation_id", "    finally:"), size=7)
code(E.get("code/hw08/api.py", "call_worker"), size=7)
code(E.get("code/hw08/homework_demo.py", "roundtrip"), size=7)
h2("Evidence")
code((RAW / "part1_docker_evidence.txt").read_text())
shot("1.1: docker ps showing the Kafka, worker and FastAPI containers, with the worker's \"Consumer is ready and listening...\" line "
     "and the API's \"FastAPI server started at http://127.0.0.1:8470\" line (name visible)")
create_part = section_of(demo, "STEPS 1-7", "STEPS 8-10")
code(trim([ln for ln in create_part if ln.strip() and "====" not in ln], 200))
shot("1.2: homework_demo.py — CREATE_INCIDENT request, response, extracted incident_id, success status and correlation_id (name visible)")
get_part = section_of(demo, "STEPS 8-10", "ERROR PATHS")
code(trim([ln for ln in get_part if ln.strip() and "====" not in ln], 200))
shot("1.3: Kafka message-flow logs for GET_INCIDENT — sent to s3170_entity_requests, received and processed by the worker, "
     "reply on s3170_entity_responses, response received by the client (name visible)")
seq = [ln for ln in demo.splitlines() if any(k in ln for k in ("SEND", "RECV", "PROCESS", "REPLY", "STEP", "preserved", "correlation_id sent", "correlation_id received"))]
code(trim(seq, 190), size=7)
shot("1.4: full sequence CREATE_INCIDENT → GET_INCIDENT (send, receive, process, reply, final client response, in order)")
api_run = (RAW / "part1_api_run.txt").read_text()
code("\n".join(ln[:190] for ln in api_run.splitlines()[:22]), size=7)
shot("1.5: the FastAPI wrapper — curl POST /incidents (201) and GET /incidents/{id} (200) with the X-Correlation-Id header, and the "
     "API container's own Kafka send/receive log lines (name visible)")

# =========================================================================================
h1("Part 2 — Three-Agent Kafka Pipeline")
h2("What I did")
bullet("Planner (reads s3170_inbox → writes s3170_tasks), Writer (tasks → s3170_drafts) and Reviewer (drafts → s3170_final) run as "
       "three separate processes. No agent calls another; every hand-off is a Kafka message, keyed by correlation_id.")
bullet("The Planner and Writer call the local qwen3:8b (capped at a few hundred tokens, with a client timeout); the Reviewer is "
       "rule-based (length and placeholder checks), so the final message is reproducible.")
bullet("send_question.py puts a question on s3170_inbox and waits on s3170_final for the message with the same correlation_id.")
bullet("The four topics were created with the Kafka CLI (s3170_tasks has 2 partitions, which Part 3 uses for ordering).")
h2("Topics")
code((RAW / "part2_topics.txt").read_text())
shot("2.1: the four pipeline topics (plus the others) created/listed with the Kafka CLI, s3170_tasks showing PartitionCount 2 (name visible)")
h2("Code")
code(E.get("code/hw08/planner.py", "make_plan"), size=7)
code(E.get("code/hw08/reviewer.py", "review"), size=7)
code(E.between("code/hw08/writer.py", "def work(task", "def record_side_effect", ), size=7)
code(E.between("code/hw08/planner.py", "            plan = make_plan(question)", "            consumer.commit(message=msg", include_end=True), size=7)
shot("2.2: the four terminals — planner.py, writer.py, reviewer.py running, and send_question.py sending the question (name visible)")
h2("One complete message journey")
code("\n".join(ln[:215] for ln in journey.splitlines()), size=7)
shot("2.3: the log lines of one message journey from s3170_inbox to s3170_final, one stage per line (name visible)")
shot("2.4: the final JSON message (status and answer) read from s3170_final")
h2("How Kafka helped the agents coordinate")
body("Kafka decoupled the three agents in time, in failure and in speed. The Planner finished and moved on while the slower Writer was "
     "still generating; the broker held the plan until the Writer was ready, so no agent had to wait on, or even know about, another. "
     "Each topic is a durable buffer with its own offsets, so an agent that is restarted resumes where it stopped instead of "
     "losing work (Part 3). The correlation_id carried in every message tied the whole journey together across five processes, "
     "so one grep reconstructs it. And because the hand-offs are messages, any stage can be scaled out (the tasks topic has two "
     "partitions) or replaced without touching the others.")

# =========================================================================================
h1("Part 3 — Failure Behavior")
h2("What I did")
bullet("Every scenario runs against the real broker with real Writer processes (the same writer.py as Part 2, with one safeguard "
       "switched off for \"before\" and on for \"after\"); failures are injected with SIGKILL, replays and bad payloads.")
bullet("The failure tests use stub drafts (instant) because they test Kafka behavior, not model quality. Two consecutive full runs gave "
       "identical outcomes.")
h2("Failure table")
d, a = fail["duplicate"]["before"], fail["duplicate"]["after"]
db, da = fail["death"]["before"], fail["death"]["after"]
pb, pa = fail["poison"]["before"], fail["poison"]["after"]
ob, oa = fail["ordering"]["before"], fail["ordering"]["after"]
table(["Failure scenario", "Before fix", "After fix"], [
    ["Duplicate delivery", f"same correlation_id sent {d['messages_sent']}× → {d['drafts_produced']} drafts, {d['side_effects']} side effects",
     f"sent {a['messages_sent']}× (incl. a replay after a restart) → {a['drafts_produced']} draft, {a['side_effects']} side effect; "
     f"{a['duplicates_ignored']} replays logged DUPLICATE and ignored"],
    ["Consumer killed mid-work", f"auto-commit: offset advanced before the work finished; after SIGKILL + restart the message is never "
                                 f"redelivered ({db['drafts_produced']} drafts) — lost",
     f"commit after success: lag 1 after the kill; restart redelivers it, completes it, commits, lag 0 ({da['drafts_produced']} draft)"],
    ["Poison message", f"unbounded retries: {pb['retries_logged']}+ attempts on one offset; the good message behind it is BLOCKED",
     f"3 attempts then s3170_dead_letter ({pa['dead_letter_records']} bad messages); the good message is processed"],
    ["Two partitions / two consumers", f"no key: {ob['entities_out_of_order']} of {ob['entities']} incidents processed out of order; "
                                       f"{ob['entities'] - ob['entities_in_one_partition']} of {ob['entities']} split across both partitions",
     f"key = incident: {oa['entities_out_of_order']} of {oa['entities']} out of order; {oa['entities_in_one_partition']} of "
     f"{oa['entities']} stay in one partition"],
], size=9, widths=[1.5, 2.7, 2.7])

h2("3.I Duplicate delivery")
body("A task is replayed with the same correlation_id. The fix is idempotency: the Writer records each completed correlation_id in an "
     "append-only state log (it survives a restart) and ignores a replay.")
code(E.between("code/hw08/writer.py", "            if IDEMPOTENT and correlation_id in processed", "            attempts, delivered", ), size=7)
code(E.get("code/hw08/writer.py", "mark_processed"), size=7)
keep = [ln for ln in dup_sec if any(k in ln for k in ("[TEST", "RECV", "DUPLICATE", "SEND", "COMMIT", "---"))]
code(trim(keep[:34], 175), size=7)
shot("3.1: duplicate delivery — before (2 drafts, 2 side effects) and after (1 draft, replay logged as DUPLICATE) (name visible)")

h2("3.II Consumer death")
body("The Writer is killed with SIGKILL while it is processing. Before: auto-commit advances the group's offset on a timer, so the in-flight "
     "message is lost. After: the offset is committed only once the draft is delivered, so the broker redelivers it to the restarted Writer.")
code(E.between("code/hw08/writer.py", "            if delivered:", "    finally:"), size=7)
code(trim([ln for ln in death_sec if ln.strip() and "====" not in ln and "WORKING" not in ln][:46], 175), size=7)
shot("3.2: consumer death — the Writer killed mid-work, the consumer-group offsets (committed vs log-end, lag) and the restart; before vs after (name visible)")

h2("3.III Poison message")
body("A task with no plan always fails. Before: the Writer retries it forever and the partition behind it is blocked. After: at most 3 attempts, then "
     "the message is published to s3170_dead_letter with its error and the offset is committed, so later messages flow. An unparseable message is handled the same way.")
code(E.between("code/hw08/writer.py", "                except Exception as exc:", "            if delivered:"), size=7)
poison_keep = [ln for ln in poison_sec if any(k in ln for k in ("[TEST", "RETRY", "GIVE UP", "DEAD-LETTER", "SEND", "COMMIT", "RECV", "---"))]
before_retry = [ln for ln in poison_keep if "attempt" in ln and "(no limit)" in ln]
poison_show = []
for ln in poison_keep:
    if ln in before_retry[3:-1]:
        if ln == before_retry[3]:
            poison_show.append(f"      ... (attempts 4-{len(before_retry) - 1} omitted here; the full log is in RUN_LOG.txt) ...")
        continue
    poison_show.append(ln)
code(trim(poison_show[:34], 175), size=7)
shot("3.3: poison message — before (endless retries, later message blocked) and after (3 attempts, s3170_dead_letter, later message processed) (name visible)")

h2("3.IV Ordering")
body("20 related messages are generated from VERIFY_SEED = 263170 (5 incidents, random per-message work time) and sent through s3170_tasks "
     "(2 partitions) with two Writers in one consumer group. Run 1 has no key (messages alternate across the partitions); run 2 uses the incident id as the "
     "message key, so Kafka hashes every message for one incident to the same partition.")
code(E.between("code/hw08/failure_tests.py", "        if keyed:", "        sent_partition[m[\"entity\"]].add(partition)"), size=7)
for label, name in (("Run 1 — no key", "ordering_unkeyed.csv"), ("Run 2 — key = incident id", "ordering_keyed.csv")):
    rows = list(csv.DictReader((RAW / name).open()))
    body(f"{label}: order in which the 20 messages were processed", bold=True, after=1)
    table(["#", "writer", "partition", "incident", "seq"], [[r["order"], r["writer"], r["partition"], r["entity"], r["seq"]] for r in rows], size=8)
summary_lines = [ln for ln in order_sec if "IN ORDER" in ln or "OUT OF ORDER" in ln or "RESULT" in ln]
code("\n".join(ln[:200] for ln in summary_lines), size=7)
shot("3.4: both ordering runs — processing order and per-incident verdict (name visible)")

h2("V. Comparison with the HW2 in-process graph")
body("In HW2 the graph was function calls inside one process, each step waiting on the previous one. With Kafka:")
body("Two benefits gained.", bold=True, after=1)
bullet("Independent scaling: the Writer (slow, model-bound) can be run as 2 instances sharing the s3170_tasks partitions while the Planner and "
       "Reviewer stay single — impossible when every step is a call in one process.")
bullet("Decoupled failure: when the Writer was killed mid-work, the Planner and Reviewer were unaffected and the broker held the message until "
       "the Writer came back; in the HW2 graph, one crashed step would have taken the whole run down.")
body("Two new responsibilities I now own.", bold=True, after=1)
bullet("Duplicate delivery: Kafka is at-least-once, so the Writer must make processing idempotent (a replayed correlation_id must not repeat the "
       "side effect); in-process calls never delivered a step twice.")
bullet("Ordering and offsets: order exists only within a partition, so related messages need a key; and the offset must be committed after the work, "
       "not before, or a crash silently loses the message. (The same applies to poison messages: bounded retries and a dead-letter topic are mine to build.)")
h2("A bug in my own Writer, found while testing")
body("While running the ordering test one message was processed twice. The cause was my Writer: it kept its idempotency state in one file that "
     "every instance rewrote through the same temporary filename, so two Writers raced and one failed with ENOENT — and my retry loop then re-ran "
     "the whole message, delivering the draft a second time. Fixes: an append-only state log that instances can safely share, and retries that "
     "cover only the work and the delivery (bookkeeping runs afterwards and is never retried). The failing and fixed runs are in raw/dev_history/.")

# =========================================================================================
h1("Self-check and repository")
body("make verify-hw08 checks, against the running stack, that CREATE_INCIDENT → GET_INCIDENT round-trips through Kafka with the correlation_id "
     "preserved, that errors and invalid input are rejected cleanly, that the API wrapper works, that the three containers and the required log lines "
     "are present, that a stub-mode pipeline reaches s3170_final, and that all four failure scenarios behave as reported "
     + (f"({ver['passed']} passed, {ver['failed']} failed, {ver['skipped']} skipped of {ver['total_checks']}). " if ver else ". ")
     + "Deliverables in reports/hw08/: RUN_LOG.txt, raw/, METRICS.md, AI_USE.md, verification.json and this report.")
shot("4.1 (optional): terminal — make verify-hw08 ending in the passed/failed summary (name visible)")

h1("AI use statement")
fill_in("Paste your AI_USE.md answers here: (1) what you used an AI assistant for and what you did yourself; (2) one AI-produced output that was "
        "wrong/unsuitable, or one thing you independently verified; (3) how you detected the problem or verified the result; (4) what you changed "
        "and why it works now.")
h1("References")
bullet("Apache Kafka documentation: https://kafka.apache.org/documentation/ (consumer groups, offsets, partitioning by key).")
bullet("confluent-kafka-python: https://docs.confluent.io/kafka-clients/python/current/overview.html")

doc.save(OUT)
print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes, {len(doc.paragraphs)} paragraphs, {len(doc.tables)} tables, "
      f"{sum('Screenshot' in p.text for p in doc.paragraphs)} screenshot placeholders; HEAD {short})")
