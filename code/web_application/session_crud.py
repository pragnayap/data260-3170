"""
HW4 Part 2 - user + server-side session CRUD.

Password hashing reuses HW3's scheme (PBKDF2-HMAC-SHA256, 200k iterations,
per-user salt), packed as "salt_hex$hash_hex" into the single password_hash
column the spec asks for. The session token is opaque and random; the cookie
never carries anything but that token, and every lookup goes through the
sessions table, so revoking a row is what makes logout real.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets

from sqlalchemy.orm import Session as OrmSession

import models

PBKDF2_ITERATIONS = 200_000
SESSION_LIFETIME = dt.timedelta(hours=1)


def _hash_password(password: str, salt_hex: str) -> str:
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ITERATIONS
    )
    return derived.hex()


def create_user(db: OrmSession, name: str, email: str, password: str) -> models.User:
    salt = secrets.token_hex(16)
    packed = f"{salt}${_hash_password(password, salt)}"
    user = models.User(name=name, email=email, password_hash=packed)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_email(db: OrmSession, email: str) -> models.User | None:
    return db.query(models.User).filter(models.User.email == email).first()


def verify_login(db: OrmSession, email: str, password: str) -> models.User | None:
    user = get_user_by_email(db, email)
    if user is None:
        # Run a hash anyway so a missing email costs the same time as a wrong
        # password -- timing should not reveal whether the email exists.
        _hash_password(password, "00" * 16)
        return None

    salt, _, stored_hash = user.password_hash.partition("$")
    candidate = _hash_password(password, salt)
    if not hmac.compare_digest(candidate, stored_hash):
        return None
    return user


def create_session(db: OrmSession, user_id: int) -> models.SessionToken:
    token = secrets.token_urlsafe(32)
    now = dt.datetime.utcnow()
    session = models.SessionToken(
        id=token, user_id=user_id, created_at=now, expires_at=now + SESSION_LIFETIME
    )
    db.add(session)
    db.commit()
    return session


def get_active_session(db: OrmSession, token: str) -> models.SessionToken | None:
    session = db.get(models.SessionToken, token)
    if session is None:
        return None
    if session.expires_at < dt.datetime.utcnow():
        db.delete(session)
        db.commit()
        return None
    return session


def delete_session(db: OrmSession, token: str) -> None:
    session = db.get(models.SessionToken, token)
    if session is not None:
        db.delete(session)
        db.commit()


def purge_expired_sessions(db: OrmSession) -> int:
    now = dt.datetime.utcnow()
    stale = db.query(models.SessionToken).filter(models.SessionToken.expires_at < now).all()
    for session in stale:
        db.delete(session)
    db.commit()
    return len(stale)
