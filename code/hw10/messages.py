# ruff: noqa: I001  (import order matters: common10 puts hw08 on sys.path before kafka_common is imported)
"""
HW10 Part 2.1 - collect the Planner plan, Writer draft and Reviewer final answer that share a correlation_id.

Reads s3170_tasks (plan), s3170_drafts (draft) and s3170_final (final) from the beginning with a throw-away
consumer group, and joins them on correlation_id. The ORIGINAL message bodies plus the Kafka metadata
(topic, partition, offset, broker timestamp, producer sent_at_ms) are kept so an evaluation can be reproduced.

Bounded on purpose: the whole read stops at `timeout` seconds, or after `idle` seconds with nothing new once
every wanted id is complete - a missing message can never hang a run.
"""
from __future__ import annotations

import time
from typing import Any

import common10 as c  # noqa: F401  (puts hw08 on sys.path)
from kafka_common import BOOTSTRAP, DRAFTS, FINAL, TASKS, decode, new_id
from confluent_kafka import Consumer

TOPIC_ROLE = {TASKS: "plan", DRAFTS: "draft", FINAL: "final"}


def collect(ids: set[str] | None, timeout: float = 60.0, idle: float = 8.0) -> dict[str, dict[str, Any]]:
    """Return {correlation_id: {"plan": msg, "draft": msg, "final": msg}} for `ids` (all ids if None).
    Each msg = {"body": <original JSON>, "meta": {topic, partition, offset, kafka_ts_ms, sent_at_ms}}."""
    consumer = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": f"{c.PREFIX}_hw10_collect_{new_id()[:8]}",
                         "auto.offset.reset": "earliest", "enable.auto.commit": False})
    consumer.subscribe(list(TOPIC_ROLE))
    out: dict[str, dict[str, Any]] = {}
    deadline, last_new = time.time() + timeout, time.time()
    try:
        while time.time() < deadline:
            m = consumer.poll(1.0)
            if m is None or m.error():
                if ids and time.time() - last_new > idle and all(len(out.get(i, {})) == 3 for i in ids):
                    break
                if time.time() - last_new > idle * 3:       # nothing arriving for a long time: stop with what we have
                    break
                continue
            try:
                body = decode(m.value())
            except ValueError:
                continue                                      # malformed message: skipped, never fatal
            cid = body.get("correlation_id")
            if not cid or (ids is not None and cid not in ids):
                continue
            role = TOPIC_ROLE[m.topic()]
            out.setdefault(cid, {})[role] = {"body": body, "meta": {
                "topic": m.topic(), "partition": m.partition(), "offset": m.offset(),
                "kafka_ts_ms": m.timestamp()[1], "sent_at_ms": body.get("sent_at_ms")}}
            last_new = time.time()
    finally:
        consumer.close()
    return out
