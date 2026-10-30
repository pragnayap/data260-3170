#!/usr/bin/env python3
"""
HW8 Part 2 - "You". Puts a question on s3170_inbox, then waits on s3170_final for the message
that carries the same correlation_id and prints it.

    python code/hw08/send_question.py "What should a rider do when a bus is cancelled?"
"""

from __future__ import annotations

import json
import sys
import time

from kafka_common import (
    FINAL,
    INBOX,
    banner,
    decode,
    ensure_topics,
    log,
    make_consumer,
    make_producer,
    new_id,
    produce,
    student_banner,
    wait_for_assignment,
)

DEFAULT_QUESTION = "What should a rider do when their bus is cancelled and the next one is an hour away?"


def main() -> int:
    question = " ".join(a for a in sys.argv[1:] if not a.startswith("--")) or DEFAULT_QUESTION
    timeout = 900
    student_banner("send_question.py")
    ensure_topics()
    consumer = make_consumer(f"s3170_you_{new_id()[:8]}", [FINAL], reset="latest")
    wait_for_assignment(consumer)
    producer = make_producer()
    correlation_id = new_id()
    partition, offset = produce(producer, INBOX, {"correlation_id": correlation_id, "question": question},
                                key=correlation_id)
    log("YOU", f"SEND  topic={INBOX} partition={partition} offset={offset} correlation_id={correlation_id}")
    log("YOU", f"question: {question}")
    deadline = time.time() + timeout
    while time.time() < deadline:
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            continue
        final = decode(msg.value())
        if final.get("correlation_id") == correlation_id:
            log("YOU", f"RECV  topic={msg.topic()} partition={msg.partition()} offset={msg.offset()} "
                       f"correlation_id={correlation_id}")
            banner("FINAL MESSAGE")
            print(json.dumps(final, indent=2), flush=True)
            consumer.close()
            return 0 if final.get("status") == "approved" else 1
    log("YOU", f"no final message within {timeout}s - are planner, writer and reviewer running?")
    return 2


if __name__ == "__main__":
    sys.exit(main())
