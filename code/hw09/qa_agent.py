"""
HW9 - the domain Q&A agent that sits BEHIND the semantic cache.

It is the HW8 pipeline (planner -> writer -> reviewer, each stage the HW8 code, local qwen3:8b via the
llm.py adapter) run in-process rather than over Kafka, plus one extra step HW8 did not have: the stage
reads the s3170_rel rows the question is about, so the final answer DEPENDS on database records. That
dependency is what makes a cached answer able to go stale (Part 3.5).
"""
from __future__ import annotations

import hashlib
import re
import time
from typing import Any

import common  # noqa: F401  (puts web_application and hw08 on sys.path)
from sqlalchemy import text

from database import engine

ROUTE_RE = re.compile(r"\bR-\d{4}\b")
INCIDENT_RE = re.compile(r"\bINC-\d{4}-\d{5}\b")
CATEGORIES = ["Delay", "Mechanical Failure", "Accident-Collision", "Safety Hazard"]


def extract_entities(question: str) -> list[str]:
    return sorted(set(ROUTE_RE.findall(question)) | set(INCIDENT_RE.findall(question)))


# --- database access -------------------------------------------------------------------------
def route_facts(code: str) -> dict[str, Any] | None:
    with engine.connect() as c:
        r = c.execute(text("SELECT id, route_code, route_name, agency, route_type, updated_at FROM routes "
                           "WHERE route_code = :c"), {"c": code}).mappings().first()
        if r is None:
            return None
        agg = c.execute(text("SELECT COUNT(*) n, COALESCE(SUM(riders_affected),0) riders, MAX(updated_at) last "
                             "FROM incidents WHERE related_route_id = :i"), {"i": r["id"]}).mappings().first()
        cats = dict(c.execute(text("SELECT category, COUNT(*) FROM incidents WHERE related_route_id = :i "
                                   "GROUP BY category"), {"i": r["id"]}).all())
    return {"route_code": r["route_code"], "route_name": r["route_name"], "agency": r["agency"],
            "route_type": r["route_type"], "incident_count": int(agg["n"]), "riders_total": int(agg["riders"]),
            "by_category": {k: int(cats.get(k, 0)) for k in CATEGORIES},
            "_route_updated": r["updated_at"], "_incident_last": agg["last"]}


def incident_facts(code: str) -> dict[str, Any] | None:
    with engine.connect() as c:
        r = c.execute(text("SELECT incident_code, route_id, location, category, riders_affected, updated_at "
                           "FROM incidents WHERE incident_code = :c"), {"c": code}).mappings().first()
    return dict(r) if r else None


def data_version(entities: list[str]) -> str:
    """The data-version marker: a short hash over the updated_at stamps (and incident count) of every row
    the answer depends on. Any UPDATE to those rows changes it; a view-count sync does not (raw UPDATE)."""
    if not entities:
        return "none"
    parts = []
    for e in sorted(entities):
        if e.startswith("R-"):
            f = route_facts(e)
            parts.append(f"{e}:{f['_route_updated']}:{f['incident_count']}:{f['_incident_last']}" if f else f"{e}:missing")
        else:
            f = incident_facts(e)
            parts.append(f"{e}:{f['updated_at']}" if f else f"{e}:missing")
    return "v-" + hashlib.sha1("|".join(parts).encode()).hexdigest()[:12]


def facts_text(entities: list[str]) -> str:
    lines = []
    for e in entities:
        if e.startswith("R-"):
            f = route_facts(e)
            if f:
                cats = ", ".join(f"{k}={v}" for k, v in f["by_category"].items())
                lines.append(f"Route {f['route_code']}: name={f['route_name']}; agency={f['agency']}; "
                             f"type={f['route_type']}; incidents_recorded={f['incident_count']}; "
                             f"total_riders_affected={f['riders_total']}; incidents_by_category: {cats}")
        else:
            f = incident_facts(e)
            if f:
                lines.append(f"Incident {f['incident_code']}: route={f['route_id']}; location={f['location']}; "
                             f"category={f['category']}; riders_affected={f['riders_affected']}")
    return "\n".join(lines) or "No database record matched the question."


# --- ground truth (used only to LABEL results, never by the agent) -----------------------------
def ground_truth(key: dict[str, Any]) -> str:
    f = route_facts(key["route"])
    kind = key["kind"]
    if kind == "agency":
        return f["agency"]
    if kind == "route_type":
        return f["route_type"]
    if kind == "route_name":
        return f["route_name"]
    if kind == "incident_count":
        return str(f["incident_count"])
    if kind == "riders_total":
        return str(f["riders_total"])
    if kind == "category_count":
        return str(f["by_category"][key["category"]])
    raise ValueError(kind)


# --- the HW8 path ------------------------------------------------------------------------------
def run_agent(question: str) -> dict[str, Any]:
    """planner -> (DB read) -> writer -> reviewer. Returns the final answer plus the data-version marker."""
    from llm import complete  # HW8 adapter: qwen3:8b through Ollama, token cap + timeout
    from planner import make_plan  # HW8 planner stage
    from reviewer import review  # HW8 reviewer stage (rule based)

    t0 = time.perf_counter()
    entities = extract_entities(question)
    plan = make_plan(question)
    t1 = time.perf_counter()
    facts = facts_text(entities)
    version = data_version(entities)
    prompt = (f"Question: {question}\nPlan: {plan}\nDatabase facts:\n{facts}\n"
              "Write the answer in one or two complete sentences. Use the database facts when they are given.")
    draft = complete(prompt, max_tokens=120)
    status, why = review(draft)
    retried = False
    if status == "rejected":                       # one retry, same as a reviewer sending a draft back
        retried = True
        draft = complete(prompt + " Reply with a full sentence.", max_tokens=120)
        status, why = review(draft)
    t2 = time.perf_counter()
    return {"answer": draft, "data_version": version, "entities": entities, "plan": plan,
            "reviewer": status, "reviewer_note": why, "retried": retried,
            "planner_ms": round((t1 - t0) * 1000), "writer_ms": round((t2 - t1) * 1000),
            "agent_ms": round((t2 - t0) * 1000)}
