"""Signal blocks — fresh, composable boolean conditions (NOT reused from the
repo's existing signal stack).

Each block is a per-bar boolean; the research runner combines them into
2-and-3-way "Super-Signal" composites per direction. Blocks fire on the CLOSE
of a bar; the backtest always enters at the NEXT bar's open (no lookahead).

GEX_NOTE: gex_pos/gex_neg read features.gex_bias, which is neutral (0) until a
real gamma-exposure feed is wired into features.build(). They are excluded
from the grid while neutral so they can't fake accuracy.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _near(a: pd.Series, level: pd.Series, atr: pd.Series, k: float = 0.5):
    return (a - level).abs() <= k * atr


def blocks(d: pd.DataFrame) -> dict[str, dict[str, pd.Series]]:
    c, o, h, l = d["Close"], d["Open"], d["High"], d["Low"]
    atr = d["atr"]

    bull = {
        # flow / value acceptance
        "vwap_reclaim":  (c > d["vwap"]) & (c.shift(1) <= d["vwap"].shift(1)),
        "above_vwap":    c > d["vwap"],
        "poc_reject_up": (l <= d["y_poc"]) & (c > d["y_poc"]),
        "adi_up":        d["adi_slope"] > 0,
        "delta_surge":   (d["delta"] > 0) & (d["delta3"] > 0)
                         & (d["Volume"] > 1.5 * d["vol_med20"]),
        # levels
        "s1_bounce":     (l <= d["s1"]) & (c > d["s1"]),
        "ylow_reclaim":  (l <= d["y_low"]) & (c > d["y_low"]),
        "pm_high_break": (c > d["pm_high"]) & (c.shift(1) <= d["pm_high"]),
        "yhigh_break":   (c > d["y_high"]) & (c.shift(1) <= d["y_high"]),
        "above_pivot":   c > d["pivot"],
        # momentum
        "macd_x_up":     d["macd_x_up"],
        "macd_x_up_neg": d["macd_x_up"] & (d["macd"] < 0),
        "bull_div":      d["bull_div"],
        "hist_turn_up":  (d["macd_hist"] > d["macd_hist"].shift(1))
                         & (d["macd_hist"].shift(1) < d["macd_hist"].shift(2)),
        "strong_close":  (c - l) >= 0.75 * (h - l).replace(0, np.nan),
    }

    bear = {
        "vwap_loss":     (c < d["vwap"]) & (c.shift(1) >= d["vwap"].shift(1)),
        "below_vwap":    c < d["vwap"],
        "poc_reject_dn": (h >= d["y_poc"]) & (c < d["y_poc"]),
        "adi_dn":        d["adi_slope"] < 0,
        "delta_dump":    (d["delta"] < 0) & (d["delta3"] < 0)
                         & (d["Volume"] > 1.5 * d["vol_med20"]),
        "r1_reject":     (h >= d["r1"]) & (c < d["r1"]),
        "yhigh_reject":  (h >= d["y_high"]) & (c < d["y_high"]),
        "pm_low_break":  (c < d["pm_low"]) & (c.shift(1) >= d["pm_low"]),
        "ylow_break":    (c < d["y_low"]) & (c.shift(1) >= d["y_low"]),
        "below_pivot":   c < d["pivot"],
        "macd_x_dn":     d["macd_x_dn"],
        "macd_x_dn_pos": d["macd_x_dn"] & (d["macd"] > 0),
        "bear_div":      d["bear_div"],
        "hist_turn_dn":  (d["macd_hist"] < d["macd_hist"].shift(1))
                         & (d["macd_hist"].shift(1) > d["macd_hist"].shift(2)),
        "weak_close":    (h - c) >= 0.75 * (h - l).replace(0, np.nan),
    }

    return {"LONG": {k: v.fillna(False) for k, v in bull.items()},
            "SHORT": {k: v.fillna(False) for k, v in bear.items()}}


def noise_gate(d: pd.DataFrame, k_atr: float, vol_mult: float) -> pd.Series:
    """Noise-candle filter: only bars with real range AND real participation
    may generate entries (kills low-liquidity sideways chop)."""
    return ((d["bar_range"] >= k_atr * d["atr"])
            & (d["Volume"] >= vol_mult * d["vol_med20"])).fillna(False)
