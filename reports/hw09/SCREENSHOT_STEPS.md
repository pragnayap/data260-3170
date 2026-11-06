# HW9 screenshots (the only manual step left)

Every `part*.py` prints `Pragnaya Priyadarshini HW9 - <script>` as its first line — keep that line (and the prompt) in each shot.
Start: `make redis-up-hw09` (Redis Stack), MySQL and Ollama running.

| # | Part | Command | Frame |
|---|---|---|---|
| 1 | 1 | `make counter-hw09` | whole output: Access #1…#25, "✓ Synced views to database" after #10 and #20, Redis 25 / MySQL 20 |
| 2 | 1 | `docker exec s3170_redis redis-cli get s3170:views:incident:1` | shows the PREFIX key |
| 3 | 2 | `make cache-hw09` | the CACHE HIT / CACHE MISS log lines and the summary block (hit rate, cached vs not-cached latency) — scroll to two shots if needed |
| 4 | 3.2 | `make sweep-hw09` (≈ 15 min, Ollama) | final threshold table |
| 5 | 3.3 | `.venv/bin/python -c "import json;print(json.dumps(json.load(open('reports/hw09/raw/part3_sweep.json'))['example_false_hit_at_0.85'],indent=1))"` | the false hit |
| 6 | 3.5 | `make stale-hw09` | steps 1–5: stale hit, STALE eviction log line, fresh answer |
| 7 | 4.1 | `cd code/hw09 && ../../.venv/bin/python part4_run.py demo` | controlled revision sequence |
| 8 | 4.2 | `grep -B3 -A6 "lesson_001" reports/hw09/raw/part4_stage1.log` (name banner is the first line of that log) or re-run `part4_run.py train` | lesson created after the repeated failure, then "lessons loaded: ['lesson_001']" on a later question |
| 9 | 4.3/4.4 | `cat reports/hw09/METRICS.md` | validation decisions + the four-variant table |
| 10 | all | `make verify-hw09` | pass/fail summary |

Then paste into the PDF: `cache_cases.yaml`, the filled threshold table, the Part 4 results table, the reference dataset and the
three input datasets (short excerpts), `lessons.json`, the 3.3 / 3.4 / 3.5 explanations from `REPORT_NOTES.md`, and `AI_USE.md`.
Save as `reports/hw09/Priyadarshini_HW9.pdf`. Format: main headings 14 pt bold, subheadings 12 pt bold, body 11 pt.
