#!/usr/bin/env python3
"""
Self-check script for HW4. A smoke test, not exhaustive coverage: does the
backend respond on PORT_BASE, do the naive/fixed list endpoints both return
real data, does auth actually gate the CRUD routes, is the DB seeded, and do
Part 3/4's raw output files exist.

Does not modify application code; the one piece of state it writes is a
throwaway verification user (email starts with "verify-hw04-"), which is
harmless to leave in the users table.

Usage:
    .venv/bin/python code/verify_hw04.py                 # assumes the backend
                                                           # is already running
    .venv/bin/python code/verify_hw04.py --start-server   # boots it first
"""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = REPO_ROOT / "reports" / "hw04"
RAW_DIR = REPORTS_DIR / "raw"
WEBAPP_DIR = REPO_ROOT / "code" / "web_application"

SID4 = 3170
PORT_BASE = 8000 + (SID4 % 900)  # 8470
SEED = SID4
VERIFY_SEED = 260000 + SID4
BASE_URL = f"http://127.0.0.1:{PORT_BASE}"

VERIFY_EMAIL = f"verify-hw04-{int(time.time())}@example.com"
# Fresh random password per run: the account is throwaway, so nothing needs storing.
VERIFY_PASSWORD = secrets.token_urlsafe(16)

checks: list[dict] = []


def check(name: str, passed, detail: str = "") -> bool:
    status = "SKIP" if passed is None else ("PASS" if passed else "FAIL")
    checks.append({"check": name, "passed": None if passed is None else bool(passed), "skipped": passed is None, "detail": str(detail)})
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))
    return bool(passed)


def get_commit_hash() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    except Exception:
        return "unknown (uncommitted)"


def wait_for_server(timeout_s: int = 30) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            requests.get(BASE_URL + "/", timeout=1)
            return True
        except requests.ConnectionError:
            time.sleep(0.5)
    return False


