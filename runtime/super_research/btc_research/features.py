"""Feature engineering — every input the research brief calls for, built fresh
(no reuse of the repo's existing signal stack).

Given raw 5m OHLCV (CST, incl. extended hours) produces a single frame with:
  levels   : y_high, y_low, y_close, pm_high, pm_low, pivot P/S1/S2/R1/R2
  flow     : session VWAP, prior-day POC (volume profile), ADI (Chaikin A/D),
             per-bar volume delta (intrabar-position proxy) + rolling delta
  momentum : MACD line/signal/hist, bullish & bearish crossovers, divergence
             proxies, ATR(14)
  session  : rth flag, entry-window flag, bar range

GEX / options flow: no free historical gamma-exposure source exists, so the
pipeline exposes a neutral `gex_bias` column (0) as the documented hook — wire
a GEX feed in and the signal blocks pick it up (see signals.GEX_NOTE).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config as C


def _atr(df: pd.DataFrame, n: int) -> pd.Series:
    pc = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(),
                    (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _macd(close: pd.Series):
    fast = close.ewm(span=C.MACD_FAST, adjust=False).mean()
    slow = close.ewm(span=C.MACD_SLOW, adjust=False).mean()
    line = fast - slow
    sig = line.ewm(span=C.MACD_SIG, adjust=False).mean()
    return line, sig, line - sig


def _day_poc(day: pd.DataFrame) -> float:
    """Point of Control: price bin holding the most traded volume."""
    if day.empty:
        return np.nan
    mid = (day["High"] + day["Low"]) / 2
    bins = (mid / C.POC_BIN).round() * C.POC_BIN
    vp = day["Volume"].groupby(bins).sum()
    return float(vp.idxmax()) if len(vp) else np.nan


def build(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    t = d.index
    d["date"] = t.date
    tod = pd.Series([x.time() for x in t], index=t)
    d["rth"] = (tod >= C.RTH_OPEN) & (tod < C.RTH_CLOSE)
    # crypto: "pre-market" = the overnight range 00:00 → 09:00 CST
    d["premkt"] = (tod >= C.PREMARKET_OPEN) & (tod < getattr(C, "PM_END", C.RTH_OPEN))

    # ── per-day levels from the PRIOR session ────────────────────────────────
    rth = d[d["rth"]]
    daily = rth.groupby("date").agg(
        day_high=("High", "max"), day_low=("Low", "min"), day_close=("Close", "last"))
    daily["poc"] = [ _day_poc(rth[rth["date"] == dt]) for dt in daily.index ]
    prior = daily.shift(1)
    prior.columns = ["y_high", "y_low", "y_close", "y_poc"]
    # classic floor pivots off yesterday's H/L/C
    P = (prior["y_high"] + prior["y_low"] + prior["y_close"]) / 3
    prior["pivot"] = P
    prior["r1"] = 2 * P - prior["y_low"]
    prior["s1"] = 2 * P - prior["y_high"]
    prior["r2"] = P + (prior["y_high"] - prior["y_low"])
    prior["s2"] = P - (prior["y_high"] - prior["y_low"])

    pm = d[d["premkt"]].groupby("date").agg(pm_high=("High", "max"), pm_low=("Low", "min"))

    d = d.join(prior, on="date").join(pm, on="date")

    # ── volume & flow ────────────────────────────────────────────────────────
    tp = (d["High"] + d["Low"] + d["Close"]) / 3
    pv = (tp * d["Volume"]).where(d["rth"], 0.0)
    vv = d["Volume"].where(d["rth"], 0.0)
    d["vwap"] = pv.groupby(d["date"]).cumsum() / vv.groupby(d["date"]).cumsum().replace(0, np.nan)

    rng = (d["High"] - d["Low"]).replace(0, np.nan)
    mfm = ((d["Close"] - d["Low"]) - (d["High"] - d["Close"])) / rng   # money-flow multiplier
    d["delta"] = (mfm * d["Volume"]).fillna(0.0)                        # per-bar volume delta proxy
    d["delta3"] = d["delta"].rolling(3).sum()
    d["adi"] = d["delta"].cumsum()                                      # Chaikin Acc/Dist line
    d["adi_slope"] = d["adi"] - d["adi"].shift(3)
    d["vol_med20"] = d["Volume"].rolling(20).median()

    # ── momentum ─────────────────────────────────────────────────────────────
    line, sig, hist = _macd(d["Close"])
    d["macd"], d["macd_sig"], d["macd_hist"] = line, sig, hist
    d["macd_x_up"] = (line > sig) & (line.shift(1) <= sig.shift(1))
    d["macd_x_dn"] = (line < sig) & (line.shift(1) >= sig.shift(1))
    lb = C.DIV_LOOKBACK
    d["bull_div"] = (d["Close"] <= d["Close"].rolling(lb).min()) & (line > line.rolling(lb).min())
    d["bear_div"] = (d["Close"] >= d["Close"].rolling(lb).max()) & (line < line.rolling(lb).max())

    d["atr"] = _atr(d, C.ATR_LEN)
    d["bar_range"] = d["High"] - d["Low"]

    # ── derivatives hook (optional per brief) ────────────────────────────────
    d["gex_bias"] = 0.0   # neutral until a real GEX feed is wired in

    return d
