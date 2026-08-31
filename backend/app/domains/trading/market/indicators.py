"""Wilder DMI/ADX, and the bar aggregation the venue cannot do for us.

ONE implementation. Phase 1 found the desk's HOT scan and the 36-Trades DMI
board sharing this maths by reaching across modules for a private function,
and the commodity bots running a second copy of it over a different data
source. Same indicator, three call sites, two implementations. This is the
one, and the callers differ only in which bars they hand it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

# Tradier serves 1min, 5min and 15min. Anything else has to be built from a
# finer bar, which is why NATIVE and DERIVED are separate ideas here rather
# than one list of "supported intervals".
NATIVE_INTERVALS = ("1min", "5min", "15min")
DERIVED_FROM = {"2min": ("1min", 2), "3min": ("1min", 3), "10min": ("5min", 2)}


def source_interval(interval: str) -> tuple[str, int]:
    """(what to ask the venue for, how many of those make one bar).

    A factor of 1 means the venue serves it directly.
    """
    if interval in NATIVE_INTERVALS:
        return interval, 1
    if interval in DERIVED_FROM:
        return DERIVED_FROM[interval]
    raise ValueError(
        f"unsupported interval {interval!r}; native: "
        f"{', '.join(NATIVE_INTERVALS)}; derived: "
        f"{', '.join(DERIVED_FROM)}")


def _parse(ts: str | int | float) -> datetime | None:
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts)
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(
            tzinfo=None)
    except ValueError:
        return None


def aggregate(bars: list[dict], factor: int) -> list[dict]:
    """Fold N bars into one.

    Grouped by the bar's own timestamp rather than by position in the list, so
    a gap in the feed does not silently shift every later bucket by one. A
    2-minute bar built from 09:31 and 09:33 because 09:32 was missing is not a
    2-minute bar, and nothing downstream could tell.
    """
    if factor <= 1:
        return bars

    buckets: dict[int, list[dict]] = {}
    for bar in bars:
        moment = _parse(bar.get("time") or bar.get("timestamp"))
        if moment is None:
            continue
        # Minutes since midnight, floored to the bucket width.
        slot = ((moment.hour * 60 + moment.minute) // factor) * factor
        buckets.setdefault(moment.toordinal() * 10_000 + slot, []).append(bar)

    out = []
    ordered = sorted(buckets)
    for key in ordered:
        group = buckets[key]
        # ONLY the last bucket is dropped when short, and only because it is
        # the bar still forming -- keeping it would make the newest reading
        # flicker as it fills.
        #
        # This used to drop EVERY short bucket, which is a different rule
        # wearing the same comment. On a contiguous feed the two are
        # identical, because only the final bucket is ever partial. On a feed
        # with gaps they are not: a thinly traded market publishes no candle
        # for a minute with no trades, so most of its buckets are short and
        # nearly the whole series was being discarded. BNB spanned 531
        # minutes and produced 15 five-minute bars instead of ~106, which is
        # below what an ADX needs -- the column simply went blank, with
        # nothing anywhere saying why.
        #
        # An interior bucket missing a minute is still the right time window.
        # Its high, low and close are all real; there is just less inside it.
        if len(group) < factor and key == ordered[-1]:
            continue
        out.append({
            "time": group[0].get("time") or group[0].get("timestamp"),
            "open": float(group[0].get("open") or 0),
            "high": max(float(b.get("high") or 0) for b in group),
            "low": min(float(b.get("low") or 0) for b in group if b.get("low")),
            "close": float(group[-1].get("close") or 0),
            "volume": sum(float(b.get("volume") or 0) for b in group),
        })
    return out


def _wilder(values: list[float], period: int) -> list[float | None]:
    """Wilder's smoothing: a seed average, then an accumulating decay."""
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = (prev * (period - 1) + values[i]) / period
        out[i] = prev
    return out


# Wilder's DMI needs two full periods plus the seed bar before ADX means
# anything. Named here rather than left inline, because callers have to be
# able to ask "is there enough data yet?" without re-deriving the arithmetic
# and drifting from what dmi() actually enforces.
DEFAULT_PERIOD = 14
MIN_BARS = DEFAULT_PERIOD * 2 + 1


def min_bars(period: int = DEFAULT_PERIOD) -> int:
    return period * 2 + 1


def dmi(bars: list[dict], period: int = DEFAULT_PERIOD) -> dict | None:
    """+DI, -DI and ADX from the latest bar.

    Returns None rather than a partial reading when there are not enough bars.
    A number computed from its own seed looks exactly like a real one on a
    board, and there is no way for the operator to tell.
    """
    if len(bars) < min_bars(period):
        return None

    highs = [float(b.get("high") or 0) for b in bars]
    lows = [float(b.get("low") or 0) for b in bars]
    closes = [float(b.get("close") or 0) for b in bars]

    trs, plus_dm, minus_dm = [], [], []
    for i in range(1, len(bars)):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
        trs.append(max(highs[i] - lows[i],
                       abs(highs[i] - closes[i - 1]),
                       abs(lows[i] - closes[i - 1])))

    atr = _wilder(trs, period)
    sm_plus = _wilder(plus_dm, period)
    sm_minus = _wilder(minus_dm, period)

    dx: list[float] = []
    for a, p, m in zip(atr, sm_plus, sm_minus):
        if not a or a <= 0 or p is None or m is None:
            continue
        pdi, mdi = 100 * p / a, 100 * m / a
        total = pdi + mdi
        dx.append(100 * abs(pdi - mdi) / total if total else 0.0)

    if len(dx) < period:
        return None
    adx_series = _wilder(dx, period)
    adx = next((v for v in reversed(adx_series) if v is not None), None)
    if adx is None or not atr[-1]:
        return None

    plus_di = 100 * (sm_plus[-1] or 0) / atr[-1]
    minus_di = 100 * (sm_minus[-1] or 0) / atr[-1]
    return {
        "plus_di": round(plus_di, 2),
        "minus_di": round(minus_di, 2),
        "adx": round(adx, 2),
        # The side the dominant direction points at, or None when neither
        # dominates. "flat" is a real answer and must not be rendered as a
        # weak buy.
        "side": ("call" if plus_di > minus_di else
                 "put" if minus_di > plus_di else None),
        "bars": len(bars),
    }


def lookback_days(interval: str) -> int:
    """How far back to ask, so a coarse bar still reaches a usable count.

    40 days of hourly bars is roughly the same number of readings as 5 days of
    5-minute ones. Ask for 5 days of hourly and the ADX comes back built
    mostly from its own seed.
    """
    return {"1min": 2, "2min": 3, "3min": 4, "5min": 5,
            "10min": 8, "15min": 10}.get(interval, 5)


def start_date(interval: str, today: datetime | None = None) -> str:
    day = (today or datetime.now()) - timedelta(days=lookback_days(interval))
    return day.strftime("%Y-%m-%d")
