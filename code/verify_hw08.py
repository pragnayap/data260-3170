#!/usr/bin/env python3
"""
HW8 self-check - a smoke test over the tagged commit. Writes reports/hw08/verification.json.

    .venv/bin/python code/verify_hw08.py            # everything (Kafka + worker + API must be up: make kafka-up-hw08)
    .venv/bin/python code/verify_hw08.py --quick    # skip the ~6 minute failure-test run

Checks test behaviour, not wording: status/success flags, preserved correlation_ids, UUID format,
counts of messages on topics, files on disk. A check whose service is down is SKIPPED with its
reason, not failed. The script starts only throwaway writer/planner/reviewer subprocesses with
unique consumer groups; it never edits application code.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HW8 = REPO / "code" / "hw08"
REPORT = REPO / "reports" / "hw08"
SID4, SEED, VERIFY_SEED, PORT_BASE = 3170, 3170, 263170, 8470
sys.path.insert(0, str(HW8))

checks: list[dict] = []


class Skip(Exception):
    pass


def record(name: str, status: str, detail: str = "") -> None:
    checks.append({"check": name, "status": status, "detail": detail})
    print(f"[{status:<4}] {name}" + (f" -- {detail}" if detail else ""), flush=True)


def run(name: str, fn) -> None:
    try:
        ok, detail = fn()
        record(name, "PASS" if ok else "FAIL", detail)
    except Skip as s:
        record(name, "SKIP", str(s))
    except Exception as exc:  # noqa: BLE001
        record(name, "FAIL", f"{exc.__class__.__name__}: {exc}")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def checks_with_kafka() -> None:
    import httpx
    import kafka_common as kc

    try:
        kc.ensure_topics(retries=3)
    except Exception as exc:  # noqa: BLE001
        raise Skip(f"Kafka not reachable at {kc.BOOTSTRAP}: {exc}") from exc

    producer = kc.make_producer()
    consumer = kc.make_consumer(f"s3170_verify_{kc.new_id()[:8]}", [kc.RESPONSES], reset="latest")
    kc.wait_for_assignment(consumer)

    def call(operation: str, data: dict, timeout: float = 20) -> tuple[dict, dict]:
        cid = kc.new_id()
        req = {"correlation_id": cid, "reply_to": kc.RESPONSES, "operation": operation, "data": data}
        kc.produce(producer, kc.REQUESTS, req, key=cid)
        end = time.time() + timeout
        while time.time() < end:
            msg = consumer.poll(0.5)
            if msg is None or msg.error():
                continue
            body = kc.decode(msg.value())
            if body.get("correlation_id") == cid:
                return req, body
        raise TimeoutError(f"no response for {operation} - is the worker container running?")

    incident = {"routeId": "Line 22", "location": "Downtown Transit Center", "submitterEmail": "verify@example.com",
                "description": "Verification probe: bus arrived forty minutes late with no announcement.",
                "category": "Delay", "agreeTerms": True}
    state: dict = {}

    def topics():
        from confluent_kafka.admin import AdminClient
        meta = AdminClient({"bootstrap.servers": kc.BOOTSTRAP}).list_topics(timeout=10).topics
        have = {t: len(meta[t].partitions) for t in kc.TOPIC_PARTITIONS if t in meta}
        ok = have == kc.TOPIC_PARTITIONS and all(t.startswith("s3170_") for t in have)
        return ok, f"{have}"

    def create_get():
        req, created = call("CREATE_INCIDENT", incident)
        ok1 = (created["success"] is True and bool(UUID_RE.match(created.get("incident_id", "")))
               and created["correlation_id"] == req["correlation_id"] and created.get("message") == "Incident created")
        state["id"] = created.get("incident_id")
        req2, got = call("GET_INCIDENT", {"incident_id": state["id"]})
        entity = got.get("incident", {})
        ok2 = (got["success"] is True and got["correlation_id"] == req2["correlation_id"]
               and entity.get("incident_id") == state["id"]
               and all(entity.get(k) == incident[k] for k in incident))
        return ok1 and ok2, f"incident_id={state['id']}; both correlation_ids preserved; stored fields match"

    def not_found():
        req, resp = call("GET_INCIDENT", {"incident_id": str(uuid.uuid4())})
        return (resp["success"] is False and resp["correlation_id"] == req["correlation_id"]
                and resp["error"] == "Incident not found"), f"error={resp.get('error')!r}"

    def unknown_op():
        req, resp = call("DELETE_INCIDENT", {})
        return (resp["success"] is False and resp["correlation_id"] == req["correlation_id"]
                and resp["error"] == "Unknown operation"), f"error={resp.get('error')!r}"

    def validation():
        bad = {"missing field": {k: v for k, v in incident.items() if k != "location"},
               "empty value": {**incident, "routeId": "   "},
               "bad email": {**incident, "submitterEmail": "not-an-email"},
               "short description": {**incident, "description": "too short"},
               "bad category": {**incident, "category": "Party"},
               "terms not agreed": {**incident, "agreeTerms": False}}
        outcomes = {}
        for label, data in bad.items():
            req, resp = call("CREATE_INCIDENT", data)
            outcomes[label] = (resp["success"] is False and bool(resp.get("error"))
                               and resp["correlation_id"] == req["correlation_id"])
        return all(outcomes.values()), f"{sum(outcomes.values())}/{len(outcomes)} invalid inputs rejected with an error + correlation_id"

    def malformed_request():
        cid = kc.new_id()
        kc.produce(producer, kc.REQUESTS, {"correlation_id": cid, "operation": "GET_INCIDENT"}, key=cid)  # no data, no reply_to
        end = time.time() + 20
        while time.time() < end:
            msg = consumer.poll(0.5)
            if msg and not msg.error() and kc.decode(msg.value()).get("correlation_id") == cid:
                resp = kc.decode(msg.value())
                return resp["success"] is False and bool(resp.get("error")), f"error={resp.get('error')!r}"
        return False, "no response"

    def api_roundtrip():
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{PORT_BASE}", timeout=30) as c:
                created = c.post("/incidents", json=incident)
                got = c.get(f"/incidents/{created.json().get('incident_id')}")
                missing = c.get("/incidents/does-not-exist")
        except httpx.HTTPError as exc:
            raise Skip(f"API not reachable on {PORT_BASE}: {exc}") from exc
        ok = (created.status_code == 201 and got.status_code == 200 and missing.status_code == 404
              and created.headers.get("x-correlation-id") and got.json()["incident"]["incident_id"] == created.json()["incident_id"])
        return bool(ok), f"POST {created.status_code}, GET {got.status_code}, unknown id {missing.status_code}, X-Correlation-Id header present"

    def containers():
        out = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=20).stdout.split()
        need = {"s3170_kafka", "s3170_worker", "s3170_api"}
        return need <= set(out), f"running: {sorted(set(out) & need)}"

    def logs():
        w = subprocess.run(["docker", "logs", "s3170_worker"], capture_output=True, text=True, timeout=20)
        a = subprocess.run(["docker", "logs", "s3170_api"], capture_output=True, text=True, timeout=20)
        w_ok = "Consumer is ready and listening..." in (w.stdout + w.stderr)
        a_ok = f"http://127.0.0.1:{PORT_BASE}" in (a.stdout + a.stderr)
        return w_ok and a_ok, f"worker ready line: {w_ok}; API started line: {a_ok}"

    def pipeline():
        group = uuid.uuid4().hex[:6]
        env = {**os.environ, "RESET": "latest", "PLANNER_MODE": "stub", "WRITER_MODE": "stub", "PYTHONUNBUFFERED": "1",
               "STATE_DIR": str(REPO / "data" / "hw08_state" / f"verify_{group}")}
        procs = [subprocess.Popen([sys.executable, str(HW8 / f), ], cwd=HW8, env={**env, "GROUP": f"s3170_v_{f[:3]}_{group}"},
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                 for f in ("planner.py", "writer.py", "reviewer.py")]
        try:
            time.sleep(12)                                    # let the three groups join
            fc = kc.make_consumer(f"s3170_v_final_{group}", [kc.FINAL], reset="latest")
            kc.wait_for_assignment(fc)
            cid = kc.new_id()
            kc.produce(producer, kc.INBOX, {"correlation_id": cid, "question": "Why was the 22 bus late today?"}, key=cid)
            end = time.time() + 60
            while time.time() < end:
                msg = fc.poll(0.5)
                if msg and not msg.error():
                    final = kc.decode(msg.value())
                    if final.get("correlation_id") == cid:
                        fc.close()
                        return (final.get("status") == "approved" and bool(final.get("answer"))), \
                            f"final status={final.get('status')}, correlation_id preserved through inbox->tasks->drafts->final"
            fc.close()
            return False, "no final message within 60 s"
        finally:
            for p in procs:
                p.terminate()
            for p in procs:
                try:
                    p.wait(10)
                except subprocess.TimeoutExpired:
                    p.kill()

    run("topics: the 7 s3170_* topics exist; s3170_tasks has 2 partitions, the rest 1", topics)
    run("CREATE_INCIDENT -> GET_INCIDENT round-trips through Kafka (UUID id, fields intact, correlation_id preserved)", create_get)
    run("GET_INCIDENT with an unknown id -> success false, 'Incident not found', correlation_id preserved", not_found)
    run("unknown operation -> success false, 'Unknown operation', correlation_id preserved", unknown_op)
    run("invalid CREATE_INCIDENT payloads (6 kinds) are rejected with a clean error and the correlation_id", validation)
    run("malformed request (no data, no reply_to) gets an error response, worker keeps running", malformed_request)
    run("FastAPI wrapper: POST /incidents 201, GET 200, unknown id 404, X-Correlation-Id header", api_roundtrip)
    run("docker ps shows the Kafka, worker and FastAPI containers", containers)
    run("worker log has 'Consumer is ready and listening...' and the API log has its 127.0.0.1:8470 start line", logs)
    run("three-agent pipeline: inbox -> planner -> writer -> reviewer -> final, status approved, correlation_id preserved", pipeline)
    consumer.close()


def failure_checks() -> None:
    def results():
        cp = subprocess.run([sys.executable, "-u", str(HW8 / "failure_tests.py"), "all"], cwd=HW8, capture_output=True,
                            text=True, timeout=1200, env={**os.environ, "FAILURE_TAG": "_verify"})
        out = REPO / "reports" / "hw08" / "raw" / "failure_tests_summary_verify.json"
        data = json.loads(out.read_text())["results"]
        out.unlink()
        for leftover in (REPO / "reports" / "hw08" / "raw").glob("ordering_*_verify.csv"):
            leftover.unlink()
        return data, cp

    data, cp = results()
    for key, label in (("duplicate", "duplicate delivery: replay creates 2 drafts before the fix, 1 after (state survives a restart)"),
                       ("death", "consumer death: auto-commit loses the in-flight message; commit-after redelivers and completes it"),
                       ("poison", "poison message: unbounded retries block the partition; bounded retries + s3170_dead_letter unblock it"),
                       ("ordering", "ordering: unkeyed run has out-of-order entities; keyed run keeps each entity in one partition, in order")):
        run(label, lambda k=key: (data[k]["passed"], json.dumps({p: v for p, v in data[k].items() if p == "passed"})
                                  if k != "ordering" else
                                  f"unkeyed out-of-order={data[k]['before']['entities_out_of_order']}, keyed out-of-order={data[k]['after']['entities_out_of_order']}"))


def static_checks() -> None:
    def ruff():
        r = subprocess.run([str(REPO / ".venv/bin/ruff"), "check", "code/hw08", "code/verify_hw08.py"], cwd=REPO, capture_output=True, text=True)
        return r.returncode == 0, (r.stdout.strip().splitlines() or ["clean"])[-1]

    def files():
        need = ["worker.py", "api.py", "homework_demo.py", "planner.py", "writer.py", "reviewer.py", "send_question.py",
                "failure_tests.py", "kafka_common.py", "Dockerfile"]
        missing = [f for f in need if not (HW8 / f).exists()] + ([] if (REPO / "docker-compose.yml").exists() else ["docker-compose.yml"])
        return not missing, "all required files present" if not missing else f"missing {missing}"

    run("required HW8 files exist (worker, API, demo, planner, writer, reviewer, send_question, compose, Dockerfile)", files)
    run("ruff passes on HW8 code", ruff)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="skip the failure-test run (about 6 minutes)")
    args = ap.parse_args()
    static_checks()
    try:
        checks_with_kafka()
    except Skip as s:
        record("Kafka-backed checks", "SKIP", str(s))
    if not args.quick:
        try:
            failure_checks()
        except Exception as exc:  # noqa: BLE001
            record("failure tests (duplicate, death, poison, ordering)", "FAIL", f"{exc.__class__.__name__}: {exc}")
    passed = sum(c["status"] == "PASS" for c in checks)
    failed = sum(c["status"] == "FAIL" for c in checks)
    skipped = sum(c["status"] == "SKIP" for c in checks)
    out = {
        "homework": 8, "SID4": SID4, "PORT_BASE": PORT_BASE, "PREFIX": "s3170", "SEED": SEED, "VERIFY_SEED": VERIFY_SEED,
        "DOMAIN_ID": 2, "commit": git("rev-parse", "HEAD"), "working_tree_clean": git("status", "--porcelain", "--untracked-files=no") == "",   # tracked files only
        "model_configuration": {"kafka": "apache/kafka:3.8.0 (KRaft, single broker, via Docker)", "client": "confluent-kafka 2.16.1",
                                "entity": "Transit Incident (CREATE_INCIDENT / GET_INCIDENT)", "agents_model": "qwen3:8b via Ollama (checks use stub mode)",
                                "quick_mode": args.quick},
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "passed": passed, "failed": failed, "skipped": skipped, "total_checks": len(checks), "checks": checks,
    }
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / "verification.json").write_text(json.dumps(out, indent=2))
    print(f"\n{passed} passed, {failed} failed, {skipped} skipped of {len(checks)} -> {REPORT / 'verification.json'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
