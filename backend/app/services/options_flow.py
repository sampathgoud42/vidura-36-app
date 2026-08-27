"""Unusual options activity across a large-cap universe.

The desk question this answers: which single contracts are trading hardest
right now, and is that trade OPENING positions or closing them?

    volume        today's contracts traded (live)
    open_interest positions outstanding as of the PRIOR close
    oi_chg        today's OI minus the last session's, once a baseline exists
    vol_oi        volume / open interest — the live proxy for the same thing:
                  above 1.0 the day's trade is bigger than everything already
                  open, which is what "new positioning" looks like before the
                  next morning's OI is published

Streaming cannot serve this: Tradier's market socket carries quotes, trades
and summaries — no open interest — so the numbers come from the options
chain over REST and are refreshed on a timer in the background. A request
never waits for the venue: it gets the last good snapshot and a refresh is
kicked off if that snapshot is stale (stale-while-revalidate).

Cost is the reason for all the caching: one chain call per symbol per
expiration, ~0.9s each, so a 50-name sweep is ~100 calls. Expirations are
cached for the CST day (they do not move intraday) and the sweep runs in a
small thread pool.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings

logger = logging.getLogger(__name__)

CST = ZoneInfo("America/Chicago")
_OI_KIND = "opt_oi"

# user_id -> {"at": monotonic, "day": YYYY-MM-DD, "rows": [...], "meta": {...}}
_CACHE: dict[str, dict] = {}
_REFRESHING: set[str] = set()
_LOCK = threading.Lock()
# symbol -> (day, [expirations]); expirations do not change intraday
_EXP_CACHE: dict[str, tuple[str, list[str]]] = {}


def _today() -> str:
    return f"{datetime.now(CST):%Y-%m-%d}"


def universe() -> list[str]:
    s = get_settings()
    return [t.strip().upper() for t in s.tradier_flow_universe.split(",") if t.strip()]


def _oi_baseline(day: str) -> tuple[str | None, dict]:
    """(date, {occ: oi}) of the most recent snapshot BEFORE ``day``."""
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.super_research import DailySnapshot

    db = SessionLocal()
    try:
        row = db.scalar(
            select(DailySnapshot)
            .where(DailySnapshot.kind == _OI_KIND, DailySnapshot.snapshot_date < day)
            .order_by(DailySnapshot.snapshot_date.desc())
            .limit(1)
        )
        return (row.snapshot_date, dict(row.payload or {})) if row else (None, {})
    finally:
        db.close()


def _store_oi(day: str, oi: dict) -> None:
    """Today's OI per contract, one row per day (upserted)."""
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.super_research import DailySnapshot

    db = SessionLocal()
    try:
        row = db.scalar(
            select(DailySnapshot).where(DailySnapshot.kind == _OI_KIND,
                                        DailySnapshot.snapshot_date == day)
        )
        if row is None:
            db.add(DailySnapshot(kind=_OI_KIND, snapshot_date=day, payload=oi,
                                 source_file="tradier:chains"))
        else:
            row.payload = oi
        db.commit()
    except Exception as exc:                      # noqa: BLE001 - never fatal
        logger.warning("options-flow: could not store OI baseline: %s", exc)
        db.rollback()
    finally:
        db.close()


def _expirations(client, symbol: str, day: str, keep: int) -> list[str]:
    hit = _EXP_CACHE.get(symbol)
    if hit and hit[0] == day:
        return hit[1][:keep]
    exps = client.expirations(symbol) or []
    _EXP_CACHE[symbol] = (day, exps)
    return exps[:keep]


def _price_of(o: dict) -> float | None:
    """What the contract is worth: the last print, else the offer, else the bid."""
    for key in ("last", "ask", "bid"):
        try:
            v = float(o.get(key))
        except (TypeError, ValueError):
            continue
        if v > 0:
            return v
    return None


