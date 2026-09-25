#!/usr/bin/env python
"""The DMI-stack engine: one quarter-hour loop, four instruments, two rules.

BTC, gold, silver and oil all trade the same shape of contract -- a
fifteen-minute market that settles yes or no -- against the same desk board.
The only things that differ between them are which Kalshi series to search,
which row of which board to read, and what to call the result in the ledger.

So this is the engine, once, and the four bot scripts beside it are each about
twenty lines that name a `Profile` and call `main`. Writing it four times was
the obvious path and the wrong one: the commodity family already carries three
near-identical 20KB copies of an older engine, and every fix to one of them
has to be remembered three more times.

THE RULES, in full -- see ``app.domains.botstation.dmi_stack`` for the why.
A profile names one of them; the gates below are identical either way.

    UNANIMOUS (v7)   all four timeframes call    ->  buy YES
                     all four timeframes put     ->  buy NO

    MAJORITY (v8)    3 of 4 call AND 3 of 4 with ADX rising   ->  buy YES
                     3 of 4 put  AND 3 of 4 with ADX rising   ->  buy NO

    anything else    ->  stand aside

    enter only 5-300 seconds after the market opened
    pay only 30c-65c on the side being bought
    take profit at +tp_pct, stop at -sl_pct

The signal is read from the SAME module the CRYPTO and COMMODITIES panels
render from, so the bot and the screen cannot disagree about what the market
is doing. A second copy of the indicator would drift the first time either was
touched, and nothing would report it.

Paper is the default. ``--live`` is the only way to reach real money and is
refused outright when the server is locked to paper.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths. Everything this engine needs is inside the project, so the path comes
# from this file rather than from PYTHONPATH: the bot station launches these
# scripts as bare subprocesses, and a bot that only runs under one launcher
# cannot be debugged by hand.
#
# parents[2]: kalshi -> prediction-trade -> runtime -> ROOT
_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parents[2]
# The desk's shared Kalshi primitives -- the signed async client and the order
# helpers. They live in the btc15 folder for historical reasons and are NOT
# BTC-specific; `bot_kalshi_btc15.py` is the re-export shim the sports bots
# already import for exactly this reason. Reusing it rather than writing a
# third copy of RSA-PSS request signing, which is the part of this system it
# would be worst to get subtly wrong.
_VENUE_DIR = _HERE / "btc" / "btc15"
for _p in (str(ROOT / "backend"), str(_VENUE_DIR), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The desk-wide sell guard, shared by every engine on this desk that sells.
import sell_guard                                       # noqa: E402

# Force UTF-8 on stdout/stderr. On Windows a redirected stream defaults to
# cp1252, which cannot encode the ↑ and ↓ this engine logs -- and those arrows
# are the whole point of the log line, because they are what makes a bot's
# decision comparable to the board on screen. Without this they arrive as
# ↑ escapes, or crash the log call outright.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

log = logging.getLogger("v7")
# httpx and aiohttp log every request at INFO, which buries the eight lines
# that say what this bot decided under eighty saying it fetched a candle.
# Named once and quieted twice -- here, and again after basicConfig in main(),
# which otherwise resets them. The registry is on the list because loading the
# bot configs (which the commodity board needs) announces all eight bots on
# every start, burying the four lines that say what this one decided.
NOISY_LOGGERS = ("httpx", "httpcore", "urllib3", "aiohttp", "yfinance",
                 "peewee", "app.domains.botstation.registry")
for _noisy in NOISY_LOGGERS:
    logging.getLogger(_noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# What makes one bot different from another.

@dataclass(frozen=True)
class Profile:
    """The few facts that distinguish one DMI-stack bot from the others."""

    bot_key: str        # ledger key: btc15 | gold15 | silver15 | oil15
    version: str        # ledger version string, as the registry names it
    series: str         # Kalshi series ticker, e.g. KXBTC15M
    board: str          # which desk board: crypto | commodities
    row_key: str        # which row of it: btc | gold15 | silver15 | oil15
    # WHICH reading of the board this engine trades on:
    #
    #   "unanimous"  v7 -- all four timeframes on the same side
    #   "majority"   v8 -- three of four on a side AND three of four rising
    #
    # Defaulted to unanimous so an existing profile keeps the rule it was
    # written with. A version is a name; this is the behaviour, and the two
    # are kept apart deliberately -- the loop never asks what version it is.
    rule: str = "unanimous"


# ---------------------------------------------------------------------------
# The boards.
#
# Each returns the same thing -- the panel's own rows -- so the rule above it
# never learns which market it is looking at.

def _crypto_rows() -> list[dict]:
    """The CRYPTO panel's rows, from Coinbase. No credential, keyless."""
    from app.domains.trading.market import crypto

    return crypto.snapshot().get("rows", [])


