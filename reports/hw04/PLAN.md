# HW4 — build plan

Four parts. Read `CLAUDE.md` at the repo root first for fixed config and gotchas.

## Decisions already made

| Question | Decision | Why |
|---|---|---|
| Folder layout | Extend `code/web_application/` as the backend; add `code/frontend/` | HW4 says "continue extending your existing codebase… do not create a separate copy". The demo's `backend/`+`frontend/` split is a standalone project with no history to preserve. |
| Frontend ↔ backend | **CORS**, not a Vite proxy | Matches the class demo, and Postman screenshots hit the same URLs the React app does. |
| Vite port | 8471 (`strictPort: true`) | Spec doesn't name one. PORT_BASE+1 reads as an obvious pair. |
| Related table (Part 3) | **`routes`** — 200 rows, `incidents.route_id` FK | Spec leaves it open ("just test data for now"); the demo has no Part 3. Many-to-one gives the textbook one-extra-query-per-record. |
| MySQL driver | `pymysql` | Pure Python. `mysqlclient` compiles C and fails often on Intel macOS. |
| Part 4 corpus | New `data/rag_docs/`, separate from HW3's | Need ≥5 small docs where we control exactly which facts exist — Q5/Q6 must have no answer present. |
| MySQL host | Local brew MySQL, not Docker | Confirmed against `Homework 4 demo code/DATA236_demo4` — the class demo also connects to plain `localhost:3306`, no container. |
| DB session variable name | `db_session_basede26` (literal) | Spec requires this exact name "strictly" for the sessionmaker in `database.py`. |
| Session cookie | New `s3170_db_session` cookie, separate from HW3's `s3170_session` | HW4 needs an *opaque* token (no signed session blob) referencing the new `sessions` table; reusing the old signed cookie name would collide with HW3's Starlette `SessionMiddleware`, which still runs for the old server-rendered login. |

## Part 1 — React client

- [x] `code/frontend/` scaffold: Vite + React, `vite.config.js` port 8471 strictPort
- [x] `src/api/incidentsApi.js` — axios, `baseURL: http://localhost:8470`, `withCredentials: true`
- [x] `pages/Login.jsx` — **email + password** (not username)
- [x] `pages/Home.jsx` — list at `/`
- [x] `pages/CreateRecord.jsx` — `/create`, routeId + location, redirect home
- [x] `pages/UpdateRecord.jsx` — `/update/:id`
- [x] `pages/DeleteRecord.jsx` — `/delete/:id`
- [x] State in `App.jsx`, handlers passed **as props** (spec requires this)
- [x] `useState` / `useEffect`; react-router-dom for routing
- [x] Logged-out: show "Login required", hide/disable Add Record
- [ ] **Manual**: click through in a real browser and screenshot each state (see `reports/hw04/NEXT_STEPS.md`) — no browser automation available in this environment

## Part 2 — MySQL + server-side sessions

- [x] Database `s3170_rel`
- [x] `incidents` — auto-inc id, routeId (primary), location (secondary), + existing fields, `related_route_id` FK
- [x] `routes` — 200 rows (also serves Part 3)
- [x] `users` — id, name, email (unique), password_hash
- [x] `sessions` — id (token), user_id, created_at, expires_at
- [x] `database.py`, `models.py`, `schemas_db.py`, `crud.py`, `session_crud.py`
- [x] Password hashing: reuse HW3 PBKDF2-HMAC-SHA256, 200k iterations, per-user salt
- [x] Login issues an **opaque** token; cookie carries the token only, HttpOnly
- [x] `require_session` dependency on **every** CRUD route, not just list
- [x] REST: POST / GET all / GET by id / PUT / DELETE — verified live via curl, see `verify_hw04.py`
- [ ] **Manual**: Postman screenshots for each operation + DB screenshot + folder-structure screenshot — collection ready at `reports/hw04/postman_collection.json`

