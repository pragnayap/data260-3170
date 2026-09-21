# HW3 Part 2 - METRICS

Municipal Transit Incidents corpus (DOMAIN_ID 2). Retrieval only - no LLM,
no generation. Every number below is recomputed from
`reports/hw03/raw/retrieval_rows.jsonl` by `code/summarize_rag_metrics.py`;
nothing here is transcribed by hand.

- **Embedding model:** `sentence-transformers/all-MiniLM-L6-v2`
- **top_k:** 5
- **Questions scored:** 5 (from `questions.yaml`, committed before this run)
- **SEED / VERIFY_SEED:** 3170 / 263170
- **Generated:** 2026-09-21T10:57:00-0700

## 1. Retrieval quality

| Technique | Chunks | Avg chunk length | Top-1 cosine | Mean@5 cosine | Recall@5 | Mean retrieval latency (ms) |
|---|---|---|---|---|---|---|
| Token | 544 | 1,980 chars (~361 tok) | 0.7532 | 0.7193 | 1.00 (5/5) | 93.32 |
| Semantic | 442 | 2,146 chars (~391 tok) | 0.7476 | 0.7158 | 1.00 (5/5) | 92.21 |
| Sentence window | 6,008 | 158 chars (~28 tok) | 0.7809 | 0.7615 | 1.00 (5/5) | 235.14 |

### Chunking cost and spread

| Technique | Min chunk | Max chunk | Chunking time (s) | Embedding time (s) |
|---|---|---|---|---|
| Token | 197 | 3,506 | 1.88 | 29.66 |
| Semantic | 3 | 51,993 | 699.84 | 22.87 |
| Sentence window | 2 | 3,508 | 2.03 | 510.16 |

## 2. Per-question top-1 cosine and document hit

`hit` means the expected source file appeared somewhere in the top-5. `rank-1 from` is the file the single best-scoring chunk came from.

| Question | Token top-1 | Semantic top-1 | Sentence window top-1 | Token hit | Semantic hit | Sentence window hit |
|---|---|---|---|---|---|---|
| `q1_sacramento_probable_cause` | 0.8350 | 0.8517 | 0.8287 | yes | yes | yes |
| `q2_wmata_derailment_cause` | 0.7183 | 0.7099 | 0.7604 | yes | yes | yes |
| `q3_two_hour_notification` | 0.7005 | 0.6814 | 0.6914 | yes | yes | yes |
| `q4_assault_directive_deadline` | 0.8057 | 0.7780 | 0.8442 | yes | yes | yes |
| `q5_section_5307_safety_set_aside` | 0.7063 | 0.7172 | 0.7797 | yes | yes | yes |

### Where the single best-scoring chunk actually came from

