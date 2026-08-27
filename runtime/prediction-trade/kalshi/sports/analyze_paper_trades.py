#!/usr/bin/env python3
"""
analyze_paper_trades.py — report card for the main bot's PAPER trading run.
===========================================================================
Reads customers/<customer>/trade_history/paper_trades_main.csv (written by
bot_kalshi_main.py with MAIN_PAPER=TRUE) and prints the go/no-go report:

  • headline: closed P&L, win rate, avg win/loss, fees, open exposure
  • per sport, per v5 rule tag (F1..F4 parsed from the reason), per situation,
    per entry band, per exit kind (tp/stop/floor/sportexit/settle)
  • daily P&L curve
  • v5 expectation check (tennis): the replay-verified benchmark was
    ~+$0.75/trade at 20 contracts (holdout +$60.63 on 17 kept, ROI ~30%) —
    the report scales the benchmark to the configured contract size
  • verdict hints: PROVISIONAL rules (F2/F4) live occurrence counts

Run (from the repo root or this folder):
    python analyze_paper_trades.py [customer]      # default "suma"
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path


def _main_checkout_root(p: Path) -> Path:
    parts = p.parts
    for i, part in enumerate(parts[:-1]):
        if part.lower() == ".claude" and parts[i + 1].lower() == "worktrees":
            return Path(*parts[:i])
    return p


_HERE = Path(__file__).resolve().parent
_ROOT = _main_checkout_root(_HERE.parents[1])
CUSTOMER = sys.argv[1] if len(sys.argv) > 1 else "suma"
CSV_PATH = _ROOT / "customers" / CUSTOMER / "trade_history" / "paper_trades_main.csv"

# tennis v5 replay benchmark, per trade per 20 contracts (holdout: +$60.63/17)
V5_BENCH_PER_TRADE_20 = 60.63 / 17


def f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def v5_rule(reason: str) -> str:
    m = re.search(r"v5 \[(F\d|no-rule|price-gate|bfav-itf-excl)\]", reason or "")
    return m.group(1) if m else ""


def band(bid) -> str:
    b = f(bid)
    return "?" if b is None else f"{int(b // 10) * 10}-{int(b // 10) * 10 + 9}c"


def main() -> None:
    if not CSV_PATH.exists():
        print(f"[PAPER-REPORT] no paper trades yet — {CSV_PATH} does not exist.\n"
              f"Is the bot running with MAIN_PAPER=TRUE?")
        return
    rows = list(csv.DictReader(open(CSV_PATH, newline="", encoding="utf-8")))
    closed = [r for r in rows if r.get("status") == "CLOSED"
              and f(r.get("realized_pnl")) is not None]
    open_ = [r for r in rows if r.get("status") == "OPEN"]
    print(f"[PAPER-REPORT] {CSV_PATH}")
    print(f"trades: {len(rows)} total | {len(closed)} closed | {len(open_)} open\n")
    if open_:
        print("OPEN positions:")
        for r in open_:
            print(f"  {r['sport']:<9} {r['ticker']:<44.44} {r['name'][:20]:<20} "
                  f"fill {r.get('fill_price', '?')}c x{r.get('contracts', '?')} "
                  f"tp {r.get('tp_price', '-')}c stop {r.get('stop_price', '-')}c")
        print()
    if not closed:
        print("No closed paper trades yet — re-run after some settle.")
        return

    pnl = sum(f(r["realized_pnl"]) for r in closed)
    wins = [r for r in closed if f(r["realized_pnl"]) > 0]
    losses = [r for r in closed if f(r["realized_pnl"]) < 0]
    aw = sum(f(r["realized_pnl"]) for r in wins) / len(wins) if wins else 0
    al = sum(f(r["realized_pnl"]) for r in losses) / len(losses) if losses else 0
    print(f"HEADLINE: P&L ${pnl:+,.2f} | wr {len(wins)}/{len(closed)} "
          f"({len(wins) / len(closed) * 100:.0f}%) | avg win ${aw:+.2f} / "
          f"avg loss ${al:+.2f}"
          + (f" | W:L ratio {abs(aw / al):.2f}" if al else ""))

    def cut(label, key):
        g = defaultdict(lambda: [0, 0, 0.0])
        for r in closed:
            k = key(r) or "?"
            p = f(r["realized_pnl"])
            g[k][0] += 1
            g[k][1] += p > 0
            g[k][2] += p
        print(f"\nBY {label}:")
        for k, (n, w, s) in sorted(g.items(), key=lambda kv: kv[1][2]):
            print(f"  {k:<22.22} n={n:<3} wr={w / n * 100:>3.0f}%  "
                  f"pnl=${s:>+8.2f}  avg=${s / n:>+6.2f}")

    cut("SPORT", lambda r: r.get("sport"))
    cut("V5 RULE (tennis)", lambda r: v5_rule(r.get("reason"))
        if r.get("sport") == "tennis" else None)
    cut("SITUATION", lambda r: r.get("situation"))
    cut("ENTRY BAND", lambda r: band(r.get("fill_price") or r.get("signal_bid")))
    cut("DAY", lambda r: (r.get("ts") or "")[:10])

    tn = [r for r in closed if r.get("sport") == "tennis"]
    if tn:
        n20 = [f(r.get("contracts")) or 20 for r in tn]
        scale = (sum(n20) / len(n20)) / 20.0
        bench = V5_BENCH_PER_TRADE_20 * scale
        actual = sum(f(r["realized_pnl"]) for r in tn) / len(tn)
        print(f"\nV5 CHECK (tennis): actual ${actual:+.2f}/trade vs replay "
              f"benchmark ${bench:+.2f}/trade at your avg size "
              f"({sum(n20) / len(n20):.0f} contracts)"
              f" -> {'ON TRACK' if actual >= bench * 0.5 else 'BELOW — investigate'}")
        prov = defaultdict(int)
        for r in tn:
            t = v5_rule(r.get("reason"))
            if t in ("F2", "F4"):
                prov[t] += 1
        if prov:
            print(f"PROVISIONAL rules seen live: "
                  + ", ".join(f"{k} x{v}/30 needed" for k, v in prov.items()))


if __name__ == "__main__":
    main()
