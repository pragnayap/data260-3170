# HW10 — report notes (draft text for the PDF; every number comes from `METRICS.md` / `raw/`)

Heading sizes for the PDF: main headings 14 pt bold, subheadings 12 pt bold, body 11 pt. **Page limit 35.**
The student name "Pragnaya Priyadarshini" is printed by every runnable script and sits in the dashboard sidebar.

## Setup
Kafka `apache/kafka:3.8.0` (KRaft, Docker `s3170_kafka`), Redis Stack 7.4 (`s3170_redis`), Ollama `qwen3:8b` (CPU). Agents: the HW8 Planner,
Writer, Reviewer (separate processes, `code/hw10/agents.sh`). Cache: the HW9 semantic cache at threshold **0.95** (the value HW9 shipped),
namespace `s3170:hw10`. Judge: DeepEval `GEval` on `qwen3:8b`, temperature 0, seed 3170, thinking off, 400-token cap, fixed evaluation steps,
1–5 rubric. Dashboard: Streamlit 1.40.2 on port 8472.

## Part 4.1 — tracing (built first because everything else reads it)
`code/hw08/tracing.py` writes one JSON span per stage to `data/hw10/spans/spans.jsonl`: `trace_id, stage, start, end, start_ms, end_ms, duration_ms,
status, error` (+ stage attributes). **trace_id is the HW8 correlation_id** — no second identifier exists anywhere. Stages:
`cache_lookup` (ingress), `inbox` (queue wait), `planner`, `tasks` (queue), `writer`, `drafts` (queue), `reviewer`, `final` (queue back to the caller),
`evaluator`. Queue spans run from the producer's `sent_at_ms` stamp (added to every message) to the moment the next stage picked it up.
`code/hw10/ingress.py` does the cache lookup first, goes to Kafka only on a miss, and stores the answer afterwards. Tracing is off unless `HW10_TRACE=1`
so HW8 behaves as before. A hit trace has a single `cache_lookup` span (`is_cached: true`); a miss trace has all eight stages.

