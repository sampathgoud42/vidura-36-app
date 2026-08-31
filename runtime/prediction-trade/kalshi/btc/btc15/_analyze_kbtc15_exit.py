"""Realistic DOLLAR-P&L exit search for the KXBTC15M momentum entry.
Models entry/exit crossing the spread and the actual gap-through fills from the
bid path. Goal: find an exit with positive $/trade (win rate alone lied).
Reads kbtc-15.log + all kalshi/kbtc15_bids_*.log. Throwaway analysis."""
import glob
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CROSS = 3                       # cents crossed to fill (entry up, exit down) — matches bot
# entry rule (the +EV config from entry research; later window survives the stop)
N, D, EMIN, EMAX, TLO, THI = 3, 8, 60, 88, 15, 55

MKT = re.compile(r"\[(KXBTC15M-[^\]]+)\]")
BID = re.compile(r"\['yes':\s*(\d+),\s*'no':\s*(\d+)\]")


def load_markets():
    files = []
    seed = HERE.parent / "kbtc-15.log"
    if seed.exists():
        files.append(str(seed))
    files += sorted(glob.glob(str(HERE / "kbtc15_bids_*.log")))
    markets = []
    for fp in files:
        cur = None
        for ln in Path(fp).read_text(encoding="utf-8", errors="replace").splitlines():
            if "bid price live data" in ln and MKT.search(ln):
                cur = {"s": []}
                markets.append(cur)
            elif "[bid-price]" in ln and cur is not None:
                b = BID.search(ln)
                if b:
                    cur["s"].append((int(b.group(1)), int(b.group(2))))
    markets = [m for m in markets if len(m["s"]) >= 8]
    for m in markets:
        ly, ln_ = m["s"][-1]
        m["res"] = "yes" if ly > ln_ else "no"
    return markets


def entries(m):
    """yield (col, entry_idx, entry_bid) for the first momentum entry."""
    s = m["s"]
    n = len(s)
    for i in range(max(TLO, N), min(THI, n - 1)):
        for col in (0, 1):
            if s[i][col] - s[i - N][col] >= D and EMIN <= s[i][col] <= EMAX:
                return col, i, s[i][col]
    return None


def simulate(markets, stop, tp_pct, trail):
    """$ per contract per trade with realistic fills.
    stop = cents below entry to bail (None=off). tp_pct = take-profit (None=ride to
    resolution). trail = cents off running peak to bail (None=off)."""
    pnl = []
    for m in markets:
        e = entries(m)
        if not e:
            continue
        col, i, B = e
        buy = min(B + CROSS, 97)
        s = m["s"]
        n = len(s)
        peak = B
        exit_px = None
        for j in range(i + 1, n):
            px = s[j][col]
            peak = max(peak, px)
            if tp_pct is not None and px >= math.ceil(B * (1 + tp_pct)):
                exit_px = max(px - CROSS, 1)
                break
            if stop is not None and px <= B - stop:
                exit_px = max(px - CROSS, 1)
                break
            if trail is not None and px <= peak - trail and px < B:
                exit_px = max(px - CROSS, 1)
                break
        if exit_px is None:                       # held to resolution
            won = (m["res"] == ("yes" if col == 0 else "no"))
            exit_px = 100 if won else 0
        pnl.append((exit_px - buy) / 100.0)       # $ per contract
    if len(pnl) < 20:
        return None
    n = len(pnl)
    wins = sum(1 for p in pnl if p > 0)
    return n, wins / n * 100, sum(pnl) / n, sum(pnl)


markets = load_markets()
print(f"markets={len(markets)}  (entries fire on ~{sum(1 for m in markets if entries(m))} of them)")
print()
print("stop  tp     trail  n   WR%   avg$/contract  total$/contract")
rows = []
for stop in (None, 20, 25, 30, 35, 40, 45):     # wide stops cap the -100% tail
    for tp in (0.15, 0.30, 0.50, None):          # None = ride to resolution
        for trail in (None, 15, 25):
            r = simulate(markets, stop, tp, trail)
            if r:
                rows.append((r[2], stop, tp, trail, r[0], r[1], r[3]))
rows.sort(key=lambda r: r[0], reverse=True)        # by avg $/contract
for avg, stop, tp, trail, n, wr, tot in rows[:18]:
    print("%-5s %-5s  %-5s  %3d  %4.0f%%   %+.4f        %+.3f" %
          (stop, tp if tp else "ride", trail if trail else "-", n, wr, avg, tot))
print()
print("baseline (current live: stop20 tp0.15):")
r = simulate(markets, 20, 0.15, None)
if r:
    print("  n=%d WR=%.0f%% avg$/contract=%+.4f total=%+.3f" % (r[0], r[1], r[2], r[3]))
