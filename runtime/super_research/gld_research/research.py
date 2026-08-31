"""Research runner — grid-search composite Super-Signals to near-100% accuracy.

    python research.py            # full grid, writes results/ + REPORT.md

Pipeline: load 60d of 5m GLD -> engineer features -> enumerate 2- and 3-block
composites per direction x noise filters x entry windows -> precomputed
outcome join -> rank. "Success" is strict: TP (+/-0.30%) hit within 60 min,
counted against ALL trades taken (time-stop scratches count against the rate).
tp_before_sl is also reported (target-vs-stop only) for comparison.
"""
from __future__ import annotations

import sys
from datetime import datetime
from itertools import combinations
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import config as C
import data
import features
import signals
from backtest import metrics, precompute_outcomes

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
RESULTS.mkdir(exist_ok=True)


def log(msg: str) -> None:
    print(f"[{datetime.now(ZoneInfo(C.TZ)):%H:%M:%S}] {msg}", flush=True)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    log("loading 5m GLD bars (yfinance, 60d, incl. pre-market)…")
    bars = data.load_bars()
    log(f"{len(bars)} bars {bars.index[0]:%Y-%m-%d} → {bars.index[-1]:%Y-%m-%d %H:%M}")

    log("engineering features…")
    d = features.build(bars)
    blk = signals.blocks(d)
    outs = {dir_: precompute_outcomes(d, dir_) for dir_ in ("LONG", "SHORT")}
    n_days = d.loc[d["rth"], "date"].nunique()
    log(f"features + outcomes ready · {n_days} sessions")

    tod = pd.Series([x.time() for x in d.index], index=d.index)
    win_masks = {name: ((tod >= a) & (tod < b) & d["rth"]).fillna(False)
                 for name, (a, b) in C.WINDOWS.items()}

    rows = []
    total = 0
    for direction in ("LONG", "SHORT"):
        names = list(blk[direction])
        combos = [cmb for r in (2, C.MAX_COMBO_SIZE)
                  for cmb in combinations(names, r)]
        out = outs[direction]
        for nk in C.NOISE_KS:
            for vm in C.VOL_MULTS:
                gate = signals.noise_gate(d, nk, vm)
                for wname, wmask in win_masks.items():
                    base = gate & wmask
                    for cmb in combos:
                        m = base.copy()
                        for b in cmb:
                            m &= blk[direction][b]
                        if not m.any():
                            continue
                        stat = metrics(m, out, n_days)
                        if stat["trades"] == 0:
                            continue
                        rows.append({"direction": direction, "combo": "+".join(cmb),
                                     "noise_k": nk, "vol_mult": vm, "window": wname,
                                     **stat})
                        total += 1
        log(f"{direction}: grid done ({total} configs so far)")

    r = pd.DataFrame(rows)
    r.to_csv(RESULTS / "all_configs.csv", index=False)
    log(f"{len(r)} configs -> results/all_configs.csv")

    # ── selection ─────────────────────────────────────────────────────────────
    daily = r[r["trades_per_day"] >= C.MIN_TRADES_PER_DAY].sort_values(
        ["win_rate", "profit_factor", "trades"], ascending=False)
    precision = r[r["trades"] >= 10].sort_values(
        ["win_rate", "trades"], ascending=False)
    tp_sl = r[(r["trades"] >= 10) & (r["stops"] + r["wins"] >= 8)].sort_values(
        ["tp_before_sl", "trades"], ascending=False)

    def md_table(df: pd.DataFrame) -> str:
        if df.empty:
            return "_none_"
        cols = list(df.columns)
        out = ["| " + " | ".join(cols) + " |",
               "|" + "|".join("---" for _ in cols) + "|"]
        for _, row in df.iterrows():
            out.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
        return "\n".join(out)

    stamp = f"{datetime.now(ZoneInfo(C.TZ)):%Y-%m-%d %H:%M CST}"
    L = [f"# GLD 5m Super-Signal research — {stamp}\n",
         f"_{n_days} sessions of 5-minute GLD (yfinance, incl. pre-market) · entries {list(C.WINDOWS)} (CST) · "
         f"entry = next bar open · TP {C.TP_PCT}% ≤ {C.TP_BARS} bars · SL {C.SL_PCT}% ≤ {C.SL_BARS} bars · "
         f"time-stop at bar {C.TP_BARS} close · same-bar TP+SL = stop (conservative)._",
         f"_win_rate counts time-stop scratches as non-wins (strict); tp_before_sl ignores scratches._",
         f"_GEX/options-flow: no free historical feed — neutral hook only (see signals.GEX_NOTE)._\n",
         f"## Best configs with ≥{C.MIN_TRADES_PER_DAY:g} signal/day (strict win-rate)\n",
         md_table(daily.head(15)),
         "\n## Highest strict win-rate overall (≥10 trades)\n",
         md_table(precision.head(15)),
         "\n## Highest TP-before-SL rate (≥10 trades)\n",
         md_table(tp_sl.head(15)),
         ]
    (HERE / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    log("wrote REPORT.md")

    print("\n=== BEST ≥1/day (strict) ===")
    print(daily.head(8).to_string(index=False))
    print("\n=== BEST precision (≥10 trades) ===")
    print(precision.head(8).to_string(index=False))
    print("\n=== BEST tp-before-sl (≥10 trades) ===")
    print(tp_sl.head(8).to_string(index=False))


if __name__ == "__main__":
    main()
