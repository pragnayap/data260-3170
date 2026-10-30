# HW8 - METRICS

Generated from `reports/hw08/raw/` by `code/hw08/build_metrics.py`.

## Section 0 - configuration

| Value | Mine |
|---|---|
| SID4 | 3170 |
| PORT_BASE | 8470 |
| PREFIX | s3170 |
| SEED | 3170 |
| VERIFY_SEED | 263170 |
| DOMAIN_ID | 2 (Municipal Transit Incidents; entity = Transit Incident) |
| Hardware | Intel Core i9-9880H x86_64, 16 GB RAM, macOS 15, Docker Desktop (7.6 GB) |
| Local model (Part 2 agents) | qwen3:8b via Ollama, CPU-only; failure tests use stub drafts |
| Kafka | apache/kafka:3.8.0 (KRaft, single broker) in Docker; client confluent-kafka 2.16.1 |
| Commit at generation time | a76e45f (final tagged hash goes in the report) |

## Part 1 - request/response over Kafka

Topics: `s3170_entity_requests` (1 partition), `s3170_entity_responses` (1 partition). Operations: `CREATE_INCIDENT`, `GET_INCIDENT` for the Transit Incident entity. Evidence: `raw/part1_demo_run.txt` (the 10-step demo with the worker container's own log lines) and `raw/part1_api_run.txt` (HTTP calls through the FastAPI wrapper).

| Call | Result |
|---|---|
| POST /incidents (valid) | 201 Created, incident_id (UUID), `X-Correlation-Id` header |
| GET /incidents/{id} | 200 OK, entity returned, correlation_id echoed |
| GET /incidents/does-not-exist | 404, `Incident not found`, correlation_id echoed |
| POST /requests {operation: DROP_EVERYTHING} | 400, `Unknown operation`, correlation_id echoed |

## Part 2 - three-agent pipeline

Topics: `s3170_inbox`, `s3170_tasks` (2 partitions), `s3170_drafts`, `s3170_final`. One complete journey (planner, writer and reviewer are separate processes; no agent calls another): `raw/pipeline_journey.txt`.

```
09:35:33.819 [YOU     ] SEND  topic=s3170_inbox partition=0 offset=0 correlation_id=b7ce8dd1-f4ac-4eeb-8183-174329d22e3a
09:35:33.820 [PLANNER ] RECV  topic=s3170_inbox partition=0 offset=0 correlation_id=b7ce8dd1-f4ac-4eeb-8183-174329d22e3a question='What should a rider do when their bus is cancelled and the next one i
09:38:03.478 [PLANNER ] PLAN  correlation_id=b7ce8dd1-f4ac-4eeb-8183-174329d22e3a steps=['Check for alternative transportation options like a taxi or ride-sharing service.', "Look for real-time update
09:38:03.505 [PLANNER ] SEND  topic=s3170_tasks partition=1 offset=0 correlation_id=b7ce8dd1-f4ac-4eeb-8183-174329d22e3a
09:38:03.523 [writer-1] RECV  topic=s3170_tasks partition=1 offset=0 correlation_id=b7ce8dd1-f4ac-4eeb-8183-174329d22e3a
09:38:31.554 [writer-1] SEND  topic=s3170_drafts partition=0 offset=0 correlation_id=b7ce8dd1-f4ac-4eeb-8183-174329d22e3a
09:38:31.572 [REVIEWER] RECV  topic=s3170_drafts partition=0 offset=0 correlation_id=b7ce8dd1-f4ac-4eeb-8183-174329d22e3a
09:38:31.578 [REVIEWER] REVIEW correlation_id=b7ce8dd1-f4ac-4eeb-8183-174329d22e3a status=approved (draft passes length and content checks)
09:38:31.593 [REVIEWER] SEND  topic=s3170_final partition=0 offset=0 correlation_id=b7ce8dd1-f4ac-4eeb-8183-174329d22e3a
09:38:31.615 [YOU     ] RECV  topic=s3170_final partition=0 offset=0 correlation_id=b7ce8dd1-f4ac-4eeb-8183-174329d22e3a
```

## Part 3 - failure behaviour (each scenario run against real Kafka, before and after the fix)

| Failure scenario | Before fix | After fix |
|---|---|---|
| Duplicate delivery (same correlation_id replayed) | 2 messages sent -> 2 drafts, 2 side effects (duplicate work) | 3 messages sent (incl. a replay after a Writer restart) -> 1 draft, 1 side effect, 2 duplicates ignored |
| Consumer killed mid-work | auto-commit: offset committed before the work finished; after SIGKILL + restart the message is never redelivered (0 drafts) - lost | commit-after: lag 1 right after the kill; restart redelivers the message, completes it, commits, lag 0 (1 draft) |
| Poison message | unbounded retries: 12+ retries on one offset, the good message behind it is BLOCKED | 3 attempts then `s3170_dead_letter` (2 bad messages dead-lettered); the good message is processed |
| Two partitions / two consumers (ordering) | no key: 3 of 5 incidents processed OUT of order; related messages spread over both partitions (4 of 5 incidents split) | key = incident: 0 of 5 out of order; 5 of 5 incidents stay in one partition |

Ordering run: 20 related messages generated from VERIFY_SEED 263170 (5 incidents, random per-message work time), 2 partitions, 2 Writers in one group. Processed order per run: `raw/ordering_unkeyed.csv`, `raw/ordering_keyed.csv`.

### Unkeyed run - order in which the 20 messages were processed

| # | writer | partition | incident | seq |
|---|---|---|---|---|
| 1 | writer-A | 1 | INC-8446 | 1 |
| 2 | writer-B | 0 | INC-5457 | 1 |
| 3 | writer-B | 0 | INC-2393 | 1 |
| 4 | writer-A | 1 | INC-5457 | 2 |
| 5 | writer-A | 1 | INC-8206 | 1 |
| 6 | writer-B | 0 | INC-4412 | 1 |
| 7 | writer-A | 1 | INC-2393 | 3 |
| 8 | writer-A | 1 | INC-5457 | 3 |
| 9 | writer-B | 0 | INC-2393 | 2 |
| 10 | writer-A | 1 | INC-5457 | 5 |
| 11 | writer-B | 0 | INC-4412 | 2 |
| 12 | writer-A | 1 | INC-4412 | 3 |
| 13 | writer-A | 1 | INC-2393 | 4 |
| 14 | writer-B | 0 | INC-5457 | 4 |
| 15 | writer-A | 1 | INC-2393 | 5 |
| 16 | writer-A | 1 | INC-4412 | 5 |
| 17 | writer-B | 0 | INC-5457 | 6 |
| 18 | writer-B | 0 | INC-8206 | 2 |
| 19 | writer-B | 0 | INC-4412 | 4 |
| 20 | writer-B | 0 | INC-2393 | 6 |

### Keyed run - order in which the 20 messages were processed

| # | writer | partition | incident | seq |
|---|---|---|---|---|
| 1 | writer-B | 1 | INC-2393 | 1 |
| 2 | writer-A | 0 | INC-5457 | 1 |
| 3 | writer-B | 1 | INC-2393 | 2 |
| 4 | writer-A | 0 | INC-8446 | 1 |
| 5 | writer-B | 1 | INC-2393 | 3 |
| 6 | writer-B | 1 | INC-2393 | 4 |
| 7 | writer-A | 0 | INC-5457 | 2 |
| 8 | writer-B | 1 | INC-2393 | 5 |
| 9 | writer-B | 1 | INC-2393 | 6 |
| 10 | writer-A | 0 | INC-4412 | 1 |
| 11 | writer-A | 0 | INC-8206 | 1 |
| 12 | writer-A | 0 | INC-4412 | 2 |
| 13 | writer-A | 0 | INC-5457 | 3 |
| 14 | writer-A | 0 | INC-5457 | 4 |
| 15 | writer-A | 0 | INC-5457 | 5 |
| 16 | writer-A | 0 | INC-5457 | 6 |
| 17 | writer-A | 0 | INC-4412 | 3 |
| 18 | writer-A | 0 | INC-8206 | 2 |
| 19 | writer-A | 0 | INC-4412 | 4 |
| 20 | writer-A | 0 | INC-4412 | 5 |

## Development history

Bugs found in my own code while building the failure tests, kept as evidence in `raw/dev_history/`:

1. **Harness race** - the Writer printed "ready" before a `latest`-offset consumer had fixed its start position, so a message sent right after "ready" could be skipped (consumer-death and poison tests failed). Fix: the position is pinned inside the assignment callback.
2. **Poison test sent the bad and the good message to different partitions.** Head-of-line blocking is per partition, so the good message was not blocked. Fix: both go to partition 0.
3. **Consumer-death warm-up went to the wrong partition**, leaving the victim's partition with no committed offset; a restarted `latest` consumer then started past the message. Fix: warm-up goes to the same partition.
4. **A real Writer bug - the idempotency state file was rewritten through one shared temp name**, so two Writers in a group raced; the loser's `ENOENT` made the retry loop re-run the whole message and deliver its draft twice (21 messages processed instead of 20 in the ordering run). Fix: append-only state log, and retries now cover only work + delivery, with bookkeeping afterwards and never retried.

Files: `failure_tests_run1_harness_bugs.txt`, `failure_tests_run2_before_deadletter_count_fix.txt`, `failure_tests_run3_state_file_race_and_warmup_partition.txt`, `failure_tests_run4_repeatability_first_of_two.txt`, `failure_tests_summary_run1_harness_bugs.json`, `failure_tests_summary_run2.json`, `failure_tests_summary_run3.json`

## Self-check

`verification.json`: 16 passed, 0 failed, 0 skipped of 16 (generated 2026-10-30T17:01:31+00:00).
