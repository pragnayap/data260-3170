# DATA260 - convenience targets. Everything here is a one-line wrapper around a
# command already documented in README.md; nothing happens only via make.
#
# SID4 3170 -> PORT_BASE 8470, PREFIX s3170, DOMAIN_ID 2 (Municipal Transit Incidents)

PY      ?= .venv/bin/python
PORT    ?= 8470
APP_DIR := code/web_application

.PHONY: help install nltk run corpus corpus-verify warmup rag metrics verify-hw03 hw3 clean-hw3 \
        seed-hw04 n1-hw04 verify-hw04 frontend-install frontend-dev hw4 \
        seed-hw05 faults-hw05 contracts-hw05 test-hw05 safety-hw05 agent-scenarios verify-hw05 \
        mongo-up sweep-hw06 consolidate-hw06 agent-check-hw06 metrics-hw06 test-hw06 file-memory verify-hw06 \
        seed-hw07 test-hw07 demo-hw07 reliability-hw07 reflexion-hw07 bike-data-hw07 snapshots-hw07 attacks-hw07 verify-hw07 \
        metrics-hw07 runlog-hw07 report-hw07 \
        kafka-up-hw08 topics-hw08 demo-hw08 agents-hw08 failures-hw08 verify-hw08 down-hw08

help:
	@echo "install       install deps from requirements.txt, then the NLTK data"
	@echo "nltk          download just the NLTK sentence tokenizer"
	@echo "run           serve the authenticated app on port $(PORT)"
	@echo "corpus        download the transit corpus + write SOURCES.md and CORPUS_MANIFEST.json"
	@echo "corpus-verify re-hash data/corpus against the manifest (no network)"
	@echo "warmup        Tiny Shakespeare smoke test of the three chunkers"
	@echo "rag           run the three retrieval pipelines, tee-ing RUN_LOG.txt"
	@echo "metrics       recompute reports/hw03/METRICS.md from reports/hw03/raw/"
	@echo "verify-hw03   run the HW3 self-check -> reports/hw03/verification.json"
	@echo "hw3           corpus -> rag -> metrics -> verify-hw03"
	@echo "seed-hw04     seed MySQL with 5,000 incidents + 200 routes from SEED"
	@echo "n1-hw04       run the 180-request N+1 measurement -> reports/hw04/raw/"
	@echo "verify-hw04   run the HW4 self-check -> reports/hw04/verification.json"
	@echo "frontend-install  npm install in code/frontend"
	@echo "frontend-dev  run the Vite dev server on 8471"
	@echo "hw4           seed-hw04 -> n1-hw04 -> verify-hw04 (backend must already be running: make run)"
	@echo "seed-hw05     seed MySQL for HW5: 200 routes + 5,000 incidents (new columns, RESTRICT FK)"
	@echo "faults-hw05   150-call seeded fault injection -> reports/hw05/raw/"
	@echo "contracts-hw05  tool contracts from the live MCP schemas -> reports/hw05/raw/tool_contracts.md"
	@echo "test-hw05     offline Part 4/5 test runner (no DB, no network, no LLM)"
	@echo "safety-hw05   Part 5.I allowed vs blocked call demo"
	@echo "agent-scenarios  Ollama agent scenarios -> METRICS.md + raw/agent_runs.jsonl"
	@echo "verify-hw05   run the HW5 self-check -> reports/hw05/verification.json"
	@echo "mongo-up      start the s3170_mongo Docker container (MongoDB 7) on 27017"
	@echo "sweep-hw06   Part 3: 4 settings x (30-message conversation + 5 probes) -> reports/hw06/raw/"
	@echo "consolidate-hw06  Part 4: consolidate the 55-line MEMORY test file -> reports/hw06/memory_test/"
	@echo "agent-check-hw06  Part 4: generate a function under AGENT.md and check it complies"
	@echo "metrics-hw06 rebuild reports/hw06/METRICS.md from raw/"
	@echo "test-hw06    offline file-memory unit tests"
	@echo "file-memory  interactive CLI with /memory /compact /dream /help"
	@echo "verify-hw06  run the HW6 self-check -> reports/hw06/verification.json"
	@echo "seed-hw07    add username/role to users and seed reader/writer/moderator (JWT login)"
	@echo "test-hw07    Part 6 file tools + safety-gate test (no model)"
	@echo "demo-hw07    Part 2 tasks A/B/C + nonexistent-ID case (needs Ollama)"
	@echo "reliability-hw07  Part 2 20-attempt reliability run -> reports/hw07/raw/ (needs Ollama)"
	@echo "reflexion-hw07    Part 3 original-vs-Reflexion comparison -> reports/hw07/raw/ (needs Ollama)"
	@echo "bike-data-hw07    Part 4 build the two Capital Bikeshare datasets (downloads public files)"
	@echo "snapshots-hw07    Part 4 freeze the pricing page (text + SHA-256 + access time)"
	@echo "attacks-hw07      Part 5 prompt-injection before/after table (needs Ollama)"
	@echo "verify-hw07  run the HW7 self-check -> reports/hw07/verification.json"
	@echo "metrics-hw07 rebuild reports/hw07/METRICS.md from raw/"
	@echo "runlog-hw07  rebuild reports/hw07/RUN_LOG.txt from the real run logs"
	@echo "report-hw07  rebuild reports/hw07/Priyadarshini_HW7.docx (screenshot placeholders to fill)"
	@echo "kafka-up-hw08  docker compose up: Kafka + worker + FastAPI (port 8470; stop local uvicorn first)"
	@echo "topics-hw08    create the 7 s3170_* topics with the Kafka CLI"
	@echo "demo-hw08      Part 1 homework_demo.py (CREATE_INCIDENT -> GET_INCIDENT over Kafka)"
	@echo "agents-hw08    Part 2: start planner, writer, reviewer (3 terminals) / send_question.py"
	@echo "failures-hw08  Part 3: duplicate, consumer death, poison message, ordering - before and after"
	@echo "verify-hw08    run the HW8 self-check -> reports/hw08/verification.json"
	@echo "down-hw08      docker compose down"

