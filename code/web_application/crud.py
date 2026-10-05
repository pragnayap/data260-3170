"""
HW4 Part 2/3 + HW5 Part 1.II - data access for both entities.

HW4 content kept as-is: list_incidents_naive / list_incidents_fixed are the
N+1 pair Part 3 benchmarked, and they still work the same way.

HW5 adds:
  * full CRUD for the related entity (Route)
  * list_incidents_for_route -- the relationship query endpoint's data access
  * DuplicateCodeError / RouteInUseError, so the routers can map constraint
    problems onto 409 Conflict instead of letting MySQL raise a 500
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

import models


# --- domain errors 
#
# crud/ stays free of HTTP concepts. It raises these; the routers translate
# them into status codes. That keeps the data layer reusable by the HW5
# Part 2B MCP server, which has no HTTP layer at all.

class DuplicateCodeError(Exception):
    """A unique field (route_code / incident_code) collided with an existing row."""


class RouteInUseError(Exception):
    """Delete refused: the route still has incidents pointing at it."""

    def __init__(self, route_id: int, incident_count: int) -> None:
        self.route_id = route_id
        self.incident_count = incident_count
        super().__init__(
            f"Route {route_id} still has {incident_count} incident(s); "
            "reassign or delete them first."
        )


# Incidents (primary entity)


def get_incident(db: Session, incident_id: int) -> models.Incident | None:
    return db.get(models.Incident, incident_id)


def get_incident_by_code(db: Session, code: str) -> models.Incident | None:
    return db.query(models.Incident).filter(models.Incident.incident_code == code).first()


def list_incidents_naive(db: Session, page: int, page_size: int) -> tuple[list[models.Incident], int]:
    """HW4 Part 3 baseline: one extra SELECT per row to load its route."""
    total = db.query(func.count(models.Incident.id)).scalar()
    rows = (
        db.query(models.Incident)
        .order_by(models.Incident.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    for incident in rows:
        _ = incident.route  # triggers one lazy-load query per row
    return rows, total


def list_incidents_fixed(db: Session, page: int, page_size: int) -> tuple[list[models.Incident], int]:
    """HW4 Part 3 fix: selectinload collapses the per-row lookups into one IN query."""
    total = db.query(func.count(models.Incident.id)).scalar()
    rows = (
        db.query(models.Incident)
        .options(selectinload(models.Incident.route))
        .order_by(models.Incident.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def list_incidents_for_route(
    db: Session, route_id: int, page: int, page_size: int
) -> tuple[list[models.Incident], int]:
    """HW5 Part 1.II relationship query: every incident for one route.

    Eager-loads the route for the same reason list_incidents_fixed does --
    without it, serializing N rows costs N extra SELECTs for a route we
    already know.
    """
    base = db.query(models.Incident).filter(models.Incident.related_route_id == route_id)
    total = base.with_entities(func.count(models.Incident.id)).scalar()
    rows = (
        base.options(selectinload(models.Incident.route))
        .order_by(models.Incident.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def create_incident(db: Session, data: dict) -> models.Incident:
    incident = models.Incident(**data)
    db.add(incident)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateCodeError(str(exc.orig)) from exc
    db.refresh(incident)
    return incident


def update_incident(db: Session, incident: models.Incident, data: dict) -> models.Incident:
    for key, value in data.items():
        setattr(incident, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateCodeError(str(exc.orig)) from exc
    db.refresh(incident)
    return incident


def delete_incident(db: Session, incident: models.Incident) -> None:
    db.delete(incident)
    db.commit()



# Routes (related entity) -- new in HW5 Part 1.II

def get_route(db: Session, route_id: int) -> models.Route | None:
    return db.get(models.Route, route_id)


def get_route_by_code(db: Session, code: str) -> models.Route | None:
    return db.query(models.Route).filter(models.Route.route_code == code).first()


def list_routes(db: Session, page: int, page_size: int) -> tuple[list[models.Route], int]:
    total = db.query(func.count(models.Route.id)).scalar()
    rows = (
        db.query(models.Route)
        .order_by(models.Route.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return rows, total


def count_incidents_for_route(db: Session, route_id: int) -> int:
    return (
        db.query(func.count(models.Incident.id))
        .filter(models.Incident.related_route_id == route_id)
        .scalar()
    )


def create_route(db: Session, data: dict) -> models.Route:
    route = models.Route(**data)
    db.add(route)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateCodeError(str(exc.orig)) from exc
    db.refresh(route)
    return route


def update_route(db: Session, route: models.Route, data: dict) -> models.Route:
    for key, value in data.items():
        setattr(route, key, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateCodeError(str(exc.orig)) from exc
    db.refresh(route)
    return route


def delete_route(db: Session, route: models.Route) -> None:
    """HW5 Part 1.I: refuse to delete a route that still has incidents.

    Checked here before the DELETE is issued so the caller gets a counted,
    readable error. The ON DELETE RESTRICT constraint in models.py is the
    second line of defence for anything that bypasses this function.
    """
    child_count = count_incidents_for_route(db, route.id)
    if child_count:
        raise RouteInUseError(route.id, child_count)

    db.delete(route)
    try:
        db.commit()
    except IntegrityError as exc:
        # Belt and braces: a concurrent insert could have added a child
        # between the count above and this commit.
        db.rollback()
        raise RouteInUseError(route.id, count_incidents_for_route(db, route.id)) from exc
