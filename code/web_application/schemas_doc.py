"""
HW6 Part 1.III - Pydantic schemas for the MongoDB incident document.

Rules enforced here (and mirrored by the $jsonSchema validator in mongo_db.py):
    routeId       required, 1-100 chars after stripping whitespace
    location      optional, <= 200 chars
    description   optional, <= 2000 chars
    status        enum, default "Open"
    category      enum, required
    occurredAt    required ISO-8601 datetime
    createdAt / updatedAt   server-set, never accepted from the client
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Status(str, Enum):
    open = "Open"
    investigating = "Investigating"
    resolved = "Resolved"


class Category(str, Enum):
    delay = "Delay"
    mechanical = "Mechanical Failure"
    accident = "Accident-Collision"
    safety = "Safety Hazard"


class IncidentBase(BaseModel):
    # extra="forbid": a typo like "stauts" is a 422, not a silently dropped field.
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    routeId: str = Field(..., min_length=1, max_length=100, description="Route identifier")
    location: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    status: Status = Status.open
    category: Category
    occurredAt: datetime


class IncidentCreate(IncidentBase):
    pass


class IncidentUpdate(IncidentBase):
    """PUT replaces the document, so the body has the same required fields."""


class IncidentOut(IncidentBase):
    id: str
    createdAt: datetime
    updatedAt: datetime

    @field_validator("id", mode="before")
    @classmethod
    def _stringify(cls, v):
        return str(v)
