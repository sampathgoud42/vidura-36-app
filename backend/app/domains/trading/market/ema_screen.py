"""A 21-period EMA on 4-hour bars, and the two setups the Best Bets sheet lists.

Tradier has no 4-hour bar. /markets/timesales serves tick, 1min, 5min and
15min, and keeps 15-minute bars for 40 days when asked for the regular session
only (18 when extended hours are included); /markets/history is daily and
coarser. So the 4-hour chart is BUILT here, from regular-session 15-minute
bars, in buckets anchored on the 09:30 open: 09:30-13:30 and 13:30-16:00. That
is the session-anchored 4H chart charting platforms draw for US stocks by
default. Buckets anchored on midnight would run 08:00-12:00 and 12:00-16:00,
cut the morning in two, and disagree with any chart the operator checks this
against.

Forty days of the regular session is ~27 sessions, which is ~55 four-hour
bars. That is all the history there is, and it bounds what "the recent past"
can mean for Strategy A: the first 20 bars only warm the EMA up, so a dip is
looked for in the last ~35 bars, about 17 sessions.

The EMA is the recursive one, ``ewm(span=21, adjust=False)``, which is what
charting platforms plot. The default ``adjust=True`` reweights the first bars as
if the history had begun there; on 55 bars the two agree by the last bar, but
the first 21 are unreliable either way, so they are masked (``min_periods``)
rather than read.

The setups
  A  deep retracement: in the window, a bar's LOW fell more than 20% below that
     bar's EMA; the close is still below the EMA now, but turning back up --
     rising over the last 5 closes, the newest close above the one before it,
     and the gap narrower than it was at its worst.
  B  fresh cross: the close crossed above the EMA on one of the last 3 candles
     (1 = the newest), is still above it, and less than 20% above.

Days to catch
  "Price rises at v a bar, how long until it reaches the EMA" is usually worked
  out as gap / v, as if the EMA stood still. It does not: every new bar pulls
  the EMA a fraction alpha = 2/(span+1) of the way toward the price, so the gap
  closes from both ends. Under a constant velocity v the gap follows

      g(n+1) = (1 - alpha) * (g(n) - v)

  which reaches zero after

      n = ln(1 + alpha * g0 / ((1 - alpha) * v)) / -ln(1 - alpha)   bars.

  A $20 gap closing at $1 a bar is 20 bars by the flat-EMA sum and 11.5 by this
  one. Bars become trading days at two per session, and trading hours at 6.5
  per session. It is a projection of the last five bars, not a forecast.

Pure functions over data: nothing here fetches, caches or knows about a venue.
The desk's /tradier/best-bets and tools/ema_screener.py both call ``screen``,
so the sheet and the terminal can never disagree about a ticker.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

EASTERN = ZoneInfo("America/New_York")

# How each session is cut into 4-hour bars. `offset` is where the buckets are
# anchored (from midnight, exchange time); `open`/`close` bound the bars kept.
SESSIONS = {
    "regular": {"offset": "9h30min", "open": "09:30", "close": "16:00",
                "bars_per_day": 2, "hours_per_day": 6.5},
    # 04:00-20:00 with every bucket a full four hours. Tradier keeps only 18
    # days of 15-minute bars once extended hours are included.
    "extended": {"offset": "0h", "open": "04:00", "close": "20:00",
                 "bars_per_day": 4, "hours_per_day": 16.0},
}


# The bar sizes the screen can fold its 15-minute bars into, in hours.
BAR_HOURS = (1, 2, 4)
SPAN_RANGE = (5, 100)


def bars_per_day(session: str, hours: int = 4) -> int:
    """How many bars of `hours` one session day holds -- the last one short
    when the session does not divide evenly (a regular day is 6.5 hours)."""
    return math.ceil(SESSIONS[session]["hours_per_day"] / hours)


@dataclass(frozen=True)
class Rules:
    span: int = 21              # EMA period, in bars of bar_hours
    deep_pct: float = 20.0      # A: a low more than this far below the EMA
    near_pct: float = 20.0      # B: now less than this far above it
    cross_within: int = 3       # B: crossed on one of the last N candles
    velocity_bars: int = 5      # closes the rate of change is fitted over
    session: str = "regular"
    bar_hours: int = 4          # the bar the EMA is read on: 1, 2 or 4 hours

    def __post_init__(self):
        if self.bar_hours not in BAR_HOURS:
            raise ValueError(f"bar_hours must be one of {', '.join(map(str, BAR_HOURS))}")
        if not SPAN_RANGE[0] <= self.span <= SPAN_RANGE[1]:
            raise ValueError(f"the EMA period must be {SPAN_RANGE[0]} to {SPAN_RANGE[1]}")
        if self.session not in SESSIONS:
            raise ValueError(f"unknown session {self.session!r}; "
                             f"one of {', '.join(SESSIONS)}")
        if self.span < 2 or self.velocity_bars < 2 or self.cross_within < 1:
            raise ValueError("span and velocity_bars need at least 2, "
                             "cross_within at least 1")

    @property
    def alpha(self) -> float:
        return 2.0 / (self.span + 1)

    @property
    def min_bars(self) -> int:
        """Enough for one trusted EMA reading plus a velocity fit after it."""
        return self.span + self.velocity_bars

    def public(self) -> dict:
        return asdict(self)


# ---- bars -----------------------------------------------------------------

def _num(value) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _when(bar: dict) -> datetime | None:
    """The bar's start in exchange time, without a zone.

    Tradier's `time` is already US/Eastern wall clock, which is what makes the
    09:30 anchor right on both sides of a daylight-saving change. The epoch
    `timestamp` is the fallback, converted to the same clock.
    """
    raw = bar.get("time")
    if raw:
        try:
            moment = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            moment = None
        if moment is not None:
            if moment.tzinfo is not None:
                moment = moment.astimezone(EASTERN).replace(tzinfo=None)
            return moment
    stamp = _num(bar.get("timestamp"))
    if stamp:
        return datetime.fromtimestamp(stamp, EASTERN).replace(tzinfo=None)
    return None


def frame(bars: list[dict], session: str = "regular") -> pd.DataFrame:
    """Venue bars -> a time-indexed OHLCV frame, inside the session only.

    A row with no usable close is dropped rather than zero-filled: a zero close
    is a 100% drop to the EMA. Duplicate timestamps keep the last copy, which
    is how a re-sent bar corrects itself.
    """
    spec = SESSIONS[session]
    rows = []
    for bar in bars or []:
        at = _when(bar)
        close = _num(bar.get("close"))
        if close is None:
            close = _num(bar.get("price"))
        if at is None or close is None or close <= 0:
            continue
        opened = _num(bar.get("open")) or close
        high = _num(bar.get("high")) or max(opened, close)
        low = _num(bar.get("low")) or min(opened, close)
        rows.append((at, opened, high, low, close, _num(bar.get("volume")) or 0.0))
    out = pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"])
    if out.empty:
        return out.set_index("time")
    out = out.set_index("time").sort_index()
    out = out[~out.index.duplicated(keep="last")]
    # A venue that ignores session_filter still cannot put a 07:45 print into
    # the 09:30 bar: the session is enforced here as well as asked for.
    return out.between_time(spec["open"], spec["close"], inclusive="left")


def four_hour(bars: pd.DataFrame, session: str = "regular", hours: int = 4) -> pd.DataFrame:
    """Fold finer bars into session-anchored bars of `hours` (4 by default).

    Grouped by clock time, not by position, so a missing 15-minute bar leaves a
    thinner 4-hour bar rather than shifting every later one. The newest bucket
    is kept even while it is still forming: its close is the current price, and
    the EMA a chart shows includes it.
    """
    if bars.empty:
        return bars.assign(n=pd.Series(dtype="int64"))
    spec = SESSIONS[session]
    grouped = bars.resample(f"{hours}h", offset=spec["offset"], label="left", closed="left")
    out = grouped.agg({"open": "first", "high": "max", "low": "min",
                       "close": "last", "volume": "sum"})
    out["n"] = grouped["close"].count()
    return out[out["n"] > 0]


def ema(close: pd.Series, span: int = 21) -> pd.Series:
    """The recursive EMA, masked until it has seen `span` bars."""
    return close.ewm(span=span, adjust=False, min_periods=span).mean()


def slope(values) -> float:
    """Least-squares slope per bar. Fitted over every close in the window
    rather than its two ends, so one outsized bar does not set the pace."""
    y = np.asarray(values, dtype=float)
    return float(np.polyfit(np.arange(len(y)), y, 1)[0])


def bars_to_catch(gap: float, velocity: float, alpha: float) -> float | None:
    """Bars until a close below the EMA reaches it (module docstring).

    ``gap`` is EMA - price. Zero when there is no gap to close; None when the
    price is not rising, because then the two only converge asymptotically.
    """
    if gap <= 0:
        return 0.0
    if velocity <= 0:
        return None
    k = (1.0 - alpha) * velocity / alpha
    return math.log1p(gap / k) / -math.log1p(-alpha)


def _bucket_end(start: pd.Timestamp, session: str, hours: int = 4) -> datetime:
    close_h, close_m = map(int, SESSIONS[session]["close"].split(":"))
    session_close = start.normalize() + timedelta(hours=close_h, minutes=close_m)
    return min(start + timedelta(hours=hours), session_close).to_pydatetime()


def _r(value, places: int = 2):
    return None if value is None or not math.isfinite(value) else round(float(value), places)


def thin_bars(fine: pd.DataFrame, four: pd.DataFrame, session: str = "regular",
              hours: int = 4) -> int:
    """How many settled 4-hour bars were built from fewer bars than their
    window holds -- the venue's missing chunks, made countable.

    The step is read off the data (15 minutes from Tradier), so the count
    holds for whatever interval was fetched. The newest bar is left out: it
    is short because it is still forming, not because anything is missing.
    A half-day's single bar counts, which is honest -- it IS thin.
    """
    if len(four) < 2 or len(fine) < 2:
        return 0
    gaps = fine.index.to_series().diff().dropna()
    gaps = gaps[gaps <= pd.Timedelta(hours=1)]
    if gaps.empty:
        return 0
    step = gaps.min()
    thin = 0
    for start, count in zip(four.index[:-1], four["n"].iloc[:-1]):
        span = pd.Timestamp(_bucket_end(start, session, hours)) - start
        if count < round(span / step):
            thin += 1
    return thin


# ---- the screen -----------------------------------------------------------

def screen(symbol: str, bars: list[dict], rules: Rules | None = None, *,
           as_of: datetime | None = None) -> dict:
    """One ticker's reading: price against its 4-hour EMA, and which setup
    (if either) it is in. ``as_of`` is exchange time without a zone; with it,
    the row says whether the newest 4-hour bar is still forming."""
    rules = rules or Rules()
    fine = frame(bars, rules.session)
    four = four_hour(fine, rules.session, rules.bar_hours)
    base = {"symbol": symbol, "setup": None, "bars": int(len(four))}
    if len(four) < rules.min_bars:
        return {**base, "available": False,
                "reason": f"{len(four)} {rules.bar_hours}-hour bars; a {rules.span} EMA and a "
                          f"{rules.velocity_bars}-bar velocity need {rules.min_bars}"}

    four = four.assign(ema=ema(four["close"], rules.span))
    trusted = four[four["ema"].notna()]
    closes = four["close"].to_numpy()
    price = float(closes[-1])
    level = float(four["ema"].iloc[-1])
    gap = price - level
    distance = 100.0 * gap / level

    # Strategy A's dip is measured on the LOW: a wick that reached 20% below
    # the EMA is a price that traded there, and the capitulation bar is often
    # exactly that wick.
    dips = 100.0 * (trusted["low"] - trusted["ema"]) / trusted["ema"]
    deepest_at = dips.idxmin()
    deepest = float(dips.min())

    velocity = slope(closes[-rules.velocity_bars:])
    ema_slope = float(trusted["ema"].iloc[-1] - trusted["ema"].iloc[-2])

    # A cross needs a trusted EMA on both sides of it, so the first trusted
    # bar can never be one.
    above = trusted["close"] > trusted["ema"]
    crossed = above & ~above.shift(1, fill_value=True).astype(bool)
    cross_age = None
    if crossed.any():
        last_cross = crossed[crossed].index[-1]
        cross_age = int(len(four) - four.index.get_loc(last_cross))

    turning_up = velocity > 0 and closes[-1] > closes[-2]
    setup = None
    if deepest < -rules.deep_pct and gap < 0 and turning_up and distance > deepest:
        setup = "A"
    elif (cross_age is not None and cross_age <= rules.cross_within
          and gap > 0 and distance < rules.near_pct):
        setup = "B"

    spec = SESSIONS[rules.session]
    catch = bars_to_catch(-gap, velocity, rules.alpha) if gap < 0 else None
    days = None if catch is None else catch / bars_per_day(rules.session, rules.bar_hours)
    last_start = four.index[-1]
    return {
        **base,
        "available": True,
        "setup": setup,
        "price": _r(price, 4 if price < 1 else 2),
        "ema": _r(level, 4 if level < 1 else 2),
        "gap": _r(gap, 4 if abs(gap) < 1 else 2),
        "distance_pct": _r(distance),
        "deepest_pct": _r(deepest),
        "deepest_at": deepest_at.isoformat(),
        "velocity": _r(velocity, 4),
        "ema_slope": _r(ema_slope, 4),
        "cross_age": cross_age,
        "bars_to_catch": _r(catch, 1),
        "days_to_catch": _r(days, 1),
        "hours_to_catch": _r(None if days is None else days * spec["hours_per_day"], 1),
        "trusted_bars": int(len(trusted)),
        "thin_bars": thin_bars(fine, four, rules.session, rules.bar_hours),
        "window": {"from": four.index[0].isoformat(), "to": last_start.isoformat()},
        "as_of": bars_as_of(bars),
        "forming": (None if as_of is None
                    else as_of < _bucket_end(last_start, rules.session, rules.bar_hours)),
    }


def bars_as_of(bars: list[dict]) -> str | None:
    """When the newest bar handed in started, exchange time."""
    moments = [m for m in (_when(b) for b in bars or []) if m is not None]
    return max(moments).isoformat() if moments else None


def by_setup(rows: list[dict]) -> dict[str, list[dict]]:
    """The two tables: A soonest-to-catch first, B freshest cross first."""
    a = [r for r in rows if r.get("setup") == "A"]
    b = [r for r in rows if r.get("setup") == "B"]
    a.sort(key=lambda r: (r["days_to_catch"] is None,
                          r["days_to_catch"] if r["days_to_catch"] is not None else 0.0,
                          r["distance_pct"]))
    b.sort(key=lambda r: (r["cross_age"], r["distance_pct"]))
    return {"A": a, "B": b}


def now_eastern() -> datetime:
    return datetime.now(EASTERN).replace(tzinfo=None)
