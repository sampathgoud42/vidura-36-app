"""econ_events.py — daily macro context for the signal desk.

Builds super_research/econ_today.json once per day (first aggregate cycle):

  * scheduled events for today from the 2026 US macro calendar — FOMC rate
    decisions, CPI releases (BLS schedule), and the jobs report (first Friday)
  * live rate context from the same yfinance stack the bots run on:
    10y/5y/30y treasury yields (^TNX/^FVX/^TYX) with day-over-day deltas,
    flagged when the 10y moves >= 5bp (a real macro tape day)

The supervisor stamps the composed note into the `econ` column of every A/B
ledger row logged that day, so a signal fired into an FOMC afternoon or a
CPI morning carries that warning with it (desk + chat watcher display it).

Zero keys, zero new dependencies; every fetch is fail-soft (worst case the
note is just the scheduled-calendar part, or empty).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Chicago")
BIG_MOVE_BP = 5.0            # 10y daily move that makes the tape "macro-driven"

# ── 2026 US macro calendar (CST release times) ────────────────────────────────
# FOMC decision days (second day of each 2026 meeting, statement 13:00 CST)
FOMC_2026 = {"2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
             "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09"}
# CPI release mornings per the BLS schedule (07:30 CST)
CPI_2026 = {"2026-01-13", "2026-02-11", "2026-03-11", "2026-04-10",
            "2026-05-12", "2026-06-10", "2026-07-14", "2026-08-11",
            "2026-09-11", "2026-10-13", "2026-11-10", "2026-12-10"}


def _is_nfp_day(d: date) -> bool:
    """Jobs report = first Friday of the month, 07:30 CST."""
    return d.weekday() == 4 and d.day <= 7


def _events_for(d: date) -> list[dict]:
    ds = d.isoformat()
    ev = []
    if ds in FOMC_2026:
        ev.append({"time_cst": "13:00", "name": "FOMC rate decision", "impact": "high"})
    if ds in CPI_2026:
        ev.append({"time_cst": "07:30", "name": "CPI release", "impact": "high"})
    if _is_nfp_day(d):
        ev.append({"time_cst": "07:30", "name": "Jobs report (NFP)", "impact": "high"})
    return ev


def _yields() -> dict:
    """Treasury yields + day-over-day deltas via yfinance index tickers
    (^TNX/^FVX/^TYX quote yield*10). Fail-soft: returns {} on any error."""
    try:
        import yfinance as yf
        out = {}
        raw = yf.download(["^TNX", "^FVX", "^TYX"], interval="1d", period="5d",
                          progress=False, auto_adjust=False)["Close"]
        for sym, name in (("^TNX", "10y"), ("^FVX", "5y"), ("^TYX", "30y")):
            s = raw[sym].dropna()
            if len(s) >= 2:
                v, pv = float(s.iloc[-1]), float(s.iloc[-2])
                scale = 0.1 if v > 20 else 1.0   # ^TNX legacy 45.7 form vs direct 4.57
                out[name] = round(v * scale, 3)
                out[f"d{name}_bp"] = round((v - pv) * scale * 100, 1)
        return out
    except Exception:
        return {}


def _note(events: list[dict], y: dict) -> str:
    bits = [f'{e["name"]} {e["time_cst"]} CST' for e in events]
    d10 = y.get("d10y_bp")
    if d10 is not None and abs(d10) >= BIG_MOVE_BP:
        bits.append(f'10Y {"+" if d10 >= 0 else ""}{d10:.0f}bp to {y.get("10y", "?")}%')
    return " · ".join(bits)


def refresh_today(here: Path) -> dict:
    """Build/return today's econ context, cached to econ_today.json (one
    yfinance call per day; every later call is a file read)."""
    path = Path(here) / "econ_today.json"
    today = datetime.now(TZ).date()
    try:
        cur = json.loads(path.read_text(encoding="utf-8"))
        if cur.get("date") == today.isoformat():
            return cur
    except Exception:
        pass
    events = _events_for(today)
    y = _yields()
    ctx = {"date": today.isoformat(), "events": events, "yields": y,
           "note": _note(events, y),
           "high_impact": bool(events) or abs(y.get("d10y_bp", 0)) >= BIG_MOVE_BP}
    try:
        path.write_text(json.dumps(ctx, indent=1), encoding="utf-8")
    except Exception:
        pass
    return ctx


if __name__ == "__main__":
    import sys
    ctx = refresh_today(Path(__file__).resolve().parent)
    json.dump(ctx, sys.stdout, indent=1)
