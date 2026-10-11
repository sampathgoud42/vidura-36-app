"""One row of a DMI board, whatever the instrument.

The commodity board and the crypto board ask the same question of different
feeds: what does DMI say on 2, 5, 10, 15 and 30 minutes, and do they agree?
That is one calculation, so it lives here once and both boards call it.

Writing it twice was the obvious path and the wrong one. Two copies of a
signal rule drift the first time either is touched, and the drift is silent --
nothing compares the boards, so gold and bitcoin would quietly start using
different definitions of "the 2-minute side" and the desk would have no way to
tell.

Every source feeds this the same thing: a list of 1-minute bars, oldest first,
each ``{"time", "open", "high", "low", "close"}``. Whatever fetched them --
Tradier, a spot poller, Coinbase -- has already done its own job by then.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.domains.trading.market import indicators


def bar_epoch(bar: dict) -> int | None:
    """When a bar began, in unix seconds, whichever shape its source writes:
    Coinbase an epoch; Tradier an epoch ``timestamp`` beside its ET clock
    time; the off-hours accumulator a Chicago "YYYY-MM-DD HH:MM"."""
    for key in ("timestamp", "time"):
        value = bar.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
    value = bar.get("time")
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace(" ", "T"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo("America/Chicago"))
    return int(moment.timestamp())

# The timeframes every board shows, and the factor each is folded from. All
# of them come from ONE fetch of 1-minute bars: separate fetches would let the
# rows describe different instants and disagree for a reason that has nothing
# to do with the market.
#
# The slowest one sets how much history a feed has to supply. A 10-minute ADX
# needs 29 ten-minute bars, so roughly 290 minutes of coverage -- which is why
# aggregate keeps interior buckets that are missing a minute rather than
# discarding them.
TIMEFRAMES = {"m1": 1, "m2": 2, "m5": 5, "m10": 10, "m15": 15, "m30": 30}

# What the board SHOWS, in order. 1m is still computed and still in the row
# -- the V7/V8 bot engines (botstation.dmi_stack) read m1..m10 and trade on
# them -- but the desk no longer shows it or signals from it.
SHOWN = ("m2", "m5", "m10", "m15", "m30")

# The signal: the fast-to-mid stack must agree -- 2m, 5m and 15m, the last
# being the horizon of the fifteen-minute contracts these boards trade -- and
# the slow side confirms it: 30m pointing the same way is the ✓. 10m is shown
# as context and decides nothing, so one middling column cannot veto a trend
# the three deciding clocks agree on.
SIGNAL_FRAMES = ("m2", "m5", "m15")
CONFIRM_FRAME = "m30"

# 15m and 30m need hours of history -- a 30m ADX needs 29 thirty-minute bars,
# about 14.5 hours -- which a single 1-minute fetch cannot reach on every
# feed. A feed that has 5-minute bars passes them as ``slow_bars`` and the
# slow columns fold from those instead, into 15- and 30-minute buckets.
SLOW = {"m15": 15, "m30": 30}     # bucket width, minutes, over 5-minute input
SLOW_BAR_MINUTES = 5


def with_slope(bars: list[dict]) -> dict | None:
    """A DMI reading plus which way ADX is moving.

    The slope is this reading minus the same calculation one bar back.
    Without it an ADX of 25 looks identical whether the trend is building or
    dying -- which are opposite trades.
    """
    reading = indicators.dmi(bars)
    if reading is None:
        return None
    previous = (indicators.dmi(bars[:-1])
                if len(bars) > indicators.MIN_BARS else None)
    reading["adx_slope"] = (round(reading["adx"] - previous["adx"], 2)
                            if previous is not None else None)
    return reading


def last_close(bars: list[dict]) -> float | None:
    for bar in reversed(bars):
        if bar.get("close") is not None:
            return float(bar["close"])
    return None


def row_from_bars(key: str, label: str, symbol: str, bars: list[dict],
                  source: str, *, slow_bars: list[dict] | None = None) -> dict:
    """One board row: 2, 5, 10, 15 and 30-minute DMI (and 1m, kept for the
    bots), with the signal the desk trades.

    ``slow_bars`` are 5-minute bars for the same instrument, when the feed
    has them: 15m and 30m fold from those, which reach back far enough. Without
    them they fold from the 1-minute bars, and read as unavailable until the
    feed holds enough history.

    ``key`` is what the desk keys the row by and is emitted as ``bot`` --
    the field name the panel reads. It is called ``bot`` because that is what
    the board has always sent; renaming it here would blank the panel for a
    tidiness nobody asked for.
    """
    # Fold ONCE per timeframe and reuse. Every timeframe was being aggregated
    # twice -- once to compute the reading and again to count its bars -- so a
    # four-timeframe row folded the series eight times instead of four, on
    # every coin, on every refresh. Eight coins on a 60s poll made that the
    # single largest CPU cost on the box.
    folded = {}
    for name, factor in TIMEFRAMES.items():
        if name in SLOW and slow_bars:
            folded[name] = indicators.aggregate(slow_bars, SLOW[name],
                                                bar_minutes=SLOW_BAR_MINUTES)
        else:
            folded[name] = indicators.aggregate(bars, factor) if factor > 1 else bars
    readings = {name: with_slope(series) for name, series in folded.items()}

    # A signal only when 2m, 5m and 15m all lean the same way. Any of them
    # missing or disagreeing is "mixed" rather than resolved in favour of one:
    # the point of reading several clocks is that any one can be wrong.
    sides = [(readings[name] or {}).get("side") for name in SIGNAL_FRAMES]
    signal = sides[0] if (sides[0] and all(s == sides[0] for s in sides)) else None
    confirms = bool(signal) and (readings[CONFIRM_FRAME] or {}).get("side") == signal
    # The OLD headline, 1m and 2m agreeing, kept for the BTC-15 v6 engine
    # (btc15.alignment), which is frozen on its own rule: moving the board's
    # signal to 2m/5m/15m must not quietly change a bot that may be live.
    m1_side = (readings["m1"] or {}).get("side")
    signal_1m2m = m1_side if (m1_side and m1_side == (readings["m2"] or {}).get("side")) else None

    row = {
        "bot": key,
        "label": label,
        "symbol": symbol,
        "source": source,
        "last": last_close(bars),
        "signal": signal,
        "direction": signal,
        # 30m agrees with the signal. ``m5_confirms`` is the same flag under
        # the name every consumer read before the rule moved to 30m.
        "confirms": confirms,
        "m5_confirms": confirms,
        "signal_rule": {"agree": [f"{n[1:]}m" for n in SIGNAL_FRAMES],
                        "confirm": f"{CONFIRM_FRAME[1:]}m"},
        "signal_1m2m": signal_1m2m,
        # When the newest bar the DMI was read from began. A board cached a
        # minute ago over a market that stopped trading hours ago is fresh
        # as a cache and stale as a signal; this is the second one.
        "bar_time": bar_epoch(bars[-1]) if bars else None,
    }
    for name in TIMEFRAMES:
        reading = readings[name] or {}
        row[f"{name}_side"] = reading.get("side")
        row[f"{name}_adx"] = reading.get("adx")
        row[f"{name}_pdi"] = reading.get("plus_di")
        row[f"{name}_mdi"] = reading.get("minus_di")
        row[f"{name}_slope"] = reading.get("adx_slope")
        row[f"bars_{name[1:]}m"] = len(folded[name])
    return row


def unavailable_row(key: str, label: str, symbol: str, *, reason: str,
                    bars_seen: int = 0) -> dict:
    """A row that could not be computed, saying why.

    A row of dashes is indistinguishable from a flat market, and those are not
    the same news: one needs somebody to look at a feed, the other needs
    nobody to do anything.
    """
    return {"bot": key, "label": label, "symbol": symbol,
            "source": "unavailable", "error": reason,
            "warmup": {"bars": bars_seen, "needs": indicators.MIN_BARS}}
