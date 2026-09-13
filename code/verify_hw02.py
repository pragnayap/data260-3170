"""
Self-check script for HW2.

Smoke test only -- does the system come up and do the basic things, not every
edge case. Checks are behavioral rather than textual (the model never says the
same thing twice, so nothing here asserts on wording): the FastAPI backend is
started on PORT_BASE and exercised over HTTP, and the LangGraph pipeline is run
once and checked for "finished, and returned exactly three tags".

Writes reports/hw02/verification.json. Creates temporary files while running;
never modifies application code.

Usage:
    python code/verify_hw02.py
    python code/verify_hw02.py --skip-graph     # static + HTTP checks only (fast)
"""

import argparse
import json
import os
import py_compile
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CODE_DIR.parent
REPORTS_DIR = REPO_ROOT / "reports" / "hw02"
WEBAPP_DIR = CODE_DIR / "web_application"

# --- Section 0 personal configuration (SID4 = 3170) ---
SID4 = 3170
PORT_BASE = 8000 + (SID4 % 900)      # 8470
PREFIX = f"s{SID4}"                  # s3170
SEED = SID4                          # 3170
VERIFY_SEED = 260000 + SID4          # 263170
DOMAIN_ID = SID4 % 8                 # 2 -> transit incidents

MODEL = os.environ.get("SMOL_MODEL", "qwen3:8b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

GRAPH_TIMEOUT_S = 180  # a warm 2-node run is ~20s; this only catches a hang

checks = []


def check(name, passed, detail=""):
    checks.append({"check": name, "passed": bool(passed), "detail": str(detail)})
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f" -- {detail}" if detail else ""))
    return bool(passed)


def file_exists(path: Path, label: str):
    return check(f"file_exists:{label}", path.exists(), str(path))


def compiles(path: Path, label: str):
    if not path.exists():
        return check(f"compiles:{label}", False, "file missing")
    try:
        py_compile.compile(str(path), doraise=True)
        return check(f"compiles:{label}", True)
    except py_compile.PyCompileError as e:
        return check(f"compiles:{label}", False, e)


def port_is_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def wait_for_port(port: int, timeout: float = 25.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.4)
    return False