install:
	$(PY) -m pip install -r requirements.txt
	$(MAKE) nltk

# The semantic and sentence-window chunkers split on sentences using NLTK's
# punkt tokenizer. LlamaIndex fetches it lazily, part-way through the run;
# fetching it here means a network problem shows up now instead of several
# minutes into `make rag`, after the token stage has already been paid for.
nltk:
	$(PY) -m nltk.downloader punkt_tab stopwords

run:
	cd $(APP_DIR) && ../../$(PY) -m uvicorn app:app --reload --port $(PORT)

corpus:
	$(PY) code/fetch_corpus.py

corpus-verify:
	$(PY) code/fetch_corpus.py --verify

warmup:
	$(PY) code/run_rag_chunking.py --warmup

# caffeinate keeps the Mac awake: semantic chunking embeds every sentence in the
# corpus and is the slow one.
#
# python -u matters here. Piping to tee makes Python block-buffer stdout, so
# without it RUN_LOG.txt sits empty for the whole run and there is no way to
# tell progress from a hang. -u forces unbuffered output so the log streams.
rag: nltk
	caffeinate -i $(PY) -u code/run_rag_chunking.py 2>&1 | tee reports/hw03/RUN_LOG.txt

metrics:
	$(PY) code/summarize_rag_metrics.py

verify-hw03:
	$(PY) code/verify_hw03.py

hw3: corpus rag metrics verify-hw03

clean-hw3:
	rm -f reports/hw03/raw/retrieval_rows.* reports/hw03/raw/chunk_stats.json \
	      reports/hw03/raw/query_vectors.json reports/hw03/METRICS.md

seed-hw04:
	$(PY) code/seed_hw04.py

n1-hw04:
	$(PY) code/measure_n1.py

verify-hw04:
	$(PY) code/verify_hw04.py

frontend-install:
	cd code/frontend && npm install

frontend-dev:
	cd code/frontend && npm run dev

# Assumes the backend is already running (`make run` in another terminal) --
# unlike hw3, this can't boot+measure+shut-down in one shot because the N+1
# measurement needs a live server the whole time.
hw4: seed-hw04 n1-hw04 verify-hw04

seed-hw05:
	$(PY) -u code/seed_hw05.py

faults-hw05:
	$(PY) -u code/mcp_servers/fault_injection.py

contracts-hw05:
	$(PY) -u code/mcp_servers/tool_contracts.py

test-hw05:
	$(PY) -u code/mcp_servers/test_tools.py

safety-hw05:
	$(PY) -u code/mcp_servers/agent_loop.py --demo-safety

agent-scenarios:
	$(PY) -u code/mcp_servers/agent_loop.py --scenarios

verify-hw05:
	$(PY) -u code/verify_hw05.py

