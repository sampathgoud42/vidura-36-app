"""Synthetic intraday bars shaped like the venue's, for the screen tests.

Deterministic price paths -- a crash and a recovery, a fresh cross -- so a test
can say which setup a ticker must land in without a network or a market.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd


def sessions(n: int, start: date = date(2026, 8, 3)) -> list[date]:
    """The first n weekdays from `start`."""
    out, day = [], start
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def bars(closes_by_day: list[tuple[date, list[float]]], *, open_at=(9, 30),
         minutes: int = 15, wick: float = 0.001) -> list[dict]:
    """Tradier-shaped timesales rows: one close per bar, open at the last close."""
    out = []
    for day, closes in closes_by_day:
        at = datetime(day.year, day.month, day.day, *open_at)
        prev = closes[0]
        for close in closes:
            out.append({"time": at.isoformat(), "open": prev, "close": close,
                        "high": max(prev, close) * (1 + wick),
                        "low": min(prev, close) * (1 - wick), "volume": 1000})
            prev = close
            at += timedelta(minutes=minutes)
    return out


def path(days: list[date], price_at) -> list[tuple[date, list[float]]]:
    """26 regular-session 15-minute closes a day, from price_at(day_index, bar)."""
    return [(d, [round(price_at(i, k), 4) for k in range(26)]) for i, d in enumerate(days)]


def crash_then(recovery_per_bar: float, *, crash_days: int = 3, days: int = 28,
               start: date = date(2026, 8, 3)) -> list[dict]:
    """Flat near 100 with a small wobble, a crash to ~70, then a steady drift
    of `recovery_per_bar` per 15-minute bar for the last ten sessions."""
    ds = sessions(days, start)
    level = {"px": 100.0}

    def price_at(i, k):
        if i < days - 10 - crash_days:
            return 100 + math.sin((i * 26 + k) / 7)
        if i < days - 10:
            level["px"] -= 30 / (crash_days * 26)
        else:
            level["px"] += recovery_per_bar
        return level["px"]

    return bars(path(ds, price_at))


def cross(bars_ago: int, *, jump: float = 1.03, days: int = 28,
          start: date = date(2026, 8, 3)) -> list[dict]:
    """Drifting down under its EMA, then a jump above it `bars_ago` 4-hour bars
    from the end (1 = the newest), holding flat after."""
    ds = sessions(days, start)
    cross_bar = len(ds) * 2 - bars_ago

    def price_at(i, k):
        bar = i * 2 + (0 if k < 16 else 1)
        base = 100 - 0.2 * min(bar, cross_bar)
        return base * jump if bar >= cross_bar else base

    return bars(path(ds, price_at))


def flat(price: float = 50.0, *, days: int = 28, start: date = date(2026, 8, 3)) -> list[dict]:
    ds = sessions(days, start)
    return bars(path(ds, lambda i, k: price + 0.05 * math.sin(k)))


# ---- BreakoutRadar: daily candles that coil, then break out ----------------

BASE_VOL = 1_000_000


def breakout_frame(opens, closes, vols, *, highs=None, start="2026-03-02") -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=len(closes))
    o = np.asarray(opens, float)
    c = np.asarray(closes, float)
    h = np.asarray(highs, float) if highs is not None else np.maximum(o, c) * 1.004
    return pd.DataFrame({"open": o, "high": h, "low": np.minimum(o, c) * 0.996,
                         "close": c, "volume": np.asarray(vols, float)}, index=idx)


def breakout_scenario(*, lead=None, coil=None, breakout=(104.5, 110.5), vol_x=3.0, after=(),
                      base_vol=BASE_VOL, wick_spike=None):
    """A climb from 80 to 99, twenty candles whose bodies sit in 99..104, then a
    green breakout candle on `vol_x` volume -- which passes all eight rules.

    lead: closes before the coil; coil: (open, close) pairs; breakout: the
    breakout candle's (open, close); after: (open, close) candles after it."""
    lead = list(lead if lead is not None else np.linspace(80, 99, 60))
    coil = list(coil if coil is not None else
                [(99 + (i % 3), 101 + (i % 4)) for i in range(20)])   # bodies 99..104
    opens = [c * 0.998 for c in lead] + [o for o, _ in coil] + [breakout[0]] + [o for o, _ in after]
    closes = lead + [c for _, c in coil] + [breakout[1]] + [c for _, c in after]
    vols = [base_vol] * (len(lead) + len(coil)) + [base_vol * vol_x] + [base_vol] * len(after)
    highs = None
    if wick_spike is not None:
        highs = list(np.maximum(opens, closes) * 1.004)
        highs[len(lead) + 5] = wick_spike            # a wick inside the coil
    return breakout_frame(opens, closes, vols, highs=highs)
