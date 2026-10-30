#!/usr/bin/env python3
"""
HW8 Parts 2-3 - Writer. Reads s3170_tasks (a plan), writes s3170_drafts (a draft answer).

The defaults are the FIXED behaviour. Part 3's "before fix" runs turn one mechanism off with an
environment variable, so the same file shows both sides of every failure:

  IDEMPOTENT=1|0     skip a correlation_id already completed (state survives a restart)
  COMMIT=after|auto  commit the offset only after the draft is delivered | let the client auto-commit
  MAX_RETRIES=3      bounded retries on a failing message, then dead-letter it. 0 = retry forever
  DLQ=1|0            publish exhausted messages to s3170_dead_letter and move on
  WRITER_MODE=llm|stub   real local-model draft | instant canned draft (failure tests need speed)
  WRITER_ID, GROUP, RESET, STATE_DIR, SIDE_EFFECT_LOG, PROCESS_LOG   per-run plumbing

Order of operations for one message (the whole point of the offset rule):
    process -> deliver draft -> record side effect + mark processed -> COMMIT the offset
A crash anywhere before the commit means the broker redelivers the message to a restarted writer.
"""

from __future__ import annotations

import csv
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

from kafka_common import (
    DEAD_LETTER,
    DRAFTS,
    PREFIX,
    TASKS,
    decode,
    ensure_topics,
    log,
    make_consumer,
    make_producer,
    now,
    produce,
)

WRITER_ID = os.environ.get("WRITER_ID", "writer-1")
GROUP = os.environ.get("GROUP", f"{PREFIX}_writer")
MODE = os.environ.get("WRITER_MODE", "llm")
IDEMPOTENT = os.environ.get("IDEMPOTENT", "1") == "1"
COMMIT = os.environ.get("COMMIT", "after")
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
DLQ = os.environ.get("DLQ", "1") == "1"
RESET = os.environ.get("RESET", "earliest")
STATE_DIR = Path(os.environ.get("STATE_DIR", Path(__file__).resolve().parents[2] / "data" / "hw08_state"))
SIDE_EFFECT_LOG = Path(os.environ.get("SIDE_EFFECT_LOG", STATE_DIR / f"side_effects_{GROUP}.log"))
PROCESS_LOG = os.environ.get("PROCESS_LOG")

STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = STATE_DIR / f"processed_{GROUP}.log"      # one correlation_id per line, append-only


# --- idempotency state ---------------------------------------------------------------
def load_processed() -> set[str]:
    try:
        return {ln.strip() for ln in STATE_FILE.read_text().splitlines() if ln.strip()}
    except OSError:
        return set()


def mark_processed(processed: set[str], correlation_id: str) -> None:
    """Append one line. Appends of a short line are atomic, so several Writers in one group can share this file
    without the rename race a rewrite-the-whole-file design has (which this file once suffered, see the README)."""
    with STATE_FILE.open("a") as fh:
        fh.write(correlation_id + "\n")
        fh.flush()
        os.fsync(fh.fileno())
    processed.add(correlation_id)


# --- the work --------------------------------------------------------------------------
def write_draft(task: dict[str, Any]) -> str:
    plan = task.get("plan")
    if not isinstance(plan, list) or not plan:
        raise ValueError("task has no plan")           # the poison-message trigger
    question = task.get("question", "")
    if MODE == "stub":
        return f"[stub draft] Answer to '{question}' following the plan: " + "; ".join(map(str, plan))
    from llm import complete
    return complete(f"Question: {question}\nPlan: {json.dumps(plan)}\n"
                    "Write a concise answer of about 3 sentences that follows the plan.", max_tokens=220)


def work(task: dict[str, Any]) -> dict[str, Any]:
    slow = task.get("simulate_slow_ms")
    if slow:
        log(WRITER_ID, f"WORKING correlation_id={task.get('correlation_id')} - busy for {slow} ms "
                       "(kill this process now to simulate a crash mid-work)")
        time.sleep(slow / 1000)
    if task.get("work_ms"):
        time.sleep(task["work_ms"] / 1000)
    text = write_draft(task)
    passthrough = {k: task[k] for k in ("entity", "seq", "run") if k in task}
    return {"correlation_id": task["correlation_id"], "question": task.get("question"), "draft": text,
            "writer": WRITER_ID, **passthrough}


