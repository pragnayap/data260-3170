"""
HW6 Part 2 - short-term, long-term and episodic memory over MongoDB.

Collections (all in s3170_doc, see mongo_db.py):
    messages   user_id, session_id, role, content, created_at
    summaries  user_id, session_id (null for lifetime), scope, text, created_at
    episodes   user_id, session_id, fact, importance, embedding, created_at

One chat turn (handle_chat):
    1. save the user message
    2. load the short-term window (last N messages of this session, before this one)
    3. load the latest session summary and lifetime summary
    4. retrieve top-k episodic facts by cosine similarity to the message embedding
    5. assemble the prompt and call the model through the HW1 ModelClient adapter
    6. save the reply
    7. extract up to 3 facts from the user message, embed, store as episodes
    8. every SUMMARIZE_EVERY user messages: refresh the session summary, and every
       LIFETIME_EVERY session summaries: condense them into the lifetime summary

Knobs come from the environment (defaults below) and can be overridden per
request, which is how the Part 3 sweep runs N=4/12/30 against one live server.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from model_client import ModelClient  # noqa: E402

from mongo_db import get_db  # noqa: E402

SHORT_TERM_N = int(os.environ.get("SHORT_TERM_N", "12"))
SUMMARIZE_EVERY = int(os.environ.get("SUMMARIZE_EVERY_USER_MSGS", "6"))
LIFETIME_EVERY = int(os.environ.get("LIFETIME_EVERY_SESSION_SUMMARIES", "3"))
TOP_K = int(os.environ.get("EPISODE_TOP_K", "3"))
MEMORY_POLICY = os.environ.get("MEMORY_POLICY", "none")  # none | evict_old_assistant
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # same model HW3 used

# Policy knob (Part 3.4): assistant replies older than the newest KEEP_RECENT
# messages of the window are evicted; the user's own messages are never dropped.
POLICY_KEEP_RECENT = 4

METRICS_LOG = Path(
    os.environ.get(
        "S3170_CHAT_LOG",
        Path(__file__).resolve().parents[2] / "reports" / "hw06" / "raw" / "chat_metrics.jsonl",
    )
)

SYSTEM_PRIMER = (
    "You are a helpful assistant for riders and staff of a municipal transit system. "
    "You help people report and follow up on transit incidents (delays, mechanical "
    "failures, accidents, safety hazards). Answer in at most three sentences. "
    "Use the long-term summary and remembered facts below when they are relevant, "
    "and do not invent details about the user that are not in the conversation."
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# model + embeddings
# --------------------------------------------------------------------------- #

_embedder = None


def embed(text: str) -> list[float]:
    """384-d unit-length MiniLM embedding (unit length makes cosine == dot product)."""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer

        _embedder = SentenceTransformer(EMBED_MODEL)
    vec = _embedder.encode(text, normalize_embeddings=True)
    return [float(x) for x in vec]


def llm_call(messages: list[dict]) -> tuple[str, dict]:
    """Call the model through the HW1 adapter; return (text, {input, output} tokens)."""
    client = ModelClient()  # new instance per call: last_usage is not shared across threads
    text = client.complete(messages)
    return text, {"input": client.last_usage.input_tokens, "output": client.last_usage.output_tokens}


# --------------------------------------------------------------------------- #
# episodic memory: extraction, storage, retrieval
# --------------------------------------------------------------------------- #

EXTRACT_PROMPT = (
    "Extract up to 3 short, durable facts about the USER from the message below "
    "(who they are, routes they use, preferences, problems they report, plans). "
    "Skip small talk. Each fact is one short sentence in third person. "
    "Give each an importance from 0 to 1 (1 = must never be forgotten).\n"
    'Reply with ONLY a JSON array like [{"fact": "...", "importance": 0.8}] '
    "or [] if there is nothing worth remembering.\n\nUser message: "
)


def parse_facts(raw: str) -> list[dict]:
    """Pull a JSON array out of model output; tolerate fences and chatter around it."""
    match = re.search(r"\[.*\]", raw, flags=re.S)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    facts = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or not isinstance(it.get("fact"), str):
            continue
        fact = it["fact"].strip()[:200]
        try:
            importance = min(1.0, max(0.0, float(it.get("importance", 0.5))))
        except (TypeError, ValueError):
            importance = 0.5
        if fact:
            facts.append({"fact": fact, "importance": round(importance, 2)})
    return facts[:3]


def extract_episodes(user_id: str, session_id: str, user_msg: str) -> tuple[list[dict], dict]:
    raw, usage = llm_call([{"role": "user", "content": EXTRACT_PROMPT + user_msg}])
    facts = parse_facts(raw)
    docs = [
        {
            "user_id": user_id,
            "session_id": session_id,
            "fact": f["fact"],
            "importance": f["importance"],
            "embedding": embed(f["fact"]),
            "created_at": _now(),
        }
        for f in facts
    ]
    if docs:
        get_db().episodes.insert_many(docs)
    return facts, usage


def cosine_top_k(query_vec: list[float], rows: list[dict], k: int) -> list[dict]:
    """Rank rows by cosine similarity to query_vec; rows must carry 'embedding'."""
    if not rows or k <= 0:
        return []
    mat = np.asarray([r["embedding"] for r in rows], dtype=np.float32)
    q = np.asarray(query_vec, dtype=np.float32)
    sims = (mat @ q) / (np.linalg.norm(mat, axis=1) * np.linalg.norm(q) + 1e-9)
    order = np.argsort(-sims)[:k]
    return [
        {"fact": rows[i]["fact"], "importance": rows[i]["importance"], "score": round(float(sims[i]), 4)}
        for i in order
    ]


def retrieve_episodes(user_id: str, message: str, k: int) -> list[dict]:
    rows = list(get_db().episodes.find({"user_id": user_id}))
    return cosine_top_k(embed(message), rows, k)


# --------------------------------------------------------------------------- #
# short-term window and the compression policy
# --------------------------------------------------------------------------- #

def load_window(user_id: str, session_id: str, n: int, before_id) -> list[dict]:
    cur = (
        get_db()
        .messages.find({"user_id": user_id, "session_id": session_id, "_id": {"$lt": before_id}})
        .sort("_id", -1)
        .limit(n)
    )
    return [{"role": m["role"], "content": m["content"]} for m in reversed(list(cur))]


def apply_policy(window: list[dict], policy: str) -> list[dict]:
    """Part 3.4 eviction policy.

    evict_old_assistant: the user's messages state the facts worth keeping; the
    assistant's replies are paraphrase of what the user already said plus advice,
    and they are about half of the window's tokens. Every assistant reply except
    those in the newest POLICY_KEEP_RECENT messages is dropped from the window.
    """
    if policy != "evict_old_assistant":
        return window
    cutoff = len(window) - POLICY_KEEP_RECENT
    return [m for i, m in enumerate(window) if m["role"] == "user" or i >= cutoff]


# --------------------------------------------------------------------------- #
# long-term summaries
# --------------------------------------------------------------------------- #

def latest_summary(user_id: str, scope: str, session_id: str | None = None) -> dict | None:
    q = {"user_id": user_id, "scope": scope}
    if scope == "session":
        q["session_id"] = session_id
    return get_db().summaries.find_one(q, sort=[("created_at", -1), ("_id", -1)])


SESSION_SUMMARY_PROMPT = (
    "Summarize the conversation below into at most 6 concise bullet points that keep "
    "every concrete detail about the user (names, routes, locations, preferences, "
    "decisions). Merge the previous summary into the result; drop nothing that is still "
    "true. Output only the bullets, each starting with '- '.\n\n"
)
LIFETIME_SUMMARY_PROMPT = (
    "Condense these session summaries about one user into at most 8 bullet points of "
    "durable facts and preferences. Keep concrete details, merge duplicates, and prefer "
    "the newer statement if two disagree. Output only the bullets, each starting with '- '.\n\n"
)


def maybe_summarize(user_id: str, session_id: str, every: int) -> tuple[dict, dict]:
    """Refresh summaries when due. Returns (what_was_written, extra_token_usage)."""
    db = get_db()
    written, usage = {}, {"input": 0, "output": 0}
    n_user = db.messages.count_documents({"user_id": user_id, "session_id": session_id, "role": "user"})
    if every <= 0 or n_user % every != 0:
        return written, usage

    recent = list(
        db.messages.find({"user_id": user_id, "session_id": session_id}).sort("_id", -1).limit(2 * every)
    )[::-1]
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in recent)
    prev = latest_summary(user_id, "session", session_id)
    prompt = SESSION_SUMMARY_PROMPT + (f"Previous summary:\n{prev['text']}\n\n" if prev else "") + (
        f"Conversation:\n{transcript}"
    )
    text, u = llm_call([{"role": "user", "content": prompt}])
    usage["input"] += u["input"]
    usage["output"] += u["output"]
    db.summaries.insert_one(
        {"user_id": user_id, "session_id": session_id, "scope": "session", "text": text.strip(), "created_at": _now()}
    )
    written["session_summary"] = True

    n_sess = db.summaries.count_documents({"user_id": user_id, "scope": "session"})
    if LIFETIME_EVERY > 0 and n_sess % LIFETIME_EVERY == 0:
        parts = list(db.summaries.find({"user_id": user_id, "scope": "session"}).sort("_id", -1).limit(5))[::-1]
        old = latest_summary(user_id, "user")
        body = (f"Existing lifetime summary:\n{old['text']}\n\n" if old else "") + "\n\n".join(
            f"Session summary {i + 1}:\n{p['text']}" for i, p in enumerate(parts)
        )
        text, u = llm_call([{"role": "user", "content": LIFETIME_SUMMARY_PROMPT + body}])
        usage["input"] += u["input"]
        usage["output"] += u["output"]
        db.summaries.insert_one(
            {"user_id": user_id, "session_id": None, "scope": "user", "text": text.strip(), "created_at": _now()}
        )
        written["lifetime_summary"] = True
    return written, usage


# --------------------------------------------------------------------------- #
# prompt assembly
# --------------------------------------------------------------------------- #

def assemble_prompt(
    session_summary: str | None,
    lifetime_summary: str | None,
    episodes: list[dict],
    window: list[dict],
    message: str,
) -> tuple[list[dict], dict[str, str]]:
    """Return (messages for the model, {component: text}) for token accounting."""
    long_term = ""
    if lifetime_summary:
        long_term += f"Lifetime summary of this user:\n{lifetime_summary}\n"
    if session_summary:
        long_term += f"Summary of this session so far:\n{session_summary}\n"
    episodic = ""
    if episodes:
        episodic = "Remembered facts relevant to this message:\n" + "\n".join(f"- {e['fact']}" for e in episodes)

    system = SYSTEM_PRIMER + ("\n\n" + long_term.strip() if long_term else "") + (
        "\n\n" + episodic if episodic else ""
    )
    messages = [{"role": "system", "content": system}, *window, {"role": "user", "content": message}]
    parts = {
        "system_primer": SYSTEM_PRIMER,
        "long_term_summary": long_term.strip(),
        "episodic_facts": episodic,
        "short_term_window": "\n".join(m["content"] for m in window),
        "current_message": message,
    }
    return messages, parts


def split_tokens(prompt_tokens: int, parts: dict[str, str]) -> dict[str, int]:
    """Allocate the model's reported prompt_tokens across components by character share.

    Ollama reports one prompt_eval_count per call and exposes no per-segment
    tokenizer, so component figures are a proportional estimate that always
    sums to the reported total (chat-template overhead is spread across them).
    """
    total_chars = sum(len(t) for t in parts.values()) or 1
    return {k: round(prompt_tokens * len(t) / total_chars) for k, t in parts.items()}


# --------------------------------------------------------------------------- #
# the turn
# --------------------------------------------------------------------------- #

def handle_chat(
    user_id: str,
    message: str,
    session_id: str | None = None,
    short_term_n: int | None = None,
    summarize_every: int | None = None,
    top_k: int | None = None,
    policy: str | None = None,
    run_label: str | None = None,
) -> dict:
    t0 = time.perf_counter()
    n = SHORT_TERM_N if short_term_n is None else short_term_n
    every = SUMMARIZE_EVERY if summarize_every is None else summarize_every
    k = TOP_K if top_k is None else top_k
    pol = MEMORY_POLICY if policy is None else policy
    session_id = session_id or uuid.uuid4().hex[:12]
    db = get_db()

    user_doc = {"user_id": user_id, "session_id": session_id, "role": "user", "content": message, "created_at": _now()}
    user_doc["_id"] = db.messages.insert_one(user_doc).inserted_id

    window = apply_policy(load_window(user_id, session_id, n, user_doc["_id"]), pol)
    sess = latest_summary(user_id, "session", session_id)
    life = latest_summary(user_id, "user")
    episodes = retrieve_episodes(user_id, message, k)

    prompt, parts = assemble_prompt(sess["text"] if sess else None, life["text"] if life else None, episodes, window, message)
    reply, usage = llm_call(prompt)
    reply = reply.strip()
    db.messages.insert_one(
        {"user_id": user_id, "session_id": session_id, "role": "assistant", "content": reply, "created_at": _now()}
    )

    chat_latency_ms = round((time.perf_counter() - t0) * 1000)  # the part the user waits on
    new_facts, ex_usage = extract_episodes(user_id, session_id, message)
    written, sum_usage = maybe_summarize(user_id, session_id, every)

    metrics = {
        "ts": _now().isoformat(),
        "run_label": run_label,
        "user_id": user_id,
        "session_id": session_id,
        "short_term_n": n,
        "policy": pol,
        "prompt_tokens": usage["input"],
        "completion_tokens": usage["output"],
        "component_tokens": split_tokens(usage["input"], parts),
        "latency_ms": chat_latency_ms,
        "total_latency_ms": round((time.perf_counter() - t0) * 1000),
        "overhead_tokens": {
            "extraction_in": ex_usage["input"],
            "extraction_out": ex_usage["output"],
            "summary_in": sum_usage["input"],
            "summary_out": sum_usage["output"],
        },
    }
    try:
        METRICS_LOG.parent.mkdir(parents=True, exist_ok=True)
        with METRICS_LOG.open("a") as fh:
            fh.write(json.dumps(metrics) + "\n")
    except OSError:
        pass  # metrics are best-effort; never fail a chat turn over a log write

    return {
        "reply": reply,
        "session_id": session_id,
        "memory_used": {
            "short_term_count": len(window),
            "short_term": window,
            "session_summary": sess["text"] if sess else None,
            "long_term_summary": life["text"] if life else None,
            "episodic_facts": episodes,
        },
        "memory_written": {"new_episodes": new_facts, **written},
        "metrics": metrics,
    }


# --------------------------------------------------------------------------- #
# read endpoints
# --------------------------------------------------------------------------- #

def _clean(doc: dict | None, drop_embedding: bool = True) -> dict | None:
    if doc is None:
        return None
    out = dict(doc)
    out["id"] = str(out.pop("_id"))
    if drop_embedding and "embedding" in out:
        out["embedding_dim"] = len(out.pop("embedding"))
    for key, val in out.items():
        if isinstance(val, datetime):
            out[key] = val.isoformat()
    return out


def get_memory(user_id: str) -> dict:
    db = get_db()
    msgs = list(db.messages.find({"user_id": user_id}).sort("_id", -1).limit(16))[::-1]
    sess = db.summaries.find_one({"user_id": user_id, "scope": "session"}, sort=[("_id", -1)])
    life = db.summaries.find_one({"user_id": user_id, "scope": "user"}, sort=[("_id", -1)])
    eps = list(db.episodes.find({"user_id": user_id}).sort("_id", -1).limit(20))
    return {
        "user_id": user_id,
        "messages": [_clean(m) for m in msgs],
        "latest_session_summary": _clean(sess),
        "latest_lifetime_summary": _clean(life),
        "episodes": [_clean(e) for e in eps],
    }


def get_aggregate(user_id: str) -> dict:
    db = get_db()
    daily = db.messages.aggregate(
        [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}}, "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
        ]
    )
    recent = db.summaries.find({"user_id": user_id}).sort("_id", -1).limit(5)
    return {
        "user_id": user_id,
        "daily_message_counts": [{"date": d["_id"], "count": d["count"]} for d in daily],
        "recent_summaries": [_clean(s) for s in recent],
    }