def _commodity_rows() -> list[dict]:
    """The COMMODITIES panel's rows.

    Two things about this are worth knowing before reading a log from it.

    FIRST, the registry has to be loaded. The board asks each registered bot
    which symbol stands in for it, and in a bare subprocess nothing has
    registered anything yet -- so without this the board is not wrong, it is
    EMPTY, and every pass would report "no gold15 row" as though the feed had
    failed.

    SECOND, this process holds no Tradier credential. The desk passes one when
    an operator is signed in; a bot subprocess has no keyring. The board
    handles that by design: with no credential it falls through to the futures
    feed (GC=F / SI=F / CL=F via yfinance), which needs none. The reading is
    then computed from futures rather than from the tracking ETF, so it can
    differ from what a signed-in operator sees on screen during market hours.
    That is why every pass logs which source answered -- it is part of the
    answer, not a footnote.
    """
    from app.domains.botstation import registry
    from app.domains.trading.market import commodities

    # Idempotent: re-registering is a no-op rather than an error.
    registry.load_builtin_bots()
    return commodities.snapshot(None, sandbox=True).get("rows", [])


BOARDS = {"crypto": _crypto_rows, "commodities": _commodity_rows}


def _rows(profile: Profile) -> list[dict]:
    return BOARDS[profile.board]()


def _source_of(rows: list[dict], row_key: str) -> str:
    row = next((r for r in rows if r.get("bot") == row_key), None)
    return str((row or {}).get("source") or "unavailable")


# ---------------------------------------------------------------------------
# The exchange.

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


async def _fresh_market(client, profile: Profile, *, opens_at: int,
                        closes_at: int):
    """The open market in this series whose age is inside the entry window.

    Returns (market, age_seconds) or (None, age_of_nearest). Markets younger
    than the window are left alone rather than waited on inside this call, so
    the loop stays responsive and reports what it is waiting for.
    """
    from app.domains.botstation import dmi_stack

    data = await client.req("GET", "/markets", params={
        "series_ticker": profile.series, "status": "open", "limit": 5})
    best = None
    for market in data.get("markets", []):
        # BINARY ONLY. The series filter already asks for one series, but this
        # engine reasons about a quarter-hour that settles yes or no -- a
        # perpetual has no expiry for "5 to 300 seconds after open" to mean
        # anything against, and its price is not a probability.
        kind = str(market.get("market_type") or "binary").lower()
        if kind != "binary":
            log.info("skipping %s: %s, not a binary quarter-hour market",
                     market.get("ticker"), kind)
            continue
        age = dmi_stack.seconds_since_open(market.get("open_time", ""))
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
    log.warning("  balance: $%s total (%s) — %s settles on its own shard. "
                "Cash on another shard is NOT reachable from the API unless "
                "automatic rebalancing is on: POST "
                "/portfolio/target_balance_allocation with a percent for that "
                "index. An empty allocation turns rebalancing off, which is "
                "what starves this bot while the Kalshi app still trades fine "
                "(it moves funds itself).",
                data.get("balance_dollars"), parts, ticker.split("-")[0])


def _tp_sl(entry: int, tp_pct: float, sl_pct: float) -> tuple[int, int]:
    """Take-profit and stop, in cents, as percentages OF THE ENTRY.

    Rounded away from the entry so a 20% target is never accidentally set
    below it, and clamped inside 1-99c because those are the only prices a
    binary contract has.
    """
    tp_c = min(99, max(entry + 1, round(entry * (1 + tp_pct / 100))))
    sl_c = max(1, min(entry - 1, round(entry * (1 - sl_pct / 100))))
    return tp_c, sl_c


