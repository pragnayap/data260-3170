"""
HW5 Part 1.II - full CRUD for the RELATED entity (Route), plus the
relationship query.

HW4 shipped this router read-only (one GET, to populate the React form's route
dropdown). HW5 requires the related entity to have the same endpoint set as
the primary one -- create, list with pagination, retrieve, update, delete --
plus one endpoint that returns all primary-entity records for a given related
record.

Status codes used here:
    201  record created
    204  record deleted, nothing to return
    404  route id does not exist
    409  unique field collision, or delete refused because incidents remain
    422  FastAPI/Pydantic rejected the body (bad route_code format, etc.)

Every route requires a live session, same as HW4's incident router.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

import crud
import models
from database import get_db
from routers.auth_db import require_session
from schemas_db import (
    IncidentPage,
    RouteCreate,
    RouteDetailOut,
    RouteOut,
    RoutePage,
    RouteUpdate,
)

# has a list of routes and paginated access to them

router = APIRouter(
    prefix="/api/routes",
    tags=["routes"],
    dependencies=[Depends(require_session)],
)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"


def _get_or_404(db: Session, route_id: int) -> models.Route:
    route = crud.get_route(db, route_id)
    if route is None:
        raise HTTPException(status_code=404, detail=f"Route {route_id} not found")
    return route


# --- list / retrieve 

@router.get("", response_model=RoutePage)
def list_routes(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    """Paginated list of routes.

    NOTE: HW4 returned a bare JSON array here. HW5 requires pagination, so the
    response is now {items, total, page, page_size}. The React route dropdown
    reads `.items`.
    """
    _no_store(response)
    rows, total = crud.list_routes(db, page, page_size)
    return RoutePage(items=rows, total=total, page=page, page_size=page_size)


@router.get("/{route_id}", response_model=RouteDetailOut)
def get_route(route_id: int, response: Response, db: Session = Depends(get_db)):
    _no_store(response)
    route = _get_or_404(db, route_id)
    out = RouteDetailOut.model_validate(route)
    out.incident_count = crud.count_incidents_for_route(db, route_id)
    return out


# --- the relationship query ------------------------------------------------

@router.get("/{route_id}/incidents", response_model=IncidentPage)
def incidents_for_route(
    route_id: int,
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """HW5 Part 1.II: every incident associated with one route.

    404s on an unknown route rather than returning an empty page, so the
    client can tell "no such route" apart from "route exists, no incidents".
    """
    _no_store(response)
    _get_or_404(db, route_id)

    rows, total = crud.list_incidents_for_route(db, route_id, page, page_size)
    return IncidentPage(
        items=rows, total=total, page=page, page_size=page_size, impl="fixed"
    )


# --- create / update / delete ---------------------------------------------

@router.post("", response_model=RouteOut, status_code=201)
def create_route(body: RouteCreate, response: Response, db: Session = Depends(get_db)):
    _no_store(response)
    try:
        return crud.create_route(db, body.model_dump())
    except crud.DuplicateCodeError:
        raise HTTPException(
            status_code=409,
            detail=f"route_code '{body.route_code}' already exists",
        )


@router.put("/{route_id}", response_model=RouteOut)
def update_route(
    route_id: int, body: RouteUpdate, response: Response, db: Session = Depends(get_db)
):
    _no_store(response)
    route = _get_or_404(db, route_id)
    try:
        return crud.update_route(db, route, body.model_dump())
    except crud.DuplicateCodeError:
        raise HTTPException(
            status_code=409,
            detail=f"route_code '{body.route_code}' already belongs to another route",
        )


@router.delete("/{route_id}", status_code=204)
def delete_route(route_id: int, response: Response, db: Session = Depends(get_db)):
    """Refuses with 409 while incidents still reference this route.

    No cascade is implemented: deleting a route that has incidents would
    silently destroy incident reports, which is the wrong default for an
    audit-style domain. Reassign or delete the incidents first.
    """
    _no_store(response)
    route = _get_or_404(db, route_id)
    try:
        crud.delete_route(db, route)
    except crud.RouteInUseError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Route {route_id} still has {exc.incident_count} incident(s). "
                "Delete or reassign them first (no cascade is implemented)."
            ),
        )
    return Response(status_code=204)
