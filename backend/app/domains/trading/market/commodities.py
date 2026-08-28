"""Commodity DMI, read from Tradier during the regular session.

The commodity bots trade Kalshi contracts on gold, silver and oil, but Kalshi
does not publish a price series to compute an indicator from. So the signal
comes from a liquid ETF that tracks the same underlying:

    gold15    GLD
    silver15  SLV
    oil15     USO

Inside 08:30-15:00 CST Monday to Friday those ETFs trade, Tradier serves their
bars, and the reading comes from the SAME indicator the desk uses -- so the
board and the bot agree about what the market is doing. Outside that window
the ETFs are shut and their last bar is stale, so the off-hours engine
(yfinance futures) answers instead and the response says so.

Which source produced a reading is part of the answer, not a detail. An
operator looking at a gold signal at 7pm needs to know it came from futures
rather than from a closed ETF -- they are not the same number and they do not
move together overnight.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from app.domains.trading.execution import venue as venue_mod
from app.domains.trading.market import indicators
from app.domains.trading.risk import clock

logger = logging.getLogger(__name__)

# The intervals the commodity board offers. 1min and 5min come straight from
# the venue; 2min is folded from 1min bars because Tradier does not serve it.
OFFERED_INTERVALS = ("1min", "2min", "5min")

# One reading cannot change until the next bar closes, so the cache is keyed
# by interval and expires just inside the shortest bar.
_TTL_S = 55
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()


@dataclass(frozen=True)
class Proxy:
    bot_key: str
    symbol: str
    label: str


def proxies_from_registry() -> list[Proxy]:
    """Which bots want a commodity reading, and which symbol stands in.

    Read from each bot's own config rather than hard-coded here. A fourth
    commodity bot declares its proxy in its config entry and appears on this
    board with no edit to this file -- the same onboarding contract everything
    else obeys.
    """
    from app.domains.botstation import registry

    out = []
    for config in registry.all_bots():
        symbol = (config.extra or {}).get("proxy_symbol")
        if symbol:
            out.append(Proxy(bot_key=config.key, symbol=symbol,
                             label=config.name))
    return out


def _cached(key: str) -> dict | None:
    with _lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < _TTL_S:
        return hit[1]
    return None


def _store(key: str, value: dict) -> None:
    with _lock:
        _cache[key] = (time.time(), value)


def _from_tradier(cred, symbol: str, interval: str, *,
                  sandbox: bool) -> dict | None:
    """One reading, from venue bars.

    2min is folded from 1min here rather than asked for, because the venue
    does not serve it. Doing the fold in indicators.aggregate keeps that fact
    in one place instead of every caller inventing its own.
    """
    native, factor = indicators.source_interval(interval)
    bars = venue_mod.timesales(
        symbol, interval=native, cred=cred, sandbox=sandbox,
        start=indicators.start_date(interval))
    if not bars:
        return None
    return indicators.dmi(indicators.aggregate(bars, factor))


def _from_off_hours(symbol: str, bot_key: str) -> dict | None:
    """The existing futures engine, unchanged.

    Deliberately left where it is. It is a vendored engine the commodity bots
    already trade on, and swapping its internals is a different change from
    choosing when to consult it.
    """
    try:
        from app.services import commodity_signals as legacy

        snapshot = legacy.snapshot(force=False) or {}
        return (snapshot.get("signals") or {}).get(bot_key)
    except Exception as exc:                            # noqa: BLE001
        logger.info("off-hours commodity source unavailable: %s", exc)
        return None


def snapshot(cred=None, *, interval: str = "5min", sandbox: bool = True,
             force: bool = False, at=None) -> dict:
    """The commodity board: one row per bot that declares a proxy symbol."""
    if interval not in OFFERED_INTERVALS:
        raise ValueError(
            f"interval must be one of {', '.join(OFFERED_INTERVALS)}")

    in_session = clock.is_regular_session(at)
    key = f"{interval}:{'rth' if in_session else 'off'}:{'sb' if sandbox else 'live'}"
    if not force:
        hit = _cached(key)
        if hit is not None:
            return hit

    rows = []
    for proxy in proxies_from_registry():
        reading, source = None, "unavailable"
        if in_session and cred is not None:
            try:
                reading = _from_tradier(cred, proxy.symbol, interval,
                                        sandbox=sandbox)
                source = "tradier"
            except Exception as exc:                    # noqa: BLE001
                # One symbol failing must not blank the whole board.
                logger.info("commodity %s via tradier: %s", proxy.symbol, exc)
        if reading is None:
            reading = _from_off_hours(proxy.symbol, proxy.bot_key)
            if reading is not None:
                source = "futures_off_hours"

        rows.append({
            "bot_key": proxy.bot_key,
            "label": proxy.label,
            "symbol": proxy.symbol,
            "source": source,
            # Null rather than omitted: the board lays out one row per bot, and
            # a missing row reads as a rendering bug rather than "no reading".
            "plus_di": (reading or {}).get("plus_di"),
            "minus_di": (reading or {}).get("minus_di"),
            "adx": (reading or {}).get("adx"),
            "side": (reading or {}).get("side"),
            "bars": (reading or {}).get("bars", 0),
        })

    out = {
        "rows": rows,
        "meta": {
            "interval": interval,
            "native_interval": indicators.source_interval(interval)[0],
            "aggregated_from": (indicators.source_interval(interval)[0]
                                if indicators.source_interval(interval)[1] > 1
                                else None),
            "in_session": in_session,
            "session": "08:30-15:00 CST Mon-Fri",
            "venue": "sandbox" if sandbox else "live",
            "ttl_s": _TTL_S,
        },
    }
    _store(key, out)
    return out
