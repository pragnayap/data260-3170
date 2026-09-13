# METRICS — HW2 Part 4: Output Schema and Loop Safety

**Model:** qwen3:8b via Ollama, temperature 0.0, reasoning disabled, `num_ctx` 2048
**Adapter:** all node LLM calls routed through `src/model_client.py`
**Hardware:** Intel Core i9-9880H, 16 GB RAM, macOS 15.7.9 — CPU inference, ~9s per warm
model call
**Frozen input:** `reports/hw02/cases/schema_input.json`
**Adversarial input:** `reports/hw02/cases/adversarial_input.json`

**Primary data:** `raw/runs.jsonl`, `raw/schema_runs.csv`, `raw/schema_summary.json` — 75
runs, all produced by the final code in one session.
**Secondary data:** `raw/runs_batch1.jsonl`, `raw/schema_summary_batch1.json` and
`RUN_LOG_batch1.txt` — an earlier 75-run batch, retained because comparing the two
produced the most significant finding in this assignment (§4.6).

Latency is measured per graph run — the whole `graph.invoke()`, including every Planner
and Reviewer turn the run needed, not a single model call.

---

## 4.1–4.2 Schema and retry mechanism

The Planner's raw output is validated against `PlannerOutput` in `src/schemas.py`:
exactly three tags, each 3–30 characters, and a summary of at most 25 words. Output is
**never coerced**. On failure, `validate_planner_output()` returns flattened error text,
the router sends control back to the Planner, and `planner_node` appends the error to its
prompt so the next attempt corrects a named fault.

This is a deliberate departure from HW1's `coerce_reply()` in `agents_demo.py`, which
silently repairs bad output by padding tags and truncating the summary. Had the graph
validated coerced output, every run would have been "valid first attempt" by
construction, leaving nothing to measure.

---

## 4.3 Schema validation over 30 runs

Fixed input, turn ceiling 8, 30 runs.

| Outcome over 30 runs | Count | Mean latency (ms) |
|---|---|---|
| Valid first attempt | **30** | 62,260 |
| Valid after 1 retry | 0 | — |
| Valid after 2+ retries | 0 | — |
| Hit turn ceiling | 0 | — |

Latency spread: min 60,575 ms, median 62,255 ms, max 65,301 ms.

**The schema was never violated.** Pydantic rejected nothing in 30 runs, so the schema
retry path was not exercised here. At temperature 0 on an ordinary single-topic incident,
qwen3:8b reliably produces three tags and a short summary — HW1's non-determinism
experiment found the same determinism (1 distinct tag set across 20 runs at temperature
0.0). The schema-retry path is exercised in §4.5.

**But the runs were not short.** Each took 7 turns and 3 Planner attempts, because the
*Reviewer* sent the proposal back twice per run. The buckets above count schema retries
only; these were content objections, tracked separately in `issue_history`. See §4.6 —
those objections were wrong, and that is the interesting part.

---

## 4.4 Turn ceiling 2 versus 10

Same frozen input and model settings, 20 runs at each ceiling.

| Turn ceiling | Runs | Completed | Completion rate | Mean latency (ms) | Turns used | Planner attempts |
|---|---|---|---|---|---|---|
| 2 | 20 | 0 | **0.0%** | 9,022 | 2 | 1 |
| 10 | 20 | 20 | **100.0%** | 61,168 | 7 | 3 |

A run counts as completed when it reaches `END` on its own terms — a schema-valid proposal
the Reviewer then passed — rather than being cut off by the ceiling.

**Why ceiling 2 never completes.** It is a structural limit, not bad luck. The supervisor
increments the counter before every routing decision, so a ceiling of 2 buys exactly one
worker turn: the Planner runs, the counter reaches 2, and the router stops the graph
before the Reviewer has ever seen the proposal. The output is schema-valid but unreviewed.
Completion is impossible by construction, which is why the rate is 0/20 rather than low.

**Choice for deployment: ceiling 10.** Every completed run used exactly 7 turns, so the
minimum workable ceiling for this input is 7. Ceilings of 2, 4 and 6 would all fail. Ten
is the smallest of the offered options that clears 7 with margin for a run that needs one
more correction round.

The cost is real and should be stated plainly: 61,168 ms against 9,022 ms, about **6.8×**
the latency of ceiling 2. That is not the price of the ceiling itself — it is the price of
letting the Reviewer loop run to convergence. Ceiling 2 is cheap precisely because it
does no review at all, which is the same reason it never completes. Given a choice between
a fast unreviewed answer and a slow reviewed one, the reviewed answer is the deployable
one; but §4.6 shows most of that 6.8× is being spent on objections that should never have
been raised, so the honest recommendation is ceiling 10 **together with** the §4.5 fix.

---

## 4.5 Adversarial input

`reports/hw02/cases/adversarial_input.json`, turn ceiling 10, 5 runs.

| Metric | Result |
|---|---|
| Runs reaching the turn ceiling | **5 / 5 (100%)** |
| Turns used per run | 10, 10, 10, 10, 10 |
| Planner attempts per run | 5, 5, 5, 5, 5 |
| Schema retries per run | 0, 0, 0, 0, 0 |
| Mean latency | 149,383 ms |
| Versus the frozen input | **2.4× slower** (149,383 ms vs 62,260 ms) |

The observed ceiling-reaching rate is 5 of 5, exceeding the "at least four runs" the
assignment prefers. All five are bucketed `valid_first_attempt`: the *schema* was satisfied
immediately every time. Ceiling exhaustion and schema failure are different things, which
is why they are counted from different fields — these runs never failed validation once,
yet none terminated on their own.

