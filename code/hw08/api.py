#!/usr/bin/env python3
"""
HW8 Part 1 - FastAPI wrapper. It never touches the entity dict: every call becomes a Kafka request
on s3170_entity_requests, and the HTTP reply is whatever the worker sent back on
s3170_entity_responses for the SAME correlation_id.

    POST /incidents                  -> CREATE_INCIDENT
    GET  /incidents/{incident_id}    -> GET_INCIDENT
    POST /requests                   -> any operation (to show "Unknown operation" errors)
    GET  /health
"""

from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from kafka_common import (
    PORT_BASE,
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

TIMEOUT_S = 15.0
PENDING: dict[str, dict[str, Any]] = {}      # correlation_id -> {"event": Event, "response": dict}
_ready = threading.Event()
_stop = threading.Event()
_producer = None


def _response_loop() -> None:
    """Reads every response and hands it to whichever HTTP call is waiting for that correlation_id."""
    consumer = make_consumer(f"s3170_api_{new_id()[:8]}", [RESPONSES], reset="latest",
                             on_ready=lambda parts: _ready.set())
    try:
        while not _stop.is_set():
            msg = consumer.poll(0.5)
            if msg is None or msg.error():
                continue
            response = decode(msg.value())
            correlation_id = response.get("correlation_id")
            slot = PENDING.get(correlation_id)
            if slot is None:
                continue                      # someone else's response (or a late one)
            log("API", f"RECV  topic={msg.topic()} partition={msg.partition()} offset={msg.offset()} "
                       f"correlation_id={correlation_id} success={response.get('success')}")
            slot["response"] = response
            slot["event"].set()
    finally:
        consumer.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _producer
    ensure_topics()
    _producer = make_producer()
    thread = threading.Thread(target=_response_loop, daemon=True)
    thread.start()
    if not _ready.wait(30):
        raise RuntimeError("API response consumer never got its partitions")
    log("API", f"FastAPI server started at http://127.0.0.1:{PORT_BASE}")
    yield
    _stop.set()


app = FastAPI(title="HW8 Kafka entity API", lifespan=lifespan)


def call_worker(operation: str, data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Send one request through Kafka and block until its response arrives (or time out)."""
    correlation_id = new_id()                  # created once, here, and never changed
    PENDING[correlation_id] = {"event": threading.Event(), "response": None}
    request = {"correlation_id": correlation_id, "reply_to": RESPONSES, "operation": operation, "data": data}
    start = time.time()
    try:
        partition, offset = produce(_producer, REQUESTS, request, key=correlation_id)
        log("API", f"SEND  topic={REQUESTS} partition={partition} offset={offset} "
                   f"correlation_id={correlation_id} operation={operation}")
        slot = PENDING[correlation_id]
        if not slot["event"].wait(TIMEOUT_S):
            log("API", f"TIMEOUT correlation_id={correlation_id} after {TIMEOUT_S}s")
            raise HTTPException(504, {"correlation_id": correlation_id, "error": "Worker did not answer in time"})
        response = slot["response"]
    finally:
        PENDING.pop(correlation_id, None)
    log("API", f"CLIENT-RESPONSE correlation_id={correlation_id} success={response.get('success')} "
               f"in {int((time.time() - start) * 1000)} ms")
    return correlation_id, response


def status_for(response: dict[str, Any], created: bool = False) -> int:
    if response.get("success"):
        return 201 if created else 200
    error = response.get("error", "")
    if error.endswith("not found"):
        return 404
    if error == "Unknown operation":
        return 400
    return 422


@app.post("/incidents")
def create_incident(body: dict[str, Any], response: Response):
    correlation_id, reply = call_worker("CREATE_INCIDENT", body)
    response.status_code = status_for(reply, created=True)
    response.headers["X-Correlation-Id"] = correlation_id
    return reply


@app.get("/incidents/{incident_id}")
def get_incident(incident_id: str, response: Response):
    correlation_id, reply = call_worker("GET_INCIDENT", {"incident_id": incident_id})
    response.status_code = status_for(reply)
    response.headers["X-Correlation-Id"] = correlation_id
    return reply


@app.post("/requests")
def generic(body: dict[str, Any], response: Response):
    correlation_id, reply = call_worker(str(body.get("operation")), body.get("data") or {})
    response.status_code = status_for(reply)
    response.headers["X-Correlation-Id"] = correlation_id
    return reply


@app.get("/", include_in_schema=False)
def home():
    """A readable landing page so opening http://127.0.0.1:8470/ in a browser shows what the service is."""
    return {"service": "HW8 Kafka entity API (SID4 3170)", "docs": "/docs", "health": "/health",
            "topics": {"requests": REQUESTS, "responses": RESPONSES},
            "endpoints": ["POST /incidents", "GET /incidents/{incident_id}", "POST /requests"]}


@app.get("/health")
def health():
    return {"status": "ok", "topics": [REQUESTS, RESPONSES]}
