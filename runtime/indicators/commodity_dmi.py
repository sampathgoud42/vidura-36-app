"""
commodity_dmi.py — Wilder DMI / DI-dominance signal for commodities.

Ported from the tradier-bot project's ``hot_scan.py`` commodities scanner
(``_wilder``, ``dmi``, ``_commodity_side``, ``_aggregate_2min``): call/put
is decided purely by which of +DI / -DI is bigger, computed independently
on 1-minute bars and on synthesized 2-minute bars (merged consecutive
1-minute bars). A signal only fires when both timeframes agree — that
agreement is the whole confirmation filter, there are no ADX/DI thresholds.

Where tradier-bot reads 1-min bars from Tradier's timesales endpoint, this
version pulls them from Yahoo Finance (GC=F / SI=F / CL=F) via yfinance,
matching the data source already used by ``commodity_score.py`` for these
same three symbols.
"""
from __future__ import annotations

import yfinance as yf

SYMBOLS = {
    "gold15":   "GC=F",
    "silver15": "SI=F",
    "oil15":    "CL=F",
}

DMI_PERIOD = 9
DMI_SLOPE_LB = 3
_MIN_BARS = DMI_PERIOD * 2 + 2


# ── Wilder DMI/ADX (ported verbatim from tradier-bot backend/app/services/hot_scan.py) ──

def _wilder(src: list[float], period: int) -> list[float | None]:
    """Seed with a sum over the first `period`, then decay by 1/period.

    Not a moving average of the last `period` values — Wilder's own smoothing,
    which is what every charting package draws and therefore the only version
    whose numbers match the ones on screen.
    """
    out: list[float | None] = []
    acc = 0.0
    for i, v in enumerate(src):
        if i < period:
            acc += v
            out.append(acc if i == period - 1 else None)
        else:
            acc = acc - acc / period + v
            out.append(acc)
    return out


def dmi(bars: list[dict], period: int = 14, slope_lb: int = 0) -> dict | None:
    """Latest {plus_di, minus_di, adx, dxs, adx_slope} for these bars, or None.

    ``bars`` are dicts with high/low/close. Needs 2*period+2 of them: the ADX
    is an average of DX values that are themselves smoothed, so a short series
    produces a number that is mostly its own seed.
    """
    n = len(bars)
    if n < period * 2 + 2:
        return None

    tr: list[float] = []
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for i in range(1, n):
        h, low = float(bars[i]["high"]), float(bars[i]["low"])
        pc = float(bars[i - 1]["close"])
        ph, pl = float(bars[i - 1]["high"]), float(bars[i - 1]["low"])
        tr.append(max(h - low, abs(h - pc), abs(low - pc)))
        up = h - ph
        down = pl - low
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)

    s_tr = _wilder(tr, period)
    s_p = _wilder(plus_dm, period)
    s_m = _wilder(minus_dm, period)

    plus_di: list[float | None] = []
    minus_di: list[float | None] = []
    dx: list[float | None] = []
    for i in range(len(tr)):
        if s_tr[i] is None or s_tr[i] == 0:
            plus_di.append(None)
            minus_di.append(None)
            dx.append(None)
            continue
        pdi = 100.0 * (s_p[i] / s_tr[i])
        mdi = 100.0 * (s_m[i] / s_tr[i])
        plus_di.append(pdi)
        minus_di.append(mdi)
        total = pdi + mdi
        dx.append(0.0 if total == 0 else 100.0 * (abs(pdi - mdi) / total))

    first = next((i for i, v in enumerate(dx) if v is not None), None)
    if first is None or first + period > len(dx):
        return None
    adx: list[float | None] = [None] * len(dx)
    adx[first + period - 1] = sum(dx[first:first + period]) / period
    for i in range(first + period, len(dx)):
        adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    if plus_di[-1] is None or minus_di[-1] is None or adx[-1] is None:
        return None

    pdi_last = plus_di[-1]
    mdi_last = minus_di[-1]
    total = pdi_last + mdi_last
    dxs = (pdi_last - mdi_last) / total if total > 0 else 0.0

    adx_slope = 0.0
    if slope_lb > 0:
        prior_idx = len(adx) - 1 - slope_lb
        if prior_idx >= 0 and adx[prior_idx] is not None:
            adx_slope = adx[-1] - adx[prior_idx]

    return {
        "plus_di": pdi_last, "minus_di": mdi_last, "adx": adx[-1],
        "dxs": dxs, "adx_slope": adx_slope,
    }


