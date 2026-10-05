#!/usr/bin/env python3
"""
HW5 Part 4 - the offline test runner.

The spec:
  * a simple Python test runner using assert statements
  * for each of the three domain tools, at least one valid input and the
    invalid input cases described in Part 3
  * at least six tests overall
  * print PASS or FAIL for each test and a final X/Y summary
  * temporary fixtures or dependency injection, so the tests run offline,
    repeatedly, and without an LLM

Run (from the repo root):
    .venv/bin/python code/mcp_servers/test_tools.py

HOW IT RUNS OFFLINE
    The tools read MySQL through `db_session_basede26`, imported from
    web_application/database.py. Before importing anything that touches it,
    _install_fixture() puts a stand-in `database` module into sys.modules
    backed by an in-memory SQLite database, creates the real tables from the
    real models, and seeds six deterministic rows.

    So the tests exercise the actual tool code and the actual ORM models --
    only the connection is swapped. Nothing here needs MySQL running, a
    network connection, an API key or a language model, and the result is the
    same on every run because the fixture is fixed rather than sampled.

    The seeded rows are chosen to make the assertions meaningful: two
    locations share a substring so search returns a known count, and the two
    routes sit under different agencies so the aggregate has more than one
    group.

EXIT CODE
    0 if every test passed, 1 otherwise -- so verify_hw05.py can call this and
    read the result rather than parsing its output.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "web_application"))


# --- the offline fixture ---------------------------------------------------

def _install_fixture() -> None:
    """Swap in an in-memory SQLite database before the tools are imported.

    StaticPool and check_same_thread are both required, and the reason is
    specific to this project. call_with_retry (Part 3) runs every attempt on a
    ThreadPoolExecutor worker so it can enforce a timeout. SQLAlchemy's default
    pool for an in-memory SQLite URL hands each thread its own connection --
    and a separate connection to ":memory:" is a separate, empty database. The
    tables would be created on the main thread and the tools would then run on
    a worker thread that cannot see them ("no such table: incidents").

    StaticPool keeps exactly one connection and shares it, and
    check_same_thread=False lets the sqlite3 driver accept use from another
    thread. Neither applies to the real MySQL engine, which pools per
    checkout and is thread-safe already.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import DeclarativeBase, sessionmaker
    from sqlalchemy.pool import StaticPool

    class Base(DeclarativeBase):
        pass

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Session = sessionmaker(bind=engine)

    stub = types.ModuleType("database")
    stub.Base = Base
    stub.engine = engine
    stub.db_session_basede26 = Session
    sys.modules["database"] = stub

    import models  # real models, against the stub Base

    Base.metadata.create_all(engine)

    db = Session()
    db.add_all(
        [
            models.Route(route_code="R-0001", route_name="Line 1",
                         agency="VTA", route_type="Bus"),
            models.Route(route_code="R-0002", route_name="Rapid 2",
                         agency="BART", route_type="Subway"),
        ]
    )
    db.commit()

    rows = [
        # code,            route,     location,                   category,             riders, route
        ("INC-3170-00001", "Line 1",  "Downtown Transit Center",  "Delay",                 40, 1),
        ("INC-3170-00002", "Line 1",  "Civic Center Station",     "Delay",                 10, 1),
        ("INC-3170-00003", "Rapid 2", "Downtown Transit Center",  "Safety Hazard",          0, 2),
        ("INC-3170-00004", "Rapid 2", "Harbor Point Station",     "Mechanical Failure",    25, 2),
        ("INC-3170-00005", "Line 1",  "Airport Terminal Stop",    "Accident-Collision",    12, 1),
        ("INC-3170-00006", "Rapid 2", "Downtown Transit Center",  "Delay",                  7, 2),
    ]
    for code, route_id, location, category, riders, related in rows:
        db.add(
            models.Incident(
                incident_code=code,
                route_id=route_id,
                location=location,
                submitter_email="rider@example.com",
                description="Seeded fixture row for the offline test suite.",
                category=category,
                riders_affected=riders,
                related_route_id=related,
            )
        )
    db.commit()
    db.close()


_install_fixture()

import transit_tools  # noqa: E402
from envelope import is_envelope  # noqa: E402
from execute_tool import execute_tool, tool_catalog  # noqa: E402


# --- the runner ------------------------------------------------------------

