"""Trade engine — spy_research rules with a PERCENT target/stop.

  * entry  : next bar OPEN after the signal bar close (no lookahead)
  * TP     : ±0.30% in the trade direction within 12 bars (60 min)
  * SL     : 0.30% adverse, monitored ONLY the first 6 bars (30 min)
  * time   : flat at bar-48 close if TP never hit; outcomes truncate
           at TP_DEADLINE (14:35 CST, 25 min before close)
  * tie    : same-bar TP+SL -> counted as a stop (conservative)

pnl is expressed in PERCENT of entry.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config as C

# TP must hit before this time (desk rule: 25 min before close)
DEADLINE = getattr(C, "TP_DEADLINE", C.RTH_CLOSE)


def precompute_outcomes(d: pd.DataFrame, direction: str) -> pd.DataFrame:
    o = d["Open"].to_numpy(float)
    h = d["High"].to_numpy(float)
    l = d["Low"].to_numpy(float)
    c = d["Close"].to_numpy(float)
    dates = d["date"].to_numpy()
    times = d.index
    n = len(d)
    sgn = 1.0 if direction == "LONG" else -1.0

    result = np.full(n, "", dtype=object)
    pnl = np.full(n, np.nan)      # percent of entry
    hold = np.full(n, np.nan)

    for i in range(n - 1):
        e = i + 1
        if dates[e] != dates[i] or not (times[e].time() < DEADLINE):
            continue
        entry = o[e]
        if not np.isfinite(entry) or entry <= 0:
            continue
        tp = entry * (1 + sgn * C.TP_PCT / 100)
        sl = entry * (1 - sgn * C.SL_PCT / 100)
        res, p, hb = "scratch", np.nan, np.nan
        last_j = e - 1
        for j in range(e, min(e + C.TP_BARS, n)):
            if dates[j] != dates[e] or not (times[j].time() < DEADLINE):
                break
            last_j = j
            k = j - e + 1
            hit_tp = h[j] >= tp if sgn > 0 else l[j] <= tp
            hit_sl = (l[j] <= sl if sgn > 0 else h[j] >= sl) and k <= C.SL_BARS
            if hit_tp and hit_sl:
                res, p, hb = "stop", -C.SL_PCT, k
                break
            if hit_sl:
                res, p, hb = "stop", -C.SL_PCT, k
                break
            if hit_tp:
                res, p, hb = "target", C.TP_PCT, k
                break
        if res == "scratch":
            if last_j < e:
                continue
            p = sgn * (c[last_j] - entry) / entry * 100
            hb = last_j - e + 1
        result[i], pnl[i], hold[i] = res, p, hb

    return pd.DataFrame({"result": result, "pnl": pnl, "hold": hold}, index=d.index)


def metrics(mask: pd.Series, out: pd.DataFrame, n_days: int) -> dict:
    """Performance of taking every entry where mask is True (pnl in %)."""
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
        "net_pct": round(float(sel["pnl"].sum()), 2),
        "max_drawdown_pct": round(max_dd, 2),
        "avg_hold_min": round(float(sel["hold"].mean()) * 5, 1),
    }
