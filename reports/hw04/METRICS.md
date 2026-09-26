# HW4 Metrics -- Pragnaya Priyadarshini (SID4 3170)

## Section 0 - configuration

| Value | Definition | Mine |
|---|---|---|
| SID4 | last 4 of SJSU student ID | 3170 |
| PORT_BASE | 8000 + (SID4 mod 900) | 8470 |
| PREFIX | "s" + SID4 | s3170 |
| SEED | SID4 | 3170 |
| VERIFY_SEED | 260000 + SID4 | 263170 |
| DOMAIN_ID | SID4 mod 8 | 2 -- Municipal Transit Incidents |

Hardware: Intel x86_64 MacBook Pro, macOS 15.7.9. Local model: Ollama `qwen3:8b` (Part 4). Tagged commit: `hw4` (see `verification.json` for the exact hash).

## Part 3 -- N+1 measurement (180 requests: 3 page sizes x 2 versions x 30 each)

| Page size | Version | SQL stmts/req | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|---|---|
| 10 | naive | 12 | 12.98 | 13.62 | 13.79 |
| 10 | fixed | 3 | 8.16 | 8.54 | 8.68 |
| 50 | naive | 44 | 36.81 | 39.07 | 39.27 |
| 50 | fixed | 3 | 13.59 | 15.82 | 29.54 |
| 200 | naive | 126 | 103.76 | 107.03 | 119.81 |
| 200 | fixed | 3 | 31.47 | 37.49 | 52.27 |

Raw per-request data: `raw/n1_requests.csv` (180 rows). Machine-readable summary: `raw/n1_summary.json`.

**SQL statements per request.** Naive issues `page_size + 2` statements: one `COUNT(*)`, one paginated `SELECT` for the page of incidents, and one additional `SELECT` per incident to fetch its related route (the classic N+1 lazy-load). Fixed issues exactly 3 regardless of page size: the same count and page query, plus a single batched `SELECT ... WHERE related_route_id IN (...)` from `selectinload`, which loads every route referenced by the whole page in one round trip.

**Why the speed-up grows with page size.** At page_size=10, naive's per-record overhead (10 extra queries) is small next to fixed connection/query fixed costs, so the ratio is modest (1.59x). As page_size grows, naive's query count grows linearly (12 -> 44 -> 126) while fixed's stays flat at 3, so the fraction of naive's total time spent on per-record round trips keeps increasing, and the speed-up compounds (1.59x -> 2.71x -> 3.30x). Each extra query pays a fixed per-round-trip cost (network + parse + plan) on top of its actual work, and naive pays that fixed cost `page_size` times over while fixed pays it once.

## Part 3.8 -- Added index

Query under test: `SELECT * FROM incidents WHERE category = 'Delay';` (5,000-row table, 4 categories, ~1,250 matching rows).

**Before** (no index on `category`): `type=ALL`, `key=NULL`, `rows≈4901` -- a full table scan filtering every row.

**After** (`CREATE INDEX ix_incidents_category ON incidents (category)`): `type=ref`, `key=ix_incidents_category`, `rows≈1286`, `filtered=100%` -- MySQL uses the index to jump straight to the matching rows instead of scanning the table.

Full EXPLAIN output: `raw/index_explain.txt`.

## Part 4 -- Grounded RAG

Corpus: `data/rag_docs/` -- 5 invented "Baywood Transit Authority" policy documents (incident reporting, route/service standards, safety hazard procedures, mechanical maintenance, accident/collision investigation), themed to DOMAIN_ID 2, chunked at size 500 / overlap 50. Model: Ollama `qwen3:8b`, local. Full per-question prompts and raw model output: `raw/generations_full.txt` (machine-readable: `raw/generations.jsonl`). Retrieved-chunk printouts (source + score, before generation): `raw/retrieval_printouts.txt`.

### Evaluation table (18 rows = 6 questions x 3 configs A/B/C)

| qid | config | correct_retrieval | correct_answer | grounded | refused_when_needed |
|---|---|---|---|---|---|
| q1_single_chunk | A | n/a | YES | n/a | n/a |
| q1_single_chunk | B | YES | YES | YES | n/a |
| q1_single_chunk | C | YES | YES | YES | n/a |
| q2_dual_fact | A | n/a | YES | n/a | n/a |
| q2_dual_fact | B | YES | YES | YES | n/a |
| q2_dual_fact | C | YES | YES | YES | n/a |
| q3_overlap_disambiguation | A | n/a | no | n/a | n/a |
| q3_overlap_disambiguation | B | YES | YES | YES | n/a |
| q3_overlap_disambiguation | C | YES | YES | YES | n/a |
| q4_ambiguous | A | n/a | YES | n/a | n/a |
| q4_ambiguous | B | YES | YES | YES | n/a |
| q4_ambiguous | C | YES | no | YES | n/a |
| q5_not_in_corpus | A | n/a | no | n/a | n/a |
| q5_not_in_corpus | B | YES | no | YES | n/a |
| q5_not_in_corpus | C | YES | **YES** | YES | **YES** |
| q6_unrelated | A | n/a | no | n/a | n/a |
| q6_unrelated | B | YES | no | YES | n/a |
| q6_unrelated | C | YES | **YES** | YES | **YES** |

**Summary**: accuracy 12/18 answers correct overall; faithfulness 12/12 (every B/C answer that made a claim was grounded in its cited chunk); format compliance / robustness 2/2 (config C refused both must-refuse questions, Q5 and Q6, with the exact required string `"I cannot answer this question from the provided documents"` -- confirmed by exact string comparison against `raw/generations.jsonl`, not visual inspection).

Full methodology notes on how `correct_answer`/`correct_retrieval` were scored (including why A's/B's Q5/Q6 rows read `no` even though neither hallucinated a number for Q5) are in `raw/evaluation_table.md`.

### k-sweep (Q1, k = 1, 3, 5)

| k | chunks in context | answer |
|---|---|---|
| 1 | only the document's opening/routeId-scheme chunk (not the target fact) | correctly refused -- the needed fact wasn't in context |
| 3 | + the actual target chunk, + one more | correct, grounded, cited Source 2 |
| 5 | + 2 off-topic chunks (another doc's purpose statement, an unrelated holiday-schedule note) | identical answer to k=3; the extra chunks were ignored |

k=3 was best: k=1 under-retrieved and correctly declined rather than guessing; k=5 added noise the model had to filter but didn't change the outcome. More context neither helped nor hurt once k=3 already contained the needed fact.

### Analysis

Full 499-word analysis: `raw/analysis.md`. Headline finding: retrieval quality was the dominant lever -- Q2's original phrasing (around a brake-wear threshold) failed retrieval entirely because a generic, topic-adjacent "inspection intervals" chunk out-scored the actually-relevant chunk on word overlap; no prompt change could fix that, only redesigning which fact the question targeted could. Q3 (the cross-document "2 hours" overlap) showed de-duplication and source-labeling keep the right chunks in context, but "cite a source" is a weaker rule than "address every source": config C answered from one of three valid framings rather than reconciling all three. Config A hallucinated confident wrong numbers on Q3 and Q2 with no evidence in context, and both A and B answered the unrelated Q6 correctly but ungrounded -- exactly the contrast grounding rules are meant to fix, and config C's refusals on Q5/Q6 (plus an honest, unforced refusal on the ambiguous Q4, where retrieval only surfaced generic section-openers) confirm they worked.
