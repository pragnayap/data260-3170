#!/usr/bin/env python3
"""
HW8 Part 2 - Planner. Reads s3170_inbox (a question), writes s3170_tasks (a plan).
It never calls the Writer: the plan is a Kafka message, keyed by correlation_id.
"""

from __future__ import annotations

import json
import os
import re
import signal
import sys

from kafka_common import (
    INBOX,
    PREFIX,
    TASKS,
    decode,
    ensure_topics,
    log,
    make_consumer,
    make_producer,
    produce,
)
from llm import complete


def make_plan(question: str) -> list[str]:
    if os.environ.get("PLANNER_MODE") == "stub":      # fast canned plan for the self-check
        return ["Restate the question", "Give the key facts", "Summarise in two sentences"]
    reply = complete("Break this question into exactly 3 short steps for writing a good answer. "
                     "Reply with only a JSON array of 3 strings.\nQuestion: " + question, max_tokens=150)
    match = re.search(r"\[.*\]", reply)
    try:
        steps = [str(s) for s in json.loads(match.group(0))] if match else []
    except ValueError:
        steps = []
    return steps[:5] or ["Restate the question", "Give the key facts", "Summarise in two sentences"]


def main() -> int:
    ensure_topics()
    producer = make_producer()
    running = {"go": True}
    signal.signal(signal.SIGINT, lambda *_: running.update(go=False))
    signal.signal(signal.SIGTERM, lambda *_: running.update(go=False))
    consumer = make_consumer(os.environ.get("GROUP", f"{PREFIX}_planner"), [INBOX], reset=os.environ.get("RESET", "earliest"),
                             on_ready=lambda p: log("PLANNER", f"ready - listening on {INBOX}"))
    try:
        while running["go"]:
            msg = consumer.poll(1.0)
            if msg is None or msg.error():
                continue
            try:
                incoming = decode(msg.value())
                correlation_id, question = incoming["correlation_id"], incoming["question"]
            except (ValueError, KeyError):
                log("PLANNER", f"RECV  topic={msg.topic()} offset={msg.offset()} unreadable message - skipped")
                consumer.commit(message=msg, asynchronous=False)
                continue
            log("PLANNER", f"RECV  topic={msg.topic()} partition={msg.partition()} offset={msg.offset()} "
                           f"correlation_id={correlation_id} question={question!r}")
            plan = make_plan(question)
            log("PLANNER", f"PLAN  correlation_id={correlation_id} steps={plan}")
            partition, offset = produce(producer, TASKS, {"correlation_id": correlation_id, "question": question,
                                                          "plan": plan}, key=correlation_id)
            log("PLANNER", f"SEND  topic={TASKS} partition={partition} offset={offset} correlation_id={correlation_id}")
            consumer.commit(message=msg, asynchronous=False)
    finally:
        consumer.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
