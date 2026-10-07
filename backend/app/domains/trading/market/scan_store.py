"""The stored scans (market/models.py): read one combination, or replace it.

Replacing is TRUNCATE AND LOAD, one combination at a time: the combination's
rows and its run row are deleted and the new ones inserted inside one
transaction, so a reader on another connection sees the whole old scan or the
whole new one. Every function opens its own short session -- the writers run
on sweep threads that have no request around them.

Times go out as epoch seconds (``at``, what the sheets already count "how
long ago" from) and as ISO UTC (``scanned_at``), never as a zone-less local
string: the desks show them in Central time, and a string without a zone is
one they would have to guess about.
"""

from __future__ import annotations

import math
from datetime import timedelta, timezone

from sqlalchemy import delete, select

from app.domains.trading.market.models import BestBetsRow, BreakoutHistory, BreakoutRow, ScanRun
from app.domains.trading.risk import clock
from app.platform.db.base import utcnow
from app.platform.db.session import session_scope

BEST_BETS = "best_bets"
BREAKOUT = "breakout"
HISTORY_DAYS = 30           # how long a breakout stays listed after it last passed


def breakout_combo(market: str, timeframe: str) -> str:
    return f"{market}:{timeframe}"


def _plain(value):
    """What a JSON column can hold, and what the API may send back.

    The screens hand back numpy scalars here and there (a numpy bool is not a
    bool to ``json``), and a non-finite float is not JSON at all -- the answer
    would fail to serialise long after the row was stored. Both are settled
    once, on the way in."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value) if math.isfinite(value) else None
    item = getattr(value, "item", None)             # a numpy scalar
    if callable(item):
        return _plain(item())
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _epoch(moment) -> float:
    return moment.replace(tzinfo=timezone.utc).timestamp()


def _stamp(run: ScanRun) -> dict:
    return {"at": round(_epoch(run.scanned_at), 3),
            "scanned_at": run.scanned_at.isoformat(timespec="seconds") + "Z",
            "trade_date": run.trade_date, "trigger": run.trigger,
            "took_s": run.took_s}


def _new_run(db, kind: str, combo: str, *, meta: dict, row_count: int,
             trigger: str, now) -> None:
    db.execute(delete(ScanRun).where(ScanRun.kind == kind, ScanRun.combo == combo))
    db.add(ScanRun(kind=kind, combo=combo, trade_date=clock.today().isoformat(),
                   scanned_at=now, took_s=meta.get("took_s"), row_count=row_count,
                   trigger=trigger, meta=_plain(meta)))


# ---- Best Bets ---------------------------------------------------------------

def replace_best_bets(venue: str, rows: list[dict], meta: dict, *, trigger: str) -> float:
    """Truncate and load one venue's sheet. Returns when it was stored."""
    now = utcnow()
    with session_scope() as db:
        db.execute(delete(BestBetsRow).where(BestBetsRow.venue == venue))
        _new_run(db, BEST_BETS, venue, meta=meta, row_count=len(rows),
                 trigger=trigger, now=now)
        db.add_all([
            BestBetsRow(venue=venue, rank=rank, symbol=str(row.get("symbol") or "")[:16],
                        setup=row.get("setup"), available=bool(row.get("available")),
                        data=_plain(row), scanned_at=now)
            for rank, row in enumerate(rows)])
    return _epoch(now)


def best_bets(venue: str) -> dict | None:
    """The venue's stored sheet in its order, or None when never scanned."""
    with session_scope() as db:
        run = db.scalar(select(ScanRun).where(ScanRun.kind == BEST_BETS,
                                              ScanRun.combo == venue))
        if run is None:
            return None
        rows = db.scalars(select(BestBetsRow.data).where(BestBetsRow.venue == venue)
                          .order_by(BestBetsRow.rank)).all()
        return {"rows": list(rows), "meta": dict(run.meta or {}), **_stamp(run)}


# ---- BreakoutRadar -------------------------------------------------------------

def replace_breakout(market: str, timeframe: str, *, rows: list[dict],
                     near_misses: list[dict], meta: dict, trigger: str) -> float:
    """Truncate and load one market and timeframe. Returns when it was stored."""
    now = utcnow()
    with session_scope() as db:
        db.execute(delete(BreakoutRow).where(BreakoutRow.market == market,
                                             BreakoutRow.timeframe == timeframe))
        _new_run(db, BREAKOUT, breakout_combo(market, timeframe), meta=meta,
                 row_count=len(rows), trigger=trigger, now=now)
        db.add_all([
            BreakoutRow(market=market, timeframe=timeframe, section=section, rank=rank,
                        ticker=str(row.get("ticker") or "")[:24], data=_plain(row),
                        scanned_at=now)
            for section, part in (("pass", rows), ("near", near_misses))
            for rank, row in enumerate(part)])
        _remember(db, market, timeframe, rows, now)
    return _epoch(now)


