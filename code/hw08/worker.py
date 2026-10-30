#!/usr/bin/env python3
"""
HW8 Part 1 - the entity worker.

Consumes s3170_entity_requests, handles CREATE_INCIDENT / GET_INCIDENT, and answers on the topic
named by the request's reply_to. Entities live in a plain dict in this process (as the handout
asks). The correlation_id is copied into every response, including every error.

Request : {"correlation_id", "reply_to", "operation", "data": {...}}
Response: {"correlation_id", "success": true,  "incident_id" | "incident", "message"?}
          {"correlation_id", "success": false, "error": "..."}

Offsets are committed only after the reply has been delivered, so a crash mid-request makes the
broker redeliver it (at-least-once) instead of losing it.
"""

from __future__ import annotations

import re
import signal
import sys
from typing import Any

from kafka_common import (
    PREFIX,
    REQUESTS,
    RESPONSES,
    decode,
    ensure_topics,
    log,
    make_consumer,
    make_producer,
    new_id,
    produce,
)

CATEGORIES = ("Delay", "Mechanical Failure", "Accident/Collision", "Safety Hazard")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
REQUIRED = ("routeId", "location", "submitterEmail", "description", "category", "agreeTerms")

ENTITIES: dict[str, dict[str, Any]] = {}      # incident_id -> entity (plain dict, per the handout)


def validate(data: Any) -> str | None:
    """Return a clean error message for missing / empty / invalid fields, else None."""
    if not isinstance(data, dict):
        return "data must be an object"
    for field in REQUIRED:
        if field not in data:
            return f"Missing required field: {field}"
    for field in ("routeId", "location", "submitterEmail", "description", "category"):
        if not isinstance(data[field], str) or not data[field].strip():
            return f"Field {field} must be a non-empty string"
    if not EMAIL.match(data["submitterEmail"].strip()):
        return "Field submitterEmail must be a valid email address"
    if len(data["description"].strip()) <= 25:
        return "Field description must be longer than 25 characters"
    if data["category"] not in CATEGORIES:
        return f"Field category must be one of: {', '.join(CATEGORIES)}"
    if data["agreeTerms"] is not True:
        return "Field agreeTerms must be true"
    return None


def handle(request: dict[str, Any]) -> dict[str, Any]:
    """Process one request dict and return the response body (without correlation_id)."""
    operation = request.get("operation")
    data = request.get("data")

    if operation == "CREATE_INCIDENT":
        error = validate(data)
        if error:
            return {"success": False, "error": error}
        incident_id = new_id()
        ENTITIES[incident_id] = {"incident_id": incident_id,
                                 **{k: (data[k].strip() if isinstance(data[k], str) else data[k])
                                    for k in REQUIRED}}
        return {"success": True, "incident_id": incident_id, "message": "Incident created"}

    if operation == "GET_INCIDENT":
        incident_id = data.get("incident_id") if isinstance(data, dict) else None
        if not isinstance(incident_id, str) or not incident_id.strip():
            return {"success": False, "error": "Missing required field: incident_id"}
        entity = ENTITIES.get(incident_id)
        if entity is None:
            return {"success": False, "error": "Incident not found"}
        return {"success": True, "incident": entity}

    return {"success": False, "error": "Unknown operation"}


def main() -> int:
    ensure_topics()
    producer = make_producer()
    running = {"go": True}
    signal.signal(signal.SIGTERM, lambda *_: running.update(go=False))
    signal.signal(signal.SIGINT, lambda *_: running.update(go=False))

    consumer = make_consumer(f"{PREFIX}_entity_worker", [REQUESTS], reset="earliest",
                             on_ready=lambda parts: log("WORKER", "Consumer is ready and listening..."))
    log("WORKER", f"subscribed to {REQUESTS}; replies go to the topic named by each request's reply_to")
    try:
        while running["go"]:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                log("WORKER", f"consumer error: {msg.error()}")
                continue

            try:
                request = decode(msg.value())
            except ValueError:
                log("WORKER", f"RECV  topic={msg.topic()} partition={msg.partition()} offset={msg.offset()} "
                              "INVALID JSON - answered with an error, offset committed")
                request = {}
            correlation_id = request.get("correlation_id")
            operation = request.get("operation")
            reply_to = request.get("reply_to")
            log("WORKER", f"RECV  topic={msg.topic()} partition={msg.partition()} offset={msg.offset()} "
                          f"correlation_id={correlation_id} operation={operation}")

            if not correlation_id or not isinstance(request.get("data"), dict | type(None)):
                body = {"success": False, "error": "Request must include correlation_id and operation"}
            else:
                log("WORKER", f"PROCESS correlation_id={correlation_id} operation={operation} data={request.get('data')}")
                body = handle(request)
            # reply_to must be one of our own topics; anything else is answered on the default topic.
            target = reply_to if isinstance(reply_to, str) and reply_to.startswith(f"{PREFIX}_") else RESPONSES
            response = {"correlation_id": correlation_id, **body}
            partition, offset = produce(producer, target, response, key=correlation_id)
            log("WORKER", f"REPLY topic={target} partition={partition} offset={offset} "
                          f"correlation_id={correlation_id} success={body['success']} "
                          f"{'error=' + body['error'] if not body['success'] else ''}".rstrip())
            consumer.commit(message=msg, asynchronous=False)   # only after the reply is on the broker
    finally:
        consumer.close()
        log("WORKER", "worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
