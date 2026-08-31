"""SPY 0DTE dealer-gamma from getgamma.io's option chain.

The vendor endpoint returns the RAW chain — per-contract gamma, open interest
and strike — and its dashboard computes the headline numbers in the browser.
So we compute them here:

    net GEX    signed dollar gamma across the chain (calls +, puts -)
    flip       the strike where CUMULATIVE gamma crosses zero
    call wall  strike carrying the most call gamma
    put wall   strike carrying the most put gamma
    magnets    the heaviest-gamma strikes bracketing spot — price tends to
               pin between them into the close

TRANSPORT NOTE (2026-07-30): getgamma sits behind Vercel bot protection that
answers a server-side request with HTTP 429 + a "Security Checkpoint" page,
even carrying the exact browser headers and a valid session cookie. A real
browser on the site gets 200. Defeating that check is not something this
service does, so ``fetch_live`` reports the block plainly and the endpoint
also accepts a payload captured from the browser. The maths below is the same
either way.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

log = logging.getLogger(__name__)

VENDOR_URL = "https://www.getgamma.io/api/options"
CONTRACT_MULTIPLIER = 100          # one option = 100 shares

# Ordinary browser-shaped headers so a legitimate request is not rejected for
# looking malformed. Nothing here attempts to defeat the bot check.
_HEADERS = {
    "accept": "*/*",
    "accept-language": "en-US,en;q=0.9",
    "referer": "https://www.getgamma.io/dashboard",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36"
    ),
}


class GammaError(Exception):
    """Vendor unreachable, challenged, or the session expired."""


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out          # drop NaN


def fetch_live(ticker: str = "SPY", strikes: int = 50) -> dict:
    """Try the vendor directly. No credentials: the endpoint needs none.

    Verified 2026-07-30 — identical requests with a session JWT, with only the
    gamma_fp visitor cookie, and with no cookies at all all return HTTP 429 +
    a Vercel checkpoint page, while a real browser gets 200. The gate is client
    fingerprinting, not authentication, so there is nothing to authenticate
    with and nothing here tries to look like a browser past that check.
    """
    import requests

    try:
        resp = requests.get(
            VENDOR_URL,
            params={"ticker": ticker, "mode": "0dte", "strikes": strikes},
            headers=_HEADERS,
            timeout=30,
        )
    except Exception as exc:                     # network / DNS / TLS
        raise GammaError(f"getgamma unreachable: {exc}") from exc

    ctype = resp.headers.get("content-type") or ""
    if "json" not in ctype:
        raise GammaError(
            f"getgamma answered HTTP {resp.status_code} with a bot-check page, not JSON. "
            "Its edge blocks server-side calls regardless of cookies — push the "
            "chain from a browser tab on getgamma.io instead."
        )
    if resp.status_code >= 400:
        raise GammaError(f"getgamma HTTP {resp.status_code}")
    return resp.json()


def compute(payload: dict) -> dict:
    """Turn the raw chain into the desk line. Pure — no network, no clock."""
    if not isinstance(payload, dict):
        raise GammaError("payload is not an object")
    contracts = payload.get("contracts")
    if not isinstance(contracts, list) or not contracts:
        raise GammaError("payload carries no option contracts")
    spot = _num(payload.get("spotPrice"))
    if not spot:
        raise GammaError("payload carries no spot price")

    # dollar gamma per 1% move, the convention the desk line quotes
    unit = CONTRACT_MULTIPLIER * spot * spot * 0.01

    per_strike: dict[float, dict[str, float]] = {}
    oi_by_strike: dict[float, dict[str, float]] = {}
    for c in contracts:
        strike = _num(c.get("strike_price"))
        gamma = _num((c.get("greeks") or {}).get("gamma"))
        oi = _num(c.get("open_interest"))
        if strike is None or gamma is None or oi is None or oi <= 0:
            continue
        side = str(c.get("contract_type") or "").lower()
        if side not in ("call", "put"):
            continue
        per_strike.setdefault(strike, {"call": 0.0, "put": 0.0})[side] += gamma * oi * unit
        oi_by_strike.setdefault(strike, {"call": 0.0, "put": 0.0})[side] += oi

    if not per_strike:
        raise GammaError("no contracts carried gamma and open interest")

    strikes_sorted = sorted(per_strike)
    # dealers are short calls / long puts: call gamma positive, put gamma negative
    net_by_strike = {k: per_strike[k]["call"] - per_strike[k]["put"] for k in strikes_sorted}
    net_gex = sum(net_by_strike.values())
    call_gex = sum(per_strike[k]["call"] for k in strikes_sorted)
    put_gex = sum(per_strike[k]["put"] for k in strikes_sorted)

    # Walls are the OPEN-INTEREST peaks per side, not the gamma peaks — checked
    # against getgamma's own dashboard on 2026-07-30: it showed call wall 740 /
    # put wall 726, which are max call OI and max put OI. The gamma peak that
    # day sat at 738, so ranking by exposure gave the wrong put wall.
    call_wall = max(strikes_sorted, key=lambda k: oi_by_strike[k]["call"])
    put_wall = max(strikes_sorted, key=lambda k: oi_by_strike[k]["put"])

    # gamma flip: where the running total crosses zero, interpolated between
    # the bracketing strikes rather than snapped to one of them
    flip = None
    running = 0.0
    prev_k, prev_run = None, 0.0
    for k in strikes_sorted:
        running += net_by_strike[k]
        if prev_k is not None and (prev_run <= 0 < running or prev_run >= 0 > running):
            span = running - prev_run
            flip = k if span == 0 else prev_k + (k - prev_k) * (-prev_run / span)
            break
        prev_k, prev_run = k, running

    # Magnets are the SIGNED extremes, matching getgamma's "+GEX MAGNET" and
    # "-GEX MAGNET": the single most positive and most negative net-gamma
    # strikes. (Its dashboard showed +740 / -733 and these reproduce both.)
    # Not "heaviest absolute near spot" — that picked the wrong pair.
    magnet_hi = max(strikes_sorted, key=lambda k: net_by_strike[k])   # +GEX
    magnet_lo = min(strikes_sorted, key=lambda k: net_by_strike[k])   # -GEX
    magnets = sorted({magnet_hi, magnet_lo}, reverse=True)

    regime = "NEG" if net_gex < 0 else "POS"
    return {
        "ticker": payload.get("ticker") or "SPY",
        "mode": payload.get("mode") or "0dte",
        "spot": round(spot, 2),
        "regime": regime,
        "net_gex": round(net_gex, 2),
        "call_gex": round(call_gex, 2),
        "put_gex": round(put_gex, 2),
        "flip": round(flip, 2) if flip is not None else None,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "magnet_hi": magnet_hi,
        "magnet_lo": magnet_lo,
        "magnets": magnets,
        "market_status": payload.get("marketStatus"),
        "market_open": payload.get("marketOpen"),
        "vendor_ts": payload.get("timestamp"),
        "contracts": len(contracts),
        "strikes": len(strikes_sorted),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "note": summary_line(payload.get("ticker") or "SPY", regime, net_gex,
                             flip, call_wall, put_wall, magnet_hi, magnet_lo),
    }


def fmt_gex(value: float | None) -> str:
    """$-12.56B / $980.4M / $12.3K — the desk's shorthand."""
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    n = abs(float(value))
    for cut, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= cut:
            return f"{sign}${n / cut:.2f}{suffix}"
    return f"{sign}${n:.0f}"


