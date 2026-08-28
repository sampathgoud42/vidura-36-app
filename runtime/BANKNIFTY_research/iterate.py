"""Iteration 2 — precision stacking + greedy ensemble.

The v1 grid (research.py) showed the accuracy/frequency trade-off: single
composites reach ~82% strict accuracy at ~1 trade/week, or ~58% at 1+/day.
This pass:

  A. 4-block stacking seeded from the highest-precision families, trying every
     remaining block as an extra filter (kill the last few stops).
  B. GREEDY ENSEMBLE: union many high-precision composites into one playbook —
     each added config must keep the book's strict win-rate above the bar
     while growing day coverage toward >= 1 signal every session.

Outputs: results/iteration2_stacks.csv, results/ensemble.csv, appends the
ensemble verdict to REPORT.md.

    python iterate.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from itertools import combinations
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

import config as C
import data
import features
import signals
from backtest import metrics, precompute_outcomes

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
WIN_BAR = 75.0          # ensemble must stay above this strict win-rate
SEED_MIN_TRADES = 6
SEED_MIN_WINRATE = 70.0
SEED_MIN_TPSL = 85.0


def log(m):
    print(f"[{datetime.now(ZoneInfo(C.TZ)):%H:%M:%S}] {m}", flush=True)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    bars = data.load_bars()
    d = features.build(bars)
    blk = signals.blocks(d)
    outs = {k: precompute_outcomes(d, k) for k in ("LONG", "SHORT")}
    n_days = d.loc[d["rth"], "date"].nunique()
    dates = d["date"].to_numpy()
    tod = pd.Series([x.time() for x in d.index], index=d.index)
    win_masks = {name: ((tod >= a) & (tod < b) & d["rth"]).fillna(False).to_numpy()
                 for name, (a, b) in C.WINDOWS.items()}
    gates = {(nk, vm): signals.noise_gate(d, nk, vm).to_numpy()
             for nk in C.NOISE_KS for vm in C.VOL_MULTS}
    log(f"ready · {n_days} sessions")

    # ── enumerate candidate configs (2..4 blocks) with masks kept ────────────
    def config_mask(direction, cmb, nk, vm, wname):
        m = gates[(nk, vm)] & win_masks[wname]
        for b in cmb:
            m = m & blk[direction][b].to_numpy()
        return m

    candidates = []          # (label, direction, mask, stat)
    for direction in ("LONG", "SHORT"):
        names = list(blk[direction])
        out = outs[direction]
        valid = (out["result"] != "").to_numpy()
        for r in (2, 3, 4):
            for cmb in combinations(names, r):
                # cheap pre-mask on the loosest gate to skip dead combos fast
                pre = blk[direction][cmb[0]].to_numpy().copy()
                for b in cmb[1:]:
                    pre &= blk[direction][b].to_numpy()
                if pre.sum() < SEED_MIN_TRADES:
                    continue
                for (nk, vm), g in gates.items():
                    for wname, wm in win_masks.items():
                        m = pre & g & wm & valid
                        n = int(m.sum())
                        if n < SEED_MIN_TRADES:
                            continue
                        stat = metrics(pd.Series(m, index=d.index), out, n_days)
                        if (stat["win_rate"] >= SEED_MIN_WINRATE
                                and stat["tp_before_sl"] >= SEED_MIN_TPSL):
                            label = f"{direction}:{'+'.join(cmb)}|nk{nk}|vm{vm}|{wname}"
                            candidates.append((label, direction, m, stat))
        log(f"{direction}: candidate pool now {len(candidates)}")

    pd.DataFrame([{"config": lab, **st} for lab, _, _, st in candidates]) \
        .sort_values(["win_rate", "trades"], ascending=False) \
        .to_csv(RESULTS / "iteration2_stacks.csv", index=False)
    log(f"{len(candidates)} high-precision candidates -> iteration2_stacks.csv")
    if not candidates:
        log("no candidates cleared the precision bar — relax SEED_* and rerun")
        return

    # ── greedy ensemble: maximize day coverage, keep strict win-rate high ────
    def book_stats(sel_idx):
        """Union of entry bars across selected configs; direction conflicts
        (same bar LONG+SHORT) are dropped."""
        by_dir = {"LONG": np.zeros(len(d), bool), "SHORT": np.zeros(len(d), bool)}
        for i in sel_idx:
            _, direction, m, _ = candidates[i]
            by_dir[direction] |= m
        conflict = by_dir["LONG"] & by_dir["SHORT"]
        rows = []
        for direction, m in by_dir.items():
            mm = m & ~conflict
            o = outs[direction][mm & (outs[direction]["result"] != "").to_numpy()]
            for ts, r in o.iterrows():
                rows.append({"time": ts, "date": ts.date(), "dir": direction,
                             "result": r["result"], "pnl": r["pnl"], "hold": r["hold"]})
        b = pd.DataFrame(rows)
        if b.empty:
            return None, b
        wins = int((b["result"] == "target").sum())
        stops = int((b["result"] == "stop").sum())
        eq = b.sort_values("time")["pnl"].cumsum()
        st = {"trades": len(b), "wins": wins, "stops": stops,
              "scratch": len(b) - wins - stops,
              "win_rate": round(wins / len(b) * 100, 1),
              "tp_before_sl": round(wins / max(wins + stops, 1) * 100, 1),
              "days_covered": b["date"].nunique(),
              "signals_per_day": round(len(b) / n_days, 2),
              "profit_factor": round(float(b.loc[b.pnl > 0, "pnl"].sum()
                                           / max(-b.loc[b.pnl < 0, "pnl"].sum(), 1e-9)), 2),
              "net_pct": round(float(b["pnl"].sum()), 2),
              "max_drawdown_pct": round(float((eq.cummax() - eq).max()), 2),
              "avg_hold_min": round(float(b["hold"].mean()) * 5, 1)}
        return st, b

    order = sorted(range(len(candidates)),
                   key=lambda i: (-candidates[i][3]["win_rate"], -candidates[i][3]["trades"]))
    chosen: list[int] = []
    best = None
    for i in order:
        trial = chosen + [i]
        st, _ = book_stats(trial)
        if st is None:
            continue
        if st["win_rate"] >= WIN_BAR:
            chosen = trial
            best = st
            if st["days_covered"] >= n_days and st["signals_per_day"] >= C.MIN_TRADES_PER_DAY:
                break
    st, book = book_stats(chosen)
    if st is None:
        pd.DataFrame(columns=["config"]).to_csv(RESULTS / "ensemble.csv", index=False)
        log("ensemble empty — no candidate cleared the win-rate bar; skipping report")
        return
    book.to_csv(RESULTS / "ensemble_trades.csv", index=False)
    pd.DataFrame([{"config": candidates[i][0], **candidates[i][3]} for i in chosen]) \
        .to_csv(RESULTS / "ensemble.csv", index=False)

    lines = [f"\n\n## ITERATION 2 — greedy precision ensemble ({datetime.now(ZoneInfo(C.TZ)):%Y-%m-%d %H:%M IST})\n",
             f"_{len(chosen)} composites unioned (each ≥{SEED_MIN_WINRATE:.0f}% strict / ≥{SEED_MIN_TPSL:.0f}% tp-before-sl on its own); "
             f"book constrained to ≥{WIN_BAR:.0f}% strict win-rate._\n",
             f"- **trades:** {st['trades']} ({st['signals_per_day']}/day, {st['days_covered']}/{n_days} days covered)",
             f"- **strict win-rate:** {st['win_rate']}%  ·  **tp-before-sl:** {st['tp_before_sl']}%",
             f"- **profit factor:** {st['profit_factor']}  ·  **net:** {st['net_pct']}%  ·  **maxDD:** {st['max_drawdown_pct']}%",
             f"- **avg hold:** {st['avg_hold_min']} min",
             "\nConfigs (see results/ensemble.csv):\n"]
    for i in chosen:
        lines.append(f"  - `{candidates[i][0]}` — {candidates[i][3]['win_rate']}% on {candidates[i][3]['trades']} trades")
    with open(HERE / "REPORT.md", "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    log("ensemble appended to REPORT.md")
    print("\n=== ENSEMBLE ===")
    for k, v in st.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