def http(method: str, url: str, payload=None, timeout: float = 10.0):
    """Return (status, parsed_body). Raises only on transport failure."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw.decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


# -------------------------
# Part 1/2 - FastAPI backend
# -------------------------

def check_fastapi():
    """Start the app on PORT_BASE, exercise CRUD + search over HTTP, shut down."""
    app_path = WEBAPP_DIR / "app.py"
    if not file_exists(app_path, "app_py") or not compiles(app_path, "app_py"):
        return

    if not port_is_free(PORT_BASE):
        check("fastapi:port_free", False,
              f"port {PORT_BASE} already in use; stop the other process and re-run")
        return
    check("fastapi:port_free", True, f"PORT_BASE={PORT_BASE}")

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", str(PORT_BASE)],
        cwd=str(WEBAPP_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        if not wait_for_port(PORT_BASE):
            out = ""
            if proc.poll() is not None:
                out = (proc.stdout.read() or "")[-500:]
            check("fastapi:starts_on_port_base", False, f"no listener after 25s. {out}")
            return
        check("fastapi:starts_on_port_base", True)

        base = f"http://127.0.0.1:{PORT_BASE}"

        status, body = http("GET", f"{base}/api/incidents")
        listed = check("fastapi:get_list_200", status == 200, f"status={status}")
        is_list = isinstance(body, list)
        check("fastapi:get_list_returns_array", listed and is_list, f"type={type(body).__name__}")
        before = len(body) if is_list else 0

        # Create -- the record must actually appear in the list afterwards.
        new_record = {
            "routeId": f"{PREFIX}-verify-route",
            "location": "Verification Station",
            "submitterEmail": "verify@example.com",
            "description": "Smoke-test record created by verify_hw02.py.",
            "category": "Delay",
        }
        status, created = http("POST", f"{base}/api/incidents", new_record)
        check("fastapi:post_create_201", status == 201, f"status={status}")
        new_id = created.get("id") if isinstance(created, dict) else None
        check("fastapi:post_returns_id", isinstance(new_id, int), f"id={new_id}")

        status, body = http("GET", f"{base}/api/incidents")
        after = len(body) if isinstance(body, list) else -1
        check("fastapi:list_grew_by_one", after == before + 1, f"{before} -> {after}")

        # Update -- record 1 must come back with the new values.
        if isinstance(body, list) and body:
            updated_fields = dict(new_record, routeId=f"{PREFIX}-updated-route")
            status, _ = http("PUT", f"{base}/api/incidents/1", updated_fields)
            check("fastapi:put_update_200", status == 200, f"status={status}")
            status, one = http("GET", f"{base}/api/incidents/1")
            check(
                "fastapi:update_persisted",
                status == 200 and isinstance(one, dict)
                and one.get("routeId") == f"{PREFIX}-updated-route",
                f"routeId={one.get('routeId') if isinstance(one, dict) else one}",
            )

        # Search -- every returned row must match the query somewhere.
        status, found = http("GET", f"{base}/api/incidents?search=Verification")
        ok = status == 200 and isinstance(found, list)
        matches = ok and all(
            "verification" in f"{r.get('routeId','')} {r.get('location','')}".lower()
            for r in found
        )
        check("fastapi:search_filters", ok and len(found) >= 1 and matches,
              f"status={status} hits={len(found) if ok else 'n/a'}")

        # Delete the highest id -- the list must shrink.
        status, body = http("GET", f"{base}/api/incidents")
        if isinstance(body, list) and body:
            highest = max(r["id"] for r in body if isinstance(r.get("id"), int))
            n_before = len(body)
            status, _ = http("DELETE", f"{base}/api/incidents/{highest}")
            check("fastapi:delete_2xx", status in (200, 204), f"status={status}")
            status, body = http("GET", f"{base}/api/incidents")
            n_after = len(body) if isinstance(body, list) else -1
            check("fastapi:list_shrank_by_one", n_after == n_before - 1, f"{n_before} -> {n_after}")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


# -------------------------
# Part 3/4 - graph
# -------------------------

def check_graph():
    """Run the graph once in a subprocess; it must finish and return 3 tags."""
    graph_path = CODE_DIR / "agents_graph.py"
    if not file_exists(graph_path, "agents_graph") or not compiles(graph_path, "agents_graph"):
        return

    case_path = REPORTS_DIR / "cases" / "schema_input.json"
    if not file_exists(case_path, "schema_input"):
        return
    case = json.loads(case_path.read_text())

    script = (
        "import json,sys;"
        f"sys.path.insert(0,{str(CODE_DIR)!r});"
        f"sys.path.insert(0,{str(REPO_ROOT / 'src')!r});"
        "from agents_graph import run_graph;"
        f"r=run_graph({case['title']!r},{case['content']!r},turn_ceiling=4);"
        "print('RESULT_JSON:'+json.dumps(r))"
    )
    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, "-c", script],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=GRAPH_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        check("graph:completes_without_hanging", False, f"still running after {GRAPH_TIMEOUT_S}s")
        return

    elapsed = int((time.time() - t0) * 1000)
    if proc.returncode != 0:
        check("graph:completes_without_hanging", False,
              f"exit {proc.returncode}: {proc.stderr.strip()[-300:]}")
        return
    check("graph:completes_without_hanging", True, f"{elapsed} ms")

    line = next((l for l in proc.stdout.splitlines() if l.startswith("RESULT_JSON:")), None)
    if not line:
        check("graph:returns_result", False, "no RESULT_JSON in output")
        return
    result = json.loads(line[len("RESULT_JSON:"):])
    check("graph:returns_result", True)

    check("graph:respected_turn_ceiling", result["turn_count"] <= result["turn_ceiling"],
          f"turn_count={result['turn_count']} ceiling={result['turn_ceiling']}")
    check("graph:made_at_least_one_attempt", result["planner_attempts"] >= 1,
          f"attempts={result['planner_attempts']}")

    # Behavioral, not textual: if it validated, it must carry exactly 3 tags.
    if result["valid"]:
        check("graph:valid_run_has_exactly_3_tags", len(result["tags"]) == 3,
              f"tags={result['tags']}")
        words = len(result["summary"].split())
        check("graph:valid_run_summary_within_25_words", 0 < words <= 25, f"words={words}")
    else:
        check("graph:invalid_run_recorded_reason", bool(result["validation_history"]),
              "abandoned at ceiling with recorded validation errors")


def check_model_client_routing():
    """Part 3 requires node LLM calls to go through src/model_client.py.

    Checked statically rather than at runtime: a direct ChatOllama call inside a
    node would still produce correct-looking output, so only reading the source
    can show the requirement is met.
    """
    graph_path = CODE_DIR / "agents_graph.py"
    if not graph_path.exists():
        check("routing:agents_graph_present", False, "file missing")
        return
    source = graph_path.read_text()

    banned = ["ChatOllama(", "make_llm(", "ollama.Client", "langchain_ollama"]
    found = [token for token in banned if token in source]
    check("routing:no_direct_model_calls", not found, f"found {found}" if found else "")

    calls = [ln.strip() for ln in source.splitlines() if ".complete(" in ln]
    routed = [c for c in calls if 'state["llm"].complete(' in c]
    check("routing:all_llm_calls_via_model_client",
          bool(calls) and len(routed) == len(calls),
          f"{len(routed)}/{len(calls)} call sites use state['llm'].complete()")


def check_schema_module():
    """The Pydantic validator must accept a good record and reject each bad shape."""
    sys.path.insert(0, str(REPO_ROOT / "src"))
    try:
        from schemas import validate_planner_output
    except Exception as e:
        check("schemas:importable", False, e)
        return
    check("schemas:importable", True)

    good = {"tags": ["bus delay", "transit reliability", "rider impact"],
            "summary": "A morning bus never arrived and riders waited forty minutes without any announcement."}
    ok, _, err = validate_planner_output(good)
    check("schemas:accepts_valid", ok, err)

    bad_cases = {
        "two_tags": {"tags": ["a bus delay", "transit"], "summary": "Short summary."},
        "four_tags": {"tags": ["one", "two", "three", "four"], "summary": "Short summary."},
        "short_tag": {"tags": ["ab", "transit reliability", "rider impact"], "summary": "Short."},
        "long_summary": {"tags": ["bus delay", "transit reliability", "rider impact"],
                         "summary": " ".join(["word"] * 26)},
    }
    for label, payload in bad_cases.items():
        ok, _, _ = validate_planner_output(payload)
        check(f"schemas:rejects_{label}", not ok)


def git_commit_hash() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-graph", action="store_true",
                    help="skip the live LLM run (static + HTTP checks only)")
    args = ap.parse_args()

    print("=== Static files ===")
    file_exists(WEBAPP_DIR / "HW1-PragnayaPriyadarshini.html", "html")
    file_exists(WEBAPP_DIR / "styles.css", "styles_css")
    file_exists(WEBAPP_DIR / "hw1.js", "hw1_js")

    # Part 1 lives in the stylesheet now, so assert its rules are actually there.
    css_path = WEBAPP_DIR / "styles.css"
    if css_path.exists():
        css = css_path.read_text()
        check("css:responsive_breakpoint", "max-width: 480px" in css, "covers 375px")
        check("css:wraps_long_text", "overflow-wrap: anywhere" in css,
              "prevents horizontal scroll at 375px")
        for state in ("state-loading", "state-empty", "state-error"):
            check(f"css:{state}_styled", f".{state}" in css)
    file_exists(REPO_ROOT / "DOMAIN_SCHEMA.md", "domain_schema")
    file_exists(REPO_ROOT / "requirements.txt", "requirements")
    compiles(REPO_ROOT / "src" / "model_client.py", "model_client")
    compiles(REPO_ROOT / "src" / "schemas.py", "schemas")
    compiles(CODE_DIR / "run_schema_experiments.py", "run_schema_experiments")

    print("\n=== Part 3 model-client routing ===")
    check_model_client_routing()

    print("\n=== Part 4 schema validator ===")
    check_schema_module()

    print("\n=== Ollama ===")
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as resp:
            names = [m["name"] for m in json.loads(resp.read()).get("models", [])]
        check("ollama:reachable", True)
        check("ollama:model_pulled", any(MODEL in n for n in names), str(names))
    except Exception as e:
        check("ollama:reachable", False, e)

    print("\n=== Part 2 FastAPI ===")
    check_fastapi()

    if args.skip_graph:
        print("\n=== Part 3/4 graph (skipped) ===")
    else:
        print("\n=== Part 3/4 graph ===")
        check_graph()

    result = {
        "homework": "HW2",
        "sid4": SID4,
        "commit_hash": git_commit_hash(),
        "model": MODEL,
        "configuration": {
            "port_base": PORT_BASE,
            "prefix": PREFIX,
            "domain_id": DOMAIN_ID,
            "temperature": 0.0,
            "ollama_url": OLLAMA_URL,
        },
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_checks": len(checks),
        "passed": sum(1 for c in checks if c["passed"]),
        "failed": sum(1 for c in checks if not c["passed"]),
        "checks": checks,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORTS_DIR / "verification.json"
    out_path.write_text(json.dumps(result, indent=2))

    print(f"\n{result['passed']}/{result['total_checks']} checks passed")
    print(f"Written to: {out_path}")
    sys.exit(0 if result["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
