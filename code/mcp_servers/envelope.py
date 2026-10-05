"""
HW5 Part 2B - the response envelope, defined once.

The spec: "Use one response envelope for all three tools: {ok, data, error},
where error is null on success. This is the same envelope shape you will reuse
for execute_tool in Part 4 - define it once here and carry it through."

This module is that single definition. It is imported by:

    Part 2B  transit_tools.py   every tool returns ok() or err()
    Part 3   fault_injection.py reads .ok to score success rate
    Part 4   execute_tool.py    serializes this exact shape to a JSON string
    Part 5   the safety rule returns err(...) instead of raising

Keeping it in its own module, rather than retyping the three keys in each
file, is what makes "define it once and carry it through" literally true --
and it means a future change to the envelope cannot drift between parts.

Design rules:
  * exactly three keys, always all three present
  * ok=True  -> data holds the result, error is None
  * ok=False -> data is None, error is a human-readable string
  * never raise across the envelope boundary; a failure is a value, not an
    exception. That is what lets the Part 5 agent loop keep running after a
    tool refuses a call.
"""

from __future__ import annotations

from typing import Any, TypedDict


class Envelope(TypedDict):
    """The one response shape. Every tool in Parts 2B-5 returns this."""

    ok: bool
    data: Any | None
    error: str | None


def ok(data: Any) -> Envelope:
    """A successful call. `error` is null, per the spec."""
    return {"ok": True, "data": data, "error": None}


def err(message: str) -> Envelope:
    """A refused or failed call. `data` is null and the reason is a string.

    Used for every rejection: bad input, unknown record, a violated safety
    rule. The caller inspects `ok`; it never has to catch an exception.
    """
    return {"ok": False, "data": None, "error": message}


def is_envelope(value: Any) -> bool:
    """True if `value` has exactly the envelope's three keys.

    Used by the Part 4 test runner to assert that every tool honors the
    contract, rather than trusting each one to have been written correctly.
    """
    return isinstance(value, dict) and set(value.keys()) == {"ok", "data", "error"}
