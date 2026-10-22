#!/usr/bin/env python3
"""
HW7 Part 4 - build the two acceptance datasets from real Capital Bikeshare trip files
(https://s3.amazonaws.com/capitalbikeshare-data/), sampled with SEED 3170.

    heavy_rider.csv  600 trips from one month (2023-07), each 15+ minutes  -> membership wins
    light_rider.csv  525 trips of 1-12 minutes, ~75 from each of seven files spread over
                     2011-2024, so the rider averages ~3 rides a month        -> pay-per-use wins

Both are normalised to: started_at, ended_at, duration_min, rideable_type, member_type.
Pre-2020 files use the old schema (Duration in seconds, 'Start date', 'Member type');
2020-12+ files use started_at/ended_at/rideable_type/member_casual.

Honest limits, repeated in the report: trips are real but a "rider" is assembled by
sampling (the public data has no rider id), and the light dataset applies today's prices
to historical trips. Downloads go to data/hw07_raw/ (gitignored).
"""

from __future__ import annotations

import csv
import io
import random
import sys
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path

SEED = 3170
BASE = "https://s3.amazonaws.com/capitalbikeshare-data/"
ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "data" / "hw07_raw"
OUT = ROOT / "reports" / "hw07" / "raw" / "bike_data"
FIELDS = ["started_at", "ended_at", "duration_min", "rideable_type", "member_type"]

LIGHT_FILES = ["2011", "2012", "201806", "201906", "202106", "202306", "202406"]
HEAVY_FILE = "202307"


def download(tag: str) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / f"{tag}-capitalbikeshare-tripdata.zip"
    if not dest.exists():
        print(f"downloading {dest.name} ...", flush=True)
        urllib.request.urlretrieve(f"{BASE}{dest.name}", dest)
    return dest


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.strip()[:19])


def normalise(row: dict) -> dict | None:
    try:
        if "started_at" in row:
            start, end = parse(row["started_at"]), parse(row["ended_at"])
            kind = (row.get("rideable_type") or "classic_bike").replace("docked_bike", "classic_bike")
            member = row.get("member_casual", "")
        else:
            start, end = parse(row["Start date"]), parse(row["End date"])
            kind, member = "classic_bike", row.get("Member type", "")
    except (KeyError, ValueError):
        return None
    minutes = (end - start).total_seconds() / 60
    if minutes <= 0:
        return None
    return {"started_at": start.strftime("%Y-%m-%d %H:%M:%S"),
            "ended_at": end.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_min": round(minutes, 2), "rideable_type": kind, "member_type": member}


def load(tag: str) -> list[dict]:
    rows = []
    with zipfile.ZipFile(download(tag)) as z:
        for name in z.namelist():
            if name.lower().endswith(".csv") and not name.startswith("__MACOSX"):
                with z.open(name) as fh:
                    for raw in csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig")):
                        r = normalise(raw)
                        if r:
                            rows.append(r)
    return rows


def write(path: Path, rows: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: r["started_at"])
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path.name}: {len(rows)} trips, {rows[0]['started_at']} -> {rows[-1]['started_at']}")


def main() -> None:
    rng = random.Random(SEED)
    heavy_pool = [r for r in load(HEAVY_FILE) if r["duration_min"] >= 15]
    write(OUT / "heavy_rider.csv", rng.sample(heavy_pool, 600))

    light = []
    for tag in LIGHT_FILES:
        pool = [r for r in load(tag) if 1 <= r["duration_min"] <= 12]
        light += rng.sample(pool, 75)
        print(f"  {tag}: pool {len(pool)}", flush=True)
    write(OUT / "light_rider.csv", light)


if __name__ == "__main__":
    sys.exit(main())
