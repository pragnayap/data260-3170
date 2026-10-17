# MEMORY.md
<!-- last_consolidated: 2026-10-15T09:01:43+00:00 -->

## Identity and course
- [2026-09-03] The student goes by the name Lucky.
- [2026-09-01] The student is in the SJSU MS Applied Data Intelligence program.
- [2026-09-03] The student's SID4 is 3170.
- [2026-09-05] The project domain is Municipal Transit Incidents (DOMAIN_ID 2).
- [2026-09-05] The assigned domain is Municipal Transit Incidents.

## Ports and servers
- [2026-09-02] The FastAPI backend runs on port 8470 (assigned by SID4, do not change).
- [2026-09-02] The FastAPI backend must listen on port 8470.
- [2026-09-15] The Vite dev server uses port 5173.
- [2026-09-25] The Vite dev server uses port 8471 with strictPort true.
- [2026-10-09] The backend runs on port 8000 for local development.
- [2026-09-04] MySQL runs on localhost:3306 and the database is s3170_rel.
- [2026-10-01] MongoDB runs locally, installed through Homebrew.
- [2026-10-12] MongoDB runs in a Docker container named s3170_mongo on port 27017.
- [2026-10-12] The MongoDB database for HW6 is s3170_doc.

## Models and machine
- [2026-09-06] The machine is an Intel x86_64 Mac with Homebrew at /usr/local.
- [2026-09-06] This is an Intel Mac, so Homebrew lives in /usr/local.
- [2026-09-06] PyTorch is pinned to 2.2.2 because newer versions do not support Intel Macs.
- [2026-09-07] sentence-transformers must stay at 3.0.1 on this machine.
- [2026-09-07] Do not upgrade sentence-transformers beyond 3.0.1.
- [2026-09-08] The local chat model is qwen3:8b served by Ollama.
- [2026-09-08] Embeddings use all-MiniLM-L6-v2.
- [2026-10-14] The embedding model is the same MiniLM model used in HW3.

## Security and sessions
- [2026-10-03] Session cookies must always set Secure=True.
<!-- resolved contradiction: kept "Session cookies must always set Secure=True." over "Safari rejects Secure cookies over plain http, so Secure stays off in development." (F27 explicitly states that session cookies must set Secure=True, which contradicts F26's note to keep Secure off in development. F27 is more recent and specific.) -->
- [2026-09-05] The MySQL root password is documented in the README for convenience.
- [2026-10-02] Secrets live only in gitignored .env files and never in the README.
- [2026-09-20] The HW3 session cookie is named s3170_session.
- [2026-10-04] The HW4 session cookie is named s3170_db_session.
- [2026-09-20] Signed cookies are not revocable, so logout needs a server-side session record.

## Workflow and conventions
- [2026-09-10] Deliverables go in reports/hwNN/.
- [2026-09-10] Each homework gets a verify_hwNN.py script and a make target.
- [2026-09-10] Tag the submitted state hw1, hw2, hw3 and so on.
- [2026-09-11] Never commit .env, node_modules, dist or data/corpus_raw.
- [2026-09-11] Never commit the .env file.
- [2026-10-13] Remember to restart uvicorn after editing app.py today.
- [2026-10-13] The sweep script is still running in the background right now.
- [2026-10-13] Ask the TA about the report formatting on Thursday.
- [2026-10-14] There is a pending git stash from this morning to review.
- [2026-10-14] Lucky is currently waiting for the Docker image to finish pulling.

## Retrieval and RAG
- [2026-09-18] HW3 compared fixed-size, semantic and sentence-window chunking.
- [2026-09-18] HW3 chunking comparison covered fixed-size, semantic and sentence-window chunkers.
- [2026-09-19] Retrieval in HW3 used an in-memory SimpleVectorStore, not faiss.
- [2026-09-22] NTSB RIR2315.pdf is AES-encrypted and needs the cryptography package.
- [2026-10-05] HW5 added MCP servers, retries and an agent loop with execute_tool.
- [2026-10-12] HW6 adds MongoDB documents, chat memory and file-based memory.
