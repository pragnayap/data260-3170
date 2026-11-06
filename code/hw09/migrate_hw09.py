#!/usr/bin/env python3
"""HW9 Part 1 - add incidents.view_count to the existing s3170_rel table (create_all never alters a table)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web_application"))
from sqlalchemy import inspect, text  # noqa: E402

from database import engine  # noqa: E402

cols = {c["name"] for c in inspect(engine).get_columns("incidents")}
if "view_count" in cols:
    print("incidents.view_count already exists")
else:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE incidents ADD COLUMN view_count INT NOT NULL DEFAULT 0"))
    print("added incidents.view_count INT NOT NULL DEFAULT 0")
