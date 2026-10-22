#!/usr/bin/env python3
"""HW7 Part 4.IV - run both acceptance scenarios through the live /api/bike endpoints
(the same path the UI uses) and save each result to reports/hw07/raw/bike_run_<scenario>.json."""

import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[3]
RAW = ROOT / "reports" / "hw07" / "raw"
API = "http://localhost:8470"
URL = "https://capitalbikeshare.com/pricing"
SCENARIOS = {"membership_wins": "heavy_rider.csv", "pay_per_use_wins": "light_rider.csv"}


def main(which: list[str]) -> int:
    c = httpx.Client(base_url=API, timeout=60)
    token = c.post("/auth/login", json={"username": "writer", "password": "WriterPass#2026"}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    bad = 0
    for name in which:
        path = RAW / "bike_data" / SCENARIOS[name]
        print(f"\n=== {name}: {path.name}", flush=True)
        r = c.post("/api/bike/run", headers=h, data={"url": URL},
                   files={"file": (path.name, path.read_bytes(), "text/csv")})
        r.raise_for_status()
        job = r.json()["job_id"]
        seen = 0
        while True:
            j = c.get(f"/api/bike/jobs/{job}", headers=h).json()
            for ev in j["timeline"][seen:]:
                print(f"  [{ev['t_s']:>6}s] #{ev['step']} {ev['tool']} {json.dumps(ev['input'])[:150]} -> "
                      f"{'ok' if ev['success'] else 'ERR'}", flush=True)
            seen = len(j["timeline"])
            if j["status"] in ("done", "error"):
                break
            time.sleep(5)
        if j["status"] == "error":
            print("  JOB ERROR:", j["error"])
            bad += 1
            continue
        res = j["result"]
        (RAW / f"bike_run_{name}.json").write_text(json.dumps(j, indent=2))
        a = res["answer"] or {}
        print(f"  decision={a.get('decision')} stop={res['stop_reason']} steps={res['step_count']} "
              f"time={res['total_time_s']}s checks={res['agent_vs_reference']}", flush=True)
        bad += not all(res["agent_vs_reference"].values())
    return bad


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or list(SCENARIOS)))
