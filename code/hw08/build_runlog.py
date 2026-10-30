#!/usr/bin/env python3
"""HW8 - assemble reports/hw08/RUN_LOG.txt from the real console logs the runs wrote (nothing re-typed)."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "reports" / "hw08" / "raw"
OUT = REPO / "reports" / "hw08" / "RUN_LOG.txt"
NOISE = re.compile(r"warning|urllib3|NotOpenSSL|warnings\.warn", re.IGNORECASE)

SECTIONS = [
    ("Part 1 - docker ps, worker 'Consumer is ready and listening...' and API start lines", "part1_docker_evidence.txt"),
    ("Part 1 - homework_demo.py: CREATE_INCIDENT -> GET_INCIDENT with worker log lines", "part1_demo_run.txt"),
    ("Part 1 - FastAPI wrapper over HTTP (each call is a Kafka request/response)", "part1_api_run.txt"),
    ("Part 2 - the seven s3170_* topics (Kafka CLI)", "part2_topics.txt"),
    ("Part 2 - one complete message journey inbox -> tasks -> drafts -> final", "pipeline_journey.txt"),
    ("Part 2 - Planner process log", "logs/pipeline_planner.log"),
    ("Part 2 - Writer process log", "logs/pipeline_writer.log"),
    ("Part 2 - Reviewer process log", "logs/pipeline_reviewer.log"),
    ("Part 2 - send_question.py log", "logs/pipeline_send_question.log"),
    ("Part 3 - duplicate, consumer death, poison message, ordering (before and after each fix)", "failure_tests_run_raw.txt"),
    ("Self-check - make verify-hw08", "verify_hw08_run.txt"),
]
DEV = sorted(f"dev_history/{p.name}" for p in (RAW / "dev_history").glob("*.txt"))


def clean(text: str) -> str:
    return "\n".join(ln for ln in text.splitlines() if not NOISE.search(ln)).strip()


def main() -> None:
    parts = ["HW8 RUN LOG - Pragnaya Priyadarshini, SID4 3170",
             "Real console output of the runs behind the reported results (filtered only for Python warning lines).", ""]
    for title, name in SECTIONS + [(f"Development history - {n}", n) for n in DEV]:
        path = RAW / name
        body = clean(path.read_text(errors="ignore")) if path.exists() else "(log file not present)"
        parts += ["=" * 100, title, f"source: reports/hw08/raw/{name}", "=" * 100, body, ""]
    OUT.write_text("\n".join(parts))
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
