"""
HW7 Part 4 - HTTP front for the bike-share ReAct agent.

    GET  /hw7                 the single-page UI (public HTML; every API call below needs a JWT)
    POST /api/bike/run        multipart: csv file + url  -> {"job_id"}
    GET  /api/bike/jobs/{id}  status, live tool-call timeline, and the final result

The agent takes minutes on a local model, so a run is a background job the page polls.
One job runs at a time (the local model is the bottleneck). The pricing page is captured
at run start and its text, hash and access time are returned as the run's citation.
"""

from __future__ import annotations

import csv
import io
import sys
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from jwt_auth import READ_ROLES, require_roles

BIKE_DIR = Path(__file__).resolve().parents[2] / "hw07" / "bike"
UI_FILE = Path(__file__).resolve().parents[1] / "bike_ui.html"
sys.path.insert(0, str(BIKE_DIR))

import bike_agent  # noqa: E402
import snapshot  # noqa: E402

REQUIRED_COLUMNS = {"started_at", "ended_at", "duration_min"}
MAX_BYTES = 5_000_000

page = APIRouter(tags=["bike-ui"])
router = APIRouter(prefix="/api/bike", tags=["bike"], dependencies=[Depends(require_roles(*READ_ROLES))])

JOBS: dict[str, dict] = {}
_run_lock = threading.Lock()


@page.get("/hw7", include_in_schema=False)
def ui():
    return FileResponse(UI_FILE)


def _validate_csv(text: str) -> int:
    reader = csv.DictReader(io.StringIO(text))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
    if missing:
        raise HTTPException(422, f"CSV is missing columns: {', '.join(sorted(missing))}")
    rows = sum(1 for _ in reader)
    if rows == 0:
        raise HTTPException(422, "CSV has no trip rows")
    return rows


def _work(job_id: str, csv_text: str, url: str) -> None:
    job = JOBS[job_id]
    with _run_lock:
        job["status"] = "running"
        try:
            meta = snapshot.freeze(url, f"run_{job_id}")
            result = bike_agent.run_bike_agent(
                csv_text, url, snapshot=meta, on_event=lambda ev: job["timeline"].append(ev))
            job["result"], job["status"] = result, "done"
        except Exception as exc:  # noqa: BLE001 - a job must always end in a state
            job["status"], job["error"] = "error", f"{type(exc).__name__}: {exc}"


@router.post("/run")
async def run(file: UploadFile = File(...), url: str = Form("")):
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "CSV larger than 5 MB")
    text = raw.decode("utf-8-sig", errors="replace")
    rows = _validate_csv(text)
    if not url.startswith("https://"):
        raise HTTPException(422, "pricing URL must be an https:// address")
    job_id = uuid.uuid4().hex[:8]
    JOBS[job_id] = {"status": "queued", "rows": rows, "timeline": [], "result": None}
    threading.Thread(target=_work, args=(job_id, text, url), daemon=True).start()
    return {"job_id": job_id, "rows": rows}


@router.get("/jobs/{job_id}")
def job(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(404, "no such job")
    return JOBS[job_id]