# ---------------------------------------------------------------------------
# Managing a filled entry.
#
# Every sell below goes through `sell_guard`, the desk-wide check shared by all
# of these bots: there IS a position, and there is NO live order on the ticker,
# each read twice ten seconds apart. It is enforced inside `place_tp_sell`
# itself, so it cannot be skipped by forgetting to call it here.

async def _manage_position(client, venue, ticker: str, side: str,
                           contracts: float, tp_c: int, sl_c: int, *,
                           poll_s: int = 5) -> None:
    """Rest the take-profit, then watch the stop, for one filled entry.

    Runs as its own task so the main loop stays free to find the next
    quarter-hour rather than blocking through the guard's confirmation delays.

    It is started ONLY after the buy is confirmed FILLED. An accepted order is
    not a filled one -- an order that finds no counterparty is accepted,
    cancelled and returns an ordinary-looking response -- and everything below
    would then be resting a take-profit against a position that does not exist
    and arming a stop on nothing.
    """
    # --- the take-profit ---------------------------------------------------
    # The guard inside place_tp_sell confirms the position twice before this
    # goes anywhere, which is also what makes it safe to call the instant the
    # fill is reported: a fill the exchange has not finished booking shows up
    # as "no position" and is refused rather than sold into.
    await venue.place_tp_sell(client, ticker, side, contracts, tp_c)

    # --- the stop ----------------------------------------------------------
    # Kalshi has no stop order type, so a stop is something a process has to
    # WATCH. A stop that exists only as a number in a launch form is worse
    # than no stop at all, because the operator believes it is there.
    while True:
        await asyncio.sleep(poll_s)
        try:
            position = await venue.position_for(client, ticker)
            if not position or not position.get("contracts"):
                return                      # took profit, or settled
            bid = await _price_c(client, ticker, side, improve_c=0)
            if bid is None:
                continue                    # no book right now; keep watching
            if bid > sl_c:
                continue

            log.warning("  STOP %s: %s bid %dc is at or below the %dc stop",
                        ticker, side.upper(), bid, sl_c)
            # OUR OWN take-profit is resting on this ticker, and the guard
            # refuses to sell while anything is live. So it comes off first --
            # otherwise the take-profit would block the stop that is meant to
            # override it, which is the guard defeating the thing it exists to
            # protect.
            await sell_guard.cancel_live(client, ticker, log=log.warning)

            held = int((position or {}).get("contracts") or 0)
            # Sold at the bid, which crosses and fills, rather than at the
            # stop price -- a limit at the stop on a book that has already
            # traded through it is an order that rests while the loss grows.
            # The guard inside place_tp_sell re-confirms before it goes.
            await venue.place_tp_sell(client, ticker, side, held, bid)

            # Whether that sold is the guard's decision, not ours, so the loop
            # re-reads the position rather than assuming. A refusal means
            # something was still live or the position had gone; either way
            # the next pass sees the truth.
        except asyncio.CancelledError:
            raise
        except Exception as exc:            # noqa: BLE001
            # A failed read is not a reason to abandon a live position.
            log.info("  position watch on %s: %s: %s", ticker,
                     type(exc).__name__, exc)


# ---------------------------------------------------------------------------
# From "order sent" to "position monitored".

async def _arm_filled(client, venue, args) -> None:
    """Start monitoring any buy that has since FILLED.

    A buy at bid+1 does not cross, so it RESTS -- which is the point, but it
    means the usual path (order response reports a fill, arm the monitor) only
    covers the case where somebody happened to be selling at that instant.
    Every other entry fills later, quietly, with nothing watching it: no
    take-profit, no stop, no ledger row.

    So a resting buy is remembered, and every pass asks whether it has become
    a position yet. Monitoring starts when the fill is real and not before,
    which is the same rule the immediate path follows.
    """
    for ticker, order in list(args.pending.items()):
        try:
            held = await sell_guard.held_contracts(client, ticker, order["side"])
        except Exception as exc:                        # noqa: BLE001
            log.info("  could not check %s for a fill: %s: %s", ticker,
                     type(exc).__name__, exc)
            continue
        if held <= 0:
            # Still working, or it was cancelled/expired with the market. A
            # market that has closed can never fill, so it is dropped rather
            # than watched forever.
            if await _market_is_closed(client, ticker):
                log.info("  %s closed with the order unfilled — dropping it",
                         ticker)
                args.pending.pop(ticker, None)
            continue

        args.pending.pop(ticker, None)
        if ticker in args.managed:
            continue
        log.info("  %s FILLED %d @ %dc — take-profit %dc, stop %dc", ticker,
                 held, order["entry"], order["tp_c"], order["sl_c"])
        _record(args, order, ticker, held)
        _manage(client, venue, args, ticker, order["side"], held,
                order["tp_c"], order["sl_c"])


