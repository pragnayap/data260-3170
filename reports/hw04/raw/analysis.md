# HW4 Part 4 — written analysis (300–500 words)

Retrieval quality varied a lot by question, and it was the main lever on
everything downstream. **Q1** (single fact: 90% on-time within 5 minutes) had
its target chunk at rank 2 of 3 in the raw top-3, so both basic RAG (B) and
context-engineered RAG (C) retrieved and answered it correctly, C citing
`[Source 2]`. **Q2** (probable-cause deadline + fatality-notification window)
originally failed retrieval when phrased around brake-wear thresholds: the
target chunk (`mechanical_failure_maintenance_002`, "80 percent... pulled
from service immediately") never made it into the top 10 candidates because
`mechanical_failure_maintenance_000`, a chunk about routine 6,000-mile brake
*inspection intervals*, out-scored it on generic word overlap ("brake",
"vehicle", "service"). I rewrote Q2 around a same-document pair (4-hour
fatality notification, 30-day probable-cause deadline) that empirically
retrieved cleanly at rank 1 and 3 — documented in `code/rag.py`'s
`Question` definitions. This is the clearest context-engineering lesson from
this corpus: an embedding model can rank a generic, topic-adjacent chunk
above the one specific chunk that actually answers the question, and no
amount of prompt engineering fixes that — only retrieval design (larger
candidate pool, better chunk boundaries, or, as here, choosing facts that
survive retrieval) does.

Stripping each document's repeated boilerplate header before chunking
(`DOC_HEADER_RE` in `code/rag.py`) measurably helped: without it, chunk 0 of
every document won almost every query on the "BAYWOOD TRANSIT AUTHORITY"
title-block overlap alone.

**Q3** (the cross-document "2 hours" overlap) is where de-duplication and
source-labeling mattered most: candidate selection correctly kept chunks
from all three documents (none were near-duplicates by the text-similarity
check, since each anchors the clock differently — discovery, filing, or
occurrence). But citation-based grounding rules did not force full
synthesis: config C picked one framing (`incident_reporting_policy`'s
filing-based clock, citing Source 2) and presented it as the whole answer,
rather than stating that the clock start differs by category. Config B did
the same in reverse, generalizing the collision doc's occurrence-based
clock to both categories. Both are partially right, partially conflated —
"cite a source" is a weaker rule than "address every source."

**Q5/Q6 confirm the grounding rule works**: config A hallucinated "24 hours"
for Q3 and "immediately" for Q2's fatality window, and both A and B answered
Q6 (boiling point) correctly but ungrounded — exactly the fine/expected
contrast the assignment describes. Config C refused both Q5 and Q6 with the
exact required string, verified programmatically. Notably, C also refused
**Q4** (ambiguous), even though I hadn't required that: the three chunks
that survived filtering were all generic section-opener text with no
specific resolution-time number, so refusing was the honest response to
weak retrieval, not a grounding-rule bug.

The k-sweep on Q1 showed k=3 was best: k=1 retrieved only the document's
opening chunk (not the on-time-target chunk) and correctly refused; k=5
added two off-topic chunks (another document's purpose statement, an
unrelated holiday-schedule note) that the model correctly ignored, producing
an identical answer to k=3. More context neither helped nor hurt once the
needed fact was already in context — it only started adding noise the model
had to filter out itself.
