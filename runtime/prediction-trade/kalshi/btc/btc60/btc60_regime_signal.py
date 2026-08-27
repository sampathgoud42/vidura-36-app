#!/usr/bin/env python3
"""
btc60_regime_signal.py — phase-3: engineer the BTC-specific "burst" signal.
===========================================================================
Phase-2 verdict: no static combo holds 80% first-touch (±$100/30min) across
46 days; the best hold 55-65%.  The dominant missing variable is the
VOLATILITY REGIME — when 30-min realized range ≥ $100 is physically common,
directional triggers work; in chop they coin-flip.

This script builds and sweeps a composite "BTC-BURST" signal:

    REGIME  gate : rolling 6-bar ATR-sum (≈ achievable 30-min range) and/or
                   realized-vol percentile must clear a floor.
    TRIGGER      : impulse candidates — mom3>=X, don_break_1h, squeeze_break,
                   range_burst, vol_burst, cusum_k, poc_cross.
    CONFIRM gate : DI dominance / momentum / adx floor (optional).

Scores BOTH metrics over 45 days of 5m bars with weekly folds:
    ftouch : +$100 before −$100 within 30 min   (tradable direction edge)
    reach  : touched +$100 at all within 30 min (user's literal spec)

Output: btc60_regime_signal_report.md (this folder)
"""
from __future__ import annotations

import importlib.util
import itertools
import math
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
from backtest_signals_btc60 import (          # noqa: E402
    HORIZON_BARS, TARGET_USD, outcomes_100, cusum_events, entries_of)
from btc60_validate_ensemble import wilson_lb  # noqa: E402

FETCH_HOURS = 45 * 24
MIN_N = 25            # need real support this time


