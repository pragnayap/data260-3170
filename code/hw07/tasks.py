"""
HW7 Parts 2-3 - the three fixed verification tasks (A, B, C) and the error-recovery
case, each with a deterministic check computed from the live database through the
same execute_tool the agent uses. A check never looks at exact wording: it asks
whether the required tool chain happened and whether the answer carries the fact the
tools actually returned.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import execute_tool  # noqa: E402


def _tool(name: str, **inputs):
    return json.loads(execute_tool(name, inputs))["data"]


def _calls(run, name):
    return [c for c in run.tool_log if c["tool"] == name and c["ok"]]


def check_A(run):
    """Search, then detail-lookup the FIRST search result."""
    searches = _calls(run, "search_incidents")
    details = _calls(run, "incident_details")
    if not searches or not details:
        return False, "lost chain: needs search_incidents then incident_details"
    first = searches[0]["data"]["results"][0]
    got = details[0]["data"]
    if got["incident_code"] != first["incident_code"]:
        return False, f"detail looked up {got['incident_code']}, not first result {first['incident_code']}"
    ans = (run.answer or "").lower()
    if first["incident_code"].lower() not in ans and got["category"].lower() not in ans:
        return False, "answer does not state the looked-up incident's code or category"
    return True, f"detailed first result {first['incident_code']}"


def check_B(run):
    """Aggregate (most common category), then one supporting example."""
    top = _tool("incident_stats", group_by="category")["groups"][0]["group"]
    stats = [c for c in _calls(run, "incident_stats") if c["inputs"].get("group_by") == "category"]
    if not stats:
        return False, "lost chain: no incident_stats(group_by=category) call"
    if len(run.tool_log) < 2:
        return False, "lost chain: no supporting-example lookup"
    example = any(
        (c["tool"] == "search_incidents" and c["inputs"].get("category") == top)
        or (c["tool"] == "incident_details" and c["ok"] and c["data"]["category"] == top)
        for c in run.tool_log
    )
    if not example:
        return False, f"no example lookup for top category {top!r}"
    if top.lower() not in (run.answer or "").lower():
        return False, f"answer does not name the top category {top!r}"
    return True, f"top category {top}"


def check_C(run):
    """Compare two entities: search + two detail lookups, name the one with more riders."""
    searches = _calls(run, "search_incidents")
    details = _calls(run, "incident_details")
    if not searches or len(details) < 2:
        return False, "lost chain: needs search plus two incident_details"
    first_two = [r["incident_code"] for r in searches[0]["data"]["results"][:2]]
    looked = {d["data"]["incident_code"]: d["data"]["riders_affected"] for d in details}
    if not all(code in looked for code in first_two):
        return False, f"did not detail both of {first_two}"
    winner = max(first_two, key=lambda c: looked[c])
    if winner.lower() not in (run.answer or "").lower():
        return False, f"answer does not name {winner}, which affected more riders"
    return True, f"{winner} affected more riders"


def check_missing(run):
    """Nonexistent ID: the tool says so usefully and the agent still answers."""
    notfound = [c for c in run.tool_log if not c["ok"] and "no incident found" in (c["error"] or "")]
    if not notfound:
        return False, "never hit the not-found case"
    if run.stop_reason != "completed" or not run.answer:
        return False, f"agent did not finish cleanly ({run.stop_reason})"
    return True, f"tool said: {notfound[0]['error']!r}; agent answered"


TASKS = {
    "A": ("Search incidents for 'Main St', then look up the full details of the first "
          "search result and tell me its incident code, category and route.", check_A),
    "B": ("Which incident category has the most incidents overall? Then find one example "
          "incident of that category to support your answer.", check_B),
    "C": ("Search for incidents at 'Main St & 4th Ave', then get the full details of the "
          "first two results and say which one affected more riders.", check_C),
}
MISSING = ("Show me the full details of incident INC-3170-99999.", check_missing)
IMPOSSIBLE = ("Show me the full details of incident banana.", check_missing)