def summary_line(ticker, regime, net_gex, flip, call_wall, put_wall, hi, lo) -> str:
    """SPY NEG · net -$12.56B · flip 743.09 · call wall 740 · put wall 730 · magnets 744-733"""
    parts = [
        f"{ticker} {regime}",
        f"net {fmt_gex(net_gex)}",
        f"flip {flip:.2f}" if flip is not None else "flip —",
        f"call wall {call_wall:g}" if call_wall is not None else "call wall —",
        f"put wall {put_wall:g}" if put_wall is not None else "put wall —",
    ]
    if hi is not None and lo is not None:
        parts.append(f"magnets {hi:g}-{lo:g}")
    return " · ".join(parts)


# --- hourly history ---------------------------------------------------------
#
# The desk wants the day at a glance: +500M >> +420M >> ... one reading per
# CST trading hour, 08:00 through 16:00. Snapshots arrive whenever a getgamma
# tab pushes, so this buckets them by hour rather than storing every push.

TRADING_HOURS = tuple(range(8, 17))          # 08:00 .. 16:00 CST inclusive
CST = ZoneInfo("America/Chicago")


def fmt_signed(value: float | None) -> str:
    """+500M / -420M / 0 — the hourly chain's shorthand.

    Always carries an explicit sign, because the whole point of the chain is
    reading the flip from positive to negative gamma at a glance.
    """
    if not value:
        return "0"
    sign = "-" if value < 0 else "+"
    n = abs(float(value))
    for cut, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= cut:
            return f"{sign}{n / cut:.0f}{suffix}" if n / cut >= 100 else f"{sign}{n / cut:.1f}{suffix}"
    return f"{sign}{n:.0f}"


