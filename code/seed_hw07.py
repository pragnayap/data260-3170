#!/usr/bin/env python3
"""
HW7 Part 1 - add username/role to the MySQL users table and seed one account
per role.

Base.metadata.create_all() never alters an existing table, so the two columns
are added with ALTER TABLE if they are missing. Safe to re-run: existing
accounts get their role and password reset to the values below, nothing else
is touched. Only hashes reach the database.

    reader     / ReaderPass#2026
    writer     / WriterPass#2026
    moderator  / ModPass#2026

Run (from repo root):
    .venv/bin/python code/seed_hw07.py
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).parent / "web_application"))

import models  # noqa: E402
import session_crud  # noqa: E402
from database import Base, db_session_basede26, engine  # noqa: E402

SEED_USERS = {
    "reader": ("Rita Reader", "reader@s3170.example", "ReaderPass#2026"),
    "writer": ("Wendy Writer", "writer@s3170.example", "WriterPass#2026"),
    "moderator": ("Maya Moderator", "moderator@s3170.example", "ModPass#2026"),
}


def ensure_columns() -> None:
    Base.metadata.create_all(bind=engine)
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    with engine.begin() as conn:
        if "username" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(64) NULL"))
            conn.execute(text("CREATE UNIQUE INDEX ix_users_username ON users (username)"))
        if "role" not in cols:
            conn.execute(
                text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'reader'")
            )


def seed() -> None:
    ensure_columns()
    db = db_session_basede26()
    try:
        for username, (name, email, password) in SEED_USERS.items():
            user = db.query(models.User).filter(models.User.username == username).first()
            salt = secrets.token_hex(16)
            packed = f"{salt}${session_crud._hash_password(password, salt)}"
            if user is None:
                user = models.User(name=name, email=email, username=username)
                db.add(user)
            user.role = username
            user.password_hash = packed
        db.commit()
        for u in db.query(models.User).filter(models.User.username.isnot(None)).all():
            print(f"{u.id:>3}  {u.username:<10} {u.role:<10} hash={u.password_hash[:12]}...")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
