# AI_USE — HW2

> **Pragnaya: read this before submitting.** It is written to match what actually
> happened in the session. If any sentence overstates or understates your own
> involvement, correct it — an inaccurate disclosure is worse than a large one.

## 1. What I used an AI assistant for, and what I did myself

I used Claude Code (Claude Fable 5 / Opus 5, via the terminal) as a pair programmer for
this homework. The division of labour was:

**Written by the assistant, at my direction:**

- `src/schemas.py` — the Pydantic `PlannerOutput` validator (Part 4.1) and the
  `ReviewIssue` contract used to filter Reviewer objections.
- `code/agents_graph.py` — the LangGraph refactor (Part 3): `AgentState`, the Planner,
  Reviewer and Supervisor nodes, `router_logic`, and graph assembly.
- `code/run_schema_experiments.py` — the Part 4.3–4.5 experiment harness.
- `code/verify_hw02.py` — the smoke-test script that writes `verification.json`.
- `code/web_application/app.py` — the FastAPI backend (Part 2).
- The HW2 additions to `HW1-PragnayaPriyadarshini.html` and `hw1.js` (Part 1: responsive
  layout, loading/empty/error states, list rendering, search, update and delete).

**Done by me:**

- Set the scope and the order of work, and chose which parts to hand over.
- Chose the domain input for the frozen case and reviewed the adversarial case.
- Reviewed the generated code, ran the experiments, and interpreted the results.
- Wrote the analysis in `METRICS.md` and the report.

I had originally agreed a split where I wrote Parts 1–3 myself from scaffolds the
assistant produced, and it wrote only the Part 4 harness. I changed my mind partway
through and asked it to write the remaining parts as well. The scaffolds it produced
first (with the state shape and numbered TODO steps) are what the final node
implementations are built on.

## 2. An AI-produced output that was wrong or unsuitable

The first version of the Reviewer's prompt, written by the assistant, contained a rule
that contradicted the Planner's instructions:

> 1. A tag names something that does not appear in the input at all.

The Planner is told to produce *topical* tags — labels that generalise the input. Rule 1,
read literally, rejects exactly that. The model applied it literally and rejected its own
correct output every single pass, so the self-correction loop could never terminate. Every
run burned its full turn ceiling.

A second defect was in the experiment harness: `classify()` bucketed runs using
`planner_attempts`, the count of *all* Planner calls. Because the Reviewer could also send
a proposal back, runs whose schema validation passed on the first try were being reported
as retries.

## 3. How I detected it

Not from the summary table — the summary looked plausible. I caught both by running a
3-run smoke test before committing to the full batch and reading the per-run records in
`raw/runs.jsonl`:

- Every run was classified `hit_turn_ceiling`, yet `validation_history` was **empty** in
  each one. An empty validation history means Pydantic never rejected anything, so
  "abandoned at the ceiling" was impossible on the schema's account. That contradiction
  is what exposed the classification bug.
- Printing `issue_history` showed the Reviewer objecting to `'Service Failure'` and
  `'Transit Center'` with the reason "names something that does not appear in the input" —
  even though the input says "Downtown Transit Center". Seeing the objection text, rather
  than just the issue count, is what identified the contradictory rule.

I also probed the Reviewer directly on a known-good proposal, outside the graph, and got
two different verdicts on identical input (`[]`, then `["Service Communication"]`) — the
second being a bare tag name with no stated fault, which the prompt explicitly forbade.

## 4. What I changed, and why it works now

