"""
HW4 Part 2/3 - incident CRUD, including the naive vs. fixed list handlers
Part 3 benchmarks against each other.

list_incidents_naive loads each incident's route with a separate query inside
the loop -- the classic N+1 shape. list_incidents_fixed issues one query total
via selectinload, which is what Part 3's speed-up measurement compares against.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

import models


def get_incident(db: Session, incident_id: int) -> models.Incident | None:
    return db.get(models.Incident, incident_id)


def list_incidents_naive(db: Session, page: int, page_size: int) -> tuple[list[models.Incident], int]:
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


def create_incident(db: Session, data: dict) -> models.Incident:
    incident = models.Incident(**data)
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


def update_incident(db: Session, incident: models.Incident, data: dict) -> models.Incident:
    for key, value in data.items():
        setattr(incident, key, value)
    db.commit()
    db.refresh(incident)
    return incident


def delete_incident(db: Session, incident: models.Incident) -> None:
    db.delete(incident)
    db.commit()
