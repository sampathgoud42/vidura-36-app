"""Crypto DMI: the same 1m/2m/5m/10m board, priced from Coinbase.

Crypto is the one market on this desk that never closes, so unlike the
commodity board there is no session to switch sources around. One feed
answers at 3am on a Sunday exactly as it does on a Tuesday morning, which is
why this module has no clock in it at all.

Coinbase's candle endpoint is public and keyless -- no credential reaches
this code, and none is needed. That also means no budget to protect, so the
only reason for the cache is that a reading cannot change until the next
minute closes.

The DMI itself is not computed here. It comes from the shared board module,
the same one the commodity board uses, so "the 2-minute side" means exactly
one thing across the desk rather than one thing per panel.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from app.domains.trading.market import board, indicators

logger = logging.getLogger(__name__)

COINBASE_CANDLES = "https://api.exchange.coinbase.com/products/{product}/candles"

# A minute bar cannot change until the minute is over, and the desk polls
# every 60s, so the cache expires just inside that.
_TTL_S = 55
_cache: tuple[float, dict] | None = None
_lock = threading.Lock()


@dataclass(frozen=True)
class Coin:
    key: str
    product: str
    label: str


# The board, in display order. A list rather than a dict because the order is
# part of the answer -- the desk reads left to right and BTC belongs first.
COINS = [
    Coin("btc", "BTC-USD", "BTC"),
    Coin("eth", "ETH-USD", "ETH"),
    Coin("sol", "SOL-USD", "SOL"),
    Coin("doge", "DOGE-USD", "DOGE"),
    Coin("xrp", "XRP-USD", "XRP"),
    Coin("bnb", "BNB-USD", "BNB"),
    Coin("zec", "ZEC-USD", "ZEC"),
    Coin("hype", "HYPE-USD", "HYPE"),
]

# All eight are quoted against USD, not USDC. It matters: ZEC-USDC is a
# different book at a different price entirely (~$53 against ~$800), so a
# quote pair chosen carelessly shows a real number for the wrong asset.


def _bars_from_coinbase(product: str, *, timeout: float = 15.0) -> list[dict]:
    """1-minute candles, oldest first.

    Coinbase returns ``[time, low, high, open, close, volume]`` NEWEST FIRST,
    and every indicator here assumes oldest first. Feeding the list through
    unreversed computes DMI on a series running backwards through time, which
    produces a perfectly plausible number with the trend inverted -- the kind
    of wrong answer nothing downstream can detect.
    """
    import httpx

    response = httpx.get(COINBASE_CANDLES.format(product=product),
                         params={"granularity": 60}, timeout=timeout)
    response.raise_for_status()
    raw = response.json()
    if not isinstance(raw, list):
        # Coinbase reports errors as a JSON object, not a list.
        raise ValueError(str(raw)[:160])

    bars = []
    for candle in reversed(raw):
        try:
            stamp, low, high, open_, close, volume = candle[:6]
        except (TypeError, ValueError):
            continue
        bars.append({"time": int(stamp), "open": float(open_),
                     "high": float(high), "low": float(low),
                     "close": float(close), "volume": float(volume)})
    return bars


def _row(coin: Coin) -> dict:
    try:
        bars = _bars_from_coinbase(coin.product)
    except Exception as exc:                            # noqa: BLE001
        # One coin failing must not blank the board.
        logger.info("crypto %s: %s: %s", coin.product, type(exc).__name__, exc)
        return board.unavailable_row(
            coin.key, coin.label, coin.product,
            reason=f"Coinbase did not answer for {coin.product}")

    if len(bars) < indicators.MIN_BARS:
        return board.unavailable_row(
            coin.key, coin.label, coin.product, bars_seen=len(bars),
            reason=f"only {len(bars)} bars; {indicators.MIN_BARS} needed")
    return board.row_from_bars(coin.key, coin.label, coin.product, bars,
                               "coinbase")


def snapshot(*, force: bool = False) -> dict:
    """The crypto board: one row per coin, 1m/2m/5m/10m."""
    global _cache

    if not force:
        with _lock:
            hit = _cache
        if hit is not None and time.time() - hit[0] < _TTL_S:
            return {**hit[1], "age_s": int(time.time() - hit[0])}

    started = time.time()
    # One independent HTTP call per coin, nothing shared between them.
    # Serially that is eight round trips the desk waits through for no reason.
    with ThreadPoolExecutor(max_workers=len(COINS)) as pool:
        rows = list(pool.map(_row, COINS))

    live = [r for r in rows if r.get("source") == "coinbase"]
    out = {
        "rows": rows,
        "meta": {
            "source": "coinbase" if live else "unavailable",
            "took_s": round(time.time() - started, 1),
            "scanned": len(rows),
            "venue": "coinbase",
            # Said explicitly because it is the one real difference from the
            # commodity board, which has a session and swaps sources around it.
            "session": "24/7",
            "ttl_s": _TTL_S,
        },
        "age_s": 0,
    }
    with _lock:
        _cache = (time.time(), out)
    return out
