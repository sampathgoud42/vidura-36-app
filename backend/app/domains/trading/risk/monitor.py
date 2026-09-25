"""The position monitor: arm exits, then watch the stop.

What it does each pass, per position:

  pending   is the buy filled? record the entry. Then, once the wait has
            elapsed AND the account actually shows the contract, arm BOTH
            exits — a resting take-profit and a resting stop.
  open      did the target fill? did the stop fill? has the bid breached a
            stop that is only monitored?

STARTUP_DELAY_S is zero, and that is a fix rather than a default. The old loop
slept 15 seconds before its first pass, so every restart had a blind window
with live positions in it. There is no reason for a stop to be unwatched
during the one moment we know the process just came back.

``run_pass`` takes its tenant as a KEYWORD-ONLY argument with no default. That
is deliberate: it must be impossible to sweep "everything" by forgetting an
argument, because an unscoped sweep is how one tenant's failure becomes
everyone's and how a write reaches the wrong account.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.domains.trading.execution import venue as venue_mod
from app.domains.trading.models import Position
from app.domains.trading.risk import heartbeat
from app.domains.trading.risk.validation import exit_prices
from app.platform.db.base import utcnow
from app.platform.db.session import session_factory

logger = logging.getLogger(__name__)

# No cold-start blind window. See the module docstring.
STARTUP_DELAY_S = 0

# How long after a fill before exits are armed. A buy that reports "filled" is
# not yet a position; selling into that gap is what the venue rejects.
ARM_DELAY_S = 30

ACTIVE = ("pending", "open")


# The same failure, logged once and then only occasionally. A position whose
# operator has no credential fails on EVERY pass, so at a 10s cadence one
# broken position wrote ~8,600 identical lines a day -- enough to bury the
# first occurrence of anything else and to keep the disk busy saying nothing
# new. The first is logged in full; repeats are summarised every few minutes.
_REPEAT_AFTER_S = 300
_last_said: dict[str, float] = {}


def _say_once(key: str, message: str, *args) -> None:
    import time

    now = time.time()
    seen = _last_said.get(key)
    if seen is None:
        _last_said[key] = now
        logger.warning(message, *args)
        return
    if now - seen >= _REPEAT_AFTER_S:
        _last_said[key] = now
        logger.warning("(still) " + message, *args)


def clear_repeat_suppression(key: str | None = None) -> None:
    """Forget what has been said, so a recurrence is reported in full.

    Called when a pass SUCCEEDS: the next failure after a good pass is new
    information, not a repeat, and suppressing it would hide a fault that had
    genuinely gone away and come back.
    """
    if key is None:
        _last_said.clear()
    else:
        _last_said.pop(key, None)


class MonitorPassIncomplete(RuntimeError):
    """At least one position could not be checked.

    Raised AFTER every other position in the pass has been swept, so the
    failure is loud without being contagious. Carries which positions failed,
    because "the monitor pass failed" is not actionable and "#41 could not be
    quoted" is.
    """


def _credential(tenant_id: str, sandbox: bool):
    from app.api_v2 import deps
    from app.platform.db.session import session_scope
    from app.tenancy import repository as tenants

    venue_name = "tradier_sandbox" if sandbox else "tradier"
    with session_scope() as db:
        return tenants.load_credential(db, tenant_id, venue_name, deps.keyring())


def run_pass(*, tenant_id: str) -> dict:
    """One sweep over one tenant's active positions."""
    events: list[str] = []
    db = session_factory()()
    try:
        rows = list(db.scalars(select(Position).where(
            Position.tenant_id == tenant_id,
            Position.status.in_(ACTIVE),
        )).all())
        if not rows:
            db.commit()
            heartbeat.record_pass(tenant_id)
            return {"checked": 0, "events": events}

        # Every position is checked even when an earlier one fails. The
        # comment here used to say exactly that while the code did the
        # opposite: it re-raised on the first failure, so one contract the
        # venue would not quote aborted the sweep and left every OTHER stop
        # on that account unwatched for the rest of the pass. A single bad
        # contract must not disarm the account.
        failures: list[str] = []
        for pos in rows:
            try:
                _check_one(db, tenant_id, pos, events)
            except Exception as exc:                    # noqa: BLE001
                _say_once(f"pos:{pos.id}", "monitor: position %s: %s",
                          pos.id, exc)
                events.append(f"#{pos.id} check failed: {exc}")
                failures.append(f"#{pos.id}: {exc}")
        db.commit()
    except Exception as exc:                            # noqa: BLE001
        db.rollback()
        heartbeat.record_failure(tenant_id, str(exc))
        raise
    finally:
        db.close()

    if failures:
        # Loud AFTER the sweep, not instead of it. The heartbeat is what stops
        # new entries when stops are unreliable, so a pass that could not
        # check everything must never be recorded as healthy -- but it still
        # had to check everything it could first.
        reason = "; ".join(failures)
        heartbeat.record_failure(tenant_id, reason)
        raise MonitorPassIncomplete(
            f"{len(failures)} of {len(rows)} positions could not be checked: "
            f"{reason}")

    # A clean pass resets the suppression, so if this breaks again it is
    # reported in full rather than swallowed as a repeat.
    clear_repeat_suppression(f"tenant:{tenant_id}")
    heartbeat.record_pass(tenant_id)
    return {"checked": len(rows), "events": events}


