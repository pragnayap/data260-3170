#!/usr/bin/env python3
"""
HW8 Part 3 - failure behaviour, each scenario run BEFORE and AFTER its fix against real Kafka.

    python code/hw08/failure_tests.py duplicate | death | poison | ordering | all

Every scenario starts real writer.py processes (the same file Part 2 uses) with one mechanism
switched off ("before") or on ("after") through environment variables, then reads what the broker
and the writer's own side-effect log say happened. Logs land in reports/hw08/raw/logs/ and the
machine-readable results in reports/hw08/raw/. The writers use WRITER_MODE=stub: these tests are
about Kafka behaviour, not about model quality, and stub drafts keep each run to seconds.
"""

from __future__ import annotations

import csv
import json
import os
import random
import signal
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from kafka_common import (
    DEAD_LETTER,
    DRAFTS,
    TASKS,
    VERIFY_SEED,
    banner,
    decode,
    ensure_topics,
    log,
    make_consumer,
    make_producer,
    new_id,
    produce,
    student_banner,
)

HERE = Path(__file__).resolve().parent
RAW = HERE.parents[1] / "reports" / "hw08" / "raw"
STATE = HERE.parents[1] / "data" / "hw08_state"
# FAILURE_TAG lets verify_hw08.py run this suite without overwriting the reported evidence: tagged runs write
# their summary/CSVs with the tag in the name and their process logs under data/ (not committed).
TAG = os.environ.get("FAILURE_TAG", "")
LOGS = (STATE / "verify_logs") if TAG else (RAW / "logs")
RUN = time.strftime("%m%d%H%M%S")
KAFKA_CONTAINER = "s3170_kafka"


# --- process + broker helpers -----------------------------------------------------------
class Writer:
    """A real writer.py subprocess whose stdout goes to a log file we can read back."""

    def __init__(self, test: str, phase: str, writer_id: str, group: str, **env: str):
        LOGS.mkdir(parents=True, exist_ok=True)
        self.path = LOGS / f"{test}_{phase}_{writer_id}_{time.strftime('%H%M%S')}.log"
        self.writer_id = writer_id
        full = {**os.environ, "WRITER_ID": writer_id, "GROUP": group, "WRITER_MODE": "stub", "RESET": "latest",
                "STATE_DIR": str(STATE / f"{test}_{RUN}"), "PYTHONUNBUFFERED": "1", **env}
        self.out = self.path.open("w")
        self.proc = subprocess.Popen([sys.executable, str(HERE / "writer.py")], env=full, cwd=HERE,
                                     stdout=self.out, stderr=subprocess.STDOUT)

    def text(self) -> str:
        self.out.flush()
        return self.path.read_text()

    def wait_for(self, needle: str, timeout: float = 60, count: int = 1) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.text().count(needle) >= count:
                return True
            if self.proc.poll() is not None and needle not in self.text():
                return False
            time.sleep(0.2)
        return False

    def kill(self) -> None:
        self.proc.send_signal(signal.SIGKILL)
        self.proc.wait()
        log("TEST", f"{self.writer_id}: SIGKILL sent (process died without cleaning up)")

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.out.close()

    def lines(self, *needles: str) -> list[str]:
        return [ln for ln in self.text().splitlines() if any(n in ln for n in needles)]


def show(title: str, lines: list[str], limit: int = 14) -> None:
    print(f"  --- {title}", flush=True)
    for ln in lines[:limit]:
        print(f"      {ln}", flush=True)
    if len(lines) > limit:
        print(f"      ... ({len(lines) - limit} more)", flush=True)


def describe_group(group: str) -> list[str]:
    """`kafka-consumer-groups --describe`: committed offset, log-end offset and lag per partition."""
    cmd = ["docker", "exec", KAFKA_CONTAINER, "/opt/kafka/bin/kafka-consumer-groups.sh",
           "--bootstrap-server", "localhost:9092", "--describe", "--group", group]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return [ln for ln in (out.stdout + out.stderr).splitlines() if ln.strip() and "WARN" not in ln]


