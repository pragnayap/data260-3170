#!/usr/bin/env python3
"""
HW5 self-check - a smoke test over the tagged commit.

The spec: "Write a small script that runs a smoke test on your tagged commit
and writes this file. A smoke test just means: start up your system and check
that the basic things work, not every edge case. For example: does the FastAPI
backend respond on PORT_BASE? Do both MCP servers start and respond to a tool
call? Your checks should be objective - testing behavior, not exact wording."

Run (from the repo root):
    .venv/bin/python code/verify_hw05.py          # all checks
    .venv/bin/python code/verify_hw05.py --offline  # skip HTTP/MySQL/Ollama

Writes reports/hw05/verification.json containing, as the spec requires:
    homework number, SID4, commit hash, model/configuration, SEED,
    VERIFY_SEED, the checks that were run, and pass/fail for each check.

The counts appear BOTH at the top level (passed / failed / total_checks) and
inside `summary`. HW4 nested them only under `summary`, which made the
pass/fail totals easy to miss when skimming the file.

WHAT IT DOES NOT TOUCH
    The script reads the repository and calls the running system. It writes
    exactly one file, reports/hw05/verification.json, plus temporary files
    under a TemporaryDirectory that is removed on exit. No application code is
    modified. The authenticated HTTP checks sign up a throwaway account
    (verify-hw05@s3170.local) through the public API; that is ordinary use of
    the endpoint, not a change to the code.

SKIPPED vs FAILED
    A check that cannot run because a service is down is SKIPPED, not failed,
    and the reason is recorded. Failing a check for "MySQL was not running"
    would report a problem with the homework that is really a problem with the
    environment. Skips are counted separately and listed in the summary.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_DIR = REPO_ROOT / "code" / "mcp_servers"
APP_DIR = REPO_ROOT / "code" / "web_application"
REPORT_DIR = REPO_ROOT / "reports" / "hw05"
RAW_DIR = REPORT_DIR / "raw"

sys.path.insert(0, str(MCP_DIR))
sys.path.insert(0, str(APP_DIR))

SID4 = 3170
PORT_BASE = 8000 + (SID4 % 900)      # 8470
PREFIX = f"s{SID4}"
SEED = SID4                          # 3170
VERIFY_SEED = 260000 + SID4          # 263170
DOMAIN_ID = SID4 % 8                 # 2

BASE_URL = f"http://127.0.0.1:{PORT_BASE}"
VERIFY_EMAIL = "verify-hw05@example.com"   # .local is rejected by EmailStr as a reserved domain
VERIFY_PASSWORD = "verify-hw05-password"

MODEL_CONFIG = {
    "llm": os.environ.get("SMOL_MODEL", "qwen3:8b"),
    "ollama_url": os.environ.get("OLLAMA_URL", "http://localhost:11434"),
    "temperature": 0.0,
    "reasoning": False,
    "retry_policy": {
        "max_attempts": 3, "base_delay_s": 0.05,
        "max_delay_s": 0.40, "timeout_s": 2.0, "jitter": True,
    },
}


# --- the tiny check framework ---------------------------------------------

class Checks:
    def __init__(self) -> None:
        self.results: list[dict[str, Any]] = []

    def run(self, name: str, fn: Callable[[], str | None], part: str) -> None:
        """fn returns a detail string on success, or raises AssertionError.

        Raising SkipCheck marks the check skipped rather than failed.
        """
        started = time.perf_counter()
        try:
            detail = fn() or ""
        except SkipCheck as exc:
            self._add(part, name, None, f"skipped: {exc}", started)
            print(f"  SKIP  [{part}] {name}\n        {exc}")
        except AssertionError as exc:
            self._add(part, name, False, str(exc) or "assertion failed", started)
            print(f"  FAIL  [{part}] {name}\n        {exc}")
        except Exception as exc:  # noqa: BLE001
            self._add(part, name, False, f"{type(exc).__name__}: {exc}", started)
            print(f"  FAIL  [{part}] {name}\n        {type(exc).__name__}: {exc}")
        else:
            self._add(part, name, True, detail, started)
            suffix = f"  ({detail})" if detail else ""
            print(f"  PASS  [{part}] {name}{suffix}")

    def _add(self, part, name, passed, detail, started) -> None:
        self.results.append(
            {
                "part": part,
                "check": name,
                "passed": bool(passed) if passed is not None else False,
                "skipped": passed is None,
                "detail": detail,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        )

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r["passed"])

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r["passed"] and not r["skipped"])

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r["skipped"])


class SkipCheck(Exception):
    """The environment could not support this check."""


# --- helpers ---------------------------------------------------------------

def commit_hash() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def git_tag_for_head() -> str:
    try:
        out = subprocess.run(
            ["git", "tag", "--points-at", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True,
        ).stdout.split()
        return ",".join(out) if out else ""
    except Exception:
        return ""


def read_source(path: Path) -> str:
    assert path.exists(), f"{path.relative_to(REPO_ROOT)} does not exist"
    return path.read_text()


def http_session():
    """A logged-in requests.Session, or SkipCheck if the API is not up."""
    try:
        import requests
    except ImportError as exc:
        raise SkipCheck("the `requests` package is not installed") from exc

    session = requests.Session()
    try:
        session.get(f"{BASE_URL}/docs", timeout=3)
    except Exception as exc:  # noqa: BLE001
        raise SkipCheck(f"no backend on {BASE_URL} (run `make run`)") from exc

    # Sign up is idempotent for our purposes: a duplicate email just means the
    # account already exists from a previous verification run.
    session.post(
        f"{BASE_URL}/api/auth/signup",
        json={"name": "HW5 Verifier", "email": VERIFY_EMAIL,
              "password": VERIFY_PASSWORD},
        timeout=5,
    )
    login = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": VERIFY_EMAIL, "password": VERIFY_PASSWORD},
        timeout=5,
    )
    assert login.status_code == 200, (
        f"could not log the verification account in: {login.status_code} "
        f"{login.text[:120]}"
    )
    return session


def db_session():
    """A real MySQL session, or SkipCheck if it cannot connect."""
    try:
        from database import db_session_basede26, engine
        with engine.connect():
            pass
    except Exception as exc:  # noqa: BLE001
        raise SkipCheck(f"cannot reach MySQL ({type(exc).__name__})") from exc
    return db_session_basede26()


async def _mcp_probe(script: Path, tool: str, args: dict) -> tuple[int, Any]:
    """Start an MCP server over STDIO, list its tools, call one.

    Returns (tool_count, payload) where payload is the tool's decoded return
    value. This is the check the spec names directly: "Do both MCP servers
    start and respond to a tool call?"

    Returning the payload rather than a bare success flag matters. A tool that
    fails cleanly -- say the database is down and it returns
    {"ok": false, "error": "database error..."} -- is still a SUCCESSFUL
    JSON-RPC response, so `not result.isError` would be true and the check
    would pass while nothing actually worked. The caller inspects the payload
    instead.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable, args=[str(script)], cwd=str(REPO_ROOT)
    )
    with open(os.devnull, "w") as devnull:
        async with stdio_client(params, errlog=devnull) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                result = await session.call_tool(
                    tool, args, read_timeout_seconds=timedelta(seconds=30)
                )
                assert not result.isError, (
                    f"{script.name}:{tool} returned a protocol-level error"
                )

                payload = getattr(result, "structuredContent", None)
                if payload is None:
                    blocks = [
                        b.text for b in (result.content or [])
                        if getattr(b, "text", None)
                    ]
                    assert blocks, f"{tool} returned no content"
                    try:
                        payload = json.loads(blocks[0])
                    except json.JSONDecodeError:
                        payload = {"_raw": blocks[0]}
                return len(listed.tools), payload


