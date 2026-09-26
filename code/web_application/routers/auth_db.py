"""
HW4 Part 1/2 - email+password auth for the React client, backed by MySQL.

Distinct from HW3's auth.py (which still serves the old server-rendered
username/password login under the "s3170_session" Starlette-signed cookie).
This router issues its own opaque, unsigned cookie ("s3170_db_session") whose
value is meaningless without a matching row in the sessions table -- exactly
the "cookie carries no user data" requirement in the HW4 spec. The two auth
systems run side by side without conflicting, since they use different cookie
names and never touch each other's state.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import models
import session_crud
from database import get_db
from schemas_db import LoginRequest, SignupRequest, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])

DB_SESSION_COOKIE = "s3170_db_session"
COOKIE_HTTPS_ONLY = os.environ.get("S3170_COOKIE_INSECURE", "") != "1"
COOKIE_MAX_AGE = 60 * 60  # matches session_crud.SESSION_LIFETIME


def require_session(
    db: Session = Depends(get_db),
    s3170_db_session: str | None = Cookie(default=None),
) -> models.User:
    """FastAPI dependency: 401s any request without a live session."""
    if not s3170_db_session:
        raise HTTPException(status_code=401, detail="Login required")

    session = session_crud.get_active_session(db, s3170_db_session)
    if session is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")

    user = db.get(models.User, session.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    return user


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    try:
        user = session_crud.create_user(db, body.name, body.email, body.password)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered")
    return user


@router.post("/login", response_model=UserOut)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = session_crud.verify_login(db, body.email, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    session = session_crud.create_session(db, user.id)
    response.set_cookie(
        key=DB_SESSION_COOKIE,
        value=session.id,
        httponly=True,
        secure=COOKIE_HTTPS_ONLY,
        samesite="lax",
        max_age=COOKIE_MAX_AGE,
    )
    return user


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    db: Session = Depends(get_db),
    s3170_db_session: str | None = Cookie(default=None),
):
    if s3170_db_session:
        session_crud.delete_session(db, s3170_db_session)
    response.delete_cookie(DB_SESSION_COOKIE)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(user: models.User = Depends(require_session)):
    return user
