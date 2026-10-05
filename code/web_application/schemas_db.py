"""HW4 Part 2 + HW5 Part 1.II - Pydantic I/O schemas for the DB-backed API.

HW5 adds:
  * full CRUD schemas for the related entity (routes): create, update, out,
    a detail view with its incident count, and a paginated page object
  * format validation on both unique fields (the `pattern=` arguments)
  * the new incident columns: incident_code, riders_affected, timestamps

A malformed unique field is rejected here, before any query runs, so it
surfaces as 422. Not-found (404) and conflict (409) are decided in the routers,
because they depend on what is already in the database.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, EmailStr, Field

# Unique-field formats. These are the patterns HW5 Part 1.II means by
# "ensure the unique field's format is validated". The seed script generates
# codes in exactly these shapes, so every seeded row passes its own schema.
ROUTE_CODE_PATTERN = r"^R-\d{4}$"              # e.g. R-0042
INCIDENT_CODE_PATTERN = r"^INC-\d{4}-\d{5}$"   # e.g. INC-3170-00001


class ErrorOut(BaseModel):
    """Shape of every 404 / 409 body: FastAPI's HTTPException `detail`."""

    detail: str


# --- related entity: Route -------------------------------------------------

class RouteBase(BaseModel):
    route_code: str = Field(
        ...,
        pattern=ROUTE_CODE_PATTERN,
        description="Unique field. Format R-NNNN, e.g. R-0042.",
    )
    route_name: str = Field(..., min_length=1, max_length=120)   # primary text field
    agency: str = Field(..., min_length=1, max_length=80)        # secondary text field
    route_type: str = Field(..., min_length=1, max_length=40)

    model_config = {"str_strip_whitespace": True}


class RouteCreate(RouteBase):
    """POST /api/routes body."""


class RouteUpdate(RouteBase):
    """PUT /api/routes/{id} body. Full replacement, same rules as create."""


class RouteOut(RouteBase):
    id: int
    created_at: dt.datetime
    updated_at: dt.datetime

    model_config = {"from_attributes": True}


class RouteDetailOut(RouteOut):
    """Single-route GET: adds the child count, which is what makes the 409 on
    DELETE predictable from the client side."""

    incident_count: int = 0


class RoutePage(BaseModel):
    items: list[RouteOut]
    total: int
    page: int
    page_size: int


# --- primary entity: Incident ----------------------------------------------

class IncidentBase(BaseModel):
    incidentCode: str = Field(
        ...,
        alias="incident_code",
        pattern=INCIDENT_CODE_PATTERN,
        description="Unique field. Format INC-NNNN-NNNNN, e.g. INC-3170-00001.",
    )
    routeId: str = Field(..., min_length=1, alias="route_id", description="Primary field")
    location: str = Field(..., min_length=1, alias="location", description="Secondary field")
    submitterEmail: EmailStr = Field(..., alias="submitter_email")
    description: str = Field(..., min_length=25)
    category: str
    ridersAffected: int = Field(
        0,
        alias="riders_affected",
        ge=0,
        description="Numeric field. Defaults to 0 when the reporter gives no estimate.",
    )
    relatedRouteId: int = Field(..., alias="related_route_id", gt=0)

    model_config = {"str_strip_whitespace": True, "populate_by_name": True}


class IncidentCreate(IncidentBase):
    pass


class IncidentUpdate(IncidentBase):
    pass


class IncidentOut(IncidentBase):
    id: int
    created_at: dt.datetime
    updated_at: dt.datetime
    route: RouteOut | None = None

    model_config = {"str_strip_whitespace": True, "populate_by_name": True, "from_attributes": True}


class IncidentPage(BaseModel):
    items: list[IncidentOut]
    total: int
    page: int
    page_size: int
    impl: str


# --- auth (unchanged from HW4) ---------------------------------------------

class SignupRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr

    model_config = {"from_attributes": True}
