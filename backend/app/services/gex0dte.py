"""SPY gamma for the desk's "SPY 0DTE GEX" stat, from flashAlpha.

Source: flashAlpha's /v1/stock/SPY/summary on the FREE key, five calls a day
for the whole desk (services/gex.py meters them). Two are spent on a schedule
-- 08:45 and 11:19 CT on weekdays -- and the other three are on demand, from
the desk's refresh. An on-demand refresh that would leave a scheduled slot
with no call is refused.

WHAT IT IS, AND IS NOT: the free summary carries flashAlpha's ALL-EXPIRY
exposure -- net GEX, gamma flip, call wall, put wall, regime. Its per-expiry
and 0DTE breakdowns (exposure.zero_dte, top_strikes) are empty on this plan;
the true 0DTE endpoint is Growth tier. For SPY most gamma sits in the next
two sessions, so the all-expiry reading tracks the near-dated book, but it is
not a 0DTE-only number, and there are no per-strike magnets. The view says so
(``scope``).

This replaced getgamma.io, which was a browser bookmarklet pushing the raw
0DTE chain every minute (getgamma blocks server-side requests). The hourly
history below is the same table, now filled by these readings.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

CST = ZoneInfo("America/Chicago")
# The scheduled flashAlpha reads, CT, weekdays. A slot missed while the
# server was down is still taken within SLOT_GRACE_MIN of its time.
SLOTS = (time(8, 45), time(11, 19))
SLOT_GRACE_MIN = 30
POLL_S = 60
SCOPE = "all expiries (flashAlpha free summary)"


class GammaError(Exception):
    pass


def from_flashalpha(payload: dict) -> dict:
    """The desk view from one flashAlpha /summary payload. Pure."""
    ex = (payload or {}).get("exposure") or {}
    spot = ((payload or {}).get("price") or {}).get("last")
    net = ex.get("net_gex")
    if net is None:
        raise GammaError("the flashAlpha summary carried no net GEX")
    flip = ex.get("gamma_flip")
    flip = round(float(flip), 2) if isinstance(flip, (int, float)) else None
    regime = "NEG" if float(net) < 0 else "POS"
    call_wall, put_wall = ex.get("call_wall"), ex.get("put_wall")
    ticker = str(payload.get("symbol") or "SPY").upper()
    return {
        "ticker": ticker, "mode": "all_expiry", "scope": SCOPE, "source": "flashAlpha",
        "spot": round(float(spot), 2) if isinstance(spot, (int, float)) else spot,
        "regime": regime, "vendor_regime": ex.get("regime"),
        "net_gex": float(net), "call_gex": None, "put_gex": None,
        "flip": flip, "call_wall": call_wall, "put_wall": put_wall,
        "magnet_hi": None, "magnet_lo": None, "magnets": [],
        "max_pain": ex.get("max_pain"),
        "gamma_note": (ex.get("interpretation") or {}).get("gamma"),
        "vendor_ts": payload.get("as_of"),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "note": summary_line(ticker, regime, float(net), flip, call_wall, put_wall,
                             None, None) + " · all expiries",
    }


def slot_due(now: datetime | None = None) -> str | None:
    """The scheduled slot to take now ("08:45"), or None."""
    now = (now or datetime.now(timezone.utc)).astimezone(CST)
    if now.weekday() > 4:
        return None
    minutes = now.hour * 60 + now.minute
    for slot in SLOTS:
        start = slot.hour * 60 + slot.minute
        if start <= minutes < start + SLOT_GRACE_MIN:
            return slot.strftime("%H:%M")
    return None


def pending_slots(now: datetime | None = None, taken: set[str] | None = None) -> list[str]:
    """Today's scheduled slots not yet taken and not yet past their grace --
    the calls an on-demand refresh must leave in the budget."""
    now = (now or datetime.now(timezone.utc)).astimezone(CST)
    if now.weekday() > 4:
        return []
    minutes = now.hour * 60 + now.minute
    out = []
    for slot in SLOTS:
        label = slot.strftime("%H:%M")
        if label in (taken or set()):
            continue
        if minutes < slot.hour * 60 + slot.minute + SLOT_GRACE_MIN:
            out.append(label)
    return out


def refresh(db, *, slot: str | None = None) -> dict:
    """One flashAlpha SPY call: the desk's GEX view, its hour slot, and the
    banner's SPY row (gex.refresh). ``slot`` marks a scheduled read; without
    it the call is on demand and must leave the pending slots their calls."""
    from app.services import gex as gex_svc
    from app.services import super_research as sr

    result = gex_svc.refresh(db, ["spy"], persist=True, slot=slot)
    raw = (result.get("raw") or {}).get("spy")
    if raw is None:
        raise GammaError("; ".join((result.get("errors") or {}).values()) or "no SPY reading")
    view = from_flashalpha(raw)
    sr.store_payload(db, "gex0dte", view, source=f"flashAlpha {slot}" if slot else "flashAlpha")
    record_hour(db, view)
    return {"view": view, "quota": result.get("quota")}


def budget(db) -> dict:
    """Today's flashAlpha spend as the desk shows it: the scheduled reads and
    whether each has run, and how many on-demand refreshes are left."""
    from app.services import gex as gex_svc

    quota = gex_svc.quota_state(db)
    taken = gex_svc.slots_taken(db)
    pending = pending_slots(taken=taken)
    return {
        "scheduled": [{"slot": s.strftime("%H:%M"), "taken": s.strftime("%H:%M") in taken}
                      for s in SLOTS],
        "on_demand_left": max(0, quota["remaining"] - len(pending)),
        "used": quota["used_by_api"], "cap": quota["cap"],
    }


def sweep(now: datetime | None = None) -> str | None:
    """The scheduled reads: take the due slot once. Returns it when taken."""
    from app.platform.db.session import session_scope
    from app.services import gex as gex_svc

    slot = slot_due(now)
    if slot is None:
        return None
    with session_scope() as db:
        if slot in gex_svc.slots_taken(db):
            return None
        try:
            refresh(db, slot=slot)
            log.info("SPY GEX: scheduled %s CT read taken", slot)
            return slot
        except Exception as exc:                        # noqa: BLE001
            log.warning("SPY GEX scheduled %s CT read failed: %s", slot, exc)
            return None


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
# CST trading hour, 08:00 through 16:00. Readings arrive at the scheduled
# slots and on demand, so this buckets them by hour.

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


# Readings are a few a day, so "stale" means older than the gap between the
# scheduled reads -- not a minute-cadence pusher missing ticks.
STALE_AFTER_S = 3 * 60 * 60


def staleness(fetched_at) -> dict:
    """How old the snapshot is, and whether that is a problem right now.

    Age alone is not a fault: readings are taken at 08:45 and 11:19 CT and on
    demand, so one a few hours old is normal. Inside the session one older
    than STALE_AFTER_S means a scheduled read did not land, and the desk
    says so.
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
