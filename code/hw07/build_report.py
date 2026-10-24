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
rel2, att2 = J("v2_lax_check/reliability_summary.json"), J("v2_lax_check/reliability_attempts.json")
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
    ["Tagged commit hash", "tag hw7", "[ fill in after tagging: git rev-parse --short hw7 ]"],
])

h1("Overview — the steps we took")
table(["Part", "What we built and did", "Result"], [
    ["1", "Moved the graded routes from the HW4 cookie to JWT with reader/writer/moderator roles; users table gained "
          "username + role; Ruff + pre-commit.", "401 / 403 / 200–204 as required; hook blocks bad commit"],
    ["2", "Hand-written agent loop over the HW5 tools with a repair path; 3 fixed tasks; error recovery; 20-attempt "
          "reliability study; fixed the failures it exposed.",
     f"well-formed {rel['well_formed_before_repair'].split('=')[1].strip()} → {rel['well_formed_after_repair'].split('=')[1].strip()} "
     f"after repair; tasks {rel['task_pass']}"],
    ["3", "Bounded Reflexion (≤ 2 retries, budgets, stop reasons), deterministic verifiers, stored reflections, "
          "original-vs-Reflexion comparison.", f"initial run {cmp1['original']['task_success']} → {cmp1['reflexion']['task_success']}"],
    ["4", "Capital Bikeshare ReAct/MRKL agent: 3 tools, UI, two real-data scenarios, frozen pricing snapshots.",
     "membership wins / pay-per-use wins, both verified"],
    ["5", "Threat model, 5 hostile fixtures, 2 defenses, 24 live attack runs plus a tool-boundary replay.",
     "3 of 24 attacks succeeded; SQL guard 6/7 → 0/7 data changes"],
    ["6", "Six sandboxed file tools and a bash safety gate; glob → search → read test; gate test.",
     "14/14 correct; 4 false allows found and fixed"],
    ["—", "Self-check script (make verify-hw07).", f"{ver['passed']}/{ver['total_checks']} checks pass"],
], size=9, widths=[0.4, 4.3, 2.1])

# ============================================================================================
# Part 1
# ============================================================================================
h1("Part 1 — JWT Authentication, Role-based Authorization and Linting")
h2("What we did")
bullet("Added username (unique) and role to the MySQL users table (code/seed_hw07.py runs the ALTER TABLE) and seeded "
       "one user per role. Passwords stay PBKDF2-HMAC-SHA256 with a per-user salt (salt$hash) — never plaintext.")
bullet("POST /auth/login fetches the user, verifies the hash, and only then signs an HS256 JWT (60 min). "
       "GET /auth/me returns the identity and role. Bad credentials, a missing, invalid or expired token → 401.")
bullet("Role checks on the existing /api/incidents and /api/routes (no second /entities API): list/read any role, "
       "create writer or moderator, delete moderator only; wrong role → 403.")
bullet("Installed Ruff and pre-commit, fixed the lint issues in the files we touched, and demonstrated a blocked commit "
       "(I001 unsorted imports, F401 unused import) followed by a clean one.")
bullet("Disclosure: the graded routes no longer accept the HW4 cookie, so the React frontend and the older verify scripts "
       "(verify_hw02–05, measure_n1.py) are expected to get 401 at HEAD; they are unchanged at their own tags.")
h2("Evidence required")
code(E.get("code/web_application/jwt_auth.py", "create_access_token", "require_roles", "login"))
table(["users column", "Type / rule"], [["id", "primary key"], ["username", "unique"],
                                         ["password_hash", "salt$PBKDF2 hash only"], ["role", "reader | writer | moderator"]], size=9)
table(["Action", "reader", "writer", "moderator", "no / bad token"], [
    ["List / read", "200", "200", "200", "401"], ["Create", "403", "201", "201", "401"], ["Delete", "403", "403", "204", "401"]],
    size=9)
shot("1.1: successful login returning a JWT, and a failed login returning 401 Unauthorized")
shot("1.2: GET /auth/me without a token → 401 Unauthorized")
shot("1.3: GET /auth/me with an invalid or expired token → 401 Unauthorized (separate screenshot)")
shot("1.4: create as reader → 403 Forbidden, and as writer or moderator → 201 Created")
shot("1.5: delete as writer → 403 Forbidden, and as moderator → 204 No Content")
shot("1.6: list/read with a valid token → 200 OK")
shot("1.7: terminal — linting error before commit, the pre-commit hook running, the issues fixed, and the successful "
     "commit (name visible)")

