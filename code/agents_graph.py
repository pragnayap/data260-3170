"""
HW2 Part 3 - Stateful agent graph (supervisor pattern) with LangGraph.
"""

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, TypedDict

from langgraph.graph import END, StateGraph

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO_ROOT, "src"))

from model_client import ModelClient  # noqa: E402
from schemas import parse_review_issues, validate_planner_output  # noqa: E402

# agents_demo.extract_json_block handles fenced/rambling model output. Reuse it
# rather than writing a second JSON extractor.
sys.path.insert(0, HERE)
from agents_demo import extract_json_block  # noqa: E402

DEFAULT_TURN_CEILING = 4

# Set by --force-reviewer-issue (Part 3, Step 6). Never on during experiments.
FORCE_REVIEWER_ISSUE = False

# Set by --force-schema-failure (Part 4.2 demo). Never on during experiments.
FORCE_SCHEMA_FAILURE = False


# -------------------------
# Shared state
# -------------------------

class AgentState(TypedDict):
    """Memory shared by every node. Nodes return only the keys they change."""

    # Inputs (set once, before the graph runs)
    title: str
    content: str
    email: str
    strict: bool
    task: str
    llm: Any  # ModelClient from src/model_client.py

    # Agent outputs
    planner_proposal: Dict[str, Any]
    reviewer_feedback: Dict[str, Any]

    # Loop control
    turn_count: int
    turn_ceiling: int

    # Part 4 - schema validation and retry bookkeeping
    valid: bool
    validation_error: str       # feedback for the next Planner attempt ("" if clean)
    validation_history: List[str]
    planner_attempts: int       # every Planner call, whatever sent it back
    schema_retries: int         # only the calls that FAILED Pydantic validation
    issue_history: List[str]    # every actionable Reviewer objection, in order


# -------------------------
# Nodes  (Part 3, Step 3)
# -------------------------

PLANNER_SYSTEM = (
    "You tag and summarize incident reports. Return ONLY one JSON object, no prose "
    'and no code fences, with exactly these keys: "tags" (an array of exactly 3 '
    "topical tags, each 3-30 characters, preferring multi-word phrases drawn from "
    'the input) and "summary" (at most 25 words, plain text).'
)

REVIEWER_SYSTEM = (
    "You check a tag-and-summary proposal for factual faults. Return ONLY one JSON "
    'object with the key "issues": an array of objects, each with exactly these '
    'keys: "rule" (1, 2 or 3), "quote" (the exact offending text, copied verbatim '
    'from the proposal) and "problem" (a full sentence naming the fault).\n'
    "Report an issue ONLY under one of these rules:\n"
    "  1. A tag is about a subject the input never raises -- for example a tag "
    "about fare payment when the input describes a delay.\n"
    "  2. The summary asserts a fact the input does not support.\n"
    "  3. The proposal contains markdown, code fences, or JSON syntax as text.\n"
    "Tags are meant to be topical labels, so a tag NEVER has to appear word for "
    "word in the input. 'Service Failure' for a bus that never arrived, or "
    "'Transit Center' for 'Downtown Transit Center', are both correct and must "
    "not be reported.\n"
    "Do NOT report matters of taste: wording you would have phrased differently, "
    "tags you consider too broad or too narrow, or detail you would have included. "
    "Most proposals are acceptable; an empty array is the normal answer. "
    "Do not rewrite the proposal."
)


def _parse_json_reply(raw: str) -> Any:
    """Pull a JSON object out of raw model text; return {} if there isn't one."""
    try:
        return json.loads(extract_json_block(raw))
    except (json.JSONDecodeError, TypeError):
        return {}


def planner_node(state: AgentState) -> Dict[str, Any]:
    """Propose exactly 3 tags and a <=25-word summary, then validate the result.

    The proposal is validated but never repaired: an invalid proposal stays
    invalid so the router has something to send back for correction. On a retry
    the previous validation error (and any reviewer issues) are fed back in, so
    the model corrects a specific fault instead of re-rolling the dice.
    """
    print("--- NODE: Planner ---")

    user_parts = [state["task"]]

    if state["validation_error"]:
        user_parts.append(
            "Your previous answer was rejected by schema validation:\n"
            f"{state['validation_error']}\n"
            "Return a corrected JSON object that fixes exactly that problem."
        )

    issues = (state.get("reviewer_feedback") or {}).get("issues") or []
    if issues:
        user_parts.append(
            "A reviewer raised these issues with your previous answer:\n"
            + "\n".join(f"- {i}" for i in issues)
            + "\nAddress them while keeping exactly 3 tags and a summary of at most 25 words."
        )

    messages = [
        {"role": "system", "content": PLANNER_SYSTEM},
        {"role": "user", "content": "\n\n".join(user_parts)},
    ]

    raw = state["llm"].complete(messages)
    parsed = _parse_json_reply(raw)

    # Part 4.2 demo: corrupt the FIRST attempt only, so the validator rejects it
    # and the retry path can be observed. On this input the model never actually
    # violates the schema, so without this the retry branch has nothing to show.
    if FORCE_SCHEMA_FAILURE and state["planner_attempts"] == 0 and isinstance(parsed, dict):
        parsed = dict(parsed, tags=(parsed.get("tags") or [])[:2])
        print("    [forced] first attempt truncated to 2 tags")

    ok, normalized, error = validate_planner_output(parsed)

    if ok:
        proposal = normalized
    else:
        # Keep the rejected output so the report can show what was wrong.
        proposal = parsed if isinstance(parsed, dict) else {"raw": str(raw)[:500]}

    print(f"    valid={ok}" + (f" error={error}" if error else ""))

    return {
        "planner_proposal": proposal,
        "valid": ok,
        "validation_error": error,
        "validation_history": state["validation_history"] + ([error] if error else []),
        "planner_attempts": state["planner_attempts"] + 1,
        "schema_retries": state["schema_retries"] + (0 if ok else 1),
        # Clear stale critique so the Reviewer re-runs against this new proposal.
        "reviewer_feedback": {},
    }