def read_topic(topic: str, keep, quiet_s: float = 3.0, max_s: float = 25.0) -> list[dict[str, Any]]:
    """Read a topic from the start with a throwaway group and keep messages where keep(msg) is true."""
    consumer = make_consumer(f"s3170_reader_{new_id()[:8]}", [topic], reset="earliest")
    found, last, start = [], time.time(), time.time()
    try:
        while time.time() - start < max_s and time.time() - last < quiet_s:
            msg = consumer.poll(0.5)
            if msg is None or msg.error():
                continue
            last = time.time()
            try:
                body = decode(msg.value())
            except ValueError:
                body = {"_raw": msg.value().decode("utf-8", "replace")}
            if keep(body):
                found.append({**body, "_partition": msg.partition(), "_offset": msg.offset()})
    finally:
        consumer.close()
    return found


def task(correlation_id: str, **extra: Any) -> dict[str, Any]:
    return {"correlation_id": correlation_id, "question": "Why is the 22 bus late?",
            "plan": ["Check the schedule", "Report the delay", "Suggest an alternative"], **extra}


def side_effects(test: str, group: str) -> list[str]:
    path = STATE / f"{test}_{RUN}" / f"side_effects_{group}.log"
    return path.read_text().splitlines() if path.exists() else []


# --- 1. duplicate delivery ---------------------------------------------------------------
def duplicate() -> dict[str, Any]:
    banner("PART 3.I  DUPLICATE DELIVERY - replay one message with the same correlation_id")
    producer, result = make_producer(), {}
    for phase, idempotent in (("before", "0"), ("after", "1")):
        group = f"s3170_dup_{phase}_{RUN}"
        correlation_id = f"dup-{phase}-{RUN}"
        writer = Writer("duplicate", phase, "writer-1", group, IDEMPOTENT=idempotent)
        assert writer.wait_for("Consumer is ready"), "writer did not start"
        log("TEST", f"[{phase.upper()}] idempotency {'OFF' if idempotent == '0' else 'ON'}: sending the SAME task twice "
                    f"(correlation_id={correlation_id})")
        for n in (1, 2):
            p, o = produce(producer, TASKS, task(correlation_id), key=correlation_id)
            log("TEST", f"  send #{n} -> {TASKS} partition={p} offset={o}")
        writer.wait_for("RECV", count=2, timeout=20)          # both copies were received (a duplicate logs no COMMIT)
        time.sleep(2)
        shown = writer.lines("RECV", "DUPLICATE", "SEND", "COMMIT")
        if idempotent == "1":
            writer.stop()
            log("TEST", "[AFTER] writer restarted; replaying the same message a third time (state must survive)")
            writer = Writer("duplicate", "after_restart", "writer-1", group, IDEMPOTENT="1")
            writer.wait_for("Consumer is ready")
            produce(producer, TASKS, task(correlation_id), key=correlation_id)
            writer.wait_for("DUPLICATE", timeout=20)
            shown += ["--- writer restarted ---"] + writer.lines("Consumer is ready", "RECV", "DUPLICATE", "SEND", "COMMIT")
        drafts = read_topic(DRAFTS, lambda m, c=correlation_id: m.get("correlation_id") == c)
        effects = [ln for ln in side_effects("duplicate", group) if correlation_id in ln]
        show(f"[{phase.upper()}] writer log", shown)
        log("TEST", f"[{phase.upper()}] drafts on {DRAFTS} for this correlation_id: {len(drafts)}   "
                    f"side effects recorded: {len(effects)}")
        result[phase] = {"correlation_id": correlation_id, "messages_sent": 3 if idempotent == "1" else 2,
                         "drafts_produced": len(drafts), "side_effects": len(effects),
                         "duplicates_ignored": sum("DUPLICATE" in ln for ln in shown)}
        writer.stop()
    result["passed"] = result["before"]["drafts_produced"] == 2 and result["after"]["drafts_produced"] == 1
    log("TEST", f"RESULT duplicate: before={result['before']['drafts_produced']} drafts, "
                f"after={result['after']['drafts_produced']} draft -> {'PASS' if result['passed'] else 'FAIL'}")
    return result


