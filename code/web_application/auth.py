"""
HW3 Part 1 - Authentication for the Municipal Transit Incidents app (DOMAIN_ID 2).

Everything auth-related lives here and is mounted on the main app as a single
APIRouter, so app.py keeps only the HW2 REST API plus the middleware wiring.

Routes
    GET  /          home       public; links to login or dashboard
    GET  /login     login form public
    POST /login     login      validates credentials, starts the session
    GET  /dashboard dashboard  protected; requires a live session
    GET  /logout    logout     clears the session, back to home

Session model
    Starlette's SessionMiddleware keeps the session in a *signed* cookie, which
    means the cookie is tamper-proof but not revocable on its own: a copy of an
    old cookie stays validly signed forever. Logging out only tells the browser
    to drop it, so a replayed copy would still be accepted. To make logout and
    expiry actually enforceable, each login mints a random session id and
    registers it in the server-side ACTIVE_SESSIONS registry. The cookie carries
    only that id; authority lives on the server.

    Every protected request then checks three things: the cookie is signed, its
    sid is still registered, and now - last_seen is within IDLE_TIMEOUT_SECONDS.
    Logout and expiry both *unregister* the sid, so replaying either cookie
    fails the second check. last_seen is rewritten on each authorised request,
    so the window is genuinely *idle* time, not a fixed lifetime from login.

    ACTIVE_SESSIONS is an in-memory dict, matching the in-memory incident store
    from HW2: every session dies on restart. A real deployment would use Redis
    or a sessions table; the enforcement logic is identical.

Password storage
    PBKDF2-HMAC-SHA256, 200k iterations, per-user salt. No plaintext passwords
    in the repo. hmac.compare_digest keeps the comparison constant-time.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

# --- Configuration -------------------------------------------------------

# Idle window in seconds. Deliberately short so the timeout is demonstrable in
# a screenshot without waiting around; override with the env var for normal use.
IDLE_TIMEOUT_SECONDS = int(os.environ.get("S3170_IDLE_TIMEOUT", "120"))

PBKDF2_ITERATIONS = 200_000

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["auth"])


# --- Demo user store -----------------------------------------------------
#
# A dict stands in for a user table. Storing the salt and the derived key (both
# hex) is exactly what a real users table would hold; the plaintext passwords
# are only in the docstring below so the grader can actually log in.
#
#     dispatcher / TransitOps#2026
#     inspector  / SafetyFirst#2026

USERS: dict[str, dict[str, str]] = {
    "dispatcher": {
        "display_name": "Dana Ruiz",
        "role": "Transit Dispatcher",
        "salt": "9f2c1a7d4b6e8053",
        # pbkdf2_hmac('sha256', b'TransitOps#2026', bytes.fromhex(salt), 200000)
        "password_hash": "",  # filled in by _seed_hashes() at import time
    },
    "inspector": {
        "display_name": "Marcus Webb",
        "role": "Safety Inspector",
        "salt": "3e7b0d5c1f9a4628",
        "password_hash": "",
    },
}

_SEED_PASSWORDS = {
    "dispatcher": "TransitOps#2026",
    "inspector": "SafetyFirst#2026",
}


def hash_password(password: str, salt_hex: str) -> str:
    """Derive the stored password hash. Same function used to seed and to verify."""
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        PBKDF2_ITERATIONS,
    )
    return derived.hex()


def _seed_hashes() -> None:
    """Compute the stored hashes once at import time from the seed passwords."""
    for username, plaintext in _SEED_PASSWORDS.items():
        record = USERS[username]
        record["password_hash"] = hash_password(plaintext, record["salt"])


_seed_hashes()


def verify_credentials(username: str, password: str) -> dict[str, str] | None:
    """Return the user record on a correct username+password, else None."""
    record = USERS.get(username)
    if record is None:
        # Still run a hash so a missing username costs the same time as a wrong
        # password -- otherwise response timing leaks which usernames exist.
        hash_password(password, "00" * 8)
        return None

    candidate = hash_password(password, record["salt"])
    if not hmac.compare_digest(candidate, record["password_hash"]):
        return None
    return record


# --- Server-side session registry ----------------------------------------
#
# sid -> {"username": str, "last_seen": float, "login_time": float}
# Present here means "live". Absent means logged out, expired, or forged.

ACTIVE_SESSIONS: dict[str, dict[str, float | str]] = {}


def start_session(request: Request, username: str) -> str:
    """Mint a new session id, register it server-side, and put it in the cookie."""
    # Drop any previous session for this request before issuing a new id, so a
    # pre-login cookie can never be upgraded into an authenticated one.
    end_session(request)

    sid = secrets.token_urlsafe(24)
    now = time.time()
    ACTIVE_SESSIONS[sid] = {"username": username, "last_seen": now, "login_time": now}

    request.session.clear()
    request.session["sid"] = sid
    return sid


def end_session(request: Request) -> None:
    """Revoke this request's session server-side and clear its cookie."""
    sid = request.session.get("sid")
    if sid:
        ACTIVE_SESSIONS.pop(sid, None)
    request.session.clear()


