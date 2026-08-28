#!/usr/bin/env python3
"""
backtest_trades.py — summarize realized P&L per situation/confidence from the
sports trade-history CSV (kalshi/trade_history_sports.csv) written by the bot.

Each trade is an OPEN row (entry context) followed later by a CLOSE row with the
realized P&L (from fills) and the account PV delta.  Run after the bot has logged
a few sessions of trades — then feed the findings back into tennis/predict.py.

    python tennis/backtest_trades.py [path-to-csv]
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT = Path(__file__).resolve().parent.parent / "kalshi" / "trade_history_sports.csv"


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    if not path.exists():
        print(f"no trade history yet at {path} — let the bot run to collect trades.")
        return

    opens: dict[str, dict] = {}
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    # pair each CLOSE with the most recent OPEN for that ticker
    by_key = defaultdict(lambda: {"n": 0, "pnl": 0.0, "wins": 0, "pct": 0.0})
    closes = 0
    for r in rows:
        tk = r.get("ticker", "")
        if r.get("phase") == "OPEN":
            opens[tk] = r
        elif r.get("phase") == "CLOSE":
            o = opens.pop(tk, {})
            key = f"{o.get('situation') or r.get('situation') or '?'}/{o.get('confidence') or r.get('confidence') or '?'}"
            try:
                pnl = float(r.get("realized_pnl") or 0)
            except ValueError:
                pnl = 0.0
            try:
                pct = float(r.get("pv_delta_pct") or 0)
            except ValueError:
                pct = 0.0
            s = by_key[key]
            s["n"] += 1
            s["pnl"] += pnl
            s["pct"] += pct
            s["wins"] += 1 if pnl > 0 else 0
            closes += 1

    if not closes:
        print("trade history has no closed trades yet — run longer, then re-check.")
        return

    print(f"closed trades: {closes}  (file: {path.name})\n")
    print(f"{'situation/confidence':24} {'n':>3} {'totPnL$':>8} {'avgPnL$':>8} {'win%':>5} {'avgPVdelta%':>11}")
    for key in sorted(by_key, key=lambda k: -by_key[k]["pnl"]):
        s = by_key[key]
        n = s["n"]
        print(f"{key:24} {n:>3} {s['pnl']:>8.2f} {s['pnl']/n:>8.2f} {100*s['wins']/n:>4.0f}% {s['pct']/n:>10.2f}%")
    tot = sum(s["pnl"] for s in by_key.values())
    print(f"\nTOTAL realized P&L: ${tot:.2f} over {closes} closed trades")


if __name__ == "__main__":
    main()
