#!/usr/bin/env python3
"""HW9 Part 4 - build the reference dataset (ground truth) from s3170_rel + a seeded fare history, and write the
three INPUT datasets (questions only - no expected answers) into data/hw09/part4/."""
from __future__ import annotations

import json
import random
import sys

import common
from common import SEED, banner
from sqlalchemy import text

from database import engine

OUT = common.DATA / "part4"
ROUTES = [f"R-{n:04d}" for n in range(101, 131)]          # 30 routes; none is used by the Part 2/3 cache cases

TRAINING = [
    "What is the current fare on route R-0101?",
    "Which agency operates route R-0102 and what type of route is it?",
    "What is the capital of Australia?",
    "How many incidents are recorded for route R-0103?",
    "What is the ticket price for route R-0104?",
    "What is the most common incident category on route R-0105?",
    "Who won the most recent football World Cup?",
    "How many riders were affected in total on route R-0106, and which agency runs it?",
    "What is the name of route R-0107?",
    "How much does it cost to ride route R-0108?",
    "Recommend a good restaurant near Union Square in San Francisco.",
    "What agency runs route R-0109?",
]
VALIDATION = [
    "What is the current fare for route R-0111?",
    "Which agency operates route R-0112, and what is its route type?",
    "How do I convert Celsius to Fahrenheit?",
    "How many incidents are recorded for route R-0113?",
    "What does a ticket cost on route R-0114?",
    "What is the most common incident category on route R-0115, and how many incidents are recorded there?",
    "Who painted the Mona Lisa?",
    "What agency operates the route named Line 116?",             # no route code: by name, must still be answered
    "What is the name of route R-0117?",
    "How many riders were affected in total on route R-0118?",
]
TEST = [
    "What is the current fare on route R-0121?",
    "Which agency operates route R-0122 and what type of route is it?",
    "What is the largest ocean on Earth?",
    "How many incidents are recorded for route R-0123?",
    "How much is a single ride on route R-0124?",
    "What is the most common incident category on route R-0125?",
    "Who is the current president of France?",
    "How many riders were affected in total on route R-0126, and which agency runs it?",
    "What is the name of route R-0127?",
    "What agency operates the route named Caltrain Line 128?",            # by name, no code
    "What is the current fare on route R-0129 and which agency operates it?",
    "How many incidents are recorded for route R-9999?",           # route that does not exist
    "What is the best pizza topping?",
    "What type of route is R-0130?",
]


def build_reference() -> list[dict]:
    rng = random.Random(SEED)
    out = []
    with engine.connect() as c:
        for code in ROUTES:
            r = c.execute(text("SELECT id, route_name, agency, route_type FROM routes WHERE route_code=:c"), {"c": code}).mappings().one()
            agg = c.execute(text("SELECT COUNT(*) n, COALESCE(SUM(riders_affected),0) s FROM incidents WHERE related_route_id=:i"),
                            {"i": r["id"]}).mappings().one()
            cats = c.execute(text("SELECT category, COUNT(*) k FROM incidents WHERE related_route_id=:i GROUP BY category "
                                  "ORDER BY k DESC, category"), {"i": r["id"]}).all()
            base = round(rng.choice([1.75, 2.00, 2.25, 2.50]), 2)
            fares = [{"fare_usd": base, "effective": "2025-01-01"},
                     {"fare_usd": round(base + 0.25, 2), "effective": "2025-07-01"},
                     {"fare_usd": round(base + 0.50, 2), "effective": "2026-07-01"}]
            out.append({"route_code": code, "route_name": r["route_name"], "agency": r["agency"], "route_type": r["route_type"],
                        "incident_count": int(agg["n"]), "riders_total": int(agg["s"]),
                        "top_incident_category": cats[0][0], "fare_history": fares})
    return out


def main() -> int:
    banner("part4_build_data.py")
    OUT.mkdir(parents=True, exist_ok=True)
    ref = build_reference()
    (OUT / "reference_dataset.json").write_text(json.dumps({"description": "Ground truth for HW9 Part 4. Route facts come from "
        "s3170_rel (routes + incident aggregates); fare_history is synthetic, generated with random.Random(3170). "
        "The current fare is the entry with the latest effective date.", "routes": ref}, indent=2))
    for name, qs in (("training_data", TRAINING), ("validation_data", VALIDATION), ("test_data", TEST)):
        (OUT / f"{name}.json").write_text(json.dumps([{"id": f"{name[:3]}_{i:02d}", "question": q} for i, q in enumerate(qs, 1)], indent=2))
    names = [r["route_name"] for r in ref]
    for n in ("Line 116", "Caltrain Line 128"):
        print(f"route name {n!r} present in reference:", names.count(n))
    print(f"wrote reference_dataset.json ({len(ref)} routes) + training {len(TRAINING)} / validation {len(VALIDATION)} / test {len(TEST)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