def reviewer_node(state: AgentState) -> Dict[str, Any]:
    """Critique a schema-valid proposal and record any issues found.

    Only content quality is judged here -- shape was already settled by the
    Pydantic validator in planner_node, so the Reviewer never sees a malformed
    proposal and does not need to re-check the tag count.
    """
    print("--- NODE: Reviewer ---")

    # Part 3, Step 6: force an objection so the correction loop can be observed.
    # A flag rather than a temporary source edit, so the demonstration is
    # reproducible and there is nothing to remember to revert.
    if FORCE_REVIEWER_ISSUE:
        forced = "[forced] Reviewer set to always object (Part 3 Step 6 loop test)."
        print("    issues=1 (forced)")
        return {
            "reviewer_feedback": {"issues": [forced], "reviewed": True, "dropped": 0},
            "issue_history": state["issue_history"] + [forced],
        }

    proposal = state["planner_proposal"]

    # Present the proposal as plain text, not json.dumps(). Serializing it put
    # braces and quotes in front of the Reviewer, which it then reported under
    # rule 3 ("contains JSON syntax as text") on every single proposal -- an
    # objection about the prompt's formatting rather than the Planner's work.
    tags = proposal.get("tags", [])
    summary = proposal.get("summary", "")
    proposal_text = "Tags: " + "; ".join(str(t) for t in tags) + f"\nSummary: {summary}"

    messages = [
        {"role": "system", "content": REVIEWER_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Input title: {state['title']}\n"
                f"Input content: {state['content']}\n\n"
                f"Proposal to review:\n{proposal_text}"
            ),
        },
    ]

    raw = state["llm"].complete(messages)
    parsed = _parse_json_reply(raw)

    raw_issues = parsed.get("issues", []) if isinstance(parsed, dict) else []
    # Quotes are checked against the field VALUES only, so an objection can only
    # cite text the Planner actually produced.
    issues, dropped = parse_review_issues(raw_issues, " ".join([*map(str, tags), str(summary)]))

    print(f"    issues={len(issues)}" + (f" (dropped {dropped} un-actionable)" if dropped else ""))

    # Always a non-empty dict, so the router can tell "reviewed, clean" apart
    # from "not reviewed yet".
    return {
        "reviewer_feedback": {"issues": issues, "reviewed": True, "dropped": dropped},
        "issue_history": state["issue_history"] + issues,
    }


# -------------------------
# Supervisor  (Part 3, Step 4)
# -------------------------

def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """Update state only -- increment the turn counter. No LLM call here."""
    turn = state["turn_count"] + 1
    print(f"--- NODE: Supervisor (turn {turn}/{state['turn_ceiling']}) ---")
    return {"turn_count": turn}


def router_logic(state: AgentState) -> str:
    """Decide the next node: "planner", "reviewer", or END.

    The ceiling is checked first and unconditionally. Any other order lets a
    proposal that keeps failing validation cycle forever, because the retry
    branch would always fire before the stop condition was consulted.
    """
    if state["turn_count"] >= state["turn_ceiling"]:
        print(f"    router -> END (hit turn ceiling {state['turn_ceiling']})")
        return END

    if not state["valid"]:
        # `valid` starts False, so distinguish "nothing has run yet" from a real
        # rejection -- otherwise the first turn of every run logs "schema
        # invalid" before the Planner has produced anything to validate.
        reason = "no proposal yet" if state["planner_attempts"] == 0 else "schema invalid"
        print(f"    router -> planner ({reason})")
        return "planner"

    feedback = state.get("reviewer_feedback") or {}
    if not feedback:
        print("    router -> reviewer (proposal not yet reviewed)")
        return "reviewer"

    if feedback.get("issues"):
        print(f"    router -> planner ({len(feedback['issues'])} reviewer issues)")
        return "planner"

    print("    router -> END (valid and reviewed clean)")
    return END


# -------------------------
# Graph assembly  (Part 3, Step 5)
# -------------------------

