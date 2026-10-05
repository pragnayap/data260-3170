"""
HW4 Part 2/3 + HW5 Part 1.II - MySQL-backed incident CRUD for the PRIMARY
domain entity.

HW4 content kept: the naive/fixed list toggle (?impl=naive|fixed) that Part
3's N+1 measurement drives, and the X-SQL-Statements response header
measure_n1.py reads instead of parsing logs.

HW5 adds proper error semantics:
    404  incident id does not exist
    404  related_route_id points at a route that does not exist
    409  incident_code collides with an existing row
    422  Pydantic rejected the body (bad incident_code format, description
         under 25 chars, negative riders_affected, ...)

Every route requires a live session (require_session on the router, not just
on list), per the HW4 spec.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

import crud
import models
from database import get_db, get_query_count, reset_query_count
from routers.auth_db import require_session
from schemas_db import IncidentCreate, IncidentOut, IncidentPage, IncidentUpdate

router = APIRouter(
    prefix="/api/incidents",
    tags=["incidents"],
    dependencies=[Depends(require_session)],
)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"


def _get_or_404(db: Session, incident_id: int) -> models.Incident:
    incident = crud.get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")
    return incident


def _require_route(db: Session, related_route_id: int) -> None:
    """A create/update naming a non-existent route is a client mistake about a
    resource, not a schema violation -- so 404, not 422. Without this check
    MySQL would raise a raw foreign-key error and FastAPI would answer 500.
    """
    if crud.get_route(db, related_route_id) is None:
        raise HTTPException(
            status_code=404, detail=f"Route {related_route_id} not found"
        )


@router.get("", response_model=IncidentPage)
def list_incidents(
    response: Response,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=5000),
    impl: str = Query("fixed", pattern="^(naive|fixed)$"),
    db: Session = Depends(get_db),
):
    _no_store(response)
    reset_query_count()

    if impl == "naive":
        rows, total = crud.list_incidents_naive(db, page, page_size)
    else:
        rows, total = crud.list_incidents_fixed(db, page, page_size)

    response.headers["X-SQL-Statements"] = str(get_query_count())
    return IncidentPage(items=rows, total=total, page=page, page_size=page_size, impl=impl)


@router.get("/{incident_id}", response_model=IncidentOut)
def get_incident(incident_id: int, response: Response, db: Session = Depends(get_db)):
    _no_store(response)
    return _get_or_404(db, incident_id)


@router.post("", response_model=IncidentOut, status_code=201)
def create_incident(body: IncidentCreate, response: Response, db: Session = Depends(get_db)):
    _no_store(response)
    _require_route(db, body.relatedRouteId)
    try:
        return crud.create_incident(db, body.model_dump(by_alias=True))
    except crud.DuplicateCodeError:
        raise HTTPException(
            status_code=409,
            detail=f"incident_code '{body.incidentCode}' already exists",
        )


@router.put("/{incident_id}", response_model=IncidentOut)
def update_incident(
    incident_id: int, body: IncidentUpdate, response: Response, db: Session = Depends(get_db)
):
    _no_store(response)
    incident = _get_or_404(db, incident_id)
    _require_route(db, body.relatedRouteId)
    try:
        return crud.update_incident(db, incident, body.model_dump(by_alias=True))
    except crud.DuplicateCodeError:
        raise HTTPException(
            status_code=409,
            detail=f"incident_code '{body.incidentCode}' already belongs to another incident",
        )


@router.delete("/{incident_id}", status_code=204)
def delete_incident(incident_id: int, response: Response, db: Session = Depends(get_db)):
    _no_store(response)
    incident = _get_or_404(db, incident_id)
    crud.delete_incident(db, incident)
    return Response(status_code=204)