def sweep_all_tenants() -> list[dict]:
    """Every ACTIVE tenant -- not just the ones already holding something.

    The obvious version of this asked which tenants have active positions and
    swept only those. It deadlocked the guard it feeds: an operator with
    nothing open was never swept, so no heartbeat row was ever written, so
    ``seconds_since_last_pass`` was infinite, so guard 7 refused the entry
    that would have given them their first position. The monitor reported
    "never" and the operator could not get out of it from the desk.

    A tenant with nothing at risk is swept in the cheapest possible way --
    ``run_pass`` finds no rows and stamps the heartbeat -- and that stamp is
    the truthful one: there are no stops, so every stop is being watched.

    Each tenant is swept independently and a failure is contained: one
    operator's expired credential must not disarm another operator's stop.
    """
    from app.tenancy.models import Tenant

    out = []
    db = session_factory()()
    try:
        tenant_ids = {
            t.id for t in db.scalars(select(Tenant).where(
                Tenant.status == "active")).all()
        }
    finally:
        db.close()

    for tenant_id in sorted(tenant_ids):
        try:
            out.append(run_pass(tenant_id=tenant_id))
        except Exception as exc:                        # noqa: BLE001
            _say_once(f"tenant:{tenant_id}",
                      "monitor: tenant %s failed: %s", tenant_id, exc)
            out.append({"tenant_id": tenant_id, "error": str(exc)})
    return out


# ---- one position ---------------------------------------------------------

def _check_one(db, tenant_id: str, pos: Position, events: list[str]) -> None:
    cred = _credential(tenant_id, pos.venue_sandbox)
    sandbox = pos.venue_sandbox

    if pos.status == "pending":
        _check_pending(db, cred, pos, events, sandbox)
        return
    _check_open(db, cred, pos, events, sandbox)


def _check_pending(db, cred, pos: Position, events: list[str],
                   sandbox: bool) -> None:
    if pos.entry_price is None:
        order = venue_mod.order_status(pos.buy_order_id, cred=cred, sandbox=sandbox)
        state = (order.get("status") or "").lower()
        if state == "filled":
            pos.entry_price = float(order.get("avg_fill_price") or 0)
            pos.opened_at = pos.opened_at or utcnow()
            pos.note = (f"filled @ {pos.entry_price:.2f}; confirming the "
                        f"position before arming exits ({ARM_DELAY_S}s)")
            events.append(f"#{pos.id} filled @ {pos.entry_price:.2f}")
        elif state in ("canceled", "cancelled", "rejected", "expired"):
            pos.status = "failed"
            pos.closed_at = utcnow()
            pos.note = f"buy {state}; nothing at risk"
            events.append(f"#{pos.id} buy {state}")
        return

    # Filled. Wait out the arm delay, then confirm the holding really exists.
    waited = (utcnow() - (pos.opened_at or utcnow())).total_seconds()
    if waited < ARM_DELAY_S:
        return

    held = venue_mod.held_quantity(pos.occ_symbol, cred=cred, sandbox=sandbox)
    if held <= 0:
        # The contract IS owned; the books have not caught up. Say so once and
        # keep checking — giving up would leave it unmanaged.
        if "not on the books" not in (pos.note or ""):
            pos.note = (f"filled @ {pos.entry_price:.2f}; position not on the "
                        f"books yet — exits not armed")
            events.append(f"#{pos.id} filled but not on the books yet")
        return

    _arm_exits(db, cred, pos, events, sandbox, held)


