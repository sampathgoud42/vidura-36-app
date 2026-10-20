#!/usr/bin/env python
"""The PREDICT-15 engine: buy the call at T+2, while the last 24h says it pays.

Every Kalshi fifteen-minute window of one coin (KXBTC15M / KXETH15M):

    at T+2 minutes (entry_open_s 120 .. entry_close_s 180 after the open)
      1. the GATE -- replay the last 24 hours of this very rule against the
         real Kalshi quotes at T+2, fee included (predict15.simulate,
         rule="call"). Its P&L must be above zero, or the window is skipped.
         Recomputed at most every GATE_TTL_S, between windows.
      2. the CALL -- predict15.predict: the digital-option fair value of the
         price against the strike, blended with Kalshi's mid. YES or NO.
      3. BUY the call's side at the live ask (YES at the YES ask, NO at
         1 - the YES bid), immediate-or-cancel, for stake_usd ($1): as many
         whole contracts as the stake buys, at least one.
    hold to settlement -- no take-profit, no stop; the replay the gate reads
    is settled the same way. The reconciler closes the ledger row.

One entry per window; nothing if the coin is already held there or an order
is already working. Paper is the default; ``--live`` is the only way to real
money and is refused when the server is locked to paper. The research is
docs/research/predict-15.md; the model is app.domains.botstation.predict15.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parents[2]
for _p in (str(ROOT / "backend"), str(_HERE / "btc" / "btc15"), str(_HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import sell_guard                                       # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

log = logging.getLogger("predict15")
NOISY_LOGGERS = ("httpx", "httpcore", "urllib3", "aiohttp", "app.domains.botstation.registry")

GATE_TTL_S = 30 * 60
GATE_DAYS = 1
DECISION_MINUTE = 2


@dataclass(frozen=True)
class Profile:
    bot_key: str        # ledger key: btc15 | eth15
    version: str        # v11 | v3
    coin: str           # BTC | ETH -- a key of predict15.COINS


def _env(name: str, fallback, cast=str):
    raw = os.environ.get(name.upper())
    if raw is None or raw == "":
        return fallback
    try:
        return cast(raw)
    except (TypeError, ValueError):
        log.warning("%s=%r is not a %s; using %r", name.upper(), raw, cast.__name__, fallback)
        return fallback


def _gate(profile: Profile, args, *, force: bool = False) -> dict:
    """The last 24h of buy-the-call-at-T+2, cached for GATE_TTL_S."""
    from app.domains.botstation import predict15

    if not force and args.gate and time.time() - args.gate_at < GATE_TTL_S:
        return args.gate
    r = predict15.simulate(profile.coin, days=GATE_DAYS, minute=DECISION_MINUTE, rule="call")
    args.gate, args.gate_at = r, time.time()
    log.info("24h gate: %s windows, call right %s, P&L %+.2f per $1 contract (ROI %s) -> %s",
             r.get("windows"), f"{r['accuracy']:.0%}" if r.get("accuracy") is not None else "?",
             r.get("pnl_per_contract") or 0.0,
             f"{r['roi']:+.1%}" if r.get("roi") is not None else "?",
             "TRADING" if (r.get("pnl_per_contract") or 0) > 0 else "SITTING OUT")
    return r


def _record(args, profile: Profile, order: dict, ticker: str, contracts: float) -> None:
    from app.domains.botstation.ledger import entries

    if not entries.record_entry(
            tenant_slug=args.customer, bot_key=profile.bot_key, bot_version=profile.version,
            ticker=ticker, external_id=order["order_id"], contracts=contracts,
            entry_price_c=order["entry"], market_title=ticker.split("-")[0],
            outcome=order["side"].upper(),
            entry_usd=round(contracts * order["entry"] / 100.0, 4),
            is_live=args.live, raw=order.get("raw") or {}):
        log.warning("  the trade was NOT written to the ledger")


async def run_once(client, profile: Profile, args) -> str:
    """One pass. "placed" | "watching" | "waiting" | "idle"."""
    from app.domains.botstation import predict15

    import bot_kalshi_btc15 as venue

    series, _product = predict15.COINS[profile.coin]
    m = await asyncio.to_thread(predict15._market, series)
    if not m:
        log.info("no open %s market", series)
        return "idle"
    ticker = m["ticker"]
    opened = predict15._ts(m["open_time"])
    age = (datetime.now(timezone.utc) - opened).total_seconds()

    if age < args.opens_at or age > args.closes_at:
        # Between decisions: keep the gate fresh here, never inside the window.
        if age > args.closes_at or age < args.opens_at - 60:
            await asyncio.to_thread(_gate, profile, args)
        return "waiting" if args.opens_at - 60 <= age < args.opens_at else "idle"
    if ticker in args.done:
        return "idle"
    args.done.add(ticker)                         # one decision per window, whatever happens

    gate = await asyncio.to_thread(_gate, profile, args)
    if (gate.get("pnl_per_contract") or 0) <= 0:
        log.info("%s T+%.0fs: SKIP -- the last 24h of this rule lost %+.2f per $1 contract",
                 ticker, age, gate.get("pnl_per_contract") or 0.0)
        return "idle"

    pred = await asyncio.to_thread(predict15.predict, profile.coin)
    if pred.get("error") or pred.get("ticker") != ticker:
        log.info("%s: no call (%s)", ticker, pred.get("error") or "the window moved on")
        return "idle"
    side = pred["call"].lower()
    pick = predict15.call_side(pred["p_yes"], pred.get("yes_bid"), pred.get("yes_ask"))
    if pick["price"] is None:
        log.info("%s: %s %s but no quote to buy at", ticker, pred["call"], f"{pred['p_yes']:.0%}")
        return "idle"
    price_c = int(round(pick["price"] * 100))
    if not args.min_price_c <= price_c <= args.max_price_c:
        log.info("%s: %s at %dc is outside %d-%dc; standing aside", ticker, pred["call"],
                 price_c, args.min_price_c, args.max_price_c)
        return "idle"
    contracts = max(1, math.floor(args.stake_usd * 100 / price_c))
    log.info("%s T+%.0fs: CALL %s %.0f%% (model %.0f%%) | %s | BUY %s x%d @ %dc = $%.2f",
             ticker, age, pred["call"], pred["p_yes"] * 100, pred["p_model"] * 100,
             pred.get("reason", ""), side.upper(), contracts, price_c, contracts * price_c / 100)

    if await venue.position_for(client, ticker):
        log.info("  already holding %s -- no second entry", ticker)
        return "idle"
    if await sell_guard.live_orders(client, ticker):
        log.info("  an order is already working on %s -- not sending another", ticker)
        return "idle"
    if not args.live:
        log.info("  paper -- no order sent")
        return "placed"

    order = await venue.place_buy(client, ticker, side, price_c, contracts)
    if not order:
        log.warning("  the buy was not accepted")
        return "idle"
    body = order.get("order") if isinstance(order, dict) else None
    body = body if isinstance(body, dict) else (order or {})
    filled = sell_guard.filled_count(order)
    if filled <= 0:
        log.info("  not filled at %dc (%s) -- immediate-or-cancel, so nothing rests", price_c,
                 body.get("status") or "no fill")
        return "idle"
    placed = {"side": side, "entry": price_c,
              "order_id": str(body.get("order_id") or body.get("id") or ""), "raw": body}
    log.info("  FILLED %g @ %dc -- held to settlement", filled, price_c)
    _record(args, profile, placed, ticker, filled)
    return "placed"


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
                log.warning("pass failed: %s: %s", type(exc).__name__, exc)
            await asyncio.sleep(args.window_poll_s if status == "waiting" else args.poll_s)
    finally:
        await client.close()


def main(profile: Profile) -> int:
    logging.basicConfig(level=logging.INFO,
                        format=f"[{profile.bot_key}-{profile.version}] %(message)s")
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    ap = argparse.ArgumentParser(description=f"{profile.bot_key} {profile.version} (PREDICT-15)")
    ap.add_argument("customer", nargs="?", default=None)
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--poll-s", type=int, default=10, dest="poll_s")
    ap.add_argument("--window-poll-s", type=int, default=2, dest="window_poll_s")
    args = ap.parse_args()

    args.stake_usd = _env("stake_usd", 1.0, float)
    args.min_price_c = _env("min_price_c", 5, int)
    args.max_price_c = _env("max_price_c", 95, int)
    args.opens_at = _env("entry_open_s", 120, int)
    args.closes_at = _env("entry_close_s", 180, int)
    args.done, args.gate, args.gate_at = set(), None, 0.0
    args.customer = (args.customer or os.environ.get("BTC_CUSTOMER") or Path.cwd().name)

    from app.domains.botstation import lifecycle

    args.live = lifecycle.wants_live(args.live)
    # Bought at the ask, so it crosses: immediate-or-cancel, never resting.
    os.environ["KALSHI_TIF"] = "immediate_or_cancel"

    from app.core.config import get_settings

    if args.live and get_settings().paper_only:
        log.error("this server is locked to paper; --live is refused")
        return 2

    log.info("%s %s (PREDICT-15) -- %s | %s | buy the call at T+%ds-%ds for $%.2f, "
             "%d-%dc, held to settlement | only while the last 24h of this rule is profitable",
             profile.bot_key, profile.version, "LIVE" if args.live else "paper (no orders will be sent)",
             profile.coin, args.opens_at, args.closes_at, args.stake_usd,
             args.min_price_c, args.max_price_c)
    return asyncio.run(amain(profile, args))
