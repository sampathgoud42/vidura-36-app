"""Trade engine + metrics.

Rules (from the research brief):
  * entry  : next bar OPEN after a signal bar close (no lookahead)
  * TP     : +/- 1.0 SPY point in the trade direction, within 12 bars (60 min)
  * SL     : 1.0 point adverse, monitored ONLY for the first 6 bars (30 min)
  * time   : if no TP by bar 12 (and no SL inside the first 6), exit at the
             bar-12 close; positions never carry past the 15:00 CST close
  * same-bar TP+SL touch -> counted as a STOP (conservative)

Outcomes are precomputed once per direction for every bar, so grid-searching
hundreds of composites is just boolean-mask aggregation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config as C


def precompute_outcomes(d: pd.DataFrame, direction: str) -> pd.DataFrame:
    """For every bar i (as a potential SIGNAL bar): entry at open[i+1], then
    walk forward. Returns per-bar result/pnl/hold_bars (NaN where no entry
    is possible)."""
    o = d["Open"].to_numpy(float)
    h = d["High"].to_numpy(float)
    l = d["Low"].to_numpy(float)
    c = d["Close"].to_numpy(float)
    dates = d["date"].to_numpy()
    times = d.index
    n = len(d)
    sgn = 1.0 if direction == "LONG" else -1.0

    result = np.full(n, "", dtype=object)
    pnl = np.full(n, np.nan)
    hold = np.full(n, np.nan)

    for i in range(n - 1):
        e = i + 1                                  # entry bar
        if dates[e] != dates[i]:
            continue                               # signal at day end — no entry
        if not (times[e].time() < C.RTH_CLOSE):
            continue
        entry = o[e]
        tp = entry + sgn * C.TP_POINTS
        sl = entry - sgn * C.SL_POINTS
        res, p, hb = "scratch", np.nan, np.nan
        last_j = e - 1
        for j in range(e, min(e + C.TP_BARS, n)):
            if dates[j] != dates[e] or not (times[j].time() < C.RTH_CLOSE):
                break                              # day ended first
            last_j = j
            k = j - e + 1                          # bars in trade (1-based)
            hit_tp = h[j] >= tp if sgn > 0 else l[j] <= tp
            hit_sl = (l[j] <= sl if sgn > 0 else h[j] >= sl) and k <= C.SL_BARS
            if hit_tp and hit_sl:
                res, p, hb = "stop", -C.SL_POINTS, k      # conservative
                break
            if hit_sl:
                res, p, hb = "stop", -C.SL_POINTS, k
                break
            if hit_tp:
                res, p, hb = "target", C.TP_POINTS, k
                break
        if res == "scratch":
            if last_j < e:
                continue                           # no tradable bars at all
            p = sgn * (c[last_j] - entry)
            hb = last_j - e + 1
        result[i], pnl[i], hold[i] = res, p, hb

    return pd.DataFrame({"result": result, "pnl": pnl, "hold": hold}, index=d.index)


def metrics(mask: pd.Series, out: pd.DataFrame, n_days: int) -> dict:
    """Performance of taking every entry where mask is True."""
    sel = out[mask.to_numpy() & (out["result"] != "").to_numpy()]
    n = len(sel)
    if n == 0:
        return {"trades": 0}
    wins = int((sel["result"] == "target").sum())
    stops = int((sel["result"] == "stop").sum())
    scratch = n - wins - stops
    gross_up = sel.loc[sel["pnl"] > 0, "pnl"].sum()
    gross_dn = -sel.loc[sel["pnl"] < 0, "pnl"].sum()
    equity = sel["pnl"].cumsum()
    max_dd = float((equity.cummax() - equity).max())
    return {
        "trades": n,
        "trades_per_day": round(n / max(n_days, 1), 2),
        "wins": wins, "stops": stops, "scratch": scratch,
        "win_rate": round(wins / n * 100, 1),
        "tp_before_sl": round(wins / max(wins + stops, 1) * 100, 1),
        "profit_factor": round(float(gross_up / gross_dn), 2) if gross_dn > 0 else float("inf"),
        "net_points": round(float(sel["pnl"].sum()), 2),
        "max_drawdown_pts": round(max_dd, 2),
        "avg_hold_min": round(float(sel["hold"].mean()) * 5, 1),
    }
