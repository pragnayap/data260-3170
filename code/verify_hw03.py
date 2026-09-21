"""
Self-check script for HW3.

Two halves, matching the two halves of the assignment:

  Part 1  starts the FastAPI app on PORT_BASE and drives the real auth flow over
          HTTP -- anonymous access to the protected route, a bad login, a good
          login, the Set-Cookie attributes, logout, cookie replay after logout,
          and the idle timeout. The server is launched with a 3-second idle
          window so the timeout is testable in seconds rather than minutes.

  Part 2  checks the corpus, its manifest hashes, questions.yaml, and -- if the
          retrieval run has been done -- the raw output and METRICS.md. The
          Part 2 checks degrade to SKIP rather than FAIL when the run has not
          happened yet, so this script is useful before and after the run.

Behavioural, not textual: nothing asserts on page wording, only on status
codes, headers and file contents that the assignment actually requires.

Writes reports/hw03/verification.json and, as a side effect,
reports/hw03/raw/set_cookie_header.txt -- the captured Set-Cookie line the
write-up has to show.

Usage:
    python code/verify_hw03.py
    python code/verify_hw03.py --skip-server     # file/corpus checks only
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import py_compile
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

CODE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CODE_DIR.parent
REPORTS_DIR = REPO_ROOT / "reports" / "hw03"
RAW_DIR = REPORTS_DIR / "raw"
WEBAPP_DIR = CODE_DIR / "web_application"
TEMPLATES_DIR = WEBAPP_DIR / "templates"
CORPUS_DIR = REPO_ROOT / "data" / "corpus"

# --- Section 0 personal configuration (SID4 = 3170) ---
SID4 = 3170
PORT_BASE = 8000 + (SID4 % 900)      # 8470
PREFIX = f"s{SID4}"                  # s3170
SEED = SID4                          # 3170
VERIFY_SEED = 260000 + SID4          # 263170
DOMAIN_ID = SID4 % 8                 # 2 -> municipal transit incidents

MIN_CORPUS_BYTES = 200 * 1024
IDLE_TIMEOUT_FOR_TEST = 3            # seconds, injected into the server's env
SERVER_BOOT_TIMEOUT_S = 40

DEMO_USER = "dispatcher"
DEMO_PASSWORD = "TransitOps#2026"

checks: list[dict] = []


def check(name: str, passed, detail: str = "") -> bool:
    """Record a check. passed=None means 'skipped', which is not a failure."""
    status = "SKIP" if passed is None else ("PASS" if passed else "FAIL")
    checks.append({
        "check": name,
        "passed": None if passed is None else bool(passed),
        "skipped": passed is None,
        "detail": str(detail),
    })
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail else ""))
    return bool(passed)


def file_exists(path: Path, label: str) -> bool:
    return check(f"file_exists:{label}", path.exists(), str(path))


def compiles(path: Path, label: str) -> bool:
    if not path.exists():
        return check(f"compiles:{label}", False, "missing")
    try:
        py_compile.compile(str(path), doraise=True)
        return check(f"compiles:{label}", True)
    except py_compile.PyCompileError as exc:
        return check(f"compiles:{label}", False, str(exc).splitlines()[-1])


# --- Tiny HTTP client that does not follow redirects ---------------------

class Response:
    def __init__(self, status: int, headers: list[tuple[str, str]], body: bytes):
        self.status = status
        self.headers = headers
        self.body = body

    def header(self, name: str) -> str | None:
        for key, value in self.headers:
            if key.lower() == name.lower():
                return value
        return None

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def request(method: str, path: str, cookie: str | None = None,
            form: dict | None = None, timeout: float = 20.0) -> Response:
    """One HTTP request to the local server. Redirects are NOT followed, because
    every interesting auth assertion here is about the 303 itself."""
    connection = http.client.HTTPConnection("127.0.0.1", PORT_BASE, timeout=timeout)
    headers = {}
    body = None
    if cookie:
        headers["Cookie"] = cookie
    if form is not None:
        body = urlencode(form)
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        connection.request(method, path, body=body, headers=headers)
        raw = connection.getresponse()
        return Response(raw.status, raw.getheaders(), raw.read())
    finally:
        connection.close()


def cookie_from(response: Response) -> str | None:
    """The 'name=value' part of Set-Cookie, ready to send back."""
    header = response.header("set-cookie")
    if not header:
        return None
    pair = header.split(";", 1)[0].strip()
    return pair if pair and not pair.endswith("=") else None


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def wait_for_server(timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if request("GET", "/", timeout=3).status == 200:
                return True
        except (ConnectionRefusedError, socket.timeout, OSError):
            time.sleep(0.4)
    return False


# --- Part 1: auth over HTTP ---------------------------------------------

def check_part1_files() -> None:
    print("\nPart 1 - files and structure")
    file_exists(WEBAPP_DIR / "auth.py", "auth_py")
    file_exists(WEBAPP_DIR / "app.py", "app_py")
    for name in ("base.html", "home.html", "login.html", "dashboard.html"):
        file_exists(TEMPLATES_DIR / name, f"template_{name.split('.')[0]}")
    compiles(WEBAPP_DIR / "auth.py", "auth_py")
    compiles(WEBAPP_DIR / "app.py", "app_py")

    app_source = (WEBAPP_DIR / "app.py").read_text() if (WEBAPP_DIR / "app.py").exists() else ""
    check("app:uses_session_middleware", "SessionMiddleware" in app_source)
    check("app:includes_auth_router", "include_router(auth.router)" in app_source)

    auth_source = (WEBAPP_DIR / "auth.py").read_text() if (WEBAPP_DIR / "auth.py").exists() else ""
    check("auth:uses_apirouter", "APIRouter(" in auth_source,
          "routes are handled separately in a router")
    check("auth:no_plaintext_passwords_in_store",
          "password_hash" in auth_source and '"password":' not in auth_source)
    check("auth:server_side_revocation", "ACTIVE_SESSIONS" in auth_source,
          "signed cookies alone cannot be revoked on logout")

    base = (TEMPLATES_DIR / "base.html").read_text() if (TEMPLATES_DIR / "base.html").exists() else ""
    check("bootstrap:stylesheet_linked", "bootstrap" in base.lower())
    check("bootstrap:navbar", "navbar" in base.lower())
    login = (TEMPLATES_DIR / "login.html").read_text() if (TEMPLATES_DIR / "login.html").exists() else ""
    check("bootstrap:alert_on_login", "alert-" in login)
    dashboard = (TEMPLATES_DIR / "dashboard.html").read_text() if (TEMPLATES_DIR / "dashboard.html").exists() else ""
    check("bootstrap:cards", "card" in dashboard)


def check_part1_http() -> None:
    print(f"\nPart 1 - live auth flow on port {PORT_BASE}")

    if not port_is_free(PORT_BASE):
        check("server:port_free", False,
              f"something is already listening on {PORT_BASE}; stop it and re-run")
        return
    check("server:port_free", True, str(PORT_BASE))

    environment = dict(os.environ)
    environment["S3170_IDLE_TIMEOUT"] = str(IDLE_TIMEOUT_FOR_TEST)
    environment["S3170_SESSION_SECRET"] = "verify-hw03-fixed-secret"
    environment["PYTHONUNBUFFERED"] = "1"

    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app",
         "--host", "127.0.0.1", "--port", str(PORT_BASE), "--log-level", "warning"],
        cwd=str(WEBAPP_DIR), env=environment,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    try:
        if not check("server:started", wait_for_server(SERVER_BOOT_TIMEOUT_S),
                     f"uvicorn app:app on {PORT_BASE}"):
            output = process.stdout.read(4000).decode("utf-8", "replace") if process.stdout else ""
            print(output)
            return

        response = request("GET", "/")
        check("route:home_200", response.status == 200, f"GET / -> {response.status}")

        response = request("GET", "/dashboard")
        check("route:dashboard_anonymous_redirects",
              response.status == 303 and response.header("location", ) == "/login?expired=1",
              f"{response.status} -> {response.header('location')}")

        response = request("GET", "/login")
        check("route:login_200", response.status == 200, f"GET /login -> {response.status}")

        response = request("POST", "/login", form={"username": DEMO_USER, "password": "wrong-password"})
        check("auth:bad_password_rejected", response.status == 401, f"-> {response.status}")
        check("auth:bad_password_shows_alert", "alert-danger" in response.text,
              "Bootstrap alert rendered on the login page")
        check("auth:bad_password_issues_no_session", cookie_from(response) is None)

        response = request("POST", "/login", form={"username": "no-such-user", "password": "x"})
        check("auth:unknown_user_same_response", response.status == 401
              and "Invalid username or password" in response.text,
              "does not reveal which half was wrong")

        response = request("POST", "/login", form={"username": DEMO_USER, "password": DEMO_PASSWORD})
        set_cookie = response.header("set-cookie") or ""
        session_cookie = cookie_from(response)
        check("auth:good_login_redirects",
              response.status == 303 and response.header("location") == "/dashboard",
              f"{response.status} -> {response.header('location')}")
        check("auth:session_cookie_issued", session_cookie is not None)

        lowered = set_cookie.lower()
        check("cookie:httponly", "httponly" in lowered)
        check("cookie:secure", "secure" in lowered)
        check("cookie:samesite", "samesite" in lowered)
        check("cookie:all_three_attributes",
              all(a in lowered for a in ("httponly", "secure", "samesite")),
              set_cookie[:120])

        RAW_DIR.mkdir(parents=True, exist_ok=True)
        (RAW_DIR / "set_cookie_header.txt").write_text(
            "Captured from POST /login on 127.0.0.1:%d\n"
            "Generated by code/verify_hw03.py at %s\n\n"
            "Set-Cookie: %s\n" % (
                PORT_BASE,
                datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                set_cookie,
            )
        )
        check("cookie:header_captured_to_file", True,
              str((RAW_DIR / "set_cookie_header.txt").relative_to(REPO_ROOT)))

        response = request("GET", "/dashboard", cookie=session_cookie)
        check("route:dashboard_authenticated_200", response.status == 200,
              f"GET /dashboard with session -> {response.status}")
        check("dashboard:greets_user", "Dana Ruiz" in response.text)

        # Keep a copy of the live cookie, then log out and try to replay it.
        replay_cookie = session_cookie

        response = request("GET", "/logout", cookie=session_cookie)
        check("route:logout_redirects",
              response.status == 303 and response.header("location") == "/",
              f"{response.status} -> {response.header('location')}")

        response = request("GET", "/dashboard", cookie=replay_cookie)
        check("session:logged_out_cookie_cannot_reach_dashboard",
              response.status == 303,
              f"replayed a valid signed cookie after logout -> {response.status}")

        # Idle timeout: log in fresh, wait past the window, try again.
        response = request("POST", "/login", form={"username": DEMO_USER, "password": DEMO_PASSWORD})
        idle_cookie = cookie_from(response)
        check("session:relogin_ok", idle_cookie is not None)

        response = request("GET", "/dashboard", cookie=idle_cookie)
        check("session:live_before_timeout", response.status == 200, f"-> {response.status}")

        time.sleep(IDLE_TIMEOUT_FOR_TEST + 1.5)
        response = request("GET", "/dashboard", cookie=idle_cookie)
        check("session:idle_timeout_blocks_dashboard",
              response.status == 303 and response.header("location") == "/login?expired=1",
              f"after {IDLE_TIMEOUT_FOR_TEST}s idle -> {response.status} "
              f"{response.header('location')}")

        response = request("GET", "/api/incidents")
        check("hw2:api_still_works", response.status == 200,
              "HW2 REST API unaffected by the HW3 changes")
        response = request("GET", "/incidents")
        check("hw2:form_moved_to_incidents", response.status == 200)

    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


# --- Part 2: corpus, questions, retrieval output -------------------------

def check_part2() -> None:
    print("\nPart 2 - corpus and retrieval artefacts")

    for label, path in [
        ("fetch_corpus", CODE_DIR / "fetch_corpus.py"),
        ("run_rag_chunking", CODE_DIR / "run_rag_chunking.py"),
        ("summarize_rag_metrics", CODE_DIR / "summarize_rag_metrics.py"),
    ]:
        file_exists(path, label)
        compiles(path, label)

    questions_path = REPORTS_DIR / "questions.yaml"
    manifest_path = REPORTS_DIR / "CORPUS_MANIFEST.json"
    sources_path = REPORTS_DIR / "SOURCES.md"

    file_exists(questions_path, "questions_yaml")
    file_exists(sources_path, "sources_md")
    file_exists(manifest_path, "corpus_manifest")

    # --- corpus ---
    if not CORPUS_DIR.exists() or not any(CORPUS_DIR.iterdir()):
        check("corpus:present", None, "data/corpus is empty -- run code/fetch_corpus.py")
        check("corpus:size_over_200kb", None, "corpus not built yet")
        check("corpus:hashes_match_manifest", None, "corpus not built yet")
    else:
        total = sum(p.stat().st_size for p in CORPUS_DIR.iterdir() if p.is_file())
        check("corpus:present", True, f"{len(list(CORPUS_DIR.iterdir()))} files")
        check("corpus:size_over_200kb", total >= MIN_CORPUS_BYTES,
              f"{total:,} bytes ({total / 1024:.1f} KB), floor {MIN_CORPUS_BYTES:,}")

        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            mismatched = []
            for entry in manifest.get("documents", []):
                local = CORPUS_DIR / entry["filename"]
                if not local.exists():
                    mismatched.append(f"{entry['filename']}: missing")
                    continue
                digest = hashlib.sha256()
                with local.open("rb") as handle:
                    for block in iter(lambda: handle.read(1 << 20), b""):
                        digest.update(block)
                if digest.hexdigest() != entry["sha256"]:
                    mismatched.append(f"{entry['filename']}: hash differs")
            check("corpus:hashes_match_manifest", not mismatched,
                  "; ".join(mismatched) if mismatched
                  else f"{len(manifest.get('documents', []))} documents verified")
            check("manifest:records_sha256",
                  all("sha256" in d and "bytes" in d for d in manifest.get("documents", [])))
        else:
            check("corpus:hashes_match_manifest", None, "no manifest yet")

    # --- questions ---
    try:
        import yaml
    except ImportError:
        check("questions:parse", None, "pyyaml not installed")
        yaml = None

    spec = None
    if yaml and questions_path.exists():
        spec = yaml.safe_load(questions_path.read_text())
        questions = spec.get("questions", [])
        check("questions:at_least_five", len(questions) >= 5, f"{len(questions)} questions")
        check("questions:have_expected_answers",
              all(q.get("expected_answer") for q in questions))
        check("questions:have_expected_source_files",
              all(q.get("expected_source_file") for q in questions))
        single = [q for q in questions if q.get("single_source")]
        check("questions:at_least_two_single_source", len(single) >= 2,
              f"{len(single)} marked single_source")
        if CORPUS_DIR.exists() and any(CORPUS_DIR.iterdir()):
            names = {p.name for p in CORPUS_DIR.iterdir()}
            missing = [q["expected_source_file"] for q in questions
                       if q.get("expected_source_file") not in names]
            check("questions:expected_files_exist_in_corpus", not missing,
                  "; ".join(missing) if missing else "all present")
        else:
            check("questions:expected_files_exist_in_corpus", None, "corpus not built yet")

    # --- questions.yaml committed before the results existed ---
    check_commit_ordering()

    # --- retrieval output ---
    rows_path = RAW_DIR / "retrieval_rows.jsonl"
    stats_path = RAW_DIR / "chunk_stats.json"
    metrics_path = REPORTS_DIR / "METRICS.md"

    if not rows_path.exists():
        for name in ("raw:retrieval_rows", "raw:three_techniques", "raw:graded_embed_model",
                     "raw:csv_present", "metrics:written", "metrics:no_placeholders",
                     "metrics:confident_miss_found"):
            check(name, None, "retrieval run not done yet -- run code/run_rag_chunking.py")
        return

    rows = [json.loads(line) for line in rows_path.read_text().splitlines() if line.strip()]
    check("raw:retrieval_rows", len(rows) > 0, f"{len(rows)} rows")
    techniques = {r["technique"] for r in rows}
    check("raw:three_techniques", techniques >= {"token", "semantic", "sentence"},
          ", ".join(sorted(techniques)))
    check("raw:csv_present", (RAW_DIR / "retrieval_rows.csv").exists())

    if stats_path.exists():
        stats = json.loads(stats_path.read_text())
        model = str(stats.get("embed_model", ""))
        check("raw:graded_embed_model", "all-MiniLM-L6-v2" in model,
              f"embed_model={model}")
    else:
        check("raw:graded_embed_model", None, "chunk_stats.json missing")

    if metrics_path.exists():
        metrics = metrics_path.read_text()
        check("metrics:written", True, f"{len(metrics.splitlines())} lines")
        check("metrics:no_placeholders", "TO FILL IN" not in metrics,
              "observations and conclusion still unwritten" if "TO FILL IN" in metrics else "")
        check("metrics:confident_miss_found",
              "_None at threshold" not in metrics,
              "the assignment requires at least one confidently-wrong retrieval")
    else:
        check("metrics:written", None, "run code/summarize_rag_metrics.py")
        check("metrics:no_placeholders", None, "")
        check("metrics:confident_miss_found", None, "")


def check_commit_ordering() -> None:
    """questions.yaml must be committed before the retrieval results exist.

    The assignment is explicit that the expected answers must not be rewritten
    after seeing the output, and a commit timestamp is the only evidence of that
    which survives into the repository.
    """
    def committed_at(relative: str) -> int | None:
        try:
            out = subprocess.run(
                ["git", "log", "-1", "--format=%ct", "--", relative],
                cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=20,
            )
            value = out.stdout.strip()
            return int(value) if value else None
        except (subprocess.SubprocessError, ValueError):
            return None

    questions_commit = committed_at("reports/hw03/questions.yaml")
    results_commit = committed_at("reports/hw03/raw/retrieval_rows.jsonl")

    if questions_commit is None:
        check("git:questions_committed", False,
              "reports/hw03/questions.yaml has no commit yet -- commit it BEFORE running retrieval")
        return
    check("git:questions_committed", True,
          datetime.fromtimestamp(questions_commit, timezone.utc).isoformat())

    if results_commit is None:
        check("git:questions_committed_before_results", None,
              "results not committed yet -- ordering still intact")
    else:
        check("git:questions_committed_before_results",
              questions_commit <= results_commit,
              f"questions {questions_commit} vs results {results_commit}")


# --- Main ----------------------------------------------------------------

def main() -> int:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--skip-server", action="store_true",
                                 help="skip the live HTTP auth flow")
    args = argument_parser.parse_args()

    print("=" * 78)
    print(f"HW3 verification  |  SID4 {SID4}  PORT_BASE {PORT_BASE}  PREFIX {PREFIX}")
    print(f"SEED {SEED}  VERIFY_SEED {VERIFY_SEED}  DOMAIN_ID {DOMAIN_ID} "
          f"(municipal transit incidents)")
    print("=" * 78)

    print("\nSection 0 - configuration")
    check("config:port_base", PORT_BASE == 8470, str(PORT_BASE))
    check("config:prefix", PREFIX == "s3170", PREFIX)
    check("config:seed", SEED == 3170, str(SEED))
    check("config:verify_seed", VERIFY_SEED == 263170, str(VERIFY_SEED))
    check("config:domain_id", DOMAIN_ID == 2, str(DOMAIN_ID))

    check_part1_files()
    if args.skip_server:
        check("server:started", None, "--skip-server")
    else:
        check_part1_http()
    check_part2()

    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
                            capture_output=True, text=True).stdout.strip()
    tags = subprocess.run(["git", "tag"], cwd=str(REPO_ROOT),
                          capture_output=True, text=True).stdout.split()
    check("git:hw3_tag_present", "hw3" in tags,
          "tag the submitted state hw3" if "hw3" not in tags else "hw3")

    passed = sum(1 for c in checks if c["passed"] is True)
    failed = sum(1 for c in checks if c["passed"] is False)
    skipped = sum(1 for c in checks if c["skipped"])

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "verification.json").write_text(json.dumps({
        "homework": "HW3",
        "sid4": SID4,
        "commit_hash": commit,
        "configuration": {
            "port_base": PORT_BASE,
            "prefix": PREFIX,
            "domain_id": DOMAIN_ID,
            "domain": "Municipal Transit Incidents",
            "idle_timeout_used_in_test_s": IDLE_TIMEOUT_FOR_TEST,
        },
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_checks": len(checks),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "checks": checks,
    }, indent=2) + "\n")

    print("\n" + "=" * 78)
    print(f"{passed} passed, {failed} failed, {skipped} skipped "
          f"(of {len(checks)} checks)")
    print(f"wrote {(REPORTS_DIR / 'verification.json').relative_to(REPO_ROOT)}")
    if skipped:
        print("\nSkipped checks are steps not done yet, not failures:")
        for c in checks:
            if c["skipped"]:
                print(f"  - {c['check']}: {c['detail']}")
    print("=" * 78)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
