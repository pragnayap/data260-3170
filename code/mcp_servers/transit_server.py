#!/usr/bin/env python3
"""
HW5 Part 2B - the domain MCP server.

A FastMCP server over the s3170 municipal-transit data, exposing exactly the
three tools the spec asks for: search, detail lookup, and one aggregate. All
three return the {ok, data, error} envelope defined in envelope.py.

Run it in the Inspector (from the repo root):

    .venv/bin/mcp dev code/mcp_servers/transit_server.py

The Inspector opens in your browser. For each of the three tools make one
successful call and one intentionally invalid call, and screenshot both --
those rejected calls are what Part 3 documents, so capture them cleanly the
first time rather than re-running later.

Suggested calls for the screenshots:

  search_incidents    ok   query="Downtown", limit=5
                      bad  query="Downtown", limit=0        -> limit out of range
  incident_details    ok   incident_code="INC-3170-00001"
                      bad  incident_code="INC-317-1"        -> malformed code
  incident_stats      ok   group_by="agency"
                      bad  group_by="banana"                -> not an allowed value

LOGGING RULE (the one that breaks STDIO servers):
    stdout carries the JSON-RPC stream. Anything printed there corrupts it and
    the Inspector disconnects with a parse error. So this file configures
    logging to stderr before anything else runs, and contains no print()
    calls at all.
"""

from __future__ import annotations

import logging
import sys

# Configure logging BEFORE importing anything that might log. stream=sys.stderr
# is the whole point: the default for basicConfig is also stderr, but stating
# it explicitly documents the constraint for anyone reading the file.
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("transit-mcp")

from mcp.server.fastmcp import FastMCP  # noqa: E402

import transit_tools  # noqa: E402
from envelope import Envelope  # noqa: E402

mcp = FastMCP("s3170-transit")


@mcp.tool()
def search_incidents(query: str, limit: int = 10, category: str = "") -> Envelope:
    """Search transit incidents by route or location.

    Args:
        query: text to match against the route name or the stop/station.
        limit: how many results to return, 1-50.
        category: optional exact filter -- Delay, Mechanical Failure,
            Accident-Collision or Safety Hazard.

    Returns the {ok, data, error} envelope. On success, data holds
    {query, count, results[]}.
    """
    return transit_tools.search_incidents(query=query, limit=limit, category=category)


@mcp.tool()
def incident_details(incident_code: str, include_submitter: bool = False) -> Envelope:
    """Look up one incident by its unique code, e.g. INC-3170-00001.

    Args:
        incident_code: the unique code, format INC-NNNN-NNNNN.
        include_submitter: include the reporter's email address. Off by
            default; the Part 5 safety rule refuses to turn it on.

    Returns the {ok, data, error} envelope. On success, data holds the full
    record including its route.
    """
    return transit_tools.incident_details(
        incident_code=incident_code, include_submitter=include_submitter
    )


@mcp.tool()
def incident_stats(group_by: str = "category") -> Envelope:
    """Aggregate incident counts and rider impact.

    Args:
        group_by: one of "category", "agency" or "route_type". The last two
            join through to the routes table.

    Returns the {ok, data, error} envelope. On success, data holds
    {group_by, total_incidents, groups[]}.
    """
    return transit_tools.incident_stats(group_by=group_by)


if __name__ == "__main__":
    log.info("s3170-transit MCP server starting on STDIO (3 tools)")
    mcp.run()  # transport="stdio" is the default