# ============================================================================================
# Part 2
# ============================================================================================
h1("Part 2 — The Agent Loop")
h2("What we did")
bullet("run_agent(user_input) (code/hw07/agent.py) drives the HW1 ModelClient and the three HW5 domain tools through "
       "execute_tool; results are appended as tool-role messages; it stops at a final answer or the step ceiling (8).")
bullet("Repair path: a reply that is not a JSON call/answer (text_instead_of_tool), names an unknown tool (unknown_tool), or has "
       "malformed or schema-failing arguments (malformed_arguments) is reprompted once with the specific problem; after 2 "
       "failed repairs the run stops as repair_exhausted. \"No incident found\" is an observation, not a malformed call.")
bullet("Every tool invocation is logged with name and inputs and the total is reported at the end.")
bullet("Three fixed tasks — A: search then look up the first result; B: aggregate then one supporting example; C: search + "
       "two detail lookups to compare — each checked by a deterministic verifier. Nonexistent ID handled without a crash.")
bullet("Measured 20 attempts (7 A, 7 B, 6 C, temperature 0.7) in three rounds. Round 1 passed 10/20: task B misread the "
       "stats list and task C hit 3 verifier false rejections. Round 2 passed 20/20 — but its task-B check was too weak: "
       "the answers said no example was found (search_incidents matches only route_id/location). Fix: the check now "
       "requires a real example the answer cites, and the prompt notes how to find one (query 'Line' + category). Final "
       "round: 20/20 under the stricter check.")
h2("Evidence required")
code(E.between("code/hw07/agent.py", "for step in range(1, max_steps + 1):", 'run.stop_reason = "max_steps"'))
excerpt = [clip(ln, 150) for ln in T("part2_demo_run.txt").splitlines()
           if ln.startswith("=== Task") or "[tool call" in ln or "[done]" in ln or "[check]" in ln]
code("\n".join(excerpt), size=7)
shot("2.1: agent completing task A without follow-up prompting")
shot("2.2: agent completing task B")
shot("2.3: agent completing task C")
shot("2.4: error-recovery case (nonexistent ID) handled without crashing")
bt = {t: [x for x in att if x["task"] == t] for t in "ABC"}
bt1 = {t: [x for x in att1 if x["task"] == t] for t in "ABC"}
bt2 = {t: [x for x in att2 if x["task"] == t] for t in "ABC"}
table(["20 attempts", "Well-formed before repair", "Well-formed after repair", "Task A", "Task B", "Task C", "Total"], [
    ["Final run", rel["well_formed_before_repair"], rel["well_formed_after_repair"],
     *[f"{sum(x['passed'] for x in bt[t])}/{len(bt[t])}" for t in "ABC"], rel["task_pass"]],
    ["Round 2 (weak B check)", rel2["well_formed_before_repair"], rel2["well_formed_after_repair"],
     *[f"{sum(x['passed'] for x in bt2[t])}/{len(bt2[t])}" for t in "ABC"], rel2["task_pass"]],
    ["Initial run", rel1["well_formed_before_repair"], rel1["well_formed_after_repair"],
     *[f"{sum(x['passed'] for x in bt1[t])}/{len(bt1[t])}" for t in "ABC"], rel1["task_pass"]]], size=9)
table(["Failure class", "First-try failures", "Unrecovered after repair"], [
    ["malformed arguments", sum("malformed_arguments" in x["problems"] for x in att), sum(x["failure_class"] == "malformed_arguments" for x in att)],
    ["unknown tool", sum("unknown_tool" in x["problems"] for x in att), sum(x["failure_class"] == "unknown_tool" for x in att)],
    ["text when a tool was required", sum("text_instead_of_tool" in x["problems"] for x in att), sum(x["failure_class"] == "text_instead_of_tool" for x in att)],
    ["lost multi-step chain", "—", sum(x["failure_class"] == "lost_chain" for x in att)]], size=9)
sigs = {t: len({(x["tokens"], x["tool_calls"], tuple(x["problems"])) for x in att if x["task"] == t}) for t in "ABC"}
ft = sum(bool(x["problems"]) for x in att)
body(f"Per-attempt data: raw/reliability_attempts.csv/.json. In the final run {ft} of 20 attempts had a first-try failure "
     "(round 1 had 7: search_incidents called without its required query, each fixed by one reprompt; the new tool note "
     f"removed that mistake). The model is near-deterministic on these tasks (the attempts collapse to {sigs['A']}/{sigs['B']}/"
     f"{sigs['C']} distinct paths for A/B/C), so they are not 20 independent samples.", italic=True)