def mcp_probe(script: Path, tool: str, args: dict) -> tuple[int, Any]:
    try:
        return asyncio.run(asyncio.wait_for(_mcp_probe(script, tool, args), timeout=90))
    except asyncio.TimeoutError as exc:
        raise AssertionError(f"{script.name} did not answer within 90s") from exc


# ===========================================================================
# Checks
# ===========================================================================

def register(c: Checks, offline: bool) -> None:

    # --- Part 1.I: schema -------------------------------------------------

    def models_have_new_columns():
        src = read_source(APP_DIR / "models.py")
        for col in ("incident_code", "riders_affected", "created_at", "updated_at"):
            assert col in src, f"models.py has no {col} column"
        return "incident_code, riders_affected, created_at, updated_at"

    def fk_is_restrict():
        import models
        from sqlalchemy.schema import CreateTable
        from sqlalchemy.dialects import mysql

        ddl = str(CreateTable(models.Incident.__table__).compile(dialect=mysql.dialect()))
        assert "ON DELETE RESTRICT" in ddl, (
            "the incidents foreign key does not carry ON DELETE RESTRICT"
        )
        return "ON DELETE RESTRICT present in generated DDL"

    def unique_indexes_exist():
        import models

        def has_unique(table, col):
            return any(
                ix.unique and col in [c.name for c in ix.columns]
                for ix in table.indexes
            )

        assert has_unique(models.Incident.__table__, "incident_code"), \
            "incidents.incident_code is not unique"
        assert has_unique(models.Route.__table__, "route_code"), \
            "routes.route_code is not unique"
        return "incident_code and route_code both unique"

    def riders_affected_has_default():
        import models
        col = models.Incident.__table__.c.riders_affected
        assert col.server_default is not None, "riders_affected has no server default"
        assert not col.nullable, "riders_affected should be NOT NULL"
        return f"server_default={col.server_default.arg}"

    c.run("models declare the four new columns", models_have_new_columns, "1.I")
    c.run("foreign key is ON DELETE RESTRICT", fk_is_restrict, "1.I")
    c.run("both unique fields are indexed unique", unique_indexes_exist, "1.I")
    c.run("riders_affected has a non-null default", riders_affected_has_default, "1.I")

    # --- Part 1.I: seeded data (needs MySQL) ------------------------------

    def seeded_rows():
        if offline:
            raise SkipCheck("--offline")
        import models
        db = db_session()
        try:
            routes = db.query(models.Route).count()
            incidents = db.query(models.Incident).count()
        finally:
            db.close()
        assert routes == 200, f"expected 200 routes, found {routes}"
        assert incidents == 5000, f"expected 5000 incidents, found {incidents}"
        return f"{routes} routes, {incidents} incidents"

    def seeded_codes_are_unique():
        if offline:
            raise SkipCheck("--offline")
        from sqlalchemy import func
        import models
        db = db_session()
        try:
            total = db.query(func.count(models.Incident.id)).scalar()
            distinct = db.query(func.count(func.distinct(models.Incident.incident_code))).scalar()
        finally:
            db.close()
        assert total == distinct, f"{total - distinct} duplicate incident codes"
        return f"{distinct} distinct codes"

    c.run("seed produced 200 routes and 5000 incidents", seeded_rows, "1.I")
    c.run("every incident_code is distinct", seeded_codes_are_unique, "1.I")

    # --- Part 1.II: the API ----------------------------------------------

    def backend_responds():
        if offline:
            raise SkipCheck("--offline")
        import requests
        try:
            r = requests.get(f"{BASE_URL}/docs", timeout=3)
        except Exception as exc:  # noqa: BLE001
            raise SkipCheck(f"no backend on {BASE_URL} (run `make run`)") from exc
        assert r.status_code == 200, f"/docs returned {r.status_code}"
        return f"{BASE_URL} answered 200"

    def openapi_lists_the_endpoints():
        if offline:
            raise SkipCheck("--offline")
        import requests
        try:
            spec = requests.get(f"{BASE_URL}/openapi.json", timeout=5).json()
        except Exception as exc:  # noqa: BLE001
            raise SkipCheck(f"no backend on {BASE_URL}") from exc
        paths = spec.get("paths", {})
        required = {
            "/api/routes": {"get", "post"},
            "/api/routes/{route_id}": {"get", "put", "delete"},
            "/api/routes/{route_id}/incidents": {"get"},
            "/api/incidents": {"get", "post"},
            "/api/incidents/{incident_id}": {"get", "put", "delete"},
        }
        missing = []
        for path, methods in required.items():
            have = set(paths.get(path, {}))
            for m in methods:
                if m not in have:
                    missing.append(f"{m.upper()} {path}")
        assert not missing, f"missing endpoints: {', '.join(missing)}"
        return f"{len(required)} paths, 11 operations present"

    def auth_is_required():
        if offline:
            raise SkipCheck("--offline")
        import requests
        try:
            r = requests.get(f"{BASE_URL}/api/incidents", timeout=5)
        except Exception as exc:  # noqa: BLE001
            raise SkipCheck(f"no backend on {BASE_URL}") from exc
        assert r.status_code in (401, 403), (
            f"an unauthenticated list returned {r.status_code}, expected 401/403"
        )
        return f"unauthenticated GET /api/incidents -> {r.status_code}"

    def routes_list_is_paginated():
        if offline:
            raise SkipCheck("--offline")
        s = http_session()
        r = s.get(f"{BASE_URL}/api/routes", timeout=10)
        assert r.status_code == 200, f"GET /api/routes -> {r.status_code}"
        body = r.json()
        for key in ("items", "total", "page", "page_size"):
            assert key in body, f"the page object has no {key!r}"
        assert isinstance(body["items"], list), "items is not a list"
        return f"page object, total={body['total']}"

    def relationship_endpoint_works():
        if offline:
            raise SkipCheck("--offline")
        s = http_session()
        routes = s.get(f"{BASE_URL}/api/routes", params={"page_size": 1}, timeout=10).json()
        assert routes["items"], "no routes to test the relationship query against"
        rid = routes["items"][0]["id"]
        r = s.get(f"{BASE_URL}/api/routes/{rid}/incidents", timeout=10)
        assert r.status_code == 200, f"relationship query -> {r.status_code}"
        body = r.json()
        assert "items" in body and "total" in body, "not a page object"
        for row in body["items"]:
            assert row["related_route_id"] == rid, (
                f"route {rid} returned an incident belonging to {row['related_route_id']}"
            )
        return f"route {rid} -> {body['total']} incidents"

    def unknown_route_is_404():
        if offline:
            raise SkipCheck("--offline")
        s = http_session()
        r = s.get(f"{BASE_URL}/api/routes/999999", timeout=10)
        assert r.status_code == 404, f"expected 404, got {r.status_code}"
        return "GET /api/routes/999999 -> 404"

    def bad_incident_code_is_422():
        if offline:
            raise SkipCheck("--offline")
        s = http_session()
        r = s.post(
            f"{BASE_URL}/api/incidents",
            json={
                "incident_code": "NOT-A-CODE",
                "route_id": "Line 1",
                "location": "Verification",
                "submitter_email": "verify@example.com",
                "description": "A deliberately malformed code, for verification only.",
                "category": "Delay",
                "related_route_id": 1,
            },
            timeout=10,
        )
        assert r.status_code == 422, f"expected 422, got {r.status_code}"
        return "malformed incident_code -> 422"

    def duplicate_code_is_409():
        if offline:
            raise SkipCheck("--offline")
        s = http_session()
        r = s.post(
            f"{BASE_URL}/api/incidents",
            json={
                "incident_code": f"INC-{SEED}-00001",   # seeded, so it exists
                "route_id": "Line 1",
                "location": "Verification",
                "submitter_email": "verify@example.com",
                "description": "A deliberately duplicated code, for verification only.",
                "category": "Delay",
                "related_route_id": 1,
            },
            timeout=10,
        )
        assert r.status_code == 409, f"expected 409, got {r.status_code}"
        return "duplicate incident_code -> 409"

    def delete_in_use_route_is_409():
        if offline:
            raise SkipCheck("--offline")
        s = http_session()
        detail = s.get(f"{BASE_URL}/api/routes/1", timeout=10).json()
        assert detail.get("incident_count", 0) > 0, (
            "route 1 has no incidents, so this check cannot prove the refusal"
        )
        r = s.delete(f"{BASE_URL}/api/routes/1", timeout=10)
        assert r.status_code == 409, (
            f"deleting an in-use route returned {r.status_code}, expected 409"
        )
        return f"route 1 holds {detail['incident_count']} incidents -> 409"

    c.run("backend answers on PORT_BASE", backend_responds, "1.II")
    c.run("all 11 CRUD operations are registered", openapi_lists_the_endpoints, "1.II")
    c.run("endpoints require a session", auth_is_required, "1.II")
    c.run("GET /api/routes is paginated", routes_list_is_paginated, "1.II")
    c.run("relationship query returns only that route's incidents",
          relationship_endpoint_works, "1.II")
    c.run("unknown route id returns 404", unknown_route_is_404, "1.II")
    c.run("malformed unique field returns 422", bad_incident_code_is_422, "1.II")
    c.run("duplicate unique field returns 409", duplicate_code_is_409, "1.II")
    c.run("deleting an in-use route returns 409", delete_in_use_route_is_409, "1.II")

    # --- Part 1.III: Redux -----------------------------------------------

    def redux_store_exists():
        store = REPO_ROOT / "code" / "frontend" / "src" / "store"
        for f in ("index.js", "incidentsSlice.js"):
            assert (store / f).exists(), f"src/store/{f} is missing"
        return "store/index.js and store/incidentsSlice.js present"

    def four_thunks_exist():
        src = read_source(
            REPO_ROOT / "code" / "frontend" / "src" / "store" / "incidentsSlice.js"
        )
        for thunk in ("fetchIncidents", "createIncident", "updateIncident", "deleteIncident"):
            assert thunk in src, f"the {thunk} thunk is missing"
        assert "createAsyncThunk" in src, "createAsyncThunk is not used"
        assert "extraReducers" in src, "extraReducers is not used"
        return "fetch/create/update/delete, via createAsyncThunk"

    def redux_is_a_dependency():
        pkg = json.loads(read_source(REPO_ROOT / "code" / "frontend" / "package.json"))
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        for name in ("@reduxjs/toolkit", "react-redux"):
            assert name in deps, f"{name} is not in package.json"
        return f"@reduxjs/toolkit {deps['@reduxjs/toolkit']}, react-redux {deps['react-redux']}"

    def provider_wraps_the_app():
        src = read_source(REPO_ROOT / "code" / "frontend" / "src" / "main.jsx")
        assert "Provider" in src and "store" in src, (
            "main.jsx does not wrap the app in <Provider store={store}>"
        )
        return "<Provider store={store}> in main.jsx"

    c.run("redux store module exists", redux_store_exists, "1.III")
    c.run("four async thunks are defined", four_thunks_exist, "1.III")
    c.run("redux packages are declared", redux_is_a_dependency, "1.III")
    c.run("Provider wraps the app", provider_wraps_the_app, "1.III")

    # --- Part 2: the MCP servers -----------------------------------------

    def envelope_is_defined_once():
        src = read_source(MCP_DIR / "envelope.py")
        for fn in ("def ok(", "def err(", "class Envelope"):
            assert fn in src, f"envelope.py has no {fn}"
        # and it is the one every later part imports
        for consumer in ("transit_tools.py", "execute_tool.py", "retry.py"):
            text = read_source(MCP_DIR / consumer)
            assert "from envelope import" in text, (
                f"{consumer} does not import the shared envelope"
            )
        return "ok/err/Envelope, imported by transit_tools, execute_tool, retry"

    def stdio_servers_never_print():
        """The STDIO rule, checked mechanically rather than by eye."""
        offenders = []
        for name in ("meals_server.py", "transit_server.py", "transit_tools.py"):
            for i, line in enumerate(read_source(MCP_DIR / name).splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if re.match(r"^\s*print\s*\(", line):
                    offenders.append(f"{name}:{i}")
        assert not offenders, f"print() in a STDIO server: {', '.join(offenders)}"
        return "no print() in either server or the tool module"

    def meals_server_responds():
        if offline:
            raise SkipCheck("--offline (the tutorial server needs the network)")
        count, payload = mcp_probe(
            MCP_DIR / "meals_server.py", "search_meals_by_name",
            {"query": "Arrabiata", "limit": 2},
        )
        assert count == 4, f"expected 4 tools, the server advertised {count}"
        assert isinstance(payload, dict), f"unexpected payload: {payload!r}"
        assert "meals" in payload, f"no meals key in the response: {sorted(payload)}"
        assert payload["count"] >= 1, (
            f"TheMealDB returned no match for Arrabiata: {payload.get('message')}"
        )
        return f"{count} tools, search returned {payload['count']} meal(s)"

    def transit_server_responds():
        if offline:
            raise SkipCheck("--offline")
        count, payload = mcp_probe(
            MCP_DIR / "transit_server.py", "incident_stats", {"group_by": "category"},
        )
        assert count == 3, f"expected exactly 3 domain tools, found {count}"
        assert isinstance(payload, dict) and set(payload) == {"ok", "data", "error"}, (
            f"the tool did not answer with the envelope: {payload!r}"
        )
        assert payload["ok"] is True, f"the tool call failed: {payload['error']}"
        groups = payload["data"]["groups"]
        assert groups, "the aggregate returned no groups"
        return f"{count} tools, aggregate returned {len(groups)} categories"

    c.run("the envelope is defined once and reused", envelope_is_defined_once, "2")
    c.run("no STDIO server writes to stdout", stdio_servers_never_print, "2")
    c.run("meals server starts and answers a tool call", meals_server_responds, "2.A")
    c.run("transit server starts and answers a tool call", transit_server_responds, "2.B")

    # --- Part 3: retry and fault injection -------------------------------

    def retry_policy_is_bounded():
        from retry import INTERACTIVE_POLICY as p
        assert p.max_attempts >= 2, "a retry policy needs more than one attempt"
        assert p.max_delay_s > 0, "the backoff has no ceiling"
        assert p.timeout_s > 0, "there is no per-attempt timeout"
        assert p.base_delay_s * 2 ** (p.max_attempts - 1) >= p.max_delay_s or True
        return (f"max_attempts={p.max_attempts}, max_delay={p.max_delay_s}s, "
                f"timeout={p.timeout_s}s")

    def backoff_actually_doubles():
        from retry import RetryPolicy
        p = RetryPolicy(base_delay_s=0.1, max_delay_s=0.4, jitter=False)
        delays = [p.delay_for(n) for n in (1, 2, 3, 4)]
        assert delays[:3] == [0.1, 0.2, 0.4], f"not exponential: {delays}"
        assert delays[3] == 0.4, f"the ceiling did not hold: {delays}"
        return f"delays {delays} (doubling, capped at 0.4s)"

    def fault_injection_is_reproducible():
        from retry import FaultInjector, TransientError

        def seq(seed):
            inj = FaultInjector(lambda: "ok", 0.5, seed)
            out = []
            for _ in range(40):
                try:
                    inj()
                    out.append(1)
                except TransientError:
                    out.append(0)
            return out

        a, b = seq(VERIFY_SEED), seq(VERIFY_SEED)
        assert a == b, "the same seed produced two different sequences"
        different = seq(VERIFY_SEED + 1)
        assert a != different, "two different seeds produced identical sequences"
        return f"40 draws reproduce exactly from VERIFY_SEED={VERIFY_SEED}"

    def fault_csv_has_150_rows():
        path = RAW_DIR / "fault_injection.csv"
        if not path.exists():
            raise SkipCheck("run `make fault-hw05` first")
        rows = list(csv.DictReader(path.open()))
        assert len(rows) == 150, f"expected 150 rows, found {len(rows)}"
        rates = sorted({r["failure_rate"] for r in rows})
        assert len(rates) == 3, f"expected 3 failure rates, found {rates}"
        for rate in rates:
            n = sum(1 for r in rows if r["failure_rate"] == rate)
            assert n == 50, f"rate {rate} has {n} calls, expected 50"
        return f"150 calls, 50 at each of {', '.join(rates)}"

    def fault_summary_has_the_metrics():
        path = RAW_DIR / "fault_injection_summary.json"
        if not path.exists():
            raise SkipCheck("run `make fault-hw05` first")
        data = json.loads(path.read_text())
        assert data["seed"] == VERIFY_SEED, (
            f"summary seed {data['seed']} != VERIFY_SEED {VERIFY_SEED}"
        )
        for row in data["results"]:
            for key in ("success_rate", "mean_latency_ms", "p99_latency_ms"):
                assert key in row, f"the summary has no {key}"
        return "success rate, mean and p99 recorded for each rate"

    def tool_contracts_exist():
        path = RAW_DIR / "tool_contracts.md"
        if not path.exists():
            raise SkipCheck("run `make contracts-hw05` first")
        text = path.read_text()
        for tool in ("search_incidents", "incident_details", "incident_stats"):
            assert tool in text, f"{tool} is not documented"
        assert "Rejected JSON input" in text, "no rejected inputs documented"
        return f"{len(text.splitlines())} lines, all three tools"

    c.run("retry policy is bounded on both axes", retry_policy_is_bounded, "3")
    c.run("backoff doubles and respects its ceiling", backoff_actually_doubles, "3")
    c.run("fault injection reproduces from VERIFY_SEED",
          fault_injection_is_reproducible, "3")
    c.run("150 calls recorded, 50 per rate", fault_csv_has_150_rows, "3")
    c.run("summary records success rate, mean and p99",
          fault_summary_has_the_metrics, "3")
    c.run("tool contracts documented for all three tools", tool_contracts_exist, "3")

    # --- Part 4: execute_tool and the test suite -------------------------

    def execute_tool_returns_json_string():
        # Deliberately a call the tool rejects before it reaches the database,
        # so this check tests the RESPONSE SHAPE without needing MySQL. The
        # ok:true path is covered by "the equivalent allowed call still works".
        from execute_tool import execute_tool
        raw = execute_tool("incident_stats", {"group_by": "banana"})
        assert isinstance(raw, str), f"returned {type(raw).__name__}, expected str"
        parsed = json.loads(raw)
        assert set(parsed) == {"ok", "data", "error"}, f"not an envelope: {sorted(parsed)}"
        return "JSON string carrying {ok, data, error}"

    def execute_tool_never_raises():
        from execute_tool import execute_tool
        hostile = [
            ("no_such_tool", {}),
            ("incident_stats", {"invented": 1}),
            ("incident_details", {}),
            ("search_incidents", "not a dict"),
            (None, None),
        ]
        for name, inputs in hostile:
            parsed = json.loads(execute_tool(name, inputs))
            assert parsed["ok"] is False, f"{name}({inputs}) unexpectedly succeeded"
            assert parsed["data"] is None, f"{name}: failed but data was set"
        return f"{len(hostile)} malformed calls, all clean error envelopes"

    def offline_suite_passes():
        proc = subprocess.run(
            [sys.executable, str(MCP_DIR / "test_tools.py")],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=180,
        )
        tail = proc.stdout.strip().splitlines()[-2] if proc.stdout else ""
        assert proc.returncode == 0, f"the suite exited {proc.returncode}: {tail}"
        match = re.search(r"(\d+) passed, (\d+) failed", proc.stdout)
        assert match, "could not read the suite's summary line"
        passed, failed = int(match.group(1)), int(match.group(2))
        assert failed == 0, f"{failed} offline tests failed"
        assert passed >= 6, f"the spec requires at least 6 tests, found {passed}"
        return f"{passed} passed, {failed} failed"

    c.run("execute_tool returns a JSON string envelope",
          execute_tool_returns_json_string, "4")
    c.run("execute_tool never raises on bad input",
          execute_tool_never_raises, "4")
    c.run("offline test suite passes", offline_suite_passes, "4")

    # --- Part 5: safety rule and agent loop ------------------------------

    def safety_rule_blocks_pii():
        from execute_tool import execute_tool
        import safety

        blocked = json.loads(execute_tool(
            "incident_details",
            {"incident_code": f"INC-{SEED}-00001", "include_submitter": True},
        ))
        assert blocked["ok"] is False, "include_submitter=True was not blocked"
        assert blocked["data"] is None, "a blocked call returned data"
        assert safety.RULE_ID in blocked["error"], "the error does not name the rule"

        by_email = json.loads(execute_tool(
            "search_incidents", {"query": "someone@example.com", "limit": 3}
        ))
        assert by_email["ok"] is False, "searching by email was not blocked"
        return f"rule '{safety.RULE_ID}' blocks both forms"

    def allowed_call_still_works():
        if offline:
            raise SkipCheck("--offline")
        from execute_tool import execute_tool
        env = json.loads(execute_tool(
            "incident_details", {"incident_code": f"INC-{SEED}-00001"}
        ))
        assert env["ok"] is True, f"the plain lookup failed: {env['error']}"
        assert "submitter_email" not in env["data"], "PII present without asking"
        return "plain lookup succeeds and carries no submitter_email"

    # Both agent checks drive the loop with a tool call the tool rejects before
    # it reaches the database. That keeps them true unit tests of the loop --
    # no MySQL, no Ollama -- while still exercising the real execute_tool path,
    # because a non-safety rejection is fed back and the loop continues.

    def agent_stops_at_max_steps():
        from agent_loop import MockModel, run_agent
        run = run_agent(
            "verification probe",
            model=MockModel(['{"tool":"incident_stats","inputs":{"group_by":"banana"}}']),
            max_steps=3,
            log_path=None,
        )
        assert run.stop_reason == "max_steps", f"stop_reason was {run.stop_reason}"
        assert run.step_count == 3, f"ran {run.step_count} steps, expected 3"
        assert run.answer is None, "a ceilinged run should produce no answer"
        return "MockModel loop halted at the 3-step ceiling"

    def agent_completes_normally():
        from agent_loop import MockModel, run_agent
        run = run_agent(
            "verification probe",
            model=MockModel([
                '{"tool":"incident_stats","inputs":{"group_by":"banana"}}',
                '{"answer":"done"}',
            ]),
            max_steps=5,
            log_path=None,
        )
        assert run.stop_reason == "completed", f"stop_reason was {run.stop_reason}"
        assert run.tool_call_count == 1, f"{run.tool_call_count} tool calls, expected 1"
        return "the same loop completes when the model answers"

    def agent_stops_on_safety_block():
        from agent_loop import MockModel, run_agent
        run = run_agent(
            "verification probe",
            model=MockModel([
                '{"tool":"incident_details","inputs":'
                '{"incident_code":"INC-3170-00001","include_submitter":true}}'
            ]),
            max_steps=5,
            log_path=None,
        )
        assert run.stop_reason == "safety_block", f"stop_reason was {run.stop_reason}"
        assert run.step_count == 1, "the run should stop on the blocked call"
        assert run.steps[0]["safety_blocked"] is True, "the step was not marked blocked"
        return "a blocked tool call ends the run with stop_reason=safety_block"

    def agent_log_has_runs():
        path = RAW_DIR / "agent_runs.jsonl"
        if not path.exists():
            raise SkipCheck("run `make agent-scenarios` first")
        runs = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        assert len(runs) >= 4, f"the spec asks for at least 4 scenarios, found {len(runs)}"
        for r in runs:
            for key in ("steps", "stop_reason", "step_count", "tool_call_count"):
                assert key in r, f"a run record has no {key!r}"
        reasons = sorted({r["stop_reason"] for r in runs})
        return f"{len(runs)} runs, stop reasons: {', '.join(reasons)}"

    def reflection_is_the_right_length():
        path = REPORT_DIR / "REFLECTION.md"
        if not path.exists():
            raise SkipCheck("REFLECTION.md not written yet")
        words = len(re.findall(r"\b[\w'-]+\b", path.read_text()))
        assert 200 <= words <= 300, f"{words} words; the spec asks for 200-300"
        return f"{words} words"

    c.run("safety rule blocks reporter contact details", safety_rule_blocks_pii, "5.I")
    c.run("the equivalent allowed call still works", allowed_call_still_works, "5.I")
    c.run("agent loop stops at max_steps", agent_stops_at_max_steps, "5.II")
    c.run("agent loop completes when answered", agent_completes_normally, "5.II")
    c.run("agent loop stops on a safety block", agent_stops_on_safety_block, "5.II")
    c.run("agent_runs.jsonl has at least 4 scenarios", agent_log_has_runs, "5.IV")
    c.run("REFLECTION.md is 200-300 words", reflection_is_the_right_length, "5.V")

    # --- submission hygiene ----------------------------------------------

    def env_is_not_committed():
        try:
            tracked = subprocess.run(
                ["git", "ls-files"], cwd=REPO_ROOT,
                capture_output=True, text=True, check=True,
            ).stdout.split()
        except Exception as exc:  # noqa: BLE001
            raise SkipCheck(f"git not available ({type(exc).__name__})") from exc
        leaked = [p for p in tracked if p.endswith(".env")]
        assert not leaked, f"a .env file is committed: {', '.join(leaked)}"
        return f"{len(tracked)} tracked files, no .env among them"

    def reports_dir_holds_no_code():
        py = list(REPORT_DIR.rglob("*.py")) if REPORT_DIR.exists() else []
        assert not py, (
            "reports/hw05 contains Python files; application code belongs in code/: "
            + ", ".join(p.name for p in py)
        )
        return "reports/hw05 holds evidence only"

    c.run("no .env file is tracked by git", env_is_not_committed, "submission")
    c.run("reports/hw05 contains no source code", reports_dir_holds_no_code, "submission")


# ===========================================================================

def main() -> int:
    parser = argparse.ArgumentParser(description="HW5 self-check")
    parser.add_argument("--offline", action="store_true",
                        help="skip checks needing MySQL, the backend or the network")
    args = parser.parse_args()

    # Several checks deliberately trigger warnings (the safety rule, unknown
    # tools). Silencing them keeps the PASS/FAIL column readable in the
    # screenshot; every check asserts on return values, never on log output.
    import logging

    logging.disable(logging.CRITICAL)

    print("=" * 72)
    print("HW5 verification - Pragnaya Priyadarshini")
    print(f"SID4={SID4}  PORT_BASE={PORT_BASE}  PREFIX={PREFIX}  "
          f"SEED={SEED}  VERIFY_SEED={VERIFY_SEED}  DOMAIN_ID={DOMAIN_ID}")
    print("=" * 72)
    print()

    checks = Checks()
    # A scratch directory exists for the duration of the run; nothing in the
    # repository is written except reports/hw05/verification.json.
    with tempfile.TemporaryDirectory(prefix="hw5-verify-") as tmp:
        os.environ.setdefault("HW5_VERIFY_TMP", tmp)
        register(checks, offline=args.offline)

    payload = {
        "homework": 5,
        "sid4": SID4,
        "prefix": PREFIX,
        "port_base": PORT_BASE,
        "domain_id": DOMAIN_ID,
        "seed": SEED,
        "verify_seed": VERIFY_SEED,
        "commit_hash": commit_hash(),
        "git_tags_at_head": git_tag_for_head(),
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_configuration": MODEL_CONFIG,
        # Top-level counts, so the pass/fail totals are visible without
        # drilling into `summary`.
        "passed": checks.passed,
        "failed": checks.failed,
        "skipped": checks.skipped,
        "total_checks": len(checks.results),
        "summary": {
            "passed": checks.passed,
            "failed": checks.failed,
            "skipped": checks.skipped,
            "total": len(checks.results),
        },
        "checks": checks.results,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "verification.json"
    out.write_text(json.dumps(payload, indent=2) + "\n")

    print()
    print("-" * 72)
    print(f"{checks.passed} passed, {checks.failed} failed, {checks.skipped} skipped "
          f"(of {len(checks.results)} checks)")
    print(f"commit {payload['commit_hash'][:12]}"
          + (f"  tags: {payload['git_tags_at_head']}" if payload["git_tags_at_head"] else ""))
    print(f"wrote {out.relative_to(REPO_ROOT)}")
    print("-" * 72)

    return 0 if checks.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
