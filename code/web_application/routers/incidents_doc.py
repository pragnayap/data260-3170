"""
HW6 Part 1.II - CRUD over the MongoDB `transit_incidents` collection.

    POST   /api/doc/incidents          201  created
    GET    /api/doc/incidents          200  list (newest first, limit/skip)
    GET    /api/doc/incidents/{id}     200 / 404 / 400 (malformed id)
    PUT    /api/doc/incidents/{id}     200 / 404 / 400 / 422
    DELETE /api/doc/incidents/{id}     204 / 404 / 400

Status codes beyond the happy path:
    400  id is not a valid 24-hex ObjectId
    404  well-formed id, no such document
    422  Pydantic rejected the body (missing field, bad enum, bad date, too long)
    503  MongoDB unreachable
    500  anything else, logged server-side and reported without internals
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query, Response
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError, WriteError

from mongo_db import get_db
from schemas_doc import IncidentCreate, IncidentOut, IncidentUpdate

log = logging.getLogger("hw6.incidents_doc")
router = APIRouter(prefix="/api/doc/incidents", tags=["hw6-mongo-incidents"])


def _now_ms() -> datetime:
    """UTC now truncated to milliseconds, which is all BSON dates store; without this the value
    returned by POST would differ from the one read back by GET."""
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def _col():
    return get_db().transit_incidents


def _oid(raw: str) -> ObjectId:
    try:
        return ObjectId(raw)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail=f"'{raw}' is not a valid incident id")


def _out(doc: dict) -> IncidentOut:
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return IncidentOut(**doc)


def _db_errors(fn):
    """Map PyMongo failures to 503/500/422 so no route leaks a stack trace."""
    from functools import wraps

    @wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except HTTPException:
            raise
        except ServerSelectionTimeoutError:
            raise HTTPException(status_code=503, detail="MongoDB is unreachable")
        except WriteError as exc:
            # Document failed the server-side $jsonSchema validator.
            raise HTTPException(status_code=422, detail=f"MongoDB validation rejected the document: {exc.code}")
        except PyMongoError:
            log.exception("MongoDB error")
            raise HTTPException(status_code=500, detail="Database error")

    return wrapper


@router.post("", response_model=IncidentOut, status_code=201)
@_db_errors
def create_incident(body: IncidentCreate):
    now = _now_ms()
    doc = body.model_dump(mode="python")
    doc["status"] = body.status.value
    doc["category"] = body.category.value
    doc["createdAt"] = now
    doc["updatedAt"] = now
    res = _col().insert_one(doc)
    doc["_id"] = res.inserted_id
    return _out(doc)


@router.get("", response_model=list[IncidentOut])
@_db_errors
def list_incidents(limit: int = Query(50, ge=1, le=500), skip: int = Query(0, ge=0)):
    cur = _col().find().sort("createdAt", -1).skip(skip).limit(limit)
    return [_out(d) for d in cur]


@router.get("/{incident_id}", response_model=IncidentOut)
@_db_errors
def get_incident(incident_id: str):
    doc = _col().find_one({"_id": _oid(incident_id)})
    if doc is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _out(doc)


@router.put("/{incident_id}", response_model=IncidentOut)
@_db_errors
def update_incident(incident_id: str, body: IncidentUpdate):
    fields = body.model_dump(mode="python")
    fields["status"] = body.status.value
    fields["category"] = body.category.value
    fields["updatedAt"] = _now_ms()  # createdAt is left untouched
    doc = _col().find_one_and_update(
        {"_id": _oid(incident_id)}, {"$set": fields}, return_document=ReturnDocument.AFTER
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _out(doc)


@router.delete("/{incident_id}", status_code=204)
@_db_errors
def delete_incident(incident_id: str):
    res = _col().delete_one({"_id": _oid(incident_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Incident not found")
    return Response(status_code=204)
