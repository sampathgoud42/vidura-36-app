"""BreakoutRadar's scan: fetch once, judge many times -- and keep the result.

A scan has two halves with very different costs. Fetching a market's candles
is ~500 tickers from Yahoo and takes a minute or two; judging them against the
eight rules takes milliseconds. So they are separate:

  * a SWEEP downloads one (market, timeframe) and keeps the prepared arrays. It
    runs only when asked ("Run Scan", the page's own auto-refresh, or the
    day's first sign-in) and never on a request thread -- the answer says
    `refreshing`, with progress, and the page polls. Nothing refreshes on a
    timer of the server's own.
  * every read JUDGES the cached arrays with the thresholds it was sent, so the
    parameter drawer's sliders answer at once and download nothing.

STORED. Each sweep's result, judged with the thresholds it was started with,
replaces that market and timeframe's rows in the database (scan_store:
truncate and load). A read with no arrays in memory -- after a restart, or for
a combination the day's first sign-in swept -- answers from those rows, with
when they were scanned, and says whether its own thresholds are the ones they
were judged with (`params_match`). Only arrays in memory can be re-judged, so a
different threshold on stored rows needs a Run Scan.

Arrays are kept for the few most recently read combinations (KEEP_SERIES).
All ten combinations of ~500 tickers would hold a quarter of a gigabyte for
views nobody has open, and the stored rows already answer for the rest.

Market data is the same for every operator, so the cache is shared: one
operator's scan is every operator's scan. Market cap is looked up only for the
few names that pass the other seven rules, and cached for the day.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
import time
from collections import Counter, OrderedDict

from app.domains.trading.market import breakout, fundamentals, universes, yahoo

logger = logging.getLogger(__name__)

NEAR_MISS_LIMIT = 30
# Market caps looked up on a request thread before it answers. Past this the
# rest are fetched behind the answer and show as unverified until they land:
# a drawer slid to zero can make every name a contender, and five hundred
# Yahoo calls would outlast the page's own timeout. A sweep storing its rows
# is not on a request thread, and looks every one up.
SYNC_CAPS = 24
KEEP_SERIES = 4

# The order a market's sweep takes its timeframes (sweep_market): the daily
# first, since its download is every timeframe's daily context, and the two
# hourly ones together, since one 180-day hourly download serves both.
ORDER = ("1d", "5m", "15m", "1h", "4h")

# (market, timeframe) -> {"series": {ticker: Series}, "at", "universe", "took_s",
#                         "missing", "trigger"}, least recently read first
_DATA: OrderedDict[tuple[str, str], dict] = OrderedDict()
# (market, timeframe) -> {"phase", "done", "total", "started", "trigger"}
_JOBS: dict[tuple[str, str], dict] = {}
# (market, timeframe) -> {"at", "reason"}: the last sweep that failed outright
_ERRORS: dict[tuple[str, str], dict] = {}
_THREADS: set[threading.Thread] = set()
_LOCK = threading.Lock()


class NoCandles(RuntimeError):
    """Yahoo answered for none of the universe: a failed sweep, not a scan of
    nothing to store over the last good one."""


def _keep(key: tuple[str, str], data: dict) -> None:
    """Hold a sweep's arrays, dropping the least recently read past
    KEEP_SERIES. The caller holds _LOCK."""
    _DATA[key] = data
    _DATA.move_to_end(key)
    while len(_DATA) > KEEP_SERIES:
        _DATA.popitem(last=False)


def _progress(key: tuple[str, str]):
    def report(done: int, total: int) -> None:
        with _LOCK:
            if key in _JOBS:
                _JOBS[key].update(phase="downloading", done=done, total=total)
    return report


def _phase(key: tuple[str, str], phase: str) -> None:
    with _LOCK:
        if key in _JOBS:
            _JOBS[key].update(phase=phase)


def _prepared(symbols: list[str], candles: dict, daily: dict, timeframe: str) -> dict:
    series = {}
    for sym in symbols:
        prepared = breakout.prepare(sym, candles.get(sym), daily.get(sym), timeframe=timeframe)
        if prepared is not None:
            series[sym] = prepared
    return series


def _sweep(market: str, timeframe: str) -> dict:
    key = (market, timeframe)
    started = time.time()
    universe = universes.for_market(market)
    symbols = universe["symbols"]

    candles, daily = yahoo.fetch(market, symbols, timeframe, progress=_progress(key))
    if not daily:
        # judged without its daily context every name would fail two rules
        raise NoCandles(f"Yahoo returned no daily candles for any of the {len(symbols)} tickers")
    _phase(key, "preparing")
    series = _prepared(symbols, candles, daily, timeframe)
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


def _judge(data: dict, market: str, timeframe: str, params: breakout.Params, *,
           sync_caps: int | None = SYNC_CAPS):
    """Every ticker against the rules; market cap only where it can matter.
    ``sync_caps`` None looks every contender's cap up before answering."""
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
            now = len(missing) if sync_caps is None else sync_caps
            facts.update(fundamentals.lookup(missing[:now]))
            if missing[now:]:
                fundamentals.warm(missing[now:])
        for ticker, sym in by_yahoo.items():
            known = facts.get(ticker) or {}
            cap = fundamentals.market_cap(known, results[sym]["price"])
            results[sym] = breakout.evaluate(data["series"][sym], params, timeframe=timeframe,
                                             market=market, market_cap=cap)
            results[sym]["name"] = known.get("name")
            results[sym]["industry"] = known.get("industry")
    return results


