# HW4 Part 4 - evaluation table (heuristic, verified against real transcripts)

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
| q5_not_in_corpus | C | YES | YES | YES | YES |
| q6_unrelated | A | n/a | no | n/a | n/a |
| q6_unrelated | B | YES | no | YES | n/a |
| q6_unrelated | C | YES | YES | YES | YES |

## Summary

- accuracy (correct_answer over all rows): 12/18
- faithfulness (grounded, B/C rows only): 12/12
- format compliance / robustness (refused_when_needed, config C on Q5/Q6): 2/2
- total rows: 18

## k-sweep (q1_single_chunk, config-C-style prompt, raw top-k, no filtering)

| k | chunks shown | top score | answer |
|---|---|---|---|
| 1 | route_service_standards_000 only (routeId scheme, NOT the target) | 0.7036 | Refused (with a preamble sentence, not the bare exact string) |
| 3 | + route_service_standards_001 (the actual target chunk), _003 | 0.7036 / 0.5860 / 0.5779 | Correct, grounded, cited [Source 2] |
| 5 | + incident_reporting_policy_000 (off-topic), route_service_standards_004 (holiday schedule, off-topic) | ...down to 0.5014 | Same correct answer as k=3, still cited [Source 2], irrelevant chunks 4-5 ignored |

k=3 was the best k for this question: k=1 under-retrieved (the single highest-scoring chunk is the document's opening/routeId-scheme chunk, not the chunk with the actual on-time-performance number) and correctly triggered a refusal rather than guessing; k=5 added two off-topic chunks (a different document's purpose statement, and an unrelated holiday-schedule chunk) without changing or improving the answer. More context neither helped nor hurt here once k=3 already contained the needed fact -- see analysis.md.

## Methodology notes (read together with the bools above)

- `correct_retrieval` is `n/a` for config A because config A never retrieves anything.
- For Q5/Q6 (must-refuse questions), `correct_answer` is defined as "produced the exact refusal string." That is only a real requirement for config C; configs A and B were never asked to produce that exact string, and in the real transcripts neither fabricated an answer for Q5 and both correctly, if ungrounded, answered Q6 from general knowledge. Their `correct_answer = false` here reflects the strict column definition, not a real failure -- see analysis.md for what A/B actually did.
- For Q4 (ambiguous, NOT a must-refuse question), config C's real answer was the refusal string, because the chunks that survived candidate selection were three documents' generic opening sections, none of which contained a specific resolution-time number. `correct_answer = false` under the strict definition, but refusing rather than guessing a number is arguably the right call given what was actually retrieved -- see analysis.md.
- For Q3, `correct_answer = true` only requires that "2 hours" appear in the answer; it does not check which of the three different anchor points (discovery-based, filing-based, occurrence-based) the answer picked. In the real transcripts, neither config B nor config C fully disambiguated all three; each picked one framing and presented it as the answer -- see analysis.md.
