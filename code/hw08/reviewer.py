#!/usr/bin/env python3
"""
HW8 Part 2 - Reviewer. Reads s3170_drafts, writes the verdict to s3170_final as
{"correlation_id", "status": "approved"|"rejected", "answer": ...}.

The review is rule-based on purpose (non-empty, sensible length, not a refusal or a placeholder):
the point of this homework is the Kafka coordination, and a deterministic reviewer keeps the final
message reproducible.
"""

from __future__ import annotations

import os
import signal
import sys

from kafka_common import (
    DRAFTS,
    FINAL,
    PREFIX,
    decode,
    ensure_topics,
    log,
    make_consumer,
    make_producer,
    produce,
)

MIN_CHARS, MAX_CHARS = 40, 2000
BAD_PHRASES = ("todo", "lorem ipsum", "as an ai language model")


def review(draft: str) -> tuple[str, str]:
    text = (draft or "").strip()
    if len(text) < MIN_CHARS:
        return "rejected", f"draft too short ({len(text)} < {MIN_CHARS} characters)"
    if len(text) > MAX_CHARS:
        return "rejected", f"draft too long ({len(text)} > {MAX_CHARS} characters)"
    for phrase in BAD_PHRASES:
        if phrase in text.lower():
            return "rejected", f"draft contains placeholder text: {phrase!r}"
    return "approved", "draft passes length and content checks"


def main() -> int:
    ensure_topics()
    producer = make_producer()
    running = {"go": True}
    signal.signal(signal.SIGINT, lambda *_: running.update(go=False))
    signal.signal(signal.SIGTERM, lambda *_: running.update(go=False))
    consumer = make_consumer(os.environ.get("GROUP", f"{PREFIX}_reviewer"), [DRAFTS], reset=os.environ.get("RESET", "earliest"),
                             on_ready=lambda p: log("REVIEWER", f"ready - listening on {DRAFTS}"))
    try:
        while running["go"]:
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            try:
                draft = decode(msg.value())
                correlation_id = draft["correlation_id"]
            except (ValueError, KeyError):
                log("REVIEWER", f"RECV  topic={msg.topic()} offset={msg.offset()} unreadable message - skipped")
                consumer.commit(message=msg, asynchronous=False)
                continue
            log("REVIEWER", f"RECV  topic={msg.topic()} partition={msg.partition()} offset={msg.offset()} "
                            f"correlation_id={correlation_id}")
            status, reason = review(draft.get("draft", ""))
            log("REVIEWER", f"REVIEW correlation_id={correlation_id} status={status} ({reason})")
            final = {"correlation_id": correlation_id, "status": status,
                     "answer": draft.get("draft") if status == "approved" else None, "reason": reason}
            partition, offset = produce(producer, FINAL, final, key=correlation_id)
            log("REVIEWER", f"SEND  topic={FINAL} partition={partition} offset={offset} correlation_id={correlation_id}")
            consumer.commit(message=msg, asynchronous=False)
    finally:
        consumer.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