def _summary(data: dict, results: dict) -> dict:
    """The table, the near misses and the rule counts from judged results."""
    judged = [r for r in results.values() if r.get("available")]
    rows = [r for r in judged if r["passed"]]
    rows.sort(key=lambda r: (r["breakout_age"], -(r["rvol"] or 0)))
    near = [r for r in judged if len(r["failed"]) == 1]
    near.sort(key=lambda r: (r["failed"][0], -(r["rvol"] or 0)))
    failures = Counter(rule for r in judged for rule in r["failed"])
    return {"scanned": len(judged),
            "unavailable": len(data["missing"]) + len(results) - len(judged),
            "rows": rows, "near_misses": near[:NEAR_MISS_LIMIT],
            "failures": {rule: failures.get(rule, 0) for rule in breakout.RULES}}


def _store(market: str, timeframe: str, data: dict, params: breakout.Params,
           trigger: str) -> None:
    """Judge a fresh sweep with ``params`` and truncate-and-load its rows."""
    from app.domains.trading.market import scan_store

    got = _summary(data, _judge(data, market, timeframe, params, sync_caps=None))
    scan_store.replace_breakout(
        market, timeframe, rows=got["rows"], near_misses=got["near_misses"], trigger=trigger,
        meta={"params": params.resolved(timeframe, market), "took_s": data["took_s"],
              "universe": data["universe"], "scanned": got["scanned"],
              "unavailable": got["unavailable"], "failures": got["failures"],
              "fetched_at": round(data["at"], 3)})


def _failed(key: tuple[str, str], exc: Exception, trigger: str) -> None:
    reason = str(exc) if isinstance(exc, NoCandles) else \
        f"the sweep stopped ({type(exc).__name__})"
    with _LOCK:
        _ERRORS[key] = {"at": time.time(), "reason": reason}
    # The last good scan stays readable; its age says how old it is.
    logger.warning("breakout sweep (%s) %s %s failed: %s: %s", trigger, key[0], key[1],
                   type(exc).__name__, exc)


