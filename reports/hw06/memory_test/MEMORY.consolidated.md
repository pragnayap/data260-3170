# MEMORY.md
<!-- last_consolidated: 2026-10-15T10:51:51+00:00 -->

## Identity and course
- [2026-09-03] The student is Pragnaya Priyadarshini and goes by Lucky.
- [2026-09-01] The student is in the SJSU MS Applied Data Intelligence program.
- [2026-09-01] The course is DATA 260 Agentic AI.
- [2026-09-03] The student's SID4 is 3170.
- [2026-09-05] The project domain is Municipal Transit Incidents (DOMAIN_ID 2).

## Ports and servers
- [2026-09-02] The FastAPI backend runs on port 8470 (assigned by SID4, do not change).
<!-- resolved contradiction: kept "The FastAPI backend runs on port 8470 (assigned by SID4, do not change)." over "The backend runs on port 8000 for local development." (Both describe the backend port, but A specifies a fixed port while B describes a local development setup.) -->
- [2026-09-25] The Vite dev server uses port 8471 with strictPort true.
<!-- resolved contradiction: kept "The Vite dev server uses port 8471 with strictPort true." over "The Vite dev server uses port 5173." (Both facts refer to the same setting (Vite dev server port) but with different values.) -->
- [2026-09-04] MySQL runs on localhost:3306 and the database is s3170_rel.
- [2026-10-12] MongoDB runs in a Docker container named s3170_mongo on port 27017.
<!-- resolved contradiction: kept "MongoDB runs in a Docker container named s3170_mongo on port 27017." over "MongoDB runs locally, installed through Homebrew." (Both describe MongoDB setup, but B specifies a Docker container and port, while A describes a local installation.) -->
- [2026-10-12] HW6 adds MongoDB documents, chat memory and file-based memory.

## Models and machine
- [2026-09-06] The machine is an Intel x86_64 Mac with Homebrew at /usr/local.
- [2026-09-06] PyTorch is pinned to 2.2.2 because newer versions do not support Intel Macs.
- [2026-09-07] sentence-transformers must stay at 3.0.1 on this machine.
- [2026-09-08] The local chat model is qwen3:8b served by Ollama.
- [2026-10-14] The embedding model is the same MiniLM model used in HW3.

## Security and sessions
- [2026-10-03] Session cookies must always set Secure=True.
<!-- resolved contradiction: kept "Session cookies must always set Secure=True." over "Safari rejects Secure cookies over plain http, so Secure stays off in development." (Both address Secure cookies, but A says Secure stays off while B requires Secure=True.) -->
- [2026-10-02] Secrets live only in gitignored .env files and never in the README.
<!-- resolved contradiction: kept "Secrets live only in gitignored .env files and never in the README." over "The MySQL root password is documented in the README for convenience." (Both facts address password storage, but they contradict each other.) -->
- [2026-09-20] The HW3 session cookie is named s3170_session.
- [2026-10-04] The HW4 session cookie is named s3170_db_session.
- [2026-09-20] Signed cookies are not revocable, so logout needs a server-side session record.

## Workflow and conventions
- [2026-09-10] Deliverables go in reports/hwNN/.
- [2026-09-10] Each homework gets a verify_hwNN.py script and a make target.
- [2026-09-10] Tag the submitted state hw1, hw2, hw3 and so on.
- [2026-09-11] Never commit .env, node_modules, dist or data/corpus_raw.

## Retrieval and RAG
- [2026-09-18] HW3 chunking comparison covered fixed-size, semantic and sentence-window chunkers.
- [2026-09-19] Retrieval in HW3 used an in-memory SimpleVectorStore, not faiss.
- [2026-09-22] NTSB RIR2315.pdf is AES-encrypted and needs the cryptography package.
- [2026-10-05] HW5 added MCP servers, retries and an agent loop with execute_tool.