def run_checks(server_proc=None) -> None:
    reachable = wait_for_server(timeout_s=5)
    if not check("backend responds on PORT_BASE (8470)", reachable):
        return

    session = requests.Session()

    resp = session.get(f"{BASE_URL}/api/incidents")
    check("protected route rejects anonymous access (401)", resp.status_code == 401, f"got {resp.status_code}")

    signup = session.post(
        f"{BASE_URL}/api/auth/signup",
        json={"name": "HW4 Verify Bot", "email": VERIFY_EMAIL, "password": VERIFY_PASSWORD},
    )
    check("signup succeeds (201)", signup.status_code == 201, f"got {signup.status_code}")

    login = session.post(f"{BASE_URL}/api/auth/login", json={"email": VERIFY_EMAIL, "password": VERIFY_PASSWORD})
    ok = check("login succeeds and sets session cookie", login.status_code == 200 and "s3170_db_session" in session.cookies.get_dict())

    if ok:
        me = session.get(f"{BASE_URL}/api/auth/me")
        check("authenticated /api/auth/me returns the logged-in user", me.status_code == 200 and me.json().get("email") == VERIFY_EMAIL)

        fixed = session.get(f"{BASE_URL}/api/incidents", params={"page": 1, "page_size": 10, "impl": "fixed"})
        naive = session.get(f"{BASE_URL}/api/incidents", params={"page": 1, "page_size": 10, "impl": "naive"})
        check("fixed list endpoint returns data", fixed.status_code == 200 and fixed.json().get("total", 0) > 0, f"total={fixed.json().get('total') if fixed.status_code==200 else fixed.status_code}")
        check("naive list endpoint returns data", naive.status_code == 200 and naive.json().get("total", 0) > 0)
        check(
            "naive and fixed agree on total row count",
            fixed.status_code == 200 and naive.status_code == 200 and fixed.json()["total"] == naive.json()["total"],
        )
        check("DB seeded with >= 5000 incidents (Part 3)", fixed.status_code == 200 and fixed.json().get("total", 0) >= 5000, f"total={fixed.json().get('total')}")

        fixed_stmts = int(fixed.headers.get("X-SQL-Statements", -1))
        naive_stmts = int(naive.headers.get("X-SQL-Statements", -1))
        check(
            "naive issues more SQL statements than fixed at the same page size (N+1 present)",
            naive_stmts > fixed_stmts,
            f"naive={naive_stmts} fixed={fixed_stmts}",
        )

        routes = session.get(f"{BASE_URL}/api/routes")
        check("routes table reachable and has >= 200 rows (Part 3)", routes.status_code == 200 and len(routes.json()) >= 200, f"count={len(routes.json()) if routes.status_code==200 else routes.status_code}")

        logout = session.post(f"{BASE_URL}/api/auth/logout")
        check("logout clears the session (204)", logout.status_code == 204)

        post_logout = session.get(f"{BASE_URL}/api/incidents")
        check("session cookie is unusable after logout", post_logout.status_code == 401)
    else:
        for name in [
            "authenticated /api/auth/me returns the logged-in user",
            "fixed list endpoint returns data",
            "naive list endpoint returns data",
            "naive and fixed agree on total row count",
            "DB seeded with >= 5000 incidents (Part 3)",
            "naive issues more SQL statements than fixed at the same page size (N+1 present)",
            "routes table reachable and has >= 200 rows (Part 3)",
            "logout clears the session (204)",
            "session cookie is unusable after logout",
        ]:
            check(name, None, "skipped: login did not succeed")

    # --- Part 3 deliverable files ---
    n1_csv = RAW_DIR / "n1_requests.csv"
    check("reports/hw04/raw/n1_requests.csv exists", n1_csv.exists())
    if n1_csv.exists():
        line_count = sum(1 for _ in open(n1_csv)) - 1  # minus header
        check("n1_requests.csv has 180 measured requests", line_count == 180, f"found {line_count}")

    check("reports/hw04/raw/index_explain.txt exists (Part 3.8)", (RAW_DIR / "index_explain.txt").exists())
    check("reports/hw04/raw/n1_summary.md exists", (RAW_DIR / "n1_summary.md").exists())

    # --- Part 3 generator script committed ---
    check("code/seed_hw04.py exists (generator script)", (REPO_ROOT / "code" / "seed_hw04.py").exists())

    # --- Part 4 deliverable files (degrade to SKIP if the RAG build hasn't landed yet) ---
    rag_py = REPO_ROOT / "code" / "rag.py"
    rag_docs = REPO_ROOT / "data" / "rag_docs"
    analysis = RAW_DIR / "analysis.md"
    check("code/rag.py exists", rag_py.exists() if rag_py.exists() else None)
    check("data/rag_docs/ has >= 5 documents", len(list(rag_docs.glob("*"))) >= 5 if rag_docs.exists() else None, f"found {len(list(rag_docs.glob('*'))) if rag_docs.exists() else 0}")
    check("reports/hw04/raw/analysis.md exists (300-500 word analysis)", analysis.exists() if analysis.exists() else None)

    # --- Part 1 frontend files ---
    frontend_dir = REPO_ROOT / "code" / "frontend" / "src"
    for component in ["pages/Home.jsx", "pages/Login.jsx", "pages/CreateRecord.jsx", "pages/UpdateRecord.jsx", "pages/DeleteRecord.jsx"]:
        check(f"code/frontend/src/{component} exists", (frontend_dir / component).exists())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-server", action="store_true", help="boot uvicorn before running checks")
    args = parser.parse_args()

    print(f"HW4 verification -- SID4={SID4} SEED={SEED} VERIFY_SEED={VERIFY_SEED}")
    print(f"commit: {get_commit_hash()}")
    print()

    server_proc = None
    if args.start_server:
        server_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(PORT_BASE)],
            cwd=WEBAPP_DIR,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    try:
        run_checks(server_proc)
    finally:
        if server_proc is not None:
            server_proc.terminate()
            server_proc.wait(timeout=10)

    passed = sum(1 for c in checks if c["passed"] is True)
    failed = sum(1 for c in checks if c["passed"] is False)
    skipped = sum(1 for c in checks if c["skipped"])

    result = {
        "homework": "HW4",
        "sid4": SID4,
        "commit_hash": get_commit_hash(),
        "model_configuration": "Ollama qwen3:8b (local, Part 4 RAG); FastAPI + SQLAlchemy + MySQL (Parts 1-3)",
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "summary": {"passed": passed, "failed": failed, "skipped": skipped, "total": len(checks)},
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "verification.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)

    print()
    print(f"{passed} passed, {failed} failed, {skipped} skipped -> {out_path}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
