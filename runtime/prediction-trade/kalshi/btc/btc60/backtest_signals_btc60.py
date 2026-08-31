#!/usr/bin/env python3
"""
backtest_signals_btc60.py — signal research for the Kalshi BTC-60 bot rebuild.
==============================================================================
GOAL (user spec): find the signal(s) with MAXIMUM accuracy predicting a
>= $100 BTC move within 30 minutes (6 x 5m candles) in the signal direction
(LONG: +100 first; SHORT: -100 first), with as many occurrences/day as
possible.  Tested over trailing 24H / 48H / 72H / 100H / 150H / 250H windows
of 5-minute candles.

TWO scoring modes per signal:
  reach : did price touch >= +$100 (LONG) within 6 bars at all?  (user's
          literal spec — "jumps at least 100 points within 30 minutes")
  ftouch: FIRST-TOUCH — +$100 touched BEFORE -$100 (same-bar both = loss).
          The honest tradability metric; reported as the headline accuracy.

SIGNAL UNIVERSE
  A. combined_scalp engine (stock-trade/38trades_signals.py):
     liquidity_sweep, vidya_dmi, adx_di_cross, scalp_bias,
     mechanical_trigger, orderflow_vp_premium, confluence_star
     + filters delta / cumdelta / near_level / momentum / adx>{15,20,25,30}
  B. NEW BTC-specific (this file):
     cusum_{1.0,1.5,2.0}   AFML symmetric CUSUM on 5m log returns, EWMA vol
     squeeze_break          BB(20,2) width in bottom 20% of 24h -> band break
     don_break_1h           close breaks the prior 12-bar (1h) high/low
     vol_burst              volume > 2x SMA20 AND directional body > 0.4 ATR
     range_burst            single-bar body > 1.2 ATR in direction
     mom3_60                3-bar net move >= $60 in direction
     vwap_cross             close crosses session VWAP in direction
     poc_cross              close crosses the volume-profile POC in direction
     + filters above_poc / below_poc / net30_up / net30_dn / di_dom

Usage:
    python backtest_signals_btc60.py            # full run, writes report+csv
Outputs (this folder):
    btc60_signal_backtest_report.md
    btc60_signal_backtest.csv
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
# stock-trade lives in the MAIN checkout two levels above prediction-trade;
# walk out of any .claude/worktrees nesting first.
def _main_root(p: Path) -> Path:
    parts = p.parts
    for i, part in enumerate(parts[:-1]):
        if part.lower() == ".claude" and parts[i + 1].lower() == "worktrees":
            return Path(*parts[:i])
    return p

_REPO = _main_root(_HERE.parents[3])          # 38trades-py-claude
_ST = _REPO / "stock-trade"
sys.path.insert(0, str(_ST))

_spec = importlib.util.spec_from_file_location("t38", _ST / "38trades_signals.py")
t38 = importlib.util.module_from_spec(_spec)
sys.modules["t38"] = t38
_spec.loader.exec_module(t38)

TARGET_USD   = 100.0          # the +/- move that defines success
HORIZON_BARS = 6              # 30 minutes of 5m candles
WINDOWS_H    = [24, 48, 72, 100, 150, 250]
MAX_HOURS    = max(WINDOWS_H)
K_CONF       = 2              # engine signal counts if fired within last K bars
ADX_SWEEP    = [15, 20, 25, 30]
MIN_SUPPORT_FULL = 8          # min entries over the FULL window to report

ENGINE_SIGS = {               # family -> (long_col, short_col)
    "liquidity_sweep":     ("sweep_low", "sweep_high"),
    "vp_premium":          ("premium_long", "premium_short"),
    "vidya_dmi":           ("buy_signal", "sell_signal"),
    "scalp_bias":          ("long_bias", "short_bias"),
    "confluence_star":     ("confluence_long", "confluence_short"),
    "mech_trigger":        ("fire_long", "fire_short"),
    "adx_di_cross":        ("show_plus", "show_minus"),
}


# ─────────────────────────── outcomes ────────────────────────────────────────
def outcomes_100(df: pd.DataFrame):
    """reach/first-touch outcome arrays for LONG and SHORT (+bars to target)."""
    high, low, close = (df[c].to_numpy() for c in ("High", "Low", "Close"))
    n = len(df)
    reach_l = np.zeros(n, bool); reach_s = np.zeros(n, bool)
    ft_l = np.empty(n, object);  ft_s = np.empty(n, object)
    bars_l = np.full(n, np.nan); bars_s = np.full(n, np.nan)
    for i in range(n):
        lt, ls = close[i] + TARGET_USD, close[i] - TARGET_USD
        rl = rs = None
        for j in range(i + 1, min(i + 1 + HORIZON_BARS, n)):
            hi, lo = high[j], low[j]
            if hi >= lt: reach_l[i] = True
            if lo <= ls: reach_s[i] = True
            if rl is None and (hi >= lt or lo <= ls):
                rl = "loss" if lo <= ls else "win"        # same-bar tie = loss
                if rl == "win": bars_l[i] = j - i
            if rs is None and (lo <= ls or hi >= lt):
                rs = "loss" if hi >= lt else "win"
                if rs == "win": bars_s[i] = j - i
        ft_l[i] = rl or "open"
        ft_s[i] = rs or "open"
    return (reach_l, ft_l, bars_l), (reach_s, ft_s, bars_s)


# ─────────────────────────── new BTC signals ─────────────────────────────────
def cusum_events(close: np.ndarray, k_sigma: float, lam: float = 0.94):
    """AFML symmetric CUSUM on log returns w/ EWMA vol threshold.
    Returns (buy_fire, sell_fire) boolean arrays."""
    n = len(close)
    buy = np.zeros(n, bool); sell = np.zeros(n, bool)
    sp = sn = var = 0.0
    for i in range(1, n):
        if close[i - 1] <= 0: continue
        r = math.log(close[i] / close[i - 1])
        var = lam * var + (1 - lam) * r * r
        h = max(k_sigma * math.sqrt(var), 5e-5)
        sp = max(0.0, sp + r); sn = min(0.0, sn + r)
        if sp >= h:  buy[i] = True;  sp = 0.0
        if -sn >= h: sell[i] = True; sn = 0.0
    return buy, sell


def build_btc_predicates(d: pd.DataFrame) -> dict[str, dict[str, np.ndarray]]:
    """{name: {"LONG": arr, "SHORT": arr}} for the BTC-specific signal set."""
    o, h, l, c = (d[x].to_numpy() for x in ("Open", "High", "Low", "Close"))
    v = d["Volume"].to_numpy(dtype=float)
    atr = d["atr"].to_numpy()
    n = len(d)
    P: dict[str, dict[str, np.ndarray]] = {}

    for k in (1.0, 1.5, 2.0):
        b, s = cusum_events(c, k)
        P[f"cusum_{k}"] = {"LONG": b, "SHORT": s}

    cs = pd.Series(c)
    ma, sd = cs.rolling(20).mean(), cs.rolling(20).std()
    upper, lower = (ma + 2 * sd).to_numpy(), (ma - 2 * sd).to_numpy()
    width = (4 * sd / ma)
    w_pct = width.rolling(288, min_periods=60).rank(pct=True).to_numpy()
    squeeze = w_pct < 0.20
    P["squeeze_break"] = {"LONG":  squeeze & (c > upper),
                          "SHORT": squeeze & (c < lower)}

    hi12 = pd.Series(h).rolling(12).max().shift(1).to_numpy()
    lo12 = pd.Series(l).rolling(12).min().shift(1).to_numpy()
    P["don_break_1h"] = {"LONG": c > hi12, "SHORT": c < lo12}

    vma = pd.Series(v).rolling(20).mean().to_numpy()
    body = c - o
    P["vol_burst"] = {"LONG":  (v > 2 * vma) & (body > 0.4 * atr),
                      "SHORT": (v > 2 * vma) & (body < -0.4 * atr)}

    P["range_burst"] = {"LONG": body > 1.2 * atr, "SHORT": body < -1.2 * atr}

    net3 = cs.diff(3).to_numpy()
    P["mom3_60"] = {"LONG": net3 >= 60, "SHORT": net3 <= -60}

    vwap = d["session_vwap"].to_numpy()
    prev_c = np.r_[np.nan, c[:-1]]
    P["vwap_cross"] = {"LONG":  (prev_c <= vwap) & (c > vwap),
                       "SHORT": (prev_c >= vwap) & (c < vwap)}

    poc = d["poc"].to_numpy()
    P["poc_cross"] = {"LONG":  (prev_c <= poc) & (c > poc),
                      "SHORT": (prev_c >= poc) & (c < poc)}
    return P


def build_filters(d: pd.DataFrame) -> dict[str, dict[str, np.ndarray]]:
    c = d["Close"].to_numpy()
    bar_delta = d["bar_delta"].to_numpy()
    cum_delta = d["cum_delta"].to_numpy()
    adx = d["adx"].to_numpy()
    pdi, mdi = d["plus_di"].to_numpy(), d["minus_di"].to_numpy()
    poc = d["poc"].to_numpy()
    net30 = pd.Series(c).diff(6).to_numpy()          # 30-min net move
    F: dict[str, dict[str, np.ndarray]] = {
        "delta":    {"LONG": bar_delta > 0, "SHORT": bar_delta < 0},
        "cumdelta": {"LONG": cum_delta > 0, "SHORT": cum_delta < 0},
        "near_lvl": {"LONG": d["near_sup"].to_numpy().astype(bool),
                     "SHORT": d["near_res"].to_numpy().astype(bool)},
        "momentum": {"LONG": d["mom_up"].to_numpy().astype(bool),
                     "SHORT": d["mom_dn"].to_numpy().astype(bool)},
        "di_dom":   {"LONG": pdi > mdi, "SHORT": mdi > pdi},
        "poc_side": {"LONG": c > poc, "SHORT": c < poc},
        "net30_dir": {"LONG": net30 > 0, "SHORT": net30 < 0},
    }
    for t in ADX_SWEEP:
        m = np.where(np.isnan(adx), False, adx > t)
        F[f"adx>{t}"] = {"LONG": m, "SHORT": m}
    return F


# ─────────────────────────── scoring ─────────────────────────────────────────
def entries_of(mask: np.ndarray) -> np.ndarray:
    """Collapse consecutive True runs to single entry indices."""
    e = mask & ~np.r_[False, mask[:-1]]
    return np.nonzero(e)[0]


def score(idx: np.ndarray, reach: np.ndarray, ft: np.ndarray,
          bars: np.ndarray) -> dict:
    if idx.size == 0:
        return dict(n=0)
    r = reach[idx]
    f = ft[idx]
    resolved = np.isin(f, ("win", "loss"))
    wins = (f[resolved] == "win").sum()
    nres = int(resolved.sum())
    b = bars[idx]; b = b[~np.isnan(b)]
    return dict(
        n=int(idx.size),
        reach_acc=float(r.mean() * 100),
        ft_n=nres,
        ft_acc=float(wins / nres * 100) if nres else np.nan,
        med_bars=float(np.median(b)) if b.size else np.nan,
    )


def main() -> None:
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass

    print(f"Building BTC-USD 5m engine frame ({MAX_HOURS}h + warmup)…")
    t38.NOISE_RTH_PCT = 2.5; t38.NOISE_EH_PCT = 2.0; t38.EXTENDED_HOURS = True
    d, _ = t38._build_engine_df(True, hours=MAX_HOURS, ticker="BTC-USD",
                                closed_only=True)
    print(f"  bars: {len(d)}  span: {d.index[0]} → {d.index[-1]}")

    (reach_l, ft_l, bars_l), (reach_s, ft_s, bars_s) = outcomes_100(d)

    # baseline rates (all bars) per window — the number every signal must beat
    def unconditional(w_mask):
        i = np.nonzero(w_mask)[0]
        rl = float(reach_l[i].mean() * 100)
        rs = float(reach_s[i].mean() * 100)
        fl = ft_l[i]; res = np.isin(fl, ("win", "loss"))
        ftl = float((fl[res] == "win").mean() * 100) if res.any() else np.nan
        return rl, rs, ftl

    # predicates
    n = len(d)
    preds: dict[str, dict[str, np.ndarray]] = {}
    for fam, (lc, sc) in ENGINE_SIGS.items():
        fl = pd.Series(d[lc].to_numpy().astype(bool)).rolling(
            K_CONF, min_periods=1).max().to_numpy().astype(bool)
        fs = pd.Series(d[sc].to_numpy().astype(bool)).rolling(
            K_CONF, min_periods=1).max().to_numpy().astype(bool)
        preds[f"S:{fam}"] = {"LONG": fl, "SHORT": fs}
    for nm, dd in build_btc_predicates(d).items():
        preds[f"S:{nm}"] = dd
    filters = {f"F:{nm}": dd for nm, dd in build_filters(d).items()}

    sig_names = list(preds)
    filt_names = list(filters)
    preds.update(filters)

    ages = (d.index[-1] - d.index) / pd.Timedelta(hours=1)
    win_masks = {h: np.asarray(ages <= h) for h in WINDOWS_H}
    span_h = {h: min(h, (d.index[-1] - d.index[0]) / pd.Timedelta(hours=1))
              for h in WINDOWS_H}

    rows = []
    for direction in ("LONG", "SHORT"):
        reach, ft, bars = ((reach_l, ft_l, bars_l) if direction == "LONG"
                           else (reach_s, ft_s, bars_s))
        for r in (1, 2, 3):
            for combo in itertools.combinations(sig_names + filt_names, r):
                if not any(x.startswith("S:") for x in combo):
                    continue
                m = np.ones(n, bool)
                for x in combo:
                    m &= preds[x][direction]
                full_idx = entries_of(m & win_masks[MAX_HOURS])
                if full_idx.size < MIN_SUPPORT_FULL:
                    continue
                st_full = score(full_idx, reach, ft, bars)
                if np.isnan(st_full.get("ft_acc", np.nan)):
                    continue
                row = {
                    "direction": direction,
                    "combo": " + ".join(x.split(":", 1)[1] for x in combo),
                    "size": r,
                }
                for h in WINDOWS_H:
                    idx = entries_of(m & win_masks[h])
                    st = score(idx, reach, ft, bars)
                    row[f"n_{h}h"] = st.get("n", 0)
                    row[f"ft_{h}h"] = round(st.get("ft_acc", np.nan), 1) \
                        if st.get("n") else np.nan
                    row[f"reach_{h}h"] = round(st.get("reach_acc", np.nan), 1) \
                        if st.get("n") else np.nan
                row["ft_full"] = round(st_full["ft_acc"], 1)
                row["reach_full"] = round(st_full["reach_acc"], 1)
                row["n_full"] = st_full["n"]
                row["per_day"] = round(st_full["n"] / (span_h[MAX_HOURS] / 24), 2)
                row["med_bars"] = st_full["med_bars"]
                rows.append(row)

    res = pd.DataFrame(rows)
    res = res.sort_values(["ft_full", "n_full"], ascending=[False, False])
    out_csv = _HERE / "btc60_signal_backtest.csv"
    res.to_csv(out_csv, index=False)

    # ---- report ----
    rep = [
        f"# BTC-60 signal backtest — ±${TARGET_USD:.0f} within {HORIZON_BARS*5} min",
        f"- data: BTC-USD 5m, {len(d)} bars, {d.index[0]} → {d.index[-1]} "
        f"({(d.index[-1]-d.index[0])/pd.Timedelta(hours=1):.0f}h)",
        f"- ftouch = +$100 before −$100 within 30 min (headline accuracy); "
        f"reach = touched +$100 at all (user spec)",
        f"- engine-signal confluence window K={K_CONF} bars; entries de-duped; "
        f"min {MIN_SUPPORT_FULL} entries/{MAX_HOURS}h\n",
        "## Unconditional baselines (what any signal must beat)",
    ]
    for h in WINDOWS_H:
        rl, rs, ftl = unconditional(win_masks[h])
        rep.append(f"- {h:>3}h: reach LONG {rl:.1f}%  SHORT {rs:.1f}%  "
                   f"first-touch LONG {ftl:.1f}% (SHORT ≈ {100-ftl:.1f}%)")

    show = [c for c in res.columns if c not in ("size",)]
    for direction in ("LONG", "SHORT"):
        top = res[res["direction"] == direction].head(30)
        rep.append(f"\n## Top 30 by first-touch accuracy — {direction}\n")
        rep.append(top[show].to_string(index=False))

    # occurrence champions at >=80%
    hot = res[(res["ft_full"] >= 80)].sort_values("per_day", ascending=False)
    rep.append("\n## ≥80% first-touch, ranked by occurrences/day\n")
    rep.append(hot[show].head(25).to_string(index=False)
               if not hot.empty else "_(none cleared 80%)_")

    out_md = _HERE / "btc60_signal_backtest_report.md"
    out_md.write_text("\n".join(rep), encoding="utf-8")
    print(f"\nreport → {out_md}\ncsv    → {out_csv}")
    print(f"combos scored: {len(res)}")
    if not hot.empty:
        print("\nTop ≥80% by per_day:")
        print(hot[["direction", "combo", "ft_full", "n_full", "per_day"]]
              .head(12).to_string(index=False))


if __name__ == "__main__":
    main()
