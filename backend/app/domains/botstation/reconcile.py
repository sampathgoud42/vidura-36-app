"""Resolving trades the bots opened and never closed.

A bot records a trade when it ENTERS. It cannot record the outcome, because
the outcome happens later -- at settlement, or when a later process sells --
long after the process that opened the position has exited. So an ``open`` row
in the ledger means "nobody has looked since", not "still running", and left
alone it stays open forever while the bot's own entry-time estimate stands in
for a realised number that exists at the exchange.

That is what this module fixes: for every open row, ask Kalshi what actually
happened, write the real P&L, and close it.

The exchange is asked in a deliberate order, cheapest and most authoritative
first:

  1. positions    net contracts still held, and Kalshi's OWN realized P&L.
                  A non-zero position means the trade really IS open and must
                  be left alone -- this is the check that stops the reconciler
                  from closing live trades. A flat position means finished,
                  and realized_pnl_dollars is the answer, fees included.
  2. settlements  the market resolved. Gives won/lost specifically, from
                  market_result, rather than inferring it from a sign.
  3. fills        reconstruct the round trip from executions. Only for
                  markets old enough to have aged out of both feeds above.

If none of the three knows the ticker, the row is closed with NO P&L rather
than with zero. A fabricated 0.00 is worse than a null: it is silently
averaged into every performance figure on the desk, and nothing downstream can
tell it apart from a trade that genuinely broke even.

UNITS, because they are not uniform and getting them wrong is invisible:

    revenue                  CENTS   (integer)
    *_total_cost_dollars     DOLLARS (decimal string)
    fee_cost                 DOLLARS (decimal string)
    realized_pnl_dollars     DOLLARS (decimal string)
    position_fp, count_fp    CONTRACTS (decimal string)

The previous implementation read ``yes_total_cost``, which does not exist. It
came back None, the cost basis became zero, fees were ignored, and every P&L
was overstated by the entire amount staked -- a wrong number that looks
entirely plausible on a board.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import and_, or_, select

from app.domains.botstation.models import BotTrade
from app.platform.db.base import utcnow

logger = logging.getLogger(__name__)

# Below this many contracts a position counts as flat. Kalshi reports
# fractional contracts, so an exact == 0 comparison on a float parsed from a
# decimal string is not something to rely on.
FLAT_EPSILON = 0.0001

# What each resolution path means, in words the operator can act on.
RESOLUTION_NOTES = {
    "settlement": "the market resolved; P&L is revenue less cost and fees",
    "position": "the position is flat; P&L is the exchange's own realised "
                "figure for this market",
    "fills": "reconstructed from the executions on this market",
    "no venue record": "the account has no position, fill or settlement for "
                       "this market — the bot recorded an entry that never "
                       "became a filled order, so there is no P&L to record",
}


def _num(value, default: float = 0.0) -> float:
    """Kalshi sends decimals as strings. None and "" are not zero by accident
    here -- they are explicitly defaulted, so a missing field cannot silently
    become a number that gets written to the ledger."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _status_for(pnl: float | None) -> str:
    if pnl is None:
        return "closed"
    if pnl > 0:
        return "won"
    if pnl < 0:
        return "lost"
    return "settled"


def _from_settlement(row: dict) -> tuple[float, str]:
    """(realised P&L in dollars, status) for a resolved market."""
    revenue = _num(row.get("revenue")) / 100.0          # cents -> dollars
    cost = (_num(row.get("yes_total_cost_dollars"))
            + _num(row.get("no_total_cost_dollars")))
    fees = _num(row.get("fee_cost"))
    pnl = round(revenue - cost - fees, 2)
    # market_result names the outcome directly, so a genuinely break-even
    # settlement is not reported as though nobody knows what happened.
    result = (row.get("market_result") or "").lower()
    if result in ("yes", "no"):
        return pnl, ("won" if pnl > 0 else "lost" if pnl < 0 else "settled")
    return pnl, _status_for(pnl)