async def _market_is_closed(client, ticker: str) -> bool:
    try:
        data = await client.req("GET", f"/markets/{ticker}")
    except Exception:                                   # noqa: BLE001
        return False
    market = data.get("market") or data
    return str(market.get("status") or "").lower() not in ("open", "active", "")


def _record(args, order: dict, ticker: str, contracts: float) -> None:
    """Open the ledger row. Reconciliation only closes rows that already
    exist, so a trade nobody records here never appears on the desk however
    real the position is."""
    from app.domains.botstation.ledger import entries

    if not entries.record_entry(
            tenant_slug=args.customer, bot_key=args.profile.bot_key,
            bot_version=args.profile.version, ticker=ticker,
            external_id=order["order_id"], contracts=contracts,
            entry_price_c=order["entry"], market_title=ticker.split("-")[0],
            outcome=order["side"].upper(),
            entry_usd=round(contracts * order["entry"] / 100.0, 4),
            is_live=args.live, raw=order.get("raw") or {}):
        log.warning("  the trade was NOT written to the ledger")


def _manage(client, venue, args, ticker: str, side: str, contracts: float,
            tp_c: int, sl_c: int) -> None:
    """Arm the take-profit and stop for a position we are confirmed to hold.

    Fire-and-forget on purpose: the loop must stay free to find the next
    quarter-hour while the sell guard spends its confirmation delay. The task
    is kept in a set so it is not garbage-collected mid-flight, which is a
    real way for a stop to disappear silently.
    """
    args.managed.add(ticker)
    task = asyncio.create_task(
        _manage_position(client, venue, ticker, side, contracts, tp_c, sl_c))
    args.stops.add(task)

    def _done(finished, _t=ticker):
        args.stops.discard(finished)
        args.managed.discard(_t)

    task.add_done_callback(_done)


# ---------------------------------------------------------------------------
# One pass.