| Question | Technique | Rank-1 cosine | Rank-1 source file | Expected file | Rank-1 correct? |
|---|---|---|---|---|---|
| `q1_sacramento_probable_cause` | Token | 0.8350 | `ntsb_rir2207_sacramento_light_rail_collision.pdf` | `ntsb_rir2207_sacramento_light_rail_collision.pdf` | yes |
| `q1_sacramento_probable_cause` | Semantic | 0.8517 | `ntsb_rir2207_sacramento_light_rail_collision.pdf` | `ntsb_rir2207_sacramento_light_rail_collision.pdf` | yes |
| `q1_sacramento_probable_cause` | Sentence window | 0.8287 | `ntsb_rir2207_sacramento_light_rail_collision.pdf` | `ntsb_rir2207_sacramento_light_rail_collision.pdf` | yes |
| `q2_wmata_derailment_cause` | Token | 0.7183 | `ntsb_rir2315_wmata_rosslyn_derailment.pdf` | `ntsb_rir2315_wmata_rosslyn_derailment.pdf` | yes |
| `q2_wmata_derailment_cause` | Semantic | 0.7099 | `ntsb_rir2315_wmata_rosslyn_derailment.pdf` | `ntsb_rir2315_wmata_rosslyn_derailment.pdf` | yes |
| `q2_wmata_derailment_cause` | Sentence window | 0.7604 | `ntsb_rir2315_wmata_rosslyn_derailment.pdf` | `ntsb_rir2315_wmata_rosslyn_derailment.pdf` | yes |
| `q3_two_hour_notification` | Token | 0.7005 | `ecfr_49cfr674_state_safety_oversight.txt` | `ecfr_49cfr674_state_safety_oversight.txt` | yes |
| `q3_two_hour_notification` | Semantic | 0.6814 | `fr_2024_ptasp_final_rule.txt` | `ecfr_49cfr674_state_safety_oversight.txt` | **no** |
| `q3_two_hour_notification` | Sentence window | 0.6914 | `ecfr_49cfr674_state_safety_oversight.txt` | `ecfr_49cfr674_state_safety_oversight.txt` | yes |
| `q4_assault_directive_deadline` | Token | 0.8057 | `fr_2024_general_directive_24_1_assaults.txt` | `fr_2024_general_directive_24_1_assaults.txt` | yes |
| `q4_assault_directive_deadline` | Semantic | 0.7780 | `fr_2024_general_directive_24_1_assaults.txt` | `fr_2024_general_directive_24_1_assaults.txt` | yes |
| `q4_assault_directive_deadline` | Sentence window | 0.8442 | `fr_2024_general_directive_24_1_assaults.txt` | `fr_2024_general_directive_24_1_assaults.txt` | yes |
| `q5_section_5307_safety_set_aside` | Token | 0.7063 | `fr_2024_ptasp_final_rule.txt` | `fr_2024_ptasp_final_rule.txt` | yes |
| `q5_section_5307_safety_set_aside` | Semantic | 0.7172 | `fr_2024_ptasp_final_rule.txt` | `fr_2024_ptasp_final_rule.txt` | yes |
| `q5_section_5307_safety_set_aside` | Sentence window | 0.7797 | `fr_2024_ptasp_final_rule.txt` | `fr_2024_ptasp_final_rule.txt` | yes |

## 3. Confidently scored retrievals that do not contain the answer

Wrong-document chunks scoring at or above cosine 0.45. These are the failures the assignment asks to surface: the embedding was sure, and it was wrong.

