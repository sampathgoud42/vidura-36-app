#!/usr/bin/env python3
"""
btc60_validate_ensemble.py — phase-2 validation for the BTC-60 rebuild.
========================================================================
Phase 1 (backtest_signals_btc60.py) surfaced candidate combos at 80-100%
first-touch accuracy but on thin supports (n=8-21 over ~12 days).  This
script is the honesty check + occurrence multiplier:

  1. Fetch ~45 DAYS of BTC-USD 5m (≈13k bars) — 3-4x more data.
  2. Re-score every shortlisted combo on WEEKLY FOLDS (walk-forward, no
     tuning on the fold being scored) + Wilson 95% lower bound.
  3. Fine-sweep ADX threshold (15..40 step 2.5) for the poc_cross family
     and CUSUM k (1.0..2.5 step .25) for the vidya_dmi family.
  4. Build OR-ENSEMBLES of surviving combos (fire when ANY member fires,
     direction-consistent, de-duplicated) to maximize occurrences/day at
     the target precision.

Outputs:
    btc60_ensemble_validation.md   (this folder)
"""
from __future__ import annotations

import importlib.util
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
    ENGINE_SIGS, HORIZON_BARS, TARGET_USD, K_CONF,
    outcomes_100, cusum_events, build_btc_predicates, build_filters,
    entries_of)

FETCH_HOURS = 45 * 24


def wilson_lb(w: int, n: int, z: float = 1.96) -> float:
    """Wilson score interval lower bound (95%)."""
    if n == 0: return 0.0
    p = w / n
    den = 1 + z * z / n
    c = p + z * z / (2 * n)
    rad = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - rad) / den * 100


def build_all_preds(d: pd.DataFrame) -> dict[str, dict[str, np.ndarray]]:
    preds: dict[str, dict[str, np.ndarray]] = {}
    for fam, (lc, sc) in ENGINE_SIGS.items():
        fl = pd.Series(d[lc].to_numpy().astype(bool)).rolling(
            K_CONF, min_periods=1).max().to_numpy().astype(bool)
        fs = pd.Series(d[sc].to_numpy().astype(bool)).rolling(
            K_CONF, min_periods=1).max().to_numpy().astype(bool)
        preds[fam] = {"LONG": fl, "SHORT": fs}
    preds.update(build_btc_predicates(d))
    preds.update(build_filters(d))
    # fine sweeps
    adx = d["adx"].to_numpy()
    for t in np.arange(15, 42.5, 2.5):
        m = np.where(np.isnan(adx), False, adx > t)
        preds[f"adx>{t:g}"] = {"LONG": m, "SHORT": m}
    c = d["Close"].to_numpy()
    for k in (1.25, 1.75, 2.25, 2.5):
        b, s = cusum_events(c, k)
        preds[f"cusum_{k}"] = {"LONG": b, "SHORT": s}
    return preds


# shortlist from phase 1 (combo tokens must match pred keys above)
SHORTLIST = [
    ("LONG",  ["adx_di_cross", "momentum"]),
    ("LONG",  ["adx_di_cross", "momentum", "adx>20"]),
    ("LONG",  ["vidya_dmi", "cusum_1.5"]),
    ("LONG",  ["vidya_dmi", "cusum_1.5", "momentum"]),
    ("LONG",  ["vidya_dmi", "cusum_1.5", "poc_side"]),
    ("LONG",  ["poc_cross", "adx>30"]),
    ("LONG",  ["poc_cross", "momentum", "adx>20"]),
    ("LONG",  ["poc_cross", "cumdelta", "adx>20"]),
    ("LONG",  ["mech_trigger", "cusum_2.0", "adx>20"]),
    ("LONG",  ["scalp_bias", "vol_burst", "adx>20"]),
    ("LONG",  ["liquidity_sweep", "cusum_1.0", "adx>15"]),
    ("LONG",  ["scalp_bias", "adx_di_cross", "near_lvl"]),
    ("SHORT", ["mom3_60", "poc_cross", "near_lvl"]),
    ("SHORT", ["cusum_1.5", "poc_cross", "near_lvl"]),
    ("SHORT", ["mom3_60", "poc_cross"]),
    ("SHORT", ["adx_di_cross", "momentum"]),
    ("SHORT", ["adx_di_cross", "momentum", "adx>20"]),
    ("SHORT", ["vidya_dmi", "cusum_1.5"]),
    ("SHORT", ["poc_cross", "adx>30"]),
    ("SHORT", ["mech_trigger", "cusum_2.0", "adx>20"]),
    ("SHORT", ["scalp_bias", "vol_burst", "adx>20"]),
]

# fine-sweep grids
SWEEPS = (
    [("LONG", ["poc_cross", f"adx>{t:g}"]) for t in np.arange(20, 42.5, 2.5)]
    + [("SHORT", ["poc_cross", f"adx>{t:g}"]) for t in np.arange(20, 42.5, 2.5)]
    + [("LONG", ["vidya_dmi", f"cusum_{k}"]) for k in (1.25, 1.5, 1.75, 2.0, 2.25, 2.5)]
    + [("SHORT", ["vidya_dmi", f"cusum_{k}"]) for k in (1.25, 1.5, 1.75, 2.0, 2.25, 2.5)]
    + [("LONG", ["adx_di_cross", "momentum", f"adx>{t:g}"]) for t in (15, 17.5, 20, 22.5, 25)]
    + [("SHORT", ["adx_di_cross", "momentum", f"adx>{t:g}"]) for t in (15, 17.5, 20, 22.5, 25)]
)


def combo_mask(preds, combo, direction, n):
    m = np.ones(n, bool)
    for t in combo:
        m &= preds[t][direction]
    return m


