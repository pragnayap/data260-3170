# HW9 — report notes (draft text for the PDF; numbers come from `METRICS.md` / `raw/`)

Heading sizes for the PDF: main headings 14 pt bold, subheadings 12 pt bold, body 11 pt. Put the name
"Pragnaya Priyadarshini" in every terminal screenshot (every `part*.py` prints it as its first line).

## Setup
Redis Stack 7.4 (Docker `s3170_redis`, port 6379), every key starts with `s3170:`. Embeddings: `all-MiniLM-L6-v2`
(384-d, normalised), HNSW index, COSINE. Local model: `qwen3:8b` via the HW8 `llm.py` adapter.

## Part 1 — Redis view counter
`IncidentCache.increment_incident_views(incident_id)` in `code/web_application/cache_db.py` does `INCR s3170:views:incident:<id>`;
when `count % 10 == 0` it writes the count to `incidents.view_count` (new column, `make migrate-hw09`) and returns the count.
The write is a raw `UPDATE` so `updated_at` is not touched (a view is not a content change). `GET /api/incidents/{id}` also calls it
and returns the count in an `X-View-Count` header. Screenshot: `make counter-hw09` (25 accesses, syncs after #10 and #20;
Redis 25, MySQL 20 at the end — the DB lags by up to 9 views by design).

## Part 2 — semantic cache (threshold 0.85, 14 queries)
Hit rate 57.1 % (8/14). Average latency cached 538 ms vs not cached 30 959 ms. These are what was measured, not a target.
- Hit latency is almost all *embedding the query* (CPU MiniLM); the Redis KNN search is ~2 ms. Several hits took 0.7–1.2 s
  because the embedding ran while Ollama was still using the cores; hits not near an agent run took 30–160 ms.
- Query 11 ("name of route R-0052") was not a planned duplicate or paraphrase, yet it hit "What type of route is R-0045?"
  at 0.8836 and returned a wrong answer; query 12 (R-0053) hit the same entry. That is the Part 3 problem showing up early.
- Query 8 (a true paraphrase) scored 0.8480 and *missed* at 0.85.

## Part 3.1 — labeled set
`code/hw09/cache_cases.yaml`: 10 exact duplicates, 10 paraphrases, 10 superficially similar (different route / different
category, answer differs — checked against MySQL before the sweep), 10 unrelated. Committed (5eafe4c) before the sweep and not
edited afterwards. No labeling mistakes found so far; if one is found it goes in `LABEL_NOTES.md`, not in the file.

## Part 3.2 — threshold sweep
See the table in `METRICS.md`. Definitions: hit rate = hits / 40; false-hit rate = hits on the 20 should-miss cases / 20;
missed hits = should-hit cases that missed. Hit latency is measured (embed + search); miss latency = measured lookup + the
**mean of the 20 measured agent runs (36.3 s)** — the sweep did not re-run the agent for every miss.

## Part 3.3 — one false hit
Cached: "How many incidents are recorded for route R-0071?" → "…is 21…". Incoming: "…for route R-0072?" (similarity 0.9876).
Returned the cached 21; correct answer is 28. Why: MiniLM turns the question into one vector that mostly encodes *what is being
asked* (a count of incidents on a route). "R-0071" and "R-0072" differ by one word-piece out of ~14 and identifiers carry
almost no semantic weight, so the two sentences are near-identical to the model. Similarity does not mean "same answer".

## Part 3.4 — cost model and choice
- Cache-miss cost = **$0.02**: one agent path = planner call + writer call (+ one retry sometimes), roughly 2k tokens in and 300 out;
  at hosted mid-tier pricing that is 1–2 cents. (Locally it costs ~36 s of CPU instead.) It is paid for every miss.
- False-hit cost = **$5.00**: a rider or dispatcher gets a confident wrong fact and someone has to catch and fix it —
  about 10 minutes of support time at $30/h. 250× a miss.
- Total cost = misses × $0.02 + false hits × $5. Break-even: removing one false hit is worth it if it adds fewer than 250 extra misses.
- Sensitivity ($1 / $5 / $25 per false hit) is in `METRICS.md`: **0.95 is the cheapest threshold in all three.**
- **Ship 0.95.** Honest caveats: it is only the cheapest of the five, not good — 7 of 20 should-miss cases still hit (all near-misses
  that differ in one route number or one category) and only 2 of 10 paraphrases hit. No threshold fixes this because the
  confusable pairs (0.93–0.99) overlap the paraphrases (0.84–0.98). The supplement table in `METRICS.md` (computed offline from the same rows)
  shows that requiring the same route code in both queries cuts false hits to 0–1 at every threshold; that guard is the next change,
  but it is not part of the 5-row table.

## Part 3.5 — stale answer and invalidation
Cached question "What agency operates route R-0099?" depends on `routes` row R-0099 (Caltrain). `UPDATE … agency = 'Golden Gate Transit'`
→ cache with no invalidation still answers "Caltrain" (stale hit, similarity 1.0). Strategy: each entry stores a **data-version marker**
(hash of `updated_at` of the route row + incident count + latest incident `updated_at`); on every hit the handler recomputes the
marker and, if it differs, evicts the entry and runs the agent. Result: fresh answer "Golden Gate Transit", next ask is a valid hit.
The row was restored afterwards. **Trade-off:** correct on every hit, but every hit now costs a DB read (3.1 ms measured here, small
next to the 30 s agent run, but it puts MySQL back on the hit path and does not scale to answers that depend on many rows); it only
sees rows named in the question (an answer that silently depends on another table would still go stale); and it evicts on *any* update to
those rows, even one that does not change the answer. Alternatives: a TTL (cheap, but stale until it expires) or event-driven delete on write
(no read cost, but every writer must remember to do it).