def _remember(db, market: str, timeframe: str, rows: list[dict], now) -> None:
    """Upsert the history with a sweep's breakouts, and drop the expired.

    A ticker's breakout candle decides whether it "popped up again": the same
    breakout still passing on the next rescan only refreshes its row; a new
    breakout candle counts a hit and brings it back to the top (popped_at)."""
    known = {h.ticker: h for h in db.scalars(select(BreakoutHistory).where(
        BreakoutHistory.market == market, BreakoutHistory.timeframe == timeframe)).all()}
    for row in rows:
        ticker = str(row.get("ticker") or "")[:24]
        if not ticker:
            continue
        at = row.get("breakout_candle_timestamp")
        at = None if at is None else str(_plain(at))[:40]
        h = known.get(ticker)
        if h is None:
            h = BreakoutHistory(market=market, timeframe=timeframe, ticker=ticker,
                                first_seen=now, popped_at=now, last_seen=now,
                                breakout_at=at, hits=1, data=_plain(row))
            db.add(h)
            known[ticker] = h
            continue
        if at != h.breakout_at:
            h.hits = (h.hits or 1) + 1
            h.popped_at = now
            h.breakout_at = at
        h.last_seen = now
        h.data = _plain(row)
    db.execute(delete(BreakoutHistory).where(
        BreakoutHistory.market == market, BreakoutHistory.timeframe == timeframe,
        BreakoutHistory.last_seen < now - timedelta(days=HISTORY_DAYS)))


def breakout_history(market: str, timeframe: str) -> list[dict]:
    """Every breakout of the last HISTORY_DAYS, the latest to pop up first:
    each its latest row, with ``popped_at``, ``first_seen`` and ``last_seen``
    (epoch seconds), ``hits`` and ``again`` (it broke out more than once)."""
    cutoff = utcnow() - timedelta(days=HISTORY_DAYS)
    with session_scope() as db:
        found = db.scalars(select(BreakoutHistory).where(
            BreakoutHistory.market == market, BreakoutHistory.timeframe == timeframe,
            BreakoutHistory.last_seen >= cutoff)
            .order_by(BreakoutHistory.popped_at.desc())).all()
        return [{**dict(h.data or {}), "ticker": h.ticker,
                 "popped_at": round(_epoch(h.popped_at), 3),
                 "first_seen": round(_epoch(h.first_seen), 3),
                 "last_seen": round(_epoch(h.last_seen), 3),
                 "hits": h.hits, "again": (h.hits or 1) > 1} for h in found]


def breakout(market: str, timeframe: str) -> dict | None:
    """One stored scan: its breakouts, its near misses, and its run."""
    with session_scope() as db:
        run = db.scalar(select(ScanRun).where(
            ScanRun.kind == BREAKOUT, ScanRun.combo == breakout_combo(market, timeframe)))
        if run is None:
            return None
        found = db.execute(select(BreakoutRow.section, BreakoutRow.data).where(
            BreakoutRow.market == market, BreakoutRow.timeframe == timeframe)
            .order_by(BreakoutRow.section, BreakoutRow.rank)).all()
        return {"rows": [data for section, data in found if section == "pass"],
                "near_misses": [data for section, data in found if section == "near"],
                "meta": dict(run.meta or {}), **_stamp(run)}


# ---- the day ------------------------------------------------------------------

def run_meta(kind: str, combo: str) -> dict | None:
    """Only the run's meta -- what a scan was judged with -- without its rows."""
    with session_scope() as db:
        meta = db.scalar(select(ScanRun.meta).where(ScanRun.kind == kind,
                                                    ScanRun.combo == combo))
        return dict(meta) if meta is not None else None


def scanned_today(kind: str) -> set[str]:
    """The combinations of ``kind`` already scanned on the desk's today."""
    with session_scope() as db:
        return set(db.scalars(select(ScanRun.combo).where(
            ScanRun.kind == kind, ScanRun.trade_date == clock.today().isoformat())).all())
