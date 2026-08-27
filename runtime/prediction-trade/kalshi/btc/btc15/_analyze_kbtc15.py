"""Backtest entry/exit rules on kbtc-15.log bid prices.
Find configs hitting +TP with >70% win rate. Throwaway analysis script."""
import re, math
from pathlib import Path

txt = Path("kbtc-15.log").read_text(encoding="utf-8", errors="replace").splitlines()
mkt_re = re.compile(r"\[(KXBTC15M-[^\]]+)\]")
bid_re = re.compile(r"\[bid-price\]\s*\[(\d\d:\d\d:\d\d)\]\s*\['yes':\s*(\d+),\s*'no':\s*(\d+)\]")
markets = []
cur = None
for ln in txt:
    m = mkt_re.search(ln)
    if m and "bid price live data" in ln:
        cur = {"ticker": m.group(1), "s": []}
        markets.append(cur)
        continue
    b = bid_re.search(ln)
    if b and cur is not None:
        cur["s"].append((int(b.group(2)), int(b.group(3))))
markets = [m for m in markets if len(m["s"]) >= 8]
for m in markets:
    ly, ln_ = m["s"][-1]
    m["res"] = "YES" if ly > ln_ else ("NO" if ln_ > ly else "TIE")


def sim(N, D, emin, emax, t_lo, t_hi, tp, stop):
    """Momentum entry: side rose >=D over N samples, bid in [emin,emax], between
    sample t_lo..t_hi. Exit at +tp (TP), -stop cents (STOP), or resolution."""
    tr = []
    for m in markets:
        s = m["s"]
        n = len(s)
        ent = False
        hi = min(t_hi, n - 1)
        for i in range(max(t_lo, N), hi):
            if ent:
                break
            for side in (0, 1):
                cur_p = s[i][side]
                prev_p = s[i - N][side]
                if cur_p - prev_p < D or not (emin <= cur_p <= emax):
                    continue
                B = cur_p
                tppx = math.ceil(B * (1 + tp))
                out = None
                ex = None
                for j in range(i + 1, n):
                    px = s[j][side]
                    if px >= tppx:
                        out, ex = "TP", px
                        break
                    if stop and px <= B - stop:
                        out, ex = "STOP", px
                        break
                if out is None:
                    won = (m["res"] == ("YES" if side == 0 else "NO"))
                    ex = 100 if won else 0
                tr.append((ex - B) / B)
                ent = True
                break
    if len(tr) < 25:
        return None
    wins = sum(1 for p in tr if p > 0)
    return len(tr), wins / len(tr), sum(tr) / len(tr)


best = []
for N in (2, 3, 4):
    for D in (3, 5, 8, 12):
        for (emin, emax) in ((55, 80), (60, 85), (65, 88), (70, 90), (75, 92), (50, 75), (78, 90)):
            for (tlo, thi) in ((1, 55), (8, 50), (15, 55), (20, 55)):
                for stop in (6, 10, 15, 20):
                    r = sim(N, D, emin, emax, tlo, thi, 0.15, stop)
                    if r and r[1] > 0.70 and r[0] >= 30:
                        best.append((r[1], r[2], r[0], N, D, emin, emax, tlo, thi, stop))
best.sort(reverse=True)
print("configs with WR>70%% & >=30 trades: %d" % len(best))
print("WR    avgPnL  n    N  D  band    time    stop")
for b in best[:20]:
    print("%.3f %+.3f  %3d   %d  %2d %2d-%2d %2d-%2d  %2d" %
          (b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7], b[8], b[9]))
