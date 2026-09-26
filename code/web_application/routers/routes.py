"""HW4 - read-only listing of the routes table, for the React create/update forms."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import models
from database import get_db
from routers.auth_db import require_session
from schemas_db import RouteOut

router = APIRouter(prefix="/api/routes", tags=["routes"], dependencies=[Depends(require_session)])


@router.get("", response_model=list[RouteOut])
def list_routes(db: Session = Depends(get_db)):
    return db.query(models.Route).order_by(models.Route.route_name).all()
