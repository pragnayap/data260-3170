"""Route-id helpers for the transit-incident domain.

HW6 Part 4.4: a function written to follow AGENT.md, checked by check_agent_compliance.py.
"""

import logging

import pytest

logger = logging.getLogger(__name__)


def normalize_route_id(raw: str) -> str:
    """Return the canonical form of a route id: upper-case, single spaces, no outer whitespace.

    Raises ValueError if the input is empty or only whitespace.
    """
    words = raw.split()
    if not words:
        raise ValueError("route id must not be empty")
    canonical = " ".join(words).upper()
    logger.debug("normalized %r -> %r", raw, canonical)
    return canonical


def test_normalize_route_id():
    """Covers the spec example, tabs/newlines, an already-canonical id and the empty cases."""
    assert normalize_route_id("  line   22 ") == "LINE 22"
    assert normalize_route_id("bart\tred\nline") == "BART RED LINE"
    assert normalize_route_id("LINE 22") == "LINE 22"
    for bad in ("", "   ", "\t\n"):
        with pytest.raises(ValueError):
            normalize_route_id(bad)
