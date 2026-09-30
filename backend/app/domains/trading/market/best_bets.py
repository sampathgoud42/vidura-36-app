"""Best Bets: the 4-hour 21-EMA screen over a watchlist, as a snapshot.

One Tradier call per symbol (15-minute bars, regular session, 40 days), folded
into 4-hour bars and read by ema_screen, then market cap and industry from
fundamentals. Sixty names is sixty requests against a venue that allows 120 a
minute in production and 60 on the sandbox, so the endpoint never waits for a
sweep: it answers from the last stored sweep and runs a new one behind it only
when asked. The desk polls while `refreshing` is set and picks the new rows up
on its own.

STORED, per venue (scan_store, truncate and load). The sheet is the same for
every operator on a venue -- one universe, one set of rules, the venue's own
bars -- so one sweep serves them all, and it survives a restart. It is not
re-swept on a timer: the day's first sign-in sweeps each venue once
(daily_scans), the refresh button sweeps again, and between the two the sheet
says exactly when its rows are from.

A symbol the venue will not answer, or that has too little history, is still
a row -- unavailable, with the reason -- because a watchlist that silently
shrinks reads as "nothing qualifies" when the truth is "nothing was asked".
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from app.domains.trading.execution import venue as venue_mod
from app.domains.trading.market import ema_screen, fundamentals
from app.services.tradier_client import TradierError

logger = logging.getLogger(__name__)

# The venues ("live", "sandbox") with a sweep running, and the last sweep of
# each that failed outright: {"at": epoch seconds, "reason": text}.
_REFRESHING: set[str] = set()
_ERRORS: dict[str, dict] = {}
_THREADS: set[threading.Thread] = set()
_LOCK = threading.Lock()

# A venue never scanned starts its first sweep when the sheet opens -- unless
# that sweep just failed, which the next open should report rather than
# repeat on every poll.
RETRY_FIRST_AFTER_S = 300.0

# Tradier answers 429 once the minute's allowance is spent. Waiting it out is
# the whole fix; the allowance resets within the minute.
RETRIES = 3
BACKOFF_S = 2.0


def universe() -> list[str]:
    from app.core.config import get_settings

    raw = get_settings().tradier_best_bets_universe
    return list(dict.fromkeys(t.strip().upper() for t in raw.split(",") if t.strip()))


def rules() -> ema_screen.Rules:
    from app.core.config import get_settings

    s = get_settings()
    return ema_screen.Rules(
        span=s.tradier_best_bets_ema_span, deep_pct=s.tradier_best_bets_deep_pct,
        near_pct=s.tradier_best_bets_near_pct,
        cross_within=s.tradier_best_bets_cross_within,
        velocity_bars=s.tradier_best_bets_velocity_bars,
        session=s.tradier_best_bets_session)


def _bars(symbol: str, *, cred, sandbox: bool, start: str, session: str) -> list[dict]:
    """One symbol's 15-minute bars, waiting out the venue's rate limit."""
    for attempt in range(RETRIES + 1):
        try:
            return venue_mod.timesales(
                symbol, cred=cred, interval="15min", start=start, sandbox=sandbox,
                session_filter="open" if session == "regular" else "all")
        except TradierError as exc:
            if exc.status == 429 and attempt < RETRIES:
                time.sleep(BACKOFF_S * (2 ** attempt))
                continue
            raise
    return []                                           # unreachable


def _row(symbol: str, *, cred, sandbox: bool, start: str,
         screen_rules: ema_screen.Rules, as_of) -> dict:
    try:
        bars = _bars(symbol, cred=cred, sandbox=sandbox, start=start,
                     session=screen_rules.session)
    except (TradierError, OSError, ValueError) as exc:
        # Never the venue's own text: a 401 body can carry the refused token.
        status = getattr(exc, "status", None)
        logger.info("best bets: %s unavailable (%s %s)", symbol,
                    type(exc).__name__, status or "")
        return {"symbol": symbol, "setup": None, "available": False, "bars": 0,
                "reason": ("the venue refused the request" if status
                           else "the venue could not be reached")}
    try:
        return ema_screen.screen(symbol, bars, screen_rules, as_of=as_of)
    except (ValueError, TypeError, KeyError, IndexError, ZeroDivisionError) as exc:
        # One malformed series costs its own row, never the sweep.
        logger.info("best bets: %s could not be read (%s: %s)", symbol,
                    type(exc).__name__, exc)
        return {"symbol": symbol, "setup": None, "available": False, "bars": 0,
                "reason": "the venue's bars could not be read"}


def _order(rows: list[dict]) -> list[dict]:
    """A (soonest catch) then B (freshest cross) then everything else,
    closest to its EMA first, and the unreadable last."""
    tables = ema_screen.by_setup(rows)
    rest = [r for r in rows if r.get("setup") is None and r.get("available")]
    rest.sort(key=lambda r: abs(r.get("distance_pct") or 0.0))
    dead = [r for r in rows if not r.get("available")]
    return tables["A"] + tables["B"] + rest + dead


def sweep(cred, *, sandbox: bool) -> dict:
    """Screen the whole universe now. Blocking; the endpoint never calls this
    on a request thread."""
    from app.core.config import get_settings

    settings = get_settings()
    screen_rules = rules()
    symbols = universe()
    started = time.time()
    as_of = ema_screen.now_eastern()
    # Tradier documents `start` as YYYY-MM-DD HH:MM, so that is what it gets.
    start = (as_of - timedelta(days=settings.tradier_best_bets_days)).strftime("%Y-%m-%d 00:00")

    workers = max(1, min(settings.tradier_best_bets_workers, len(symbols) or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(
            lambda sym: _row(sym, cred=cred, sandbox=sandbox, start=start,
                             screen_rules=screen_rules, as_of=as_of),
            symbols))

    readable = [r["symbol"] for r in rows if r.get("available")]
    facts = fundamentals.lookup(readable) if readable else {}
    for row in rows:
        known = facts.get(row["symbol"]) or {}
        row["market_cap"] = fundamentals.market_cap(known, row.get("price"))
        row["industry"] = known.get("industry")
        row["sector"] = known.get("sector")
        row["name"] = known.get("name")

    spec = ema_screen.SESSIONS[screen_rules.session]
    ordered = _order(rows)
    return {
        "rows": ordered,
        "meta": {
            "scanned": len(symbols),
            "available": len(readable),
            "matched": {"A": sum(r.get("setup") == "A" for r in rows),
                        "B": sum(r.get("setup") == "B" for r in rows)},
            "rules": screen_rules.public(),
            "timeframe": {"bar": "4h", "source_interval": "15min",
                          "session": screen_rules.session,
                          "anchor": f"{spec['open']} ET",
                          "bars_per_day": spec["bars_per_day"],
                          "hours_per_day": spec["hours_per_day"],
                          "history_days": settings.tradier_best_bets_days},
            "fundamentals": {"source": "yfinance",
                             "answered": sum(1 for s in readable if facts.get(s))},
            "as_of": as_of.isoformat(timespec="minutes"),
            "took_s": round(time.time() - started, 1),
            "venue": "sandbox" if sandbox else "live",
        },
    }


def venue_of(sandbox: bool) -> str:
    return "sandbox" if sandbox else "live"


class NothingAnswered(RuntimeError):
    """The venue answered for none of the universe: a failed sweep, not a
    sheet of empty rows to store over the last good one."""


def _run(venue: str, cred, *, sandbox: bool, trigger: str) -> None:
    """One sweep, stored. The caller has claimed the venue."""
    from app.domains.trading.market import scan_store

    try:
        got = sweep(cred, sandbox=sandbox)
        meta = got["meta"]
        if meta["scanned"] and not meta["available"]:
            reasons = sorted({r["reason"] for r in got["rows"] if r.get("reason")})
            raise NothingAnswered(f"the venue answered none of the {meta['scanned']} symbols"
                                  + (f" ({reasons[0]})" if reasons else ""))
        scan_store.replace_best_bets(venue, got["rows"], meta, trigger=trigger)
        with _LOCK:
            _ERRORS.pop(venue, None)
        logger.info("best bets sweep (%s): %s -> A %d, B %d of %d", trigger, venue,
                    meta["matched"]["A"], meta["matched"]["B"], meta["scanned"])
    except Exception as exc:                            # noqa: BLE001
        # The last stored sheet stays: stale rows whose age the sheet shows
        # beat an empty sheet that looks like a quiet market. Never the
        # exception's own text for anything else: a venue's 401 body can
        # carry the refused token.
        reason = str(exc) if isinstance(exc, NothingAnswered) else \
            f"the sweep stopped ({type(exc).__name__})"
        with _LOCK:
            _ERRORS[venue] = {"at": time.time(), "reason": reason}
        logger.warning("best bets sweep (%s) %s failed: %s", trigger, venue, reason)
    finally:
        with _LOCK:
            _REFRESHING.discard(venue)


def _claim(venue: str) -> bool:
    with _LOCK:
        if venue in _REFRESHING:
            return False
        _REFRESHING.add(venue)
        return True


def sweep_now(cred, *, sandbox: bool, trigger: str = "daily") -> bool:
    """Sweep and store on THIS thread (the day's first sign-in runs it on its
    own). False when a sweep of the venue was already running."""
    venue = venue_of(sandbox)
    if not _claim(venue):
        return False
    _run(venue, cred, sandbox=sandbox, trigger=trigger)
    return True


def _sweep_async(cred, *, sandbox: bool, trigger: str) -> None:
    """One sweep at a time per venue, behind the answer."""
    venue = venue_of(sandbox)
    if not _claim(venue):
        return

    def run() -> None:
        try:
            _run(venue, cred, sandbox=sandbox, trigger=trigger)
        finally:
            with _LOCK:
                _THREADS.discard(threading.current_thread())

    thread = threading.Thread(target=run, daemon=True, name=f"best-bets-{venue}")
    with _LOCK:
        _THREADS.add(thread)
    thread.start()


def snapshot(cred, *, sandbox: bool = True, force: bool = False) -> dict:
    """The sheet: the venue's stored rows now, with when they were scanned.

    ``force`` (the refresh button) starts a sweep but does not wait for it:
    sixty venue calls can outlast the tunnel's request ceiling, and the sheet
    polls until `refreshing` clears. A venue never scanned starts its first
    sweep here; one that has rows is swept again only when asked, or by the
    next day's first sign-in.
    """
    from app.domains.trading.market import scan_store

    venue = venue_of(sandbox)
    stored = scan_store.best_bets(venue)
    with _LOCK:
        busy = venue in _REFRESHING
        error = dict(_ERRORS[venue]) if venue in _ERRORS else None
    first = stored is None and not (error and time.time() - error["at"] < RETRY_FIRST_AFTER_S)
    if (force or first) and not busy:
        _sweep_async(cred, sandbox=sandbox, trigger="rescan" if stored else "first")
        busy = True
    # A failure older than the rows is history, not news.
    if error and stored and error["at"] <= stored["at"]:
        error = None

    if stored is None:
        return {"rows": [], "refreshing": busy, "at": None, "age_s": None,
                "last_error": error,
                "meta": {"venue": venue, "scanned": len(universe()),
                         "rules": rules().public(),
                         "note": ("the first sweep is running" if busy
                                  else "no sweep has landed for this venue yet")}}
    return {"rows": stored["rows"], "refreshing": busy, "at": stored["at"],
            "age_s": round(time.time() - stored["at"], 1),
            "scanned_at": stored["scanned_at"], "trade_date": stored["trade_date"],
            "trigger": stored["trigger"], "stored": True, "last_error": error,
            "meta": stored["meta"]}


def quiesce(timeout: float = 10.0) -> None:
    """Wait for in-flight sweeps and forget what is running (shutdown, tests).
    The stored sheets are the database's, and stay."""
    with _LOCK:
        threads = list(_THREADS)
    for thread in threads:
        thread.join(timeout=timeout)
    with _LOCK:
        _THREADS.clear()
        _REFRESHING.clear()
        _ERRORS.clear()