def build_graph():
    """Wire the nodes together and return the compiled graph.

    Both workers route back through the supervisor rather than to each other, so
    the turn counter advances on every hop and the ceiling is the single place
    the loop can terminate early.
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("reviewer", reviewer_node)

    workflow.set_entry_point("supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        router_logic,
        {"planner": "planner", "reviewer": "reviewer", END: END},
    )
    workflow.add_edge("planner", "supervisor")
    workflow.add_edge("reviewer", "supervisor")

    return workflow.compile()


# -------------------------
# Run wrapper - the interface the Part 4 harness calls
# -------------------------

def initial_state(
    title: str,
    content: str,
    email: str,
    llm: ModelClient,
    turn_ceiling: int = DEFAULT_TURN_CEILING,
    strict: bool = False,
) -> AgentState:
    """Build the starting state for one run. Every key must be present up front."""
    task = (
        f'Given input title "{title}" and content "{content}", produce exactly 3 topical tags '
        f"and a one-sentence summary in your own words. Email is {email}."
    )
    return {
        "title": title,
        "content": content,
        "email": email,
        "strict": strict,
        "task": task,
        "llm": llm,
        "planner_proposal": {},
        "reviewer_feedback": {},
        "turn_count": 0,
        "turn_ceiling": turn_ceiling,
        "valid": False,
        "validation_error": "",
        "validation_history": [],
        "planner_attempts": 0,
        "schema_retries": 0,
        "issue_history": [],
    }


def run_graph(
    title: str,
    content: str,
    email: str = "student@example.com",
    turn_ceiling: int = DEFAULT_TURN_CEILING,
    llm: ModelClient = None,
    graph=None,
) -> Dict[str, Any]:
    """Run the graph once and return the final state plus timing.

    The experiment harness reuses one ModelClient and one compiled graph across
    all runs so Ollama keeps qwen3:8b resident -- a cold call costs ~26s against
    ~9s warm, so building these per run would quadruple the experiment time.
    """
    llm = llm or ModelClient(temperature=0.0)
    graph = graph if graph is not None else build_graph()

    state = initial_state(title, content, email, llm, turn_ceiling)

    t0 = time.time()
    final_state = graph.invoke(state, {"recursion_limit": 2 * turn_ceiling + 10})
    latency_ms = int((time.time() - t0) * 1000)

    proposal = final_state.get("planner_proposal") or {}
    feedback = final_state.get("reviewer_feedback") or {}
    issues = feedback.get("issues", [])

    valid = bool(final_state.get("valid"))          # schema-valid
    reviewed_clean = bool(feedback) and not issues
    succeeded = valid and reviewed_clean            # finished the way it should

    return {
        "valid": valid,
        "reviewed_clean": reviewed_clean,
        "succeeded": succeeded,
        "planner_attempts": final_state.get("planner_attempts", 0),
        "schema_retries": final_state.get("schema_retries", 0),
        "turn_count": final_state.get("turn_count", 0),
        "turn_ceiling": turn_ceiling,
        "hit_ceiling": final_state.get("turn_count", 0) >= turn_ceiling and not succeeded,
        "tags": proposal.get("tags", []),
        "summary": proposal.get("summary", ""),
        "validation_history": final_state.get("validation_history", []),
        "issue_history": final_state.get("issue_history", []),
        "reviewer_issues": issues,
        "latency_ms": latency_ms,
    }


# -------------------------
# CLI entrypoint
# -------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", default="Delayed Line 22 bus at Downtown Transit Center")
    ap.add_argument(
        "--content",
        default="The 7:15am bus never arrived and riders waited 40 minutes with no announcement.",
    )
    ap.add_argument("--email", default="student@example.com")
    ap.add_argument("--turn-ceiling", type=int, default=DEFAULT_TURN_CEILING)
    ap.add_argument("--stream", action="store_true", help="print each node's state update")
    ap.add_argument("--force-reviewer-issue", action="store_true",
                    help="Part 3 Step 6: make the Reviewer always object, to watch the "
                         "graph route back to the Planner until the ceiling stops it")
    ap.add_argument("--force-schema-failure", action="store_true",
                    help="Part 4.2: corrupt the first Planner output so Pydantic rejects "
                         "it, to watch the validation error fed back and corrected")
    args = ap.parse_args()

    global FORCE_REVIEWER_ISSUE, FORCE_SCHEMA_FAILURE
    FORCE_REVIEWER_ISSUE = args.force_reviewer_issue
    FORCE_SCHEMA_FAILURE = args.force_schema_failure

    llm = ModelClient(temperature=0.0)
    graph = build_graph()

    if args.stream:
        # Part 3, Step 6 - watch the path the graph takes node by node.
        state = initial_state(args.title, args.content, args.email, llm, args.turn_ceiling)
        for step in graph.stream(state, {"recursion_limit": 2 * args.turn_ceiling + 10}):
            for node, update in step.items():
                printable = {k: v for k, v in (update or {}).items() if k != "llm"}
                print(f"\n[{node}] {json.dumps(printable, indent=2, default=str)}")
    else:
        result = run_graph(
            args.title, args.content, args.email, args.turn_ceiling, llm=llm, graph=graph
        )
        print(json.dumps(result, indent=2))

    llm.print_exit_summary()


if __name__ == "__main__":
    main()