def _entry_from_fills(rows: list[dict]) -> float | None:
    """What the BUYS cost, fees included, reconstructed from executions.

    The companion to _from_fills, which returns the round trip. This returns
    only the money that went out, because a row missing its entry cannot have
    an exit computed for it -- and a row with neither is swept forever without
    ever resolving, which is a loop rather than a fix.
    """
    cost = 0.0
    seen = False
    for fill in rows or []:
        if (fill.get("action") or "").lower() != "buy":
            continue
        side = (fill.get("side") or fill.get("outcome_side") or "yes").lower()
        price = _num(fill.get(f"{side}_price_dollars"))
        count = _num(fill.get("count_fp"))
        if not count:
            continue
        cost += price * count + _num(fill.get("fee_cost"))
        seen = True
    return round(cost, 4) if seen else None


def _from_fills(rows: list[dict]) -> tuple[float | None, int]:
    """(realised P&L in dollars, contracts) reconstructed from executions.

    Buys are cash out, sells are cash in, fees always out. Returns None when
    the fills do not describe a completed round trip -- a half-reconstructed
    number is not better than admitting we cannot tell.
    """
    if not rows:
        return None, 0
    cash = 0.0
    bought = sold = 0.0
    for fill in rows:
        side = (fill.get("side") or fill.get("outcome_side") or "yes").lower()
        price = _num(fill.get(f"{side}_price_dollars"))
        count = _num(fill.get("count_fp"))
        fee = _num(fill.get("fee_cost"))
        if (fill.get("action") or "").lower() == "buy":
            cash -= price * count
            bought += count
        else:
            cash += price * count
            sold += count
        cash -= fee
    if bought <= 0 or abs(bought - sold) > FLAT_EPSILON:
        # Still holding, or the feed only has one leg of the trade.
        return None, int(round(bought))
    return round(cash, 2), int(round(bought))


