"""
Part 4 - Reusable model-adapter module.

All model calls in this project go through ModelClient.complete(), which
centralizes token accounting (per-turn and cumulative) in one place instead
of scattering it across every script that talks to the model.
"""

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from langchain_ollama import ChatOllama
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage


@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ModelClient:
    """Stable adapter around the underlying chat model.

    Interface: complete(messages, tools=None) -> str
      messages: list of {"role": "system"|"user"|"assistant", "content": str}
      tools: reserved for future tool-calling support; unused for now.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.0,
    ):
        self.model_name = model or os.environ.get("SMOL_MODEL", "qwen3:8b")
        self.base_url = base_url or os.environ.get("OLLAMA_URL", "http://localhost:11434")
        self._llm = ChatOllama(
            model=self.model_name,
            base_url=self.base_url,
            temperature=temperature,
            reasoning=False,
        )

        self.turn_count = 0
        self.cumulative = TokenUsage()

    def complete(self, messages: List[Dict[str, str]], tools: Optional[List[Any]] = None) -> str:
        lc_messages = []
        for m in messages:
            role, content = m["role"], m["content"]
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            else:
                lc_messages.append(HumanMessage(content=content))

        response = self._llm.invoke(lc_messages)

        usage = getattr(response, "usage_metadata", None) or {}
        input_tokens = usage.get("input_tokens", 0) or 0
        output_tokens = usage.get("output_tokens", 0) or 0

        self.turn_count += 1
        self.cumulative.input_tokens += input_tokens
        self.cumulative.output_tokens += output_tokens

        print(
            f"[turn {self.turn_count}] input_tokens={input_tokens} "
            f"output_tokens={output_tokens} total_tokens={input_tokens + output_tokens}"
        )

        return response.content

    def stats(self, history: List[Dict[str, str]]) -> Dict[str, Any]:
        """Return current stats WITHOUT mutating history."""
        return {
            "turn_count": self.turn_count,
            "cumulative_input_tokens": self.cumulative.input_tokens,
            "cumulative_output_tokens": self.cumulative.output_tokens,
            "cumulative_total_tokens": self.cumulative.total_tokens,
            "history_length_chars": len(json.dumps(history)),
        }

    def print_exit_summary(self):
        print(
            f"\n[exit] turns={self.turn_count} "
            f"cumulative_input_tokens={self.cumulative.input_tokens} "
            f"cumulative_output_tokens={self.cumulative.output_tokens} "
            f"cumulative_total_tokens={self.cumulative.total_tokens}"
        )
