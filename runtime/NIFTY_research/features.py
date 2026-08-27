"""Feature engineering — the base spy_research inputs PLUS custom price+volume
levels/flow features for the Indian-index 0.30%/4h hunt.

Base:      y-levels, floor pivots, VWAP, prior-day POC, ADI, volume-delta, MACD,
           divergence proxies, ATR, session flags.
Custom:    opening range (ORB), VWAP σ-bands, relative volume (rvol), cumulative
           volume delta (CVD) + slope, RSI(14), consecutive-bar / rising-volume
           momentum flags, VWAP distance in ATR.

All custom features use REAL volume (the ETF proxy NIFTYBEES/BANKBEES carries
volume; the raw NSE index does not).
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
    d["premkt"] = (tod >= C.PREMARKET_OPEN) & (tod < C.RTH_OPEN)

    # ── per-day levels from the PRIOR session ────────────────────────────────
    rth = d[d["rth"]]
    daily = rth.groupby("date").agg(
        day_high=("High", "max"), day_low=("Low", "min"), day_close=("Close", "last"))
    daily["poc"] = [_day_poc(rth[rth["date"] == dt]) for dt in daily.index]
    prior = daily.shift(1)
    prior.columns = ["y_high", "y_low", "y_close", "y_poc"]
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
    mfm = ((d["Close"] - d["Low"]) - (d["High"] - d["Close"])) / rng
    d["delta"] = (mfm * d["Volume"]).fillna(0.0)
    d["delta3"] = d["delta"].rolling(3).sum()
    d["adi"] = d["delta"].cumsum()
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

    # ── CUSTOM: opening range (first ORB_MIN of the session) ─────────────────
    # bar size inferred from index spacing so 15m/30m resampled frames get the
    # right ORB bar count (5m frames behave exactly as before)
    bar_min = 5
    if len(t) > 1:
        step = pd.Series(t[1:] - t[:-1]).dt.total_seconds().mode()
        if len(step) and step.iloc[0] > 0:
            bar_min = max(1, int(step.iloc[0] // 60))
    orb_bars = max(1, getattr(C, "ORB_MIN", 15) // bar_min)
    head = d[d["rth"]].groupby("date", group_keys=False).head(orb_bars)
    orb = head.groupby("date").agg(orb_high=("High", "max"), orb_low=("Low", "min"))
    d = d.join(orb, on="date")

    # ── CUSTOM: relative volume ──────────────────────────────────────────────
    d["rvol"] = (d["Volume"] / d["vol_med20"]).replace([np.inf, -np.inf], np.nan)
    d["vol_rising"] = (d["Volume"] > d["Volume"].shift(1)) & (d["Volume"].shift(1) > d["Volume"].shift(2))

    # ── CUSTOM: VWAP σ-bands (session cumulative std of typical price vs VWAP) ─
    dev = (tp - d["vwap"]).where(d["rth"], np.nan)
    dev2 = (dev ** 2).groupby(d["date"]).cumsum()
    cnt = d["rth"].astype(float).groupby(d["date"]).cumsum().replace(0, np.nan)
    vstd = np.sqrt(dev2 / cnt)
    band = getattr(C, "VWAP_BAND", 1.5)
    d["vwap_up"] = d["vwap"] + band * vstd
    d["vwap_dn"] = d["vwap"] - band * vstd
    d["vwap_dist_atr"] = (d["Close"] - d["vwap"]) / d["atr"].replace(0, np.nan)

    # ── CUSTOM: cumulative volume delta (signed by bar direction) ─────────────
    sgn = np.sign(d["Close"] - d["Open"]).fillna(0.0)
    d["cvd"] = (sgn * d["Volume"]).where(d["rth"], 0.0).groupby(d["date"]).cumsum()
    d["cvd_slope"] = d["cvd"] - d["cvd"].shift(3)

    # ── CUSTOM: RSI(14) + streak flags ───────────────────────────────────────
    dc = d["Close"].diff()
    gain = dc.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-dc.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    d["rsi"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    c = d["Close"]
    d["up3"] = (c > c.shift(1)) & (c.shift(1) > c.shift(2)) & (c.shift(2) > c.shift(3))
    d["dn3"] = (c < c.shift(1)) & (c.shift(1) < c.shift(2)) & (c.shift(2) < c.shift(3))

    d["gex_bias"] = 0.0
    return d
