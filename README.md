# DATA-260: Agentic AI

**Student:** Pragnaya Priyadarshini
**SID4:** 3170 | **PORT_BASE:** 8470 | **PREFIX:** s3170 | **DOMAIN_ID:** 2 (Municipal Transit Incidents)

This repository is extended with new code/reports for every homework this semester.
Shared application code lives in `code/` and `src/`; homework-specific reports/results
live in `reports/hwNN/`.

## Setup (one-time)

```bash
# Python 3.12 venv with project dependencies
python3.12 -m venv .venv
source .venv/bin/activate
pip install langchain langchain-community langchain-ollama

# Ollama + model
brew install ollama
brew services start ollama
ollama pull qwen3:8b
```

## HW1 — reproducible run instructions

### Part I/II — Web form (HTML/JS)
Open directly in a browser:
```
code/web_application/HW1-PragnayaPriyadarshini.html
```

### Docker (local)
```bash
cd code
docker build -t s3170-hw1-web .
docker run -d -p 8470:8470 --name s3170-hw1-web-run s3170-hw1-web
# visit http://localhost:8470
```

### AWS ECS
Image pushed to ECR (`s3170-hw1-web`), deployed as a 1-task Fargate service
(`s3170-hw1-cluster` / `s3170-hw1-service`) listening on port 8470. See
`reports/hw01/` screenshots for the running public-IP deployment.

### Part 2 — Agentic AI demo
```bash
source .venv/bin/activate
cd code
python agents_demo.py --title "<title>" --content "<content>" --temperature 0.0
```

### Part 3 — Non-determinism experiment (40 runs)
```bash
cd code
caffeinate -i python run_nondeterminism.py 2>&1 | tee -a "../reports/hw01/RUN_LOG.txt"
```
Fixed input: `reports/hw01/cases/nondeterminism_input.json`
Results: `reports/hw01/raw/`, `reports/hw01/METRICS.md`

### Part 4 — Model client + token accounting
```bash
cd code
python hw1_client.py
# type messages; /stats for stats; /exit to quit
```

### Verification
```bash
cd code
python verify_hw01.py
```
Output: `reports/hw01/verification.json`

## HW2 — reproducible run instructions

Dependencies are pinned in `requirements.txt` (HW2 adds `fastapi`, `uvicorn`,
`email-validator`, and `langgraph`):

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Parts 1 & 2 — Responsive front end + FastAPI backend
```bash
cd code/web_application
uvicorn app:app --reload --port 8470
# visit http://localhost:8470
```
Styles are in `code/web_application/styles.css` (linked from the HTML, served by the
backend at `/styles.css`). The page serves the incident form, the list view with search, and buttons for
"update incident #1" and "delete newest". Loading, empty and error states are all
visible; the layout is usable down to 375px.

### Part 3 — Stateful agent graph
```bash
cd code
python agents_graph.py --stream          # prints each node's state update
python agents_graph.py --turn-ceiling 10

# Part 3 Step 6 - force the Reviewer to always object and watch the graph route
# back to the Planner until the turn ceiling stops it:
python agents_graph.py --force-reviewer-issue --turn-ceiling 6

# Part 4.2 - corrupt the first Planner output so Pydantic rejects it, and watch
# the validation error fed back and corrected on the retry:
python agents_graph.py --force-schema-failure --turn-ceiling 8
```
All LLM calls route through `src/model_client.py`; `verify_hw02.py` asserts this
statically. Transcript of the loop test: `reports/hw02/raw/loop_test_part3_step6.txt`.

### Part 4 — Schema validation and loop-safety experiments (75 runs)
```bash
cd code
caffeinate -i python run_schema_experiments.py 2>&1 | tee ../reports/hw02/RUN_LOG.txt
# or one experiment at a time:
python run_schema_experiments.py --only schema
python run_schema_experiments.py --only ceiling
python run_schema_experiments.py --only adversarial
```
Frozen inputs: `reports/hw02/cases/`. Results: `reports/hw02/raw/`, `reports/hw02/METRICS.md`.

All 75 runs share one `ModelClient` and one compiled graph in a single process, so Ollama
keeps `qwen3:8b` resident. A cold call costs ~26s against ~9s warm, so running the
experiments as separate processes takes roughly four times as long.

### Verification
```bash
python code/verify_hw02.py               # full smoke test, starts the API and runs the graph
python code/verify_hw02.py --skip-graph  # static + HTTP checks only
```
Output: `reports/hw02/verification.json`

## Part 4 — Written answers

**Why is prior conversation context resent with every turn?**
> LLM APIs (including Ollama's) are stateless between requests — the model itself does not
> remember earlier calls. The only way it can respond consistently with what was said
> before is if the caller resends the entire conversation history (system + all prior
> user/assistant messages) as part of every new request. `ModelClient.complete()` does
> exactly this: each call to `_llm.invoke(lc_messages)` passes the full `history` list, not
> just the newest message.

**How is a system prompt different from a user message?**
> A system prompt sets standing instructions/behavior for the whole conversation (e.g.
> `AGENT.md`'s "respond with bullet points only" rule), and is typically weighted by the
> model as higher-priority framing rather than as something to "answer." A user message is
> one turn of actual conversational content the model is expected to respond to. In this
> project, the system prompt was sent once (as the first message in `history`) but still
> applied to every subsequent turn — visible in the `hw1_client.py` run, where even
> non-code-review questions (turns 4 and 5) came back in bullet format because the system
> instruction was still part of the resent history.

**Why do input tokens grow over a conversation?**
> Because the entire conversation history is resent every turn (see above), and each new
> turn appends both the previous user message and the model's own prior reply into that
> history. This was directly observable in the actual run: input tokens climbed
> 116 → 154 → 223 → 275 → 351 across the 5 turns, growing by roughly the size of the
> previous turn's user message + assistant reply each time.

**What eventually limits that growth?**
> The model's context window (`num_ctx`, set to 2048 tokens in `model_client.py`) — once
> the cumulative conversation history approaches that limit, older turns would need to be
> truncated or summarized, or the request would fail/get cut off, since the model can only
> attend to a fixed maximum number of tokens per call.

## Assignments

| Homework | Folder | Reports |
|---|---|---|
| HW1 | [`code/`](code/), [`src/`](src/) | [`reports/hw01/`](reports/hw01/) |
| HW2 | [`code/`](code/), [`src/`](src/) | [`reports/hw02/`](reports/hw02/) |