## Part 3 — N+1 measurement

- [x] `seed_hw04.py` — 5,000 incidents + 200 routes, seeded from SEED=3170.
- [x] Naive list endpoint: one extra query per record (**leave it naive**)
- [x] `measure_n1.py` — page sizes 10/50/200 × naive/fixed × 30 requests = **180**
- [x] Record SQL statements per request + p50/p95/p99 latency
- [x] Fixed version: join or `selectinload`, re-measure
- [x] All 180 rows → `reports/hw04/raw/n1_requests.csv`
- [x] Speed-up per page size + why it grows with page size — see `METRICS.md`
- [x] One index (`category`); `EXPLAIN` before and after — `raw/index_explain.txt`
- [ ] **Manual**: Postman screenshots of both versions at each page size — collection ready

## Part 4 — Grounded RAG

- [x] `data/rag_docs/` — 5 documents (invented "Baywood Transit Authority" policy docs, DOMAIN_ID 2 themed)
- [x] Chunk 500 / overlap 50; store text, source name, chunk_id; embed into a vector store (LlamaIndex SimpleVectorStore, matching HW3's approach)
- [x] Print top-k retrievals with source + score **before** calling the LLM — `raw/retrieval_printouts.txt`
- [x] Three configs: (A) No RAG · (B) Basic RAG top-3 raw · (C) Context-engineered
      — de-duplicate, drop irrelevant, order + label with sources, grounding rules,
      cite source number, refuse with "I cannot answer this question from the provided documents"
      — verified exact-string refusal programmatically on Q5/Q6, not just visually
- [x] Six questions: Q1 one chunk · Q2 two chunks · Q3 similar across docs ·
      Q4 ambiguous · Q5 not in docs · Q6 unrelated. **Q5 and Q6 refused, confirmed.**
      (Q2 was redesigned mid-build after its original phrasing failed retrieval —
      documented as a real finding in `raw/analysis.md`, not hidden.)
- [x] k-sweep at k = 1, 3, 5 on Q1 — k=3 best, see `METRICS.md`
- [x] Evaluation table: correct retrieval, correct answer, grounded, refused-when-needed;
      summarise accuracy / faithfulness / format compliance / robustness — `raw/evaluation_table.md`
- [x] Analysis, 499 words — `raw/analysis.md`
- [x] `code/rag.py` + all outputs in `reports/hw04/raw/` — real Ollama `qwen3:8b` calls throughout, no fabricated output

## Deliverables — `reports/hw04/`

- [x] `RUN_LOG.txt` — real console output + timestamps
- [x] `raw/` — the 180 N+1 measurements, EXPLAIN output, RAG printouts/tables
- [x] `METRICS.md` — filled-in results tables
- [x] `AI_USE.md` — the four questions
- [x] `verification.json` — from `code/verify_hw04.py` — **26/26 checks pass**
- [ ] **Manual**: `Priyadarshini_HW4.pdf` — code snippet **and** output screenshot for every
      question and sub-question, written analysis, AI_USE answers — see `NEXT_STEPS.md`
- [ ] **Manual**: Tag `hw4`, push with `--tags` (holding off — not committing to git per your instruction)

## Build order

1. **Part 2** — everything else depends on the database
2. **Part 3** — needs the DB seeded; longest-running step
3. **Part 1** — React against a backend that already works
4. **Part 4** — independent, can slot in anywhere

## Open items

- [x] Confirm MySQL is running and the root password — reset locally (stored in `.env`, gitignored), see `CLAUDE.md`
- [x] `npm` available? — wasn't; installed via `nvm` (Homebrew's node build hit a checksum mismatch on an llvm dependency, so used nvm's precompiled binary instead)
- [x] Ollama model for Part 4: `qwen3:8b` from HW1/HW2, already pulled

See `reports/hw04/NEXT_STEPS.md` for exactly what's left (screenshots + PDF assembly).
