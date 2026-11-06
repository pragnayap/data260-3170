#!/usr/bin/env python3
"""HW9 Part 3.5 - a cached answer that depends on one s3170_rel row goes stale; version-marker invalidation fixes it."""
from __future__ import annotations

import json
import sys

import common
from common import banner
from qa_agent import data_version, route_facts
from semantic_cache import SemanticCache, embed
from sqlalchemy import select

from database import db_session_basede26
from models import Route

ROUTE = "R-0099"
QUERY = f"What agency operates route {ROUTE}?"
NEW_AGENCY = "Golden Gate Transit"


def set_agency(value: str) -> str:
    with db_session_basede26() as db:
        route = db.execute(select(Route).where(Route.route_code == ROUTE)).scalar_one()
        old, route.agency = route.agency, value
        db.commit()                 # ORM UPDATE -> updated_at's onupdate fires -> the data-version marker changes
        return old


def show(label: str, out: dict) -> None:
    print(f"  {label}: is_cached={out['is_cached']} similarity={out['similarity']} latency={out['latency_ms']:.0f} ms")
    print(f"      answer: {out['answer']}", flush=True)


def main() -> int:
    banner("part3_stale.py")
    cache = SemanticCache("stale")
    cache.create_index(reset=True)
    embed("warm up")
    log: dict = {"route": ROUTE, "query": QUERY}
    original = route_facts(ROUTE)["agency"]
    try:
        print(f"1) The cached question depends on routes row {ROUTE} (agency = {original!r}).")
        out = cache.handle(QUERY, validate_version=False)
        show("first ask (miss, agent runs, version marker stored)", out)
        log["first_ask"] = out
        print(f"      stored data_version = {out['data_version']}")
        print(f"\n2) UPDATE routes SET agency = {NEW_AGENCY!r} WHERE route_code = {ROUTE!r}")
        set_agency(NEW_AGENCY)
        print(f"      database now says: {route_facts(ROUTE)['agency']!r}; current data_version = {data_version([ROUTE])}")
        print("\n3) Same question again, NO invalidation (validate_version=False): the stale hit")
        stale = cache.handle(QUERY, validate_version=False)
        show("stale hit", stale)
        log["stale_hit"] = stale
        print("\n4) Same question, invalidation ON (stored marker compared with the live marker on every hit)")
        fixed = cache.handle(QUERY, validate_version=True)
        show("after invalidation", fixed)
        log["after_invalidation"] = fixed
        print("\n5) And once more: the refreshed entry is now a valid hit, at the cost of one version check")
        again = cache.handle(QUERY, validate_version=True)
        show("fresh hit", again)
        log["fresh_hit"] = again
    finally:
        restored = set_agency(original)
        print(f"\nrestored {ROUTE}.agency {restored!r} -> {original!r}")
    log["original_agency"] = original
    log["new_agency"] = NEW_AGENCY
    (common.RAW / "part3_stale.json").write_text(json.dumps(log, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