def _commodity_side(reading: dict | None) -> str | None:
    """Call/put based on DI dominance — no gates, just which side is bigger."""
    if reading is None:
        return None
    pdi, mdi = reading["plus_di"], reading["minus_di"]
    if pdi > mdi:
        return "call"
    if mdi > pdi:
        return "put"
    return None


def _aggregate_2min(bars: list[dict]) -> list[dict]:
    """Merge consecutive 1-min bars into 2-min bars."""
    out = []
    i = 0
    while i + 1 < len(bars):
        a, b = bars[i], bars[i + 1]
        out.append({
            "time": a.get("time"),
            "open": a.get("open"),
            "high": max(float(a["high"]), float(b["high"])),
            "low": min(float(a["low"]), float(b["low"])),
            "close": b.get("close"),
            "volume": (a.get("volume") or 0) + (b.get("volume") or 0),
        })
        i += 2
    return out


# ── Yahoo Finance bar fetch ─────────────────────────────────────────────────

def _fetch_1m_bars(symbol: str) -> list[dict]:
    """Last few days of 1-min OHLC bars for ``symbol`` (yfinance caps 1m
    history at ~7 days, so period="5d" stays well inside that limit while
    giving comfortable headroom over the ~20 bars period=9 DMI needs)."""
    df = yf.Ticker(symbol).history(period="5d", interval="1m")
    if df.empty:
        return []
    bars: list[dict] = []
    for ts, row in df.iterrows():
        try:
            bars.append({
                "time": ts.isoformat(),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": float(row.get("Volume") or 0),
            })
        except (TypeError, ValueError):
            continue
    return bars


# ── Public entry point ──────────────────────────────────────────────────────

def score_commodity_dmi(bot_key: str, verbose: bool = False) -> dict:
    """DI-dominance call/put signal for a gold15/silver15/oil15 bot key.

    Returns:
        {"direction": "LONG"|"SHORT"|None, "signal": "call"|"put"|None,
         "m1_side": ..., "m2_side": ..., "m1": {...}|None, "m2": {...}|None,
         "bars_1m": int, "bars_2m": int, "live_price": float}

    ``direction`` is None (skip the trade) unless the 1-min and 2-min DI
    dominance agree — the same multi-timeframe confirmation tradier-bot
    uses before it will call a commodity binary tradable.
    """
    symbol = SYMBOLS.get(bot_key)
    if not symbol:
        return {"direction": None, "signal": None, "m1_side": None, "m2_side": None,
                "m1": None, "m2": None, "bars_1m": 0, "bars_2m": 0, "live_price": 0.0}

    bars_1m = _fetch_1m_bars(symbol)
    bars_2m = _aggregate_2min(bars_1m)
    r1 = dmi(bars_1m, period=DMI_PERIOD, slope_lb=DMI_SLOPE_LB)
    r2 = dmi(bars_2m, period=DMI_PERIOD, slope_lb=DMI_SLOPE_LB)
    m1_side = _commodity_side(r1)
    m2_side = _commodity_side(r2)
    signal = m1_side if (m1_side and m1_side == m2_side) else None
    direction = {"call": "LONG", "put": "SHORT"}.get(signal)
    live_price = bars_1m[-1]["close"] if bars_1m else 0.0

    if verbose:
        def _fmt(r: dict | None) -> str:
            if not r:
                return "n/a"
            return f"+DI={r['plus_di']:.1f} -DI={r['minus_di']:.1f} ADX={r['adx']:.1f}"
        print(f"[dmi] {symbol}: bars={len(bars_1m)}  "
              f"1m[{_fmt(r1)} -> {m1_side}]  2m[{_fmt(r2)} -> {m2_side}]  "
              f"=> {signal or 'NEUTRAL'}")

    return {
        "direction": direction, "signal": signal,
        "m1_side": m1_side, "m2_side": m2_side,
        "m1": r1, "m2": r2,
        "bars_1m": len(bars_1m), "bars_2m": len(bars_2m),
        "live_price": live_price,
    }


if __name__ == "__main__":
    for key in SYMBOLS:
        score_commodity_dmi(key, verbose=True)
