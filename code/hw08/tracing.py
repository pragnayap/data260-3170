"""
HW10 Part 4 - structured spans for the request path.

trace_id IS the HW8 correlation_id (no second identifier). Every stage appends one JSON line to
data/hw10/spans/spans.jsonl:

    {"trace_id", "stage", "start", "end", "start_ms", "end_ms", "duration_ms", "status", "error", ...attrs}

Stages: cache_lookup, inbox, planner, tasks, writer, drafts, reviewer, final, evaluator.
  * planner / writer / reviewer / cache_lookup / evaluator are PROCESSING spans (work done in that component);
  * inbox / tasks / drafts / final are QUEUE spans: produced-at (stamped on the message as sent_at_ms) -> picked-up-at.

Tracing is off unless HW10_TRACE=1, so the HW8 agents and their self-check behave exactly as before.
Each span is written with ONE os.write on an O_APPEND file, which is atomic for lines this short, so the
planner, writer, reviewer, ingress and evaluator processes can share one file.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

ENABLED = os.environ.get("HW10_TRACE") == "1"
SPANS_FILE = Path(os.environ.get(
    "HW10_SPANS", Path(__file__).resolve().parents[2] / "data" / "hw10" / "spans" / "spans.jsonl"))


def now_ms() -> float:
    return time.time() * 1000.0


def iso(ms: float) -> str:
    return dt.datetime.fromtimestamp(ms / 1000.0).astimezone().isoformat(timespec="milliseconds")


def stamp(message: dict[str, Any]) -> dict[str, Any]:
    """Put the produce time on a message so the consumer can compute its queue wait. A no-op unless HW10_TRACE=1, so with
    tracing off every HW8 message is byte-for-byte what it was before HW10."""
    if ENABLED:
        message["sent_at_ms"] = round(now_ms(), 3)
    return message


def write_span(trace_id: str | None, stage: str, start_ms: float, end_ms: float, status: str = "ok",
               error: str | None = None, **attrs: Any) -> dict[str, Any] | None:
    if not ENABLED or not trace_id:
        return None
    span = {"trace_id": trace_id, "stage": stage, "start": iso(start_ms), "end": iso(end_ms),
            "start_ms": round(start_ms, 3), "end_ms": round(end_ms, 3),
            "duration_ms": round(max(end_ms - start_ms, 0.0), 3), "status": status, "error": error, **attrs}
    try:
        SPANS_FILE.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(SPANS_FILE, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(span, separators=(",", ":")) + "\n").encode("utf-8"))
        finally:
            os.close(fd)
    except OSError:
        pass            # tracing must never break the request path
    return span


def queue_span(trace_id: str | None, stage: str, sent_at_ms: float | None, recv_ms: float | None = None,
               **attrs: Any) -> None:
    """Queue wait for one hop: from the producer's stamp to the moment the consumer picked the message up."""
    if sent_at_ms is None:
        return
    write_span(trace_id, stage, float(sent_at_ms), recv_ms if recv_ms is not None else now_ms(), **attrs)


@contextmanager
def span(trace_id: str | None, stage: str, **attrs: Any) -> Iterator[dict[str, Any]]:
    """Time a block. An exception is recorded (status=error, error=<message>) and re-raised."""
    extra: dict[str, Any] = dict(attrs)
    start = now_ms()
    try:
        yield extra
    except Exception as exc:  # noqa: BLE001 - recorded, then re-raised unchanged
        write_span(trace_id, stage, start, now_ms(), status="error", error=f"{type(exc).__name__}: {exc}", **extra)
        raise
    else:
        write_span(trace_id, stage, start, now_ms(), **extra)


def read_spans(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or SPANS_FILE
    out: list[dict[str, Any]] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue                    # a torn or foreign line is skipped, not fatal
    except OSError:
        pass
    return out
