"""Guard 7: the stop's own watchdog.

Phase 3's finding was that a stop-loss living only inside a running loop is not
a risk control — a crash leaves live positions with an armed profit-taker and
no floor, and nothing says so. Three things use this module:

  the order path   refuses a new entry when nobody has swept recently
  /readiness       reports the age, so ops sees it before an operator does
  the monitor      records a pass, and records a FAILED pass as a failure

That last one is the part that is easy to get wrong. A pass that threw is not
a pass, and stamping it healthy would make the watchdog lie in exactly the
situation it exists for.
"""

from __future__ import annotations

from sqlalchemy import select

from app.domains.trading.models import RiskHeartbeat
from app.platform.db.base import utcnow
from app.platform.db.session import session_factory

# How stale is too stale. The monitor runs every 10 seconds, so a minute means
# roughly six consecutive misses — comfortably past a slow pass, comfortably
# short of a market move going unwatched.
STALE_AFTER_S = 60


def _row(db, tenant_id: str) -> RiskHeartbeat:
    row = db.get(RiskHeartbeat, tenant_id)
    if row is None:
        row = RiskHeartbeat(tenant_id=tenant_id, consecutive_failures=0)
        db.add(row)
        db.flush()
    return row


def record_pass(tenant_id: str) -> None:
    """A pass completed. Both timestamps move; failures reset."""
    db = session_factory()()
    try:
        row = _row(db, tenant_id)
        now = utcnow()
        row.last_pass_at = now
        row.last_ok_at = now
        row.consecutive_failures = 0
        row.last_error = None
        db.commit()
    finally:
        db.close()


def record_failure(tenant_id: str, error: str) -> None:
    """A pass threw.

    ``last_pass_at`` moves (we did try) but ``last_ok_at`` does NOT — that is
    what staleness is measured against, so a loop failing every tick still
    reads as unwatched rather than as healthy.
    """
    db = session_factory()()
    try:
        row = _row(db, tenant_id)
        row.last_pass_at = utcnow()
        row.consecutive_failures = (row.consecutive_failures or 0) + 1
        row.last_error = error[:500]
        db.commit()
    finally:
        db.close()


def seconds_since_last_pass(tenant_id: str) -> float:
    """Age of the last SUCCESSFUL sweep. Infinite when there has never been one.

    Infinity rather than zero on purpose: a tenant nobody has ever swept is
    the least safe case, and a default of zero would read as perfectly fresh.
    """
    db = session_factory()()
    try:
        row = db.get(RiskHeartbeat, tenant_id)
        if row is None or row.last_ok_at is None:
            return float("inf")
        return (utcnow() - row.last_ok_at).total_seconds()
    finally:
        db.close()


def consecutive_failures(tenant_id: str) -> int:
    db = session_factory()()
    try:
        row = db.get(RiskHeartbeat, tenant_id)
        return int(row.consecutive_failures or 0) if row else 0
    finally:
        db.close()


def is_stale(tenant_id: str) -> bool:
    return seconds_since_last_pass(tenant_id) > STALE_AFTER_S


def summary() -> dict:
    """What /readiness reports.

    Per tenant, because "the monitor is running" is not the same statement as
    "your stops are being watched" — one tenant's credentials failing must
    show up as that tenant being unwatched.
    """
    db = session_factory()()
    try:
        rows = list(db.scalars(select(RiskHeartbeat)).all())
        now = utcnow()
        tenants = []
        worst = 0.0
        for row in rows:
            age = (float("inf") if row.last_ok_at is None
                   else (now - row.last_ok_at).total_seconds())
            worst = max(worst, 0.0 if age == float("inf") else age)
            tenants.append({
                "tenant_id": row.tenant_id,
                "seconds_since_ok": None if age == float("inf") else round(age, 1),
                "consecutive_failures": row.consecutive_failures or 0,
                "stale": age > STALE_AFTER_S,
            })
        return {
            "available": True,
            "stale_after_s": STALE_AFTER_S,
            "tenants": tenants,
            "any_stale": any(t["stale"] for t in tenants),
            "worst_age_s": round(worst, 1) if tenants else None,
        }
    finally:
        db.close()