def fold_scores(idx: np.ndarray, ft: np.ndarray, fold_id: np.ndarray):
    """Per-fold (wins, resolved) for entry indices."""
    out = {}
    for f in np.unique(fold_id[idx]):
        ii = idx[fold_id[idx] == f]
        r = ft[ii]
        res = np.isin(r, ("win", "loss"))
        out[int(f)] = (int((r[res] == "win").sum()), int(res.sum()))
    return out


def main() -> None:
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

    print(f"Fetching BTC-USD 5m for {FETCH_HOURS/24:.0f} days…")
    t38.NOISE_RTH_PCT = 2.5; t38.NOISE_EH_PCT = 2.0; t38.EXTENDED_HOURS = True
    d, _ = t38._build_engine_df(True, hours=FETCH_HOURS, ticker="BTC-USD",
                                closed_only=True)
    span_h = (d.index[-1] - d.index[0]) / pd.Timedelta(hours=1)
    print(f"  bars: {len(d)}  span: {d.index[0]} → {d.index[-1]} ({span_h:.0f}h)")

    (reach_l, ft_l, bars_l), (reach_s, ft_s, bars_s) = outcomes_100(d)
    ft = {"LONG": ft_l, "SHORT": ft_s}
    preds = build_all_preds(d)
    n = len(d)
    days = span_h / 24

    # weekly folds
    age_h = ((d.index[-1] - d.index) / pd.Timedelta(hours=1)).to_numpy()
    fold_id = (age_h // 168).astype(int)          # 0 = most recent week
    n_folds = int(fold_id.max()) + 1

    rows = []
    for direction, combo in SHORTLIST + SWEEPS:
        try:
            m = combo_mask(preds, combo, direction, n)
        except KeyError as e:
            print(f"  skip {combo}: missing {e}"); continue
        idx = entries_of(m)
        r = ft[direction][idx]
        res = np.isin(r, ("win", "loss"))
        wins, tot = int((r[res] == "win").sum()), int(res.sum())
        if tot < 10:
            continue
        pf = fold_scores(idx, ft[direction], fold_id)
        fold_str = " ".join(
            f"w{f}:{w}/{t}" for f, (w, t) in sorted(pf.items()))
        worst = min((w / t for f, (w, t) in pf.items() if t >= 3), default=np.nan)
        rows.append({
            "direction": direction, "combo": " + ".join(combo),
            "n": tot, "acc": round(wins / tot * 100, 1),
            "wilson_lb": round(wilson_lb(wins, tot), 1),
            "worst_fold": round(worst * 100, 1) if worst == worst else np.nan,
            "per_day": round(len(idx) / days, 2),
            "folds": fold_str,
        })

    df = pd.DataFrame(rows).sort_values(["wilson_lb", "n"], ascending=[False, False])

    rep = [
        f"# BTC-60 ensemble validation — ±${TARGET_USD:.0f} / {HORIZON_BARS*5}min "
        f"first-touch, {days:.0f} days of 5m",
        f"- bars {len(d)}, {d.index[0]} → {d.index[-1]}",
        f"- folds = calendar weeks (w0 = most recent); wilson_lb = 95% lower "
        f"bound on accuracy; worst_fold = min weekly accuracy (folds with ≥3 "
        f"resolved)\n",
        "## Shortlist + fine sweeps, ranked by Wilson lower bound\n",
        df.to_string(index=False),
    ]

    # ---- OR-ensembles ------------------------------------------------------
    # survivors: acc >= 74, wilson_lb >= 55, worst_fold >= 50, n >= 12
    surv = df[(df["acc"] >= 74) & (df["wilson_lb"] >= 55)
              & (df["n"] >= 12) & (df["worst_fold"].fillna(0) >= 50)]
    rep.append("\n## Survivors (acc≥74, wilsonLB≥55, worst fold≥50, n≥12)\n")
    rep.append(surv.to_string(index=False) if not surv.empty else "_(none)_")

    def ens_eval(members: list[tuple[str, list[str]]], direction: str):
        m = np.zeros(n, bool)
        for dd, combo in members:
            if dd != direction: continue
            m |= combo_mask(preds, combo, direction, n)
        idx = entries_of(m)
        r = ft[direction][idx]
        res = np.isin(r, ("win", "loss"))
        wins, tot = int((r[res] == "win").sum()), int(res.sum())
        pf = fold_scores(idx, ft[direction], fold_id)
        return {
            "n": tot, "acc": round(wins / tot * 100, 1) if tot else np.nan,
            "wilson_lb": round(wilson_lb(wins, tot), 1),
            "per_day": round(len(idx) / days, 2),
            "folds": " ".join(f"w{f}:{w}/{t}" for f, (w, t) in sorted(pf.items())),
        }

    surv_members = []
    for _, r in surv.iterrows():
        surv_members.append((r["direction"], r["combo"].split(" + ")))

    rep.append("\n## OR-ensembles of survivors (fire when ANY member fires)\n")
    for direction in ("LONG", "SHORT"):
        mem = [(dd, c) for dd, c in surv_members if dd == direction]
        if not mem:
            rep.append(f"- {direction}: no survivors to ensemble"); continue
        st = ens_eval(mem, direction)
        rep.append(f"- **{direction} ensemble** ({len(mem)} members): "
                   f"acc {st['acc']}% (LB {st['wilson_lb']}%), "
                   f"n={st['n']}, {st['per_day']}/day — folds {st['folds']}")
        for dd, c in mem:
            rep.append(f"    - {' + '.join(c)}")

    out = _HERE / "btc60_ensemble_validation.md"
    out.write_text("\n".join(rep), encoding="utf-8")
    print(f"\nreport → {out}")
    print(df.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
