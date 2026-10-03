"""Signal trades: a DMI signal on the Bot Station, bought by hand on the
asset's Kalshi fifteen-minute market, and watched until it is out.

The commodity and crypto strips read a direction from 1m/2m DMI agreement --
CALL or PUT, with a check mark when 5m agrees too. This turns one reading into
a position, after the operator has seen and confirmed what it will be:

    CALL -> buy YES (the price finishes up)       PUT -> buy NO
    "mixed" (1m and 2m disagree) is not a signal, and is refused

    entered only while that side's BID is strictly between 35c and 70c, at
    least a minute before the quarter closes, one open trade per market

    bought AT MARKET: an immediate-or-cancel buy at the ask (plus a few cents
    of room for the book to move), so it fills against what is offered or not
    at all -- and nothing rests. A resting order has to reserve cash on the
    shard the market settles on, which is why the 15-minute bots' orders came
    back insufficient_balance on a funded account.

    take-profit +20% and stop-loss -40% on the price actually paid, both
    watched by the background loop every POLL_S and both exited the same way:
    an immediate-or-cancel sell, after reading the position again. Nothing is
    sold that is not held -- a sell with no position OPENS the opposite one.

    still held when the quarter closes: left to settle at expiry. The ledger's
    own reconciler records how it ended.

RISKY-BUY is the other way in: the same market buy, but the 35-70c bid gate
is skipped and nothing watches the position -- no take-profit, no stop-loss.
It is recorded as ``unwatched``, and the watch never touches it. A watched
trade on the same market sells only what IT bought, never these.

Every row in ``signal_trade`` with status ``watching`` is a live watch. The
loop reads them from the database on every pass, so a restart of this process
pauses the watch for as long as the restart takes and no longer.
"""

from __future__ import annotations

import json
import logging
import math
import time
from datetime import datetime, timezone

from sqlalchemy import select

logger = logging.getLogger(__name__)

BID_FLOOR_C = 35.0          # exclusive: "strictly between 35 and 70"
BID_CEIL_C = 70.0           # exclusive
TP_PCT = 20.0
SL_PCT = 40.0
# The most an entry pays above the ask it was shown. A market order with no
# ceiling is an order to pay whatever is offered, and a fifteen-minute book is
# thin enough for that to be a different price.
ENTRY_SLIPPAGE_C = 3
# The most a stop-loss exit gives up below the bid. A stop is the one order
# that must fill, so it reaches a little; a take-profit sells at its price or
# better, or waits.
EXIT_SLIPPAGE_C = 3
MIN_SECONDS_LEFT = 60
POLL_S = 2.0
DEFAULT_CONTRACTS = 10
MAX_CONTRACTS = 100
BOT_KEY = "signal15"
SIDE_FOR = {"call": "yes", "put": "no"}


class SignalTradeRefused(ValueError):
    """Refused before anything was sent, with the reason in words."""


# ---- what is being traded ---------------------------------------------------

def market_for(asset: str):
    """The catalogue's fifteen-minute market for a strip row, or None.

    Commodity rows are keyed by their bot (gold15, oil15) and crypto rows by
    coin (btc, eth). Both name the same catalogue entry: gold15 and gold are
    gold-15. Oil's series is KXWTI15M -- the catalogue knows; KXOIL15M lists
    nothing at all.
    """
    from app.domains.botstation import monitor

    key = (asset or "").strip().lower()
    if key.endswith("15"):
        key = key[:-2]
    return monitor.BY_KEY.get(f"{key}-15")


def _cents(dollars) -> float | None:
    """A Kalshi dollar quote in cents. None when nothing is quoted -- a zero
    bid is nobody buying, and an ask of a dollar is nobody selling."""
    try:
        value = float(dollars)
    except (TypeError, ValueError):
        return None
    cents = round(value * 100.0, 1)
    return None if cents <= 0 or cents >= 100 else cents