def _arm_exits(db, cred, pos: Position, events: list[str], sandbox: bool,
               held: float) -> None:
    """Rest the target and the stop. Both, or say which is missing."""
    pos.tp_price, pos.sl_price = exit_prices(pos.entry_price, pos.tp_pct, pos.sl_pct)

    # Never rest more sells than the account holds: two sells against one
    # holding is an accidental short. Ask the ACCOUNT, not our own row —
    # another copy of this loop may already have armed it.
    resting = venue_mod.resting_sells(pos.occ_symbol, cred=cred, sandbox=sandbox)
    spoken_for = sum(abs(float(o.get("quantity") or 0)) for o in resting)
    if not pos.tp_order_id and spoken_for + pos.contracts > held:
        pos.note = (f"filled @ {pos.entry_price:.2f}; exits not armed — "
                    f"{spoken_for:g} of {held:g} held already have a resting sell")
        events.append(f"#{pos.id} refused a target: {spoken_for:g} resting vs "
                      f"{held:g} held")
        return

    if not pos.tp_order_id:
        placed = venue_mod.place_sell(
            cred=cred, underlying=pos.underlying, occ_symbol=pos.occ_symbol,
            quantity=pos.contracts, price=pos.tp_price, sandbox=sandbox)
        pos.tp_order_id = placed.order_id

    # The stop that survives this process dying.
    if not pos.stop_order_id:
        try:
            stop = venue_mod.place_stop(
                cred=cred, underlying=pos.underlying, occ_symbol=pos.occ_symbol,
                quantity=pos.contracts, stop_price=pos.sl_price, sandbox=sandbox)
            pos.stop_order_id = stop.order_id
            pos.stop_protection = "venue_resting"
        except Exception as exc:                        # noqa: BLE001
            # Failing to rest a stop is acceptable. Failing QUIETLY is not:
            # the operator would believe they had venue-side protection.
            pos.stop_protection = "monitored_only"
            logger.warning("position %s: venue refused the stop (%s); "
                           "monitored stop only", pos.id, exc)
            events.append(f"#{pos.id} venue refused the stop — monitored only")

    pos.status = "open"
    if pos.stop_protection == "venue_resting":
        pos.note = (f"filled @ {pos.entry_price:.2f}; TP {pos.tp_price:.2f} and "
                    f"stop {pos.sl_price:.2f} both resting at the venue")
    else:
        pos.note = (f"filled @ {pos.entry_price:.2f}; TP {pos.tp_price:.2f} "
                    f"resting, stop {pos.sl_price:.2f} MONITORED ONLY — no "
                    f"venue-side stop, protection ends if this process stops")
    events.append(f"#{pos.id} exits armed — TP {pos.tp_price:.2f}, "
                  f"SL {pos.sl_price:.2f} ({pos.stop_protection})")


def _check_open(db, cred, pos: Position, events: list[str],
                sandbox: bool) -> None:
    if pos.tp_order_id:
        tp = venue_mod.order_status(pos.tp_order_id, cred=cred, sandbox=sandbox)
        if (tp.get("status") or "").lower() == "filled":
            _finalise(pos, "tp_filled",
                      float(tp.get("avg_fill_price") or pos.tp_price or 0),
                      "target filled")
            # An orphaned stop on a sold position is how an accidental short
            # gets opened.
            if pos.stop_order_id:
                venue_mod.cancel_order(pos.stop_order_id, cred=cred, sandbox=sandbox)
            events.append(f"#{pos.id} target filled @ {pos.exit_price:.2f}")
            return

    if pos.stop_order_id:
        stop = venue_mod.order_status(pos.stop_order_id, cred=cred, sandbox=sandbox)
        if (stop.get("status") or "").lower() == "filled":
            _finalise(pos, "sl_filled",
                      float(stop.get("avg_fill_price") or pos.sl_price or 0),
                      "stop filled at the venue")
            if pos.tp_order_id:
                venue_mod.cancel_order(pos.tp_order_id, cred=cred, sandbox=sandbox)
            events.append(f"#{pos.id} stop filled @ {pos.exit_price:.2f}")
            return

    # Monitored stop. Only meaningful when no venue stop is resting; with one
    # in place the venue is faster than this loop will ever be.
    if pos.stop_protection != "venue_resting" and pos.sl_price:
        bid = venue_mod.bid_for(pos.occ_symbol, cred=cred, sandbox=sandbox)
        if bid is not None and bid <= pos.sl_price:
            # Cancel the target BEFORE selling: a sell that races its own
            # resting target double-sells the holding.
            if pos.tp_order_id:
                venue_mod.cancel_order(pos.tp_order_id, cred=cred, sandbox=sandbox)
            venue_mod.sell_to_close(
            cred=cred, underlying=pos.underlying, occ_symbol=pos.occ_symbol,
                quantity=pos.contracts, sandbox=sandbox)
            _finalise(pos, "sl_filled", bid,
                      f"monitored stop breached at {bid:.2f}")
            events.append(f"#{pos.id} monitored stop fired @ {bid:.2f}")


def _finalise(pos: Position, status: str, exit_price: float | None,
              note: str) -> None:
    pos.status = status
    pos.exit_price = exit_price
    if exit_price is not None and pos.entry_price is not None:
        pos.pnl_usd = round((exit_price - pos.entry_price) * 100 * pos.contracts, 2)
    pos.note = note
    pos.closed_at = utcnow()
