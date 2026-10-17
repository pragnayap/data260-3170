"""
HW6 Part 2 - chat and memory endpoints.

    POST /api/chat                  one memory-aware turn (see chat_memory.handle_chat)
    GET  /api/memory/{user_id}      last 16 messages, latest summaries, last 20 episodes
    GET  /api/aggregate/{user_id}   daily message counts + 5 most recent summaries

The optional short_term_n / summarize_every / top_k / policy fields override the
env defaults for one request. They exist so the Part 3 sweep can drive N=4/12/30
and the compression policy against one running server.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError

import chat_memory

router = APIRouter(tags=["hw6-memory"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    user_id: str = Field(..., min_length=1, max_length=100)
    session_id: Optional[str] = Field(None, max_length=100)
    message: str = Field(..., min_length=1, max_length=4000)
    short_term_n: Optional[int] = Field(None, ge=0, le=200)
    summarize_every: Optional[int] = Field(None, ge=0, le=100)
    top_k: Optional[int] = Field(None, ge=0, le=20)
    policy: Optional[str] = Field(None, pattern="^(none|evict_old_assistant)$")
    run_label: Optional[str] = Field(None, max_length=100)


def _guard(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ServerSelectionTimeoutError:
        raise HTTPException(status_code=503, detail="MongoDB is unreachable")
    except PyMongoError:
        raise HTTPException(status_code=500, detail="Database error")


@router.post("/api/chat")
def chat(body: ChatRequest):
    return _guard(chat_memory.handle_chat, **body.model_dump())


@router.get("/api/memory/{user_id}")
def memory(user_id: str):
    return _guard(chat_memory.get_memory, user_id)


@router.get("/api/aggregate/{user_id}")
def aggregate(user_id: str):
    return _guard(chat_memory.get_aggregate, user_id)
