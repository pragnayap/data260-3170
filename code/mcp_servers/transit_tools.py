"""
HW5 Part 2B - the three domain tools, as plain Python.

This file holds the logic; transit_server.py is a thin FastMCP wrapper over
it. The split matters: Part 4's execute_tool() has to call these three
functions directly, with no MCP process, no STDIO and no network, so the
offline test suite can run them. If the logic lived inside the @mcp.tool()
decorators it would only be reachable through a running server.

    transit_tools.py   <- logic, pure Python, returns envelopes
         |
         +-- transit_server.py   MCP/STDIO wrapper (Part 2B, Inspector)
         +-- execute_tool.py     single entry point   (Parts 4 and 5)

The three tools the spec asks for:
    search    ->  search_incidents()
    detail    ->  incident_details()
    aggregate ->  incident_stats()

Every one returns the {ok, data, error} envelope from envelope.py. None of
them raises; a bad argument comes back as ok=False with a readable reason,
which is what Part 3 documents as the "rejected call" for each tool.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any

# The app's models/session factory live in code/web_application. Adding that
# directory to sys.path is the same trick seed_hw05.py uses, and it means
# database.py's load_dotenv() still resolves .env relative to itself.
APP_DIR = Path(__file__).resolve().parent.parent / "web_application"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from sqlalchemy import func  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

import crud  # noqa: E402
import models  # noqa: E402
from database import db_session_basede26  # noqa: E402

from envelope import Envelope, err, ok  # noqa: E402

# STDIO servers must never write to stdout -- it corrupts the JSON-RPC stream.
# Every log line in this process goes to stderr. See transit_server.py, which
# configures the handler; this module only asks for the logger.
log = logging.getLogger("transit-mcp.tools")

INCIDENT_CODE_RE = re.compile(r"^INC-\d{4}-\d{5}$")

SEARCH_LIMIT_MAX = 50
VALID_GROUP_BY = ("category", "agency", "route_type")


# --- shaping ---------------------------------------------------------------

def _summary(incident: models.Incident) -> dict[str, Any]:
    """Compact form used by search results.

    submitter_email is deliberately absent. It is personal data belonging to
    whoever filed the report, and a search result has no need of it -- this is
    the field the Part 5 safety rule exists to protect.
    """
    return {
        "incident_code": incident.incident_code,
        "route_id": incident.route_id,
        "location": incident.location,
        "category": incident.category,
        "riders_affected": incident.riders_affected,
        "route_name": incident.route.route_name if incident.route else None,
    }


def _detail(incident: models.Incident, include_submitter: bool) -> dict[str, Any]:
    record = {
        "incident_code": incident.incident_code,
        "route_id": incident.route_id,
        "location": incident.location,
        "description": incident.description,
        "category": incident.category,
        "riders_affected": incident.riders_affected,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
        "route": {
            "route_code": incident.route.route_code,
            "route_name": incident.route.route_name,
            "agency": incident.route.agency,
            "route_type": incident.route.route_type,
        }
        if incident.route
        else None,
    }
    if include_submitter:
        record["submitter_email"] = incident.submitter_email
    return record


# --- tool 1: search --------------------------------------------------------

def search_incidents(query: str, limit: int = 10, category: str = "") -> Envelope:
    """Substring search over route_id and location, optionally filtered by category.

    Input : query str (1-120 chars), limit int (1-50), category str (optional)
    Output: {"query", "count", "results": [ {incident_code, route_id, location,
             category, riders_affected, route_name} ]}

    Rejects: empty query, limit outside 1-50.
    """
    if not isinstance(query, str) or not query.strip():
        return err("query must be a non-empty string")
    if len(query) > 120:
        return err("query must be 120 characters or fewer")
    if not isinstance(limit, int) or isinstance(limit, bool):
        return err("limit must be an integer")
    if not 1 <= limit <= SEARCH_LIMIT_MAX:
        return err(f"limit must be between 1 and {SEARCH_LIMIT_MAX} (got {limit})")

    term = f"%{query.strip()}%"
    db = db_session_basede26()
    try:
        q = (
            db.query(models.Incident)
            .options(selectinload(models.Incident.route))
            .filter(
                models.Incident.route_id.like(term) | models.Incident.location.like(term)
            )
        )
        if category:
            q = q.filter(models.Incident.category == category)

        rows = q.order_by(models.Incident.id).limit(limit).all()
        log.info("search_incidents query=%r limit=%d -> %d rows", query, limit, len(rows))
        return ok(
            {
                "query": query,
                "count": len(rows),
                "results": [_summary(r) for r in rows],
            }
        )
    except Exception as exc:  # noqa: BLE001 - the envelope is the error channel
        log.exception("search_incidents failed")
        return err(f"database error: {exc}")
    finally:
        db.close()


# --- tool 2: detail lookup -------------------------------------------------

def incident_details(incident_code: str, include_submitter: bool = False) -> Envelope:
    """Full record for one incident, looked up by its unique code.

    Input : incident_code str matching INC-NNNN-NNNNN, include_submitter bool
    Output: {incident_code, route_id, location, description, category,
             riders_affected, created_at, route:{...}}

    Rejects: malformed code, unknown code.

    include_submitter adds the reporter's email address. It defaults to False
    and the Part 5 safety rule refuses to pass True -- this argument is the
    allowed/blocked pair that demonstrates the rule.
    """
    if not isinstance(incident_code, str) or not INCIDENT_CODE_RE.match(incident_code):
        return err(
            f"incident_code must match INC-NNNN-NNNNN (got {incident_code!r})"
        )

    db = db_session_basede26()
    try:
        incident = (
            db.query(models.Incident)
            .options(selectinload(models.Incident.route))
            .filter(models.Incident.incident_code == incident_code)
            .first()
        )
        if incident is None:
            log.info("incident_details miss code=%s", incident_code)
            return err(f"no incident found with code {incident_code}")

        log.info("incident_details hit code=%s submitter=%s", incident_code, include_submitter)
        return ok(_detail(incident, include_submitter))
    except Exception as exc:  # noqa: BLE001
        log.exception("incident_details failed")
        return err(f"database error: {exc}")
    finally:
        db.close()


# --- tool 3: aggregate -----------------------------------------------------

def incident_stats(group_by: str = "category") -> Envelope:
    """Counts and rider impact, grouped one of three ways.

    Input : group_by str, one of "category" | "agency" | "route_type"
    Output: {"group_by", "total_incidents", "groups": [ {group, incidents,
             total_riders_affected, avg_riders_affected} ]}

    Rejects: any other group_by value.

    "agency" and "route_type" are columns on the routes table, so those two
    join through the foreign key -- the aggregate exercises the relationship,
    not just one table.
    """
    if group_by not in VALID_GROUP_BY:
        return err(
            f"group_by must be one of {', '.join(VALID_GROUP_BY)} (got {group_by!r})"
        )

    db = db_session_basede26()
    try:
        if group_by == "category":
            column = models.Incident.category
            q = db.query(
                column.label("g"),
                func.count(models.Incident.id).label("n"),
                func.sum(models.Incident.riders_affected).label("riders"),
            ).group_by(column)
        else:
            column = getattr(models.Route, group_by)
            q = (
                db.query(
                    column.label("g"),
                    func.count(models.Incident.id).label("n"),
                    func.sum(models.Incident.riders_affected).label("riders"),
                )
                .join(models.Route, models.Incident.related_route_id == models.Route.id)
                .group_by(column)
            )

        rows = q.order_by(func.count(models.Incident.id).desc()).all()
        groups = [
            {
                "group": r.g,
                "incidents": int(r.n),
                "total_riders_affected": int(r.riders or 0),
                "avg_riders_affected": round(float(r.riders or 0) / r.n, 1) if r.n else 0.0,
            }
            for r in rows
        ]
        total = sum(g["incidents"] for g in groups)
        log.info("incident_stats group_by=%s -> %d groups", group_by, len(groups))
        return ok({"group_by": group_by, "total_incidents": total, "groups": groups})
    except Exception as exc:  # noqa: BLE001
        log.exception("incident_stats failed")
        return err(f"database error: {exc}")
    finally:
        db.close()


# The registry Part 4's execute_tool() dispatches through. Keeping it here,
# next to the functions, means adding a tool is a one-line change in one file.
TOOLS = {
    "search_incidents": search_incidents,
    "incident_details": incident_details,
    "incident_stats": incident_stats,
}