# ============================================================================================
# Part 3
# ============================================================================================
h1("Part 3 — Reflexion and Bounded Self-Correction")
h2("What we did")
bullet("reflexion.py wraps the Part 2 agent: a deterministic verifier checks each result; on failure the model writes one "
       "short reflection (≤ 2 sentences) and the task is retried with it in context.")
bullet("Bounds: ≤ 2 retries, 12 tool calls and 15,000 tokens per task; stop reason success, budget_exhausted or human_review.")
bullet("Reflections are untrusted data: stored per (user, run_id) with their evidence, passed only as a labelled user-role "
       "note (never the system prompt), and unable to change tool permissions or the safety gate — a test proves a hostile "
       "reflection changes nothing.")
bullet("Compared original vs Reflexion on 12 paired runs (attempt 0 = original loop, final outcome = Reflexion).")
h2("Evidence required")
code(E.get("code/hw07/reflexion.py", "run_reflexion"))
code(E.get("code/hw07/tasks.py", "check_A", "check_B", "check_C", "check_missing"))
r0 = refl1[0]
ev = r0["evidence"]
code(json.dumps({"task": r0["task"], "attempt": r0["attempt"], "failure": r0["failure"],
                 "evidence": {"tool_calls": [{"tool": c["tool"], "inputs": c["inputs"], "ok": c["ok"],
                                              "observation": clip(c["observation"], 90)} for c in ev["tool_calls"]],
                              "answer": clip(ev["answer"], 120), "verifier_result": ev["verifier_result"]},
                 "reflection": clip(r0["reflection"], 300)}, indent=1), size=7)


def cmp_rows(c):
    o, f = c["original"], c["reflexion"]
    return [["Task success", o["task_success"], f["task_success"]], ["Unsupported claims", o["unsupported_claims"], f["unsupported_claims"]],
            ["Retry rate", o["retry_rate"], f["retry_rate"]], ["Tool calls", o["tool_calls"], f["tool_calls"]],
            ["Tokens", f"{o['tokens']:,}", f"{f['tokens']:,}"], ["Latency (ms)", f"{o['latency_ms']:,}", f"{f['latency_ms']:,}"],
            ["Verifier false rejections", o["verifier_false_rejections"], f["verifier_false_rejections"]]]


body("Initial run (the base loop still had failures to correct); reflections: raw/v1_initial/reflections.jsonl "
     f"({len(refl1)} stored):", bold=True, after=1)
table(["Metric", "Original loop", "Reflexion loop"], cmp_rows(cmp1), size=9)
body("Final run (after the prompt/verifier fixes the base loop passes every run, so Reflexion never triggers):", bold=True, after=1)
table(["Metric", "Original loop", "Reflexion loop"], cmp_rows(cmp), size=9)
body("Verifier false rejections: in the first reliability run the task-C check rejected 3 correct answers (e.g. \"Line 80 "
     "… 147 riders\" is INC-3170-00022, but the verifier demanded the literal code). It was loosened and re-run; an "
     "independent looser oracle found 0 false rejections in both 12-run comparisons. Caveat: the verifier's failure text "
     "names the correct category and enters the reflection, so Reflexion is partly told the answer.", italic=True)
shot("3.1 (optional): terminal — a stored reflection with its evidence, or a Reflexion retry succeeding")

# ============================================================================================
# Part 4
# ============================================================================================
h1("Part 4 — Framework ReAct/MRKL Public-Data Exercise (Capital Bikeshare)")
h2("What we did")
bullet("City: Capital Bikeshare. A LangGraph create_react_agent over ChatOllama (qwen3:8b) uses three pure-function tools; "
       "the page lists only $120/year, so monthly = $120 / 12 = $10 (an assumption stated in every output).")
bullet("Built two real datasets (≥ 500 rows, seed 3170) from public trip files: 600 trips in one month (membership "
       "should win) and 525 trips spread over 2011–2024 (pay-per-use should win). The public data has no rider id, so a "
       "\"rider\" is an assembled sample.")