class Runner:
    """Minimal assert-based runner. No pytest: the spec asks for assert
    statements and a printed X/Y summary, and a dependency-free runner is one
    less thing to install before a demo."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.results: list[tuple[str, bool, str]] = []

    def run(self, name: str, fn) -> None:
        try:
            fn()
        except AssertionError as exc:
            self.failed += 1
            self.results.append((name, False, str(exc) or "assertion failed"))
            print(f"  FAIL  {name}")
            print(f"        {exc}")
        except Exception as exc:  # noqa: BLE001
            self.failed += 1
            self.results.append((name, False, f"{type(exc).__name__}: {exc}"))
            print(f"  FAIL  {name}")
            print(f"        unexpected {type(exc).__name__}: {exc}")
        else:
            self.passed += 1
            self.results.append((name, True, ""))
            print(f"  PASS  {name}")

    @property
    def total(self) -> int:
        return self.passed + self.failed


def call(name: str, inputs: dict) -> dict:
    """execute_tool returns a JSON string; the tests parse it back.

    Going through the string on every call is deliberate -- it is the contract
    the Part 5 agent actually consumes, so the tests exercise it rather than a
    convenience shortcut around it.
    """
    raw = execute_tool(name, inputs)
    assert isinstance(raw, str), f"execute_tool must return str, got {type(raw).__name__}"
    return json.loads(raw)


# --- tests: search_incidents ----------------------------------------------

def test_search_valid():
    """search_incidents with a valid query returns matching rows."""
    env = call("search_incidents", {"query": "Downtown", "limit": 5})
    assert env["ok"] is True, f"expected ok, got {env['error']}"
    assert env["error"] is None, "error must be null on success"
    assert env["data"]["count"] == 3, f"expected 3 Downtown rows, got {env['data']['count']}"
    codes = [r["incident_code"] for r in env["data"]["results"]]
    assert "INC-3170-00001" in codes, f"expected the seeded row in {codes}"


def test_search_rejects_limit_zero():
    """Part 3's rejected input for search_incidents: limit outside 1-50."""
    env = call("search_incidents", {"query": "Downtown", "limit": 0})
    assert env["ok"] is False, "limit=0 must be rejected"
    assert env["data"] is None, "data must be null on failure"
    assert "limit" in env["error"], f"error should name the bad field: {env['error']}"


def test_search_rejects_empty_query():
    """An empty query is rejected rather than scanning the whole table."""
    env = call("search_incidents", {"query": "", "limit": 5})
    assert env["ok"] is False, "empty query must be rejected"
    assert "query" in env["error"], f"error should name the bad field: {env['error']}"


# --- tests: incident_details ----------------------------------------------

def test_details_valid():
    """incident_details returns the full record for a known code."""
    env = call("incident_details", {"incident_code": "INC-3170-00001"})
    assert env["ok"] is True, f"expected ok, got {env['error']}"
    assert env["data"]["incident_code"] == "INC-3170-00001"
    assert env["data"]["route"]["agency"] == "VTA", "the route should be joined in"


def test_details_rejects_malformed_code():
    """Part 3's rejected input for incident_details: bad code format."""
    env = call("incident_details", {"incident_code": "INC-317-1"})
    assert env["ok"] is False, "a malformed code must be rejected"
    assert "INC-NNNN-NNNNN" in env["error"], f"error should state the format: {env['error']}"


def test_details_unknown_code_is_not_a_crash():
    """A well-formed code that matches nothing is a clean miss, not an exception."""
    env = call("incident_details", {"incident_code": "INC-3170-99999"})
    assert env["ok"] is False, "an unknown code must report failure"
    assert "INC-3170-99999" in env["error"], "error should name the code that missed"


# --- tests: incident_stats ------------------------------------------------

def test_stats_valid():
    """incident_stats groups correctly and joins through the foreign key."""
    env = call("incident_stats", {"group_by": "agency"})
    assert env["ok"] is True, f"expected ok, got {env['error']}"
    assert env["data"]["total_incidents"] == 6, (
        f"fixture has 6 incidents, aggregate counted {env['data']['total_incidents']}"
    )
    agencies = {g["group"] for g in env["data"]["groups"]}
    assert agencies == {"VTA", "BART"}, f"expected both agencies, got {agencies}"


def test_stats_rejects_bad_group_by():
    """Part 3's rejected input for incident_stats: an unsupported grouping."""
    env = call("incident_stats", {"group_by": "banana"})
    assert env["ok"] is False, "an unsupported group_by must be rejected"
    assert "category" in env["error"], "error should list the allowed values"


