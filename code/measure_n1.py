#!/usr/bin/env python3
"""
HW4 Part 3 - N+1 measurement.

Hits GET /api/incidents?impl=naive|fixed at page sizes 10/50/200, 30 requests
each (180 total), and records the SQL statement count the server reports via
the X-SQL-Statements response header (see database.py's query counter) plus
client-observed latency. Raw rows go to reports/hw04/raw/n1_requests.csv; the
p50/p95/p99 summary goes to reports/hw04/raw/n1_summary.{json,md}.

Requires the backend running on PORT_BASE (8470) and a seeded database
(run seed_hw04.py first). Logs in as the measurement user, creating it via
signup if it doesn't exist yet.

Run:
    .venv/bin/python code/measure_n1.py
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE = "http://127.0.0.1:8470"
PAGE_SIZES = [10, 50, 200]
IMPLS = ["naive", "fixed"]
REQUESTS_PER_CONFIG = 30

MEASURE_EMAIL = "n1-measure@example.com"
# Kept out of the repo: set S3170_N1_PASSWORD in code/web_application/.env (see .env.example).
load_dotenv(Path(__file__).parent / "web_application" / ".env")
MEASURE_PASSWORD = os.environ.get("S3170_N1_PASSWORD", "")
MEASURE_NAME = "N1 Measurement Bot"

REPORT_DIR = Path(__file__).parent.parent / "reports" / "hw04" / "raw"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def ensure_session() -> requests.Session:
    if not MEASURE_PASSWORD:
        sys.exit("S3170_N1_PASSWORD is not set -- add it to code/web_application/.env")
    session = requests.Session()
    resp = session.post(
        f"{BASE}/api/auth/login",
        json={"email": MEASURE_EMAIL, "password": MEASURE_PASSWORD},
    )
    if resp.status_code == 200:
        log(f"logged in as {MEASURE_EMAIL}")
        return session

    log(f"login failed ({resp.status_code}), signing up {MEASURE_EMAIL}")
    signup = session.post(
        f"{BASE}/api/auth/signup",
        json={"name": MEASURE_NAME, "email": MEASURE_EMAIL, "password": MEASURE_PASSWORD},
    )
    if signup.status_code not in (201, 409):
        raise RuntimeError(f"signup failed: {signup.status_code} {signup.text}")

    resp = session.post(
        f"{BASE}/api/auth/login",
        json={"email": MEASURE_EMAIL, "password": MEASURE_PASSWORD},
    )
    resp.raise_for_status()
    log(f"logged in as {MEASURE_EMAIL}")
    return session


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * (pct / 100)
    f, c = int(k), min(int(k) + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    session = ensure_session()

    try:
        health = session.get(f"{BASE}/api/incidents", params={"page": 1, "page_size": 1})
        total = health.json().get("total", 0)
        log(f"backend reachable, {total} incidents in DB")
        if total < 200:
            log("WARNING: fewer than 200 incidents seeded -- run seed_hw04.py first")
    except requests.ConnectionError:
        log(f"ERROR: cannot reach {BASE} -- is uvicorn running?")
        sys.exit(1)

    raw_rows = []

    for page_size in PAGE_SIZES:
        for impl in IMPLS:
            log(f"measuring page_size={page_size} impl={impl} ({REQUESTS_PER_CONFIG} requests)")
            for i in range(REQUESTS_PER_CONFIG):
                t0 = time.perf_counter()
                resp = session.get(
                    f"{BASE}/api/incidents",
                    params={"page": 1, "page_size": page_size, "impl": impl},
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000
                resp.raise_for_status()
                sql_statements = int(resp.headers.get("X-SQL-Statements", -1))
                raw_rows.append(
                    {
                        "page_size": page_size,
                        "impl": impl,
                        "request_index": i,
                        "sql_statements": sql_statements,
                        "latency_ms": round(elapsed_ms, 3),
                        "status_code": resp.status_code,
                    }
                )

    csv_path = REPORT_DIR / "n1_requests.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(raw_rows[0].keys()))
        writer.writeheader()
        writer.writerows(raw_rows)
    log(f"wrote {len(raw_rows)} raw rows -> {csv_path}")

    summary = []
    for page_size in PAGE_SIZES:
        for impl in IMPLS:
            subset = [r for r in raw_rows if r["page_size"] == page_size and r["impl"] == impl]
            latencies = [r["latency_ms"] for r in subset]
            sql_counts = {r["sql_statements"] for r in subset}
            summary.append(
                {
                    "page_size": page_size,
                    "impl": impl,
                    "sql_statements_per_request": sorted(sql_counts),
                    "p50_ms": round(percentile(latencies, 50), 2),
                    "p95_ms": round(percentile(latencies, 95), 2),
                    "p99_ms": round(percentile(latencies, 99), 2),
                    "mean_ms": round(statistics.mean(latencies), 2),
                }
            )

    json_path = REPORT_DIR / "n1_summary.json"
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)
    log(f"wrote summary -> {json_path}")

    md_path = REPORT_DIR / "n1_summary.md"
    with open(md_path, "w") as f:
        f.write("| Page size | Version | SQL stmts/req | p50 (ms) | p95 (ms) | p99 (ms) |\n")
        f.write("|---|---|---|---|---|---|\n")
        for row in summary:
            stmts = ",".join(str(s) for s in row["sql_statements_per_request"])
            f.write(
                f"| {row['page_size']} | {row['impl']} | {stmts} | "
                f"{row['p50_ms']} | {row['p95_ms']} | {row['p99_ms']} |\n"
            )

        f.write("\n### Speed-up (fixed vs. naive), by page size\n\n")
        for page_size in PAGE_SIZES:
            naive = next(r for r in summary if r["page_size"] == page_size and r["impl"] == "naive")
            fixed = next(r for r in summary if r["page_size"] == page_size and r["impl"] == "fixed")
            speedup = naive["p50_ms"] / fixed["p50_ms"] if fixed["p50_ms"] else float("inf")
            f.write(
                f"- page_size={page_size}: naive p50={naive['p50_ms']}ms, "
                f"fixed p50={fixed['p50_ms']}ms -> **{speedup:.2f}x** faster\n"
            )
    log(f"wrote markdown summary -> {md_path}")

    print()
    print(open(md_path).read())


if __name__ == "__main__":
    main()
