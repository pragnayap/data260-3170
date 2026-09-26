"""HW4 Part 2 - Pydantic I/O schemas for the DB-backed incident/auth API."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RouteOut(BaseModel):
    id: int
    route_code: str
    route_name: str
    agency: str
    route_type: str

    model_config = {"from_attributes": True}


class IncidentBase(BaseModel):
    routeId: str = Field(..., min_length=1, alias="route_id", description="Primary field")
    location: str = Field(..., min_length=1, description="Secondary field")
    submitterEmail: EmailStr = Field(..., alias="submitter_email")
    description: str = Field(..., min_length=25)
    category: str
    relatedRouteId: int = Field(..., alias="related_route_id")

    model_config = {"str_strip_whitespace": True, "populate_by_name": True}


class IncidentCreate(IncidentBase):
    pass


class IncidentUpdate(IncidentBase):
    pass


class IncidentOut(IncidentBase):
    id: int
    route: RouteOut | None = None

    model_config = {"str_strip_whitespace": True, "populate_by_name": True, "from_attributes": True}


class IncidentPage(BaseModel):
    items: list[IncidentOut]
    total: int
    page: int
    page_size: int
    impl: str


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
