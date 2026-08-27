"""Desk login.

The password is NOT stored in this project. It lives in the operator's own
credential folder as ``customers/<username>/.sam`` — the same single-line
plaintext file the 38trades apps have always used — and is compared by
``credentials.verify_password``, which does a timing-safe byte compare and
burns a fixed second on every failure path.

That means adding an operator is a filesystem operation, not a migration:
drop a folder under customers/ with a .sam and the broker keys in it, and
register the user. Nothing about the password ever enters the database.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models import User
from app.services import credentials as creds_svc
from app.services import sessions as session_svc

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    token: str
    user_id: str
    username: str
    expires_at: float
    expires_in_s: int


def current_session(x_api_key: str = Header(default="")) -> session_svc.Session:
    """Dependency for endpoints that need to know WHO is asking.

    The middleware has already refused anything without a valid credential,
    so reaching here with no session means the caller authenticated with the
    fixed TBOT_API_KEY instead — a script, not a person.
    """
    session = session_svc.validate(x_api_key)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not signed in (this call needs a login session, "
                   "not the shared API key)",
        )
    return session


@router.post("/login", response_model=LoginResponse, operation_id="login")
def login(payload: LoginRequest, db: DbSession = Depends(get_db)) -> LoginResponse:
    settings = get_settings()
    username = payload.username.strip()

    locked = session_svc.lockout_remaining(username)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Try again in {locked}s.",
        )

    user = db.scalar(
        select(User).where(User.username.ilike(username))
    )
    # One message for "no such user" and "wrong password" on purpose: the
    # login screen must not confirm which operators exist. The failure is
    # still counted for the typed name so guessing usernames is throttled
    # too.
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
    )
    if user is None:
        session_svc.record_failure(username)
        # Match the delay verify_password would have cost, so a missing user
        # is not detectable by how fast the answer comes back.
        import time as _time

        _time.sleep(1.0)
        raise invalid

    if not creds_svc.verify_password(user.user_root_folder, payload.password):
        session_svc.record_failure(username)
        raise invalid

    session_svc.clear_failures(username)
    session = session_svc.create(user.user_id, user.username,
                                 settings.session_ttl_s)
    return LoginResponse(
        token=session.token,
        user_id=session.user_id,
        username=session.username,
        expires_at=session.expires_at,
        expires_in_s=int(settings.session_ttl_s),
    )


@router.get("/me", operation_id="whoami")
def me(session: session_svc.Session = Depends(current_session)) -> dict:
    """Used by the desk on load to decide whether to show the login screen."""
    return session.public()


@router.post("/logout", operation_id="logout")
def logout(x_api_key: str = Header(default="")) -> dict:
    return {"logged_out": session_svc.revoke(x_api_key)}


@router.get("/status", operation_id="getAuthStatus")
def auth_status() -> dict:
    """Open endpoint: lets the desk know whether to ask for a password at
    all before it has any credential to present."""
    settings = get_settings()
    return {
        "login_required": settings.login_required,
        "shared_key_set": bool(settings.api_key),
        "active_sessions": session_svc.active_count(),
        "session_ttl_s": settings.session_ttl_s,
    }
