"""The one place a tenant is resolved.

Phase 1 found six mechanisms deciding which operator a request acted as, none
of them authoritative: a query parameter, a path segment, a shared key, an
env injection, a JSON file keyed by username, and a session that only
``/auth/me`` ever consulted. Five of them were caller-supplied.

There is now exactly one, resolved once, here, from the session. Nothing
downstream accepts a tenant, which is why the contract test can assert that
no route anywhere declares a ``user_id`` parameter — the attack has no input
surface rather than being merely ignored.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session as DbSession

from app.platform.db.repository import TenantRepository
from app.platform.db.session import session_factory
from app.platform.security import sessions
from app.platform.security.envelope import Keyring
from app.tenancy import repository as tenants
from app.tenancy.models import Tenant


def get_db() -> Iterator[DbSession]:
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()


def current_session(x_api_key: str = Header(default="")) -> sessions.Session:
    """Who is asking. A request that cannot answer this reaches nothing."""
    session = sessions.validate(x_api_key)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to use this desk",
            headers={"WWW-Authenticate": "X-API-Key"},
        )
    return session


def current_tenant(session: sessions.Session = Depends(current_session),
                   db: DbSession = Depends(get_db)) -> Tenant:
    """The operator this request acts as. Never negotiable by the caller."""
    tenant = tenants.by_id(db, session.tenant_id)
    if tenant is None or tenant.status != "active":
        # The session outlived its operator: suspended, or deleted under it.
        sessions.revoke(session.token)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to use this desk",
        )
    return tenant


def require_admin(session: sessions.Session = Depends(current_session),
                  tenant: Tenant = Depends(current_tenant)) -> Tenant:
    """Tenancy administration. Deliberately a 404, not a 403.

    A 403 tells a non-admin that the admin surface exists and that they found
    it. Not-found is the same answer an unknown path gives, which is the same
    reasoning that makes another tenant's record 404 rather than 403.
    """
    if not tenant.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Not found")
    return tenant


def scoped(tenant: Tenant = Depends(current_tenant),
           db: DbSession = Depends(get_db)) -> TenantRepository:
    """A repository that already knows whose data it may touch.

    Handlers receive THIS rather than a bare session, so a query without a
    tenant is not something a handler is able to express.
    """
    return TenantRepository(session=db, tenant_id=tenant.id)


_keyring: Keyring | None = None


def keyring() -> Keyring:
    """The master keyring, built once.

    Built lazily rather than at import so a process that never touches a
    credential — a migration, a doctor run — does not require the master key
    to be present just to start.
    """
    global _keyring
    if _keyring is None:
        _keyring = Keyring.from_env()
    return _keyring


def reset_keyring_for_tests() -> None:
    global _keyring
    _keyring = None


def tenant_scoped(fn):
    """Marks a route as returning tenant data.

    The isolation suite reads this marker to find endpoints it does not yet
    cover, so coverage cannot rot silently as the API grows.
    """
    fn.__tenant_scoped__ = True
    return fn
