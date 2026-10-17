# Agent Instructions

Durable instructions for any assistant working in this repository. Facts learned
from conversations belong in MEMORY.md, not here.

## Project description
- This is the DATA 260 course project: a municipal transit-incident reporting system
  (domain: Transit Incident, primary field `routeId`, secondary field `location`).
- One codebase is extended each homework; never fork or copy code per homework.

## Technology stack
- Backend is Python 3.12 with FastAPI, Pydantic v2 and PyMongo / SQLAlchemy; the model runs
  locally through Ollama (`qwen3:8b`) behind `src/model_client.py`.
- All model calls go through `ModelClient.complete()`; never call the Ollama HTTP API directly.

## Coding conventions
- Function and variable names use snake_case; every function has type hints on all parameters
  and on its return value, plus a docstring.
- Application code uses the `logging` module; never leave `print()` calls in it.
- Keep lines at 100 characters or fewer.

## Testing approach
- Every new function ships with a pytest test named `test_<function_name>` that covers at
  least one edge case (empty input, boundary value, or invalid input).

## Prohibited actions
- Never use `eval` or `exec`, never hardcode secrets or passwords (read them from the
  environment), and never commit `.env` files.
- Never change the fixed configuration: SID4 3170, backend port 8470, Vite port 8471,
  database names `s3170_rel` and `s3170_doc`.

## Code review mode
When asked to review code, respond using ONLY a bulleted list of issues or observations.
- No introductions, no summaries, no prose paragraphs outside the bullets.
- Each bullet must be a single, concise point.
- If there are no issues, respond with exactly one bullet: "- No issues found."
- Do not include code fences or restate the submitted code.
