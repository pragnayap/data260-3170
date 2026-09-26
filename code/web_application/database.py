"""
HW4 Part 2 - MySQL connection setup (SQLAlchemy).

Reads DATABASE_URL from .env (see .env.example) so the real credentials never
land in the repo. The assignment requires the session-factory variable to be
named `db_session_basede26` exactly -- that requirement is honored literally
below; everywhere else in this codebase imports that name, not "SessionLocal".
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv(Path(__file__).parent / ".env")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "mysql+pymysql://root:@localhost:3306/s3170_rel",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)

# Required variable name per the HW4 spec ("Name your database connection
# variable 'db_session_basede26' strictly").
db_session_basede26 = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: one session per request, always closed."""
    db: Session = db_session_basede26()
    try:
        yield db
    finally:
        db.close()


# --- Part 3: per-request SQL statement counter -----------------------------
#
# A ContextVar rather than a plain module global so concurrent requests (async
# handlers, or ASGI's threadpool for sync ones) never share a counter.

_query_count: ContextVar[int] = ContextVar("query_count", default=0)


@event.listens_for(engine, "before_cursor_execute")
def _count_statement(conn, cursor, statement, parameters, context, executemany) -> None:
    _query_count.set(_query_count.get() + 1)


def reset_query_count() -> None:
    _query_count.set(0)


def get_query_count() -> int:
    return _query_count.get()
