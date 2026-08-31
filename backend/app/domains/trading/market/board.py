"""One row of a DMI board, whatever the instrument.

The commodity board and the crypto board ask the same question of different
feeds: what does DMI say on 1, 2, 5 and 10 minutes, and do the faster
timeframes agree?
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

from app.domains.trading.market import indicators

# The timeframes every board shows, and the factor each is folded from. All
# of them come from ONE fetch of 1-minute bars: separate fetches would let the
# rows describe different instants and disagree for a reason that has nothing
# to do with the market.
#
# The slowest one sets how much history a feed has to supply. A 10-minute ADX
# needs 29 ten-minute bars, so roughly 290 minutes of coverage -- which is why
# aggregate keeps interior buckets that are missing a minute rather than
# discarding them.
TIMEFRAMES = {"m1": 1, "m2": 2, "m5": 5, "m10": 10}


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
                  source: str) -> dict:
    """One board row: 1, 2, 5 and 10-minute DMI over the same bars.

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
    folded = {name: (indicators.aggregate(bars, factor) if factor > 1 else bars)
              for name, factor in TIMEFRAMES.items()}
    readings = {name: with_slope(series) for name, series in folded.items()}

    m1_side = (readings["m1"] or {}).get("side")
    m2_side = (readings["m2"] or {}).get("side")
    # A signal only when the two fast timeframes agree. Disagreement is
    # reported as "mixed" rather than resolved in favour of the faster one:
    # the point of showing more than one timeframe is that either can be
    # wrong. 5m is reported beside it as confirmation, never folded in --
    # widening what fires a trade is a trading change, not a display one.
    signal = m1_side if (m1_side and m1_side == m2_side) else None

    row = {
        "bot": key,
        "label": label,
        "symbol": symbol,
        "source": source,
        "last": last_close(bars),
        "signal": signal,
        "direction": signal,
        "m5_confirms": (bool(signal)
                        and (readings["m5"] or {}).get("side") == signal),
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
