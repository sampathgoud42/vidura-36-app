#!/usr/bin/env python3
"""
btc60_timebox_study.py — phase-5: WHEN does the committee actually work?
========================================================================
Scores the validated committee members (btc60_bot_trsategy.md §4) by
TIME-OF-DAY over 46 days of BTC-USD 5m candles:

  1. Market rhythm: per-UTC-hour median volume, median 30-min range,
     and the unconditional ±$100/30min first-touch + reach rates.
  2. Committee accuracy per 3-hour timebox (per member and pooled).
  3. The best/worst timebox sets and the EV uplift from trading only
     inside the good boxes (with a fold check so it isn't week-luck).

Output: btc60_timebox_report.md (this folder)
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
from backtest_signals_btc60 import (   # noqa: E402
    outcomes_100, cusum_events, entries_of, K_CONF, ENGINE_SIGS)
from btc60_validate_ensemble import wilson_lb  # noqa: E402

FETCH_HOURS = 45 * 24
BOX_H = 3                     # timebox width in hours (8 boxes/day)


def main() -> None:
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

    print(f"Fetching BTC-USD 5m ({FETCH_HOURS/24:.0f}d)…")
    t38.NOISE_RTH_PCT = 2.5; t38.NOISE_EH_PCT = 2.0; t38.EXTENDED_HOURS = True
    d, _ = t38._build_engine_df(True, hours=FETCH_HOURS, ticker="BTC-USD",
                                closed_only=True)
    days = (d.index[-1] - d.index[0]) / pd.Timedelta(days=1)
    print(f"  bars {len(d)}  {d.index[0]} → {d.index[-1]}")

    (reach_l, ft_l, _), (reach_s, ft_s, _) = outcomes_100(d)
    ft = {"LONG": ft_l, "SHORT": ft_s}

    o, h, l, c = (d[x].to_numpy() for x in ("Open", "High", "Low", "Close"))
    v = d["Volume"].to_numpy(float)
    adx = d["adx"].to_numpy()
    pdi, mdi = d["plus_di"].to_numpy(), d["minus_di"].to_numpy()
    poc = d["poc"].to_numpy()
    n = len(d)
    cs = pd.Series(c)
    prev_c = np.r_[np.nan, c[:-1]]
    net3 = cs.diff(3).to_numpy()
    ma, sd = cs.rolling(20).mean(), cs.rolling(20).std()
    upper, lower = (ma + 2 * sd).to_numpy(), (ma - 2 * sd).to_numpy()
    w_pct = (4 * sd / ma).rolling(288, min_periods=60).rank(pct=True).to_numpy()
    mom_up = d["mom_up"].to_numpy().astype(bool)
    mom_dn = d["mom_dn"].to_numpy().astype(bool)
    near_res = d["near_res"].to_numpy().astype(bool)
    adx20 = np.nan_to_num(adx) > 20
    adx275 = np.nan_to_num(adx) > 27.5
    adx30 = np.nan_to_num(adx) > 30

    def roll(colL, colS):
        fl = pd.Series(d[colL].to_numpy().astype(bool)).rolling(
            K_CONF, min_periods=1).max().to_numpy().astype(bool)
        fs = pd.Series(d[colS].to_numpy().astype(bool)).rolling(
            K_CONF, min_periods=1).max().to_numpy().astype(bool)
        return fl, fs

    adxL, _ = roll(*ENGINE_SIGS["adx_di_cross"])

    COMMITTEE = {
        ("SHORT", "S1 sqz_break+di_dom"):
            (w_pct < .2) & (c < lower) & (mdi > pdi),
        ("LONG", "S2 poc_cross+adx30"):
            (prev_c <= poc) & (c > poc) & adx30,
        ("LONG", "S3 adx_di_cross+mom+adx20"):
            adxL & mom_up & adx20,
        ("SHORT", "S4 mom3_60+poc_cross"):
            (net3 <= -60) & (prev_c >= poc) & (c < poc),
        ("SHORT", "S5 poc_cross+adx27.5"):
            (prev_c >= poc) & (c < poc) & adx275,
    }

    hour = d.index.hour.to_numpy()
    box = (hour // BOX_H).astype(int)                    # 0..7 (UTC)
    age_h = ((d.index[-1] - d.index) / pd.Timedelta(hours=1)).to_numpy()
    fold_id = (age_h // 168).astype(int)
    rng30 = (pd.Series(h).rolling(6).max() - pd.Series(l).rolling(6).min()).to_numpy()

    rep = [
        f"# BTC-60 timebox study — {days:.0f} days 5m, boxes of {BOX_H}h (UTC)",
        f"- bars {len(d)}, {d.index[0]} → {d.index[-1]}",
        "- CST = UTC−5 (CDT).  Box b covers UTC [3b, 3b+3).\n",
        "## 1. Market rhythm by UTC hour",
        "hour | med volume | med 30-min range $ | uncond ft-LONG % | reach-any %",
    ]
    for hh in range(24):
        m = hour == hh
        i = np.nonzero(m)[0]
        r = ft_l[i]; res = np.isin(r, ("win", "loss"))
        acc = (r[res] == "win").mean() * 100 if res.any() else np.nan
        reach_any = (reach_l[i] | reach_s[i]).mean() * 100
        rep.append(f"{hh:02d}   | {np.median(v[m]):10.1f} | "
                   f"{np.nanmedian(rng30[m]):8.0f} | {acc:5.1f} | {reach_any:5.1f}")

    # ---- committee by timebox ----------------------------------------------
    rep.append(f"\n## 2. Committee accuracy per {BOX_H}h timebox (ft ±$100/30min)\n")
    rep.append("member | box(UTC) | n | acc% | wilsonLB")
    box_rows = []
    pooled = {b: [0, 0] for b in range(24 // BOX_H)}      # wins, resolved
    for (direction, name), mask in COMMITTEE.items():
        mask = np.asarray(mask, bool) & ~np.isnan(prev_c)
        idx = entries_of(mask)
        for b in range(24 // BOX_H):
            ii = idx[box[idx] == b]
            if ii.size == 0: continue
            r = ft[direction][ii]; res = np.isin(r, ("win", "loss"))
            wins, tot = int((r[res] == "win").sum()), int(res.sum())
            if tot == 0: continue
            pooled[b][0] += wins; pooled[b][1] += tot
            box_rows.append((name, b, tot, wins))
            rep.append(f"{name:28s} | {b*BOX_H:02d}-{b*BOX_H+BOX_H:02d} | "
                       f"{tot:3d} | {wins/tot*100:5.1f} | "
                       f"{wilson_lb(wins, tot):5.1f}")

    rep.append("\n### Pooled committee per timebox")
    rep.append("box(UTC) | n | acc% | wilsonLB")
    box_stats = {}
    for b, (w, t) in sorted(pooled.items()):
        if t == 0: continue
        box_stats[b] = (w, t, w / t * 100)
        rep.append(f"{b*BOX_H:02d}-{b*BOX_H+BOX_H:02d} | {t:3d} | "
                   f"{w/t*100:5.1f} | {wilson_lb(w, t):5.1f}")

    # ---- good-box gate ------------------------------------------------------
    # good = pooled acc >= 58% with n >= 25
    good = [b for b, (w, t, a) in box_stats.items() if a >= 58 and t >= 25]
    good_mask = np.isin(box, good)
    rep.append(f"\n## 3. Good-box gate: boxes {sorted(good)} "
               f"(UTC {[f'{b*BOX_H:02d}-{b*BOX_H+BOX_H:02d}' for b in sorted(good)]})")

    def pooled_eval(gate: np.ndarray | None):
        w = t = 0
        per_fold: dict[int, list[int]] = {}
        n_entries = 0
        for (direction, name), mask in COMMITTEE.items():
            mask = np.asarray(mask, bool) & ~np.isnan(prev_c)
            if gate is not None:
                mask = mask & gate
            idx = entries_of(mask)
            n_entries += idx.size
            r = ft[direction][idx]; res = np.isin(r, ("win", "loss"))
            w += int((r[res] == "win").sum()); t += int(res.sum())
            for f in np.unique(fold_id[idx]):
                ii = idx[fold_id[idx] == f]
                rr = ft[direction][ii]; rs = np.isin(rr, ("win", "loss"))
                pf = per_fold.setdefault(int(f), [0, 0])
                pf[0] += int((rr[rs] == "win").sum()); pf[1] += int(rs.sum())
        folds = " ".join(f"w{f}:{a}/{b}" for f, (a, b) in sorted(per_fold.items()))
        return w, t, n_entries, folds

    for label, gate in (("ALL hours", None), ("GOOD boxes only", good_mask),
                        ("BAD boxes only", ~good_mask)):
        w, t, ne, folds = pooled_eval(gate)
        acc = w / t * 100 if t else np.nan
        ev = (acc / 100 * 20 - (1 - acc / 100) * 16.5) if t else np.nan
        rep.append(f"- **{label}**: n={t}, acc {acc:.1f}% "
                   f"(LB {wilson_lb(w, t):.1f}%), {ne/days:.1f} fires/day, "
                   f"EV/50c-contract ≈ {ev:+.1f}c — folds {folds}")

    out = _HERE / "btc60_timebox_report.md"
    out.write_text("\n".join(rep), encoding="utf-8")
    print(f"report → {out}")
    for line in rep[-12:]:
        print(line)


if __name__ == "__main__":
    main()