def record_side_effect(correlation_id: str) -> None:
    with SIDE_EFFECT_LOG.open("a") as fh:
        fh.write(f"{now()} {WRITER_ID} draft_written correlation_id={correlation_id}\n")


def record_order(msg, task: dict[str, Any]) -> None:
    if not PROCESS_LOG:
        return
    path = Path(PROCESS_LOG)
    new = not path.exists()
    with path.open("a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["time", "writer", "partition", "offset", "entity", "seq", "correlation_id"])
        w.writerow([now(), WRITER_ID, msg.partition(), msg.offset(), task.get("entity"), task.get("seq"),
                    task.get("correlation_id")])


# --- main loop ---------------------------------------------------------------------------
def main() -> int:
    ensure_topics()
    producer = make_producer()
    processed = load_processed()
    running = {"go": True}
    signal.signal(signal.SIGINT, lambda *_: running.update(go=False))
    signal.signal(signal.SIGTERM, lambda *_: running.update(go=False))

    def ready(parts):
        log(WRITER_ID, f"Consumer is ready and listening... group={GROUP} partitions={sorted(p.partition for p in parts)} "
                       f"mode={MODE} idempotent={int(IDEMPOTENT)} commit={COMMIT} max_retries={MAX_RETRIES} dlq={int(DLQ)}")

    consumer = make_consumer(GROUP, [TASKS], auto_commit=(COMMIT == "auto"), reset=RESET, on_ready=ready)
    try:
        while running["go"]:
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            raw = msg.value()
            task: dict[str, Any] = {}
            where = f"topic={msg.topic()} partition={msg.partition()} offset={msg.offset()}"
            try:
                task = decode(raw)
            except ValueError:
                pass
            correlation_id = task.get("correlation_id")
            extra = f" entity={task['entity']} seq={task['seq']}" if "entity" in task else ""
            log(WRITER_ID, f"RECV  {where} correlation_id={correlation_id}{extra}")

            if IDEMPOTENT and correlation_id in processed:
                log(WRITER_ID, f"DUPLICATE correlation_id={correlation_id} already completed - ignored, no side effect")
                if COMMIT == "after":
                    consumer.commit(message=msg, asynchronous=False)
                continue

            attempts, delivered = 0, False
            while True:
                try:
                    if not task:
                        raise ValueError("message is not valid JSON")
                    draft = work(task)
                    partition, offset = produce(producer, DRAFTS, draft, key=correlation_id)
                    log(WRITER_ID, f"SEND  topic={DRAFTS} partition={partition} offset={offset} correlation_id={correlation_id}")
                    delivered = True
                    break
                except Exception as exc:  # noqa: BLE001 - any failure of one message is handled, never fatal
                    attempts += 1
                    if MAX_RETRIES == 0:
                        log(WRITER_ID, f"RETRY {where} attempt {attempts} (no limit) error={exc}")
                        time.sleep(1.0)
                        continue
                    if attempts < MAX_RETRIES:
                        log(WRITER_ID, f"RETRY {where} attempt {attempts}/{MAX_RETRIES} error={exc}")
                        time.sleep(0.3 * attempts)
                        continue
                    log(WRITER_ID, f"GIVE UP {where} after {attempts} attempts error={exc}")
                    if DLQ:
                        dead = {"correlation_id": correlation_id, "error": str(exc), "attempts": attempts,
                                "source": {"topic": msg.topic(), "partition": msg.partition(), "offset": msg.offset()},
                                "original": raw.decode("utf-8", "replace") if raw else None}
                        p, o = produce(producer, DEAD_LETTER, dead, key=correlation_id)
                        log(WRITER_ID, f"DEAD-LETTER topic={DEAD_LETTER} partition={p} offset={o} correlation_id={correlation_id}")
                    break
            if delivered:
                # Bookkeeping AFTER delivery and OUTSIDE the retry loop: if it fails it is logged, never re-run
                # the work (re-running would deliver the draft a second time).
                try:
                    record_side_effect(correlation_id)
                    record_order(msg, task)
                    mark_processed(processed, correlation_id)
                except OSError as exc:
                    log(WRITER_ID, f"WARNING bookkeeping failed for correlation_id={correlation_id}: {exc}")
            if COMMIT == "after":
                consumer.commit(message=msg, asynchronous=False)       # only now: the work is done
                log(WRITER_ID, f"COMMIT offset {msg.offset() + 1} on partition {msg.partition()} (after successful processing)")
    finally:
        consumer.close()
        log(WRITER_ID, "writer stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
