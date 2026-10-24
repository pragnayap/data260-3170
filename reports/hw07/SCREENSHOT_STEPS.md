# HW7 — screenshots you need to take

Rules from the handout: **your name must be visible in every terminal screenshot**. In each terminal first run
`echo "Pragnaya Priyadarshini (Lucky) - HW7"` (or show your shell prompt). Label each screenshot and paste it
under the matching red placeholder in `Priyadarshini_HW7.docx`. Do not submit duplicate screenshots.

Before you start (keep the Mac plugged in; in a spare tab run `caffeinate -dims` so it does not sleep):
```bash
cd "/Users/ritchit/Desktop/DATA 260--Agentic AI-Homework/data260-3170"
make run               # backend on 8470, leave this terminal open (MySQL and Ollama must be running)
```
Users already exist (`make seed-hw07` re-creates them): `reader / ReaderPass#2026`, `writer / WriterPass#2026`,
`moderator / ModPass#2026`.

## Part 1 — JWT and roles (Postman)
Import `reports/hw07/postman_collection.json`. Run the requests in order; tokens are saved automatically. Screenshot
each response **with the status code visible** (all 14 requests were replayed and return the expected code):

| # | Request(s) | Screenshot of |
|---|---|---|
| 1.1 | `1.1 Login` → "Login as writer" and "Login with a wrong password" | 200 with the `access_token` JWT, and 401 (one combined image is fine) |
| 1.2 | `GET /auth/me - no token` | 401 |
| 1.3 | `GET /auth/me - invalid token` (or `expired token`) | 401 — a separate screenshot |
| 1.4 | `POST ... as reader` and `POST ... as writer` | 403 and 201 |
| 1.5 | `DELETE ... as writer` and `DELETE ... as moderator` | 403 and 204 |
| 1.6 | `GET /api/incidents as reader` | 200 with the list |

### 1.7 Linting (terminal) — do this BEFORE you tag hw7
```bash
echo "Pragnaya Priyadarshini (Lucky) - HW7 lint demo"
# 1. add two mistakes to the top of code/web_application/jwt_auth.py: an unused "import sys",
#    and put "import os" above "import datetime as dt" (unsorted)
git add code/web_application/jwt_auth.py
git commit -m "HW7 lint demo"          # pre-commit runs Ruff and FAILS (I001, F401) — screenshot this
.venv/bin/ruff check --fix code/web_application/jwt_auth.py     # shows the issues fixed
git add code/web_application/jwt_auth.py
git commit -m "HW7 lint demo: fixed"   # hook passes, commit succeeds
```
The net change to the file is zero. One screenshot (or two stacked) showing: the error, the hook, the fix, the commit.

## Part 2 — agent loop (terminal)
```bash
make demo-hw07        # ~5 min: tasks A, B, C and the nonexistent-ID case, with the tool log
```
| # | Screenshot |
|---|---|
| 2.1 | Task A: the two tool calls, the answer and `[check] PASS` |
| 2.2 | Task B |
| 2.3 | Task C |
| 2.4 | The nonexistent-ID case: the tool says "no incident found with code INC-3170-99999" and the agent still answers |

## Part 3 — Reflexion (optional screenshot)
```bash
.venv/bin/python -c "import json;print(json.dumps(json.loads(open('reports/hw07/raw/v1_initial/reflections.jsonl').readline()),indent=1)[:2500])"
```
3.1 — the stored reflection with its evidence (tool calls, observation, verifier result). The full re-run takes ~40 min
(`make reflexion-hw07`); you do not need it.

## Part 4 — the UI (browser)
Open http://localhost:8470/hw7, sign in as `writer`, choose the CSV, leave the default pricing URL, press **Run**.
Wait until the results panel fills (the first run is slow while the model loads). Screenshot the **whole page** once
finished: the tool-call timeline, cost comparison, decision, citations and the metrics strip.

| # | CSV | Takes about |
|---|---|---|
| 4.1 | `reports/hw07/raw/bike_data/heavy_rider.csv` → Buy Monthly Membership | 10 min |
| 4.2 | `reports/hw07/raw/bike_data/light_rider.csv` → Pay Per Ride/Minute | 6 min |

A fresh run can word things differently from the saved run in the report and the model is not fully deterministic. If
the numbers in the panel differ, quote the panel's numbers, not the report's, or paste your saved run's screenshot.

## Part 5 (optional)
```bash
.venv/bin/python code/hw07/bike/part5_attacks.py replay     # instant: injected SQL, guard off vs on
```
5.1 — the terminal output. The attack runs themselves take 1+ hour each round; the results are already in the report
and in `raw/prompt_injection_results*.json`.

## Part 6 (terminal, instant)
```bash
make test-hw07
```
6.1 — one screenshot containing the glob → search → read result (finds `b.py` with DEBUG) and the safety-gate rows.

## Self-check (optional)
```bash
make verify-hw07      # ~4 min, needs the backend and Ollama running
```
7.1 — the output ending `22 passed, 0 failed`.

## Final assembly
1. Fill the red placeholders: the tagged commit hash (`git rev-parse --short hw7`) and your AI_USE.md answers.
2. Replace each red `[ Screenshot ... ]` line with its image (delete the brackets text or keep it as the caption).
3. Check headings 14 pt bold, subheadings 12 pt bold, body 11 pt (already set), and that your name shows in every
   terminal screenshot.
4. Export as `Priyadarshini_HW7.pdf` into `reports/hw07/`.
5. `git tag hw7 && git push --tags`; confirm the GitHub link works and both collaborators have access.
