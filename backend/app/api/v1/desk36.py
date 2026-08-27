"""36 Trade Desk — the snapshot board's own endpoints.

Only one thing here is new: DMI readings for an ARBITRARY symbol list.

The HOT scan already computes Wilder +DI/-DI/ADX, but it sweeps a fixed
top-100 universe and returns only the names that clear its gates. This board
shows whatever tickers the operator typed — including SPY, QQQ, SPX and VIX,
none of which are in that universe — and it wants the reading whether or not
it is "hot". So this reuses hot_scan's indicator code verbatim and skips the
universe and the gates.

Prices are NOT served here. The board reads them from the existing
/tradier/quotes, which is fast and already cached: quotes move every second,
a DMI reading only changes when a 5-minute bar closes, and pinning them to
one endpoint would either make the cheap call expensive or the expensive one
stale.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.cloud import require_local_runtime
from app.core.config import get_settings
from app.core.database import get_db
from app.models import User
from app.services import hot_scan, tradier_bot

router = APIRouter(prefix="/desk36", tags=["desk36"])
logger = logging.getLogger(__name__)

# One timesales call per symbol, so this is cached hard. A reading cannot
# change until the next bar closes anyway.
_CACHE: dict[str, tuple[float, dict]] = {}
_MUTEX = threading.Lock()
_TTL_S = 300

MAX_SYMBOLS = 24


def _cached(key: str) -> dict | None:
    with _MUTEX:
        hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < _TTL_S:
        return hit[1]
    return None


def _store(key: str, value: dict) -> None:
    with _MUTEX:
        _CACHE[key] = (time.time(), value)


@router.get("/dmi", operation_id="getDesk36Dmi")
def dmi(
    user_id: str = Query(...),
    symbols: str = Query(..., description="comma-separated, max 24"),
    live: bool = Query(default=False),
    interval: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Latest +DI / -DI / ADX per symbol.

    Missing symbols are returned with nulls rather than omitted: the board
    lays out one row per ticker the operator asked for, and a silently
    dropped row would look like a rendering bug rather than "no reading yet".
    """
    # Reads bars from the venue through a real client, so this is
    # local-runtime only for the same reason every other Tradier call is.
    require_local_runtime("The DMI board")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")

    wanted = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    # De-duplicate but keep the operator's order — it is the row order.
    seen: set[str] = set()
    ordered = [s for s in wanted if not (s in seen or seen.add(s))]
    if not ordered:
        raise HTTPException(status_code=422, detail="no symbols given")
    if len(ordered) > MAX_SYMBOLS:
        raise HTTPException(
            status_code=422,
            detail=f"too many symbols ({len(ordered)}); the board caps at {MAX_SYMBOLS}",
        )

    s = get_settings()
    iv = interval or s.tradier_hot_interval
    days = hot_scan.days_for(iv)
    venue = "live" if live else "sandbox"

    rows: dict[str, dict | None] = {}
    todo = []
    for sym in ordered:
        hit = _cached(f"{venue}:{iv}:{sym}")
        if hit is not None:
            rows[sym] = hit
        else:
            todo.append(sym)

    fetched = 0
    if todo:
        try:
            client = tradier_bot.client_for(user, live=live)
        except Exception as exc:                      # noqa: BLE001
            raise HTTPException(status_code=424, detail=str(exc)) from exc
        try:
            def one(sym: str):
                try:
                    return sym, hot_scan._scan_symbol(client, sym, iv, days)
                except Exception as exc:              # noqa: BLE001
                    # An unknown ticker is an ordinary outcome here: the
                    # operator types these by hand.
                    logger.debug("desk36 dmi %s: %s", sym, exc)
                    return sym, None

            with ThreadPoolExecutor(max_workers=s.tradier_flow_workers) as pool:
                for sym, reading in pool.map(one, todo):
                    rows[sym] = reading
                    fetched += 1
                    if reading is not None:
                        _store(f"{venue}:{iv}:{sym}", reading)
        finally:
            client.close()

    out = []
    for sym in ordered:
        r = rows.get(sym)
        out.append({
            "symbol": sym,
            "plus_di": r["plus_di"] if r else None,
            "minus_di": r["minus_di"] if r else None,
            "adx": r["adx"] if r else None,
            "side": r["side"] if r else None,
            "bars": r["bars"] if r else 0,
        })

    return {
        "rows": out,
        "meta": {
            "interval": iv, "days": days, "venue": venue,
            "requested": len(ordered), "fetched": fetched,
            "from_cache": len(ordered) - fetched,
            "ttl_s": _TTL_S,
        },
    }
