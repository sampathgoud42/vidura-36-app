"""Guard 2: a mutex that holds across processes.

The old build serialised order placement with a module-level
``threading.Lock``. Two uvicorn workers do not share one, and two HAVE run at
once on this machine — ``_warn_on_duplicate_server`` exists because of it. An
in-process lock guarding a money-moving path works right up until the day it
matters.

THE PRIMARY KEY IS THE MUTEX. ``resource_key`` is the primary key of
``execution_lease``, so two processes inserting the same key cannot both
succeed: one commits, the other gets an integrity error. That is the whole
guarantee, it needs no explicit locking statement, and it is portable to any
database rather than resting on SQLite semantics.

The first version of this module took its own connection and opened
``BEGIN IMMEDIATE``. That deadlocked against the caller: the request session
already held an open write transaction from the idempotency INSERT, so the
lease's second connection waited on a lock the first would not release until
the lease returned. It failed as "database is locked", which reads like
contention and was actually self-inflicted. The lease now runs on the
CALLER'S session — one connection, one transaction, no way to wait on
yourself.
"""

from __future__ import annotations

import contextlib
import os
import socket
import threading
from collections.abc import Iterator
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.trading.models import ExecutionLease
from app.platform.db.base import utcnow
from app.platform.db.session import session_factory

DEFAULT_TTL_S = 60


class LeaseUnavailable(RuntimeError):
    """Someone else holds this contract right now."""


def _holder() -> str:
    """Who holds it, in a form a human can act on during an incident."""
    return f"{socket.gethostname()}:{os.getpid()}:{threading.get_ident()}"


def resource_key(tenant_id: str, resource: str) -> str:
    return f"{tenant_id}|{resource}"


def _acquire_on(db: Session, key: str, tenant_id: str, ttl_s: int) -> bool:
    now = utcnow()
    existing = db.get(ExecutionLease, key)
    if existing is not None:
        if existing.expires_at > now:
            return False
        # An EXPIRED lease is taken over rather than respected: a process that
        # died holding one must not lock its contract out until someone
        # notices. The TTL bounds the stall, not the correctness.
        db.delete(existing)
        db.flush()

    row = ExecutionLease(resource_key=key, tenant_id=tenant_id,
                         holder=_holder(), acquired_at=now,
                         expires_at=now + timedelta(seconds=ttl_s))
    try:
        # A savepoint, so losing the race does not poison the caller's
        # transaction -- it still has an order to refuse cleanly.
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        return False
    return True


def acquire(*, tenant_id: str, resource: str, ttl_s: int = DEFAULT_TTL_S,
            db: Session | None = None) -> bool:
    """Take the lease, or return False.

    Pass ``db`` whenever the caller already has a session — which is always,
    inside a request. Without it this opens its own, which is only safe when
    nothing else is mid-transaction.
    """
    key = resource_key(tenant_id, resource)
    if db is not None:
        return _acquire_on(db, key, tenant_id, ttl_s)

    own = session_factory()()
    try:
        ok = _acquire_on(own, key, tenant_id, ttl_s)
        own.commit()
        return ok
    except Exception:
        own.rollback()
        raise
    finally:
        own.close()


def release(*, tenant_id: str, resource: str, db: Session | None = None) -> None:
    key = resource_key(tenant_id, resource)
    stmt = delete(ExecutionLease).where(ExecutionLease.resource_key == key)
    if db is not None:
        db.execute(stmt)
        db.flush()
        return

    own = session_factory()()
    try:
        own.execute(stmt)
        own.commit()
    finally:
        own.close()


@contextlib.contextmanager
def hold(*, tenant_id: str, resource: str, db: Session | None = None,
         ttl_s: int = DEFAULT_TTL_S) -> Iterator[None]:
    """Hold the lease for the whole critical section, or refuse.

    Deliberately does NOT wait. A second click on BUY should be told "that is
    already in flight" immediately; queueing it would place the order a moment
    later, which is precisely the duplicate this exists to prevent.
    """
    if not acquire(tenant_id=tenant_id, resource=resource, ttl_s=ttl_s, db=db):
        raise LeaseUnavailable(
            f"another request is already acting on {resource} for this "
            "operator; nothing was placed"
        )
    try:
        yield
    finally:
        # Best effort. A failed release leaves a lease that expires on its own,
        # which is strictly safer than an exception here masking the real one.
        try:
            release(tenant_id=tenant_id, resource=resource, db=db)
        except Exception:                               # noqa: BLE001
            pass


def sweep_expired() -> int:
    """Housekeeping. Expired leases are already ignored by acquire(); this
    only stops the table growing without bound."""
    db = session_factory()()
    try:
        stale = list(db.scalars(select(ExecutionLease).where(
            ExecutionLease.expires_at <= utcnow())).all())
        for row in stale:
            db.delete(row)
        db.commit()
        return len(stale)
    finally:
        db.close()
