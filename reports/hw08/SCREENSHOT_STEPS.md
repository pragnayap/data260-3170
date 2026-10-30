# HW8 — screenshots you need to take

Rules from the handout: **your name must be visible in every terminal screenshot** (points are deducted otherwise). Every
HW8 script prints a banner with your name as its first line. For plain commands, run
`echo "Pragnaya Priyadarshini (Lucky) - HW8"` first and keep that line in the frame. Paste each image under the matching
red `[ Screenshot ... ]` line in `Priyadarshini_HW8.docx`. Use a large terminal font and a tall window.

## Before you start (keep the Mac plugged in; in a spare tab run `caffeinate -dims`)
1. Start Docker Desktop and wait until it is running.
2. `cd "/Users/ritchit/Desktop/DATA 260--Agentic AI-Homework/data260-3170"`
3. Make sure the stack is up and your old local backend is NOT using port 8470:
   ```bash
   docker compose up -d                 # kafka + worker + api (already running unless you restarted)
   docker ps                            # s3170_kafka (healthy), s3170_worker, s3170_api
   ```
4. For Part 2 only: Ollama must be running (`curl localhost:11434/api/tags`).

## Part 1 — request/response over Kafka
| # | Screenshot | Commands |
|---|---|---|
| 1.1 | `docker ps` (Kafka, worker, API) + the worker "Consumer is ready and listening..." line + the API "started at http://127.0.0.1:8470" line | `echo "Pragnaya Priyadarshini (Lucky) - HW8"` then `docker ps` then `docker logs s3170_worker \| grep ready` then `docker logs s3170_api \| grep started` |
| 1.2 | CREATE_INCIDENT request and response (operation, entity data, incident_id, success, correlation_id) | `cd code/hw08 && ../../.venv/bin/python homework_demo.py` — the first screen (steps 1–7) |
| 1.3 | message-flow logs: sent to `s3170_entity_requests`, worker received/processed, reply on `s3170_entity_responses`, client received | the same run, scroll to steps 8–10 (GET_INCIDENT) |
| 1.4 | the full CREATE → GET sequence in order | the same run; one tall screenshot or two stacked |
| 1.5 | FastAPI wrapper: POST (201) + GET (200) + the API container's Kafka log lines | the commands are in `reports/hw08/raw/part1_api_run.txt`; then `docker logs s3170_api \| grep "\[API" \| tail -8` |

## Part 2 — three-agent pipeline (takes about 3 minutes with the local model)
Use four terminals, all `cd code/hw08` first. Stop any older agents first (`pkill -f planner.py; pkill -f reviewer.py; pkill -f writer.py`).
| Terminal | Command |
|---|---|
| 1 | `echo "Pragnaya Priyadarshini (Lucky) - HW8 planner"; ../../.venv/bin/python planner.py` |
| 2 | `echo "Pragnaya Priyadarshini (Lucky) - HW8 writer"; ../../.venv/bin/python writer.py` |
| 3 | `echo "Pragnaya Priyadarshini (Lucky) - HW8 reviewer"; ../../.venv/bin/python reviewer.py` |
| 4 | `../../.venv/bin/python send_question.py` (prints your name, then waits for the final message) |

| # | Screenshot |
|---|---|
| 2.1 | topics from the Kafka CLI: `make topics-hw08` (run from the repo root) — then `docker exec s3170_kafka /opt/kafka/bin/kafka-topics.sh --describe --topic s3170_tasks --bootstrap-server localhost:9092` to show **PartitionCount: 2** |
| 2.2 | all four terminals visible together after the question is answered |
| 2.3 | one message journey, one stage per line: `cat reports/hw08/raw/pipeline_journey.txt` (a real earlier run of the same code), or grep your own four logs for the correlation_id |
| 2.4 | the final JSON in terminal 4 (status + answer) |

When finished, stop the agents (Ctrl-C in terminals 1–3). **They must be stopped before Part 3**, or they also consume the test messages.

## Part 3 — failure behavior (no model needed; each command prints your name first)
```bash
cd code/hw08
../../.venv/bin/python failure_tests.py duplicate     # ~1 min   -> 3.1
../../.venv/bin/python failure_tests.py death         # ~1.5 min -> 3.2
../../.venv/bin/python failure_tests.py poison        # ~30 s    -> 3.3
../../.venv/bin/python failure_tests.py ordering      # ~30 s    -> 3.4
```
(`failure_tests.py all` runs all four in about 3 minutes; each scenario prints its before and after.) These runs write
`reports/hw08/raw/failure_test_<name>.json` — extra files you can delete or leave uncommitted; they do not replace the evidence in the report.

| # | What the screenshot must show |
|---|---|
| 3.1 | before: 2 drafts / 2 side effects; after: 1 draft, the replay logged `DUPLICATE ... ignored`, including after a Writer restart |
| 3.2 | the kill, the consumer-group table (committed vs log-end, lag), the restart: before = lost, after = lag 1 → redelivered → committed → lag 0 |
| 3.3 | before: endless `RETRY`, later message blocked; after: `RETRY 1/3, 2/3, GIVE UP, DEAD-LETTER`, then the good message processed |
| 3.4 | both ordering runs: processing order table and the per-incident `IN ORDER` / `OUT OF ORDER` lines |

## Self-check (optional)
`make verify-hw08` (about 5 minutes, needs Kafka up and **the Part 2 agents stopped**). It rewrites `reports/hw08/verification.json`;
afterwards run `git checkout -- reports/hw08/verification.json` so the committed, clean-tree version stays.

## Finish
1. Fill the red placeholders: the tagged commit hash and your AI_USE answers.
2. Export as **`Priyadarshini_HW8.pdf`** into `reports/hw08/` (14 pt bold headings, 12 pt subheadings, 11 pt body — already set).
3. Commit and tag (`hw8`), push `main` and the tag, confirm the repo link works and both collaborators still have access.
