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
