"""Login sessions for the desk.

Deliberately in-memory. Sessions are not worth persisting for a single-
operator trading desk, and not persisting them has a useful property: a
restart logs everyone out, so a machine left running overnight cannot be
walked up to and used. The cost is re-typing a password after `restart`.

A token is an opaque 256-bit random string. It travels in the X-API-Key
header — the same header the shared-key mode uses — so the frontend needed
no new plumbing and `curl -H "X-API-Key: <token>"` works the same either
way.

NOT a general auth system: no roles, no refresh, no revocation list beyond
the store itself. It exists so that a desk which can place real orders is
not open to anyone who can reach the port.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

# username -> (consecutive failures, locked-until monotonic time)
_FAILURES: dict[str, tuple[int, float]] = {}
_LOCK_AFTER = 10          # consecutive bad passwords before a cooling-off
_LOCK_SECONDS = 300.0     # 5 minutes

_SESSIONS: dict[str, "Session"] = {}
_MUTEX = threading.Lock()


@dataclass(frozen=True)
class Session:
    token: str
    user_id: str
    username: str
    created_at: float
    expires_at: float

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at

    def public(self) -> dict:
        """What the browser is allowed to see. The token is returned only
        once, by login itself — never echoed back by /auth/me."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "expires_in_s": max(0, int(self.expires_at - time.time())),
        }


def _sweep_locked() -> None:
    """Drop expired sessions. Caller holds the mutex."""
    now = time.time()
    for token in [t for t, s in _SESSIONS.items() if s.expires_at <= now]:
        _SESSIONS.pop(token, None)


def lockout_remaining(username: str) -> int:
    """Seconds this username must wait before another attempt, 0 if none."""
    with _MUTEX:
        count, until = _FAILURES.get(username.lower(), (0, 0.0))
        if count < _LOCK_AFTER:
            return 0
        left = until - time.monotonic()
        if left <= 0:
            _FAILURES.pop(username.lower(), None)
            return 0
        return int(left) + 1


def record_failure(username: str) -> None:
    """Count a bad password. credentials.verify_password already burns a
    second on every failure; this stops a patient attacker from simply
    waiting that out."""
    key = username.lower()
    with _MUTEX:
        count, _ = _FAILURES.get(key, (0, 0.0))
        count += 1
        _FAILURES[key] = (count, time.monotonic() + _LOCK_SECONDS)


def clear_failures(username: str) -> None:
    with _MUTEX:
        _FAILURES.pop(username.lower(), None)


def create(user_id: str, username: str, ttl_s: int) -> Session:
    token = secrets.token_urlsafe(32)
    now = time.time()
    session = Session(token=token, user_id=user_id, username=username,
                      created_at=now, expires_at=now + ttl_s)
    with _MUTEX:
        _sweep_locked()
        _SESSIONS[token] = session
    return session


def validate(token: str) -> Session | None:
    if not token:
        return None
    with _MUTEX:
        session = _SESSIONS.get(token)
        if session is None:
            return None
        if session.expired:
            _SESSIONS.pop(token, None)
            return None
        return session


def revoke(token: str) -> bool:
    with _MUTEX:
        return _SESSIONS.pop(token, None) is not None


def revoke_all() -> int:
    with _MUTEX:
        n = len(_SESSIONS)
        _SESSIONS.clear()
        return n


def active_count() -> int:
    with _MUTEX:
        _sweep_locked()
        return len(_SESSIONS)
