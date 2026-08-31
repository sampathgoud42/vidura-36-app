"""Options flow: the day's most-traded contracts across a large-cap universe.

The board answers one question -- where is the option volume today, and is it
opening or closing? Volume alone cannot tell you: 200k contracts traded
against 400k already open is position management, and 200k against 2k open is
somebody putting a trade on. So every row carries open interest, its change
since the previous session, and the ratio of the two.

Cost is why almost everything here is cached. One chain call per symbol per
expiration at roughly a second each makes a fifty-name sweep about a hundred
requests, which is far too slow to sit in front of a render. So the endpoint
returns the last good snapshot IMMEDIATELY and refreshes behind it. A board
that is thirty seconds stale and instant beats a board that is exact and
arrives after the operator has looked away.

This module owns the sweep for the rebuild. The old app had its own copy
keyed on a filesystem credential folder; that one goes with the rest of the
legacy tree, and this is the single implementation the desk reads.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

from app.domains.trading.execution import venue as venue_mod
from app.services.tradier_client import TradierError

logger = logging.getLogger(__name__)

CST = ZoneInfo("America/Chicago")

# The open-interest baseline is stored as a research snapshot under this kind,
# one row per trading day, so "OI change" survives a restart. Without it the
# board could only ever show today's absolute OI, and the interesting part of
# the number -- that it MOVED -- would be unavailable until someone kept a
# spreadsheet.
_OI_KIND = "opt_oi"

# tenant -> {"at": monotonic, "day": ..., "rows": [...], "meta": {...}}
_CACHE: dict[str, dict] = {}
_REFRESHING: set[str] = set()
_LOCK = threading.Lock()
# symbol -> (day, [expirations]). Expirations do not move intraday.
_EXP_CACHE: dict[str, tuple[str, list[str]]] = {}
# Live sweep threads. Tracked, not fire-and-forget: a background worker that
# holds a database connection is process-global state, and anything that tears
# the process state down -- a test, a shutdown -- has to be able to wait for it
# rather than pull the database out from under it.
_THREADS: set[threading.Thread] = set()

# How stale a snapshot may be before a read kicks off a background sweep.
_TTL_S = 120


def _today() -> str:
    return f"{datetime.now(CST):%Y-%m-%d}"


def universe() -> list[str]:
    from app.core.config import get_settings

    raw = get_settings().tradier_flow_universe
    return [t.strip().upper() for t in raw.split(",") if t.strip()]


# ---- the open-interest baseline -------------------------------------------

def _oi_baseline(day: str) -> tuple[str | None, dict]:
    """(date, {occ: oi}) from the most recent snapshot BEFORE ``day``.

    Strictly before: comparing today against a baseline written earlier today
    would report the intraday drift of a single session's bookkeeping as if it
    were new positioning, which is the opposite of what the column means.
    """
    from sqlalchemy import select

    from app.domains.research.models import DailySnapshot
    from app.platform.db.session import session_scope

    try:
        with session_scope() as db:
            row = db.scalars(
                select(DailySnapshot)
                .where(DailySnapshot.kind == _OI_KIND,
                       DailySnapshot.snapshot_date < day)
                .order_by(DailySnapshot.snapshot_date.desc())
                .limit(1)).first()
            if row is None:
                return None, {}
            return row.snapshot_date, dict(row.payload or {})
    except Exception as exc:                            # noqa: BLE001
        logger.info("options-flow: no OI baseline (%s: %s)",
                    type(exc).__name__, exc)
        return None, {}


def _store_oi(day: str, oi: dict) -> None:
    """Today's baseline for tomorrow. Upserted, so a second sweep on the same
    day replaces the row rather than racing another one."""
    from sqlalchemy import select

    from app.domains.research.models import DailySnapshot
    from app.platform.db.session import session_scope, write_lock

    if not oi:
        return
    try:
        with write_lock(), session_scope() as db:
            row = db.scalars(
                select(DailySnapshot)
                .where(DailySnapshot.kind == _OI_KIND,
                       DailySnapshot.snapshot_date == day)).first()
            if row is None:
                db.add(DailySnapshot(kind=_OI_KIND, snapshot_date=day,
                                     payload=oi, source_file="options-flow"))
            else:
                row.payload = oi
    except Exception as exc:                            # noqa: BLE001
        # Losing a baseline costs tomorrow's OI-change column, not the board.
        logger.info("options-flow: could not store OI baseline (%s: %s)",
                    type(exc).__name__, exc)


# ---- the sweep ------------------------------------------------------------

def _expirations(symbol: str, day: str, keep: int, *, cred, sandbox: bool):
    hit = _EXP_CACHE.get(symbol)
    if hit and hit[0] == day:
        return hit[1][:keep]
    exps = venue_mod.expirations(symbol, cred=cred, sandbox=sandbox) or []
    _EXP_CACHE[symbol] = (day, exps)
    return exps[:keep]


def _price_of(option: dict) -> float | None:
    """What the contract is worth: the last print, else the offer, else the bid."""
    for key in ("last", "ask", "bid"):
        try:
            value = float(option.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return None


def _scan_symbol(symbol: str, day: str, *, cred, sandbox: bool, keep_exps: int,
                 min_volume: int, min_price: float) -> list[dict]:
    """Contracts on one symbol worth ranking, from its nearest expirations."""
    out: list[dict] = []
    try:
        for expiration in _expirations(symbol, day, keep_exps, cred=cred,
                                       sandbox=sandbox):
            for option in venue_mod.option_chain(symbol, expiration, cred=cred,
                                                 sandbox=sandbox) or []:
                volume = int(option.get("volume") or 0)
                if volume < min_volume:
                    continue
                # Priced out BEFORE ranking rather than after: a penny contract
                # that traded 200k would otherwise take a slot from real flow.
                price = _price_of(option)
                if min_price > 0 and (price is None or price < min_price):
                    continue
                out.append({
                    "symbol": symbol,
                    "occ_symbol": option.get("symbol"),
                    "type": (option.get("option_type") or "").lower(),
                    "strike": option.get("strike"),
                    "expiration": expiration,
                    "volume": volume,
                    "open_interest": int(option.get("open_interest") or 0),
                    "last": option.get("last"),
                    # The day's range on the CONTRACT, not the underlying:
                    # where the premium has actually traded tells you whether
                    # you would be buying this flow near its low or its high.
                    "low": option.get("low"),
                    "high": option.get("high"),
                    "bid": option.get("bid"),
                    "ask": option.get("ask"),
                    "change_pct": option.get("change_percentage"),
                })
    except (TradierError, OSError, ValueError, TypeError) as exc:
        # One unknown or halted name must not empty the board. Narrow on
        # purpose: a broad except here swallowed an AttributeError from a
        # mistyped seam call on all fifty symbols at once and reported it as
        # "no flow today", which is a plausible-looking answer and therefore
        # the worst possible one.
        logger.info("options-flow: %s skipped (%s: %s)", symbol,
                    type(exc).__name__, exc)
    return out


def _sweep(cred, *, sandbox: bool) -> dict:
    from app.core.config import get_settings

    settings = get_settings()
    day = _today()
    symbols = universe()
    started = time.time()

    rows: list[dict] = []
    workers = max(1, min(settings.tradier_flow_workers, len(symbols) or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for got in pool.map(
                lambda sym: _scan_symbol(
                    sym, day, cred=cred, sandbox=sandbox,
                    keep_exps=settings.tradier_flow_expirations,
                    min_volume=settings.tradier_flow_min_volume,
                    min_price=settings.tradier_flow_min_price),
                symbols):
            rows.extend(got)

    base_day, base = _oi_baseline(day)
    for row in rows:
        previous = base.get(row["occ_symbol"])
        row["oi_chg"] = (row["open_interest"] - int(previous)
                         if previous is not None else None)
        row["vol_oi"] = (round(row["volume"] / row["open_interest"], 2)
                         if row["open_interest"] else None)

    rows.sort(key=lambda r: (r["volume"], r["oi_chg"] or 0), reverse=True)

    # Capped per ticker before the global cut, so one very active name cannot
    # fill the whole board and hide what everything else is doing.
    cap = settings.tradier_flow_max_per_ticker
    seen: dict[str, int] = {}
    top: list[dict] = []
    for row in rows:
        symbol = row.get("symbol", "")
        if seen.get(symbol, 0) >= cap:
            continue
        seen[symbol] = seen.get(symbol, 0) + 1
        top.append(row)
        if len(top) >= settings.tradier_flow_top:
            break

    # Tomorrow's baseline is EVERY contract seen, not just the top slice --
    # otherwise a contract that only enters the top tomorrow has no yesterday
    # to be compared against, and its oi_chg reads null exactly when it starts
    # to matter.
    _store_oi(day, {r["occ_symbol"]: r["open_interest"] for r in rows
                    if r["occ_symbol"]})

    return {
        "rows": top,
        "meta": {
            "day": day,
            "symbols": len(symbols),
            "contracts_seen": len(rows),
            "min_price": settings.tradier_flow_min_price,
            "oi_baseline_date": base_day,
            "took_s": round(time.time() - started, 1),
            "venue": "live" if not sandbox else "sandbox",
            "at": f"{datetime.now(CST):%H:%M:%S}",
        },
    }


def _sweep_async(tenant_id: str, cred, *, sandbox: bool) -> None:
    """One sweep at a time per operator.

    Without the guard, a desk polling every ten seconds would start a new
    hundred-request sweep on every tick while the first was still running.
    """
    with _LOCK:
        if tenant_id in _REFRESHING:
            return
        _REFRESHING.add(tenant_id)

    def run() -> None:
        try:
            got = _sweep(cred, sandbox=sandbox)
            with _LOCK:
                _CACHE[tenant_id] = {"at": time.monotonic(), **got}
        except Exception as exc:                        # noqa: BLE001
            logger.info("options-flow sweep failed: %s: %s",
                        type(exc).__name__, exc)
        finally:
            with _LOCK:
                _REFRESHING.discard(tenant_id)
                _THREADS.discard(threading.current_thread())

    thread = threading.Thread(target=run, name=f"flow-{tenant_id[:8]}",
                              daemon=True)
    with _LOCK:
        _THREADS.add(thread)
    thread.start()


def snapshot(tenant_id: str, cred, *, sandbox: bool = True,
             force: bool = False) -> dict:
    """The board: last good rows now, refreshed behind the response.

    ``force`` waits for a real sweep, because it means the operator pressed
    refresh and is entitled to the answer they asked for rather than the one
    already on screen.
    """
    if force:
        got = _sweep(cred, sandbox=sandbox)
        with _LOCK:
            _CACHE[tenant_id] = {"at": time.monotonic(), **got}
        return {"rows": got["rows"], "meta": {**got["meta"], "stale": False,
                                              "refreshing": False}}

    with _LOCK:
        hit = _CACHE.get(tenant_id)
        busy = tenant_id in _REFRESHING
    age = time.monotonic() - hit["at"] if hit else None
    stale = hit is None or age > _TTL_S

    if stale and not busy:
        _sweep_async(tenant_id, cred, sandbox=sandbox)
        busy = True

    if hit is None:
        # First call of the process. An empty board that says it is loading is
        # honest; an empty board that says nothing reads as "no flow today".
        return {"rows": [], "meta": {"day": _today(), "stale": True,
                                     "refreshing": busy, "contracts_seen": 0,
                                     "venue": "sandbox" if sandbox else "live",
                                     "note": "first sweep is running"}}
    return {"rows": hit["rows"],
            "meta": {**hit["meta"], "stale": stale, "refreshing": busy,
                     "age_s": round(age, 1)}}


def quiesce(timeout: float = 10.0) -> None:
    """Wait for in-flight sweeps to finish, and forget every cached board.

    Called on shutdown and between tests. A sweep thread holds a database
    connection for the moment it writes the OI baseline; deleting the database
    file while that is open fails on Windows and corrupts on nothing at all --
    which is a confusing way to learn that a daemon thread outlived what it
    was reading.
    """
    with _LOCK:
        threads = list(_THREADS)
    for thread in threads:
        thread.join(timeout=timeout)
    with _LOCK:
        _THREADS.clear()
        _CACHE.clear()
        _REFRESHING.clear()
        _EXP_CACHE.clear()
