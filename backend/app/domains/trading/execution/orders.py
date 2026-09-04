"""Opening and closing a position, with all seven guards in one place.

The order of the guards is the argument. Guards 1 and 2 are STRUCTURAL — a
uniqueness constraint and a write lock — and they run first because they are
what actually prevent a duplicate. Guards 3, 4 and 5 are CONFIRMATION: they
catch what the structure cannot see, which is an order placed by something
outside this application. Putting confirmation first would be check-then-act,
which is a race wearing a checklist.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.trading.execution import idempotency, leases
from app.domains.trading.execution import venue as venue_mod
from app.domains.trading.models import Position
from app.domains.trading.risk import clock, heartbeat
from app.domains.trading.risk.validation import RiskRefused, validate_entry
from app.platform.db.base import utcnow

logger = logging.getLogger(__name__)

# Guard 5: how long to let the venue settle before re-reading. Long enough for
# an order to appear, short enough that the operator is not left waiting.
SETTLE_SECONDS = 2.0


class ExecutionRefused(Exception):
    """A guard said no. Nothing was placed."""

    def __init__(self, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.status_code = status_code


def _resource(occ_symbol: str, sandbox: bool) -> str:
    return f"position:{'sandbox' if sandbox else 'live'}:{occ_symbol}"


# ---- guard 7 --------------------------------------------------------------

def stop_watch_warning(tenant_id: str) -> str | None:
    """The sentence, or None when the stop IS being watched.

    Separated from the decision to refuse so that the same words can be a
    refusal, a log line, or a note on the position, depending on what the
    operator has asked for.
    """
    age = heartbeat.seconds_since_last_pass(tenant_id)
    if age <= heartbeat.STALE_AFTER_S:
        return None
    pretty = "never" if age == float("inf") else f"{int(age)}s ago"
    return f"the risk monitor last completed a sweep {pretty}"


def require_watched_stops(tenant_id: str) -> str | None:
    """Refuse to open a position nobody is watching the stop for.

    Opening a position whose stop-loss is unwatched is worse than not trading:
    the take-profit rests at the venue and would still fire, so the position
    keeps its upside and silently loses its floor. This is the guard that
    makes the Phase 3 alarm visible instead of silent.

    TBOT_ENFORCE_STOP_WATCHDOG=false downgrades the refusal to a warning. That
    is an operator saying they will watch this one themselves, and the request
    is honoured -- but not quietly. The warning is logged, and it is RETURNED
    so the caller can write it onto the position, because the moment that
    matters is not now, it is later, when somebody is looking at a filled
    contract and wondering whether anything is minding its floor.
    """
    from app.core.config import get_settings

    warning = stop_watch_warning(tenant_id)
    if warning is None:
        return None

    if get_settings().enforce_stop_watchdog:
        raise ExecutionRefused(
            f"{warning}; new entries are refused while stop-losses are not "
            f"being watched",
            status_code=503,
        )

    logger.warning("tenant %s: %s -- stop-losses are NOT being watched and "
                   "the entry was allowed anyway because "
                   "TBOT_ENFORCE_STOP_WATCHDOG is off", tenant_id, warning)
    return f"{warning} — stop-loss is not being watched"


# ---- guards 3 and 4 -------------------------------------------------------

def _refuse_if_already_held(db: Session, tenant_id: str, occ_symbol: str,
                            sandbox: bool) -> None:
    existing = db.scalar(select(Position).where(
        Position.tenant_id == tenant_id,
        Position.occ_symbol == occ_symbol,
        Position.venue_sandbox == sandbox,
        Position.status.in_(("pending", "open")),
    ))
    if existing is not None:
        # Name the position. "You already have this, here it is" is the
        # answer; a bare error makes the operator go looking.
        raise ExecutionRefused(
            f"you already hold {occ_symbol} — position {existing.id} "
            f"({existing.status}, {existing.contracts} contract(s)). Pass "
            f"allow_add to add to it deliberately.",
        )


def _refuse_if_working_at_venue(cred, occ_symbol: str, sandbox: bool) -> None:
    working = venue_mod.working_orders_for(occ_symbol, cred=cred, side="buy_to_open",
                                           sandbox=sandbox)
    if working:
        ids = ", ".join(str(o.get("id")) for o in working)
        raise ExecutionRefused(
            f"the venue already has a working buy order for {occ_symbol} "
            f"({ids}); nothing was placed"
        )


# ---- guard 5 --------------------------------------------------------------

def _settle_and_confirm(cred, pos: Position, ours: str, sandbox: bool) -> bool:
    """Re-read after a beat. Exactly one working order is expected.

    Returns True when something needed cleaning up, so the caller can flag the
    position for review rather than pretending the outcome was clean.
    """
    time.sleep(SETTLE_SECONDS)
    working = venue_mod.working_orders_after_place(
        pos.occ_symbol, cred=cred, side="buy_to_open", sandbox=sandbox)
    strays = [o for o in working if str(o.get("id")) != str(ours)]
    if not strays:
        return False

    for stray in strays:
        logger.warning(
            "position %s: cancelling an unexpected second buy order %s on %s",
            pos.id, stray.get("id"), pos.occ_symbol)
        venue_mod.cancel_order(str(stray.get("id")), cred=cred,
                               sandbox=sandbox)
    return True


# ---- the entry ------------------------------------------------------------

def open_position(db: Session, *, tenant_id: str, cred, symbol: str, side: str,
                  occ_symbol: str, underlying: str, strike: float,
                  expiration: str, delta: float | None, contracts: int,
                  limit_price: float, buy_pct: float, tolerance_pct: float,
                  tp_pct: float, sl_pct: float, sandbox: bool,
                  strategy: str = "Manual", allow_add: bool = False,
                  zero_dte: bool = False) -> Position:
    """Place a managed entry. Every guard runs before the venue is touched."""

    # Guard 6 — refuse, never clamp.
    validate_entry(side=side, buy_pct=buy_pct, tp_pct=tp_pct, sl_pct=sl_pct,
                   expiration=expiration, contracts=contracts)

    # The 0DTE cutoff, checked again HERE rather than only on arrival. A
    # request that was legal when it was made can become illegal before it is
    # executed, and a same-day contract entered late is a different trade.
    if zero_dte or clock.is_same_day(expiration):
        if clock.past_zero_dte_cutoff():
            raise RiskRefused(
                f"same-day contracts are only entered before "
                f"{clock.ZERO_DTE_CUTOFF.strftime('%H:%M')} CST; it is now "
                f"{clock.now().strftime('%H:%M')}"
            )

    # Guard 7 — is anyone watching the stop? Returns the warning instead of
    # raising when the operator has turned the refusal off; it goes on the
    # position below rather than disappearing into a log nobody reads.
    unwatched = require_watched_stops(tenant_id)

    # Guard 2 — one request at a time per contract, across processes.
    with leases.hold(tenant_id=tenant_id, db=db,
                     resource=_resource(occ_symbol, sandbox)):
        # Guards 3 and 4 — our own records, and the venue's, because ours
        # can be wrong. allow_add relaxes BOTH: an operator who has explicitly
        # asked to add to a position is acknowledging the exposure these two
        # exist to surprise them with. Relaxing only guard 3 made allow_add
        # useless, because the working buy from the first order tripped guard
        # 4 and the deliberate add was refused anyway.
        if not allow_add:
            _refuse_if_already_held(db, tenant_id, occ_symbol, sandbox)
            _refuse_if_working_at_venue(cred, occ_symbol, sandbox)

        placed = venue_mod.place_buy(
            cred=cred, underlying=underlying, occ_symbol=occ_symbol,
            quantity=contracts, price=limit_price, sandbox=sandbox)

        pos = Position(
            tenant_id=tenant_id, venue_sandbox=sandbox,
            underlying=underlying, occ_symbol=occ_symbol, option_type=side,
            strike=strike, expiration=expiration, delta_at_entry=delta,
            contracts=contracts, buy_pct=buy_pct, tolerance_pct=tolerance_pct,
            tp_pct=tp_pct, sl_pct=sl_pct, buy_order_id=placed.order_id,
            status="pending", stop_protection="pending", strategy=strategy,
            opened_at=utcnow(),
            note=f"buy_to_open {contracts} @ {limit_price:.2f} limit",
        )
        if unwatched:
            # Opened with the watchdog off. Flagged for review because that is
            # the whole point: this one needs a human to keep an eye on it.
            pos.note += f" — WARNING: {unwatched}"
            pos.needs_review = True
        db.add(pos)
        db.flush()

        # Guard 5 — settle, then confirm exactly one landed.
        try:
            if _settle_and_confirm(cred, pos, placed.order_id, sandbox):
                pos.needs_review = True
                pos.note += " — an unexpected second order was cancelled; review"
        except Exception as exc:                        # noqa: BLE001
            # The confirmation failing must not fail the ORDER, which is
            # already placed. Flag it and let the monitor sort it out.
            logger.warning("position %s: settle check failed: %s", pos.id, exc)
            pos.needs_review = True

        db.flush()
        return pos


# ---- the exit -------------------------------------------------------------

def close_position(db: Session, *, tenant_id: str, cred, pos: Position,
                   force: bool = False) -> Position:
    """Exit now. Cancel both resting legs before selling.

    Order matters: a sell that races its own resting target double-sells the
    holding, and an orphaned stop left on a sold position is an accidental
    short waiting for the next tick.
    """
    if pos.status in ("closed", "tp_filled", "sl_filled", "failed"):
        raise ExecutionRefused(
            f"position {pos.id} is already {pos.status}; nothing to close")

    sandbox = pos.venue_sandbox
    with leases.hold(tenant_id=tenant_id, db=db,
                     resource=_resource(pos.occ_symbol, sandbox)):
        # Cancel EVERY order this position owns, and the entry first.
        #
        # The entry was missing, and that was a real bug: closing a position
        # whose buy is still working left that buy resting at the venue. The
        # operator sees the position close, the order fills a few minutes
        # later, and they own a contract with no exits armed and nothing
        # watching it — exactly the unmanaged position the risk layer exists
        # to prevent.
        for order_id in (pos.buy_order_id, pos.tp_order_id, pos.stop_order_id):
            if order_id:
                venue_mod.cancel_order(order_id, cred=cred, sandbox=sandbox)

        held = venue_mod.held_quantity(pos.occ_symbol, cred=cred, sandbox=sandbox)
        if held <= 0 and not force:
            # The venue does not think this is held. Selling would be
            # rejected, or worse, would open a short.
            pos.status = "closed"
            pos.closed_at = utcnow()
            pos.note = "closed: the venue no longer shows this holding"
            db.flush()
            return pos

        venue_mod.sell_to_close(
            cred=cred, underlying=pos.underlying, occ_symbol=pos.occ_symbol,
            quantity=pos.contracts, sandbox=sandbox)

        pos.status = "closed"
        pos.closed_at = utcnow()
        pos.note = "closed by the operator" + (" (forced)" if force else "")
        db.flush()
        return pos


__all__ = ["ExecutionRefused", "open_position", "close_position",
           "require_watched_stops", "stop_watch_warning", "idempotency",
           "leases"]
