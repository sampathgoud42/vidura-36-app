"""BreakoutRadar's scan: fetch once, judge many times.

A scan has two halves with very different costs. Fetching a market's candles
is ~500 tickers from Yahoo and takes a minute or two; judging them against the
eight rules takes milliseconds. So they are separate:

  * a SWEEP downloads one (market, timeframe) and keeps the prepared arrays. It
    runs only when asked ("Run Scan", or the page's own auto-refresh) and never
    on a request thread -- the answer says `refreshing`, with progress, and the
    page polls. Nothing refreshes on its own: the operator decides when data is
    fetched.
  * every read JUDGES the cached arrays with the thresholds it was sent, so the
    parameter drawer's sliders answer at once and download nothing.

Market data is the same for every operator, so the cache is shared: one
operator's scan is every operator's scan. Market cap is looked up only for the
few names that pass the other seven rules, and cached for the day.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter

from app.domains.trading.market import breakout, fundamentals, universes, yahoo

logger = logging.getLogger(__name__)

NEAR_MISS_LIMIT = 30
# Market caps looked up on a request thread before it answers. Past this the
# rest are fetched behind the answer and show as unverified until they land:
# a drawer slid to zero can make every name a contender, and five hundred
# Yahoo calls would outlast the page's own timeout.
SYNC_CAPS = 24

# (market, timeframe) -> {"series": {ticker: Series}, "at", "universe", "took_s", "missing"}
_DATA: dict[tuple[str, str], dict] = {}
# (market, timeframe) -> {"phase", "done", "total", "started"}
_JOBS: dict[tuple[str, str], dict] = {}
_THREADS: set[threading.Thread] = set()
_LOCK = threading.Lock()


def _sweep(market: str, timeframe: str) -> dict:
    key = (market, timeframe)
    started = time.time()
    universe = universes.for_market(market)
    symbols = universe["symbols"]

    def progress(done: int, total: int) -> None:
        with _LOCK:
            if key in _JOBS:
                _JOBS[key].update(phase="downloading", done=done, total=total)

    candles, daily = yahoo.fetch(market, symbols, timeframe, progress=progress)
    with _LOCK:
        if key in _JOBS:
            _JOBS[key].update(phase="preparing")
    series = {}
    for sym in symbols:
        prepared = breakout.prepare(sym, candles.get(sym), daily.get(sym), timeframe=timeframe)
        if prepared is not None:
            series[sym] = prepared
    # Warm the market caps the specification's own thresholds will ask for,
    # here in the background, so the first read after a scan need not wait.
    defaults = breakout.Params()
    passing = [sym for sym, s in series.items()
               if breakout.evaluate(s, defaults, timeframe=timeframe, market=market).get("passed")]
    if passing:
        fundamentals.lookup([yahoo.yahoo_ticker(s, market) for s in passing])
    return {"series": series, "at": time.time(), "took_s": round(time.time() - started, 1),
            "universe": {k: v for k, v in universe.items() if k != "symbols"},
            "missing": [s for s in symbols if s not in series]}


def start(market: str, timeframe: str) -> bool:
    """Start a sweep unless one is already running. True when one started."""
    key = (market, timeframe)
    with _LOCK:
        if key in _JOBS:
            return False
        _JOBS[key] = {"phase": "starting", "done": 0, "total": 0, "started": time.time()}

    def run() -> None:
        try:
            got = _sweep(market, timeframe)
            with _LOCK:
                _DATA[key] = got
            logger.info("breakout sweep %s %s: %d prepared, %d missing, %.1fs", market,
                        timeframe, len(got["series"]), len(got["missing"]), got["took_s"])
        except Exception as exc:                        # noqa: BLE001
            # The last good scan stays readable; its age says how old it is.
            logger.warning("breakout sweep %s %s failed: %s: %s", market, timeframe,
                           type(exc).__name__, exc)
        finally:
            with _LOCK:
                _JOBS.pop(key, None)
                _THREADS.discard(threading.current_thread())

    thread = threading.Thread(target=run, daemon=True, name=f"breakout-{market}-{timeframe}")
    with _LOCK:
        _THREADS.add(thread)
    thread.start()
    return True


def _judge(data: dict, market: str, timeframe: str, params: breakout.Params):
    """Every ticker against the rules; market cap only where it can matter."""
    results = {sym: breakout.evaluate(s, params, timeframe=timeframe, market=market)
               for sym, s in data["series"].items()}
    # A cap is looked up only for names the other seven rules already pass:
    # a handful, not five hundred quoteSummary calls.
    contenders = [sym for sym, r in results.items() if r.get("passed")]
    if contenders:
        by_yahoo = {yahoo.yahoo_ticker(s, market): s for s in contenders}
        facts = fundamentals.cached(list(by_yahoo))
        missing = [t for t in by_yahoo if t not in facts]
        if missing:
            facts.update(fundamentals.lookup(missing[:SYNC_CAPS]))
            if missing[SYNC_CAPS:]:
                fundamentals.warm(missing[SYNC_CAPS:])
        for ticker, sym in by_yahoo.items():
            known = facts.get(ticker) or {}
            cap = fundamentals.market_cap(known, results[sym]["price"])
            results[sym] = breakout.evaluate(data["series"][sym], params, timeframe=timeframe,
                                             market=market, market_cap=cap)
            results[sym]["name"] = known.get("name")
            results[sym]["industry"] = known.get("industry")
    return results


def scan(market: str, timeframe: str, params: breakout.Params, *, refresh: bool = False) -> dict:
    key = (market, timeframe)
    if refresh:
        start(market, timeframe)
    with _LOCK:
        data = _DATA.get(key)
        job = dict(_JOBS[key]) if key in _JOBS else None

    base = {"market": market, "timeframe": timeframe, "refreshing": job is not None,
            "progress": job, "params": params.resolved(timeframe, market)}
    if data is None:
        return {**base, "at": None, "age_s": None, "rows": [], "near_misses": [],
                "failures": {}, "scanned": 0, "universe": None,
                "note": ("the first scan is running" if job
                         else "no scan yet for this market and timeframe -- run one")}

    results = _judge(data, market, timeframe, params)
    judged = [r for r in results.values() if r.get("available")]
    rows = [r for r in judged if r["passed"]]
    rows.sort(key=lambda r: (r["breakout_age"], -(r["rvol"] or 0)))
    near = [r for r in judged if len(r["failed"]) == 1]
    near.sort(key=lambda r: (r["failed"][0], -(r["rvol"] or 0)))
    failures = Counter(rule for r in judged for rule in r["failed"])
    return {**base, "at": round(data["at"], 3), "age_s": round(time.time() - data["at"], 1),
            "took_s": data["took_s"], "universe": data["universe"],
            "scanned": len(judged),
            "unavailable": len(data["missing"]) + len(results) - len(judged),
            "rows": rows, "near_misses": near[:NEAR_MISS_LIMIT],
            "failures": {rule: failures.get(rule, 0) for rule in breakout.RULES}}


def chart(market: str, ticker: str, timeframe: str, params: breakout.Params) -> dict | None:
    """One ticker's candles and overlay, from the scan's cache when it has
    them, else fetched on their own. None when Yahoo has nothing for it."""
    with _LOCK:
        series = (_DATA.get((market, timeframe)) or {}).get("series", {}).get(ticker)
    if series is None:
        # strict: for one ticker, an outage is the answer, not "no candles"
        candles, daily = yahoo.fetch(market, [ticker], timeframe, strict=True)
        series = breakout.prepare(ticker, candles.get(ticker), daily.get(ticker),
                                  timeframe=timeframe)
        if series is None:
            return None
    yahoo_name = yahoo.yahoo_ticker(ticker, market)
    known = fundamentals.lookup([yahoo_name]).get(yahoo_name) or {}
    cap = fundamentals.market_cap(known, float(series.close[-1]))
    out = breakout.chart(series, params, timeframe=timeframe, market=market, market_cap=cap)
    out["name"] = known.get("name")
    out["industry"] = known.get("industry")
    return out


def quiesce(timeout: float = 10.0) -> None:
    """Wait for sweeps and forget every scan (shutdown, tests)."""
    with _LOCK:
        threads = list(_THREADS)
    for thread in threads:
        thread.join(timeout=timeout)
    with _LOCK:
        _THREADS.clear()
        _DATA.clear()
        _JOBS.clear()
