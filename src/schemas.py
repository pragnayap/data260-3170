"""
HW2 Part 4 - Pydantic output schema for the Planner.

The graph validates the Planner's RAW model output against PlannerOutput. A
failure is not repaired in place: the validation error text is written back
into the state so the Planner can be re-prompted with it (Part 4.2).

This is deliberately different from HW1's coerce_reply() in agents_demo.py,
which silently repairs bad output (padding tags, truncating the summary). Run
coercion here and every run would be "valid first attempt" -- the retry loop
would never fire and the Part 4 experiments would have nothing to measure.
"""

from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field, ValidationError, field_validator

MAX_SUMMARY_WORDS = 25
TAG_MIN_CHARS = 3
TAG_MAX_CHARS = 30
REQUIRED_TAG_COUNT = 3


class PlannerOutput(BaseModel):
    """Exactly three tags of 3-30 characters each, plus a summary of <=25 words."""

    tags: List[str] = Field(..., min_length=REQUIRED_TAG_COUNT, max_length=REQUIRED_TAG_COUNT)
    summary: str

    @field_validator("tags")
    @classmethod
    def check_tag_lengths(cls, tags: List[str]) -> List[str]:
        for tag in tags:
            n = len(tag.strip())
            if n < TAG_MIN_CHARS or n > TAG_MAX_CHARS:
                raise ValueError(
                    f"tag {tag.strip()!r} is {n} characters; "
                    f"each tag must be {TAG_MIN_CHARS}-{TAG_MAX_CHARS} characters"
                )
        return tags

    @field_validator("summary")
    @classmethod
    def check_summary_length(cls, summary: str) -> str:
        n = len(summary.split())
        if n == 0:
            raise ValueError("summary is empty")
        if n > MAX_SUMMARY_WORDS:
            raise ValueError(f"summary is {n} words; must be at most {MAX_SUMMARY_WORDS}")
        return summary


class ReviewIssue(BaseModel):
    """One Reviewer objection, in the evidence-bearing form the prompt demands.

    The Reviewer is prone to bare taste objections -- returning a tag name on its
    own, with no stated fault. Those are un-actionable: the Planner rewrites, the
    Reviewer objects again, and the graph burns its turn ceiling without ever
    converging. Requiring rule + quote + problem lets malformed objections be
    dropped mechanically instead of trusting the model to follow instructions.
    """

    rule: int = Field(..., ge=1, le=3)
    quote: str = Field(..., min_length=1)
    problem: str = Field(..., min_length=10)


def parse_review_issues(raw: Any, proposal_text: str) -> Tuple[List[str], int]:
    """Keep only well-formed objections that quote text actually in the proposal.

    Returns (kept_as_strings, dropped_count). A quote the Reviewer invented is
    dropped too -- a real fault can always be pointed at.
    """
    if not isinstance(raw, list):
        return [], 0

    kept: List[str] = []
    dropped = 0
    haystack = proposal_text.lower()

    for item in raw:
        if not isinstance(item, dict):
            dropped += 1
            continue
        try:
            issue = ReviewIssue.model_validate(item)
        except ValidationError:
            dropped += 1
            continue
        if issue.quote.strip().lower() not in haystack:
            dropped += 1
            continue
        kept.append(f"[rule {issue.rule}] {issue.quote.strip()!r}: {issue.problem.strip()}")

    return kept, dropped


def format_validation_error(exc: ValidationError) -> str:
    """Flatten a ValidationError into one line per problem, for re-prompting.

    Pydantic's own str() includes URLs and input echoes that add tokens without
    helping the model, so only the field path and message are kept.
    """
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        lines.append(f"{loc}: {err['msg']}")
    return "; ".join(lines)


def validate_planner_output(obj: Any) -> Tuple[bool, Dict[str, Any], str]:
    """Validate a parsed Planner object against PlannerOutput.

    Returns (is_valid, normalized_dict, error_text). On success error_text is
    "", and normalized_dict holds the validated tags/summary. On failure
    normalized_dict is {} and error_text is the re-prompt feedback.
    """
    if not isinstance(obj, dict):
        return False, {}, f"(root): expected a JSON object, got {type(obj).__name__}"

    try:
        validated = PlannerOutput.model_validate(obj)
    except ValidationError as exc:
        return False, {}, format_validation_error(exc)

    return True, validated.model_dump(), ""