def main() -> None:
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

    print(f"Fetching BTC-USD 5m for {FETCH_HOURS/24:.0f} days…")
    t38.NOISE_RTH_PCT = 2.5; t38.NOISE_EH_PCT = 2.0; t38.EXTENDED_HOURS = True
    d, _ = t38._build_engine_df(True, hours=FETCH_HOURS, ticker="BTC-USD",
                                closed_only=True)
    span_h = (d.index[-1] - d.index[0]) / pd.Timedelta(hours=1)
    days = span_h / 24
    print(f"  bars: {len(d)} span {d.index[0]} → {d.index[-1]} ({days:.0f}d)")

    (reach_l, ft_l, _), (reach_s, ft_s, _) = outcomes_100(d)
    ft = {"LONG": ft_l, "SHORT": ft_s}
    reach = {"LONG": reach_l, "SHORT": reach_s}

    o, h, l, c = (d[x].to_numpy() for x in ("Open", "High", "Low", "Close"))
    v = d["Volume"].to_numpy(dtype=float)
    atr = d["atr"].to_numpy()
    adx = d["adx"].to_numpy()
    pdi, mdi = d["plus_di"].to_numpy(), d["minus_di"].to_numpy()
    n = len(d)
    cs = pd.Series(c)

    age_h = ((d.index[-1] - d.index) / pd.Timedelta(hours=1)).to_numpy()
    fold_id = (age_h // 168).astype(int)

    # ---- REGIME gates ------------------------------------------------------
    atr6 = pd.Series(atr).rolling(6).sum().to_numpy()      # ~30-min range budget
    rv = cs.pct_change().rolling(12).std()                  # 1h realized vol
    rv_pct = rv.rolling(288 * 3, min_periods=288).rank(pct=True).to_numpy()
    regimes = {
        "none":        np.ones(n, bool),
        "atr6>=100":   atr6 >= 100,
        "atr6>=130":   atr6 >= 130,
        "atr6>=160":   atr6 >= 160,
        "rv>=p50":     rv_pct >= 0.50,
        "rv>=p65":     rv_pct >= 0.65,
        "rv>=p80":     rv_pct >= 0.80,
    }

    # ---- TRIGGERS ----------------------------------------------------------
    body = c - o
    net3 = cs.diff(3).to_numpy()
    net6 = cs.diff(6).to_numpy()
    hi12 = pd.Series(h).rolling(12).max().shift(1).to_numpy()
    lo12 = pd.Series(l).rolling(12).min().shift(1).to_numpy()
    vma = pd.Series(v).rolling(20).mean().to_numpy()
    ma, sd = cs.rolling(20).mean(), cs.rolling(20).std()
    upper, lower = (ma + 2 * sd).to_numpy(), (ma - 2 * sd).to_numpy()
    w_pct = (4 * sd / ma).rolling(288, min_periods=60).rank(pct=True).to_numpy()
    cus = {k: cusum_events(c, k) for k in (1.0, 1.5, 2.0)}
    poc = d["poc"].to_numpy()
    prev_c = np.r_[np.nan, c[:-1]]

    triggers = {
        "mom3_40":   {"LONG": net3 >= 40,  "SHORT": net3 <= -40},
        "mom3_60":   {"LONG": net3 >= 60,  "SHORT": net3 <= -60},
        "mom3_90":   {"LONG": net3 >= 90,  "SHORT": net3 <= -90},
        "mom6_120":  {"LONG": net6 >= 120, "SHORT": net6 <= -120},
        "don_break": {"LONG": c > hi12,    "SHORT": c < lo12},
        "sqz_break": {"LONG": (w_pct < .2) & (c > upper),
                      "SHORT": (w_pct < .2) & (c < lower)},
        "range_burst": {"LONG": body > 1.2 * atr, "SHORT": body < -1.2 * atr},
        "vol_burst": {"LONG": (v > 2 * vma) & (body > .4 * atr),
                      "SHORT": (v > 2 * vma) & (body < -.4 * atr)},
        "cusum_1.0": {"LONG": cus[1.0][0], "SHORT": cus[1.0][1]},
        "cusum_1.5": {"LONG": cus[1.5][0], "SHORT": cus[1.5][1]},
        "cusum_2.0": {"LONG": cus[2.0][0], "SHORT": cus[2.0][1]},
        "poc_cross": {"LONG": (prev_c <= poc) & (c > poc),
                      "SHORT": (prev_c >= poc) & (c < poc)},
    }

    # ---- CONFIRM gates -----------------------------------------------------
    confirms = {
        "none":    {"LONG": np.ones(n, bool), "SHORT": np.ones(n, bool)},
        "di_dom":  {"LONG": pdi > mdi, "SHORT": mdi > pdi},
        "mom":     {"LONG": d["mom_up"].to_numpy().astype(bool),
                    "SHORT": d["mom_dn"].to_numpy().astype(bool)},
        "adx20":   {"LONG": np.nan_to_num(adx) > 20,
                    "SHORT": np.nan_to_num(adx) > 20},
        "adx25":   {"LONG": np.nan_to_num(adx) > 25,
                    "SHORT": np.nan_to_num(adx) > 25},
        "di+adx20": {"LONG": (pdi > mdi) & (np.nan_to_num(adx) > 20),
                     "SHORT": (mdi > pdi) & (np.nan_to_num(adx) > 20)},
    }

    def eval_one(mask, direction):
        idx = entries_of(mask)
        r = ft[direction][idx]
        res = np.isin(r, ("win", "loss"))
        wins, tot = int((r[res] == "win").sum()), int(res.sum())
        if tot == 0:
            return None
        rc = reach[direction][idx]
        pf = {}
        for f in np.unique(fold_id[idx]):
            ii = idx[fold_id[idx] == f]
            rr = ft[direction][ii]
            rs = np.isin(rr, ("win", "loss"))
            pf[int(f)] = (int((rr[rs] == "win").sum()), int(rs.sum()))
        worst = min((w / t for w, t in pf.values() if t >= 3), default=np.nan)
        return dict(n=tot, acc=wins / tot * 100, lb=wilson_lb(wins, tot),
                    reach=float(rc.mean() * 100),
                    worst=worst * 100 if worst == worst else np.nan,
                    per_day=len(idx) / days,
                    folds=" ".join(f"w{f}:{w}/{t}" for f, (w, t) in sorted(pf.items())))

    rows = []
    for rg_name, rg in regimes.items():
        for tr_name, tr in triggers.items():
            for cf_name, cf in confirms.items():
                for direction in ("LONG", "SHORT"):
                    mask = rg & tr[direction] & cf[direction]
                    st = eval_one(mask, direction)
                    if st is None or st["n"] < MIN_N:
                        continue
                    rows.append({"direction": direction, "regime": rg_name,
                                 "trigger": tr_name, "confirm": cf_name, **st})

    df = pd.DataFrame(rows)
    df["acc"] = df["acc"].round(1); df["lb"] = df["lb"].round(1)
    df["reach"] = df["reach"].round(1); df["worst"] = df["worst"].round(1)
    df["per_day"] = df["per_day"].round(2)
    df = df.sort_values(["lb", "n"], ascending=[False, False])

    rep = [
        f"# BTC-BURST regime-gated signal sweep — ±${TARGET_USD:.0f}/"
        f"{HORIZON_BARS*5}min, {days:.0f} days 5m",
        f"- bars {len(d)}, {d.index[0]} → {d.index[-1]}",
        "- acc = first-touch accuracy; lb = Wilson 95% lower bound; reach = "
        "touched +$100 at all; worst = worst weekly fold (≥3 resolved)\n",
        "## Regime-only baselines (trigger=any bar in regime)",
    ]
    for rg_name, rg in regimes.items():
        for direction in ("LONG",):
            idx = np.nonzero(rg)[0]
            r = ft[direction][idx]; res = np.isin(r, ("win", "loss"))
            if res.sum() == 0: continue
            acc = (r[res] == "win").mean() * 100
            rc = reach[direction][idx].mean() * 100
            rep.append(f"- {rg_name:<11} LONG ftouch {acc:.1f}%  reach {rc:.1f}%  "
                       f"(bars {rg.sum()})")

    rep.append("\n## Top 40 by Wilson lower bound\n")
    rep.append(df.head(40).to_string(index=False))
    rep.append("\n## Top 25 by REACH (user-spec metric), n≥25, reach≥70\n")
    hot = df[df["reach"] >= 70].sort_values(["reach", "n"], ascending=[False, False])
    rep.append(hot.head(25).to_string(index=False) if not hot.empty else "_(none)_")

    out = _HERE / "btc60_regime_signal_report.md"
    out.write_text("\n".join(rep), encoding="utf-8")
    print(f"report → {out}")
    print(df.head(25).to_string(index=False))


if __name__ == "__main__":
    main()