| Question | Technique | Rank | Cosine | Came from | Should have been | Preview |
|---|---|---|---|---|---|---|
| `q3_two_hour_notification` | Semantic | 1 | 0.6814 | `fr_2024_ptasp_final_rule.txt` | `ecfr_49cfr674_state_safety_oversight.txt` | 673.29(b), and whether this requirement applies to all relevant hazards or only hazards that meet a determined |
| `q4_assault_directive_deadline` | Semantic | 5 | 0.7450 | `fr_2024_ptasp_final_rule.txt` | `fr_2024_general_directive_24_1_assaults.txt` | \13\ National Public Transportation Safety Plan, 88 FR 34917 (May 31, 2023). https://www.federalregister.gov/d |
| `q5_section_5307_safety_set_aside` | Sentence window | 4 | 0.7360 | `fr_2023_ptasp_proposed_rule.txt` | `fr_2024_ptasp_final_rule.txt` | This includes the requirement that if a large urbanized area provider does not meet one of the safety risk red |
| `q5_section_5307_safety_set_aside` | Sentence window | 5 | 0.7307 | `fr_2024_national_transit_safety_plan.txt` | `fr_2024_ptasp_final_rule.txt` | Applicability Comments: Two commenters expressed that the National Safety Plan and safety performance measurem |
| `q5_section_5307_safety_set_aside` | Semantic | 2 | 0.7120 | `fr_2023_ptasp_proposed_rule.txt` | `fr_2024_ptasp_final_rule.txt` | SUPPLEMENTARY INFORMATION: Table of Contents I. Executive Summary A. Purpose of Regulatory Action B. Statutory |
| `q5_section_5307_safety_set_aside` | Token | 3 | 0.6936 | `fr_2023_ptasp_proposed_rule.txt` | `fr_2024_ptasp_final_rule.txt` | of Federal financial assistance under 49 U.S.C. 5307 or a rail transit agency. Transit Asset Management Plan m |
| `q5_section_5307_safety_set_aside` | Token | 4 | 0.6879 | `fr_2023_ptasp_proposed_rule.txt` | `fr_2024_ptasp_final_rule.txt` | be more likely to adopt as a result of developing risk reduction programs or explicitly considering bus collis |
| `q5_section_5307_safety_set_aside` | Semantic | 4 | 0.6804 | `fr_2023_ptasp_proposed_rule.txt` | `fr_2024_ptasp_final_rule.txt` | L. 114-94; December 4, 2015). To implement the requirements of 49 U.S.C. 5329(d), FTA issued a final rule on J |
| `q3_two_hour_notification` | Sentence window | 3 | 0.6800 | `fr_2024_national_transit_safety_plan.txt` | `ecfr_49cfr674_state_safety_oversight.txt` | One commenter recommended that FTA allow individual transit agencies to define what events will be included in |
| `q3_two_hour_notification` | Sentence window | 4 | 0.6767 | `fr_2024_ptasp_final_rule.txt` | `ecfr_49cfr674_state_safety_oversight.txt` | Similarly, FTA has not established a time frame for informing transit workers of hazards, associated safety ri |
| `q3_two_hour_notification` | Token | 2 | 0.6718 | `fr_2023_ptasp_proposed_rule.txt` | `ecfr_49cfr674_state_safety_oversight.txt` | safety performance targets based on the safety performance measures established under the National Public Tran |
| `q3_two_hour_notification` | Sentence window | 5 | 0.6694 | `fr_2024_national_transit_safety_plan.txt` | `ecfr_49cfr674_state_safety_oversight.txt` | FTA disagrees with the commenter who suggested transit agencies should define what events to include in the ma |
| `q3_two_hour_notification` | Semantic | 2 | 0.6650 | `ntsb_rir2315_wmata_rosslyn_derailment.pdf` | `ecfr_49cfr674_state_safety_oversight.txt` | The National Public Transportation Safety Plan also includes guidance on how to set safety performance measure |
| `q3_two_hour_notification` | Token | 4 | 0.6603 | `fr_2024_national_transit_safety_plan.txt` | `ecfr_49cfr674_state_safety_oversight.txt` | until FTA establishes related performance [[Page 25318]] measures through the National Safety Plan (https://ww |
| `q3_two_hour_notification` | Token | 5 | 0.6566 | `fr_2024_ptasp_final_rule.txt` | `ecfr_49cfr674_state_safety_oversight.txt` | Comments: One commenter requested that FTA clarify when a transit agency must communicate hazards relevant to  |
| `q3_two_hour_notification` | Semantic | 4 | 0.6248 | `ecfr_49cfr673_agency_safety_plans.txt` | `ecfr_49cfr674_state_safety_oversight.txt` | 5311 unless it operates a rail fixed guideway public transportation system. § 673.3 Policy. The Federal Transi |
| `q3_two_hour_notification` | Semantic | 5 | 0.6190 | `fr_2024_national_transit_safety_plan.txt` | `ecfr_49cfr674_state_safety_oversight.txt` | L. 117-58). On February 5, 2016, FTA first published a Federal Register notice (81 FR 6372) seeking comment on |

_17 such retrievals in total; the 17 highest-scoring are shown._

### Why the embedding scored it that highly

The single rank-1 miss is the one that matters, because it is the chunk a naive
RAG system would actually hand to a generator: **q3_two_hour_notification**,
semantic chunking, cosine **0.6814**, pulled from `fr_2024_ptasp_final_rule.txt`
when the answer exists only in `ecfr_49cfr674_state_safety_oversight.txt`.

The retrieved chunk is 2,955 characters of rulemaking commentary about
Sec. 673.29(b) and whether a hazard requirement "applies to all relevant hazards
or only hazards that meet a determined risk rating." It shares nearly the whole
vocabulary of the query -- safety event, hazard, requirement, transit agency,
FTA, notification -- while containing none of its answer.