PUSH_EVERY_S = 60           # the pusher's own cadence
STALE_AFTER_S = 3 * 60      # two missed ticks plus slack


def staleness(fetched_at) -> dict:
    """How old the snapshot is, and whether that is a problem right now.

    Age alone is not a fault — outside 08:00-15:15 CST nothing is pushing and
    an hours-old chain is correct. Inside the window it means the pusher died,
    and the desk has to SAY so: a card that only reads "updated 23m ago" looks
    identical whether the feed is idle or broken, which is how a stall goes
    unnoticed for half a session.
    """
    out = {"age_seconds": None, "stale": False, "window_open": _window_open()}
    if not fetched_at:
        return out
    try:
        ts = datetime.fromisoformat(str(fetched_at).replace("Z", "+00:00"))
    except ValueError:
        return out
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - ts).total_seconds()
    out["age_seconds"] = round(age, 1)
    out["stale"] = bool(out["window_open"] and age > STALE_AFTER_S)
    return out


def _window_open(now: datetime | None = None) -> bool:
    """08:00-15:15 CST on a weekday — when a push is actually expected."""
    now = now or datetime.now(CST)
    if now.weekday() > 4:
        return False
    minutes = now.hour * 60 + now.minute
    return 8 * 60 <= minutes <= 15 * 60 + 15


def record_hour(db, view: dict) -> None:
    """File ``view`` under its CST trading hour, replacing that hour's row.

    Last write wins inside the hour: a push at 09:58 summarises the 09:00 hour
    better than one at 09:02. Readings outside 08-16 CST are dropped rather
    than folded into an edge bucket, which would misreport the open or close.
    """
    from app.models import Gex0dteHour

    now = datetime.now(CST)
    if now.hour not in TRADING_HOURS:
        return
    date, hour = now.strftime("%Y-%m-%d"), now.hour

    row = (
        db.query(Gex0dteHour)
        .filter(Gex0dteHour.trade_date == date, Gex0dteHour.hour_cst == hour)
        .one_or_none()
    )
    if row is None:
        row = Gex0dteHour(trade_date=date, hour_cst=hour)
        db.add(row)
    row.ticker = view.get("ticker") or "SPY"
    row.net_gex = float(view.get("net_gex") or 0)
    row.call_gex = view.get("call_gex")
    row.put_gex = view.get("put_gex")
    row.spot = view.get("spot")
    row.regime = view.get("regime")
    row.flip = view.get("flip")
    row.call_wall = view.get("call_wall")
    row.put_wall = view.get("put_wall")
    row.fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()


