"""Sign in, sign out, and "who am I".

``/auth/me`` now answers both questions the desk used to ask separately: who
this is, and which worlds they may open. Folding ``/worlds`` into it removes
a round trip on load, which is the one user-visible effect of this change and
is named as such in the Phase 4 consolidation table.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from app.api_v2 import deps
from app.core.config import get_settings
from app.platform.security import sessions
from app.tenancy import repository as tenants
from app.tenancy.models import Tenant

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    token: str
    tenant_id: str
    username: str
    is_admin: bool
    expires_at: float
    expires_in_s: int


# One message for every failure. The login screen must not confirm which
# operators exist, so "no such operator", "wrong password" and "suspended"
# are indistinguishable — in text, in status code, and (via
# passwords.verify_password) in how long they take.
_INVALID = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                         detail="Incorrect username or password")


@router.post("/login", response_model=LoginResponse, operation_id="login")
def login(payload: LoginRequest,
          db: DbSession = Depends(deps.get_db)) -> LoginResponse:
    settings = get_settings()
    slug = payload.username.strip()

    locked = sessions.lockout_remaining(slug)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Try again in {locked}s.",
        )

    tenant = tenants.authenticate(db, slug, payload.password)
    if tenant is None:
        sessions.record_failure(slug)
        raise _INVALID
    db.commit()          # authenticate() may have re-hashed at a higher cost

    sessions.clear_failures(slug)
    session = sessions.create(tenant_id=tenant.id, slug=tenant.slug,
                              is_admin=tenant.is_admin,
                              ttl_s=settings.session_ttl_s)
    return LoginResponse(
        token=session.token, tenant_id=tenant.id, username=tenant.slug,
        is_admin=tenant.is_admin, expires_at=session.expires_at,
        expires_in_s=int(settings.session_ttl_s),
    )


@router.get("/me", operation_id="whoami")
@deps.tenant_scoped
def me(session: sessions.Session = Depends(deps.current_session),
       tenant: Tenant = Depends(deps.current_tenant),
       db: DbSession = Depends(deps.get_db)) -> dict:
    """Identity and world access in one call.

    This is what replaces the old ``ensureUser()``, which read a username
    from a URL parameter, listed every operator to find it, and created one
    if it was missing. The desk no longer chooses who it is.
    """
    body = session.public()
    body.update(tenants.worlds_for(db, tenant))
    body["display_name"] = tenant.display_name
    return body


@router.post("/logout", operation_id="logout")
def logout(x_api_key: str = Header(default="")) -> dict:
    return {"logged_out": sessions.revoke(x_api_key)}


@router.get("/status", operation_id="getAuthStatus")
def auth_status() -> dict:
    """Open endpoint: the login screen has to load before anyone can
    authenticate, so it must be able to ask whether a password is needed."""
    settings = get_settings()
    return {
        "login_required": True,
        "active_sessions": sessions.active_count(),
        "session_ttl_s": settings.session_ttl_s,
    }
