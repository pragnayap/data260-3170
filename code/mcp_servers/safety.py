"""
HW5 Part 5.I - the domain safety rule.

The spec: "Add one domain-specific safety rule inside execute_tool. When the
rule is violated, return {ok: false, data: null, error: "..."} without raising
an exception."

THE RULE
    No tool call may surface, or search by, the contact details of the member
    of the public who filed an incident report.

WHY THIS RULE, FOR THIS DOMAIN
    Every row in the incidents table carries submitter_email -- the address of
    a rider who reported a delay, a hazard or a collision. That address is
    personal data about a third party who filed a civil complaint. It is
    necessary for the transit agency to follow up, and it is necessary for
    nothing an assistant does.

    An LLM agent makes that risk concrete in a way a REST API does not. The
    agent's output goes into a chat transcript, which gets copied, pasted and
    stored; and the agent decides for itself which arguments to pass, so
    "don't ask for the email" is not something the caller controls. The rule
    has to live below the model, at the one point every tool call passes
    through.

    It blocks two distinct moves, which is why it is written as a rule rather
    than a single boolean check:

      1. ASKING FOR THE FIELD.  incident_details(..., include_submitter=True)
         returns the address outright.

      2. SEARCHING BY THE FIELD. Passing an email address as a search term is
         re-identification: "show me everything rider@example.com reported"
         builds a profile of one named person's movements and complaints from
         records that are individually unremarkable. The field is never
         searched by the tools, but the attempt is itself the signal worth
         refusing and logging.

WHAT IT DOES NOT DO
    It does not redact aggregate output, and it does not stop anyone reading
    the database directly. It is a guard on the agent's tool surface, not a
    privacy control for the whole system -- which is the honest scope to claim
    for it in the report.

The rule never raises. check_call() returns None to allow, or a string reason
to block, and execute_tool turns that string into an err() envelope.
"""

from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("transit-mcp.safety")

RULE_ID = "no-reporter-pii"
RULE_TEXT = (
    "No tool call may surface, or search by, the contact details of the "
    "member of the public who filed an incident report."
)

# Deliberately loose: it only has to recognize that an argument is being used
# as an email address, not validate one.
EMAIL_LIKE = re.compile(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}")

# Arguments that, if set, would return reporter contact details.
PII_FLAGS = ("include_submitter",)

# Arguments that carry free text a caller could put an address into.
TEXT_ARGS = ("query", "category", "group_by", "incident_code")


def check_call(name: str, inputs: dict[str, Any]) -> str | None:
    """Return None to allow the call, or a reason string to block it.

    Args:
        name: the tool about to be called.
        inputs: the arguments it is about to be called with.

    Returns:
        None if the call is allowed. Otherwise a sentence explaining the
        refusal, which execute_tool passes straight through as the envelope's
        `error`. The agent reads that sentence, so it says what was refused
        and why -- enough for the model to change course on its next turn
        rather than retrying the same call.
    """
    if not isinstance(inputs, dict):
        return None  # shape problems are execute_tool's job, not the rule's

    # 1 - asking for the field
    for flag in PII_FLAGS:
        if inputs.get(flag):
            log.warning("safety rule %s blocked %s via %s", RULE_ID, name, flag)
            return (
                f"blocked by safety rule '{RULE_ID}': {name} was called with "
                f"{flag}=True, which would return the reporter's email address. "
                "Reporter contact details are not available through this "
                "assistant. The incident itself can be returned without them."
            )

    # 2 - searching by the field
    for arg in TEXT_ARGS:
        value = inputs.get(arg)
        if isinstance(value, str) and EMAIL_LIKE.search(value):
            log.warning("safety rule %s blocked %s: email in %s", RULE_ID, name, arg)
            return (
                f"blocked by safety rule '{RULE_ID}': {name} was called with an "
                f"email address in '{arg}'. Looking up incidents by reporter "
                "identity is not permitted. Search by route, location or "
                "category instead."
            )

    return None