def history(db, trade_date: str | None = None) -> dict:
    """One trading day as a chain of hourly net-gamma readings, 08:00-16:00 CST.

    Every hour is returned whether or not it was captured — an uncaptured hour
    reads 0 and is flagged ``captured: false``, so the UI can show the shape of
    the day honestly rather than pretending the gaps are data.
    """
    from app.models import Gex0dteHour

    date = trade_date or datetime.now(CST).strftime("%Y-%m-%d")
    rows = {
        r.hour_cst: r
        for r in db.query(Gex0dteHour).filter(Gex0dteHour.trade_date == date).all()
    }
    hours = []
    for h in TRADING_HOURS:
        r = rows.get(h)
        net = float(r.net_gex) if r is not None else 0.0
        hours.append(
            {
                "hour_cst": h,
                "label": f"{h if h <= 12 else h - 12}{'AM' if h < 12 else 'PM'} CST",
                "short": f"{h if h <= 12 else h - 12}{'a' if h < 12 else 'p'}",
                "net_gex": net,
                "text": fmt_signed(net),
                "sign": "pos" if net > 0 else ("neg" if net < 0 else "flat"),
                "captured": r is not None,
                "spot": r.spot if r is not None else None,
                "regime": r.regime if r is not None else None,
                "flip": r.flip if r is not None else None,
                "call_wall": r.call_wall if r is not None else None,
                "put_wall": r.put_wall if r is not None else None,
            }
        )
    return {
        "date": date,
        "ticker": next((r.ticker for r in rows.values() if r.ticker), "SPY"),
        "hours": hours,
        "captured": sum(1 for h in hours if h["captured"]),
        "chain": " >> ".join(h["text"] for h in hours),
    }


def history_dates(db, limit: int = 60) -> list[str]:
    """Dates holding at least one captured hour, newest first."""
    from app.models import Gex0dteHour

    rows = (
        db.query(Gex0dteHour.trade_date)
        .distinct()
        .order_by(Gex0dteHour.trade_date.desc())
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows]


# --- pusher liveness --------------------------------------------------------
#
# Snapshot age answers "how old is the data". It cannot answer "is the pusher
# alive", and those need different responses: a dead tab wants a re-click, a
# blocked tab does not (re-clicking a tab the vendor is refusing changes
# nothing and re-arms a loop that is already running). Heartbeats separate them.

HEARTBEAT_KEEP_DAYS = 3
DEAD_AFTER_S = 3 * PUSH_EVERY_S


def record_heartbeat(db, session: str, seq: int, ok: bool, reason: str | None,
                     wall_ms: int | None, mono_ms: int | None) -> None:
    """Append one cycle. Deliberately touches no snapshot state.

    It must never write a snapshot, an hour slot or a fetched_at: a cycle
    happening is not the same event as data arriving, and conflating them
    would make a stalled feed report itself fresh.
    """
    from app.models import PusherHeartbeat

    db.add(PusherHeartbeat(
        session=(session or "?")[:16],
        seq=int(seq or 0),
        ok=bool(ok),
        reason=(reason or None) and str(reason)[:160],
        wall_ms=wall_ms,
        mono_ms=mono_ms,
    ))
    # bounded by age, not by count, so a chatty session cannot evict the
    # history of a quiet one
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=HEARTBEAT_KEEP_DAYS)
    db.query(PusherHeartbeat).filter(PusherHeartbeat.received_at < cutoff).delete(
        synchronize_session=False
    )
    db.commit()


def pusher_state(db) -> dict:
    """pushing / blocked / dead / unknown, from the heartbeat trail.

    "blocked" is the state worth naming: heartbeats are arriving so the tab is
    alive and the timer is running, but every cycle is being refused. That
    looks identical to a dead pusher from snapshot age alone, and it calls for
    a completely different fix.
    """
    from app.models import PusherHeartbeat

    row = (db.query(PusherHeartbeat)
             .order_by(PusherHeartbeat.id.desc()).first())
    if row is None:
        return {"pusher_state": "unknown", "pusher_age_seconds": None,
                "pusher_reason": None, "pusher_seq": None}

    received = row.received_at
    if received.tzinfo is None:
        received = received.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - received).total_seconds()

    if age > DEAD_AFTER_S:
        state = "dead" if _window_open() else "idle"
    else:
        state = "pushing" if row.ok else "blocked"
    return {"pusher_state": state,
            "pusher_age_seconds": round(age, 1),
            "pusher_reason": row.reason,
            "pusher_seq": row.seq}
