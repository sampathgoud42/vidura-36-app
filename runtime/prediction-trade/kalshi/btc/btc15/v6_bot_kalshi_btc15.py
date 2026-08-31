#!/usr/bin/env python
"""BTC-15 v6 — trade the quarter-hour only when BTC, ETH and SOL agree.

Thin by design. The entry rule lives in
``app.domains.botstation.btc15.alignment``, where it is exercised with no
network, no credentials and no exchange; this file is the loop, the market
search and the order placement.

The rule, in full:

    read the desk's CRYPTO board (the same 1m/2m/5m/10m DMI the panel shows)
    all three majors CALL  ->  buy YES
    all three majors PUT   ->  buy NO
    anything else          ->  stand aside

    enter only 1-5 minutes after the market opened
    pay only 40c-70c on the side being bought
    take profit at +20%, stop at -40%

It reads the SAME crypto module the CRYPTO panel renders from, so the bot and
the screen cannot disagree about what BTC is doing -- a second copy of the
indicator would drift the first time either was touched, and nothing would
report it.

Usage:
    v6_bot_kalshi_btc15.py [--live] [--once] [--contracts N]

Paper is the default; --live is the only way to reach real money and is
refused outright when the server is locked to paper.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# Everything this bot needs is inside the project, so the path comes from this
# file rather than from PYTHONPATH: the bot station launches it as a bare
# subprocess, and a bot that only runs under one launcher cannot be debugged
# by hand.
_HERE = Path(__file__).resolve().parent
# parents[4]: btc15 -> btc -> kalshi -> prediction-trade -> runtime -> ROOT
ROOT = _HERE.parents[4]
for _p in (str(ROOT / "backend"), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

logging.basicConfig(level=logging.INFO, format="[BTC15-v6] %(message)s")
log = logging.getLogger("btc15.v6")
# httpx logs every request at INFO, which buries the eight lines that say what
# this bot decided under eight lines saying it fetched a candle.
for _noisy in ("httpx", "httpcore", "urllib3"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

SERIES = "KXBTC15M"


def _env(name: str, fallback, cast=str):
    """One launch-form option, from the environment.

    The bot station passes options as UPPERCASED environment variables, so
    anything read only from argv is a field the operator can edit in the form
    while nothing acts on it.
    """
    raw = os.environ.get(name.upper())
    if raw is None or raw == "":
        return fallback
    try:
        return cast(raw)
    except (TypeError, ValueError):
        log.warning("%s=%r is not a %s; using %r", name.upper(), raw,
                    cast.__name__, fallback)
        return fallback


async def _fresh_market(client, *, opens_at: int, closes_at: int):
    """The open BTC-15 market whose age is inside the entry window.

    Returns (market, age_seconds) or (None, None). Markets younger than the
    window are left alone rather than waited on inside this call, so the loop
    stays responsive and reports what it is waiting for.
    """
    from app.domains.botstation.btc15 import alignment

    data = await client.req("GET", "/markets", params={
        "series_ticker": SERIES, "status": "open", "limit": 5})
    best = None
    for market in data.get("markets", []):
        # BINARY ONLY. The series filter above already asks for KXBTC15M, but
        # this engine reasons about a quarter-hour that settles yes or no --
        # a perpetual has no expiry for "1-5 minutes after open" to mean
        # anything against, and its price is not a probability. If Kalshi ever
        # lists one under this series, it is not ours to trade.
        kind = str(market.get("market_type") or "binary").lower()
        if kind != "binary":
            log.info("skipping %s: %s, not a binary quarter-hour market",
                     market.get("ticker"), kind)
            continue
        age = alignment.seconds_since_open(market.get("open_time", ""))
        if age is None:
            continue
        if opens_at <= age <= closes_at:
            return market, age
        if best is None or age < best[1]:
            best = (market, age)
    return (None, best[1] if best else None)


async def _price_c(client, ticker: str, side: str,
                   improve_c: int = 1) -> int | None:
    """What this engine will BID for ``side`` right now, in cents.

    The best bid plus a cent: it becomes the new best bid, so it is first in
    the queue when a seller arrives, and it pays the spread to nobody. Paying
    the ask fills instantly but hands the whole spread away on every entry,
    and on a quarter-hour market that spread is a large share of the move
    being traded.

    The consequence, stated because it decides how the order must be sent:
    bid+1 does not cross, so it RESTS. An immediate-or-cancel order at this
    price is cancelled unfilled by definition.
    """
    data = await client.req("GET", f"/markets/{ticker}")
    market = data.get("market") or data
    for key in (f"{side}_bid_dollars", f"{side}_bid"):
        raw = market.get(key)
        if raw in (None, ""):
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        cents = int(round(value * 100)) if "dollars" in key else int(value)
        # A market with no bid at all quotes 0; one cent above nothing is not
        # a price, it is a lottery ticket on an empty book.
        return (cents + improve_c) if cents > 0 else None
    return None


async def _log_balance(client, ticker: str) -> None:
    """What the account holds, per exchange shard. Read-only, best effort."""
    try:
        data = await client.req("GET", "/portfolio/balance")
    except Exception as exc:                            # noqa: BLE001
        log.info("  (could not read the balance: %s)", type(exc).__name__)
        return
    parts = ", ".join(
        f"shard {row.get('exchange_index')}: ${row.get('balance')}"
        for row in data.get("balance_breakdown", []))
    log.warning("  balance: $%s total (%s) — %s settles on shard 2. Cash on "
                "another shard is NOT reachable from the API unless automatic "
                "rebalancing is on: POST /portfolio/target_balance_allocation "
                "with a percent for that index. An empty allocation turns "
                "rebalancing off, which is what starves this bot while the "
                "Kalshi app still trades fine (it moves funds itself).",
                data.get("balance_dollars"), parts, ticker.split("-")[0])


async def run_once(client, args) -> str:
    """One evaluation. Returns what the loop should do next.

        "placed"    an order went in
        "watching"  a market is INSIDE the entry window right now
        "opening"   one is about to enter it
        "idle"      nothing is close

    The caller polls fast for the first three. The entry window is only four
    minutes wide, and a price that dips into the 40-70c band for twenty
    seconds is a trade the old fixed cadence could not see -- it looked once
    every 20s whatever was happening, so a window got about twelve glances
    and a rejected order waited a full cycle before trying again.
    """
    from app.domains.botstation.btc15 import alignment
    from app.domains.trading.market import crypto

    market, age = await _fresh_market(client, opens_at=args.opens_at,
                                      closes_at=args.closes_at)
    if market is None:
        log.info("no market inside the %ds-%ds window%s", args.opens_at,
                 args.closes_at,
                 f" (nearest is {age:.0f}s old)" if age is not None else "")
        # Younger than the window means it opens shortly: stay close rather
        # than sleeping through the first seconds of it.
        if age is not None and age < args.opens_at:
            return "opening"
        return "idle"

    ticker = market["ticker"]
    board = crypto.snapshot()
    read = alignment.read_alignment(board["rows"])

    # The price is read for the side the majors point at. Asking before we
    # know the side would mean two round trips or a guess.
    price = (await _price_c(client, ticker, read.side)) if read.side else None

    decision = alignment.decide(
        board["rows"], open_time=market.get("open_time", ""), price_c=price,
        opens_at=args.opens_at, closes_at=args.closes_at,
        low=args.min_price_c, high=args.max_price_c)

    coins = "  ".join(f"{c}={s or 'mixed'}"
                      for c, s in decision["per_coin"].items())
    log.info("%s  %s", ticker, coins)
    for name, gate in decision["gates"].items():
        log.info("  %-9s %-3s %s", name, "ok" if gate["ok"] else "no",
                 gate["why"])

    if not decision["enter"]:
        # Inside the window and not yet takeable. Keep watching: the gates are
        # read fresh every pass, so a price that comes back into the band
        # while the window is still open is still a trade.
        return "watching"

    side = decision["side"]
    entry = decision["price_c"]
    # Percentages OF THE ENTRY, which is what the operator typed. Rounded away
    # from the entry so a 20% target is never accidentally set below it.
    tp_c = min(99, max(entry + 1, round(entry * (1 + args.tp_pct / 100))))
    sl_c = max(1, min(entry - 1, round(entry * (1 - args.sl_pct / 100))))

    import bot_kalshi_btc15 as v1

    if await v1.position_for(client, ticker):
        # Already holding this market. A second entry on the same quarter hour
        # doubles exposure to one BTC move that has already gone against the
        # first, which is the opposite of what a second opinion buys.
        log.info("  already holding %s — no second entry", ticker)
        return "idle"

    log.info("  BUY %s x%d @ %dc   TP %dc (+%g%%)  SL %dc (-%g%%)",
             side.upper(), args.contracts, entry, tp_c, args.tp_pct,
             sl_c, args.sl_pct)
    if not args.live:
        log.info("  paper — no order sent")
        return "watching"

    # RE-READ THE BOOK, and re-price against it.
    #
    # The price the gates judged was fetched several calls ago and the book
    # moves between calls. Resting at a stale bid+1 is resting behind the
    # queue, which is the difference between being filled and being ignored.
    #
    # Bounded twice over: by max_price_c, the band the operator set, and by
    # the gate that already refused anything outside it. Paying the ask can
    # never cost more than the engine was authorised to pay.
    fresh = await _price_c(client, ticker, side)
    if fresh is None:
        log.info("  no bid to improve on; will retry")
        return "watching"
    bid = min(args.max_price_c, fresh + args.cross_c)
    if bid > args.max_price_c or fresh > args.max_price_c:
        log.info("  bid+1 is %dc, past the %dc ceiling; standing aside",
                 fresh, args.max_price_c)
        return "watching"
    if bid != entry:
        log.info("  book moved; bidding %dc (was %dc)", bid, entry)
    entry = bid
    tp_c = min(99, max(entry + 1, round(entry * (1 + args.tp_pct / 100))))
    sl_c = max(1, min(entry - 1, round(entry * (1 - args.sl_pct / 100))))

    order = await v1.place_buy(client, ticker, side, entry, args.contracts)
    if not order:
        # Refused, not disqualified. The window is still open and the gates
        # may still be green, so the next pass tries again rather than
        # writing this quarter-hour off.
        log.warning("  the buy was not accepted — will retry while the "
                    "window is open")
        # Say what the exchange had to spend, per shard. "insufficient
        # balance" against a visibly funded account is the single most
        # confusing answer this bot can get, because the figure the desk and
        # the Kalshi app both show is the TOTAL -- while an order is settled
        # against the shard its market lives on. Printing the split turns an
        # argument into a reading.
        await _log_balance(client, ticker)
        return "watching"

    body = order.get("order") if isinstance(order, dict) else None
    body = body if isinstance(body, dict) else (order or {})

    # ACCEPTED IS NOT FILLED. An immediate-or-cancel order that finds no
    # counterparty is accepted, cancelled and returns a perfectly ordinary
    # response with fill_count_fp 0 -- and this engine used to read that as an
    # entry, announce "entered", and rest a take-profit against a position it
    # did not hold. A sell order backed by nothing is the worst outcome
    # available here, so the fill is checked before anything else happens.
    try:
        filled = float(body.get("fill_count_fp") or body.get("count") or 0)
    except (TypeError, ValueError):
        filled = 0.0
    if filled <= 0:
        log.info("  not filled (%s) — nobody was offering at %dc; will retry "
                 "while the window is open",
                 body.get("status") or "no fill", entry)
        return "watching"

    # Into the ledger, at entry -- reconciliation only closes rows that
    # already exist, so a trade nobody records here never appears on the desk
    # however real the position is.
    from app.domains.botstation.ledger import entries

    if not entries.record_entry(
            tenant_slug=args.customer or os.environ.get("BTC_CUSTOMER", ""),
            bot_key="btc15", bot_version="v6", ticker=ticker,
            external_id=str(body.get("order_id") or body.get("id") or ""),
            contracts=filled, entry_price_c=entry,
            market_title=ticker.split("-")[0],
            outcome=side.upper(),
            entry_usd=round(filled * entry / 100.0, 4),
            is_live=args.live, raw=body):
        log.warning("  the trade was NOT written to the ledger")

    await v1.place_tp_sell(client, ticker, side, filled, tp_c)
    log.info("  entered %g @ %dc; take-profit resting at %dc",
             filled, entry, tp_c)
    return "placed"


async def amain(args) -> int:
    import bot_kalshi_btc15 as v1

    client = v1.KalshiClient()
    try:
        if args.once:
            await run_once(client, args)
            return 0
        while True:
            status = "idle"
            try:
                status = await run_once(client, args)
            except Exception as exc:                    # noqa: BLE001
                # A failed pass is not a reason to exit. A bot that quits
                # silently is worse than one that logs and retries.
                log.warning("pass failed: %s: %s", type(exc).__name__, exc)
            # Fast while a window is open or about to be, slow otherwise.
            # Between windows there is nothing to see for ten minutes at a
            # time, and polling hard through that only spends API calls.
            near = status in ("watching", "opening")
            await asyncio.sleep(args.window_poll_s if near else args.poll_s)
    finally:
        await client.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("customer", nargs="?", default=None)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--poll-s", type=int, default=20, dest="poll_s")
    # How often to look while the entry window is actually open.
    ap.add_argument("--window-poll-s", type=int, default=5,
                    dest="window_poll_s")
    args = ap.parse_args()

    # Every knob the launch form offers, read from the environment.
    args.contracts = _env("contracts", 1, int)
    args.tp_pct = _env("tp_pct", 20.0, float)
    args.sl_pct = _env("sl_pct", 40.0, float)
    args.min_price_c = _env("min_price_c", 40, int)
    args.max_price_c = _env("max_price_c", 70, int)
    args.window_poll_s = _env("window_poll_s", args.window_poll_s, int)
    # How far above the quoted ask to bid. ZERO: pay the ask, which is the
    # price being offered, and nothing more. A buy at the ask already matches
    # the resting sell, so the earlier +2c bought nothing except a worse fill
    # on a book that happened to be steady. The knob stays, for a book that
    # ticks away faster than it can be read.
    args.cross_c = _env("cross_c", 0, int)   # extra over bid+1; normally none
    args.opens_at = _env("entry_open_s", 60, int)
    args.closes_at = _env("entry_close_s", 300, int)
    # The station decides when it started us; --live decides on a hand run.
    # Read through lifecycle.wants_live, which sits beside the code that
    # WRITES these flags, so the two cannot drift again.
    from app.domains.botstation import lifecycle

    args.live = lifecycle.wants_live(args.live)

    # Take liquidity rather than rest. See _mk_order in v4: a resting order
    # must reserve cash on the market's own shard, and with rebalancing off
    # that shard has cents. Overridable, so an operator can put it back.
    # RESTING, because the engine now bids one cent above the best bid rather
    # than paying the ask. That price does not cross, so immediate-or-cancel
    # would cancel every order the instant it was sent.
    os.environ.setdefault("KALSHI_TIF",
                          _env("time_in_force", "good_till_canceled"))

    from app.core.config import get_settings

    if args.live and get_settings().paper_only:
        log.error("this server is locked to paper; --live is refused")
        return 2

    log.info("btc15 v6 — %s | entry %ds-%ds after open | pay %dc-%dc | "
             "TP +%g%% SL -%g%% | %s | checking every %ds in the window, %ds "
             "outside it",
             "LIVE" if args.live else "paper (no orders will be sent)",
             args.opens_at, args.closes_at, args.min_price_c,
             args.max_price_c, args.tp_pct, args.sl_pct,
             os.environ.get("KALSHI_TIF", "good_till_canceled"),
             args.window_poll_s, args.poll_s)
    return asyncio.run(amain(args))


if __name__ == "__main__":
    raise SystemExit(main())