def side_quote(market: dict, side: str) -> tuple[float | None, float | None]:
    """(bid, ask) in cents on the side a trade takes. The NO side is read as
    quoted and falls back to the mirror of YES, which every book satisfies."""
    yes_bid = _cents(market.get("yes_bid_dollars"))
    yes_ask = _cents(market.get("yes_ask_dollars"))
    if side == "yes":
        return yes_bid, yes_ask
    no_bid = _cents(market.get("no_bid_dollars"))
    no_ask = _cents(market.get("no_ask_dollars"))
    if no_bid is None and yes_ask is not None:
        no_bid = round(100.0 - yes_ask, 1)
    if no_ask is None and yes_bid is not None:
        no_ask = round(100.0 - yes_bid, 1)
    return no_bid, no_ask


def tp_price(entry_c: float) -> float:
    """+20% on what was paid, in whole cents, rounded UP so the target is
    never less than twenty per cent -- and never above 99, which cannot sell."""
    return float(min(99, math.ceil(entry_c * (1 + TP_PCT / 100.0) - 1e-9)))


def sl_price(entry_c: float) -> float:
    """-40% on what was paid, in whole cents, rounded DOWN, never below 1."""
    return float(max(1, math.floor(entry_c * (1 - SL_PCT / 100.0) + 1e-9)))


def _parse(stamp) -> datetime | None:
    if not stamp:
        return None
    try:
        out = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return out if out.tzinfo else out.replace(tzinfo=timezone.utc)


def _naive_utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def current_market(client, series: str) -> dict | None:
    """The quarter trading RIGHT NOW: the open binary market closing soonest.

    The same rule the price monitor uses -- the earliest close, never the
    first row, because the order of /markets is not promised.
    """
    data = client.request("GET", "/markets", params={
        "series_ticker": series, "status": "open", "limit": 10})
    now = _now()
    best: tuple[datetime, dict] | None = None
    for market in data.get("markets") or []:
        if str(market.get("market_type") or "binary").lower() != "binary":
            continue
        close = _parse(market.get("close_time"))
        if close is None or close <= now:
            continue
        if best is None or close < best[0]:
            best = (close, market)
    return best[1] if best else None


def _market(client, ticker: str) -> dict | None:
    return (client.request("GET", f"/markets/{ticker}") or {}).get("market")


def held(client, ticker: str, side: str) -> float:
    """Contracts held on ``ticker`` on ``side``; 0 when flat or on the other
    side. Kalshi signs the position: positive is YES, negative is NO."""
    data = client.request("GET", "/portfolio/positions", params={"ticker": ticker})
    for row in data.get("market_positions") or []:
        if row.get("ticker") != ticker:
            continue
        try:
            signed = float(row.get("position_fp", row.get("position", 0)) or 0)
        except (TypeError, ValueError):
            return 0.0
        if signed > 0 and side == "yes":
            return signed
        if signed < 0 and side == "no":
            return -signed
        return 0.0
    return 0.0


def shard_cash(client, index) -> float | None:
    """Cash on one exchange shard, in dollars, or None if it cannot be read.

    Every fifteen-minute market settles on shard 2, and an order there spends
    only what that shard holds -- the total the Kalshi app shows is not what
    an API order can reach. The form shows this number beside the cost so a
    refusal is not a surprise.
    """
    if index is None:
        return None
    try:
        data = client.request("GET", "/portfolio/balance")
    except Exception:                                   # noqa: BLE001
        return None
    for row in data.get("balance_breakdown") or []:
        try:
            if int(row.get("exchange_index", -1)) == int(index):
                return round(float(row.get("balance") or 0), 4)
        except (TypeError, ValueError):
            continue
    return None


def filled_count(order: dict | None) -> float:
    """ACCEPTED IS NOT FILLED. An immediate-or-cancel order that meets nobody
    comes back as an ordinary response with a fill count of zero."""
    if not order:
        return 0.0
    body = order.get("order") if isinstance(order.get("order"), dict) else order
    for key in ("fill_count_fp", "fill_count"):
        raw = body.get(key)
        if raw in (None, ""):
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return 0.0


def _order_id(order) -> str:
    body = order.get("order") if isinstance((order or {}).get("order"), dict) else (order or {})
    return str(body.get("order_id") or "")