def _index(rows: list[dict], *keys: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for row in rows:
        for key in keys:
            ticker = str(row.get(key) or "").strip()
            if ticker:
                out.setdefault(ticker, row)
                break
    return out


def _group(rows: list[dict], *keys: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in rows:
        for key in keys:
            ticker = str(row.get(key) or "").strip()
            if ticker:
                out.setdefault(ticker, []).append(row)
                break
    return out


# How long a row must have been open before the sweeper will touch it.
#
# A trade placed seconds ago has no position at the exchange yet -- the fill
# takes a moment to appear, as the RFQ read-back showed -- and a sweeper that
# ran immediately would see "no position" and close a trade that had just been
# opened. Six hours is far past any settlement lag and far short of a
# same-day market resolving.
DEFAULT_MIN_AGE_HOURS = 6.0

# How many sweeps may miss a trade before it is written off. Three, at six
# hours apart, is eighteen hours of the exchange having no position, no
# settlement and no fill for the ticker -- long past any plausible lag.
MAX_RESOLVE_ATTEMPTS = 3


def resolve_open_trades(db, tenant_id: str, cred, *,
                        apply: bool = False,
                        min_age_hours: float = DEFAULT_MIN_AGE_HOURS) -> dict:
    """Close every open ledger row the exchange can account for.

    Only rows OLDER than ``min_age_hours`` are considered. A younger one is
    left alone whatever the exchange says about it: at that age "no position"
    means "not visible yet" at least as often as it means "gone".

    Returns what it did (or would do) per trade, so the caller can show the
    operator the change before it is written and afterwards explain it.
    """
    from datetime import timedelta

    from app.domains.botstation import venue as kalshi

    # Two kinds of unfinished row, swept together because the answer comes
    # from the same three sources:
    #
    #   still OPEN          -- nobody has looked since the bot entered
    #   CLOSED with no exit -- somebody looked, learned the trade was over,
    #                          and never learned what it returned
    #
    # The second is the more misleading of the two. It reads as settled on the
    # desk while its Exit column is blank, so it contributes nothing to P&L
    # and nobody can tell whether that is a real zero or a gap.
    unfinished = or_(
        BotTrade.status == "open",
        and_(BotTrade.status != "open", BotTrade.exit_usd.is_(None)),
    )
    scope = [BotTrade.tenant_id == tenant_id, unfinished]
    if min_age_hours and min_age_hours > 0:
        cutoff = utcnow() - timedelta(hours=float(min_age_hours))
        # A row with no opened_at has no age to judge, so it is swept rather
        # than left forever: an undated row is exactly the kind of stale entry
        # this exists to clear.
        scope.append(or_(BotTrade.opened_at.is_(None),
                         BotTrade.opened_at <= cutoff))
    open_rows = list(db.scalars(select(BotTrade).where(*scope)).all())
    if not open_rows:
        return {"candidates": 0, "resolved": 0, "still_open": 0, "applied": 0,
                "preview": not apply, "changes": [],
                "detail": "nothing is waiting on settlement"}

    positions = _index(kalshi.positions(cred), "ticker")
    settlements = _index(kalshi.settlements(cred, limit=1000), "ticker")
    fills_by_ticker: dict[str, list[dict]] | None = None

    changes: list[dict] = []
    still_open = 0

    for trade in open_rows:
        ticker = (trade.ticker or "").strip()
        position = positions.get(ticker)

        # 1. Still holding? Then it is genuinely open. This is the guard that
        #    keeps the reconciler from closing a live trade out from under a
        #    running bot.
        if (trade.status == "open" and position is not None
                and abs(_num(position.get("position_fp"))) > FLAT_EPSILON):
            still_open += 1
            continue

        pnl: float | None = None
        status = "closed"
        via = None

        settlement = settlements.get(ticker)
        if settlement is not None:
            pnl, status = _from_settlement(settlement)
            via = "settlement"
        elif position is not None:
            # Flat, and the exchange has already computed the round trip.
            pnl = round(_num(position.get("realized_pnl_dollars")), 2)
            status = _status_for(pnl)
            via = "position"
        else:
            if fills_by_ticker is None:
                fills_by_ticker = _group(kalshi.fills(cred, limit=1000),
                                         "ticker", "market_ticker")
            pnl, _contracts = _from_fills(fills_by_ticker.get(ticker, []))
            if pnl is not None:
                status = _status_for(pnl)
                via = "fills"
            else:
                # Nothing anywhere: no position, no settlement, no fill.
                #
                # That is NOT yet a conclusion. A sweep can miss a trade the
                # exchange has not caught up on, and closing on the first miss
                # is how a live position gets written off. So the miss is
                # COUNTED and the row left as it is, to be asked again on the
                # next sweep.
                #
                # After MAX_RESOLVE_ATTEMPTS misses -- three sweeps, eighteen
                # hours -- the answer is not coming and saying so is more
                # honest than a row that waits forever.
                status = trade.status
                pnl = None
                via = "no venue record"
                if trade.resolve_attempts + 1 >= MAX_RESOLVE_ATTEMPTS:
                    status = "not_found"
                    via = (f"no venue record after "
                           f"{MAX_RESOLVE_ATTEMPTS} sweeps")

        changes.append({
            "id": trade.id, "ticker": ticker, "bot_key": trade.bot_key,
            "from_status": trade.status, "to_status": status,
            "estimated_pnl": trade.realized_pnl,
            "resolved_pnl": pnl, "via": via,
        })

        if apply:
            if via.startswith("no venue record"):
                trade.resolve_attempts = (trade.resolve_attempts or 0) + 1
            if status == "not_found":
                # Zero, not null. A trade the exchange has no record of
                # returned nothing, and the desk should show that as a
                # settled zero rather than a blank that reads like a pending
                # answer.
                trade.exit_usd = 0.0
                trade.closed_at = trade.closed_at or utcnow()
            trade.status = status
            # The cash that went out, if the row never recorded it. Older rows
            # predate the entry_usd column and rows written before the fill
            # was visible have it null -- and without it there is nothing to
            # add the P&L to, so the Exit column stays blank however many
            # times this runs.
            if trade.entry_usd is None:
                if fills_by_ticker is None:
                    fills_by_ticker = _group(kalshi.fills(cred, limit=1000),
                                             "ticker", "market_ticker")
                recovered = _entry_from_fills(fills_by_ticker.get(ticker, []))
                if recovered:
                    trade.entry_usd = recovered
            # Only overwrite when we actually learned something. An unknown
            # outcome must not erase the bot's own estimate AND leave nothing
            # in its place.
            if pnl is not None:
                trade.realized_pnl = pnl
                # What came BACK, in cash, for the ledger's Exit column.
                # Derived from the entry and the realised P&L rather than
                # read separately: Kalshi's realized_pnl_dollars is already
                # net of fees, so exit = what it cost plus what it made, and
                # a loser lands at 0 without needing a special case.
                if trade.entry_usd is not None:
                    trade.exit_usd = round(
                        max(0.0, float(trade.entry_usd) + float(pnl)), 4)
            trade.closed_at = trade.closed_at or utcnow()
            trade.reconciled_at = utcnow()
            # WHY it closed, kept on the row. Months later "closed, P&L null"
            # is unreadable; "the account has no position, fill or settlement
            # for this market" is a fact somebody can act on -- it usually
            # means the bot recorded an intent that never became an order.
            # bot_trade.raw is TEXT, not a JSON column, so it takes a string.
            # Merged rather than replaced: the bot's own entry-time payload is
            # the only record of what it thought it was doing, and losing that
            # to add a reconciliation note would be a poor trade.
            try:
                existing = json.loads(trade.raw) if trade.raw else {}
                if not isinstance(existing, dict):
                    existing = {"original": existing}
            except (TypeError, ValueError):
                existing = {"original": trade.raw}
            trade.raw = json.dumps({**existing, "reconciliation": {
                "at": utcnow().isoformat(), "via": via, "resolved_pnl": pnl,
                "note": (RESOLUTION_NOTES.get(via) or f"resolved via {via}"),
            }})

    if apply and changes:
        db.commit()

    return {
        "candidates": len(open_rows),
        "resolved": len(changes),
        "still_open": still_open,
        "applied": len(changes) if apply else 0,
        "preview": not apply,
        "changes": changes,
        "detail": ("resolved against Kalshi" if apply else
                   "preview only — re-send with apply=true to write"),
    }


def sweep_all_tenants(*, apply: bool = True,
                      min_age_hours: float = DEFAULT_MIN_AGE_HOURS
                      ) -> list[dict]:
    """Resolve open trades for every operator that has any.

    Each operator is swept independently and a failure is contained: one
    expired Kalshi credential must not stop another operator's ledger from
    being reconciled.
    """
    from app.api_v2 import deps
    from app.platform.db.session import session_scope
    from app.tenancy import repository as tenants
    from app.tenancy.models import Tenant

    out = []
    with session_scope() as db:
        tenant_ids = sorted({
            r[0] for r in db.execute(
                select(BotTrade.tenant_id).where(BotTrade.status == "open"))
        })
        active = {t.id for t in db.scalars(
            select(Tenant).where(Tenant.status == "active")).all()}

    for tenant_id in tenant_ids:
        if tenant_id not in active:
            continue
        try:
            with session_scope() as db:
                cred = tenants.load_credential(db, tenant_id, "kalshi",
                                               deps.keyring())
                result = resolve_open_trades(db, tenant_id, cred, apply=apply,
                                       min_age_hours=min_age_hours)
            out.append({"tenant_id": tenant_id, **result})
        except Exception as exc:                        # noqa: BLE001
            logger.warning("reconcile: tenant %s failed: %s", tenant_id, exc)
            out.append({"tenant_id": tenant_id, "error": str(exc)})
    return out