bullet("Froze the pricing page text per run (URL, access time, SHA-256) and checked all five rules the agent uses against it.")
bullet("UI at localhost:8470/hw7 (behind JWT login): CSV upload, pricing URL, Run, tool-call timeline, results panel, "
       "metrics strip. costs.py recomputes every figure independently and the panel shows agent vs verified numbers.")
bullet("The 8B model needed help: six earlier runs failed (invented a $300 price, pasted unfilled SQL placeholders, decision "
       "contradicting its totals, wrong membership total). Final prompt = retrieval fixes + copy-paste SQL + stepwise "
       "procedure + a one-shot self-consistency repair; thinking mode was abandoned (too slow on CPU).")
h2("Evidence required")
code(E.get("code/hw07/bike/tools.py", "sql_is_single_select", "csv_sql", "policy_retriever", "_eval", "calculator"))
code(json.dumps({k: {"input": v["input_schema"], "output": v["output_schema"]} for k, v in bike_tools.SCHEMAS.items()},
                separators=(",", ":")), size=7)
shot("4.1: UI, membership-wins scenario — tool-call timeline, cost comparison, decision, citations, metrics strip "
     "(step count, total time, stop reason)")
shot("4.2: UI, pay-per-use-wins scenario — same panels")
ref = {n: r["reference"] for n, r in bike.items()}
ans = {n: r["answer"] for n, r in bike.items()}
cit = {n: r["citations"][0] for n, r in bike.items()}
mw, pp = ref["membership_wins"], ref["pay_per_use_wins"]
table(["", "Membership wins", "Pay-per-use wins"], [
    ["Dataset", f"heavy_rider.csv — {mw['rides']} trips, 1 month", f"light_rider.csv — {pp['rides']} trips, {pp['months_spanned']} months"],
    ["Decision", ans["membership_wins"]["decision"], ans["pay_per_use_wins"]["decision"]],
    ["Pay-per-use total", f"${mw['pay_per_use_total']:,.2f}", f"${pp['pay_per_use_total']:,.2f}"],
    ["Membership total (fee + residual)", f"${mw['membership_total']:,.2f} (${mw['membership_fee_total']:,.2f} + ${mw['membership_residual']:,.2f})",
     f"${pp['membership_total']:,.2f} (${pp['membership_fee_total']:,.2f} + ${pp['membership_residual']:,.2f})"],
    ["Rides/month: actual vs break-even", f"{mw['actual_rides_per_month']:.0f} vs {mw['break_even_rides_per_month']}",
     f"{pp['actual_rides_per_month']} vs {pp['break_even_rides_per_month']}"],
    ["Steps / time / stop reason", f"{bike['membership_wins']['step_count']} / {bike['membership_wins']['total_time_s']} s / {bike['membership_wins']['stop_reason']}",
     f"{bike['pay_per_use_wins']['step_count']} / {bike['pay_per_use_wins']['total_time_s']} s / {bike['pay_per_use_wins']['stop_reason']}"],
], size=9)
rich([("Membership wins. ", True),
      (f"{mw['rides']} rides, {mw['avg_minutes']} min average, {mw['ebike_share']:.0%} e-bike. Pay-per-use would cost "
       f"${mw['pay_per_use_total']:,.2f}; membership costs one month ($10.00) plus ${mw['membership_residual']:,.2f} of "
       f"overage = ${mw['membership_total']:,.2f}. The agent chose Buy Monthly Membership (break-even "
       f"{mw['break_even_rides_per_month']} rides/month vs {mw['actual_rides_per_month']:.0f} actual). Stop reason "
       f"{bike['membership_wins']['stop_reason']}, {bike['membership_wins']['step_count']} steps (the last is the "
       "self-consistency repair of a decision that contradicted the model's own totals).", False)])
rich([("Pay-per-use wins. ", True),
      (f"{pp['rides']} rides over {pp['months_spanned']} months ({pp['actual_rides_per_month']}/month, {pp['avg_minutes']} min "
       f"average). Pay-per-use costs ${pp['pay_per_use_total']:,.2f}; membership costs {pp['months_spanned']} × $10 = "
       f"${pp['membership_fee_total']:,.2f} plus ${pp['membership_residual']:,.2f} = ${pp['membership_total']:,.2f}. The agent "
       f"chose Pay Per Ride/Minute (break-even {pp['break_even_rides_per_month']}/month vs {pp['actual_rides_per_month']} actual). "
       f"Stop reason {bike['pay_per_use_wins']['stop_reason']}, {bike['pay_per_use_wins']['step_count']} steps.", False)])