# --- 2. consumer death -------------------------------------------------------------------
def death() -> dict[str, Any]:
    banner("PART 3.II  CONSUMER DEATH - kill the Writer mid-processing")
    producer, result = make_producer(), {}
    for phase, commit in (("before", "auto"), ("after", "after")):
        group = f"s3170_death_{phase}_{RUN}"
        warm, victim = f"warmup-{phase}-{RUN}", f"death-{phase}-{RUN}"
        writer = Writer("death", phase, "writer-1", group, COMMIT=commit, IDEMPOTENT="1")
        assert writer.wait_for("Consumer is ready")
        log("TEST", f"[{phase.upper()}] commit mode = {'AUTO (offset committed on a timer, before the work is done)' if commit == 'auto' else 'AFTER successful processing'}")
        produce(producer, TASKS, task(warm), key=warm, partition=0)   # gives partition 0 a committed offset to resume from
        assert writer.wait_for(f"SEND  topic={DRAFTS}", timeout=30), "warm-up message was not processed"
        time.sleep(1.5)
        produce(producer, TASKS, task(victim, simulate_slow_ms=8000), key=victim, partition=0)
        log("TEST", f"[{phase.upper()}] sent a task that takes 8 s to process (correlation_id={victim})")
        assert writer.wait_for("WORKING", timeout=20)
        time.sleep(1.5)                                              # past the 0.5 s auto-commit interval
        writer.kill()
        before_restart = describe_group(group)
        show(f"[{phase.upper()}] consumer group right after the kill (CURRENT-OFFSET = committed, LAG = unprocessed)",
             before_restart)
        log("TEST", f"[{phase.upper()}] restarting the Writer (same group, same state)")
        restarted = Writer("death", f"{phase}_restart", "writer-1", group, COMMIT=commit, IDEMPOTENT="1")
        redelivered = restarted.wait_for(f"correlation_id={victim}", timeout=45)
        finished = redelivered and restarted.wait_for(f"SEND  topic={DRAFTS}", timeout=30)
        if finished:
            restarted.wait_for("COMMIT", timeout=15)
        time.sleep(1)
        after_restart = describe_group(group)
        show(f"[{phase.upper()}] restarted writer log", restarted.lines("Consumer is ready", "RECV", "WORKING", "SEND", "COMMIT"))
        show(f"[{phase.upper()}] consumer group after the restart", after_restart)
        drafts = read_topic(DRAFTS, lambda m, c=victim: m.get("correlation_id") == c)
        log("TEST", f"[{phase.upper()}] message redelivered after restart: {redelivered}; drafts for it: {len(drafts)}")
        result[phase] = {"commit_mode": commit, "redelivered_after_restart": redelivered,
                         "drafts_produced": len(drafts), "group_after_kill": before_restart,
                         "group_after_restart": after_restart}
        restarted.stop()
    result["passed"] = (not result["before"]["redelivered_after_restart"] and result["before"]["drafts_produced"] == 0
                        and result["after"]["redelivered_after_restart"] and result["after"]["drafts_produced"] == 1)
    log("TEST", f"RESULT death: before -> message lost ({result['before']['drafts_produced']} drafts); after -> "
                f"redelivered and completed ({result['after']['drafts_produced']} draft) -> {'PASS' if result['passed'] else 'FAIL'}")
    return result


