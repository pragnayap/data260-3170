#!/usr/bin/env python3
"""
HW4 Part 3 - deterministic seed generator: 200 routes, 5,000 incidents.

Everything is derived from SEED=3170 (random.seed(SEED)), so re-running this
script reproduces byte-identical data. Routes are the "related table" Part 3
measures N+1 against; each incident picks one route at random, so most routes
end up referenced by roughly 25 incidents (5000 / 200) -- the many-to-one
shape a naive per-record lookup pays for.

Run (from repo root):
    .venv/bin/python code/seed_hw04.py
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "web_application"))

from sqlalchemy import text  # noqa: E402

from database import Base, db_session_basede26, engine  # noqa: E402
import models  # noqa: E402

SEED = 3170
N_ROUTES = 200
N_INCIDENTS = 5000

AGENCIES = ["SJ Transit", "BART", "VTA", "AC Transit", "Caltrain", "Muni", "SamTrans"]
ROUTE_TYPES = ["Bus", "Light Rail", "Subway", "Commuter Rail"]
ROUTE_NAME_TEMPLATES = [
    "Line {n}", "Route {n}", "Express {n}", "{agency} Line {n}", "Rapid {n}",
]

CATEGORIES = ["Delay", "Mechanical Failure", "Accident-Collision", "Safety Hazard"]
LOCATIONS = [
    "Downtown Transit Center", "Civic Center Station", "Main St & 4th Ave",
    "University Station", "Airport Terminal Stop", "Riverside Junction",
    "North Yard Depot", "Harbor Point Station", "Fairview Plaza Stop",
    "Central Square", "Lakeside Station", "Old Town Terminal",
]
DELAY_NOTES = [
    "never arrived and riders waited {mins} minutes with no announcement",
    "was running {mins} minutes behind schedule with no driver update",
    "skipped the stop entirely, stranding riders for {mins} minutes",
]
MECH_NOTES = [
    "had a door malfunction that delayed boarding by {mins} minutes",
    "broke down mid-route and passengers waited {mins} minutes for a replacement",
    "had failing brakes reported by the operator after a {mins}-minute inspection halt",
]
ACCIDENT_NOTES = [
    "was involved in a minor collision with a parked vehicle near the stop",
    "clipped a bike lane barrier while turning, no injuries reported",
    "had a low-speed collision with another transit vehicle at the depot",
]
HAZARD_NOTES = [
    "had a broken step that riders nearly tripped over boarding",
    "had exposed wiring near the rear door reported by a rider",
    "had a slippery floor from a leak with no warning signage posted",
]

NOTES_BY_CATEGORY = {
    "Delay": DELAY_NOTES,
    "Mechanical Failure": MECH_NOTES,
    "Accident-Collision": ACCIDENT_NOTES,
    "Safety Hazard": HAZARD_NOTES,
}

FIRST_NAMES = ["alex", "jordan", "sam", "casey", "morgan", "taylor", "riley", "jamie"]


def build_routes(rng: random.Random) -> list[dict]:
    routes = []
    for i in range(1, N_ROUTES + 1):
        agency = rng.choice(AGENCIES)
        template = rng.choice(ROUTE_NAME_TEMPLATES)
        route_name = template.format(n=i, agency=agency)
        routes.append(
            {
                "route_code": f"R-{i:04d}",
                "route_name": route_name,
                "agency": agency,
                "route_type": rng.choice(ROUTE_TYPES),
            }
        )
    return routes


def build_incidents(rng: random.Random, route_id_to_name: dict[int, str]) -> list[dict]:
    route_ids = list(route_id_to_name.keys())
    incidents = []
    for i in range(N_INCIDENTS):
        category = rng.choice(CATEGORIES)
        note = rng.choice(NOTES_BY_CATEGORY[category])
        mins = rng.randint(8, 55)
        description = f"Transit vehicle on this route {note.format(mins=mins)}."
        related_route_id = rng.choice(route_ids)
        route_id_text = route_id_to_name[related_route_id]
        location = rng.choice(LOCATIONS)
        submitter = f"{rng.choice(FIRST_NAMES)}{rng.randint(1, 999)}@example.com"
        incidents.append(
            {
                "route_id": route_id_text,
                "location": location,
                "submitter_email": submitter,
                "description": description,
                "category": category,
                "related_route_id": related_route_id,
            }
        )
    return incidents


def main() -> None:
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] seed_hw04.py starting, SEED={SEED}")

    Base.metadata.create_all(bind=engine)
    rng = random.Random(SEED)

    routes_data = build_routes(rng)

    db = db_session_basede26()
    try:
        print(f"[{time.strftime('%H:%M:%S')}] truncating incidents/routes (resets auto-increment)...")
        db.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        db.execute(text("TRUNCATE TABLE incidents"))
        db.execute(text("TRUNCATE TABLE routes"))
        db.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        db.commit()

        print(f"[{time.strftime('%H:%M:%S')}] inserting {N_ROUTES} routes...")
        db.bulk_insert_mappings(models.Route, routes_data)
        db.commit()

        route_rows = db.query(models.Route.id, models.Route.route_name).order_by(models.Route.id).all()
        route_id_to_name = {r.id: r.route_name for r in route_rows}

        print(f"[{time.strftime('%H:%M:%S')}] generating {N_INCIDENTS} incidents...")
        incidents_data = build_incidents(rng, route_id_to_name)

        print(f"[{time.strftime('%H:%M:%S')}] inserting {N_INCIDENTS} incidents...")
        db.bulk_insert_mappings(models.Incident, incidents_data)
        db.commit()

        route_count = db.query(models.Route).count()
        incident_count = db.query(models.Incident).count()
    finally:
        db.close()

    elapsed = time.time() - t0
    print(f"[{time.strftime('%H:%M:%S')}] done in {elapsed:.1f}s -- routes={route_count} incidents={incident_count}")


if __name__ == "__main__":
    main()