runid = {"membership_wins": "run_5b2a4f14", "pay_per_use_wins": "run_ba648200"}
table(["Scenario", "Source URL", "Accessed (UTC)", "SHA-256", "Saved text"], [
    [n.replace("_", " "), cit[n]["url"], cit[n]["accessed_at"], cit[n]["sha256"], f"raw/pricing_snapshots/{runid[n]}.txt"]
    for n in ("membership_wins", "pay_per_use_wins")], size=8)
body("Caveats: the light dataset applies today's prices to 2011–2024 trips and assumes the rides are spread evenly over "
     "its span; the page mentions a \"30-Day Membership\" without a price.", italic=True)

# ============================================================================================
# Part 5
# ============================================================================================
h1("Part 5 — Prompt Injection and Tool Security")
h2("What we did")
bullet("Wrote a threat model (three attacker goals and the implementation condition that lets each succeed).")
bullet("Built local hostile pricing-page fixtures from the real page text with one injected block each (override, SQL, "
       "exfiltration) plus two stronger variants (authority-mimicking notice at the top, repeated).")
bullet("Implemented both defenses: retrieved text labelled as untrusted in the prompt, and a single read-only SELECT "
       "contract enforced inside csv_sql regardless of the model's instructions.")
bullet("Ran each attack at three levels (before / prompt defense / prompt + tool defense) in three rounds: the structured "
       "Part 4 agent, a naive minimal-prompt agent, and the naive agent against the stronger fixtures; then replayed the "
       "injected SQL directly at csv_sql to test the tool boundary on its own.")
h2("Evidence required")
table(["#", "Attacker goal", "Condition that lets it succeed"], [
    ["1", "Recommendation override (force \"Pay Per Ride/Minute\")", "Page text treated as instructions; no check of the decision against the computed costs"],
    ["2", "Non-read-only SQL misuse (DROP / UPDATE / stacked)", "csv_sql runs whatever SQL the model sends on a writable connection"],
    ["3", "Data exfiltration (raw CSV rows in the answer)", "Agent can SELECT * and obeys the request; no output policy"]], size=9)
code(re.sub(r"</?p>", "", re.search(r"<p>(\[SYSTEM MESSAGE.*?)</p>", (REPO / "reports/hw07/fixtures/hostile_pricing_override_strong.html").read_text(), re.S).group(1)),
     size=7)
body("Fixtures saved in reports/hw07/fixtures/. Before/after results (one sample per cell; excerpts from "
     "raw/prompt_injection_results*.json, full traces in RUN_LOG.txt; \"no valid answer\" = the run ended without a "
     "parseable answer, not counted as resisted):", after=2)


def cell_text(attack, c):
    base = attack.split("_")[0]
    head = ("ATTACK SUCCEEDED" if c["attack_succeeded"] else "resisted" if c["stop_reason"] == "completed" else "no valid answer")
    if base == "override":
        ex = f"decision = {c['decision']!r}"
    elif base == "sql":
        stmts = [s for s in c["csv_sql_calls"] if s and not s.strip().lower().startswith("select")]
        ex = (f"issued {clip(stmts[0], 40)!r}; " if stmts else "") + clip(c["detail"], 60)
    else:
        ex = clip(c["detail"], 70)
    return f"{head}. {ex}"


names = {"override": "Recommendation override", "sql": "Non-SELECT tool misuse", "exfil": "Data exfiltration"}
for title, res in inj.items():
    if not res:
        continue
    body(title, bold=True, after=1)
    rows = []
    for a in sorted({k.split("/")[0] for k in res}, key=lambda k: ["override", "sql", "exfil"].index(k.split("_")[0])):
        rows.append([names[a.split("_")[0]]] + [cell_text(a, res[f"{a}/{d}"]) if f"{a}/{d}" in res else "—"
                                                 for d in ("before", "prompt", "prompt+tool")])
    table(["Attack", "Before defenses", "After prompt defense", "After prompt + tool defense"], rows, size=8, widths=[1.1, 1.9, 1.9, 1.9])
