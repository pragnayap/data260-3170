#!/usr/bin/env python3
"""
HW11 self-check. Writes reports/hw11/verification.json. No LLM, no Muse and no network are needed.

What it can prove from this repository: the policy, fixtures and golden labels are consistent, the labels were committed before
the first agent run, the real tool behaves as the report says on the fixtures, and the numbers in the report agree with the
evidence transcribed from the Muse run. What it cannot prove: the agent's own decisions (those live in Muse's cloud ledger and
are shown by the screenshots).

    .venv/bin/python code/verify_hw11.py

A check whose artifact does not exist yet (the PDF, unfinished report placeholders) is SKIPPED with its reason, never passed.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KIT = REPO / "code" / "hw11" / "stock-watch"
REPORT = REPO / "reports" / "hw11"
RAW = REPORT / "raw"
SID4, SEED, VERIFY_SEED, PORT_BASE, PREFIX = 3170, 3170, 263170, 8470, "s3170"
CATEGORIES = ["normal", "boundary", "adversarial", "ambiguous", "near_duplicate", "interruption"]
DECISIONS = {"notify", "digest", "ask", "quiet", "not_retrieved"}

checks: list[dict] = []


class Skip(Exception):
    pass


def banner(label: str) -> None:
    """Student name in every terminal screenshot."""
    print(f"Pragnaya Priyadarshini HW11 - {label}", flush=True)


def record(name: str, status: str, detail: str = "") -> None:
    checks.append({"check": name, "status": status, "detail": detail})
    print(f"[{status:<4}] {name}" + (f" -- {detail}" if detail else ""), flush=True)


def run(name: str, fn) -> None:
    try:
        ok, detail = fn()
        record(name, "PASS" if ok else "FAIL", detail)
    except Skip as s:
        record(name, "SKIP", str(s))
    except Exception as exc:  # noqa: BLE001
        record(name, "FAIL", f"{exc.__class__.__name__}: {exc}")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


def load_watch(home: Path):
    spec = importlib.util.spec_from_file_location("watch_hw11", home / "watch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sandbox() -> Path:
    """A throw-away copy of the kit, so verification never touches the real state folders."""
    home = Path(tempfile.mkdtemp(prefix="hw11_verify_")) / "stock-watch"
    shutil.copytree(KIT, home, ignore=shutil.ignore_patterns("state", "digests", "__pycache__", ".DS_Store"))
    return home


def tool(home: Path, *args: str) -> str:
    return subprocess.run([sys.executable, "watch.py", *args], cwd=home, capture_output=True, text=True).stdout


def main() -> int:
    banner("verify_hw11.py")
    gold = json.loads((KIT / "golden" / "gold_hw11.json").read_text())["cases"]
    evidence = json.loads((RAW / "muse_run_outputs.json").read_text())
    home = sandbox()
    watch = load_watch(home)

    def files_exist():
        need = ["policy.md", "sources.json", "watch.py", "golden/gold_hw11.json", "fixtures/hw11/edgar_8k.xml",
                "fixtures/hw11/newswire.xml", "fixtures/hw11/prices_pncr.us.csv", "fixtures/hw11/prices_rwbv.us.csv",
                "fixtures/hw11/prices_qntf.us.csv", "fixtures/hw11/prices_orbx.us.csv"]
        miss = [f for f in need if not (KIT / f).exists()] + [f for f in ("raw/muse_run_outputs.json",) if not (RAW / "muse_run_outputs.json").exists()]
        return not miss, "all present" if not miss else f"missing {miss}"

    run("required HW11 files exist", files_exist)

    def gold_ok():
        cat = Counter(c["category"] for c in gold)
        bad = [c["case_id"] for c in gold if c["expected"] not in DECISIONS or not c["match_title"] or not c["why"]]
        ok = len(gold) == 12 and all(cat[k] == 2 for k in CATEGORIES) and not bad
        return ok, f"{len(gold)} cases, per category {dict(cat)}, malformed {bad}"

    run("3: golden set is 12 cases, two per category, every label valid", gold_ok)

    def labels_first():
        paths = ["code/hw11/stock-watch/golden/gold_hw11.json", "code/hw11/stock-watch/policy.md", "code/hw11/stock-watch/fixtures/hw11"]
        ct = git("log", "-1", "--format=%ct", "--", *paths)
        if not ct:
            raise Skip("golden files were never committed")
        dirty = git("status", "--porcelain", "--", *paths)
        started = datetime.fromisoformat(evidence["fixture_run"]["started_utc"]).timestamp()
        gap = int(started - int(ct))
        return not dirty and gap > 0, f"policy, fixtures and golden labels last changed in commit {git('log', '-1', '--format=%h', '--', *paths)}, " \
                                      f"{gap} s before the first Muse run; uncommitted changes: {'none' if not dirty else dirty}"

    run("3: policy, fixtures and golden labels were committed (and unmodified) BEFORE the first agent run", labels_first)

    scan_out: dict = {}

    def fixtures_scan():
        tool(home, "reset", "--yes")
        tool(home, "init")
        scan = json.loads(tool(home, "scan", "--fixtures", "fixtures/hw11"))
        items = [r[0] for r in sqlite3.connect(home / "state" / "watch.db").execute("select title from items")]
        rows, bad = [], []
        for c in gold:
            hit = [t for t in items if watch.norm_title(c["match_title"]) in watch.norm_title(t)]
            ok = (len(hit) == 0 and c["expected"] == "not_retrieved") or (len(hit) == 1 and c["expected"] != "not_retrieved")
            rows.append({"case_id": c["case_id"], "expected": c["expected"], "matches": hit})
            if not ok:
                bad.append(c["case_id"])
        scan_out.update({"scan": scan, "case_matches": rows})
        (RAW / "local_fixture_scan.json").write_text(json.dumps(scan_out, indent=2))
        fr = evidence["fixture_run"]
        agree = scan["pending_decisions"] == fr["new"] and scan["duplicates_suppressed"] == fr["duplicates_suppressed"]
        return not bad and agree, (f"{scan['pending_decisions']} candidates, {scan['duplicates_suppressed']} duplicate suppressed "
                                   f"(Muse reported {fr['new']} new, {fr['duplicates_suppressed']} duplicate); every golden case resolves; mismatches {bad}")

    run("3: the real tool resolves every golden case on the fixtures and matches Muse's 11 new / 1 duplicate", fixtures_scan)

    def guard():
        feed = watch.parse_feed((KIT / "fixtures" / "hw11" / "newswire.xml").read_text())
        flag = {i["title"]: watch.scan_injection(i["title"] + "\n" + i["summary"])[0] for i in feed}
        a1 = next(v for k, v in flag.items() if "Voltaic Motors battery" in k)
        a2 = next(v for k, v in flag.items() if "Quantum Fabrics investor" in k)
        return a1 and not a2, f"guard flags A1={a1}, A2={a2} (A2 is the polite injection the guard is expected to miss; the model must catch it)"

    run("4: injection guard catches the explicit injection (A1) and misses the polite one (A2), as designed", guard)

    def demo():
        res = subprocess.run(["bash", "demo_test.sh"], cwd=home, capture_output=True, text=True)
        (RAW / "local_demo_test.txt").write_text(res.stdout)
        return res.returncode == 0 and "'decision_accuracy': 1.0" in res.stdout, "kit demo_test.sh still ends with decision_accuracy 1.0 after the watch.py extensions"

    run("the kit's own demo still passes after the watch.py extensions", demo)

    def price_guard():
        bad = home / "bad_fixtures"
        bad.mkdir()
        (bad / "prices_pncr.us.csv").write_text("<html>please enable JavaScript</html>")
        tool(home, "reset", "--yes")
        tool(home, "init")
        tool(home, "scan", "--fixtures", "bad_fixtures")
        trace = json.loads(tool(home, "trace"))
        errs = [t for t in trace if t["step"] == "source_error" and t["detail"].get("ticker") == "pncr.us"]
        return len(errs) == 1, f"a non-CSV price reply is logged as {len(errs)} source_error in the real tool's trace (the kit alone treated it as 'no price moves')"

    run("watch.py extension: a non-CSV price reply is an error, not 'no price moves'", price_guard)

    def evidence_ok():
        fr, mt, us = evidence["fixture_run"], evidence["metrics"], evidence["usage"]
        notify_cases = [c for c in gold if c["expected"] == "notify"]
        titles_ok = all(any(watch.norm_title(c["match_title"]) in watch.norm_title(a["title"]) for a in fr["alerts_sent"]) for c in notify_cases)
        wall = int((datetime.fromisoformat(fr["finished_utc"]) - datetime.fromisoformat(fr["started_utc"])).total_seconds())
        active = int((datetime.fromisoformat(fr["finished_utc"]) - datetime.fromisoformat(fr["resumed_utc"])).total_seconds())
        line_ok = f"{fr['new']} new, {fr['duplicates_suppressed']} duplicates suppressed, {fr['alerts']} alerts, {fr['digest']} digest, {fr['need_review']} need review" in fr["summary_line"]
        tok_ok = mt["tokens_per_accepted_notification"] == us["tokens_assumed_for_metrics"] // fr["alerts"]
        ok = (titles_ok and len(notify_cases) == fr["alerts"] == len(fr["alerts_sent"]) and line_ok and tok_ok
              and wall == 130 and active == 15 and us["after_pct"] == 0)
        return ok, (f"{fr['alerts']} alerts = the {len(notify_cases)} notify cases; summary line fields agree; tokens/alert "
                    f"{mt['tokens_per_accepted_notification']} = {us['tokens_assumed_for_metrics']}/{fr['alerts']}; wall {wall} s, active {active} s")

    run("5/6: the numbers in the report agree with the transcribed Muse evidence", evidence_ok)

    def live_honest():
        lv = evidence["live_run"]
        errs = lv["source_errors"]
        ok = lv["summary_line"].startswith("Run ") and len(errs) == 5 and not lv["agent_summary_named_source_errors"]
        return ok, f"live run shows {len(errs)} source errors and the agent's summary did not name them (recorded as a finding, not hidden)"

    run("1/7: the live-run failure is recorded in the evidence", live_honest)

    def privacy():
        needle = "sjsu" + ".edu"
        hits = [str(p.relative_to(REPO)) for base in (KIT, REPORT) for p in base.rglob("*")
                if p.is_file() and p.suffix in {".json", ".md", ".txt", ".py", ".sh", ".xml", ".csv"} and needle in p.read_text(errors="ignore")]
        return not hits, "no personal university email in the committed kit or report text files" if not hits else f"found in {hits}"

    run("the personal email is not in the repo copy", privacy)

    def shots():
        from PIL import Image
        files = sorted((REPORT / "screenshots").glob("*.png"))
        if not files:
            raise Skip("no screenshots yet")
        for f in files:
            Image.open(f).verify()
        return len(files) >= 17, f"{len(files)} screenshots, all readable"

    run("report screenshots exist and are readable images", shots)

    def report_format():
        from docx import Document
        p = REPORT / "Priyadarshini_HW11_Report.docx"
        if not p.exists():
            raise Skip("report .docx not built yet")
        d = Document(p)
        h1, h2, body = d.styles["Heading 1"], d.styles["Heading 2"], d.styles["Normal"]
        ok = (h1.font.size.pt, h1.font.bold, h2.font.size.pt, h2.font.bold, body.font.size.pt) == (14.0, True, 12.0, True, 11.0)
        return ok, f"headings {h1.font.size.pt:g}/{h2.font.size.pt:g} pt bold, body {body.font.size.pt:g} pt"

    run("report formatting: main headings 14 pt bold, subheadings 12 pt bold, body 11 pt", report_format)

    def report_complete():
        from docx import Document
        p = REPORT / "Priyadarshini_HW11_Report.docx"
        if not p.exists():
            raise Skip("report .docx not built yet")
        text = "\n".join(x.text for x in Document(p).paragraphs)
        pending = text.count("[FILL") + text.count("[INSERT SCREENSHOT HERE]")
        if pending:
            raise Skip(f"{pending} red placeholders still to fill in the report")
        return True, "no unfinished placeholders"

    run("report has no unfinished placeholders", report_complete)

    def pdf_pages():
        pdf = REPORT / "Priyadarshini_HW11.pdf"
        if not pdf.exists():
            raise Skip("report PDF not exported yet (Priyadarshini_HW11.pdf)")
        from pypdf import PdfReader
        n = len(PdfReader(str(pdf)).pages)
        return n <= 25, f"{n} pages (limit 25)"

    run("report PDF is at most 25 pages", pdf_pages)

    def ruff():
        files_ = ["code/verify_hw11.py", "code/hw11/build_metrics.py"]
        res = subprocess.run([str(REPO / ".venv/bin/ruff"), "check", *files_], cwd=REPO, capture_output=True, text=True)
        return res.returncode == 0, "ruff clean (default rules)" if res.returncode == 0 else res.stdout[-400:]

    run("ruff passes on the new HW11 scripts", ruff)

    def banners():
        scripts = [REPO / "code/verify_hw11.py", REPO / "code/hw11/build_metrics.py"]
        bad = [p.name for p in scripts if "banner(" not in p.read_text()]
        return not bad, f"{len(scripts)} runnable scripts print the student name banner" if not bad else f"no banner in {bad}"

    run("student name banner in every runnable script", banners)

    shutil.rmtree(home.parent, ignore_errors=True)
    passed = sum(c["status"] == "PASS" for c in checks)
    failed = sum(c["status"] == "FAIL" for c in checks)
    skipped = sum(c["status"] == "SKIP" for c in checks)
    out = {"homework": 11, "SID4": SID4, "PORT_BASE": PORT_BASE, "PREFIX": PREFIX, "SEED": SEED, "VERIFY_SEED": VERIFY_SEED, "DOMAIN_ID": 2,
           "commit": git("rev-parse", "HEAD"), "working_tree_clean": git("status", "--porcelain", "--untracked-files=no") == "",
           "model_configuration": {"agent": "Meta Muse (free tier), standing instructions + policy.md", "tool": "stock-watch kit watch.py with two disclosed extensions",
                                   "note": "agent decisions are shown by the Muse screenshots; this script verifies the repo side"},
           "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "passed": passed, "failed": failed, "skipped": skipped, "total_checks": len(checks), "checks": checks}
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "verification.json").write_text(json.dumps(out, indent=2))
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped of {len(checks)} -> {REPORT / 'verification.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
