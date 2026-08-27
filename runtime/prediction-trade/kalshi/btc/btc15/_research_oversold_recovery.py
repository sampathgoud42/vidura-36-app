"""Research: a side's bid drops BELOW 20c early (first ~5-6 min). If you buy it
there, how often does it recover +50% / +100% / +300%, or win outright (->100)?
Reads kbtc-15.log + kalshi/kbtc15_bids_*.log. Throwaway research."""
import glob
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CROSS = 3                 # realistic: buy a bit above the dip bid, sell a bit below the peak
EARLY = 24                # samples from watch start = ~6 min (15s cadence)
DIP = 20                  # "drops below" this many cents
MKT = re.compile(r"\[(KXBTC15M-[^\]]+)\]")
BID = re.compile(r"\['yes':\s*(\d+),\s*'no':\s*(\d+)\]")


def load():
    files = []
    seed = HERE.parent / "kbtc-15.log"
    if seed.exists():
        files.append(str(seed))
    files += sorted(glob.glob(str(HERE / "kbtc15_bids_*.log")))
    ms = []
    for fp in files:
        cur = None
        for ln in Path(fp).read_text(encoding="utf-8", errors="replace").splitlines():
            if "bid price live data" in ln and MKT.search(ln):
                cur = {"s": []}
                ms.append(cur)
            elif "[bid-price]" in ln and cur is not None:
                b = BID.search(ln)
                if b:
                    cur["s"].append((int(b.group(1)), int(b.group(2))))
    ms = [m for m in ms if len(m["s"]) >= 12]
    for m in ms:
        ly, ln_ = m["s"][-1]
        m["winc"] = 0 if ly > ln_ else 1     # 0 = yes won, 1 = no won
    return ms


MS = load()

instances = []       # (col, entry_idx, entry_bid, peak_after, won)
for m in MS:
    s = m["s"]
    n = len(s)
    for col in (0, 1):
        # first time in the early window the side's bid drops below DIP
        ei = None
        for i in range(0, min(EARLY, n - 2)):
            if s[i][col] < DIP:
                ei = i
                break
        if ei is None:
            continue
        entry = s[ei][col]
        if entry < 3:        # too close to 0 to model a fill
            continue
        peak = max(s[j][col] for j in range(ei + 1, n))
        instances.append((col, ei, entry, peak, 1 if m["winc"] == col else 0))

N = len(instances)
print(f"markets={len(MS)}   oversold instances (a side < {DIP}c within first {EARLY*15//60} min) = {N}")
if N == 0:
    raise SystemExit

def pct(cond):
    return sum(1 for x in instances if cond(x)) / N * 100

# recovery odds (peak bid vs entry bid)
r50 = pct(lambda x: x[3] >= x[2] * 1.5)
r100 = pct(lambda x: x[3] >= x[2] * 2)
r200 = pct(lambda x: x[3] >= x[2] * 3)
r300 = pct(lambda x: x[3] >= x[2] * 4)
won = pct(lambda x: x[4] == 1)
print(f"\nRECOVERY ODDS (peak bid after the dip, before close):")
print(f"  reaches +50%  (1.5x): {r50:5.1f}%")
print(f"  reaches +100% (2x):   {r100:5.1f}%")
print(f"  reaches +200% (3x):   {r200:5.1f}%")
print(f"  reaches +300% (4x):   {r300:5.1f}%")
print(f"  wins outright (->100): {won:5.1f}%")
avg_entry = sum(x[2] for x in instances) / N
print(f"  avg dip-entry bid: {avg_entry:.1f}c")

# $ EV of strategies. $ per contract.
def ev(mode, tp_mult=None, cross=CROSS):
    pnl = []
    for col, ei, entry, peak, won in instances:
        buy = min(entry + cross, 97)
        if mode == "hold":                       # ride to resolution
            ex = 100 if won else 0
        elif mode == "peak":                     # theoretical best: sell exact peak
            ex = max(peak - cross, 1)
        elif mode == "tp":                       # sell if peak hits tp_mult*entry, else resolution
            tp = entry * tp_mult
            ex = max(int(tp) - cross, 1) if peak >= tp else (100 if won else 0)
        pnl.append((ex - buy) / 100.0)
    n = len(pnl)
    return sum(pnl) / n, sum(pnl), sum(1 for p in pnl if p > 0) / n * 100

for cross in (CROSS, 0):
    tag = f"realistic (cross {cross}c)" if cross else "ZERO spread (perfect limit fills)"
    print(f"\n$ EV per contract — {tag}:")
    a = ev("hold", cross=cross)
    print(f"  hold to resolution:        avg ${a[0]:+.3f}  total ${a[1]:+.1f}  win {a[2]:.0f}%")
    for mlt, lbl in ((1.5, "+50%"), (2, "+100%"), (3, "+200%")):
        a = ev("tp", mlt, cross=cross)
        print(f"  sell at {lbl} (else hold):   avg ${a[0]:+.3f}  total ${a[1]:+.1f}  win {a[2]:.0f}%")
    a = ev("peak", cross=cross)
    print(f"  sell the EXACT peak (ideal): avg ${a[0]:+.3f}  total ${a[1]:+.1f}  win {a[2]:.0f}%")
