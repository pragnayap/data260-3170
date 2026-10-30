"""HW8 - one small local-model helper (qwen3:8b via Ollama) with a token cap and a timeout, so a
stalled generation can never hold an agent forever (the HW7 lesson)."""

from __future__ import annotations

import os

MODEL = os.environ.get("HW8_MODEL", "qwen3:8b")
_llm = None


def complete(prompt: str, max_tokens: int = 300) -> str:
    global _llm
    if _llm is None:
        from langchain_ollama import ChatOllama

        _llm = ChatOllama(model=MODEL, temperature=0.0, reasoning=False, num_predict=max_tokens,
                          client_kwargs={"timeout": 180})
    reply = _llm.invoke(prompt)
    return " ".join(str(reply.content).split())
