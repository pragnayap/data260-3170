"""
HW7 Part 1 - JWT bearer authentication and role-based authorization.

Replaces HW4's server-side session cookie on the graded domain routes (the
cookie implementation survives only as history at the hw4 tag; routers/auth_db.py
is no longer wired to any HW7 route's dependencies).

    POST /auth/login   username + password -> {"access_token", "token_type"}
    GET  /auth/me      the authenticated user's identity and role

Status codes
    401  missing, malformed, expired or badly signed token; bad login
    403  valid token, but the role is not allowed for this action

Login fetches the user from MySQL, verifies the PBKDF2 hash (session_crud's
scheme: per-user salt, 200k iterations, constant-time compare), and only then
signs a token. The token carries sub (username), role and exp. The role is
re-read from the database on every request, so demoting a user takes effect
immediately instead of waiting for their old token to expire.
"""

from __future__ import annotations

import datetime as dt
import os

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
import session_crud
from database import get_db

JWT_SECRET = os.environ.get("S3170_JWT_SECRET") or "s3170-dev-jwt-secret-do-not-ship"
JWT_ALGORITHM = "HS256"
JWT_LIFETIME = dt.timedelta(minutes=int(os.environ.get("S3170_JWT_MINUTES", "60")))

ROLES = ("reader", "writer", "moderator")
READ_ROLES = ROLES
WRITE_ROLES = ("writer", "moderator")
DELETE_ROLES = ("moderator",)

router = APIRouter(prefix="/auth", tags=["auth-jwt"])

# auto_error=False so a missing header becomes our 401, not HTTPBearer's 403.
_bearer = HTTPBearer(auto_error=False)


class LoginBody(BaseModel):
    username: str = ""
    password: str = ""


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    id: int
    username: str
    role: str


def create_access_token(user: models.User, lifetime: dt.timedelta = JWT_LIFETIME) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    claims = {"sub": user.username, "role": user.role, "iat": now, "exp": now + lifetime}
    return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> models.User:
    """401 unless the request carries a valid, unexpired token for a real user."""
    if creds is None:
        raise _unauthorized("Not authenticated")
    try:
        claims = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expired") from None
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid token") from None

    username = claims.get("sub")
    user = (
        db.query(models.User).filter(models.User.username == username).first()
        if username
        else None
    )
    if user is None:
        raise _unauthorized("Invalid token")
    return user


def require_roles(*allowed: str):
    """Dependency factory: authenticated (401) and in `allowed` (403)."""

    def checker(user: models.User = Depends(get_current_user)) -> models.User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{user.role}' may not do this; requires one of: {', '.join(allowed)}",
            )
        return user

    return checker


@router.post("/login", response_model=TokenOut)
def login(body: LoginBody, db: Session = Depends(get_db)):
    user = session_crud.verify_username_login(db, body.username.strip(), body.password)
    if user is None:
        # Same message for unknown user and wrong password.
        raise _unauthorized("Invalid username or password")
    return TokenOut(access_token=create_access_token(user))


@router.get("/me", response_model=MeOut)
def me(user: models.User = Depends(get_current_user)):
    return MeOut(id=user.id, username=user.username, role=user.role)
