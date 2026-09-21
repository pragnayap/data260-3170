# AI_USE - HW3

> **Read this before submitting.** This is a draft written from the actual
> working session, and the three incidents described below really happened in
> this repository. Edit the wording so it is your account rather than a
> transcript, and add anything you did outside the session (running the corpus
> fetch, taking the screenshots, deciding which sources to use).

## 1. What I used an AI assistant for, and what I did myself

**Assistant (Claude, via Claude Code):**

- Drafted `code/web_application/auth.py`, the four Jinja2 templates, and the
  `SessionMiddleware` wiring in `app.py`.
- Drafted `code/fetch_corpus.py`, `code/run_rag_chunking.py`,
  `code/summarize_rag_metrics.py` and `code/verify_hw03.py`.
- Drafted this file, `reports/hw03/MANUAL_DOWNLOAD.md`, and the HW3 section of
  the README.

**Me:**

- Chose the corpus: eight federal documents about transit safety and transit
  incidents, mixing regulation (eCFR), rulemaking preamble (Federal Register)
  and incident narrative (NTSB), specifically because those three genres chunk
  differently and that is what the comparison is measuring.
- Wrote and committed `questions.yaml` before any retrieval was run, and
  checked every expected answer against the source document rather than
  against a model's summary of it.
- Ran `code/fetch_corpus.py` and the retrieval pipeline on my own machine;
  the assistant's sandbox could not reach ecfr.gov, federalregister.gov,
  ntsb.gov or huggingface.co, so every number in `METRICS.md` comes from a run
  I executed.
- Took all screenshots and assembled `report.pdf`.
- Reviewed and corrected the drafted code; three of those corrections are
  described below.

## 2. An AI-produced output that was wrong or unsuitable

Three, in decreasing order of seriousness.

**(a) The first authentication implementation could not actually revoke a
session.** The drafted `auth.py` stored `username` and `last_seen` directly in
Starlette's `SessionMiddleware` cookie and treated `request.session.clear()` on
logout as sufficient. That is wrong. `SessionMiddleware` keeps a *signed*
cookie, not a server-side session: clearing it only tells the browser to stop
sending it. Anyone holding a copy of the cookie value from before the logout
could replay it, and it would still verify. Since HW3 explicitly requires
proving "an expired or logged-out session cannot be reused to reach
`/dashboard`", the implementation would have failed the requirement it was
written for.

**(b) The recomputed cosine similarity did not match the retriever's own
score.** In `run_rag_chunking.py`, the retrieved chunks were re-embedded using
`node.get_content()` and the resulting cosine was compared against the store
score. For the sentence-window technique the two disagreed by as much as 0.18.

**(c) A guessed source URL 404'd.** The Federal Register plain-text URL for
General Directive 24-1 was constructed as
`.../full_text/text/2024/10/03/2024-21923.txt` from a search-result URL, and
returned 404.

## 3. How I detected the problem

**(a)** A smoke test written before trusting the code, not after. It logged in,
kept a copy of the session cookie, logged out, and then replayed that saved
cookie in a fresh HTTP client. The expected result was a redirect to `/login`;
the actual result was `200 OK` on `/dashboard`. The test is now permanent as
`session:logged_out_cookie_cannot_reach_dashboard` in `code/verify_hw03.py`,
so the hole cannot reopen silently.

**(b)** The assignment asks for the cosine to be computed *explicitly* rather
than copied from the retriever, which only has a point if the two numbers are
then compared. Printing them side by side made the disagreement obvious
immediately: identical for token and semantic chunking, consistently off for
sentence-window only. That pattern pointed straight at the difference between
the techniques rather than at the arithmetic.

**(c)** `fetch_corpus.py` refuses to save any response under 2,000 bytes and
prints the failure instead, so the bad URL surfaced as a named failure during
the fetch rather than as a silently truncated document in the corpus. I then
looked the document up on federalregister.gov and read the real publication
date off it.

## 4. What I changed, and why it works now

**(a)** Sessions are now revocable. Each successful login mints a random
session id with `secrets.token_urlsafe(24)` and registers it in a server-side
`ACTIVE_SESSIONS` dictionary; the cookie carries only that id. Every protected
request must pass three gates: a valid signature, an id still present in the
registry, and an idle window that has not elapsed. Logout and idle expiry both
*delete* the id from the registry, so a replayed cookie now fails at the
registry lookup even though its signature is still perfectly valid. Authority
moved from the cookie to the server, which is what makes revocation possible
at all. The registry is in memory and dies with the process, matching the
in-memory incident store from HW2; a production system would use Redis or a
sessions table, with identical logic.

**(b)** The re-embedding now uses
`node.get_content(metadata_mode=MetadataMode.EMBED)` instead of the bare node
text. LlamaIndex embeds a node together with whatever metadata is not on its
exclusion list, so for `SentenceWindowNodeParser` the string that was actually
indexed is the sentence plus file metadata, while `get_content()` alone returns
just the sentence — two different strings, hence two different vectors. It was
never a scoring bug. With the fix the recomputed cosine matches the store score
for all three techniques, which also confirms the store score really is cosine
similarity rather than some other metric. `chunk_len_chars` still measures the
bare chunk, because that is what "chunk length" means in the comparison table;
the embedded length is recorded separately as `embedded_text_len_chars`.

**(c)** The correct date is 2024/09/25. Beyond fixing the one URL,
`fetch_corpus.py` now resolves every Federal Register document through the
public API (`/api/v1/documents/{number}.json`), reads `raw_text_url` from the
response, and only falls back to the hardcoded URL if the API is unreachable.
The document number is stable; the date-based path was an assumption, and the
API removes it. `SOURCES.md` records the URL that was actually retrieved, not
the one that was intended.

## Verification independent of the assistant

- `code/verify_hw03.py` runs 73 checks against the real system: it starts the
  FastAPI app on port 8470 and drives the full auth flow over HTTP, then
  re-hashes every corpus file against `CORPUS_MANIFEST.json`.
- It also checks the commit timestamp of `questions.yaml` against that of
  `raw/retrieval_rows.jsonl`, so the "questions committed before results"
  requirement is evidenced by the repository rather than asserted in prose.
- Every corpus document is hashed with SHA-256, so the exact bytes that
  produced the reported numbers are identifiable.
- `summarize_rag_metrics.py` reads only `reports/hw03/raw/`, never the corpus or
  the model, so deleting `METRICS.md` and re-running rebuilds it byte-for-byte
  from the same raw files. No number in it is transcribed by hand.
