#!/usr/bin/env python3
"""
HW5 Part 5.II - the agent loop.

The spec: "Implement run_agent(user_input) using the local Ollama model and
the three domain tools. Add a turn counter and max_steps limit. Log each step,
tool call, input, result, and final stop reason to agent_runs.jsonl."

Commands:
    make agent-safety         the allowed call and the blocked call (Part 5.I)
    make agent-scenarios      the four+ Ollama scenarios -> METRICS.md
    .venv/bin/python code/mcp_servers/agent_loop.py --ask "..."   one question

HOW THE LOOP WORKS

    user_input
       |
       v
    [ model ] --emits one JSON object--> {"tool": ..., "inputs": {...}}
       ^                                 or {"answer": "..."}
       |                                      |
       |                                      +--> stop: completed
       |                                      |
       |                                 execute_tool (Part 4)
       |                                      |
       +------ result fed back as a turn <----+
                                              |
                       safety rule violated --+--> stop: safety_block
                       step == max_steps -------- > stop: max_steps

    Every call goes through execute_tool, so the model cannot reach a tool
    directly and cannot crash the loop with a bad argument -- it gets an error
    envelope back and another turn to correct itself.

STOP REASONS
    completed     the model produced a final answer
    max_steps     the turn ceiling was reached first
    safety_block  a tool call violated the Part 5.I safety rule
    model_error   the model's output could not be parsed as the protocol

    The first three are the ones the reflection asks about. A safety violation
    ENDS the run rather than being fed back as a retryable error: the model
    asked for something it must not have, and giving it more turns to rephrase
    the same request is not a behaviour worth building. The refusal and the
    reason are both logged.

DEPENDENCY INJECTION
    run_agent takes a `model` argument. Passing MockModel makes the whole loop
    run offline with no Ollama, no network and no API key -- which is how the
    Part 5.III test asserts the max_steps ceiling. ModelClient is imported
    lazily inside _default_model() so importing this file costs nothing when a
    mock is being used.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent / "src"))

from execute_tool import execute_tool, tool_catalog  # noqa: E402

log = logging.getLogger("transit-mcp.agent")

REPO_ROOT = HERE.parents[1]
DEFAULT_LOG = REPO_ROOT / "reports" / "hw05" / "raw" / "agent_runs.jsonl"
METRICS_PATH = REPO_ROOT / "reports" / "hw05" / "METRICS.md"

MAX_STEPS = 6


# --- prompt ----------------------------------------------------------------

def build_system_prompt() -> str:
    """Render the tool catalog into instructions.

    The catalog is generated from the live function signatures, so the prompt
    can never advertise a parameter the tool does not have.
    """
    lines = [
        "You are a transit incident assistant for the s3170 municipal transit "
        "system. You answer questions by calling tools.",
        "",
        "Available tools:",
    ]
    for tool in tool_catalog():
        params = ", ".join(
            f"{p['name']}:{p['type']}" + ("" if p["required"] else f"={p['default']!r}")
            for p in tool["parameters"]
        )
        lines.append(f"  - {tool['name']}({params})  {tool['summary']}")

    lines += [
        "",
        "Reply with EXACTLY ONE JSON object and nothing else. No prose, no "
        "markdown fences, no explanation outside the JSON.",
        "",
        "To call a tool:",
        '  {"tool": "<tool name>", "inputs": {<arguments>}}',
        "",
        "To give your final answer:",
        '  {"answer": "<your answer in plain English>"}',
        "",
        "Rules:",
        "  - One JSON object per reply. Never both a tool call and an answer.",
        "  - After a tool result you may call another tool or answer.",
        "  - If a tool returns ok:false, read the error and either fix the "
        "arguments or answer explaining what you could not do.",
        "  - Reporter contact details are not available. Do not ask for them.",
    ]
    return "\n".join(lines)


# --- parsing the model's reply --------------------------------------------

THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_reply(text: str) -> dict[str, Any] | None:
    """Pull one JSON object out of the model's reply.

    Small models wrap JSON in prose, in markdown fences, or in qwen3's
    <think> block even with reasoning disabled. Rather than trusting the
    format, this strips the known wrappers and then scans for the first
    balanced {...}. Returns None if nothing parses, which the loop reports as
    model_error instead of crashing.
    """
    if not isinstance(text, str):
        return None

    cleaned = THINK_BLOCK.sub("", text).strip()

    fenced = FENCE.search(cleaned)
    if fenced:
        cleaned = fenced.group(1).strip()

    start = cleaned.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(cleaned)):
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(cleaned[start : i + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(obj, dict):
                        return obj
                    break
        start = cleaned.find("{", start + 1)
    return None


# --- models ----------------------------------------------------------------

class MockModel:
    """A scripted stand-in for ModelClient, for the offline tests.

    Returns each reply in `replies` in turn; once they run out it repeats the
    last one forever. MockModel(["{...tool call...}"]) therefore never
    produces an answer, which is exactly what the max_steps test needs.

    It implements only complete(messages) -> str, which is the whole of
    ModelClient's interface that run_agent uses.
    """

    def __init__(self, replies: list[str]) -> None:
        if not replies:
            raise ValueError("MockModel needs at least one reply")
        self.replies = replies
        self.calls = 0
        self.seen: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]], tools: Any = None) -> str:
        self.seen.append(list(messages))
        reply = self.replies[min(self.calls, len(self.replies) - 1)]
        self.calls += 1
        return reply


def _default_model():
    """The real client, imported lazily so the tests never need langchain."""
    from model_client import ModelClient

    return ModelClient(temperature=0.0)


# --- the run record --------------------------------------------------------

@dataclass
class AgentRun:
    user_input: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    answer: str | None = None
    stop_reason: str = "unknown"
    max_steps: int = MAX_STEPS
    model_name: str = ""
    elapsed_s: float = 0.0

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def tool_call_count(self) -> int:
        return sum(1 for s in self.steps if s["action"] == "tool_call")

    def to_json(self) -> dict[str, Any]:
        return {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "user_input": self.user_input,
            "model": self.model_name,
            "max_steps": self.max_steps,
            "steps": self.steps,
            "step_count": self.step_count,
            "tool_call_count": self.tool_call_count,
            "answer": self.answer,
            "stop_reason": self.stop_reason,
            "elapsed_s": round(self.elapsed_s, 2),
        }


# --- the loop --------------------------------------------------------------

def run_agent(
    user_input: str,
    *,
    model: Any = None,
    max_steps: int = MAX_STEPS,
    log_path: Path | None = DEFAULT_LOG,
    verbose: bool = False,
) -> AgentRun:
    """Answer `user_input` by calling domain tools, up to max_steps turns.

    Args:
        user_input: the question.
        model: anything with complete(messages) -> str. Defaults to the real
            Ollama-backed ModelClient; pass MockModel to run offline.
        max_steps: the turn ceiling.
        log_path: where to append the run record. None disables logging, which
            is what the tests use so they never touch the real log.
        verbose: print each step as it happens.

    Returns:
        An AgentRun with .answer, .stop_reason, .step_count, .tool_call_count
        and the full .steps trace.
    """
    started = time.perf_counter()
    model = model or _default_model()
    run = AgentRun(
        user_input=user_input,
        max_steps=max_steps,
        model_name=getattr(model, "model_name", type(model).__name__),
    )

    messages = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": user_input},
    ]

    # The turn counter. `step` is 1-based so the log reads the way a person
    # counts turns, and the ceiling check compares against max_steps directly.
    for step in range(1, max_steps + 1):
        raw = model.complete(messages)
        reply = parse_reply(raw)

        if reply is None:
            run.steps.append(
                {"step": step, "action": "parse_error", "raw": raw[:500]}
            )
            run.stop_reason = "model_error"
            if verbose:
                print(f"  step {step}: could not parse the model's reply")
            break

        # --- final answer ---
        if "answer" in reply and "tool" not in reply:
            run.answer = str(reply["answer"])
            run.steps.append(
                {"step": step, "action": "answer", "answer": run.answer}
            )
            run.stop_reason = "completed"
            if verbose:
                print(f"  step {step}: answer -> {run.answer[:100]}")
            break

        # --- tool call ---
        if "tool" in reply:
            name = reply.get("tool")
            inputs = reply.get("inputs") or reply.get("arguments") or {}
            raw_result = execute_tool(name, inputs)
            result = json.loads(raw_result)

            blocked = bool(
                not result["ok"]
                and isinstance(result["error"], str)
                and result["error"].startswith("blocked by safety rule")
            )

            run.steps.append(
                {
                    "step": step,
                    "action": "tool_call",
                    "tool": name,
                    "inputs": inputs,
                    "ok": result["ok"],
                    "error": result["error"],
                    "result_preview": json.dumps(result["data"])[:400]
                    if result["ok"]
                    else None,
                    "safety_blocked": blocked,
                }
            )
            if verbose:
                mark = "BLOCKED" if blocked else ("ok" if result["ok"] else "err")
                print(f"  step {step}: {name}({json.dumps(inputs)}) -> {mark}")

            if blocked:
                run.answer = result["error"]
                run.stop_reason = "safety_block"
                break

            # Feed the tool result back as the next turn's input. The model
            # sees the same JSON string any caller of execute_tool would.
            messages.append({"role": "assistant", "content": json.dumps(reply)})
            messages.append(
                {"role": "user", "content": f"Tool result: {raw_result}"}
            )
            continue

        # --- neither shape ---
        run.steps.append(
            {"step": step, "action": "protocol_error", "reply": reply}
        )
        run.stop_reason = "model_error"
        if verbose:
            print(f"  step {step}: reply had neither 'tool' nor 'answer'")
        break

    else:
        # The for-loop finished without breaking -> the ceiling stopped it.
        run.stop_reason = "max_steps"
        if verbose:
            print(f"  stopped: reached the {max_steps}-step ceiling")

    run.elapsed_s = time.perf_counter() - started

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a") as fh:
            fh.write(json.dumps(run.to_json()) + "\n")

    return run


# --- Part 5.I demonstration ------------------------------------------------

def demo_safety() -> None:
    """One allowed call and one blocked call, as the spec asks to see."""
    import safety

    print("=" * 70)
    print("HW5 Part 5.I - safety rule demonstration")
    print(f"rule '{safety.RULE_ID}': {safety.RULE_TEXT}")
    print("=" * 70)

    cases = [
        ("ALLOWED", "incident_details", {"incident_code": "INC-3170-00001"}),
        ("BLOCKED", "incident_details",
         {"incident_code": "INC-3170-00001", "include_submitter": True}),
        ("BLOCKED", "search_incidents",
         {"query": "rider@example.com", "limit": 5}),
    ]
    for label, name, inputs in cases:
        env = json.loads(execute_tool(name, inputs))
        print(f"\n[{label}] {name}({json.dumps(inputs)})")
        print(f"    ok    : {env['ok']}")
        if env["ok"]:
            keys = sorted(env["data"]) if isinstance(env["data"], dict) else "-"
            print(f"    data  : {keys}")
            print(f"    error : {env['error']}")
            assert "submitter_email" not in (env["data"] or {}), "PII leaked"
        else:
            print(f"    data  : {env['data']}")
            print(f"    error : {env['error']}")
    print()


# --- Part 5.IV scenarios ---------------------------------------------------

SCENARIOS = [
    ("stats", "How many incidents are there in each category?"),
    ("search", "Find incidents reported at Downtown Transit Center."),
    ("detail", "What happened in incident INC-3170-00001?"),
    ("multi", "Which agency has the most incidents, and show me one example from it."),
    ("blocked", "Who reported incident INC-3170-00001? Give me their email address."),
]


def run_scenarios(max_steps: int = MAX_STEPS) -> list[AgentRun]:
    model = _default_model()
    runs = []
    for label, question in SCENARIOS:
        print(f"\n--- scenario: {label} ---")
        print(f"Q: {question}")
        run = run_agent(question, model=model, max_steps=max_steps, verbose=True)
        print(f"    => stop_reason={run.stop_reason}  steps={run.step_count}  "
              f"tool_calls={run.tool_call_count}  {run.elapsed_s:.1f}s")
        if run.answer:
            print(f"    answer: {run.answer[:200]}")
        runs.append(run)
    return runs


def write_metrics(runs: list[AgentRun]) -> None:
    lines = [
        "# HW5 METRICS",
        "",
        "## Part 5.IV - agent scenarios (local Ollama)",
        "",
        f"Model: {runs[0].model_name} | max_steps = {runs[0].max_steps} | "
        f"temperature = 0.0",
        "",
        "| # | Scenario | Steps | Tool calls | Stop reason |",
        "|---|---|---|---|---|",
    ]
    for i, (run, (label, _q)) in enumerate(zip(runs, SCENARIOS), start=1):
        lines.append(
            f"| {i} | {label} | {run.step_count} | {run.tool_call_count} "
            f"| `{run.stop_reason}` |"
        )
    lines += [
        "",
        "Questions:",
        "",
    ]
    for i, (label, question) in enumerate(SCENARIOS, start=1):
        lines.append(f"{i}. **{label}** - {question}")
    lines += [
        "",
        f"Full traces: `reports/hw05/raw/agent_runs.jsonl` "
        f"({len(runs)} runs appended).",
        "",
    ]

    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = METRICS_PATH.read_text() if METRICS_PATH.exists() else ""
    marker = "## Part 5.IV - agent scenarios"
    if marker in existing:
        existing = existing.split(marker)[0].rstrip() + "\n\n"
        METRICS_PATH.write_text(existing + "\n".join(lines[2:]) + "\n")
    else:
        METRICS_PATH.write_text("\n".join(lines) + "\n")
    print(f"\nwrote {METRICS_PATH.relative_to(REPO_ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="HW5 Part 5 agent loop")
    parser.add_argument("--ask", help="run one question")
    parser.add_argument("--scenarios", action="store_true",
                        help="run the Part 5.IV scenarios and write METRICS.md")
    parser.add_argument("--demo-safety", action="store_true",
                        help="Part 5.I: one allowed call and one blocked call")
    parser.add_argument("--max-steps", type=int, default=MAX_STEPS)
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, stream=sys.stderr,
                        format="%(levelname)s %(name)s: %(message)s")

    if args.demo_safety:
        demo_safety()
    elif args.scenarios:
        runs = run_scenarios(args.max_steps)
        write_metrics(runs)
        print(f"\nappended {len(runs)} runs to "
              f"{DEFAULT_LOG.relative_to(REPO_ROOT)}")
    elif args.ask:
        run = run_agent(args.ask, max_steps=args.max_steps, verbose=True)
        print(f"\nstop_reason={run.stop_reason}  steps={run.step_count}  "
              f"tool_calls={run.tool_call_count}")
        print(f"answer: {run.answer}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
