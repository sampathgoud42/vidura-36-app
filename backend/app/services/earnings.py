"""Upcoming earnings for the large-cap universe, for the Super-Signals desk.

Why it exists: the desk already warns about macro events ("FOMC rate decision
13:00 CST"). An earnings print is the single-name equivalent — it gaps the
underlying and makes any intraday signal on that ticker untradeable through
the event. This surfaces the next ~24-48h so the desk can see them coming.

Source is yfinance (keyless, no budget to protect, unlike flashAlpha GEX).
The session (pre/post) is derived from the Eastern-time hour of the scheduled
timestamp, which is how the vendor encodes it: 16:00 ET = after the close,
06:00-08:00 ET = before the open.

Results are cached in daily_snapshots(kind='earnings') and only refetched when
stale, so the desk polling this endpoint never triggers 100 HTTP calls.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.super_research import DailySnapshot

log = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
CT = ZoneInfo("America/Chicago")

# Large-cap US universe ("top 100" by market cap, hand-maintained). This is an
# EARNINGS watchlist only — deliberately not the removed Top-100 signal
# feature, and nothing else reads it.
EARNINGS_UNIVERSE: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "TSLA", "BRK-B", "LLY",
    "JPM", "V", "XOM", "UNH", "MA", "COST", "HD", "PG", "WMT", "JNJ",
    "NFLX", "ABBV", "CRM", "BAC", "ORCL", "CVX", "MRK", "KO", "AMD", "PEP",
    "TMO", "LIN", "ADBE", "CSCO", "ACN", "MCD", "ABT", "WFC", "PM", "IBM",
    "GE", "TXN", "NOW", "QCOM", "DHR", "VZ", "INTU", "DIS", "CAT", "AMGN",
    "PFE", "RTX", "SPGI", "UBER", "GS", "AXP", "NEE", "UNP", "T", "LOW",
    "PGR", "HON", "ETN", "COP", "BKNG", "MS", "BLK", "SYK", "TJX", "C",
    "VRTX", "LMT", "ADP", "MDT", "BSX", "PLD", "SCHW", "MU", "CB", "GILD",
    "ADI", "MMC", "DE", "REGN", "SBUX", "CI", "AMT", "SO", "ELV", "BX",
    "PANW", "KLAC", "LRCX", "INTC", "ISRG", "PYPL", "MDLZ", "ZTS", "DUK", "SHW",
)

_MAX_WORKERS = 8
_STALE_HOURS = 12.0


def _session_of(ts: datetime) -> str:
    """pre / post / during, from the Eastern-time clock of the print."""
    et = ts.astimezone(ET)
    minutes = et.hour * 60 + et.minute
    if minutes < 9 * 60 + 30:
        return "pre"
    if minutes >= 16 * 60:
        return "post"
    return "during"


def _one(ticker: str, start: datetime, end: datetime) -> list[dict]:
    """Scheduled prints for one ticker inside [start, end]. Never raises —
    a single delisted/renamed symbol must not sink the whole sweep."""
    try:
        import yfinance as yf

        df = yf.Ticker(ticker).get_earnings_dates(limit=8)
    except Exception as exc:  # network, parse, unknown symbol
        log.debug("earnings fetch failed for %s: %s", ticker, exc)
        return []
    if df is None or len(df) == 0:
        return []

    out: list[dict] = []
    for idx, row in df.iterrows():
        ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=ET)
        if not (start <= ts <= end):
            continue
        est = row.get("EPS Estimate") if hasattr(row, "get") else None
        try:
            est = None if est is None or est != est else round(float(est), 2)  # NaN != NaN
        except (TypeError, ValueError):
            est = None
        out.append(
            {
                "ticker": ticker,
                "when_utc": ts.astimezone(timezone.utc).isoformat(),
                "when_ct": ts.astimezone(CT).strftime("%Y-%m-%d %H:%M"),
                "date": ts.astimezone(ET).strftime("%Y-%m-%d"),
                "session": _session_of(ts),
                "eps_estimate": est,
            }
        )
    return out


def fetch_upcoming(hours: int = 48, universe: tuple[str, ...] = EARNINGS_UNIVERSE) -> dict:
    """Sweep the universe for prints in the next `hours`. Network-bound;
    callers should cache via get_earnings()."""
    now = datetime.now(timezone.utc)
    end = now + timedelta(hours=hours)

    events: list[dict] = []
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        for chunk in pool.map(lambda t: _one(t, now, end), universe):
            events.extend(chunk)

    events.sort(key=lambda e: (e["when_utc"], e["ticker"]))

    # group by ET date -> session, which is how a desk reads it:
    #   07/29 Post: MSFT, AAPL   ·   07/30 Pre: NVDA
    days: dict[str, dict[str, list[str]]] = {}
    for e in events:
        days.setdefault(e["date"], {}).setdefault(e["session"], []).append(e["ticker"])

    return {
        "generated_at": now.isoformat(),
        "window_hours": hours,
        "universe_size": len(universe),
        "count": len(events),
        "events": events,
        "days": [
            {"date": d, "sessions": days[d]}
            for d in sorted(days)
        ],
        "note": summarize(days),
    }


def summarize(days: dict[str, dict[str, list[str]]], max_per_session: int = 6) -> str:
    """One-line desk summary: '07/29 Post: MSFT, AAPL · 07/30 Pre: NVDA'."""
    labels = {"pre": "Pre", "post": "Post", "during": "Intraday"}
    parts: list[str] = []
    for d in sorted(days):
        md = f"{d[5:7]}/{d[8:10]}"
        for sess in ("pre", "during", "post"):
            tks = days[d].get(sess)
            if not tks:
                continue
            shown = ", ".join(tks[:max_per_session])
            if len(tks) > max_per_session:
                shown += f" +{len(tks) - max_per_session}"
            parts.append(f"{md} {labels[sess]}: {shown}")
    return " · ".join(parts)


def _payload_age_h(payload: dict) -> float:
    try:
        gen = datetime.fromisoformat(payload["generated_at"])
    except (KeyError, TypeError, ValueError):
        return 1e9
    if gen.tzinfo is None:
        gen = gen.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - gen).total_seconds() / 3600


def get_earnings(
    db: Session, *, hours: int = 24, force: bool = False, persist: bool = True
) -> dict:
    """Cached read. Refetches only when the stored sweep is missing, stale,
    or covers a shorter window than asked for."""
    row = db.scalar(
        select(DailySnapshot)
        .where(DailySnapshot.kind == "earnings")
        .order_by(DailySnapshot.fetched_at.desc())
        .limit(1)
    )
    cached = row.payload if row else None
    fresh_enough = (
        cached
        and not force
        and _payload_age_h(cached) < _STALE_HOURS
        and cached.get("window_hours", 0) >= hours
    )
    if fresh_enough:
        return _window(cached, hours, cached_flag=True)

    # always sweep the wider window so a 24h ask can be served from a 48h cache
    payload = fetch_upcoming(max(hours, 48))
    if persist:
        _store(db, payload)
    return _window(payload, hours, cached_flag=False)


def _store(db: Session, payload: dict) -> None:
    date = datetime.now(ET).strftime("%Y-%m-%d")
    row = db.scalar(
        select(DailySnapshot).where(
            DailySnapshot.kind == "earnings", DailySnapshot.snapshot_date == date
        )
    )
    if row is None:
        db.add(
            DailySnapshot(
                kind="earnings", snapshot_date=date, payload=payload, source_file="yfinance"
            )
        )
    else:
        row.payload = payload
        row.fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()


def _window(payload: dict, hours: int, *, cached_flag: bool) -> dict:
    """Narrow a stored (wider) sweep down to the requested horizon."""
    cutoff = datetime.now(timezone.utc) + timedelta(hours=hours)
    now = datetime.now(timezone.utc)
    events = []
    for e in payload.get("events", []):
        try:
            when = datetime.fromisoformat(e["when_utc"])
        except (KeyError, TypeError, ValueError):
            continue
        if now - timedelta(hours=1) <= when <= cutoff:
            events.append(e)

    days: dict[str, dict[str, list[str]]] = {}
    for e in events:
        days.setdefault(e["date"], {}).setdefault(e["session"], []).append(e["ticker"])

    return {
        "generated_at": payload.get("generated_at"),
        "cached": cached_flag,
        "age_hours": round(_payload_age_h(payload), 2),
        "window_hours": hours,
        "universe_size": payload.get("universe_size"),
        "count": len(events),
        "events": events,
        "days": [{"date": d, "sessions": days[d]} for d in sorted(days)],
        "note": summarize(days),
    }