def test_stats_riders_are_summed():
    """The aggregate's arithmetic, checked against the fixture by hand."""
    env = call("incident_stats", {"group_by": "category"})
    groups = {g["group"]: g for g in env["data"]["groups"]}
    # Delay rows in the fixture: 40 + 10 + 7 = 57 across 3 incidents
    assert groups["Delay"]["incidents"] == 3, groups["Delay"]
    assert groups["Delay"]["total_riders_affected"] == 57, groups["Delay"]
    assert groups["Delay"]["avg_riders_affected"] == 19.0, groups["Delay"]


# --- tests: the execute_tool contract itself ------------------------------

def test_execute_tool_returns_json_string():
    """The spec requires a JSON string, not a dict."""
    raw = execute_tool("incident_stats", {"group_by": "category"})
    assert isinstance(raw, str), f"got {type(raw).__name__}, expected str"
    parsed = json.loads(raw)
    assert is_envelope(parsed), f"parsed object is not an envelope: {sorted(parsed)}"


def test_unknown_tool_does_not_crash():
    """An agent naming a tool that does not exist gets an error, not a traceback."""
    env = call("not_a_real_tool", {})
    assert env["ok"] is False, "an unknown tool must fail cleanly"
    assert "unknown tool" in env["error"], env["error"]
    assert "search_incidents" in env["error"], "the error should list what is available"


def test_unexpected_argument_does_not_crash():
    """An invented argument is reported, not raised as TypeError."""
    env = call("incident_stats", {"group_by": "category", "sort_by": "whatever"})
    assert env["ok"] is False, "an unexpected argument must be rejected"
    assert "sort_by" in env["error"], env["error"]


def test_missing_required_argument_does_not_crash():
    """A missing required argument is reported, not raised as TypeError."""
    env = call("incident_details", {})
    assert env["ok"] is False, "a missing required argument must be rejected"
    assert env["data"] is None


def test_every_response_is_an_envelope():
    """Whatever happens, the shape is always {ok, data, error}."""
    cases = [
        ("search_incidents", {"query": "Downtown"}),
        ("search_incidents", {"query": "", "limit": 0}),
        ("incident_details", {"incident_code": "INC-3170-00002"}),
        ("incident_details", {"incident_code": "nope"}),
        ("incident_stats", {"group_by": "route_type"}),
        ("incident_stats", {"group_by": ""}),
        ("ghost_tool", {}),
        ("search_incidents", "not a dict"),
    ]
    for name, inputs in cases:
        parsed = json.loads(execute_tool(name, inputs))
        assert is_envelope(parsed), f"{name}({inputs}) -> {sorted(parsed)}"
        if parsed["ok"]:
            assert parsed["error"] is None, f"{name}: ok but error set"
        else:
            assert parsed["data"] is None, f"{name}: failed but data set"


def test_search_results_carry_no_submitter_email():
    """Search results must not leak the reporter's email address.

    This is the invariant the Part 5 safety rule defends. Asserting it here
    means a future change to the result shape that re-exposes the field fails
    the suite rather than quietly shipping.
    """
    env = call("search_incidents", {"query": "Downtown", "limit": 10})
    for row in env["data"]["results"]:
        assert "submitter_email" not in row, f"PII leaked in search result: {row}"


def test_tool_catalog_matches_the_registry():
    """The catalog the agent is shown lists exactly the callable tools."""
    catalog = tool_catalog()
    assert len(catalog) == 3, f"expected 3 tools, catalog has {len(catalog)}"
    names = {t["name"] for t in catalog}
    assert names == set(transit_tools.TOOLS), f"{names} != {set(transit_tools.TOOLS)}"
    for tool in catalog:
        assert tool["summary"], f"{tool['name']} has no summary for the prompt"


# --- Part 5.III: two more tests, still offline ----------------------------
#
# The spec: "Test that execute_tool blocks a call that violates the safety
# rule, and that run_agent, using MockModel, stops after reaching max_steps.
# Both tests must run offline without an API key, live model, external API, or
# database."
#
# Both hold here: the safety rule is pure logic, and MockModel replaces
# ModelClient entirely, so no Ollama process is contacted. run_agent is called
# with log_path=None so the suite never appends to the real agent_runs.jsonl.

