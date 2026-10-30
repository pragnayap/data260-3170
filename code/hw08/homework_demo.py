#!/usr/bin/env python3
"""
HW8 Part 1.IV - the request/response demonstration, as a Kafka client.

    1 create a correlation_id            6 log the response the client receives
    2 send CREATE_INCIDENT to requests   7 extract the generated incident_id
    3 log the message sent               8 send GET_INCIDENT with that id
    4 log the worker receiving/processing 9 log the whole GET sequence
    5 log the worker replying            10 show the entity and confirm correlation_id preserved

Steps 4-5 are the worker container's own log lines for this correlation_id (read with
`docker logs`), not text this script writes on the worker's behalf.

    .venv/bin/python code/hw08/homework_demo.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import Any

from kafka_common import (
    REQUESTS,
    RESPONSES,
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

WORKER_CONTAINER = "s3170_worker"
INCIDENT = {
    "routeId": "Line 22",
    "location": "Downtown Transit Center",
    "submitterEmail": "rider@example.com",
    "description": "Bus arrived 40 minutes late with no announcement or updated signage at the stop.",
    "category": "Delay",
    "agreeTerms": True,
}


def worker_log_lines(correlation_id: str) -> list[str]:
    """The worker container's real log lines mentioning this correlation_id."""
    try:
        out = subprocess.run(["docker", "logs", WORKER_CONTAINER], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return ["(docker logs unavailable - run `docker logs s3170_worker` to see the worker lines)"]
    return [ln for ln in (out.stdout + out.stderr).splitlines() if correlation_id in ln]


def roundtrip(producer, consumer, operation: str, data: dict[str, Any]) -> tuple[dict, dict]:
    """Send one request and wait for the response carrying the same correlation_id."""
    correlation_id = new_id()
    request = {"correlation_id": correlation_id, "reply_to": RESPONSES, "operation": operation, "data": data}
    partition, offset = produce(producer, REQUESTS, request, key=correlation_id)
    log("CLIENT", f"SEND  topic={REQUESTS} partition={partition} offset={offset} "
                  f"correlation_id={correlation_id} operation={operation}")
    log("CLIENT", f"      message: {json.dumps(request)}")
    deadline = time.time() + 30
    while time.time() < deadline:
        msg = consumer.poll(0.5)
        if msg is None or msg.error():
            continue
        response = decode(msg.value())
        if response.get("correlation_id") == correlation_id:
            log("CLIENT", f"RECV  topic={msg.topic()} partition={msg.partition()} offset={msg.offset()} "
                          f"correlation_id={response['correlation_id']} success={response.get('success')}")
            log("CLIENT", f"      message: {json.dumps(response)}")
            return request, response
    raise TimeoutError(f"no response for correlation_id={correlation_id} - is the worker running?")


def show_worker(correlation_id: str) -> None:
    for line in worker_log_lines(correlation_id):
        print(f"      (worker container) {line}", flush=True)


def main() -> int:
    student_banner("homework_demo.py")
    ensure_topics()
    producer = make_producer()
    consumer = make_consumer(f"s3170_demo_{new_id()[:8]}", [RESPONSES], reset="latest")
    wait_for_assignment(consumer)        # be listening before the first request is sent

    banner("STEPS 1-7: CREATE_INCIDENT")
    log("DEMO", "STEP 1  one correlation_id is created per request, before sending")
    log("DEMO", "STEP 2-3 send CREATE_INCIDENT to the request topic and log the message")
    request, response = roundtrip(producer, consumer, "CREATE_INCIDENT", INCIDENT)
    log("DEMO", "STEP 4-5 worker received, processed and replied (its own log lines):")
    time.sleep(0.5)
    show_worker(request["correlation_id"])
    log("DEMO", "STEP 6  response received by the client (logged above)")
    incident_id = response["incident_id"]
    log("DEMO", f"STEP 7  extracted incident_id={incident_id}")
    created_ok = response["success"] and response["correlation_id"] == request["correlation_id"]

    banner("STEPS 8-10: GET_INCIDENT with that incident_id")
    log("DEMO", "STEP 8  send GET_INCIDENT")
    get_request, get_response = roundtrip(producer, consumer, "GET_INCIDENT", {"incident_id": incident_id})
    log("DEMO", "STEP 9  worker received, processed and replied (its own log lines):")
    time.sleep(0.5)
    show_worker(get_request["correlation_id"])
    log("DEMO", "STEP 10 retrieved entity:")
    print(json.dumps(get_response.get("incident"), indent=2), flush=True)
    preserved = get_response["correlation_id"] == get_request["correlation_id"]
    log("DEMO", f"correlation_id sent     = {get_request['correlation_id']}")
    log("DEMO", f"correlation_id received = {get_response['correlation_id']}")
    log("DEMO", f"correlation_id preserved: {preserved}")

    banner("ERROR PATHS (each error response still echoes its correlation_id)")
    ok = True
    for label, op, data in (
        ("unknown incident_id", "GET_INCIDENT", {"incident_id": "does-not-exist"}),
        ("unknown operation", "DELETE_INCIDENT", {}),
        ("invalid entity (short description)", "CREATE_INCIDENT", {**INCIDENT, "description": "too short"}),
    ):
        log("DEMO", f"-- {label}")
        req, resp = roundtrip(producer, consumer, op, data)
        ok &= (resp["success"] is False and resp["correlation_id"] == req["correlation_id"] and bool(resp.get("error")))
    consumer.close()

    passed = created_ok and get_response["success"] and preserved and ok
    log("DEMO", f"RESULT: {'PASS' if passed else 'FAIL'} (create ok, get ok, correlation_id preserved, errors clean)")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