1. **Rewrote rule 1** to be about subject matter rather than literal wording ("a tag about
   fare payment when the input describes a delay"), and stated explicitly that a tag never
   has to appear word for word, with `Service Failure` and `Transit Center` given as
   examples of acceptable tags. This stopped the loop running to the ceiling on ordinary
   input: runs now terminate on their own rather than being cut off. It did not make the
   Reviewer reliable, as §6 explains — it still raises the same objection the rewritten
   rule tells it not to, just no longer often enough to prevent convergence.

2. **Enforced the Reviewer's output contract in code** rather than trusting the prompt.
   `ReviewIssue` requires each objection to carry a rule number, a verbatim quote, and a
   stated problem; `parse_review_issues()` additionally drops any objection whose quote
   does not actually occur in the proposal. A bare tag name, or an invented quote, is
   discarded before it can reach the Planner. This is the same principle as Part 4.1 —
   validate the model's output against a schema instead of assuming it followed
   instructions.

3. **Split the retry counters.** `AgentState` now tracks `schema_retries` (Pydantic
   rejections only) separately from `planner_attempts` (every Planner call), and the Part
   4.3 table is built from `schema_retries`. The buckets now measure what the assignment
   asks about — how often the schema was satisfied — rather than how picky the Reviewer
   happened to be.

One further thing I verified independently: the assistant's first draft of the experiment
harness used a turn ceiling of 4 for the Part 4.3 runs. A full correction round costs four
worker turns (Planner, Reviewer, Planner, Reviewer), so a ceiling of 4 cuts off the
confirming review and records a perfectly good run as abandoned. The ceiling for those
runs is now 8.

## 5. A second defect, caught mid-experiment — and the discarded runs

`reports/hw02/raw/discarded_adversarial_prompt_bug.jsonl` holds two adversarial runs that
are **excluded** from every table in `METRICS.md`. They are kept rather than deleted so
the record of what happened is complete.

While the batch was running I read the per-run objections and found the Reviewer
reporting `'{'` and `'}'` under rule 3, "the proposal contains JSON syntax as text". The
braces were not the Planner's: `reviewer_node` was serialising the proposal with
`json.dumps()` before showing it to the Reviewer, so every proposal arrived as JSON text
and rule 3 fired on all of them. The quote-check did not catch it either, because `{`
genuinely occurred in the string being checked.

Two changes fixed it. The Reviewer now receives the proposal as plain text
(`Tags: …\nSummary: …`), and `parse_review_issues()` checks quotes against the tag and
summary **values** only, so an objection can only cite text the Planner actually wrote.

Before re-running anything I checked how far the contamination reached: across the 70 runs
behind Parts 4.3 and 4.4, the Reviewer had raised **zero** issues of any kind. Since the
filter can only ever remove issues, those results could not have been affected, so only
the five adversarial runs needed repeating at that point. I did re-run all 75 later, once
the code was final, so that every reported number came from a single code version — see
§6, which is where that re-run turned up something I had not expected.

A third defect surfaced from the same inspection: the adversarial summary counted ceiling
hits from the outcome bucket, which reports *schema* validity. A run can exhaust its turn
ceiling while holding a schema-valid proposal the Reviewer never cleared — which is
precisely what all five adversarial runs do. Counted from the bucket, the ceiling-hit rate
would have been reported as 0% for a case that reaches the ceiling every time. It is now
read from the `hit_ceiling` field.


## 6. The finding that came out of re-running everything

After the code was final I re-ran all 75 experiments so that every run came from one code
version, rather than 70 from before the Reviewer fix and 5 from after. I expected a
confirmation run. What it produced was the most interesting result in the assignment.

Every structural result reproduced exactly — completion rates 0/20 and 20/20, adversarial
ceiling hits 5/5, schema validity 30/30. But mean latency on the frozen input went from
10,862 ms to 62,260 ms, because the Reviewer went from raising **0** objections across 30
runs to raising **60**.

The only difference in the Reviewer's input was formatting: JSON versus plain text for the
same proposal. On inspection the 60 objections were all wrong, and all the same two — the
Reviewer rejecting `'Transit Center'` and `'Bus Delay'` as subjects the input never
raises, on an input that says "Downtown Transit Center" and describes a bus that never
arrived. Its own prompt names those exact tags as acceptable.

I kept both batches rather than discarding the older one, because the comparison is the
evidence. It is written up as §4.6 of `METRICS.md`. The practical lesson I took from it:
prompt formatting is a live variable rather than presentation, and a schema contract can
only catch malformed objections, not wrong ones — which is why the fix I propose for the
loop does not depend on the Reviewer being correct.
