"""Signal blocks — base spy_research composites PLUS custom price+volume blocks
for the 0.30%/4h Indian-index hunt.

Each block is a per-bar boolean; the research runner combines 2- and 3-way
composites per direction. Blocks fire on the CLOSE of a bar; the backtest enters
at the NEXT bar's open (no lookahead). Custom blocks combine a price event
(ORB break / VWAP reclaim / band bounce / streak) with a volume confirmation
(relative volume, rising volume, or cumulative volume delta).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

RVOL_HI = 1.5   # strong participation
RVOL_MD = 1.2   # above-average participation


def blocks(d: pd.DataFrame) -> dict[str, dict[str, pd.Series]]:
    c, o, h, l = d["Close"], d["Open"], d["High"], d["Low"]
    rvol, cvd_s = d["rvol"], d["cvd_slope"]
    strong = (c - l) >= 0.6 * (h - l).replace(0, np.nan)
    weakc = (h - c) >= 0.6 * (h - l).replace(0, np.nan)

    bull = {
        # ── base flow / value ──
        "vwap_reclaim":  (c > d["vwap"]) & (c.shift(1) <= d["vwap"].shift(1)),
        "above_vwap":    c > d["vwap"],
        "poc_reject_up": (l <= d["y_poc"]) & (c > d["y_poc"]),
        "adi_up":        d["adi_slope"] > 0,
        "delta_surge":   (d["delta"] > 0) & (d["delta3"] > 0) & (d["Volume"] > 1.5 * d["vol_med20"]),
        # ── base levels ──
        "s1_bounce":     (l <= d["s1"]) & (c > d["s1"]),
        "ylow_reclaim":  (l <= d["y_low"]) & (c > d["y_low"]),
        "yhigh_break":   (c > d["y_high"]) & (c.shift(1) <= d["y_high"]),
        "above_pivot":   c > d["pivot"],
        # ── base momentum ──
        "macd_x_up":     d["macd_x_up"],
        "macd_x_up_neg": d["macd_x_up"] & (d["macd"] < 0),
        "hist_turn_up":  (d["macd_hist"] > d["macd_hist"].shift(1)) & (d["macd_hist"].shift(1) < d["macd_hist"].shift(2)),
        "strong_close":  strong,
        # ── CUSTOM price + volume ──
        "orb_break_up":   (c > d["orb_high"]) & (c.shift(1) <= d["orb_high"]),
        "orb_break_up_v": (c > d["orb_high"]) & (c.shift(1) <= d["orb_high"]) & (rvol > RVOL_MD),
        "vwap_reclaim_v": (c > d["vwap"]) & (c.shift(1) <= d["vwap"].shift(1)) & (rvol > RVOL_MD),
        "rvol_thrust_up": (c > o) & (c > d["vwap"]) & (rvol > RVOL_HI) & strong,
        "above_vwap_v":   (c > d["vwap"]) & (rvol > RVOL_HI),
        "vwap_lo_bounce": (l <= d["vwap_dn"]) & (c > d["vwap_dn"]) & (rvol > 1.0),
        "cvd_up":         (cvd_s > 0) & (c > d["vwap"]),
        "cvd_up_v":       (cvd_s > 0) & (c > d["vwap"]) & (rvol > RVOL_MD),
        "mom_ignite_up":  d["up3"] & d["vol_rising"] & (d["macd_hist"] > 0),
        "rsi_thrust_up":  (d["rsi"] > 55) & (d["rsi"].shift(1) <= 55) & (rvol > RVOL_MD),
    }

    bear = {
        "vwap_loss":     (c < d["vwap"]) & (c.shift(1) >= d["vwap"].shift(1)),
        "below_vwap":    c < d["vwap"],
        "poc_reject_dn": (h >= d["y_poc"]) & (c < d["y_poc"]),
        "adi_dn":        d["adi_slope"] < 0,
        "delta_dump":    (d["delta"] < 0) & (d["delta3"] < 0) & (d["Volume"] > 1.5 * d["vol_med20"]),
        "r1_reject":     (h >= d["r1"]) & (c < d["r1"]),
        "yhigh_reject":  (h >= d["y_high"]) & (c < d["y_high"]),
        "ylow_break":    (c < d["y_low"]) & (c.shift(1) >= d["y_low"]),
        "below_pivot":   c < d["pivot"],
        "macd_x_dn":     d["macd_x_dn"],
        "macd_x_dn_pos": d["macd_x_dn"] & (d["macd"] > 0),
        "hist_turn_dn":  (d["macd_hist"] < d["macd_hist"].shift(1)) & (d["macd_hist"].shift(1) > d["macd_hist"].shift(2)),
        "weak_close":    weakc,
        # ── CUSTOM price + volume ──
        "orb_break_dn":   (c < d["orb_low"]) & (c.shift(1) >= d["orb_low"]),
        "orb_break_dn_v": (c < d["orb_low"]) & (c.shift(1) >= d["orb_low"]) & (rvol > RVOL_MD),
        "vwap_loss_v":    (c < d["vwap"]) & (c.shift(1) >= d["vwap"].shift(1)) & (rvol > RVOL_MD),
        "rvol_thrust_dn": (c < o) & (c < d["vwap"]) & (rvol > RVOL_HI) & weakc,
        "below_vwap_v":   (c < d["vwap"]) & (rvol > RVOL_HI),
        "vwap_hi_reject": (h >= d["vwap_up"]) & (c < d["vwap_up"]) & (rvol > 1.0),
        "cvd_dn":         (cvd_s < 0) & (c < d["vwap"]),
        "cvd_dn_v":       (cvd_s < 0) & (c < d["vwap"]) & (rvol > RVOL_MD),
        "mom_ignite_dn":  d["dn3"] & d["vol_rising"] & (d["macd_hist"] < 0),
        "rsi_thrust_dn":  (d["rsi"] < 45) & (d["rsi"].shift(1) >= 45) & (rvol > RVOL_MD),
    }

    return {"LONG": {k: v.fillna(False) for k, v in bull.items()},
            "SHORT": {k: v.fillna(False) for k, v in bear.items()}}


def noise_gate(d: pd.DataFrame, k_atr: float, vol_mult: float) -> pd.Series:
    """Noise-candle filter: real range AND real participation."""
    return ((d["bar_range"] >= k_atr * d["atr"])
            & (d["Volume"] >= vol_mult * d["vol_med20"])).fillna(False)