def start(market: str, timeframe: str, params: breakout.Params | None = None, *,
          trigger: str = "rescan") -> bool:
    """Start a sweep unless one is already running. True when one started.
    Its rows are stored judged with ``params`` -- the thresholds of whoever
    asked -- or the specification's."""
    key = (market, timeframe)
    judge_with = params or breakout.Params()
    with _LOCK:
        if key in _JOBS:
            return False
        _JOBS[key] = {"phase": "starting", "done": 0, "total": 0, "started": time.time(),
                      "trigger": trigger}

    def run() -> None:
        try:
            got = _sweep(market, timeframe)
            if not got["series"]:
                raise NoCandles(f"Yahoo returned no candles for any of the "
                                f"{len(got['missing'])} tickers")
            got["trigger"] = trigger
            with _LOCK:
                _keep(key, got)
            _phase(key, "storing")
            _store(market, timeframe, got, judge_with, trigger)
            with _LOCK:
                _ERRORS.pop(key, None)
            logger.info("breakout sweep (%s) %s %s: %d prepared, %d missing, %.1fs", trigger,
                        market, timeframe, len(got["series"]), len(got["missing"]),
                        got["took_s"])
        except Exception as exc:                        # noqa: BLE001
            _failed(key, exc, trigger)
        finally:
            with _LOCK:
                _JOBS.pop(key, None)
                _THREADS.discard(threading.current_thread())

    thread = threading.Thread(target=run, daemon=True, name=f"breakout-{market}-{timeframe}")
    with _LOCK:
        _THREADS.add(thread)
    thread.start()
    return True


def params_from(resolved: dict | None) -> breakout.Params | None:
    """Thresholds back from a stored run's resolved ones, or None."""
    if not isinstance(resolved, dict):
        return None
    names = {f.name for f in dataclasses.fields(breakout.Params)}
    try:
        return breakout.Params(**{k: v for k, v in resolved.items() if k in names})
    except (TypeError, ValueError):
        return None


def sweep_market(market: str, timeframes, *, trigger: str = "daily",
                 skip=None) -> dict[str, str]:
    """Sweep and store several timeframes of one market on THIS thread.

    The downloads are shared, which is the point of taking a market at once:
    the year of daily bars is every timeframe's context (and the 1d scan's
    candles), and one 180-day hourly download is both the 4h scan's (folded)
    and the 1h scan's (its last 60 days, what Yahoo's own 60-day period
    returns). Four downloads per market instead of nine.

    Each timeframe is judged with the thresholds its stored rows were last
    judged with -- someone's Run Scan -- else the specification's, so the
    morning's rows match what the page asks for. A timeframe already being
    swept is left to that sweep, and one ``skip(timeframe)`` says is done by
    now (someone ran it while this sweep worked through the others) is left
    alone. Returns {timeframe: what happened}.
    """
    from app.domains.trading.market import scan_store

    wanted = [tf for tf in ORDER if tf in set(timeframes)]
    universe = universes.for_market(market)
    symbols = universe["symbols"]
    info = {k: v for k, v in universe.items() if k != "symbols"}
    daily: dict | None = None
    hourly: dict | None = None
    outcome: dict[str, str] = {}
    for timeframe in wanted:
        key = (market, timeframe)
        if skip is not None and skip(timeframe):
            outcome[timeframe] = "already scanned"
            continue
        with _LOCK:
            if key in _JOBS:
                outcome[timeframe] = "already running"
                continue
            _JOBS[key] = {"phase": "starting", "done": 0, "total": 0,
                          "started": time.time(), "trigger": trigger}
        started = time.time()
        try:
            report = _progress(key)
            if daily is None:
                daily = yahoo.frames(market, symbols, *yahoo.DAILY, intraday=False,
                                     progress=report)
            if not daily:
                # Without the daily bars every name fails liquidity and
                # near-a-high, which would store as "nothing broke out". The
                # next timeframe asks Yahoo again.
                daily = None
                raise NoCandles(f"Yahoo returned no daily candles for any of the "
                                f"{len(symbols)} tickers")
            if timeframe == "1d":
                candles = dict(daily)
            elif timeframe in ("1h", "4h"):
                if hourly is None:
                    hourly = yahoo.frames(market, symbols, *yahoo.FETCH["4h"], intraday=True,
                                          progress=report)
                candles = ({s: yahoo.four_hour(f, market) for s, f in hourly.items()}
                           if timeframe == "4h" else
                           {s: yahoo.trim_days(f, market, 60) for s, f in hourly.items()})
            else:
                candles = yahoo.frames(market, symbols, *yahoo.FETCH[timeframe],
                                       intraday=True, progress=report)
            _phase(key, "preparing")
            series = _prepared(symbols, candles, daily, timeframe)
            del candles
            if not series:
                raise NoCandles(f"Yahoo returned no candles for any of the {len(symbols)} tickers")
            data = {"series": series, "at": time.time(),
                    "took_s": round(time.time() - started, 1), "universe": info,
                    "missing": [s for s in symbols if s not in series], "trigger": trigger}
            with _LOCK:
                # Fresher arrays for a combination someone is reading; the
                # others are not kept -- their stored rows answer for them.
                if key in _DATA:
                    _DATA[key] = data
            _phase(key, "storing")
            last = scan_store.run_meta(scan_store.BREAKOUT,
                                       scan_store.breakout_combo(market, timeframe))
            params = params_from((last or {}).get("params")) or breakout.Params()
            _store(market, timeframe, data, params, trigger)
            with _LOCK:
                _ERRORS.pop(key, None)
            outcome[timeframe] = "stored"
            logger.info("breakout sweep (%s) %s %s: %d prepared, %.1fs", trigger, market,
                        timeframe, len(series), data["took_s"])
        except Exception as exc:                        # noqa: BLE001
            _failed(key, exc, trigger)
            outcome[timeframe] = "failed"
        finally:
            with _LOCK:
                _JOBS.pop(key, None)
    return outcome


