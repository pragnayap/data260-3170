# AI_USE — HW6

<!-- Written to match what actually happened: Claude Code did most of the implementation. Review section 1 and edit it to say exactly what you personally did. -->

## 1. What did you use an AI assistant for, and what did you do yourself?

I used Claude Code (Claude Sonnet 5.5) as the main implementation assistant for this homework. It wrote
the MongoDB document API (Part 1), the memory-aware chat endpoints and memory logic (Part 2), the
30-message sweep runner, probe scoring and cost script (Part 3), and the file-memory module, CLI,
consolidation logic and tests (Part 4), and it ran the experiments on my machine.

What I did myself: I set the direction and approved the approach, stopped two unrelated Python processes
that were competing for the CPU while the sweep was running (which is why the first N=4 run is kept
only as `*_N4_contended`), kept the Mac awake and the services (Docker, Ollama) running for the multi-hour
runs, and I am responsible for the screenshots, for reading and checking the results, and for the final
report and submission. <!-- EDIT: adjust this paragraph so it matches exactly what you personally did. -->

## 2. One AI-produced output that was wrong or unsuitable, or one thing you independently verified

The assistant's first MEMORY.md consolidator was wrong in three successive versions, and the second and
third failed in ways that looked like success until they were audited.

* **v1 (one prompt with all 55 facts):** reduced 55 → 51 lines (target < 40). It found 1 duplicate group
  (there are about 9), resolved only 1 of 5 contradictions — and resolved that one wrongly (it archived the
  development-only "Secure cookies stay off over http" rule in favour of "always Secure") — and archived
  the harmless fact "The course is DATA 260 Agentic AI" as obsolete.
* **v2 (pairwise questions):** reduced 55 → **1** line. The model labelled 47 of 55 facts "TEMPORARY"
  and 58 of 87 pairs "SCOPED", and the first version of the code applied whatever it said.
* **v3/v4:** with prompt examples the model flagged 39 of 48 lasting facts as temporary, and a 45%
  safety guard that was added refused to apply the result. When the guard was changed to report what it *would* have
  removed, the proposal still contained wrong merges ("MongoDB installed via Homebrew" chained into
  "Intel Mac, Homebrew in /usr/local" because both mention Homebrew) and would have archived the
  assigned port-8470 fact.

A separate check: the model-generated `normalize_route_id` followed the style rules of AGENT.md but
omitted the required pytest test, and after two repair rounds its function still failed its own test
(`'  line   22 '` became `'LINE 22 '`, with a trailing space).

## 3. How did you detect the problem or verify the result?

* The answer key (`memory_test/ground_truth.json`) was written **before** any consolidation was run, including
  one deliberate trap (the 8470-vs-8000 port, where "newest wins" is the wrong rule) and one pair that is
  not a real contradiction (dev vs production cookies). Grading the consolidator against it is what showed
  0/5 contradictions handled correctly on v1.
* Line counts alone would have passed v2 ("55 → 1 is under 40"), so the archive file and the
  list of proposed removals were read fact by fact. That is how the wrong merges and the bogus
  "backend port conflicts with Vite port" verdict were found.
* For the sweep, the first N=4 run showed latency climbing from ~20 s to ~100 s per turn. Checking
  `ps` showed two unrelated Python processes at ~220% CPU, so that run's latency was not used.
* The compliance check is mechanical (AST + pytest), not a judgement by the same model, so it could
  not be talked into passing.
* Limitation I am reporting rather than hiding: all four memory settings scored 5.00 on the probes, so
  the probes cannot separate them; and the thresholds in the final consolidator (SAME needs cosine ≥ 0.6)
  were chosen after the results and the answer key had been seen, so 4/5 correct is not a blind score.

## 4. What did you change, and why does it work now?

* **Verify the model's claims with something deterministic.** A "TEMPORARY" verdict only counts if the
  note also contains an explicit time/to-do cue (`today`, `right now`, `pending`, `remember to`, …); a
  "SAME" verdict only counts if the two facts are also close in embedding space (cosine ≥ 0.6, while
  same-topic-but-different facts scored 0.39–0.53). The model supplies judgement, the code supplies the
  evidence check.
* **No chaining and no flip-flopping.** Duplicate groups are stars around one representative (no
  transitive closure), and each fact receives at most one contradiction decision, so one bogus verdict
  cannot overturn a good one.
* **No silent loss.** Every removed fact is written to `MEMORY.archive.md` with a reason, a resolved
  contradiction leaves an HTML comment in `MEMORY.md`, and the old wording is archived whenever a merge
  rewrites a fact (the first version overwrote the `s3170_doc` line without keeping it).
* **A refusal guard.** A consolidation that would archive more than 45% of a file of 10+ facts is
  not applied; the proposal is recorded instead.
* Result: 55 → 35 lines, duplicates merged, C1–C4 resolved correctly, and C5 still resolved incorrectly
  (the development-only cookie rule was lost) — reported as a known error rather than tuned away.
* For the generated function, the repair message now quotes the exact AGENT.md rule and the pytest
  output. The model still did not fix the logic, so `normalize_route_id` was also implemented directly
  (`code/hw6/route_utils.py`), which passes all 9 checks; the model's three attempts are kept in
  `reports/hw06/raw/` and `reports/hw06/attempts/`.