# --- HW6 ---------------------------------------------------------------
# MongoDB runs in Docker (Homebrew has no mongod formula for this machine).
# `docker start` first so an existing container keeps its data volume.
mongo-up:
	docker start s3170_mongo 2>/dev/null || docker run -d --name s3170_mongo --restart unless-stopped \
	    -p 27017:27017 -v s3170_mongo_data:/data/db mongo:7.0

# Backend must be running (make run), plus MongoDB and Ollama. python -u + tee so the log streams.
sweep-hw06:
	$(PY) -u code/hw6/run_memory_sweep.py 2>&1 | tee -a reports/hw06/RUN_LOG.txt

consolidate-hw06:
	$(PY) -u code/hw6/run_consolidation_test.py 2>&1 | tee -a reports/hw06/RUN_LOG.txt

agent-check-hw06:
	$(PY) -u code/hw6/check_agent_compliance.py 2>&1 | tee -a reports/hw06/RUN_LOG.txt

metrics-hw06:
	$(PY) code/hw6/summarize_hw6.py

test-hw06:
	cd code/hw6 && ../../$(PY) -m pytest -q test_file_memory.py

file-memory:
	$(PY) code/hw6/file_memory_cli.py

verify-hw06:
	$(PY) -u code/verify_hw06.py

seed-hw07:
	$(PY) code/seed_hw07.py

test-hw07:
	$(PY) -u code/hw07/test_part6.py

demo-hw07:
	$(PY) -u code/hw07/part2_demo.py

reliability-hw07:
	$(PY) -u code/hw07/reliability.py

reflexion-hw07:
	$(PY) -u code/hw07/part3_compare.py

bike-data-hw07:
	$(PY) -u code/hw07/bike/build_data.py

snapshots-hw07:
	$(PY) code/hw07/bike/snapshot.py

attacks-hw07:
	$(PY) -u code/hw07/bike/part5_attacks.py

verify-hw07:
	$(PY) -u code/verify_hw07.py

metrics-hw07:
	$(PY) code/hw07/build_metrics.py

runlog-hw07:
	$(PY) code/hw07/build_runlog.py

report-hw07:
	$(PY) code/hw07/build_report.py

kafka-up-hw08:
	docker compose up -d --build

topics-hw08:
	docker exec s3170_kafka /opt/kafka/bin/kafka-topics.sh --create --if-not-exists --topic s3170_entity_requests --partitions 1 --replication-factor 1 --bootstrap-server localhost:9092
	docker exec s3170_kafka /opt/kafka/bin/kafka-topics.sh --create --if-not-exists --topic s3170_entity_responses --partitions 1 --replication-factor 1 --bootstrap-server localhost:9092
	docker exec s3170_kafka /opt/kafka/bin/kafka-topics.sh --create --if-not-exists --topic s3170_inbox --partitions 1 --replication-factor 1 --bootstrap-server localhost:9092
	docker exec s3170_kafka /opt/kafka/bin/kafka-topics.sh --create --if-not-exists --topic s3170_tasks --partitions 2 --replication-factor 1 --bootstrap-server localhost:9092
	docker exec s3170_kafka /opt/kafka/bin/kafka-topics.sh --create --if-not-exists --topic s3170_drafts --partitions 1 --replication-factor 1 --bootstrap-server localhost:9092
	docker exec s3170_kafka /opt/kafka/bin/kafka-topics.sh --create --if-not-exists --topic s3170_final --partitions 1 --replication-factor 1 --bootstrap-server localhost:9092
	docker exec s3170_kafka /opt/kafka/bin/kafka-topics.sh --create --if-not-exists --topic s3170_dead_letter --partitions 1 --replication-factor 1 --bootstrap-server localhost:9092
	docker exec s3170_kafka /opt/kafka/bin/kafka-topics.sh --list --bootstrap-server localhost:9092

demo-hw08:
	cd code/hw08 && ../../$(PY) -u homework_demo.py

agents-hw08:
	@echo "Run each in its own terminal (cd code/hw08 first):"
	@echo "  ../../.venv/bin/python planner.py"
	@echo "  ../../.venv/bin/python writer.py"
	@echo "  ../../.venv/bin/python reviewer.py"
	@echo "  ../../.venv/bin/python send_question.py"

failures-hw08:
	cd code/hw08 && ../../$(PY) -u failure_tests.py all

verify-hw08:
	$(PY) -u code/verify_hw08.py

down-hw08:
	docker compose down
