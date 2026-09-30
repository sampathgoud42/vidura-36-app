"""Best Bets: the 4-hour 21-EMA screen over a watchlist, as a snapshot.

One Tradier call per symbol (15-minute bars, regular session, 40 days), folded
into 4-hour bars and read by ema_screen, then market cap and industry from
fundamentals. Sixty names is sixty requests against a venue that allows 120 a
minute in production and 60 on the sandbox, so the endpoint never waits for a
sweep: it answers from the last good snapshot and refreshes behind it, the way
the HOT board and the options flow do. The desk polls while `refreshing` is
set and picks the new rows up on its own.

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

# (tenant, live) -> {"at": epoch seconds, "rows": [...], "meta": {...}}
_CACHE: dict[tuple[str, bool], dict] = {}
_REFRESHING: set[tuple[str, bool]] = set()
_THREADS: set[threading.Thread] = set()
_LOCK = threading.Lock()

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


def _sweep_async(key: tuple[str, bool], cred, *, sandbox: bool) -> None:
    """One sweep at a time per operator and venue."""
    with _LOCK:
        if key in _REFRESHING:
            return
        _REFRESHING.add(key)

    def run() -> None:
        try:
            got = sweep(cred, sandbox=sandbox)
            with _LOCK:
                _CACHE[key] = {"at": time.time(), **got}
            logger.info("best bets sweep: %s -> A %d, B %d of %d", got["meta"]["venue"],
                        got["meta"]["matched"]["A"], got["meta"]["matched"]["B"],
                        got["meta"]["scanned"])
        except Exception as exc:                        # noqa: BLE001
            # The last good snapshot stays: stale rows whose age the sheet
            # shows beat an empty sheet that looks like a quiet market.
            logger.warning("best bets sweep failed: %s: %s", type(exc).__name__, exc)
        finally:
            with _LOCK:
                _REFRESHING.discard(key)
                _THREADS.discard(threading.current_thread())

    thread = threading.Thread(target=run, daemon=True,
                              name=f"best-bets-{key[0][:8]}-{'live' if key[1] else 'sbx'}")
    with _LOCK:
        _THREADS.add(thread)
    thread.start()


def snapshot(tenant_id: str, cred, *, sandbox: bool = True, force: bool = False) -> dict:
    """The sheet: the last good rows now, refreshed behind the response.

    ``force`` (the refresh button) starts a sweep even while the snapshot is
    fresh, but still does not wait for it: sixty venue calls can outlast the
    tunnel's request ceiling, and the sheet polls until `refreshing` clears.
    """
    from app.core.config import get_settings

    key = (tenant_id, not sandbox)
    with _LOCK:
        hit = _CACHE.get(key)
        busy = key in _REFRESHING
    age = time.time() - hit["at"] if hit else None
    stale = hit is None or age > get_settings().tradier_best_bets_ttl_s
    if (stale or force) and not busy:
        _sweep_async(key, cred, sandbox=sandbox)
        busy = True

    venue = "sandbox" if sandbox else "live"
    if hit is None:
        return {"rows": [], "refreshing": busy, "at": None, "age_s": None,
                "meta": {"venue": venue, "scanned": len(universe()),
                         "rules": rules().public(),
                         "note": "the first sweep is running"}}
    return {"rows": hit["rows"], "refreshing": busy, "at": round(hit["at"], 3),
            "age_s": round(age, 1), "meta": hit["meta"]}


def quiesce(timeout: float = 10.0) -> None:
    """Wait for in-flight sweeps and forget every snapshot (shutdown, tests)."""
    with _LOCK:
        threads = list(_THREADS)
    for thread in threads:
        thread.join(timeout=timeout)
    with _LOCK:
        _THREADS.clear()
        _CACHE.clear()
        _REFRESHING.clear()