## Part 4.2 — the three traces (ids in `METRICS.md`)
- **Cache hit:** an exact repeat of an answered question; one span, ~0.1 s, Kafka untouched.
- **Cache miss:** the median-latency request of the 50 (all 8 stages ok).
- **Failed:** a request sent with `fault="empty_plan"` (a test hook in the Planner, like HW8's `simulate_slow_ms`): the Planner emits an empty plan, the
  **Writer** raises `ValueError: task has no plan`, retries 3 times and dead-letters it, and the caller records a `final` error span after its 45 s wait.
  Failing stage: **writer**. This one is an injected fault. A *spontaneous* failure also happened during development (below).

## Part 4.3 — stage latency, 50 confirmed misses
The run first warms the embedding model, resets the cache namespace, then sends distinct questions; a request whose lookup is a hit is not counted
(0 were skipped). Table, definitions and the hit latency are in `METRICS.md`. Headlines: **Writer 59.4 %** and **Planner 37.6 %** of end-to-end; cache lookup 3.0 %;
Reviewer and queue wait ≈ 0 %. **Optimise the Writer first** (it is the longest model call: ~3 sentences, 220-token cap), then the Planner; a smaller or quantised model,
a lower `num_predict`, or merging plan+draft into one call would cut the most. Caveats to state:
- Requests were sent **one at a time**, so queue wait is ~16 ms (four Kafka hops). Under concurrent load it would grow; this run cannot say how much.
- `Evaluation` runs after the answer is returned and is not part of user-facing latency. Its 317 % is relative to the same end-to-end figure
  (p50 77.7 s vs 33.9 s; n = 50) because three judge calls take about twice as long as one pipeline run on this CPU. Its p95 (509 s) is dominated by a few model stalls
  (max 542 s), not typical behaviour; report p50 and p95 together.
- With n = 50, p95 (49.8 s) does not capture the two slowest requests (108.9 s and 143.5 s); in both the **model** stalled (Planner 39.6 s / Writer 103 s).
  Max is reported next to p95; they were not dropped.
- Cache-hit latency (p50 112 ms, p95 218 ms) is a separate metric over 20 warmed-up repeats; hit latency is almost all MiniLM embedding time.

## Part 2 — evaluator
`messages.collect()` reads `s3170_tasks`, `s3170_drafts`, `s3170_final` from the start with a throw-away consumer group and joins by correlation_id, keeping the
original bodies and Kafka topic/partition/offset/timestamp; it is time-bounded. `evaluate_pipeline.py` scores **Plan Quality** (plan), **Writer Helpfulness**
(draft; trace_id saved), **Final Answer Helpfulness** (final; answer saved) on 1–5 and computes **Final-vs-Draft Improvement** with an interpretation. A missing
message or an unavailable judge is recorded as an error for that trace and the run continues (judge calls have a 150 s client timeout, 2 tries).
It was run on **all 50 requests** (three judge calls, ~78 s per request at the median on this CPU). A model timeout left some requests unscored on the first pass; they were re-scored, and the 30 requests evaluated last were run a second time with tracing on so every evaluator span is real (the untraced first pass is kept as `raw/eval_results_untraced_backup.json`).
Results (`METRICS.md`): Plan 3.86, Writer 4.28, Final 4.30 (means). **The final answer is word-for-word the draft in 50 of 50 requests**, because the HW8 Reviewer is
rule-based and never edits text; so the Reviewer cannot improve answers and none should be claimed. The judge nevertheless scored identical text differently
in 7 of 50 cases (+1 four times, −1 three times; mean difference +0.02) — noise on identical input, even at temperature 0 with a fixed seed. The Planner's plans score lowest: they are short generic three-step lists.
Coordination reading: quality is set by the Writer; the Planner adds structure but little specificity; the Reviewer is a gate (length / placeholder checks), not an editor.

## Part 3 — judge validation (DONE; numbers in `METRICS.md`, raw in `raw/judge_runs.json`)
`eval_cases.json`: 20 real Writer drafts produced through the Kafka pipeline (cache bypassed): 14 general advice, 3 needing database facts the Writer cannot see,
2 off-topic, 1 vague. `human_labels.csv`: hand-assigned by the student, committed (commit e436acc) before any judge score; `validate_judge.py` refused to run otherwise.
The Writer-Helpfulness judge ran 3 times with identical inputs and settings (temperature 0, seed 3170).
- **Spearman (run 1 vs human): 0.198** (n = 20) — weak positive; with n = 20 this is not distinguishable from no correlation.
- **Mean absolute difference: 0.50** points; signed bias (judge − human) **−0.20** (the judge is slightly harsher).
- Exact agreement in 11/20 cases; the judge scored lower in 6 (E01, E08, E10, E13, E14, E17; E17 by 2 points), higher in 3 (E02, E06, E15).
- **Within 1 point of the human in 19/20 cases** (only E17 differs by 2: judge 3, human 5). In absolute terms the judge is close; the low Spearman partly reflects ties and a narrow label range (rank correlation is fragile when almost every label is 4 or 5), so it understates how near the scores are.
- **Human labels cluster at the top**: 15 fives, 5 fours, nothing below 4. Little spread means Spearman has little to rank, so it is low partly for that reason, not only because the judge is poor.
- **Repeatability: 0 of 20 cases changed across 3 runs** (mean and max absolute change 0). That is stable, but stable is not the same as valid: it is consistently
  off from the human on 9 cases. (Part 2's judge still scored identical text differently in 3/20 — those were different prompts, final vs draft, run at different times.)

**Would I trust it to gate a deployment? No, not yet.** It is repeatable but agrees only weakly with the human ranking, disagrees by half a point on average, and was validated
on 20 cases whose human scores barely vary. A gate needs to tell a bad answer from a good one, and these cases contain no bad answers (no human label below 4), so this
test cannot show that the judge catches failures. The judge is also the same model (qwen3:8b) that wrote the answers.
Extra evidence needed: more labelled cases (50-100) including deliberately poor answers so the 1-3 range is populated; a second human labeller and their agreement with the first;
a different, stronger judge model; confidence intervals on Spearman; and a check that the judge's pass/fail decision at the chosen threshold matches the human's.

## Incidents found while building (state them; they are findings)
1. **Stale agent processes stole messages.** `agents.sh stop` killed the launcher but not its Python child, so a stub-mode set from a plumbing test and an earlier real set
   stayed alive in the same consumer groups. Six of the first 20 drafts were stub output (`[stub draft] …`) and the first latency run showed 0.1 s "requests". Caught by
   checking drafts for stub text **before any label or judge existed**; the six cases were regenerated, `stop` now kills the tree and `start` refuses to run over stale agents.
2. **A model timeout killed the Planner** (Ollama `ReadTimeout` after Docker restarted and the model reloaded). Three requests then waited 900 s each. The Planner now retries
   once, then publishes a `failed` result for that request and keeps running.
3. **Installing Streamlit broke the FastAPI backend** (`starlette` 1.10 vs the repo's `<0.36` pin) and a newer `pyarrow` needed NumPy 2. Caught by `pip check` and `import app`;
   pinned `streamlit==1.40.2`, `pyarrow<20`, `protobuf<6` in requirements.txt.
4. The first cache-hit example was the very first repeat, which included the embedding model's cold start (217 s); the run was discarded and repeated warmed up.

## Limitations
- The judge and the agents are the same model (qwen3:8b): the judge is not independent of what it grades.
- One model, temperature 0, one run per request for Part 2; 20 cases for Part 3; 50 requests, sequential, for Part 4.3.
- The dashboard's hit rate reflects the experiment mix (50 misses, 20 deliberate repeats, 1 injected failure), not production traffic.
- Evaluation latency has heavy outliers (p95 509 s) from model stalls on a shared CPU.
