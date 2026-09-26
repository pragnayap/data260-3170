"""
HW4 Part 2/3 - SQLAlchemy ORM models.

incidents.related_route_id -> routes.id is the many-to-one relationship Part 3
measures: many incidents share one of 200 route rows, so a naive list handler
that loads the route per-incident is the classic N+1 shape.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Route(Base):
    """Part 3's related test-data table (200 rows). No CRUD of its own yet."""

    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    route_name: Mapped[str] = mapped_column(String(120))
    agency: Mapped[str] = mapped_column(String(80))
    route_type: Mapped[str] = mapped_column(String(40))

    incidents: Mapped[list["Incident"]] = relationship(back_populates="route")


class Incident(Base):
    """The domain entity. route_id/location are the assignment's primary and
    secondary fields; related_route_id is the FK Part 3 measures against."""

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    route_id: Mapped[str] = mapped_column(String(80), index=True)  # primary field
    location: Mapped[str] = mapped_column(String(160), index=True)  # secondary field
    submitter_email: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), index=True)
    related_route_id: Mapped[int] = mapped_column(ForeignKey("routes.id"), index=True)

    route: Mapped["Route"] = relationship(back_populates="incidents")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))


class SessionToken(Base):
    """Server-side session authority. The cookie carries only `id`."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
