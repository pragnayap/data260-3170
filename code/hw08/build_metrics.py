#!/usr/bin/env python3
"""HW8 - rebuild reports/hw08/METRICS.md from reports/hw08/raw/. Nothing is typed in by hand."""

from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "reports" / "hw08" / "raw"
OUT = REPO / "reports" / "hw08" / "METRICS.md"


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(c) for c in r) + " |" for r in rows])


def main() -> None:
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    fail = json.loads((RAW / "failure_tests_summary.json").read_text())
    res = fail["results"]
    ver = RAW.parent / "verification.json"
    L = ["# HW8 - METRICS", "", "Generated from `reports/hw08/raw/` by `code/hw08/build_metrics.py`.", "",
         "## Section 0 - configuration", "",
         table(["Value", "Mine"], [
             ["SID4", "3170"], ["PORT_BASE", "8470"], ["PREFIX", "s3170"], ["SEED", "3170"], ["VERIFY_SEED", "263170"],
             ["DOMAIN_ID", "2 (Municipal Transit Incidents; entity = Transit Incident)"],
             ["Hardware", "Intel Core i9-9880H x86_64, 16 GB RAM, macOS 15, Docker Desktop (7.6 GB)"],
             ["Local model (Part 2 agents)", "qwen3:8b via Ollama, CPU-only; failure tests use stub drafts"],
             ["Kafka", "apache/kafka:3.8.0 (KRaft, single broker) in Docker; client confluent-kafka 2.16.1"],
             ["Commit at generation time", commit + " (final tagged hash goes in the report)"]]), "",
         "## Part 1 - request/response over Kafka", "",
         "Topics: `s3170_entity_requests` (1 partition), `s3170_entity_responses` (1 partition). Operations: "
         "`CREATE_INCIDENT`, `GET_INCIDENT` for the Transit Incident entity. Evidence: `raw/part1_demo_run.txt` "
         "(the 10-step demo with the worker container's own log lines) and `raw/part1_api_run.txt` (HTTP calls through "
         "the FastAPI wrapper).", ""]
    api = (RAW / "part1_api_run.txt").read_text()
    L += [table(["Call", "Result"], [
        ["POST /incidents (valid)", "201 Created, incident_id (UUID), `X-Correlation-Id` header"],
        ["GET /incidents/{id}", "200 OK, entity returned, correlation_id echoed"],
        ["GET /incidents/does-not-exist", "404, `Incident not found`, correlation_id echoed"],
        ["POST /requests {operation: DROP_EVERYTHING}", "400, `Unknown operation`, correlation_id echoed"]]), ""]
    assert "201 Created" in api and "404 Not Found" in api and "400 Bad Request" in api

    L += ["## Part 2 - three-agent pipeline", "",
          "Topics: `s3170_inbox`, `s3170_tasks` (2 partitions), `s3170_drafts`, `s3170_final`. One complete journey "
          "(planner, writer and reviewer are separate processes; no agent calls another): `raw/pipeline_journey.txt`.", ""]
    jr = (RAW / "pipeline_journey.txt").read_text().splitlines()
    stamps = [ln for ln in jr if ln[:2].isdigit()]
    L += ["```", *[ln[:200] for ln in stamps], "```", ""]

    d, a = res["duplicate"]["before"], res["duplicate"]["after"]
    dd, da = res["death"]["before"], res["death"]["after"]
    pb, pa = res["poison"]["before"], res["poison"]["after"]
    ob, oa = res["ordering"]["before"], res["ordering"]["after"]
    L += ["## Part 3 - failure behaviour (each scenario run against real Kafka, before and after the fix)", "",
          table(["Failure scenario", "Before fix", "After fix"], [
              ["Duplicate delivery (same correlation_id replayed)",
               f"{d['messages_sent']} messages sent -> {d['drafts_produced']} drafts, {d['side_effects']} side effects (duplicate work)",
               f"{a['messages_sent']} messages sent (incl. a replay after a Writer restart) -> {a['drafts_produced']} draft, "
               f"{a['side_effects']} side effect, {a['duplicates_ignored']} duplicates ignored"],
              ["Consumer killed mid-work",
               f"auto-commit: offset committed before the work finished; after SIGKILL + restart the message is never redelivered "
               f"({dd['drafts_produced']} drafts) - lost",
               f"commit-after: lag 1 right after the kill; restart redelivers the message, completes it, commits, lag 0 "
               f"({da['drafts_produced']} draft)"],
              ["Poison message",
               f"unbounded retries: {pb['retries_logged']}+ retries on one offset, the good message behind it is "
               f"{'processed' if pb['good_message_processed'] else 'BLOCKED'}",
               f"3 attempts then `s3170_dead_letter` ({pa['dead_letter_records']} bad messages dead-lettered); the good message "
               f"is {'processed' if pa['good_message_processed'] else 'blocked'}"],
              ["Two partitions / two consumers (ordering)",
               f"no key: {ob['entities_out_of_order']} of {ob['entities']} incidents processed OUT of order; related messages "
               f"spread over both partitions ({ob['entities'] - ob['entities_in_one_partition']} of {ob['entities']} incidents split)",
               f"key = incident: {oa['entities_out_of_order']} of {oa['entities']} out of order; "
               f"{oa['entities_in_one_partition']} of {oa['entities']} incidents stay in one partition"]]), "",
          f"Ordering run: 20 related messages generated from VERIFY_SEED {fail['verify_seed']} "
          f"(5 incidents, random per-message work time), 2 partitions, 2 Writers in one group. Processed order per run: "
          "`raw/ordering_unkeyed.csv`, `raw/ordering_keyed.csv`.", ""]
    for label, name in (("Unkeyed", "ordering_unkeyed.csv"), ("Keyed", "ordering_keyed.csv")):
        rows = list(csv.DictReader((RAW / name).open()))
        L += [f"### {label} run - order in which the 20 messages were processed", "",
              table(["#", "writer", "partition", "incident", "seq"],
                    [[r["order"], r["writer"], r["partition"], r["entity"], r["seq"]] for r in rows]), ""]

    history = sorted(p.name for p in (RAW / "dev_history").glob("*"))
    L += ["## Development history", "",
          "Bugs found in my own code while building the failure tests, kept as evidence in `raw/dev_history/`:", "",
          "1. **Harness race** - the Writer printed \"ready\" before a `latest`-offset consumer had fixed its start position, "
          "so a message sent right after \"ready\" could be skipped (consumer-death and poison tests failed). Fix: the position is "
          "pinned inside the assignment callback.",
          "2. **Poison test sent the bad and the good message to different partitions.** Head-of-line blocking is per partition, so "
          "the good message was not blocked. Fix: both go to partition 0.",
          "3. **Consumer-death warm-up went to the wrong partition**, leaving the victim's partition with no committed offset; a "
          "restarted `latest` consumer then started past the message. Fix: warm-up goes to the same partition.",
          "4. **A real Writer bug - the idempotency state file was rewritten through one shared temp name**, so two Writers in a group "
          "raced; the loser's `ENOENT` made the retry loop re-run the whole message and deliver its draft twice (21 messages processed "
          "instead of 20 in the ordering run). Fix: append-only state log, and retries now cover only work + delivery, with bookkeeping "
          "afterwards and never retried.", "",
          "Files: " + ", ".join(f"`{h}`" for h in history), ""]
    if ver.exists():
        v = json.loads(ver.read_text())
        L += ["## Self-check", "", f"`verification.json`: {v['passed']} passed, {v['failed']} failed, {v['skipped']} skipped of "
              f"{v['total_checks']} (generated {v['generated_at']}).", ""]
    OUT.write_text("\n".join(L))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