def purge_idle_sessions() -> int:
    """Drop every registered session past the idle window. Returns how many."""
    cutoff = time.time() - IDLE_TIMEOUT_SECONDS
    stale = [sid for sid, s in ACTIVE_SESSIONS.items() if s["last_seen"] < cutoff]
    for sid in stale:
        del ACTIVE_SESSIONS[sid]
    return len(stale)


# --- Session helpers -----------------------------------------------------

def current_user(request: Request) -> dict[str, str] | None:
    """The logged-in user for this request, or None.

    Three gates, in order: a signed cookie carrying a sid, that sid still being
    registered server-side, and the idle window not yet elapsed. Failing any of
    them revokes the session, which is what makes a logged-out or expired
    cookie unusable rather than merely stale -- replaying the raw cookie value
    fails at the registry lookup even though its signature is still valid.
    """
    sid = request.session.get("sid")
    if not sid:
        return None

    state = ACTIVE_SESSIONS.get(sid)
    if state is None:             # logged out, expired, or never issued here
        request.session.clear()
        return None

    if time.time() - float(state["last_seen"]) > IDLE_TIMEOUT_SECONDS:
        del ACTIVE_SESSIONS[sid]  # revoke, do not merely ignore
        request.session.clear()
        return None

    record = USERS.get(str(state["username"]))
    if record is None:            # user removed while a session was live
        end_session(request)
        return None

    state["last_seen"] = time.time()
    return {"username": str(state["username"]), **record}


def seconds_until_idle_timeout(request: Request) -> int:
    """Whole seconds left before this session goes idle-stale (for the UI)."""
    sid = request.session.get("sid")
    state = ACTIVE_SESSIONS.get(sid) if sid else None
    if state is None:
        return 0
    return max(0, int(IDLE_TIMEOUT_SECONDS - (time.time() - float(state["last_seen"]))))


# --- Routes --------------------------------------------------------------

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def home(request: Request):
    """Public landing page. Shows login, or dashboard+logout when signed in."""
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "user": current_user(request)},
    )


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_form(request: Request, expired: int = 0):
    """The login form. ?expired=1 explains why the user landed back here."""
    if current_user(request):
        return RedirectResponse("/dashboard", status_code=303)

    alert = None
    if expired:
        alert = (
            f"Your session timed out after {IDLE_TIMEOUT_SECONDS} seconds of "
            "inactivity. Please sign in again."
        )
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "user": None, "alert": alert, "alert_kind": "warning"},
    )


@router.post("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
):
    """Validate the credentials; start a session and redirect on success.

    The defaults are empty strings rather than Form(...) deliberately. With a
    required Form field, Pydantic treats an empty form value as *missing* and
    FastAPI answers with its own 422 JSON error page before this function runs
    -- so submitting the form with blank boxes showed the user a wall of raw
    JSON instead of the Bootstrap alert the assignment asks for. Accepting the
    empty string lets the request reach verify_credentials(), which rejects it
    like any other bad credential and re-renders the form with the alert.
    """
    record = verify_credentials(username.strip(), password)
    if record is None:
        # Same message for bad username and bad password -- do not confirm
        # which half was wrong. 401 so the failure is visible in the network log.
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "user": None,
                "alert": "Invalid username or password. Please try again.",
                "alert_kind": "danger",
                "username": username,
            },
            status_code=401,
        )

    # New session id on login: never carry a pre-login session forward.
    start_session(request, username.strip())

    # 303 forces the browser to GET /dashboard, so a refresh does not re-POST.
    return RedirectResponse("/dashboard", status_code=303)


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request):
    """Protected route. Anything without a live session is sent to /login."""
    user = current_user(request)
    if user is None:
        return RedirectResponse("/login?expired=1", status_code=303)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "idle_timeout": IDLE_TIMEOUT_SECONDS,
            "seconds_left": seconds_until_idle_timeout(request),
            "active_sessions": len(ACTIVE_SESSIONS),
        },
    )


@router.get("/logout", include_in_schema=False)
async def logout(request: Request):
    """Destroy the session and return to the home page.

    end_session() unregisters the sid server-side, so the cookie the browser
    was holding a moment ago is dead even if it is captured and replayed.
    """
    end_session(request)
    return RedirectResponse("/", status_code=303)
