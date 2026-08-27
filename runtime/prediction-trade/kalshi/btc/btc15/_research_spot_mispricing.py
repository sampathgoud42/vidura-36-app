"""Research: does BTC spot-vs-strike predict the 15-min resolution better than the
market's own bid? If the bid lags spot, there's an exploitable mispricing.
Reads kalshi/kbtc15_model_*.csv (logged by bot_learning_btc15 in paper mode).
Throwaway research."""
import csv
import glob
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CROSS = 3

rows = []
for fp in sorted(glob.glob(str(HERE / "kbtc15_model_*.csv"))):
    for r in csv.DictReader(open(fp, encoding="utf-8")):
        try:
            rows.append({
                "tk": r["ticker"], "strike": float(r["strike"] or 0),
                "spot": float(r["spot"] or 0), "dist": float(r["dist_pct"] or 0),
                "secs": int(r["secs_left"] or 0),
                "yb": int(r["yes_bid"] or 0), "nb": int(r["no_bid"] or 0),
            })
        except (ValueError, KeyError):
            pass

if len(rows) < 50:
    print(f"only {len(rows)} samples logged so far — need more data (let paper run longer).")
    raise SystemExit

# resolution per ticker: from the LAST sample's bid (yes>no -> yes won)
by_tk = defaultdict(list)
for r in rows:
    by_tk[r["tk"]].append(r)
res = {}
for tk, rs in by_tk.items():
    last = rs[-1]
    res[tk] = 1 if last["yb"] > last["nb"] else 0     # 1 = yes won
for r in rows:
    r["win"] = res[r["tk"]]

usable = [r for r in rows if r["spot"] > 0]
print(f"samples={len(usable)}  markets={len(by_tk)}  resolved yes={sum(res.values())}/{len(res)}")

# --- calibration: is the yes_bid already a fair probability? ---
print("\n[bid calibration]  yes_bid bucket -> actual P(yes win)   (gap = mispricing)")
buck = defaultdict(lambda: [0, 0])
for r in usable:
    b = r["yb"] // 10 * 10
    buck[b][0] += 1
    buck[b][1] += r["win"]
for b in sorted(buck):
    n, w = buck[b]
    if n >= 10:
        print(f"  yes_bid {b:>2}-{b+9}: implied~{b+5:>2}%  actual {w/n*100:4.0f}%  (n={n})")

# --- does spot-vs-strike add info beyond the bid? trade EV grid ---
# Rule: in the mid/late window, if spot is above strike by >= d% but yes is "cheap"
# (yes_bid <= b), BUY yes and ride to resolution. Symmetric for no.
print("\n[mispricing trade EV]  (buy the side spot favors when the bid lags) ride-to-resolution $")
print("  dist%>=  yesbid<=  secs<=   n    WR%   avg$/contract")
best = []
for d in (0.02, 0.05, 0.10):
    for bmax in (50, 60, 70):
        for smax in (900, 600, 300):
            pnl = []
            for r in usable:
                if r["secs"] > smax:
                    continue
                # spot above strike -> favor YES; below -> favor NO
                if r["dist"] >= d and r["yb"] <= bmax:
                    buy = min(r["yb"] + CROSS, 97)
                    pnl.append((100 if r["win"] == 1 else 0) - buy)
                elif r["dist"] <= -d and r["nb"] <= bmax:
                    buy = min(r["nb"] + CROSS, 97)
                    pnl.append((100 if r["win"] == 0 else 0) - buy)
            if len(pnl) >= 20:
                n = len(pnl)
                w = sum(1 for p in pnl if p > 0)
                avg = sum(pnl) / n / 100.0
                best.append((avg, d, bmax, smax, n, w / n * 100))
best.sort(reverse=True)
for avg, d, bmax, smax, n, wr in best[:12]:
    print(f"  {d:>5}    {bmax:>3}     {smax:>4}  {n:>4}  {wr:4.0f}%   {avg:+.4f}")
