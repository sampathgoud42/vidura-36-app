"""Rollover: the positions held over the close, recorded.

A position bought with Near Expiry off (a 7+ day expiry) is opened marked to
carry (entry.CARRY_MARK, the same mark the desk's 🌙 switch sets). Nothing
flattens positions at the close on this server -- its exits rest at the venue
good-till-cancelled -- so a carried position simply stays open. What this adds
is the RECORD: after the close, each carried position still open, with
neither its target nor its stop hit, gets one PositionRollover row for the
session -- the closing bid, the unrealised P&L, and what the venue says of
both exits. An exit that is no longer working means the position goes into
the night unprotected, so the position is flagged for review and the row
says so.

Runs after the close, 15:00-16:00 CT on weekdays, every few minutes; the
unique (tenant, position, session) key makes a repeat a no-op. A position
whose expiry is today is not carried: it expires.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time

from sqlalchemy import select

from app.domains.trading.risk import clock

logger = logging.getLogger(__name__)

POLL_S = 300
WINDOW = (time(15, 0), time(16, 0))
CARRY_MARK = " +carry"
WORKING = {"open", "partially_filled", "pending", "accepted", "submitted"}


def due(now: datetime | None = None) -> bool:
    now = now or clock.now()
    t = now.timetz().replace(tzinfo=None)
    return clock.is_weekday(now) and WINDOW[0] <= t < WINDOW[1]


def _status(order_id: str | None, cred, sandbox: bool) -> str | None:
    from app.domains.trading.execution import venue as venue_mod

    if not order_id:
        return None
    try:
        return str((venue_mod.order_status(order_id, cred=cred, sandbox=sandbox) or {})
                   .get("status") or "unknown").lower()
    except Exception as exc:                            # noqa: BLE001
        logger.info("rollover: order %s status unreadable: %s", order_id, type(exc).__name__)
        return "unreadable"


def roll(pos, cred, today: date) -> dict:
    """The row for one carried position. Pure apart from the venue reads."""
    from app.domains.trading.execution import venue as venue_mod

    sandbox = pos.venue_sandbox
    bid = venue_mod.bid_for(pos.occ_symbol, cred=cred, sandbox=sandbox)
    tp_status = _status(pos.tp_order_id, cred, sandbox)
    stop_status = _status(pos.stop_order_id, cred, sandbox)
    unrealised = (round((bid - pos.entry_price) * pos.contracts * 100, 2)
                  if bid is not None and pos.entry_price is not None else None)
    gaps = []
    if tp_status not in WORKING:
        gaps.append(f"target {tp_status or 'not armed'}")
    if pos.stop_protection == "venue_resting" and stop_status not in WORKING:
        gaps.append(f"stop {stop_status or 'not armed'}")
    elif pos.stop_protection != "venue_resting":
        gaps.append("stop monitored only -- no venue stop overnight")
    return {
        "position_id": pos.id, "rolled_on": today.isoformat(),
        "venue_sandbox": sandbox, "underlying": pos.underlying,
        "occ_symbol": pos.occ_symbol, "option_type": pos.option_type,
        "strike": pos.strike, "expiration": pos.expiration,
        "days_left": (date.fromisoformat(pos.expiration) - today).days,
        "contracts": pos.contracts, "entry_price": pos.entry_price,
        "close_bid": bid, "unrealised_usd": unrealised,
        "tp_price": pos.tp_price, "sl_price": pos.sl_price,
        "tp_order_id": pos.tp_order_id, "stop_order_id": pos.stop_order_id,
        "tp_status": tp_status, "stop_status": stop_status,
        "stop_protection": pos.stop_protection, "strategy": pos.strategy,
        "note": ("held over the close; " + ("; ".join(gaps) if gaps
                 else "target and stop both resting at the venue")),
        "_unprotected": bool(gaps),
    }


def sweep_all_tenants(now: datetime | None = None) -> int:
    """Record every carried position still open after the close. Returns how
    many rows were written this pass."""
    from app.domains.trading.models import Position, PositionRollover
    from app.domains.trading.risk import monitor
    from app.platform.db.session import session_scope

    now = now or clock.now()
    if not due(now):
        return 0
    today = now.date()
    written = 0
    with session_scope() as db:
        rows = list(db.scalars(select(Position).where(
            Position.status == "open",
            Position.strategy.like(f"%{CARRY_MARK}"),
            Position.expiration > today.isoformat())).all())
        done = {(r.tenant_id, r.position_id) for r in db.scalars(
            select(PositionRollover).where(PositionRollover.rolled_on == today.isoformat())).all()}
        creds: dict[tuple[str, bool, bool], object] = {}
        for pos in rows:
            if (pos.tenant_id, pos.id) in done:
                continue
            try:
                key = (pos.tenant_id, pos.venue_sandbox, bool(pos.simulated))
                if key not in creds:
                    creds[key] = monitor._credential(pos.tenant_id, pos.venue_sandbox,
                                                     pos.simulated)
                rec = roll(pos, creds[key], today)
            except Exception as exc:                    # noqa: BLE001
                logger.warning("rollover: position %s: %s", pos.id, type(exc).__name__)
                continue
            unprotected = rec.pop("_unprotected")
            db.add(PositionRollover(tenant_id=pos.tenant_id, **rec))
            if unprotected:
                pos.needs_review = True
            pos.note = ((pos.note or "") + f" — rolled over {today:%m/%d}: {rec['note']}")[-1000:]
            written += 1
    if written:
        logger.info("rollover: %d position(s) recorded as held over %s", written, today)
    return written
