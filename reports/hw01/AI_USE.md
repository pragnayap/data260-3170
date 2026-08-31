# AI Use Disclosure — HW1

## 1. What did you use an AI assistant for, and what did you do yourself?

I wrote the HTML form (`HW1-PragnayaPriyadarshini.html`), the JavaScript validation logic
in `hw1.js`, `DOMAIN_SCHEMA.md`, the transit-incident scenario used as test input
("Bus number 522..."), and the written analysis of the non-determinism results myself.

I used Claude (via Claude Code) for infrastructure and backend implementation work:
setting up and debugging the Docker build and AWS ECS deployment (including diagnosing
a security group misconfiguration that was blocking the ECS task), implementing
`agents_demo.py` (the Planner/Reviewer/Finalizer pipeline and JSON-coercion logic) after
I asked it to write that file directly, implementing `src/model_client.py` and
`code/hw1_client.py` for Part 4's token-accounting adapter, writing the
`run_nondeterminism.py` experiment runner and `verify_hw01.py` self-check script, and
installing/configuring the local Ollama environment (including discovering that
`qwen3:8b`'s default "thinking" mode needed to be disabled for reasonable latency). I
reviewed and tested all of this code myself before treating it as final (running it,
checking outputs, and fixing issues such as the security group rules and a multi-line
paste bug in the CLI demo).

## 2. One AI-produced output that was wrong/unsuitable, OR one thing you independently verified

When I tested the model at first, it was super slow for my prompt "Say hello in exactly
5 words" — it took 60.29 seconds because qwen3:8b is a reasoning model that generates a
long internal chain of thought before giving me the actual answer (visible in the
terminal as a "Thinking..." block where it worked through several greeting options
before settling on one). Then I tested the same prompt in the CLI with `--think=false`
and the response time was 1.78 seconds, which was roughly 34x less. After applying this
fix in ChatOllama's parameters using LangChain (`reasoning=False`), it worked and the
time was 1.73 seconds, matching the CLI result. This verification saved a lot of time —
without it, my Part 3 experiment would have taken a few more hours, which was reduced to
60 minutes.

## 3. How did you detect the problem or verify the result?

I verified this by running the same exact prompt in CLI and in LangChain code, using
`--think=false` in the CLI flag and `reasoning=false` in LangChain's code, and after
seeing the response time found the difference.

## 4. What did you change, and why does it work now?

I added `reasoning=False` as a parameter to `ChatOllama` in `src/model_client.py` and
`code/agents_demo.py`. This tells Ollama to skip qwen3:8b's internal "thinking" step,
which normally generates a long chain-of-thought reasoning trace before producing the
final answer. Disabling it works because the task here (extracting 3 tags + a short
summary) doesn't require multi-step reasoning — a direct answer is sufficient, so
skipping the thinking phase doesn't reduce output quality but avoids the ~34x latency
overhead it added (60.29s vs. 1.73-1.78s per call, confirmed through both the CLI flag
and the LangChain parameter).