### Why this input causes trouble

The input is a quarter-end digest spanning roughly ten distinct sub-incidents — two late
routes, a stale display board, out-of-service elevators, a faulty fare gate, a cancelled
night bus, a radio dead zone, two vendor tickets, and a two-step escalation path.

The schema allows a summary of at most 25 words. Ten sub-incidents cannot be stated in 25
words, so the Planner must generalise: *"Multiple transit routes and subsystems faced
delays, equipment outages, and vendor ticket issues with escalation."* The Reviewer then
objects under rule 2 — the summary asserts something the input does not state — because no
sentence in the input says "multiple subsystems faced outages"; the input lists them
individually.

The two constraints are in direct conflict. The word limit compels abstraction and the
faithfulness rule forbids it. The final tag set was identical in all five runs: a
reproducible structural failure, not model noise.

### Proposed fix

**Add a no-progress circuit breaker to the router.** Keep a hash of each Reviewer objection
set; if the same objection is raised twice in a row, the loop is not converging and further
turns cannot help. Stop and return the current schema-valid proposal, flagged "accepted
without Reviewer sign-off", instead of spending the remaining turns to arrive at the same
place.

On this data that single change would cut the adversarial case from ~149s to roughly 60s,
and would also cut the ordinary frozen input from ~62s to ~40s, since §4.6 shows its two
objections are the same rule-1 complaint repeated.

---

## 4.6 An unplanned finding: the Reviewer is prompt-format sensitive

Two full 75-run batches were collected. Between them, **one thing changed in the Reviewer's
input: how the proposal was formatted.**

- **Batch 1** passed the proposal as `json.dumps(proposal, indent=2)`.
- **Batch 2** passed it as plain text: `Tags: a; b; c\nSummary: …`

Everything else was identical — same model, same temperature 0.0, same frozen input, same
rules, same validator, same machine.

| | Batch 1 (JSON framing) | Batch 2 (plain-text framing) |
|---|---|---|
| Reviewer objections across 30 schema runs | **0** | **60** |
| Turns per run | 3 | 7 |
| Planner attempts per run | 1 | 3 |
| Mean latency, frozen input | 10,862 ms | 62,260 ms |
| Mean latency, ceiling 10 | 10,501 ms | 61,168 ms |
| Completion rate, ceiling 10 | 20/20 | 20/20 |
| Completion rate, ceiling 2 | 0/20 | 0/20 |
| Adversarial ceiling hits | 5/5 | 5/5 |

**Every structural result reproduced exactly.** Completion rates, ceiling behaviour and
adversarial outcomes are identical across both batches, which is real evidence that those
findings are robust. What changed by a factor of six is *latency*, and it changed entirely
because of the Reviewer's objection rate.

### The objections were wrong

All 60 objections in batch 2 were the same two, once per review:

```
[rule 1] 'Transit Center': The tag 'Transit Center' is about a subject the input never raises.
[rule 1] 'Bus Delay':      The tag 'Bus Delay' is about a subject the input never raises.
```

The input reads *"Delayed Line 22 bus at Downtown Transit Center … the 7:15am bus never
arrived."* Both tags are plainly supported. Worse, the Reviewer's own prompt names these
exact cases as acceptable:

> Tags are meant to be topical labels, so a tag NEVER has to appear word for word in the
> input. 'Service Failure' for a bus that never arrived, or 'Transit Center' for
> 'Downtown Transit Center', are both correct and must not be reported.

The model was told, in the same prompt, not to make the objection it then made 60 times.
The loop still converged — the Planner replaced the rejected tags with wordier synonyms
(`Bus Service Failure`, `Transit Communication Issues`) until the Reviewer stopped
objecting — so the output quality is unchanged. The six-fold latency bought nothing.

### What this means

An instruction-following failure this specific cannot be fixed by adding more instruction;
the counter-example was already in the prompt and was ignored. Two conclusions follow, and
they are the practical lesson of this assignment:

1. **Prompt formatting is a live variable, not presentation.** A change most engineers
   would consider cosmetic — JSON versus plain text for the same content — flipped the
   objection rate from 0% to 100%. Anything measured across a prompt change is not
   comparable, and this is why both batches are kept rather than only the newer one.

2. **Enforce contracts in code, not in prose.** The objections passed the `ReviewIssue`
   contract because they were well-formed and quoted real text; they were merely *wrong*.
   That is the limit of what a schema can catch. The circuit breaker proposed in §4.5 is
   the right defence precisely because it does not require the Reviewer to be correct — it
   only requires noticing that the loop has stopped making progress.

The JSON framing was not simply the better of the two, which is why batch 2 is the primary
result: under JSON framing the Reviewer objected to the `{` and `}` characters of the
serialisation itself under rule 3 (see `raw/discarded_adversarial_prompt_bug.jsonl` and
`AI_USE.md` §5). Both framings produce spurious objections. They differ in which ones, and
under which input.

---

## Reproducing

```bash
source .venv/bin/activate

# all three experiments, 75 runs (~45 min on this hardware)
caffeinate -i python code/run_schema_experiments.py 2>&1 | tee reports/hw02/RUN_LOG.txt

python code/run_schema_experiments.py --summarize-only   # rebuild these tables from raw/
python code/agents_graph.py --force-reviewer-issue --turn-ceiling 6   # Part 3 Step 6 loop
python code/verify_hw02.py                               # smoke test -> verification.json
```

All runs in a session share one `ModelClient` and one compiled graph so Ollama keeps
qwen3:8b resident. A cold call costs ~26s against ~9s warm; running each experiment as a
separate process roughly quadruples total wall-clock time.