## Part 4 — self-improving two-agent system
Files: `code/hw09/agents_si.py` (Answering Agent, Evaluator Agent, lesson store, 2-attempt loop), `code/hw09/part4_run.py` (stages),
`data/hw09/part4/` (`reference_dataset.json`, `training_data.json` ×12, `validation_data.json` ×10, `test_data.json` ×14, `lessons.json`).
Input files hold only `{id, question}`. Reference = 30 routes (R-0101…R-0130) from `s3170_rel` plus a seeded fare history (synthetic, `Random(3170)`).

**Agent communication.** The Answering Agent (qwen3:8b through the HW8 adapter) sees only the route record its lookup returns, never the
reference dataset. The Evaluator Agent (deterministic, rule-based) checks the answer against `reference_dataset.json` and returns
`{result: PASS|REVISE, explanation, feedback, failure_type}`. On REVISE the feedback goes back to the Answering Agent with its previous answer.
**Stopping condition:** PASS, or the second attempt — never a third.

**4.1 controlled case** (`raw/part4_controlled_demo.json`): attempt 1 forced to "Route R-0110 is a Commuter Rail route." → REVISE ("missing: agency") →
attempt 2 "The agency that operates route R-0110 is AC Transit, and it is a Commuter Rail route." → PASS, 2 attempts.

**4.2 lessons.** Training stream (12 questions, repair on): the "answers an out-of-scope question from general knowledge" pattern
(`unsupported_answer`) appeared twice (tra_03, tra_07) → `lesson_001` was created, then loaded and applied at tra_11 (use_count 1; the answer
was a correct refusal on attempt 1). The stale-fare failure (tra_01) happened only once, so no lesson was created for it.

**4.3 validation** (10 questions, repair on, first-attempt and final correctness tracked):
- lesson_001 → **kept**: fixed 2 first-attempt failures (val_03, val_07), 0 regressions, no unsupported answers on out-of-scope questions.
- lesson_002 (hand-written over-broad rule "only answer if a route code is present", trigger = always) → **rejected**: it fixed nothing and the gate
  needs an improvement. It did *not* regress (the model mostly ignored it, including on the by-name question val_08). I wrote this candidate to exercise
  the gate; it did not produce the regression I expected, and I am reporting that rather than claiming it did.

**4.4 results** (test_data.json, 14 questions, evaluator frozen; run 2 on an otherwise idle machine; run 1 is in `raw/part4_variants_run1.json`):

| Variant | Correct | Incorrect | Avg attempts | Avg latency (s) |
|---|---|---|---|---|
| Baseline | 10 | 4 | 1.00 | 4.6 |
| Evaluator Repair | 14 | 0 | 1.29 | 5.5 |
| Lesson Memory | 14 | 0 | 1.14 | 5.7 |
| Validated Improvement | 14 | 0 | 1.14 | 5.7 |

Run 1 gave the same correct/incorrect/attempt numbers and latencies of 15.3 / 7.6 / 11.4 / 5.9 s — the machine was busy and the Baseline ran first, so
run-1 latencies are not comparable across variants. Do not read latency differences in either run as an effect of the variants.

**What the numbers do and do not show.** Repair lifts 10 → 14 because every baseline failure (3 out-of-scope questions answered from general knowledge,
1 outdated fare) is repairable from one round of feedback. Lessons do not add accuracy here (already 14/14); they cut attempts from 1.29 to 1.14 by
preventing 3 of the 4 first-attempt failures (the 3 out-of-scope questions). Lesson Memory and Validated Improvement tie because the only extra lesson
Lesson Memory loads (lesson_002) was harmless on this test set. Four failing questions is a small sample.

**Reuse example** (`raw/part4_training_run.json`, tra_11): "Recommend a good restaurant near Union Square…" → `lessons loaded: ['lesson_001']` →
"I do not have that information in the transit database." (PASS, 1 attempt). On the test set, `tes_12` (route R-9999) loads lesson_001 as well.

**Limitations (one required, three found).**
1. *Evaluator refusal check is a phrase list.* After the test run I saw it misjudge `tes_12`: the Baseline's "There are no recorded incidents for route R-9999"
   PASSed (it contains "no record"), while the lesson variants' correct refusal "The transit database does not have information…" got REVISE because
   "does not have" is not in the list. I did not fix it, because the rules say not to modify the system after seeing the test set; it affects the Baseline
   score (it should be 9/14) and the attempts of the lesson variants (their average would be 1.07, not 1.14). A stricter evaluator would check that a refusal contains
   no claim, using an LLM judge.
2. The evaluator, the lesson triggers and the question-field keywords are hand-written rules matched to this question style; new phrasings would slip past them.
3. Small data: 12 / 10 / 14 questions, one model, temperature 0, one run each (run 2 repeated run 1's correctness exactly, which is what temperature 0 predicts).
