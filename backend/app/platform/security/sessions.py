"""Login sessions. In-memory, and carrying the tenant.

Kept in memory deliberately (Phase 2 D8, approved): a restart signs everyone
out, so a desk left running overnight cannot be walked up to and used. The
cost is re-typing a password after a deploy, and that cost is now written
into deploy.md rather than being folklore.

The change from the old build is that a session carries a TENANT ID, and that
id is the only thing that ever decides which operator a request acts as. The
old build resolved identity from a query parameter with a hardcoded default
of 'sampath'; this module is what replaces it.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

_LOCK_AFTER = 10          # consecutive bad passwords before a cooling-off
_LOCK_SECONDS = 300.0

_sessions: dict[str, "Session"] = {}
_failures: dict[str, tuple[int, float]] = {}
_mutex = threading.Lock()


@dataclass(frozen=True)
class Session:
    token: str
    tenant_id: str
    slug: str
    is_admin: bool
    created_at: float
    expires_at: float

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at

    def public(self) -> dict:
        """What the browser may see. The token is returned once, by login
        itself, and never echoed back by /auth/me."""
        return {
            "tenant_id": self.tenant_id,
            "username": self.slug,
            "is_admin": self.is_admin,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "expires_in_s": max(0, int(self.expires_at - time.time())),
        }


def _sweep() -> None:
    """Drop expired sessions. Caller holds the mutex."""
    now = time.time()
    for token in [t for t, s in _sessions.items() if s.expires_at <= now]:
        _sessions.pop(token, None)


# ---- lockout --------------------------------------------------------------

def lockout_remaining(slug: str) -> int:
    """Seconds this name must wait, 0 if none.

    Counted per TYPED NAME rather than per existing operator, so guessing
    usernames is throttled the same as guessing passwords — otherwise the
    throttle itself reveals which names are real.
    """
    key = slug.strip().lower()
    with _mutex:
        count, until = _failures.get(key, (0, 0.0))
        if count < _LOCK_AFTER:
            return 0
        left = until - time.monotonic()
        if left <= 0:
            _failures.pop(key, None)
            return 0
        return int(left) + 1


def record_failure(slug: str) -> None:
    key = slug.strip().lower()
    with _mutex:
        count, _ = _failures.get(key, (0, 0.0))
        _failures[key] = (count + 1, time.monotonic() + _LOCK_SECONDS)


def clear_failures(slug: str) -> None:
    with _mutex:
        _failures.pop(slug.strip().lower(), None)


# ---- sessions -------------------------------------------------------------

def create(*, tenant_id: str, slug: str, is_admin: bool, ttl_s: int) -> Session:
    token = secrets.token_urlsafe(32)      # 256 bits
    now = time.time()
    session = Session(token=token, tenant_id=tenant_id, slug=slug,
                      is_admin=is_admin, created_at=now,
                      expires_at=now + ttl_s)
    with _mutex:
        _sweep()
        _sessions[token] = session
    return session


def validate(token: str) -> Session | None:
    if not token:
        return None
    with _mutex:
        session = _sessions.get(token)
        if session is None:
            return None
        if session.expired:
            _sessions.pop(token, None)
            return None
        return session


def revoke(token: str) -> bool:
    with _mutex:
        return _sessions.pop(token, None) is not None


def revoke_all_for(tenant_id: str) -> int:
    """Sign one operator out everywhere.

    Needed when a tenant is suspended or a password changes: leaving live
    sessions behind would mean revocation that does not revoke.
    """
    with _mutex:
        doomed = [t for t, s in _sessions.items() if s.tenant_id == tenant_id]
        for t in doomed:
            _sessions.pop(t, None)
        return len(doomed)


def revoke_all() -> int:
    with _mutex:
        n = len(_sessions)
        _sessions.clear()
        return n


def active_count() -> int:
    with _mutex:
        _sweep()
        return len(_sessions)
