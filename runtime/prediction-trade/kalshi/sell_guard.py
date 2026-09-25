"""The one check every bot makes before it sells. Used by all of them.

Two failures kept happening across unrelated engines, and both are invisible
in the moment:

  SELLING WITH NO POSITION      A sell on an exchange is not a no-op when you
                                hold nothing -- it OPENS the opposite
                                position. A closed trade quietly becomes a new
                                live one that nobody chose and nothing is
                                watching.

  SELLING OVER A RESTING ORDER  Our own earlier order is still in the queue
                                and can fill at any moment. Sending a second
                                one sells the same contracts twice, and the
                                account ends up short the difference.

Both are cheap to prevent and expensive to discover afterwards, so the rule is
the same everywhere and lives here rather than in each engine:

    1. there IS a position on this ticker, on the side being sold
    2. there is NO pending or resting order on this ticker

    each read TWICE, ten seconds apart, and both readings must agree

A single reading of a portfolio endpoint is a snapshot -- it can be stale,
taken mid-settlement, or caught between a fill and the position update that
follows it. Two readings ten seconds apart is what turns it into a fact.

HOW IT PLUGS IN
Every Kalshi client in this project -- v4's, the commodity bots' own, and any
future one -- exposes the same ``await client.req(method, path, params=...)``.
So this module talks to the exchange itself rather than asking each engine to
hand over its own position and order helpers, and wiring it into an engine is
one call rather than an adapter.

    ok = await sell_guard.confirm(client, ticker, side, want=contracts)
    if not ok:
        return
    ...send the sell...

It is FAIL-SAFE by construction: any error reading either endpoint refuses the
sell rather than assuming the coast is clear. A guard that fails open is not a
guard.
"""

from __future__ import annotations

import asyncio
import os

# Seconds between the two readings. Env-overridable because it is a real
# trade-off rather than a constant of nature: it is dead time on an exit, and
# on a fifteen-minute market ten seconds of it is the price of not
# double-selling. Set SELL_CONFIRM_DELAY_S=0 to make the second reading
# immediate -- which keeps the double-read but removes the pause.
CONFIRM_DELAY_S = float(os.getenv("SELL_CONFIRM_DELAY_S", "10"))

# Kalshi paths. Named here so a change is one edit rather than six.
POSITIONS_PATH = "/portfolio/positions"
ORDERS_PATH = "/portfolio/orders"

# Order states that mean "this order can still fill". Anything in one of these
# blocks a sell; anything else (executed, canceled) does not.
LIVE_ORDER_STATES = {"resting", "pending", "open", "queued"}


def _say(log, message: str) -> None:
    """Log through whatever the calling engine uses.

    The engines in this project variously use ``print``, a module-level
    ``log()`` and a ``logging`` logger. Rather than impose one, take the
    callable -- a guard nobody can see the output of is a guard nobody trusts.
    """
    try:
        (log or print)(message)
    except Exception:                                   # noqa: BLE001
        pass


def filled_count(response: dict | None) -> float:
    """How many contracts an order response actually FILLED.

    ACCEPTED IS NOT FILLED. An order that finds no counterparty is accepted,
    cancelled, and comes back as a perfectly ordinary response with
    ``fill_count_fp`` 0. Reading that as an entry means announcing a position,
    resting a take-profit against nothing and arming a stop on nothing -- so
    every engine asks this before it treats a buy as done.
    """
    if not response:
        return 0.0
    body = response.get("order") if isinstance(response, dict) else None
    body = body if isinstance(body, dict) else (response or {})
    for key in ("fill_count_fp", "fill_count", "count"):
        raw = body.get(key)
        if raw in (None, ""):
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return 0.0


async def held_contracts(client, ticker: str, side: str | None = None) -> int:
    """Contracts held on ``ticker``, 0 if none or if they are on the other leg.

    Selling the leg we do not hold opens a position rather than closing one,
    so a mismatch is reported as nothing to sell rather than as a size.
    """
    data = await client.req("GET", POSITIONS_PATH, params={"ticker": ticker})
    for position in data.get("market_positions", []):
        if position.get("ticker") != ticker:
            continue
        raw = position.get("position_fp", position.get("position", 0))
        try:
            signed = float(raw or 0)
        except (TypeError, ValueError):
            return 0
        if side is not None:
            # Kalshi signs the position: positive is YES, negative is NO.
            held_side = "yes" if signed >= 0 else "no"
            if signed != 0 and held_side != side:
                return 0
        return abs(int(signed))
    return 0