def test_safety_rule_blocks_submitter_email():
    """execute_tool refuses a call that would return reporter contact details."""
    import safety

    allowed = call("incident_details", {"incident_code": "INC-3170-00001"})
    assert allowed["ok"] is True, f"the plain lookup should work: {allowed['error']}"
    assert "submitter_email" not in allowed["data"], "PII present without asking"

    blocked = call(
        "incident_details",
        {"incident_code": "INC-3170-00001", "include_submitter": True},
    )
    assert blocked["ok"] is False, "include_submitter=True must be blocked"
    assert blocked["data"] is None, "a blocked call must return no data"
    assert safety.RULE_ID in blocked["error"], (
        f"the error should name the rule: {blocked['error']}"
    )

    # The second half of the same rule: searching by reporter identity.
    by_email = call("search_incidents", {"query": "rider@example.com", "limit": 5})
    assert by_email["ok"] is False, "searching by email address must be blocked"
    assert safety.RULE_ID in by_email["error"], by_email["error"]


def test_run_agent_stops_at_max_steps():
    """run_agent halts at the ceiling when the model never answers."""
    from agent_loop import MockModel, run_agent

    # A model that only ever calls a tool, never answers. Without the ceiling
    # this loops forever.
    never_answers = MockModel(
        ['{"tool": "incident_stats", "inputs": {"group_by": "category"}}']
    )

    run = run_agent(
        "How many incidents are there?",
        model=never_answers,
        max_steps=4,
        log_path=None,          # never touch the real agent_runs.jsonl
    )

    assert run.stop_reason == "max_steps", (
        f"expected max_steps, got {run.stop_reason}"
    )
    assert run.step_count == 4, f"expected exactly 4 steps, got {run.step_count}"
    assert run.tool_call_count == 4, f"expected 4 tool calls, got {run.tool_call_count}"
    assert run.answer is None, "no answer should have been produced"
    assert never_answers.calls == 4, (
        f"the model should have been called 4 times, not {never_answers.calls}"
    )

    # The same loop still terminates normally when the model does answer.
    answers_second = MockModel(
        [
            '{"tool": "incident_stats", "inputs": {"group_by": "category"}}',
            '{"answer": "There are 6 incidents across 4 categories."}',
        ]
    )
    done = run_agent("How many?", model=answers_second, max_steps=4, log_path=None)
    assert done.stop_reason == "completed", done.stop_reason
    assert done.step_count == 2, done.step_count
    assert done.tool_call_count == 1, done.tool_call_count
    assert "6 incidents" in (done.answer or "")


TESTS = [
    ("search_incidents: valid query returns rows", test_search_valid),
    ("search_incidents: rejects limit=0", test_search_rejects_limit_zero),
    ("search_incidents: rejects empty query", test_search_rejects_empty_query),
    ("incident_details: valid code returns record", test_details_valid),
    ("incident_details: rejects malformed code", test_details_rejects_malformed_code),
    ("incident_details: unknown code is a clean miss", test_details_unknown_code_is_not_a_crash),
    ("incident_stats: valid group_by aggregates", test_stats_valid),
    ("incident_stats: rejects bad group_by", test_stats_rejects_bad_group_by),
    ("incident_stats: rider totals are correct", test_stats_riders_are_summed),
    ("execute_tool: returns a JSON string", test_execute_tool_returns_json_string),
    ("execute_tool: unknown tool does not crash", test_unknown_tool_does_not_crash),
    ("execute_tool: unexpected argument does not crash", test_unexpected_argument_does_not_crash),
    ("execute_tool: missing argument does not crash", test_missing_required_argument_does_not_crash),
    ("execute_tool: every response is an envelope", test_every_response_is_an_envelope),
    ("privacy: search results carry no submitter_email", test_search_results_carry_no_submitter_email),
    ("catalog: matches the tool registry", test_tool_catalog_matches_the_registry),
    # Part 5.III
    ("safety rule: blocks reporter contact details", test_safety_rule_blocks_submitter_email),
    ("agent loop: stops at the max_steps ceiling", test_run_agent_stops_at_max_steps),
]


def main() -> int:
    # The tools and execute_tool log to stderr by design (the MCP STDIO rule).
    # Several tests deliberately trigger those warnings, so silence them here:
    # the suite asserts on return values, and interleaved log lines would make
    # the PASS/FAIL screenshot unreadable.
    import logging

    logging.disable(logging.CRITICAL)

    print("=" * 68)
    print("HW5 Parts 4 + 5 - offline tool tests")
    print("Pragnaya Priyadarshini | SID4 3170 | no network, no DB, no LLM")
    print("=" * 68)
    print()

    runner = Runner()
    for name, fn in TESTS:
        runner.run(name, fn)

    print()
    print("-" * 68)
    print(f"{runner.passed} passed, {runner.failed} failed    "
          f"=>  {runner.passed}/{runner.total}")
    print("-" * 68)
    return 0 if runner.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
