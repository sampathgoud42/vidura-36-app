"""Time-of-day analysis of the kbtc-15.log momentum strategy.
For each hour (CST), report the strategy's trade count, win rate, avg pnl —
to drive time-boxed contract sizing. Throwaway analysis."""
import re
import math
import collections
from pathlib import Path

txt = Path("kbtc-15.log").read_text(encoding="utf-8", errors="replace").splitlines()
mkt_re = re.compile(r"\[(KXBTC15M-[^\]]+)\]")
bid_re = re.compile(r"\[bid-price\]\s*\[(\d\d):(\d\d):(\d\d)\]\s*\['yes':\s*(\d+),\s*'no':\s*(\d+)\]")
markets = []
cur = None
for ln in txt:
    if mkt_re.search(ln) and "bid price live data" in ln:
        cur = {"s": []}
        markets.append(cur)
        continue
    b = bid_re.search(ln)
    if b and cur is not None:
        hh = int(b.group(1))
        cur["s"].append((hh, int(b.group(4)), int(b.group(5))))
markets = [m for m in markets if len(m["s"]) >= 8]
for m in markets:
    ly, ln_ = m["s"][-1][1], m["s"][-1][2]
    m["res"] = "yes" if ly > ln_ else ("no" if ln_ > ly else "tie")

# strategy params (the chosen config / bot defaults)
N, D, EMIN, EMAX, TLO, THI, TP, STOP = 2, 12, 55, 80, 15, 55, 0.15, 20

by_hour = collections.defaultdict(list)
for m in markets:
    s = m["s"]
    n = len(s)
    ent = False
    hi = min(THI, n - 1)
    for i in range(max(TLO, N), hi):
        if ent:
            break
        for side in (1, 2):                       # 1=yes col, 2=no col
            cur_p = s[i][side]
            if cur_p - s[i - N][side] < D or not (EMIN <= cur_p <= EMAX):
                continue
            B = cur_p
            hour = s[i][0]                        # entry hour (CST)
            tppx = math.ceil(B * (1 + TP))
            out = None
            ex = None
            for j in range(i + 1, n):
                px = s[j][side]
                if px >= tppx:
                    out, ex = "TP", px
                    break
                if STOP and px <= B - STOP:
                    out, ex = "STOP", px
                    break
            if out is None:
                won = (m["res"] == ("yes" if side == 1 else "no"))
                ex = 100 if won else 0
            by_hour[hour].append((ex - B) / B)
            ent = True
            break

print("hour(CST)  trades  winRate  avgPnL   band")
tot_n = tot_w = 0
for h in sorted(by_hour):
    tr = by_hour[h]
    n = len(tr)
    w = sum(1 for p in tr if p > 0)
    wr = w / n * 100
    avg = sum(tr) / n * 100
    tot_n += n
    tot_w += w
    band = "2x  " if wr > 90 else ("0.5x" if wr < 66 else "1x  ")
    star = "  <-- " + ("STRONG" if wr >= 90 else ("WEAK" if wr < 66 else "")) if (wr >= 90 or wr < 66) else ""
    print("  %2d:00     %3d    %5.1f%%  %+5.1f%%  %s%s" % (h, n, wr, avg, band, star))
print("  TOTAL     %3d    %5.1f%%" % (tot_n, tot_w / tot_n * 100))