That is the failure mode the embedding is built to have. MiniLM encodes topical
similarity, not propositional content: "how quickly must an agency notify FTA of
a safety event" and "which hazards require a risk rating" land in almost the same
region of the space, because both are about transit-safety reporting obligations.
The phrase that actually discriminates, *within two hours*, is one clause in a
38 KB regulation, and averaged into a 2,955-character chunk embedding it carries
almost no weight. Nothing about the score is wrong; the chunk really is topically
close. It just does not answer the question.

q3 is the corpus's hardest query by a wide margin: 10 of the 17 confidently-wrong
retrievals belong to it, and it produced the lowest rank-1 cosine for all three
techniques. The question was chosen because Part 673 (safety plans) and Part 674
(state oversight) discuss overlapping subject matter in near-identical register,
and that overlap is exactly what the embedding cannot separate.

## 4. Observations

Sentence-window chunking won, and it won because its retrieval unit matches the
size of the thing being retrieved. Every answer in `questions.yaml` is one or two
sentences -- a probable-cause finding, a deadline, a percentage. The mean
sentence-window node embeds 317.8 characters, against 1,980 for token and 2,146
for semantic. When a one-sentence answer is averaged into a 2,000-character
chunk vector, the rest of the chunk dilutes it; at 318 characters it dominates.
That shows up directly in the scores: top-1 cosine 0.7809 against 0.7532 and
0.7476, mean@5 0.7615 against 0.7193 and 0.7158, and the best rank-1 cosine on
three of the five questions (q2, q4, q5). The window itself costs nothing at
retrieval time -- the neighbouring sentences sit in metadata, excluded from the
embedding, so each node carries a mean 1,151.9 characters of context, 3.6x its
embedded length, without polluting the vector that does the matching.

Semantic chunking was the weakest and by far the most expensive, and the chunk
statistics say why. Its chunks range from 3 characters to 51,993 -- against
197-3,506 for token. MiniLM truncates at 256 word-pieces, roughly 1,000
characters, so a 51,993-character chunk is about 98% invisible to the model that
embeds it. The 95th-percentile breakpoint threshold, chosen to keep chunks
topical, simply never fired inside the long enumerated passages that federal
regulations are built from, and the result is a handful of enormous chunks whose
embeddings represent only their opening paragraph. Semantic was the only
technique to get a rank-1 answer wrong (q3), it owns 7 of the 17
confidently-wrong retrievals, and it cost 699.84s to chunk against token's 1.88s
-- 372x the price for the worst retrieval quality of the three.

One caveat on Recall@5: all three techniques scored 1.00, so document-level
recall does not discriminate between them at all on this corpus. Every technique
put the right file somewhere in the top 5 for every question. The separation is
entirely in rank-1 correctness and in cosine, which is why those columns carry
the argument above. The best technique does vary by query -- semantic produced
the single highest cosine in the whole run (0.8517 on q1, the Sacramento
probable-cause question, where the answer is a long formal paragraph that its
larger chunks happened to capture whole).

## 5. Conclusion

**Sentence-window chunking is the best technique for this corpus.** It has the
highest top-1 cosine (0.7809) and mean@5 cosine (0.7615) of the three, it is the
only technique with rank-1 correct on all five questions, and it wins the rank-1
cosine on three of them. The price is 2.5x the retrieval latency of the other two
(235.14 ms against ~93 ms) because the store holds 6,008 vectors instead of ~500,
and 510.16s to embed them -- real costs, but one-time at index build and still
sub-second at query time. Semantic chunking is not worth its price here: it is
the slowest to build by two orders of magnitude, produces chunks up to 51,993
characters that the embedding model can only partially read, and returns the
worst retrieval quality of the three. Token chunking is the pragmatic middle --
within 0.03 cosine of the winner for a fortieth of the total build cost -- and
would be the sensible default if index build time mattered.

---

Regenerate with:

```bash
python code/run_rag_chunking.py        # writes reports/hw03/raw/
python code/summarize_rag_metrics.py   # writes this file
```
