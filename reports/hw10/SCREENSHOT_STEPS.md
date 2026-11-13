# HW10 screenshots

Every runnable script prints `Pragnaya Priyadarshini HW10 - <script>` first; the dashboard shows your name in the sidebar. Keep it in each shot.
Run everything from the repo root:  `cd "/Users/ritchit/Desktop/DATA 260--Agentic AI-Homework/data260-3170"`
Start services first:  `docker start s3170_redis s3170_kafka`  (Docker restarts stop them)  and make sure Ollama is running.

| # | Part | What to run / open | Frame |
|---|---|---|---|
| 1 | Setup | `docker ps` and `code/hw10/agents.sh status` (start agents first with `make agents-hw10`; stop them again after the shots: `make agents-stop-hw10`) | Kafka + Redis containers up, 3 agent processes alive |
| 2 | 4.1 | `grep -m3 cache_lookup data/hw10/spans/spans.jsonl` and, for one miss trace, `grep <miss trace id> data/hw10/spans/spans.jsonl` | the structured JSON spans (trace_id, stage, start, end, status, error) |
| 3 | 1.1 | `make dashboard-hw10`, open http://localhost:8472 -> **Summary** | requests, hit rate (hits vs misses), error rate, latency, each with window + source; the stage table |
| 4 | 1.2 | dashboard -> **Evaluation** (top: Part 2 scores by stage and case) | scores by stage, by case, final-vs-draft, the coordination interpretation |
| 5 | 1.2 | dashboard -> **Evaluation** (bottom: Part 3) — only after `make judge-hw10` has run | Spearman, mean abs difference, repeatability, raw per-case table |
| 6 | 1.3 / 4.2 | dashboard -> **Trace lookup** -> "cache hit example" | the HIT badge, one cache_lookup span |
| 7 | 1.3 / 4.2 | dashboard -> **Trace lookup** -> "cache miss example" | the MISS badge, stages in order, durations, Gantt chart |
| 8 | 1.3 / 4.2 | dashboard -> **Trace lookup** -> "failed example" | the red FAILED TRACE banner (failing stage writer, error) |
| 9 | 4.3 | `make latency-report-hw10` | the p50 / p95 / % table |
| 10 | 2 | `sed -n 1,25p reports/hw10/raw/eval_run.log` (copied from data/hw10/logs/evaluate_pipeline.log) | per-request plan / draft / final scores |
| 11 | 3.2-3.3 | `make judge-hw10` (after you labelled and committed) | the three runs and the statistics |
| 12 | all | `make verify-hw10` | pass / fail summary (re-run after committing so `working_tree_clean` is true) |

Then paste into the PDF: the stage table, the three trace ids, `eval_cases.json` / `human_labels.csv` excerpts, the judge settings, the 3.x explanations
from `REPORT_NOTES.md`, and `AI_USE.md`. Save as `reports/hw10/Priyadarshini_HW10.pdf` (max **35 pages**; headings 14/12 pt bold, body 11 pt).