async def run_once(client, profile: Profile, args) -> str:
    """One evaluation. Returns what the loop should do next.

        "placed"    an order went in
        "watching"  a market is INSIDE the entry window right now
        "opening"   one is about to enter it
        "idle"      nothing is close

    The caller polls fast for the first three. This engine's window opens five
    seconds after the bell, so a slow fixed cadence would miss the front of it
    entirely -- which is the part the rule is built around.
    """
    from app.domains.botstation import dmi_stack

    import bot_kalshi_btc15 as venue

    # Before anything else: has a buy from an earlier pass filled? Monitoring
    # starts here for every entry that rested rather than crossing.
    await _arm_filled(client, venue, args)

    market, age = await _fresh_market(client, profile, opens_at=args.opens_at,
                                      closes_at=args.closes_at)
    if market is None:
        log.info("no %s market inside the %ds-%ds window%s", profile.series,
                 args.opens_at, args.closes_at,
                 f" (nearest is {age:.0f}s old)" if age is not None else "")
        if age is not None and age < args.opens_at:
            # It opens shortly. Warm the board NOW rather than inside the
            # window: the commodity board reaches out to a futures feed and
            # can take half a minute cold, which on a 295-second window is
            # time spent fetching instead of deciding. The board caches, so
            # this makes the first in-window read a cache hit.
            try:
                _rows(profile)
            except Exception as exc:                    # noqa: BLE001
                log.info("could not pre-warm the board: %s: %s",
                         type(exc).__name__, exc)
            return "opening"
        return "idle"

    ticker = market["ticker"]
    rows = _rows(profile)
    stack = dmi_stack.read(rows, profile.row_key, rule=profile.rule)

    # The price is read for the side the stack points at. Asking before we
    # know the side would mean two round trips or a guess.
    price = (await _price_c(client, ticker, stack.side)) if stack.side else None

    decision = dmi_stack.decide(
        rows, profile.row_key, open_time=market.get("open_time", ""),
        price_c=price, opens_at=args.opens_at, closes_at=args.closes_at,
        low=args.min_price_c, high=args.max_price_c, rule=profile.rule)

    log.info("%s  [%s]", ticker, _source_of(rows, profile.row_key))
    log.info("  %s", decision["board_line"])
    for name, gate in decision["gates"].items():
        log.info("  %-10s %-3s %s", name, "ok" if gate["ok"] else "no",
                 gate["why"])

    if not decision["enter"]:
        # Inside the window and not yet takeable. Keep watching: the gates are
        # read fresh every pass, so a price that comes back into the band --
        # or a 5m column that turns to match the other three -- while the
        # window is still open is still a trade.
        return "watching"

    side = decision["side"]
    entry = decision["price_c"]
    tp_c, sl_c = _tp_sl(entry, args.tp_pct, args.sl_pct)

    if await venue.position_for(client, ticker):
        # Already holding this market. A second entry on the same quarter hour
        # doubles exposure to one move that has already gone against the
        # first, which is the opposite of what a second opinion buys.
        log.info("  already holding %s — no second entry", ticker)
        return "idle"

    # An order of ours is already working on this market. Our buy RESTS at
    # bid+1 rather than crossing, so without this the next pass -- five
    # seconds later, with the same gates still green -- would send another
    # one, and the window would end with several resting buys where the
    # operator asked for one.
    if await sell_guard.live_orders(client, ticker):
        log.info("  an order is already working on %s — waiting for it to "
                 "fill rather than sending another", ticker)
        return "watching"

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
    # the gate that already refused anything outside it. Paying up can never
    # cost more than the engine was authorised to pay.
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
    tp_c, sl_c = _tp_sl(entry, args.tp_pct, args.sl_pct)

    order = await venue.place_buy(client, ticker, side, entry, args.contracts)
    if not order:
        # Refused, not disqualified. The window is still open and the gates
        # may still be green, so the next pass tries again rather than writing
        # this quarter-hour off.
        log.warning("  the buy was not accepted — will retry while the "
                    "window is open")
        # Say what the exchange had to spend, per shard. "insufficient
        # balance" against a visibly funded account is the single most
        # confusing answer this bot can get, because the figure the desk and
        # the Kalshi app both show is the TOTAL -- while an order is settled
        # against the shard its market lives on.
        await _log_balance(client, ticker)
        return "watching"

    body = order.get("order") if isinstance(order, dict) else None
    body = body if isinstance(body, dict) else (order or {})
    placed = {"side": side, "entry": entry, "tp_c": tp_c, "sl_c": sl_c,
              "order_id": str(body.get("order_id") or body.get("id") or ""),
              "raw": body}

    # ACCEPTED IS NOT FILLED, and NOTHING is monitored until it is. An order
    # that finds no counterparty is accepted and comes back as a perfectly
    # ordinary response with fill_count_fp 0 -- and reading that as an entry
    # means announcing a position, resting a take-profit against nothing and
    # arming a stop on nothing. A sell order backed by no position is the
    # worst outcome available here, so the fill is checked first, through the
    # same helper every engine on this desk uses.
    filled = sell_guard.filled_count(order)
    if filled <= 0:
        # Not a failure: a bid at bid+1 does not cross, so RESTING is the
        # normal outcome. It is remembered here and _arm_filled picks it up
        # the moment it becomes a position -- which is what makes "monitor
        # only after the fill" true for every entry rather than only for the
        # ones that happened to cross.
        log.info("  resting at %dc (%s) — will monitor it as soon as it "
                 "fills", entry, body.get("status") or "accepted")
        args.pending[ticker] = placed
        return "watching"

    log.info("  entered %g @ %dc (FILLED); take-profit %dc, stop %dc",
             filled, entry, tp_c, sl_c)
    _record(args, placed, ticker, filled)
    _manage(client, venue, args, ticker, side, filled, tp_c, sl_c)
    return "placed"


# ---------------------------------------------------------------------------
# The loop.