# --- 3. poison message -------------------------------------------------------------------
def poison() -> dict[str, Any]:
    banner("PART 3.III  POISON MESSAGE - bounded retries, dead-letter topic, no head-of-line blocking")
    producer, result = make_producer(), {}
    for phase, retries, dlq in (("before", "0", "0"), ("after", "3", "1")):
        group = f"s3170_poison_{phase}_{RUN}"
        bad, good = f"poison-{phase}-{RUN}", f"after-poison-{phase}-{RUN}"
        writer = Writer("poison", phase, "writer-1", group, MAX_RETRIES=retries, DLQ=dlq, IDEMPOTENT="1")
        assert writer.wait_for("Consumer is ready")
        log("TEST", f"[{phase.upper()}] {'unbounded retries, no dead-letter topic' if retries == '0' else 'MAX_RETRIES=3 + ' + DEAD_LETTER}")
        pb = {"correlation_id": bad, "question": "bad task", "plan": None}      # no plan -> the writer raises
        # Head-of-line blocking is per partition, so poison and the message behind it share partition 0.
        produce(producer, TASKS, pb, key=bad, partition=0)
        if phase == "after":
            producer.produce(TASKS, value=f"{{ this is not json {RUN}".encode(), key=b"poison-json", partition=0)   # unparseable
            producer.flush(10)
        produce(producer, TASKS, task(good), key=good, partition=0)
        log("TEST", f"[{phase.upper()}] sent to partition 0: a poison task, {'an unparseable message, ' if phase == 'after' else ''}then a GOOD task ({good})")
        if phase == "before":
            time.sleep(12)
        else:
            writer.wait_for(f"correlation_id={good}", timeout=40)
            writer.wait_for(f"SEND  topic={DRAFTS}", timeout=40)
            writer.wait_for("DEAD-LETTER", count=2, timeout=40)
            writer.wait_for("COMMIT", count=3, timeout=40)
            time.sleep(1)
        retry_lines = writer.lines("RETRY")
        show(f"[{phase.upper()}] writer log (retries / dead-letter / what happened next)",
             writer.lines("RECV", "RETRY", "GIVE UP", "DEAD-LETTER", "SEND", "COMMIT"), limit=18)
        good_drafts = read_topic(DRAFTS, lambda m, c=good: m.get("correlation_id") == c)
        dead = read_topic(DEAD_LETTER, lambda m: str(m.get("correlation_id", "")).endswith(RUN) or RUN in str(m.get("original"))) \
            if phase == "after" else []
        log("TEST", f"[{phase.upper()}] retries logged: {len(retry_lines)}; GOOD task processed: {len(good_drafts) == 1}; "
                    f"dead-letter records: {len(dead)}")
        if dead:
            show("dead-letter topic contents", [json.dumps({k: v for k, v in d.items() if k != "original"}) for d in dead])
        result[phase] = {"retries_logged": len(retry_lines), "good_message_processed": len(good_drafts) == 1,
                         "dead_letter_records": len(dead), "max_retries": None if retries == "0" else int(retries)}
        writer.kill() if phase == "before" else writer.stop()
    result["passed"] = (not result["before"]["good_message_processed"] and result["after"]["good_message_processed"]
                        and result["after"]["dead_letter_records"] == 2)
    log("TEST", f"RESULT poison: before -> later message BLOCKED; after -> dead-lettered and later message processed "
                f"-> {'PASS' if result['passed'] else 'FAIL'}")
    return result


# --- 4. ordering -------------------------------------------------------------------------
def make_messages() -> list[dict[str, Any]]:
    """20 related messages from VERIFY_SEED: several updates about each of 5 incidents."""
    rng = random.Random(VERIFY_SEED)
    entities = [f"INC-{rng.randint(1000, 9999)}" for _ in range(5)]
    seq: dict[str, int] = defaultdict(int)
    out = []
    for i in range(20):
        entity = rng.choice(entities)
        seq[entity] += 1
        out.append(task(f"ord-{i:02d}-{RUN}", entity=entity, seq=seq[entity], work_ms=rng.randint(20, 400),
                        question=f"Update {seq[entity]} for incident {entity}"))
    return out


