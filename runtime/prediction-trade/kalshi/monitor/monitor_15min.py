#!/usr/bin/env python
"""monitor_15min — record the yes and no bid of every 15-minute market.

It does not trade. It watches: every fifteen seconds it asks Kalshi what the
current fifteen-minute market is for each series it was launched with, reads
both sides of the book, and writes one row.

    monitor."btc-15"
    id             ticker                       timestamp            yes  no
    btc-15-00001   KXBTC15M-26SEP101215-15      2026-09-10 11:15:07   11  88
    btc-15-00002   KXBTC15M-26SEP101215-15      2026-09-10 11:15:22   10  89
    ...
    btc-15-00061   KXBTC15M-26SEP101230-15      2026-09-10 11:30:04   47  52

The ticker changes on its own at the quarter hour, because every pass asks the
exchange which market is current rather than remembering one. That is the
whole rollover story: there is no "wait for the next market" branch to get
wrong, no gap while a bot notices, and a series that goes quiet for a session
(oil and copper both do) simply reports nothing until it comes back.

MARKETS ARE MONITORED IN PARALLEL. One asyncio task each, all on one HTTP
connection pool, so fourteen markets cost fourteen small requests every
fifteen seconds rather than fourteen processes.

NO CREDENTIAL IS USED OR NEEDED. Kalshi's market data is public, and this
reads nothing else -- no portfolio, no orders, no positions. So the monitor
keeps working when a key expires, which for the thing that records what the
market did is the whole point. It also means it can never place an order: not
by configuration, but because it holds nothing that could.

Usage:
    monitor_15min.py [--markets btc-15,eth-15] [--once] [--poll-s 15]

The bot station passes the operator's selection as the MARKETS environment
variable; --markets is for a hand run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# parents[3]: monitor -> kalshi -> prediction-trade -> runtime -> ROOT
_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parents[3]
for _p in (str(ROOT / "backend"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Force UTF-8 so a redirected log on Windows does not die on a bullet.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

log = logging.getLogger("monitor15")
for _noisy in ("httpx", "httpcore", "urllib3", "asyncio"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

# Market data only, and public. The trading bots' BASE_URI works too and is
# preferred when the operator has set one, so a desk pointed at a different
# Kalshi environment monitors that environment rather than production.
PUBLIC_BASE = "https://api.elections.kalshi.com/trade-api/v2"


def _env_markets() -> list[str]:
    """The operator's selection, from the launch form.

    The station passes JSON for a list-typed option. A bare comma-separated
    string is accepted too, because that is what a hand run types.
    """
    raw = (os.environ.get("MARKETS") or "").strip()
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except ValueError:
        return [p.strip() for p in raw.split(",") if p.strip()]
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    return [str(v) for v in (value or [])]


async def current_market(client, series: str) -> dict | None:
    """The fifteen-minute market that is trading RIGHT NOW for this series.

    Asked fresh every pass. Kalshi lists one open market per series at a time,
    but the earliest close is taken rather than the first row returned: order
    is not promised by the API, and "whichever came back first" is the kind of
    assumption that works until the day it does not.
    """
    response = await client.get("/markets", params={
        "series_ticker": series, "status": "open", "limit": 10})
    response.raise_for_status()
    markets = response.json().get("markets") or []
    best, best_close = None, None
    for market in markets:
        if str(market.get("market_type") or "binary").lower() != "binary":
            continue
        close = _parsed(market.get("close_time"))
        if close is None:
            continue
        if best_close is None or close < best_close:
            best, best_close = market, close
    return best


def _parsed(stamp: str | None):
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None


async def watch(client, market, *, poll_s: int, once: bool = False) -> None:
    """One market's own loop. Never raises; a bad pass costs one tick.

    Runs forever so the desk can leave it up across sessions. Every failure
    mode below is a REASON TO WAIT, not a reason to stop: the market is
    between quarter-hours, the series is out of session, the network blipped.
    A monitor that exits on the first quiet hour is a monitor nobody trusts to
    have been running.
    """
    from app.domains.botstation import monitor as store

    store.ensure_table(market.key)
    seen_ticker: str | None = None
    quiet_logged = False

    while True:
        try:
            current = await current_market(client, market.series)
            if current is None:
                # Out of session, or between markets. Said once rather than
                # four times a minute.
                if not quiet_logged:
                    log.info("%-10s no open %s market — waiting",
                             market.key, market.series)
                    quiet_logged = True
            else:
                quiet_logged = False
                ticker = str(current.get("ticker") or "")
                yes_c = store.to_cents(current.get("yes_bid_dollars"))
                no_c = store.to_cents(current.get("no_bid_dollars"))
                row_id = store.record(market.key, ticker=ticker,
                                      yes_price=yes_c, no_price=no_c)
                if ticker != seen_ticker:
                    # The quarter turned over. Worth a line: it is the only
                    # moment the ticker in the table changes.
                    log.info("%-10s now %s", market.key, ticker)
                    seen_ticker = ticker
                log.debug("%-10s %s yes=%s no=%s -> %s", market.key, ticker,
                          yes_c, no_c, row_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:                        # noqa: BLE001
            log.info("%-10s pass failed: %s: %s", market.key,
                     type(exc).__name__, exc)
        if once:
            return
        await asyncio.sleep(poll_s)


async def amain(markets, *, poll_s: int, once: bool) -> int:
    import httpx

    base = os.environ.get("BASE_URI") or PUBLIC_BASE
    # One pool for every market. Fourteen tasks sharing keep-alive is a few
    # sockets; fourteen clients is fourteen handshakes every fifteen seconds.
    async with httpx.AsyncClient(base_url=base, timeout=20.0) as client:
        try:
            await asyncio.gather(*(
                watch(client, m, poll_s=poll_s, once=once) for m in markets))
        except asyncio.CancelledError:
            pass
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="[monitor15] %(message)s")

    ap = argparse.ArgumentParser(description="record 15-minute market bids")
    ap.add_argument("customer", nargs="?", default=None)
    ap.add_argument("--markets", default="",
                    help="comma-separated keys, e.g. btc-15,eth-15")
    ap.add_argument("--once", action="store_true",
                    help="one tick per market, then exit")
    ap.add_argument("--poll-s", type=int, default=0, dest="poll_s")
    args = ap.parse_args()

    from app.domains.botstation import monitor as store

    wanted = ([p.strip() for p in args.markets.split(",") if p.strip()]
              or _env_markets())
    markets = store.resolve(wanted)

    poll_s = args.poll_s or int(os.environ.get("POLL_S") or store.POLL_S)

    where = ("monitor.db (attach it AS monitor)"
             if _sqlite() else 'the "monitor" schema')
    log.info("watching %d market%s every %ds — %s", len(markets),
             "" if len(markets) == 1 else "s", poll_s,
             ", ".join(m.key for m in markets))
    log.info("writing to %s · this bot places NO orders and uses no "
             "credential", where)
    return asyncio.run(amain(markets, poll_s=poll_s, once=args.once))


def _sqlite() -> bool:
    from app.core.config import get_settings
    return get_settings().is_sqlite


if __name__ == "__main__":
    raise SystemExit(main())