async def amain(profile: Profile, args) -> int:
    import bot_kalshi_btc15 as venue

    client = venue.KalshiClient()
    try:
        if args.once:
            await run_once(client, profile, args)
            return 0
        while True:
            status = "idle"
            try:
                status = await run_once(client, profile, args)
            except Exception as exc:                    # noqa: BLE001
                # A failed pass is not a reason to exit. A bot that quits
                # silently is worse than one that logs and retries.
                log.warning("pass failed: %s: %s", type(exc).__name__, exc)
            # Fast while a window is open or about to be, slow otherwise.
            # Between windows there is nothing to see for ten minutes at a
            # time, and polling hard through that only spends API calls.
            near = status in ("watching", "opening", "placed")
            await asyncio.sleep(args.window_poll_s if near else args.poll_s)
    finally:
        for task in list(args.stops):
            task.cancel()
        await client.close()


def main(profile: Profile) -> int:
    """Entry point. Each bot script names its Profile and calls this."""
    logging.basicConfig(
        level=logging.INFO,
        format=f"[{profile.bot_key}-{profile.version}] %(message)s")
    for _noisy in NOISY_LOGGERS:
        logging.getLogger(_noisy).setLevel(logging.WARNING)

    ap = argparse.ArgumentParser(description=f"{profile.bot_key} "
                                             f"{profile.version} (V7 engine)")
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
    args.min_price_c = _env("min_price_c", 30, int)
    args.max_price_c = _env("max_price_c", 65, int)
    args.opens_at = _env("entry_open_s", 5, int)
    args.closes_at = _env("entry_close_s", 300, int)
    args.window_poll_s = _env("window_poll_s", args.window_poll_s, int)
    # How far above bid+1 to bid. ZERO normally; the knob stays for a book
    # that ticks away faster than it can be read.
    args.cross_c = _env("cross_c", 0, int)
    # Live state for one run: the monitor tasks, which markets already have
    # one, and the buys that are resting and not yet filled.
    args.stops: set = set()
    args.managed: set = set()
    args.pending: dict = {}
    args.profile = profile

    # Which operator's ledger this trade belongs in. The station launches
    # these bots with the CWD set to the operator's own folder, so the folder
    # name is the slug -- and it is the only source that is always present.
    # BTC_CUSTOMER is set only by the env_customer launch style, and argv only
    # on a hand run, so an engine reading either of those alone records
    # nothing under the station's own launch style.
    args.customer = (args.customer or os.environ.get("BTC_CUSTOMER")
                     or Path.cwd().name)

    # The station decides when it started us; --live decides on a hand run.
    # Read through lifecycle.wants_live, which sits beside the code that
    # WRITES these flags, so the two cannot drift.
    from app.domains.botstation import lifecycle

    args.live = lifecycle.wants_live(args.live)

    # RESTING, because the engine bids one cent above the best bid rather than
    # paying the ask. That price does not cross, so immediate-or-cancel would
    # cancel every order the instant it was sent.
    os.environ.setdefault("KALSHI_TIF",
                          _env("time_in_force", "good_till_canceled"))

    from app.core.config import get_settings

    if args.live and get_settings().paper_only:
        log.error("this server is locked to paper; --live is refused")
        return 2

    log.info("%s %s (%s rule) — %s | %s board, row %r | entry %ds-%ds after "
             "open | "
             "pay %dc-%dc | TP +%g%% SL -%g%% | %s | checking every %ds in "
             "the window, %ds outside it",
             profile.bot_key, profile.version, profile.rule,
             "LIVE" if args.live else "paper (no orders will be sent)",
             profile.board, profile.row_key, args.opens_at, args.closes_at,
             args.min_price_c, args.max_price_c, args.tp_pct, args.sl_pct,
             os.environ.get("KALSHI_TIF", "good_till_canceled"),
             args.window_poll_s, args.poll_s)
    if profile.rule == "majority":
        log.info("the rule: at least 3 of 4 timeframes CALL and at least 3 "
                 "rising ↑ -> buy YES; 3 of 4 PUT and 3 rising ↑ -> buy NO; "
                 "anything else -> stand aside")
    else:
        log.info("the rule: 1m, 2m, 5m and 10m ALL call -> buy YES; all put "
                 "-> buy NO; anything else -> stand aside")
    return asyncio.run(amain(profile, args))