async def live_orders(client, ticker: str) -> list[dict]:
    """Orders on ``ticker`` that can still fill.

    Asked WITHOUT a status filter and filtered here, because an engine that
    asks only for "resting" misses an order that is momentarily "pending" --
    and a pending order fills just as hard as a resting one.
    """
    data = await client.req("GET", ORDERS_PATH, params={"ticker": ticker})
    out = []
    for order in data.get("orders", []):
        if order.get("ticker") != ticker:
            continue
        if str(order.get("status") or "").lower() in LIVE_ORDER_STATES:
            out.append(order)
    return out


async def _read(client, ticker: str, side: str | None) -> tuple[int, int]:
    return (await held_contracts(client, ticker, side),
            len(await live_orders(client, ticker)))


async def confirm(client, ticker: str, side: str | None = None, *,
                  want: int | float | None = None, why: str = "sell",
                  log=None, delay_s: float | None = None) -> int:
    """Both preconditions, each read twice, ten seconds apart.

    Returns the number of contracts it is safe to sell RIGHT NOW, or 0 when it
    is not safe to sell at all. 0 is falsy, so a caller that forgets to check
    still cannot proceed with a size.

    The size returned is the SMALLER of the two readings, capped at ``want``:
    if the position shrank between them, the second reading is the one that is
    still true.

    Never raises. A guard that throws just moves the failure into the caller's
    error handler, where it is one more exception among many -- and the caller
    is holding a live position at the time. Every refusal is logged with its
    reason, because a sell that silently does not happen is its own kind of
    bug.
    """
    pause = CONFIRM_DELAY_S if delay_s is None else delay_s
    leg = f" {side.upper()}" if side else ""

    try:
        held_1, live_1 = await _read(client, ticker, side)
    except Exception as exc:                            # noqa: BLE001
        _say(log, f"  [{why}] {ticker}: could not read position/orders "
                  f"({type(exc).__name__}: {exc}) -- NOTHING SOLD (fail safe)")
        return 0
    _say(log, f"  [{why}] {ticker}: check 1/2 -> {held_1}{leg} held, "
              f"{live_1} order(s) still live")
    if held_1 <= 0:
        _say(log, f"  [{why}] {ticker}: no position on the{leg or ' given'} "
                  f"leg -- NOTHING SOLD")
        return 0
    if live_1:
        _say(log, f"  [{why}] {ticker}: {live_1} order(s) pending/resting -- "
                  f"NOTHING SOLD until they clear")
        return 0

    if pause > 0:
        await asyncio.sleep(pause)

    try:
        held_2, live_2 = await _read(client, ticker, side)
    except Exception as exc:                            # noqa: BLE001
        _say(log, f"  [{why}] {ticker}: could not re-read position/orders "
                  f"({type(exc).__name__}: {exc}) -- NOTHING SOLD (fail safe)")
        return 0
    _say(log, f"  [{why}] {ticker}: check 2/2 -> {held_2}{leg} held, "
              f"{live_2} order(s) still live")
    if held_2 <= 0:
        _say(log, f"  [{why}] {ticker}: the position was gone on the second "
                  f"reading -- NOTHING SOLD")
        return 0
    if live_2:
        _say(log, f"  [{why}] {ticker}: {live_2} order(s) appeared on the "
                  f"second reading -- NOTHING SOLD")
        return 0

    confirmed = min(held_1, held_2)
    if want is not None:
        try:
            confirmed = min(confirmed, int(want))
        except (TypeError, ValueError):
            pass
    if confirmed <= 0:
        _say(log, f"  [{why}] {ticker}: nothing left to sell after clamping "
                  f"to {want} -- NOTHING SOLD")
        return 0
    _say(log, f"  [{why}] {ticker}: confirmed twice -- {confirmed} "
              f"contract(s) clear to sell")
    return confirmed


async def cancel_live(client, ticker: str, *, log=None) -> int:
    """Cancel this ticker's live orders so a sell can pass the guard.

    Scoped to ONE ticker rather than the account: these bots share an account
    with everything else the desk is running, and cancelling everything to
    exit one position would pull other bots' orders off the book.

    The caller needs this when its OWN take-profit is what the guard is
    refusing to sell over -- without it a resting take-profit would block the
    stop that is supposed to override it, which is the guard defeating the
    thing it exists to protect.
    """
    try:
        orders = await live_orders(client, ticker)
    except Exception as exc:                            # noqa: BLE001
        _say(log, f"  {ticker}: could not list orders to cancel "
                  f"({type(exc).__name__}: {exc})")
        return 0
    if not orders:
        return 0
    done = 0
    for order in orders:
        order_id = order.get("order_id") or order.get("id")
        if not order_id:
            continue
        try:
            await client.req("DELETE", f"/portfolio/events/orders/{order_id}")
            done += 1
        except Exception as exc:                        # noqa: BLE001
            _say(log, f"  {ticker}: cancel of {order_id} failed "
                      f"({type(exc).__name__}: {exc})")
    _say(log, f"  {ticker}: cancelled {done}/{len(orders)} live order(s)")
    return done
