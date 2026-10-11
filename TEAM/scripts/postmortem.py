#!/usr/bin/env python
"""TEAM post-mortem: calibration and payoff report over the live ledger.

Read-only. Opens var/app-v2.db with mode=ro, so it cannot change anything.

    python TEAM/scripts/postmortem.py [--db PATH] [--bot KEY] [--live-only]

Per bot: n, win rate, realised break-even win rate (from avg win / avg loss),
the gap between them, PnL, fees, Brier score of the market price, and the
not_found share. Then the same split by 10c entry-price bucket, which is where
calibration gaps show up.
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def to_dollars(x):
    if x is None:
        return None
    return x / 100.0 if x > 1 else float(x)


def load(db: Path, bot: str | None, live_only: bool):
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    sql = ("select bot_key, bot_version, status, entry_price, realized_pnl, "
           "coalesce(fees_usd, 0), is_live from bot_trade")
    rows = con.execute(sql).fetchall()
    con.close()
    if bot:
        rows = [r for r in rows if r[0] == bot]
    if live_only:
        rows = [r for r in rows if r[6]]
    return rows


def summarise(rows):
    settled = [r for r in rows if r[4] is not None and r[3] is not None]
    n = len(settled)
    if not n:
        return None
    wins = [r[4] for r in settled if r[4] > 0]
    losses = [r[4] for r in settled if r[4] < 0]
    avg_w = sum(wins) / len(wins) if wins else 0.0
    avg_l = sum(losses) / len(losses) if losses else 0.0
    be = abs(avg_l) / (avg_w + abs(avg_l)) if (avg_w or avg_l) else None
    wr = len(wins) / n
    brier_mkt = sum((to_dollars(r[3]) - (r[4] > 0)) ** 2 for r in settled) / n
    return {
        "n": n, "win_rate": wr, "implied": sum(to_dollars(r[3]) for r in settled) / n,
        "breakeven": be, "gap": None if be is None else wr - be,
        "avg_win": avg_w, "avg_loss": avg_l,
        "pnl": sum(r[4] for r in settled), "fees": sum(r[5] for r in settled),
        "brier_mkt": brier_mkt,
    }


def pct(x):
    return "   -  " if x is None else f"{x * 100:5.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=ROOT / "var" / "app-v2.db")
    ap.add_argument("--bot")
    ap.add_argument("--live-only", action="store_true")
    a = ap.parse_args()

    rows = load(a.db, a.bot, a.live_only)
    by_bot = defaultdict(list)
    for r in rows:
        by_bot[f"{r[0]}/{r[1]}"].append(r)

    print(f"ledger: {a.db}  rows={len(rows)}\n")
    print(f"{'bot':22} {'n':>4} {'win':>6} {'impl':>6} {'b/even':>6} {'gap':>6} "
          f"{'avgW':>7} {'avgL':>7} {'pnl':>9} {'fees':>6} {'brier':>6} {'nf%':>6}")
    for key, rs in sorted(by_bot.items(), key=lambda kv: -len(kv[1])):
        s = summarise(rs)
        nf = sum(r[2] == "not_found" for r in rs) / len(rs)
        if not s:
            print(f"{key:22} {0:>4}  (no settled rows)  nf={pct(nf)}")
            continue
        print(f"{key:22} {s['n']:>4} {pct(s['win_rate'])} {pct(s['implied'])} "
              f"{pct(s['breakeven'])} {pct(s['gap'])} {s['avg_win']:7.2f} "
              f"{s['avg_loss']:7.2f} {s['pnl']:9.2f} {s['fees']:6.2f} "
              f"{s['brier_mkt']:6.3f} {pct(nf)}")

    print("\nby entry-price bucket (gap = realised win rate - avg entry price)")
    print(f"{'bot':12} {'bucket':>7} {'n':>4} {'win':>6} {'impl':>6} {'gap':>7} {'pnl':>9}  flag")
    buckets = defaultdict(list)
    for r in rows:
        if r[4] is None or r[3] is None:
            continue
        b = int(to_dollars(r[3]) * 10) * 10
        buckets[(r[0], b)].append(r)
    for (bot, b), rs in sorted(buckets.items()):
        s = summarise(rs)
        gap = s["win_rate"] - s["implied"]
        flag = ""
        if s["n"] >= 30 and gap < 0:
            flag = "CHANGE-ELIGIBLE (QA-R1)"
        elif s["n"] >= 10 and gap < -0.05:
            flag = "watch"
        print(f"{bot:12} {b:>5}c {s['n']:>4} {pct(s['win_rate'])} {pct(s['implied'])} "
              f"{gap * 100:6.1f}p {s['pnl']:9.2f}  {flag}")


if __name__ == "__main__":
    main()
