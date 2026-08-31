"""Commodity DMI for the bot station: gold, silver and oil, 1m/2m/5m/10m.

The commodity bots trade Kalshi contracts on gold, silver and oil, but Kalshi
does not publish a price series to compute an indicator from. So the reading
comes from something that tracks the same underlying, and WHICH something
depends on the clock:

    08:30-15:00 CST, Mon-Fri     Tradier bars on the tracking ETF
                                 gold15 GLD, silver15 SLV, oil15 USO
    any other time               API Ninjas spot prices, folded into
                                 1-minute bars by the poller

Inside the session the ETFs trade and Tradier serves their bars, through the
SAME indicator the desk uses -- so the board and the bot agree about what the
market is doing. Outside it those ETFs are shut and their last bar is stale.
A stale bar is not a quiet market, and rendering one as though it were live is
the failure worth avoiding here. API Ninjas quotes the commodity itself around
the clock, which is why it takes over.

Which source produced a row is part of the answer, not a footnote. An operator
looking at a gold signal at 7pm needs to know it came from spot rather than
from a closed ETF -- they are not the same number and they do not move
together overnight.

The board shows four timeframes, and all four come from ONE fetch of
1-minute bars folded to 2, 5 and 10. Separate fetches would let the rows describe
different instants and disagree for a reason that has nothing to do with the
market. Every source hands over the same thing -- 1-minute bars -- so all
three timeframes are available whichever one answered.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from app.domains.trading.execution import venue as venue_mod
from app.domains.trading.market import board, indicators
from app.domains.trading.risk import clock

logger = logging.getLogger(__name__)

# One reading cannot change until the next bar closes and the desk polls every
# 60s, so the cache expires just inside that.
_TTL_S = 55
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()

LABELS = {"gold15": "Gold", "silver15": "Silver", "oil15": "WTI Oil"}


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
        extra = config.extra or {}
        symbol = extra.get("proxy_symbol")
        if symbol:
            out.append((extra.get("board_order", 999),
                        Proxy(bot_key=config.key, symbol=symbol,
                              label=LABELS.get(config.key, config.name))))
    # Sorted by the order each bot DECLARES, not by registry key. The registry
    # is alphabetical, which put oil between gold and silver -- an ordering
    # that means nothing to anyone reading the board. A bot that declares no
    # order sorts last, by key, rather than jumping the queue.
    out.sort(key=lambda pair: (pair[0], pair[1].bot_key))
    return [proxy for _, proxy in out]


# ---- the sources ----------------------------------------------------------

def _bars_from_tradier(cred, symbol: str, *, sandbox: bool) -> list[dict]:
    """1-minute bars for the tracking ETF. The in-session source."""
    return venue_mod.timesales(
        symbol, interval="1min", cred=cred, sandbox=sandbox,
        start=indicators.start_date("1min")) or []


def _bars_from_api_ninjas(symbol: str, *, poll: bool = False) -> list[dict]:
    """1-minute bars accumulated from the spot feed. The off-hours source.

    Reads the vendor ONLY when ``poll`` is set, which the board sets only on
    an explicit refresh. There is no background timer: one used to call this
    every 60 seconds forever, spending a metered monthly budget on a board
    nobody might be looking at, and it carried on spending after the quota was
    exhausted and every call was certain to fail.

    The trade-off is honest and worth stating: the vendor quotes a spot PRICE,
    not a candle series, so bars accumulate one per refresh. Reaching the
    ~29 bars an ADX needs therefore takes 29 refreshes, and until then the
    futures fallback answers. That is why the row reports how many bars it
    has rather than simply showing nothing.
    """
    from app.services import hot_scan

    if poll:
        hot_scan.poll_once()
    return list((hot_scan._NINJA_BARS.get(symbol) or {}).get("bars") or [])


def ninja_age_s() -> int | None:
    """Seconds since the spot feed was last read successfully, or None.

    Reported separately from the board's own ``age_s``. With an on-demand
    source the two diverge immediately: the board can be recomputed every
    minute from bars that were last refreshed an hour ago, and it is the
    second number that tells the operator whether to trust the reading.
    """
    from app.services import hot_scan

    at = hot_scan.NINJA_LAST_OK.get("at") or 0.0
    return int(time.time() - at) if at else None


def ninja_state() -> dict:
    """What the spot poller is doing, and why it might have nothing.

    An empty row has several quite different causes -- the poller only just
    started, there is no API key, or the vendor has cut the account off for
    the month. They need different actions, so the board says which one it is
    rather than showing the same dash for all three.
    """
    from app.services import hot_scan

    status = dict(hot_scan.NINJA_STATUS)
    return {"state": status.get("state"), "detail": status.get("detail")}


def _bars_from_futures(bot_key: str) -> list[dict]:
    """1-minute futures bars, as a LAST resort.

    No longer the off-hours source -- API Ninjas is -- but kept behind it so
    an exhausted API quota degrades to a different number rather than to a
    blank board.

    Takes BARS rather than the engine's pre-scored rows. Those rows carried
    1m and 2m only, so a fallback row could not show a 5m column and the board
    would have gone blank in exactly the column that had just been added.
    Every source now hands over the same thing -- 1-minute bars -- and one
    row-builder derives all three timeframes from it.
    """
    try:
        from app.services import commodity_signals as legacy

        engine = legacy._dmi_module()
        symbol = engine.SYMBOLS.get(bot_key)
        if not symbol:
            return []
        return list(engine._fetch_1m_bars(symbol) or [])
    except Exception as exc:                            # noqa: BLE001
        logger.info("futures fallback unavailable: %s: %s",
                    type(exc).__name__, exc)
        return []


# ---- the board ------------------------------------------------------------

def snapshot(cred=None, *, sandbox: bool = True, force: bool = False,
             at: datetime | None = None, interval: str | None = None) -> dict:
    """The commodity board: one row per bot that declares a proxy symbol.

    ``interval`` is accepted and ignored. The board is defined as 1m/2m and
    always was; the parameter exists because callers already pass it.
    """
    in_session = clock.is_regular_session(at)
    key = f"{'rth' if in_session else 'off'}:{'sb' if sandbox else 'live'}"
    if not force:
        with _lock:
            hit = _cache.get(key)
        if hit is not None and time.time() - hit[0] < _TTL_S:
            return {**hit[1], "age_s": int(time.time() - hit[0])}

    started = time.time()
    rows = []

    for proxy in proxies_from_registry():
        bars: list[dict] = []
        source = "unavailable"

        if in_session and cred is not None:
            try:
                bars = _bars_from_tradier(cred, proxy.symbol, sandbox=sandbox)
                source = "tradier"
            except Exception as exc:                    # noqa: BLE001
                # One symbol failing must not blank the whole board.
                logger.info("commodity %s via tradier: %s", proxy.symbol, exc)
                bars = []
        elif not in_session:
            try:
                # force IS the refresh button. Quota is spent when the
                # operator asks for fresh prices, never on a poll they did
                # not initiate.
                bars = _bars_from_api_ninjas(proxy.symbol, poll=force)
                source = "api_ninjas_spot"
            except Exception as exc:                    # noqa: BLE001
                logger.info("commodity %s via api-ninjas: %s: %s",
                            proxy.symbol, type(exc).__name__, exc)
                bars = []

        if len(bars) >= indicators.MIN_BARS:
            rows.append(board.row_from_bars(
                proxy.bot_key, proxy.label, proxy.symbol, bars, source))
            continue

        # Not enough to compute an indicator from. Fall through rather than
        # render an empty row.
        fallback = _bars_from_futures(proxy.bot_key)
        if len(fallback) >= indicators.MIN_BARS:
            rows.append(board.row_from_bars(
                proxy.bot_key, proxy.label, proxy.symbol, fallback,
                "futures_fallback"))
            continue

        # Nothing anywhere. Say WHY: a row of dashes is indistinguishable
        # from a flat market, and these are not the same news.
        detail = ninja_state()
        warming = f"warming up: {len(bars)} of {indicators.MIN_BARS} bars"
        rows.append({
            "bot": proxy.bot_key, "label": proxy.label,
            "symbol": proxy.symbol, "source": "unavailable",
            "error": (f"api-ninjas: {detail['state']}"
                      if not in_session
                      and detail.get("state") not in (None, "ok")
                      else warming),
            "warmup": {"bars": len(bars), "needs": indicators.MIN_BARS,
                       **detail},
        })

    sources = sorted({r.get("source") for r in rows if r.get("source")})
    out = {
        "rows": rows,
        "meta": {
            # Printed next to the header, so it has to read as a source name
            # rather than a dump of internals.
            "source": "+".join(sources) if sources else "unavailable",
            "took_s": round(time.time() - started, 1),
            "scanned": len(rows),
            "in_session": in_session,
            # How stale the SPOT prices are, which is not the same as how old
            # this response is.
            "spot_age_s": ninja_age_s(),
            "spot_polls_on_refresh_only": True,
            "session": "08:30-15:00 CST Mon-Fri",
            "venue": "sandbox" if sandbox else "live",
            "ttl_s": _TTL_S,
        },
        "age_s": 0,
    }
    with _lock:
        _cache[key] = (time.time(), out)
    return out
