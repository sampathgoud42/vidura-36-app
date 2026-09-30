"""Market cap and industry, for the screens that list them.

Tradier's brokerage API carries neither: a quote is price and volume, not what
the company is worth or what it does. yfinance has both, keyless, and this
project already reads it for quotes and earnings. It is one quoteSummary call
per symbol, so an answer is kept for a day, and a symbol Yahoo could not answer
is not asked about again for an hour.

Market cap moves with the price, and these screens surface exactly the names
that just moved 20%, so a day-old cap would be wrong where it matters most.
What is cached is the share count the cap implies (cap / price when fetched),
and the cap is re-marked at the screen's own price. That also gets share
classes right: GOOGL's implied count is Alphabet's whole cap over the class A
price, so the re-marked cap is the company's, not the class's.

Best-effort by construction. A screen never fails because of this module: a
symbol with no answer comes back as an empty dict and its columns read "—".
"""

from __future__ import annotations

import logging
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

TTL_S = 24 * 3600
MISS_TTL_S = 3600

# symbol -> (fetched at, facts or None for "Yahoo had nothing")
_CACHE: dict[str, tuple[float, dict | None]] = {}
_LOCK = threading.Lock()

# The desk's index symbols, as Yahoo spells them.
_INDEX = {"SPX": "^GSPC", "VIX": "^VIX", "NDX": "^NDX", "DJI": "^DJI"}


def yahoo_symbol(symbol: str) -> str:
    """Yahoo's spelling. US share classes use a dash there (BRK.B -> BRK-B);
    Indian listings already carry their exchange suffix (.NS / .BO)."""
    s = symbol.strip().upper()
    if s in _INDEX:
        return _INDEX[s]
    if s.endswith((".NS", ".BO")):
        return s
    return s.replace(".", "-").replace("/", "-")


def _num(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) and out > 0 else None


def _fetch_one(symbol: str) -> dict | None:
    """One symbol from Yahoo. The seam tests substitute: nothing else here
    reaches the network."""
    import yfinance as yf                   # deferred: a heavy import

    info = yf.Ticker(yahoo_symbol(symbol)).info or {}
    if not info or info.get("quoteType") in (None, "NONE"):
        return None
    cap = _num(info.get("marketCap"))
    price = _num(info.get("currentPrice") or info.get("regularMarketPrice")
                 or info.get("previousClose"))
    industry = info.get("industry")
    if not industry and info.get("quoteType") == "ETF":
        industry = info.get("category") or "ETF"
    return {
        "name": info.get("shortName") or info.get("longName"),
        "industry": industry,
        "sector": info.get("sector"),
        "currency": info.get("currency"),
        "market_cap": cap,
        "implied_shares": cap / price if cap and price else None,
    }


def _fresh(symbol: str, now: float) -> tuple[bool, dict | None]:
    hit = _CACHE.get(symbol)
    if hit is None:
        return False, None
    at, facts = hit
    return now - at < (TTL_S if facts is not None else MISS_TTL_S), facts


def lookup(symbols: list[str], *, workers: int = 6) -> dict[str, dict]:
    """``{symbol: facts}`` for every symbol asked about, fresh from cache where
    it can be. Never raises; an unanswered symbol maps to ``{}``."""
    wanted = list(dict.fromkeys(s.strip().upper() for s in symbols if s and s.strip()))
    now = time.time()
    out: dict[str, dict] = {}
    missing: list[str] = []
    with _LOCK:
        for sym in wanted:
            known, facts = _fresh(sym, now)
            if known:
                out[sym] = dict(facts or {})
            else:
                missing.append(sym)

    def one(sym: str) -> tuple[str, dict | None]:
        try:
            return sym, _fetch_one(sym)
        except Exception as exc:                        # noqa: BLE001
            # Yahoo throttles, renames and delists without notice; one
            # symbol it cannot answer is not a reason to lose the others.
            logger.info("fundamentals: %s unavailable (%s: %s)",
                        sym, type(exc).__name__, exc)
            return sym, None

    if missing:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(missing)))) as pool:
            got = list(pool.map(one, missing))
        stamp = time.time()
        with _LOCK:
            for sym, facts in got:
                _CACHE[sym] = (stamp, facts)
                out[sym] = dict(facts or {})
    return out


def cached(symbols: list[str]) -> dict[str, dict]:
    """What is already known and fresh, without asking Yahoo anything."""
    now = time.time()
    out: dict[str, dict] = {}
    with _LOCK:
        for sym in symbols:
            known, facts = _fresh(sym.strip().upper(), now)
            if known:
                out[sym.strip().upper()] = dict(facts or {})
    return out


_WARMING: set[str] = set()


def warm(symbols: list[str]) -> None:
    """Look these up in the background, so a later read finds them cached.
    For callers on a request thread that cannot wait for hundreds of calls."""
    with _LOCK:
        todo = [s for s in dict.fromkeys(x.strip().upper() for x in symbols)
                if s and s not in _WARMING]
        _WARMING.update(todo)
    if not todo:
        return

    def run() -> None:
        try:
            lookup(todo)
        finally:
            with _LOCK:
                _WARMING.difference_update(todo)

    threading.Thread(target=run, daemon=True, name="fundamentals-warm").start()


def market_cap(facts: dict, price: float | None) -> float | None:
    """The cap at ``price``, from the share count it implied when fetched.
    Falls back to the fetched cap when either side of that is missing."""
    shares = _num((facts or {}).get("implied_shares"))
    px = _num(price)
    if shares and px:
        return shares * px
    return _num((facts or {}).get("market_cap"))


def reset() -> None:
    with _LOCK:
        _CACHE.clear()