def _stored(base: dict, market: str, timeframe: str, resolved: dict,
            error: dict | None) -> dict:
    """The answer from the stored rows, when no arrays are in memory."""
    from app.domains.trading.market import scan_store

    stored = scan_store.breakout(market, timeframe)
    if stored is None:
        job = base["progress"]
        return {**base, "at": None, "age_s": None, "rows": [], "near_misses": [],
                "failures": {}, "scanned": 0, "universe": None, "last_error": error,
                "note": ("the first scan is running" if job
                         else "no scan yet for this market and timeframe -- run one")}
    meta = stored["meta"]
    judged_with = meta.get("params") or resolved
    if error and error["at"] <= stored["at"]:
        error = None
    return {**base, "params": judged_with, "params_match": judged_with == resolved,
            "stored": True, "at": stored["at"],
            "age_s": round(time.time() - stored["at"], 1),
            "scanned_at": stored["scanned_at"], "trade_date": stored["trade_date"],
            "trigger": stored["trigger"], "took_s": meta.get("took_s"),
            "universe": meta.get("universe"), "scanned": meta.get("scanned", 0),
            "unavailable": meta.get("unavailable", 0), "rows": stored["rows"],
            "near_misses": stored["near_misses"], "failures": meta.get("failures") or {},
            "last_error": error}


def scan(market: str, timeframe: str, params: breakout.Params, *, refresh: bool = False) -> dict:
    key = (market, timeframe)
    if refresh:
        start(market, timeframe, params)
    with _LOCK:
        data = _DATA.get(key)
        if data is not None:
            _DATA.move_to_end(key)
        job = dict(_JOBS[key]) if key in _JOBS else None
        error = dict(_ERRORS[key]) if key in _ERRORS else None

    resolved = params.resolved(timeframe, market)
    base = {"market": market, "timeframe": timeframe, "refreshing": job is not None,
            "progress": job, "params": resolved}
    if data is None:
        return _stored(base, market, timeframe, resolved, error)

    got = _summary(data, _judge(data, market, timeframe, params))
    if error and error["at"] <= data["at"]:
        error = None
    return {**base, "at": round(data["at"], 3), "age_s": round(time.time() - data["at"], 1),
            "took_s": data["took_s"], "universe": data["universe"],
            "trigger": data.get("trigger"), "params_match": True, "last_error": error,
            **got}


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
    """Wait for sweeps and forget every scan held in memory (shutdown, tests).
    The stored rows are the database's, and stay."""
    with _LOCK:
        threads = list(_THREADS)
    for thread in threads:
        thread.join(timeout=timeout)
    with _LOCK:
        _THREADS.clear()
        _DATA.clear()
        _JOBS.clear()
        _ERRORS.clear()