def ordering_run(label: str, keyed: bool) -> dict[str, Any]:
    group = f"s3170_ord_{label}_{RUN}"
    csv_a, csv_b = RAW / f"_ord_{label}{TAG}_A.csv", RAW / f"_ord_{label}{TAG}_B.csv"
    for p in (csv_a, csv_b):
        p.unlink(missing_ok=True)
    wa = Writer("ordering", label, "writer-A", group, PROCESS_LOG=str(csv_a), IDEMPOTENT="0")
    wb = Writer("ordering", label, "writer-B", group, PROCESS_LOG=str(csv_b), IDEMPOTENT="0")
    for w in (wa, wb):
        assert w.wait_for("Consumer is ready")
    time.sleep(3)                                                  # let the group settle on one partition each
    show(f"[{label.upper()}] the two writers' partition assignments", wa.lines("Consumer is ready") + wb.lines("Consumer is ready"))
    producer = make_producer()
    messages = make_messages()
    sent_partition: dict[str, set[int]] = defaultdict(set)
    for i, m in enumerate(messages):
        if keyed:
            partition, _ = produce(producer, TASKS, m, key=m["entity"])        # the broker hashes the key
        else:
            partition, _ = produce(producer, TASKS, m, partition=i % 2)        # no key: round-robin across 2 partitions
        sent_partition[m["entity"]].add(partition)
    log("TEST", f"[{label.upper()}] sent 20 messages ({'key = entity' if keyed else 'NO key, round-robin'}); "
                f"partitions used per entity: " + ", ".join(f"{e}:{sorted(p)}" for e, p in sorted(sent_partition.items())))
    deadline = time.time() + 60
    rows: list[dict[str, str]] = []
    while time.time() < deadline:
        rows = [r for path in (csv_a, csv_b) if path.exists() for r in csv.DictReader(path.open())]
        if len(rows) >= 20:
            break
        time.sleep(0.5)
    rows.sort(key=lambda r: r["time"])
    out_csv = RAW / f"ordering_{label}{TAG}.csv"
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["order", "time", "writer", "partition", "offset", "entity", "seq", "correlation_id"])
        w.writeheader()
        for n, r in enumerate(rows, 1):
            w.writerow({"order": n, **r})
    by_entity: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_entity[r["entity"]].append(r)
    violations, summary = 0, {}
    print(f"  --- [{label.upper()}] order in which messages were PROCESSED (time-sorted across both writers)", flush=True)
    print("      #  time          writer    partition  entity     seq", flush=True)
    for n, r in enumerate(rows, 1):
        print(f"     {n:>2}  {r['time']}  {r['writer']:<8}  {r['partition']:>9}  {r['entity']:<9}  {r['seq']:>3}", flush=True)
    for entity, items in sorted(by_entity.items()):
        seqs = [int(i["seq"]) for i in items]
        parts = sorted({int(i["partition"]) for i in items})
        in_order = seqs == sorted(seqs)
        violations += 0 if in_order else 1
        summary[entity] = {"processed_seq_order": seqs, "partitions": parts, "in_order": in_order}
        log("TEST", f"[{label.upper()}] {entity}: partitions={parts} processed seq order={seqs} -> "
                    f"{'IN ORDER' if in_order else 'OUT OF ORDER'}")
    for w in (wa, wb):
        w.stop()
    for p in (csv_a, csv_b):
        p.unlink(missing_ok=True)
    return {"keyed": keyed, "messages_processed": len(rows), "entities_out_of_order": violations,
            "entities_in_one_partition": sum(len(v["partitions"]) == 1 for v in summary.values()),
            "entities": len(summary), "per_entity": summary, "csv": str(out_csv.relative_to(HERE.parents[1]))}


def ordering() -> dict[str, Any]:
    banner(f"PART 3.IV  ORDERING - 20 related messages from VERIFY_SEED={VERIFY_SEED}, 2 partitions, 2 writers in one group")
    before = ordering_run("unkeyed", keyed=False)
    after = ordering_run("keyed", keyed=True)
    passed = (before["entities_out_of_order"] >= 1 and after["entities_out_of_order"] == 0
              and after["entities_in_one_partition"] == after["entities"]
              and before["messages_processed"] == after["messages_processed"] == 20)
    log("TEST", f"RESULT ordering: unkeyed -> {before['entities_out_of_order']} of {before['entities']} entities out of order; "
                f"keyed -> {after['entities_out_of_order']} out of order, {after['entities_in_one_partition']}/{after['entities']} "
                f"entities in a single partition -> {'PASS' if passed else 'FAIL'}")
    return {"before": before, "after": after, "passed": passed}


SCENARIOS = {"duplicate": duplicate, "death": death, "poison": poison, "ordering": ordering}


def main() -> int:
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    student_banner(f"failure_tests.py {which}")
    ensure_topics()
    chosen = list(SCENARIOS) if which == "all" else [which]
    results = {}
    for name in chosen:
        results[name] = SCENARIOS[name]()
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / (f"failure_tests_summary{TAG}.json" if which == "all" else f"failure_test_{which}{TAG}.json")
    out.write_text(json.dumps({"run": RUN, "verify_seed": VERIFY_SEED, "results": results}, indent=2, default=str))
    banner("SUMMARY")
    for name, res in results.items():
        log("TEST", f"{name:<10} {'PASS' if res['passed'] else 'FAIL'}")
    log("TEST", f"wrote {out}")
    return 0 if all(r["passed"] for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