def order_costs(client, order_id: str) -> dict | None:
    """What an order really cost, from the exchange's own record of it.

    The V2 create response does not carry it -- an order id, a fill count
    and at most an average price -- which is how every signal trade came to
    be booked at its LIMIT: SOL bought at 51c and 43c was recorded at 54c and
    44c, and its take-profit and stop-loss were measured from those. The
    order's record has the fill cost and the fees, in dollars.

    The cost is of the contracts the order ACQUIRED. For a buy that is the
    side bought; for a sale it is the OTHER side -- on one book, selling NO
    is buying YES -- so a sale's price on the side sold is 100 less the cost
    per contract. None when the record cannot be read or shows no fill.
    """
    if not order_id:
        return None
    try:
        d = client.request("GET", f"/portfolio/orders/{order_id}")
    except Exception as exc:                            # noqa: BLE001
        logger.warning("signal trade: order %s could not be read back (%s)",
                       order_id, type(exc).__name__)
        return None
    body = d.get("order") if isinstance(d.get("order"), dict) else d

    def num(key: str) -> float:
        try:
            return float(body.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    filled = num("fill_count_fp") or num("fill_count")
    cost = num("taker_fill_cost_dollars") + num("maker_fill_cost_dollars")
    if filled <= 0 or cost <= 0:
        return None
    return {"filled": filled, "cost_usd": cost,
            "fees_usd": num("taker_fees_dollars") + num("maker_fees_dollars")}


def _response_fill(order: dict, side: str, limit_c: float) -> tuple[float, float]:
    """(price, fee) per contract in cents on ``side``, from the create
    response alone -- only when the order's record could not be read.

    Its average is a price on the YES book, as every V2 order price is: a NO
    side's is 100 less. With no average at all, the limit -- a buy can only
    have paid less, a sale only have got more.
    """
    body = order.get("order") if isinstance(order.get("order"), dict) else order
    try:
        book_c = float(body.get("average_fill_price")) * 100.0
    except (TypeError, ValueError):
        return float(limit_c), 0.0
    try:
        fee_c = float(body.get("average_fee_paid") or 0) * 100.0
    except (TypeError, ValueError):
        fee_c = 0.0
    return round(book_c if side == "yes" else 100.0 - book_c, 2), round(fee_c, 4)


def _refusal(exc: Exception) -> str:
    """The exchange's reason, in a form the desk can show. Kalshi's error
    bodies carry a code and a message and never the key; the rest of the
    exception text is not passed on."""
    body = getattr(exc, "body", "") or ""
    try:
        err = (json.loads(body) or {}).get("error") or {}
        code, message = err.get("code") or "", err.get("message") or ""
    except (ValueError, AttributeError):
        code, message = "", ""
    status = getattr(exc, "status_code", None)
    if code or message:
        return f"Kalshi refused it ({status} {code}): {message}".strip()
    return f"Kalshi refused it ({type(exc).__name__}{f' {status}' if status else ''})"


def current_signal(asset: str, tradier_cred=None) -> dict | None:
    """The strip's latest row for this asset, from the boards' own snapshot
    (cached for under a minute, the same reading the strip shows)."""
    from app.domains.trading.market import commodities, crypto

    key = (asset or "").strip().lower()
    snap = (commodities.snapshot(tradier_cred, sandbox=True) if key.endswith("15")
            else crypto.snapshot())
    for row in snap.get("rows") or []:
        if str(row.get("bot") or "").strip().lower() == key:
            return row
    return None


def _label(signal) -> str:
    return {"call": "CALL", "put": "PUT"}.get(signal or "", "mixed")


# ---- preview ------------------------------------------------------------------

def preview(cred, *, asset: str, signal: str | None, confirms: bool = False) -> dict:
    """Everything the confirmation form shows. Sends nothing, buys nothing."""
    from app.domains.botstation import venue

    sig = (signal or "").strip().lower()
    side = SIDE_FOR.get(sig)
    if side is None:
        return {"ok": False, "valid_signal": False, "asset": asset,
                "detail": "NOT a valid signal — 1m and 2m disagree (mixed), "
                          "so there is no direction to trade."}
    spec = market_for(asset)
    if spec is None:
        return {"ok": False, "valid_signal": True, "asset": asset,
                "detail": f"Kalshi lists no fifteen-minute market for {asset}."}

    client = venue._client(cred)
    try:
        market = current_market(client, spec.series)
        if market is None:
            return {"ok": False, "valid_signal": True, "asset": asset,
                    "series": spec.series, "label": spec.label,
                    "detail": f"No {spec.series} market is open right now — "
                              "out of session, or between quarters."}
        bid, ask = side_quote(market, side)
        cash = shard_cash(client, market.get("exchange_index"))
    finally:
        client.close()

    close = _parse(market.get("close_time"))
    left = int((close - _now()).total_seconds()) if close else 0
    problems = []
    if bid is None:
        problems.append("nobody is bidding on that side")
    elif not BID_FLOOR_C < bid < BID_CEIL_C:
        problems.append(f"the bid is {bid:g}c — outside 35–70c (it must be strictly between)")
    if ask is None:
        problems.append("nothing is offered on that side to buy")
    if left < MIN_SECONDS_LEFT:
        problems.append(f"this quarter closes in {max(0, left)}s — too late to enter")
    estimate = ask if ask is not None else bid
    return {
        "ok": not problems, "valid_signal": True,
        "asset": asset, "label": spec.label, "series": spec.series,
        "ticker": market.get("ticker"), "title": market.get("title"),
        "signal": sig, "confirms": bool(confirms), "side": side,
        "bid_c": bid, "ask_c": ask,
        "close_time": market.get("close_time"), "seconds_left": max(0, left),
        "bid_range_c": [BID_FLOOR_C, BID_CEIL_C],
        "tp_pct": TP_PCT, "sl_pct": SL_PCT,
        "tp_c": tp_price(estimate) if estimate else None,
        "sl_c": sl_price(estimate) if estimate else None,
        "max_entry_c": (min(99, math.ceil(ask) + ENTRY_SLIPPAGE_C)
                        if ask is not None else None),
        "contracts": DEFAULT_CONTRACTS, "max_contracts": MAX_CONTRACTS,
        "exchange_index": market.get("exchange_index"),
        "shard_cash_usd": cash,
        "problems": problems, "detail": "; ".join(problems) or None,
    }


# ---- place ----------------------------------------------------------------------

def serialize(row) -> dict:
    def stamp(moment):
        return moment.isoformat(timespec="seconds") + "Z" if moment else None
    return {"id": row.id, "asset": row.asset, "series": row.series,
            "ticker": row.ticker, "signal": row.signal, "confirmed": row.confirmed,
            "side": row.side, "contracts": row.contracts, "filled": row.filled,
            "entry_c": row.entry_c, "tp_c": row.tp_c, "sl_c": row.sl_c,
            "close_at": stamp(row.close_at), "status": row.status,
            "exited": row.exited, "exit_c": row.exit_c, "note": row.note,
            "opened_at": stamp(row.created_at), "closed_at": stamp(row.closed_at)}


def place(db, cred, *, tenant, asset: str, signal: str | None, ticker: str,
          contracts: int, request_id: str, confirms: bool = False,
          tradier_cred=None, risky: bool = False) -> dict:
    """Buy at market and start the watch. REAL MONEY.

    Everything the form showed is checked again here, because time has
    passed: the signal must still say what was confirmed, the quarter must
    still be the one that was shown, and its bid must still be in range.

    ``risky`` (RISKY-BUY) skips the bid range and starts no watch: the
    position is held with no take-profit and no stop-loss. The signal, the
    quarter, the time left and the price ceiling are still checked.
    """
    from app.domains.botstation import venue
    from app.domains.botstation.models import SignalTrade
    from app.platform.db.repository import TenantRepository

    repo = TenantRepository(db, tenant.id)
    request_id = (request_id or "").strip()
    seen = db.scalar(repo.query(SignalTrade).where(SignalTrade.request_id == request_id))
    if seen is not None:
        # The same confirmation again: the answer it got, not a second order.
        return {"placed": seen.status != "unfilled", "repeat": True,
                "trade": serialize(seen),
                "detail": seen.note if seen.status == "unfilled" else None}

    sig = (signal or "").strip().lower()
    side = SIDE_FOR.get(sig)
    if side is None:
        raise SignalTradeRefused("NOT a valid signal — mixed has no direction to trade")
    spec = market_for(asset)
    if spec is None:
        raise SignalTradeRefused(f"Kalshi lists no fifteen-minute market for {asset}")

    now_row = current_signal(asset, tradier_cred)
    now_sig = (now_row or {}).get("signal")
    if now_sig != sig:
        raise SignalTradeRefused(
            f"the signal is now {_label(now_sig)}, not {_label(sig)} — "
            "nothing was placed")

    if not risky:
        open_here = db.scalar(repo.query(SignalTrade).where(
            SignalTrade.ticker == ticker, SignalTrade.status == "watching"))
        if open_here is not None:
            raise SignalTradeRefused(
                f"a signal trade on {ticker} is already being watched")

    count = max(1, min(MAX_CONTRACTS, int(contracts)))
    client = venue._client(cred)
    try:
        market = current_market(client, spec.series)
        if market is None:
            raise SignalTradeRefused(f"no {spec.series} market is open any more")
        if market.get("ticker") != ticker:
            raise SignalTradeRefused(
                f"the quarter has rolled over to {market.get('ticker')} — "
                "reopen the form to see its price")
        bid, ask = side_quote(market, side)
        close = _parse(market.get("close_time"))
        left = (close - _now()).total_seconds() if close else 0
        if not risky and (bid is None or not BID_FLOOR_C < bid < BID_CEIL_C):
            raise SignalTradeRefused(
                f"the bid is {'none' if bid is None else f'{bid:g}c'} now — "
                "outside 35–70c, so nothing was placed")
        if ask is None:
            raise SignalTradeRefused("nothing is offered on that side to buy")
        if left < MIN_SECONDS_LEFT:
            raise SignalTradeRefused(
                f"this quarter closes in {max(0, int(left))}s — too late to enter")

        limit_c = min(99, math.ceil(ask) + ENTRY_SLIPPAGE_C)
        try:
            order = client.create_order(
                ticker=ticker, side=side, action="buy", count=count,
                price_c=limit_c, time_in_force="immediate_or_cancel",
                # The confirmation's id is the exchange's idempotency key:
                # the client's own retry of this request is one order.
                client_order_id=f"sig15-{request_id}"[:64])
        except Exception as exc:                        # noqa: BLE001
            reason = _refusal(exc)
            if "insufficient" in reason.lower():
                cash = shard_cash(client, market.get("exchange_index"))
                reason += (f" — this market settles on exchange shard "
                           f"{market.get('exchange_index')}, which holds "
                           f"${cash if cash is not None else '?'}; Kalshi's API "
                           "spends only that shard's cash")
            logger.warning("signal trade %s %s x%d refused: %s",
                           side, ticker, count, reason)
            return {"placed": False, "detail": reason}
        # Read back while the connection is open: the response says how
        # many filled, not what they cost.
        costs = (order_costs(client, _order_id(order))
                 if filled_count(order) > 0 else None)
    finally:
        client.close()

    filled = costs["filled"] if costs else filled_count(order)
    row = SignalTrade(
        request_id=request_id, asset=(asset or "").strip().lower(),
        series=spec.series, ticker=ticker, signal=sig, confirmed=bool(confirms),
        side=side, contracts=float(count), filled=filled,
        close_at=_naive_utc(close), order_id=_order_id(order),
    )
    if filled <= 0:
        row.status = "unfilled"
        row.note = (f"not filled — nobody was offering {side.upper()} at "
                    f"{limit_c}c or less when it was sent")
        row.closed_at = _naive_utc(_now())
        repo.add(row)
        db.commit()
        return {"placed": False, "trade": serialize(row), "detail": row.note}

    # TOTAL COST -- the fills plus the fees on them, the figure Kalshi's own
    # position card shows as COST -- is what the take-profit and the
    # stop-loss are measured from, per contract.
    if costs:
        fill_usd, fees_usd = costs["cost_usd"], costs["fees_usd"]
    else:
        price_c, fee_c = _response_fill(order, side, limit_c)
        fill_usd, fees_usd = filled * price_c / 100.0, filled * fee_c / 100.0
    paid_usd = fill_usd + fees_usd
    entry = round(paid_usd / filled * 100.0, 2)
    row.entry_c = entry
    bought = (f"bought {filled:g} {side.upper()} for ${paid_usd:.2f} "
              f"({entry:g}c each, fees included)"
              + ("" if costs else " — the order could not be read back, "
                                  "so the cost is estimated"))
    if risky:
        row.status = "unwatched"
        row.note = (f"RISKY-BUY: {bought}, bid was "
                    f"{'none' if bid is None else f'{bid:g}c'}; no "
                    "take-profit or stop-loss watches it")
    else:
        row.tp_c = tp_price(entry)
        row.sl_c = sl_price(entry)
        row.status = "watching"
        row.note = (f"{bought}; take-profit {row.tp_c:g}c, "
                    f"stop-loss {row.sl_c:g}c")
    repo.add(row)
    db.commit()

    # Into the shared ledger at entry, as every bot records its trades: the
    # reconciler closes the row against what Kalshi says happened.
    try:
        from app.domains.botstation.ledger import entries

        entries.record_entry(
            tenant_slug=tenant.slug, bot_key=BOT_KEY, bot_version="v1",
            ticker=ticker, external_id=row.order_id or f"sig15-{request_id}",
            contracts=filled,
            entry_price_c=round(fill_usd / filled * 100.0, 2),
            market_title=spec.series, outcome=side.upper(),
            entry_usd=round(fill_usd, 4), fees_usd=round(fees_usd, 4),
            is_live=True,
            raw={"signal_trade_id": row.id, "signal": sig, "tp_c": row.tp_c,
                 "sl_c": row.sl_c, "risky": bool(risky),
                 "close_at": serialize(row)["close_at"]})
    except Exception as exc:                            # noqa: BLE001
        logger.warning("signal trade %s not written to the ledger: %s", row.id, exc)
    logger.info("signal trade %s: %s", row.id, row.note)
    return {"placed": True, "trade": serialize(row)}


def trades(db, tenant, *, limit: int = 20) -> list[dict]:
    """The operator's signal trades: everything still watched, then the most
    recent finished ones."""
    from app.domains.botstation.models import SignalTrade
    from app.platform.db.repository import TenantRepository

    repo = TenantRepository(db, tenant.id)
    rows = db.scalars(repo.query(SignalTrade).order_by(
        SignalTrade.created_at.desc()).limit(limit)).all()
    rows = sorted(rows, key=lambda r: (r.status != "watching",))
    return [serialize(r) for r in rows]


# ---- the watch --------------------------------------------------------------------

def _exit(client, row, *, reason: str, limit_c: float, have: float) -> None:
    """One immediate-or-cancel sell of what is held. A partial fill leaves the
    trade watching, and the next pass sells what is left."""
    import uuid

    order = client.create_order(
        ticker=row.ticker, side=row.side, action="sell", count=have,
        price_c=int(limit_c), time_in_force="immediate_or_cancel",
        client_order_id=f"sig15x-{row.id}-{uuid.uuid4().hex[:12]}")
    sold = filled_count(order)
    if sold <= 0:
        logger.info("signal trade %s: %s exit at %sc found nobody; retrying",
                    row.id, reason, int(limit_c))
        return
    # What the sale actually fetched, not its limit: an immediate-or-cancel
    # sell takes the best bid there is, which is often well above it.
    costs = order_costs(client, _order_id(order))
    if costs:
        sold = costs["filled"]
        price_c = 100.0 - costs["cost_usd"] / sold * 100.0
        fee_c = costs["fees_usd"] / sold * 100.0
    else:
        price_c, fee_c = _response_fill(order, row.side, limit_c)
    # Kept AFTER fees, as the entry is kept with them, so the two compare as
    # Kalshi's card does: what came back against what it cost.
    net_c = price_c - fee_c
    prior = row.exited or 0.0
    row.exit_c = round(((row.exit_c or 0.0) * prior + net_c * sold) / (prior + sold), 2)
    row.exited = prior + sold
    if sold + 1e-9 >= have:
        row.status = reason
        row.closed_at = _naive_utc(_now())
        word = "take-profit" if reason == "tp" else "stop-loss"
        got = row.exit_c * row.exited / 100.0
        paid = (row.entry_c or 0.0) * row.exited / 100.0
        row.note = (f"{word}: sold {row.exited:g} for ${got:.2f} after fees "
                    f"({row.exit_c:g}c each) against ${paid:.2f} paid: "
                    f"{'+' if got >= paid else '-'}${abs(got - paid):.2f}")
    logger.info("signal trade %s: %s sold %g at %gc (%gc after fees)",
                row.id, reason, sold, round(price_c, 2), round(net_c, 2))


# A position read as flat is not believed at once. The portfolio endpoint can
# lag a fill by seconds, and a watch that ends on one stale reading leaves a
# live position with no stop. Flat must be read for FLAT_CONFIRM_S, and not at
# all in the first ENTRY_GRACE_S after the buy.
ENTRY_GRACE_S = 15.0
FLAT_CONFIRM_S = 10.0
_FLAT_SINCE: dict[int, float] = {}


def _watch_one(client, row) -> None:
    now = _now()
    close = row.close_at.replace(tzinfo=timezone.utc)
    if now >= close:
        row.status = "expired"
        row.closed_at = _naive_utc(now)
        row.note = ("the quarter closed with the position still held — "
                    "left to settle; the ledger records how it ended")
        _FLAT_SINCE.pop(row.id, None)
        return
    # Only what THIS trade bought. The position is the market's total, and it
    # can hold a RISKY-BUY's contracts, or the operator's own from the Kalshi
    # app, beside these -- an exit of the whole position would sell them too.
    own = max(0.0, float(row.filled or 0) - float(row.exited or 0))
    have = min(held(client, row.ticker, row.side), own)
    if have <= 0:
        opened = row.created_at.replace(tzinfo=timezone.utc) if row.created_at else now
        if (now - opened).total_seconds() < ENTRY_GRACE_S:
            return
        first = _FLAT_SINCE.setdefault(row.id, time.monotonic())
        if time.monotonic() - first < FLAT_CONFIRM_S:
            return
        _FLAT_SINCE.pop(row.id, None)
        row.status = "closed"
        row.closed_at = _naive_utc(now)
        row.note = "no longer held — closed outside this desk"
        return
    _FLAT_SINCE.pop(row.id, None)
    market = _market(client, row.ticker)
    if not market:
        return
    bid, _ask = side_quote(market, row.side)
    if bid is None:
        return
    if row.tp_c is not None and bid >= row.tp_c:
        # At the target or better, or not at all: a take-profit that reaches
        # below its own price is not one.
        _exit(client, row, reason="tp", limit_c=row.tp_c, have=have)
    elif row.sl_c is not None and bid <= row.sl_c:
        _exit(client, row, reason="sl",
              limit_c=max(1, math.floor(bid) - EXIT_SLIPPAGE_C), have=have)


_CREDS: dict[str, tuple[float, object]] = {}
CRED_TTL_S = 60.0


def _credential(db, tenant_id: str):
    held_cred = _CREDS.get(tenant_id)
    if held_cred and time.time() - held_cred[0] < CRED_TTL_S:
        return held_cred[1]
    from app.api_v2 import deps
    from app.tenancy import repository as tenants

    cred = tenants.load_credential(db, tenant_id, "kalshi", deps.keyring())
    _CREDS[tenant_id] = (time.time(), cred)
    return cred


def sweep_all_tenants() -> int:
    """One pass of the watch over every operator's open signal trades.

    Per operator, through that operator's own scope and credential -- one
    operator's failure is logged and costs nobody else their pass. Returns
    how many trades were looked at.
    """
    from app.domains.botstation import venue
    from app.domains.botstation.models import SignalTrade
    from app.platform.db.repository import TenantRepository
    from app.platform.db.session import session_scope
    from app.tenancy.models import Tenant

    looked = 0
    with session_scope() as db:
        tenant_ids = list(db.scalars(select(Tenant.id)).all())
    for tenant_id in tenant_ids:
        try:
            with session_scope() as db:
                repo = TenantRepository(db, tenant_id)
                rows = db.scalars(repo.query(SignalTrade).where(
                    SignalTrade.status == "watching")).all()
                if not rows:
                    continue
                client = venue._client(_credential(db, tenant_id))
                try:
                    for row in rows:
                        looked += 1
                        try:
                            _watch_one(client, row)
                        except Exception as exc:        # noqa: BLE001
                            logger.info("signal trade %s pass failed: %s: %s",
                                        row.id, type(exc).__name__, exc)
                        db.flush()
                finally:
                    client.close()
        except Exception as exc:                        # noqa: BLE001
            logger.warning("signal trades for one operator: %s: %s",
                           type(exc).__name__, exc)
    return looked
