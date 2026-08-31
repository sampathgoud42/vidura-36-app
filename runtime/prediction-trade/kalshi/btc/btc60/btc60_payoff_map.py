#!/usr/bin/env python3
"""
btc60_payoff_map.py — phase-4: map surviving signals to Kalshi payoff space.
============================================================================
Phase-2/3 verdict: best honest directional edge is 55-64% first-touch at
±$100/30min.  A Kalshi strategy can print money from that edge IF the payoff
is asymmetric (buy near-the-money ~35-50c contracts in signal direction).

For each SURVIVOR signal this script measures, over 45 days of 5m bars:
  fwd30_mean/med : signed forward 30-min move in signal direction (info content)
  ft100_100      : +100 before -100 (symmetric)          — reference
  ft100_50       : +100 before -50  (2:1 asym, RR)       — "buy 35c, sell 70c"
  ft80_40        : +80  before -40  (2:1 asym, tighter)
  ft150_75       : +150 before -75  (2:1 asym, wider)
  timeout%       : neither barrier in 30 min (time-stop exits, ~flat)
  per-fold weekly consistency for ft100_50

EV per $1 Kalshi contract bought at price p with win->q_win, loss->q_loss
value is left for the strategy doc; here we produce the raw probabilities.

Output: btc60_payoff_map.md (this folder)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent

def _main_root(p: Path) -> Path:
    parts = p.parts
    for i, part in enumerate(parts[:-1]):
        if part.lower() == ".claude" and parts[i + 1].lower() == "worktrees":
            return Path(*parts[:i])
    return p

_REPO = _main_root(_HERE.parents[3])
_ST = _REPO / "stock-trade"
sys.path.insert(0, str(_ST))
_spec = importlib.util.spec_from_file_location("t38", _ST / "38trades_signals.py")
t38 = importlib.util.module_from_spec(_spec)
sys.modules["t38"] = t38
_spec.loader.exec_module(t38)

sys.path.insert(0, str(_HERE))
from backtest_signals_btc60 import cusum_events, entries_of, K_CONF, ENGINE_SIGS  # noqa: E402
from btc60_validate_ensemble import wilson_lb  # noqa: E402

FETCH_HOURS = 45 * 24
HORIZON = 6


def first_touch(idx, high, low, close, up, dn, horizon=HORIZON):
    """per-entry: 'win' if +up before -dn, 'loss' if -dn first, 'open' else."""
    out = np.empty(idx.size, object)
    for k, i in enumerate(idx):
        lt, ls = close[i] + up, close[i] - dn
        r = None
        for j in range(i + 1, min(i + 1 + horizon, len(close))):
            hit_up, hit_dn = high[j] >= lt, low[j] <= ls
            if hit_up or hit_dn:
                r = "loss" if hit_dn else "win"     # same-bar tie = loss
                break
        out[k] = r or "open"
    return out


def main() -> None:
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

    print(f"Fetching BTC-USD 5m ({FETCH_HOURS/24:.0f}d)…")
    t38.NOISE_RTH_PCT = 2.5; t38.NOISE_EH_PCT = 2.0; t38.EXTENDED_HOURS = True
    d, _ = t38._build_engine_df(True, hours=FETCH_HOURS, ticker="BTC-USD",
                                closed_only=True)
    days = (d.index[-1] - d.index[0]) / pd.Timedelta(days=1)
    print(f"  bars {len(d)}  {d.index[0]} → {d.index[-1]}")

    o, h, l, c = (d[x].to_numpy() for x in ("Open", "High", "Low", "Close"))
    v = d["Volume"].to_numpy(float)
    atr = d["atr"].to_numpy(); adx = d["adx"].to_numpy()
    pdi, mdi = d["plus_di"].to_numpy(), d["minus_di"].to_numpy()
    poc = d["poc"].to_numpy()
    n = len(d)
    cs = pd.Series(c)
    prev_c = np.r_[np.nan, c[:-1]]
    net3 = cs.diff(3).to_numpy()
    ma, sd = cs.rolling(20).mean(), cs.rolling(20).std()
    upper, lower = (ma + 2 * sd).to_numpy(), (ma - 2 * sd).to_numpy()
    w_pct = (4 * sd / ma).rolling(288, min_periods=60).rank(pct=True).to_numpy()
    cb15, cs15 = cusum_events(c, 1.5)
    mom_up = d["mom_up"].to_numpy().astype(bool)
    mom_dn = d["mom_dn"].to_numpy().astype(bool)
    near_res = d["near_res"].to_numpy().astype(bool)
    fwd6 = np.r_[c[6:], [np.nan] * 6] - c        # forward 30-min net move

    def roll(colL, colS):
        fl = pd.Series(d[colL].to_numpy().astype(bool)).rolling(
            K_CONF, min_periods=1).max().to_numpy().astype(bool)
        fs = pd.Series(d[colS].to_numpy().astype(bool)).rolling(
            K_CONF, min_periods=1).max().to_numpy().astype(bool)
        return fl, fs

    adxL, adxS = roll(*ENGINE_SIGS["adx_di_cross"])
    vidL, vidS = roll(*ENGINE_SIGS["vidya_dmi"])
    adx20 = np.nan_to_num(adx) > 20
    adx30 = np.nan_to_num(adx) > 30
    adx275 = np.nan_to_num(adx) > 27.5

    SURVIVORS = {
        ("SHORT", "sqz_break+di_dom"): (w_pct < .2) & (c < lower) & (mdi > pdi),
        ("SHORT", "mom3_60+poc_cross"): (net3 <= -60) & (prev_c >= poc) & (c < poc),
        ("SHORT", "mom3_60+poc_cross+near_lvl"):
            (net3 <= -60) & (prev_c >= poc) & (c < poc) & near_res,
        ("LONG", "adx_di_cross+momentum"): adxL & mom_up,
        ("LONG", "adx_di_cross+momentum+adx20"): adxL & mom_up & adx20,
        ("LONG", "poc_cross+adx30"): (prev_c <= poc) & (c > poc) & adx30,
        ("SHORT", "poc_cross+adx27.5"): (prev_c >= poc) & (c < poc) & adx275,
        ("LONG", "vidya_dmi+cusum1.5"): vidL & pd.Series(cb15).rolling(
            K_CONF, min_periods=1).max().to_numpy().astype(bool),
        ("SHORT", "sqz_break"): (w_pct < .2) & (c < lower),
        ("LONG", "sqz_break"): (w_pct < .2) & (c > upper),
    }

    age_h = ((d.index[-1] - d.index) / pd.Timedelta(hours=1)).to_numpy()
    fold_id = (age_h // 168).astype(int)

    BAR = [("ft100_100", 100, 100), ("ft100_50", 100, 50),
           ("ft80_40", 80, 40), ("ft150_75", 150, 75)]

    rows = []
    for (direction, name), mask in SURVIVORS.items():
        mask = np.asarray(mask, bool) & ~np.isnan(prev_c)
        idx = entries_of(mask)
        if idx.size < 15: continue
        sgn = 1 if direction == "LONG" else -1
        fwd = sgn * fwd6[idx]; fwd = fwd[~np.isnan(fwd)]
        row = {"direction": direction, "signal": name, "n": idx.size,
               "per_day": round(idx.size / days, 2),
               "fwd30_mean": round(float(np.mean(fwd)), 1),
               "fwd30_med": round(float(np.median(fwd)), 1)}
        for bn, up, dn in BAR:
            if direction == "LONG":
                ft = first_touch(idx, h, l, c, up, dn)
            else:
                # mirror the tape: SHORT win = -up touched before +dn
                ft = first_touch(idx, -l, -h, -c, up, dn)
            res = np.isin(ft, ("win", "loss"))
            wins = (ft[res] == "win").sum()
            row[bn] = round(wins / res.sum() * 100, 1) if res.sum() else np.nan
            if bn == "ft100_50":
                row["timeout%"] = round((ft == "open").mean() * 100, 1)
                row["lb_100_50"] = round(wilson_lb(int(wins), int(res.sum())), 1)
                pf = {}
                for f in np.unique(fold_id[idx]):
                    ii = np.nonzero(fold_id[idx] == f)[0]
                    rr = ft[ii]; rs = np.isin(rr, ("win", "loss"))
                    if rs.sum():
                        pf[int(f)] = f"{(rr[rs]=='win').sum()}/{rs.sum()}"
                row["folds_100_50"] = " ".join(f"w{k}:{v}" for k, v in sorted(pf.items()))
        rows.append(row)

    df = pd.DataFrame(rows).sort_values("ft100_50", ascending=False)
    rep = [
        f"# Kalshi payoff map — surviving signals, {days:.0f} days BTC-USD 5m",
        f"- bars {len(d)}, {d.index[0]} → {d.index[-1]}",
        "- fwd30 = signed forward 30-min move in signal direction (info content)",
        "- ftX_Y = first-touch +X before −Y within 30 min (%)  — ft100_50 is the",
        "  2:1 asymmetric barrier that maps to 'buy ~35c near-money, sell ~70c'",
        "- timeout% = neither barrier (time-stop, ≈ scratch)\n",
        df.to_string(index=False),
        "\n## EV illustration (per contract, ft100_50 barrier)",
        "buy at 35c: EV = p*0.65 − (1−p)*0.35 − fees  → breakeven p ≈ 36%",
        "buy at 45c: EV = p*0.55 − (1−p)*0.45 − fees  → breakeven p ≈ 46%",
    ]
    out = _HERE / "btc60_payoff_map.md"
    out.write_text("\n".join(rep), encoding="utf-8")
    print(f"report → {out}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
