"""
HW8 - shared Kafka plumbing: fixed configuration, topic names, JSON helpers, one log format.

Every component (worker, API, agents, demo) logs through log() so a single grep on a
correlation_id reconstructs a message's whole journey in order.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import uuid
from typing import Any, Callable

from confluent_kafka import Consumer, KafkaException, Producer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

# --- Section 0, fixed for the semester ------------------------------------------------
SID4, PORT_BASE, PREFIX, SEED, VERIFY_SEED, DOMAIN_ID = 3170, 8470, "s3170", 3170, 263170, 2

# 127.0.0.1:9092 from the host, kafka:29092 from inside the compose network.
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "localhost:9092")

# Part 1: exactly two topics.
REQUESTS = f"{PREFIX}_entity_requests"
RESPONSES = f"{PREFIX}_entity_responses"
# Part 2 pipeline + Part 3 dead letter.
INBOX, TASKS, DRAFTS, FINAL = (f"{PREFIX}_{n}" for n in ("inbox", "tasks", "drafts", "final"))
DEAD_LETTER = f"{PREFIX}_dead_letter"

TOPIC_PARTITIONS = {REQUESTS: 1, RESPONSES: 1, INBOX: 1, TASKS: 2, DRAFTS: 1, FINAL: 1, DEAD_LETTER: 1}


def now() -> str:
    return dt.datetime.now().strftime("%H:%M:%S.%f")[:-3]


def log(component: str, message: str) -> None:
    print(f"{now()} [{component:<8}] {message}", flush=True)


def new_id() -> str:
    return str(uuid.uuid4())


def encode(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, separators=(",", ":")).encode("utf-8")


def decode(raw: bytes | None) -> dict[str, Any]:
    return json.loads(raw.decode("utf-8")) if raw else {}


def ensure_topics(partitions: dict[str, int] | None = None, retries: int = 30) -> None:
    """Create any missing topic (idempotent). Waits for the broker, which can be slow to boot."""
    wanted = partitions or TOPIC_PARTITIONS
    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    for attempt in range(retries):
        try:
            existing = set(admin.list_topics(timeout=5).topics)
            break
        except KafkaException:
            log("KAFKA", f"broker not ready at {BOOTSTRAP} (attempt {attempt + 1}/{retries}); waiting")
            time.sleep(2)
    else:
        raise RuntimeError(f"Kafka not reachable at {BOOTSTRAP}")
    missing = [NewTopic(t, num_partitions=n, replication_factor=1) for t, n in wanted.items() if t not in existing]
    for topic, future in admin.create_topics(missing).items() if missing else []:
        try:
            future.result()
            log("KAFKA", f"created topic {topic} ({wanted[topic]} partition(s))")
        except KafkaException as exc:       # another process created it first
            log("KAFKA", f"topic {topic}: {exc.args[0].str()}")


def make_producer(**extra: Any) -> Producer:
    return Producer({"bootstrap.servers": BOOTSTRAP, "linger.ms": 0, **extra})


def produce(producer: Producer, topic: str, value: dict[str, Any], key: str | None = None,
            partition: int | None = None) -> tuple[int, int]:
    """Send one JSON message and wait for the broker's ack. Returns (partition, offset)."""
    result: dict[str, Any] = {}

    def on_delivery(err, msg):
        result["err"], result["partition"], result["offset"] = err, msg.partition(), msg.offset()

    kwargs: dict[str, Any] = {"value": encode(value), "callback": on_delivery}
    if key is not None:
        kwargs["key"] = key.encode("utf-8")
    if partition is not None:
        kwargs["partition"] = partition
    producer.produce(topic, **kwargs)
    producer.flush(15)
    if result.get("err"):
        raise RuntimeError(f"delivery to {topic} failed: {result['err']}")
    return result["partition"], result["offset"]


def make_consumer(group: str, topics: list[str], *, auto_commit: bool = False, reset: str = "latest",
                  on_ready: Callable[[list[TopicPartition]], None] | None = None) -> Consumer:
    """A consumer that commits offsets only when told to (unless auto_commit)."""
    cfg = {"bootstrap.servers": BOOTSTRAP, "group.id": group, "auto.offset.reset": reset,
           "enable.auto.commit": auto_commit, "session.timeout.ms": 10000,
           "partition.assignment.strategy": "roundrobin"}
    if auto_commit:
        cfg["auto.commit.interval.ms"] = 500
    consumer = Consumer(cfg)

    def assigned(c, partitions):
        if reset == "latest":
            # "latest" is resolved lazily by the client, a moment AFTER this callback - so a message sent right
            # after the "ready" line could be skipped. Pin the start position now, to the end of each partition
            # that has no committed offset, so "ready" really means "will see everything sent from here on".
            committed = c.committed(partitions, timeout=10)
            for tp in committed:
                if tp.offset < 0:
                    _, tp.offset = c.get_watermark_offsets(TopicPartition(tp.topic, tp.partition), timeout=10)
            c.assign(committed)
            partitions = committed
        if on_ready:
            on_ready(partitions)

    consumer.subscribe(topics, on_assign=assigned)
    return consumer


def wait_for_assignment(consumer: Consumer, timeout: float = 30.0) -> None:
    """Poll until the group coordinator has handed this consumer its partitions."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        consumer.poll(0.2)
        if consumer.assignment():
            return
    raise RuntimeError("consumer was never assigned partitions")


def banner(title: str) -> None:
    print("\n" + "=" * 100 + f"\n{title}\n" + "=" * 100, flush=True)


def student_banner(label: str) -> None:
    """Prints the student's name so it is in every terminal screenshot."""
    print(f"Pragnaya Priyadarshini HW8 - {label}", flush=True)


if __name__ == "__main__":
    print(f"PREFIX={PREFIX} PORT_BASE={PORT_BASE} bootstrap={BOOTSTRAP}", file=sys.stderr)
    ensure_topics()
