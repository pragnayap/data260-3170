#!/usr/bin/env python3
"""
HW5 Part 4 - one safe entry point for every domain tool.

The spec: "Create execute_tool(name, inputs). This is the single function that
the Part 5 agent will use to call any of the three domain tools. It must reuse
the {ok, data, error} format from Part 2B, return the result as a JSON string,
and handle errors without crashing."

Why a single door at all. The Part 5 agent decides which tool to call by
emitting a name and an arguments object -- text it generated, which may name a
tool that does not exist, omit a required argument, or invent one. If the
agent called the tool functions directly, every one of those mistakes would be
a TypeError that kills the loop. Funnelling them through one function means
every possible outcome, including the agent's own errors, comes back as the
same envelope:

    {"ok": true,  "data": {...}, "error": null}
    {"ok": false, "data": null,  "error": "why it failed"}

serialized to a JSON string. execute_tool never raises. That is the property
the Part 5 loop depends on, and the Part 4 test suite asserts it directly.

What happens on the way through:

    name checked against the registry        -> unknown tool  -> ok:false
    inputs checked for shape                 -> not an object -> ok:false
    arguments bound to the signature         -> wrong args    -> ok:false
    safety.check_call (Part 5.I)             -> violation     -> ok:false
    call_with_retry (Part 3)                 -> transient     -> retried
                                             -> exhausted     -> ok:false
    tool's own validation                    -> rejected      -> ok:false
    success                                  -> ok:true

The safety rule sits after the shape checks and before the call, so a blocked
request never reaches the database.
"""

from __future__ import annotations

import inspect
import json
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from envelope import Envelope, err, is_envelope, ok  # noqa: E402
from retry import INTERACTIVE_POLICY, RetryPolicy, call_with_retry  # noqa: E402
import safety  # noqa: E402
import transit_tools  # noqa: E402

log = logging.getLogger("transit-mcp.execute")

TOOLS = transit_tools.TOOLS


# --- what the agent is told it can call ------------------------------------

def tool_catalog() -> list[dict[str, Any]]:
    """Name, purpose and parameters of each tool, for the Part 5 prompt.

    Built from the live function signatures rather than a hand-written list,
    so the catalog cannot describe a parameter the tool does not have.
    """
    catalog = []
    for name, fn in TOOLS.items():
        sig = inspect.signature(fn)
        params = []
        for pname, p in sig.parameters.items():
            params.append(
                {
                    "name": pname,
                    "type": getattr(p.annotation, "__name__", str(p.annotation)),
                    "required": p.default is inspect.Parameter.empty,
                    "default": None if p.default is inspect.Parameter.empty else p.default,
                }
            )
        summary = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else ""
        catalog.append({"name": name, "summary": summary, "parameters": params})
    return catalog


# --- the entry point -------------------------------------------------------

def execute_tool(
    name: str,
    inputs: dict[str, Any] | None = None,
    *,
    policy: RetryPolicy = INTERACTIVE_POLICY,
) -> str:
    """Call one domain tool by name. Always returns a JSON string.

    Args:
        name: "search_incidents" | "incident_details" | "incident_stats"
        inputs: the tool's arguments as a dict. None is treated as {}.
        policy: retry policy; the Part 3 interactive defaults unless overridden.

    Returns:
        json.dumps of a {ok, data, error} envelope. Never raises, never returns
        None, never returns a dict.
    """
    return json.dumps(_execute(name, inputs, policy))


def _execute(
    name: str, inputs: dict[str, Any] | None, policy: RetryPolicy
) -> Envelope:
    """The envelope-returning core. execute_tool serializes whatever this gives."""

    # --- the tool must exist ---
    if not isinstance(name, str) or name not in TOOLS:
        known = ", ".join(sorted(TOOLS))
        log.warning("unknown tool requested: %r", name)
        return err(f"unknown tool {name!r}; available tools are {known}")

    # --- inputs must be an object ---
    if inputs is None:
        inputs = {}
    if not isinstance(inputs, dict):
        return err(
            f"inputs must be a JSON object, got {type(inputs).__name__}"
        )
    if not all(isinstance(k, str) for k in inputs):
        return err("every key in inputs must be a string")

    fn = TOOLS[name]

    # --- the arguments must fit the tool's signature ---
    # sig.bind() raises TypeError for both failure modes the agent can produce:
    # an argument the tool does not have, and a required one it left out. Doing
    # this check HERE, before dispatch, is what keeps those out of the retry
    # layer -- a TypeError raised inside call_with_retry's worker thread would
    # be logged as an unexpected crash with a full traceback, which is noise,
    # not information. The agent's mistake belongs at the agent's boundary.
    signature = inspect.signature(fn)
    accepted = sorted(signature.parameters)
    unexpected = sorted(set(inputs) - set(accepted))
    if unexpected:
        return err(
            f"{name} does not accept {', '.join(unexpected)}; "
            f"valid arguments are {', '.join(accepted)}"
        )
    try:
        signature.bind(**inputs)
    except TypeError as exc:
        return err(
            f"bad arguments for {name}: {exc}; "
            f"valid arguments are {', '.join(accepted)}"
        )

    # --- Part 5.I: the domain safety rule ----------------------------------
    # Placed after the shape checks and before the call, so a blocked request
    # never reaches the database, and the refusal is a value rather than an
    # exception. safety.check_call returns None to allow, or the reason.
    violation = safety.check_call(name, inputs)
    if violation is not None:
        log.warning("safety rule blocked %s", name)
        return err(violation)
    # -----------------------------------------------------------------------

    # --- call it, with the Part 3 retry policy around it ---
    try:
        result = call_with_retry(fn, policy=policy, **inputs)
    except TypeError as exc:
        # A missing required argument lands here, since the signature check
        # above only catches arguments that should not be there.
        log.warning("bad arguments for %s: %s", name, exc)
        return err(f"bad arguments for {name}: {exc}")
    except Exception as exc:  # noqa: BLE001 - nothing escapes this function
        log.exception("unexpected failure calling %s", name)
        return err(f"{name} failed unexpectedly: {type(exc).__name__}: {exc}")

    envelope = result.envelope
    if not is_envelope(envelope):
        return err(f"{name} returned a malformed response")

    log.info(
        "execute_tool %s ok=%s attempts=%d %.1fms",
        name, envelope["ok"], result.attempt_count, result.total_ms,
    )
    return envelope


# --- manual check ----------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(levelname)s %(name)s: %(message)s")
    print("tool catalog:")
    print(json.dumps(tool_catalog(), indent=2))
    print("\nsample calls:")
    for n, i in [
        ("incident_stats", {"group_by": "category"}),
        ("incident_stats", {"group_by": "banana"}),
        ("does_not_exist", {}),
        # Part 5.I: allowed, then blocked by the safety rule.
        ("incident_details", {"incident_code": "INC-3170-00001"}),
        ("incident_details", {"incident_code": "INC-3170-00001",
                              "include_submitter": True}),
    ]:
        print(f"  {n}({i}) -> {execute_tool(n, i)[:160]}")
