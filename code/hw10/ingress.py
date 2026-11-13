#!/usr/bin/env python3
# ruff: noqa: I001  (import order matters: common10 puts hw08/hw09/web_application on sys.path first)
"""
HW10 Part 4 - request ingress: semantic-cache lookup first, Kafka only on a miss.

    hit  : cache_lookup span (is_cached=True)  -> answer returned, the Kafka pipeline is never touched
    miss : cache_lookup span (is_cached=False) -> s3170_inbox -> planner -> s3170_tasks -> writer -> s3170_drafts
           -> reviewer -> s3170_final -> answer returned and stored in the cache for next time

trace_id is the HW8 correlation_id (one new_id() per request, never a second identifier).
Run with the agents started by `make agents-hw10` (HW10_TRACE=1), e.g.:
    cd code/hw10 && ../../.venv/bin/python ingress.py "What should a rider do if a bus is cancelled?"
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any

import common10 as c
from kafka_common import FINAL, INBOX, decode, ensure_topics, make_consumer, make_producer, new_id, produce, wait_for_assignment
from qa_agent import data_version, extract_entities
from semantic_cache import SemanticCache
from tracing import now_ms, queue_span, span, stamp, write_span


class Ingress:
    def __init__(self, threshold: float = c.SHIPPED_THRESHOLD, namespace: str = c.CACHE_NAMESPACE):
        ensure_topics()
        self.cache = SemanticCache(namespace, threshold)
        self.cache.create_index()
        self.producer = make_producer()
        self.consumer = make_consumer(f"{c.PREFIX}_hw10_ingress_{new_id()[:8]}", [FINAL], reset="latest")
        wait_for_assignment(self.consumer)

    def close(self) -> None:
        self.consumer.close()

    def ask(self, question: str, *, trace_id: str | None = None, fault: str | None = None,
            timeout: float = 900.0, use_cache: bool = True) -> dict[str, Any]:
        trace_id = trace_id or new_id()
        t0 = now_ms()
        # 1) cache lookup (always the first span of a trace)
        with span(trace_id, "cache_lookup", question=question) as a:
            look = self.cache.lookup(question) if use_cache else {"hit": False, "neighbour": None, "vec": None,
                                                                   "threshold": self.cache.threshold,
                                                                   "embed_ms": 0.0, "search_ms": 0.0}
            near = look["neighbour"]
            a.update(is_cached=look["hit"], path="hit" if look["hit"] else "miss",
                     similarity=near["similarity"] if near else None, threshold=look["threshold"],
                     embed_ms=round(look["embed_ms"], 2), search_ms=round(look["search_ms"], 2))
        out: dict[str, Any] = {"trace_id": trace_id, "question": question, "is_cached": look["hit"],
                               "similarity": near["similarity"] if near else None,
                               "path": "hit" if look["hit"] else "miss"}
        if look["hit"]:
            out.update(status="approved", answer=near["answer"], e2e_ms=round(now_ms() - t0, 2),
                       matched_query=near["query"])
            return out

        # 2) miss: through Kafka
        msg: dict[str, Any] = {"correlation_id": trace_id, "question": question}
        if fault:
            msg["fault"] = fault                    # test hook, see planner.py
        produce(self.producer, INBOX, stamp(msg), key=trace_id)
        sent_ms = now_ms()
        deadline = time.time() + timeout
        while time.time() < deadline:
            m = self.consumer.poll(1.0)
            if m is None or m.error():
                continue
            final = decode(m.value())
            if final.get("correlation_id") != trace_id:
                continue
            recv = now_ms()
            queue_span(trace_id, "final", final.get("sent_at_ms"), recv)
            out.update(status=final.get("status"), answer=final.get("answer"), reason=final.get("reason"),
                       e2e_ms=round(recv - t0, 2))
            if final.get("status") == "approved" and use_cache and look["vec"] is not None:
                self.cache.store(question, final["answer"], data_version(extract_entities(question)),
                                 extract_entities(question), vec=look["vec"])
            return out
        write_span(trace_id, "final", sent_ms, now_ms(), status="error",
                   error=f"no final message within {timeout:.0f}s (writer dead-lettered or a stage is down)")
        out.update(status="no_final", answer=None, e2e_ms=round(now_ms() - t0, 2))
        return out


def main() -> int:
    c.banner("ingress.py")
    question = " ".join(a for a in sys.argv[1:] if not a.startswith("--")) or \
        "What should a rider do when their bus is cancelled and the next one is an hour away?"
    ing = Ingress()
    try:
        print(json.dumps(ing.ask(question), indent=2))
    finally:
        ing.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