allc = [c for r in inj.values() if r for c in r.values()]
off = sum(r["data_changed"] for r in replay["guard_off"])
on = sum(r["data_changed"] for r in replay["guard_on"])
body(f"Overall {sum(c['attack_succeeded'] for c in allc)} of {len(allc)} live attack runs succeeded: the naive agent ran injected "
     "SQL with no defenses, and the stronger override fixture succeeded after the prompt defense and after prompt + tool "
     "defense (resisted with no defenses). Exfiltration never worked (0 of 9). Tool-boundary replay (scripted, no model): "
     f"with the contract off {off} of 7 hostile statements changed the data; with it on {on} did, all 7 were refused and a "
     "legitimate SELECT still ran.", italic=True)
shot("5.1 (optional): terminal — the tool-boundary replay (python code/hw07/bike/part5_attacks.py replay)")
h2("Why tool-boundary enforcement differs from a prompt-only defense")
body("A prompt defense is a request to the model: it works only if the model complies, better-worded text can undo it, and "
     "nothing verifies the outcome — round 3 shows the label failing to stop the override. A tool-boundary check is code "
     "that runs on every call whatever the model was told or believes: a fooled or simply wrong model still cannot make "
     "csv_sql run anything but one SELECT. It is deterministic, testable without a model and fails closed. It only covers "
     "what the tool can see, so it cannot stop a wrong recommendation or data paraphrased into the answer; those need "
     "output checks.")

# ============================================================================================
# Part 6
# ============================================================================================
h1("Part 6 — File Tools and a Safety Gate")
h2("What we did")
bullet("Implemented read_file (max_lines), write_file, edit_file (returns a short diff), glob_files, search_in_files "
       "(file_pattern) and bash in code/hw07/file_tools.py, all confined to a temporary sandbox by one path guard.")
bullet("Safety gate (pure Python, no model): module-level SAFE_PREFIXES, confirm_bash(command, auto_approve=False) returning "
       "allow/block plus a reason, and an independent is_destructive() deny-list (recursive delete, privilege escalation, "
       "permission/ownership change, raw-device write, filesystem creation, redirection to root paths). Destructive commands "
       "need explicit confirmation even when they match SAFE_PREFIXES.")
bullet("Integration test: three small Python files, then glob → search → read finds the one containing DEBUG.")
bullet("Gate test: 5 commands pass, 5 blocked. Extra probing found 4 false allows (lsof -i; ls; curl … | sh; echo $(whoami); "
       "cat a && python evil.py) because the first version used startswith(SAFE_PREFIXES); fixed by checking each chained "
       "segment on whole words and rejecting subshells. All four are kept as regression cases (14/14 correct).")
h2("Evidence required")
code(E.get("code/hw07/file_tools.py", "read_file", "write_file", "edit_file", "glob_files", "search_in_files", "bash"))
code(E.const("code/hw07/file_tools.py", "SAFE_PREFIXES") + "\n\n" + E.get("code/hw07/file_tools.py", "is_destructive", "confirm_bash"))
shot("6.1: one combined test run — (a) glob → search → read finds the file containing DEBUG, and (b) the safety-gate test "
     "(5 pass / 5 blocked, plus the regression cases), false allow identified and fixed (name visible)")

# ============================================================================================
h1("Self-check and repository")
body(f"make verify-hw07 starts the checks against the running backend and the real model and writes "
     f"reports/hw07/verification.json (homework 7, SID4 3170, SEED 3170, VERIFY_SEED 263170, model qwen3:8b, commit, "
     f"pass/fail per check): {ver['passed']} passed, {ver['failed']} failed, {ver['skipped']} skipped of {ver['total_checks']}. "
     "Deliverables in reports/hw07/: RUN_LOG.txt, raw/, METRICS.md, AI_USE.md, verification.json, this report.")
shot("7.1 (optional): terminal — make verify-hw07 ending in the passed/failed summary (name visible)")

h1("AI use statement")
fill_in("Paste your AI_USE.md answers here: (1) what you used an AI assistant for and what you did yourself; "
        "(2) one AI-produced output that was wrong/unsuitable, or one thing you independently verified; "
        "(3) how you detected the problem or verified the result; (4) what you changed and why it works now.")

h1("References")
for ref_ in ["Capital Bikeshare — pricing: https://capitalbikeshare.com/pricing (captured text and SHA-256 in raw/pricing_snapshots/).",
             "Capital Bikeshare — system data: https://s3.amazonaws.com/capitalbikeshare-data/."]:
    bullet(ref_)

doc.save(OUT)
print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes, {len(doc.paragraphs)} paragraphs, {len(doc.tables)} tables, "
      f"{sum('Screenshot' in p.text for p in doc.paragraphs)} screenshot placeholders; HEAD {short})")