def _scan_symbol(client, symbol: str, day: str, keep_exps: int,
                 min_volume: int, min_price: float = 0.0) -> list[dict]:
    """Contracts on this symbol worth ranking, from its nearest expirations."""
    out: list[dict] = []
    try:
        for expiration in _expirations(client, symbol, day, keep_exps):
            for o in client.chain(symbol, expiration) or []:
                vol = int(o.get("volume") or 0)
                if vol < min_volume:
                    continue
                # Priced out before ranking, not after: a penny contract that
                # traded 200k would otherwise take a slot from real flow.
                px = _price_of(o)
                if min_price > 0 and (px is None or px < min_price):
                    continue
                oi = int(o.get("open_interest") or 0)
                out.append({
                    "symbol": symbol,
                    "occ_symbol": o.get("symbol"),
                    "type": (o.get("option_type") or "").lower(),
                    "strike": o.get("strike"),
                    "expiration": expiration,
                    "volume": vol,
                    "open_interest": oi,
                    "last": o.get("last"),
                    # the day's range on the CONTRACT, not the underlying:
                    # where the premium has actually traded tells you whether
                    # you would be buying this flow near its low or its high
                    "low": o.get("low"),
                    "high": o.get("high"),
                    "bid": o.get("bid"),
                    "ask": o.get("ask"),
                    "change_pct": o.get("change_percentage"),
                })
    except Exception as exc:                      # noqa: BLE001 - one bad name
        logger.info("options-flow: %s skipped (%s)", symbol, exc)
    return out


def _refresh(user, live: bool) -> dict:
    from app.services import tradier_bot

    s = get_settings()
    day = _today()
    syms = universe()
    client = tradier_bot.client_for(user, live=live)
    started = time.time()
    rows: list[dict] = []
    try:
        with ThreadPoolExecutor(max_workers=max(1, s.tradier_flow_workers)) as pool:
            for got in pool.map(
                lambda sym: _scan_symbol(client, sym, day,
                                         s.tradier_flow_expirations,
                                         s.tradier_flow_min_volume,
                                         s.tradier_flow_min_price),
                syms,
            ):
                rows.extend(got)
    finally:
        client.close()

    # OI day-over-day, against the newest snapshot from an earlier session
    base_day, base = _oi_baseline(day)
    for r in rows:
        prev = base.get(r["occ_symbol"])
        r["oi_chg"] = (r["open_interest"] - int(prev)) if prev is not None else None
        r["vol_oi"] = round(r["volume"] / r["open_interest"], 2) if r["open_interest"] else None

    rows.sort(key=lambda r: (r["volume"], r["oi_chg"] or 0), reverse=True)
    cap = s.tradier_flow_max_per_ticker
    seen: dict[str, int] = {}
    capped: list[dict] = []
    for r in rows:
        sym = r.get("symbol", "")
        if seen.get(sym, 0) >= cap:
            continue
        seen[sym] = seen.get(sym, 0) + 1
        capped.append(r)
        if len(capped) >= s.tradier_flow_top:
            break
    top = capped

    # Baseline for tomorrow: every contract seen, not just the top slice.
    _store_oi(day, {r["occ_symbol"]: r["open_interest"] for r in rows
                    if r["occ_symbol"]})

    return {
        "rows": top,
        "meta": {
            "day": day,
            "symbols": len(syms),
            "contracts_seen": len(rows),
            "min_price": s.tradier_flow_min_price,
            "oi_baseline_date": base_day,
            "took_s": round(time.time() - started, 1),
            "venue": "live" if live else "sandbox",
            "at": f"{datetime.now(CST):%H:%M:%S}",
        },
    }


def _refresh_async(user, live: bool) -> None:
    uid = user.user_id
    with _LOCK:
        if uid in _REFRESHING:
            return
        _REFRESHING.add(uid)

    def run():
        try:
            got = _refresh(user, live)
            _CACHE[uid] = {"at": time.monotonic(), "day": got["meta"]["day"], **got}
        except Exception as exc:                  # noqa: BLE001
            logger.warning("options-flow refresh failed: %s", exc)
            cached = _CACHE.get(uid)
            if cached is not None:
                cached["error"] = str(exc)[:200]
        finally:
            with _LOCK:
                _REFRESHING.discard(uid)

    threading.Thread(target=run, daemon=True,
                     name=f"optflow-{uid[:8]}").start()


def snapshot(user, *, live: bool = False, force: bool = False) -> dict:
    """Last good flow snapshot; refreshes in the background when stale.

    Returns immediately either way — the first call of a session comes back
    empty with ``refreshing: true`` rather than blocking for the sweep.
    """
    s = get_settings()
    uid = user.user_id
    cached = _CACHE.get(uid)
    fresh = (cached is not None
             and cached.get("day") == _today()
             and time.monotonic() - cached["at"] < s.tradier_flow_ttl_s)
    if force or not fresh:
        _refresh_async(user, live)
    with _LOCK:
        refreshing = uid in _REFRESHING
    if cached is None:
        return {"rows": [], "meta": {"day": _today()}, "refreshing": refreshing,
                "age_s": None}
    return {
        "rows": cached["rows"],
        "meta": cached["meta"],
        "error": cached.get("error"),
        "refreshing": refreshing,
        "age_s": int(time.monotonic() - cached["at"]),
    }
