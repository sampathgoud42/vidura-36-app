"""Research: does ANY entry have a real dollar edge on KXBTC15M, riding to
resolution (the only non-negative exit)? Realistic fills (entry crosses spread).
Tests momentum, fade-the-spike, favorite-continuation, rising-underdog.
Reads kbtc-15.log + kalshi/kbtc15_bids_*.log. Throwaway research."""
import glob
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CROSS = 3
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
    ms = [m for m in ms if len(m["s"]) >= 8]
    for m in ms:
        ly, ln_ = m["s"][-1]
        m["win"] = (0 if ly > ln_ else 1)        # 0=yes wins, 1=no wins
    return ms


MS = load()


def evalE(pick):
    """pick(m) -> (col, buy_bid) for one entry, or None. Ride to resolution.
    Returns (n, wr, avg$/contract, total$)."""
    pnl = []
    for m in MS:
        r = pick(m)
        if not r:
            continue
        col, bid = r
        buy = min(bid + CROSS, 97)
        exit_px = 100 if m["win"] == col else 0
        pnl.append((exit_px - buy) / 100.0)
    if len(pnl) < 30:
        return None
    n = len(pnl)
    w = sum(1 for p in pnl if p > 0)
    return n, w / n * 100, sum(pnl) / n, sum(pnl)


def mk_mom(N, D, lo, hi, tlo, thi, fade=False):
    def pick(m):
        s = m["s"]
        n = len(s)
        for i in range(max(tlo, N), min(thi, n - 1)):
            for col in (0, 1):
                if s[i][col] - s[i - N][col] >= D and lo <= s[i][col] <= hi:
                    if fade:
                        other = 1 - col
                        return other, s[i][other]
                    return col, s[i][col]
        return None
    return pick


def mk_fav(lo, hi, tlo, thi):
    def pick(m):
        s = m["s"]
        n = len(s)
        for i in range(tlo, min(thi, n - 1)):
            for col in (0, 1):
                if lo <= s[i][col] <= hi:
                    return col, s[i][col]
        return None
    return pick


rows = []
# momentum continuation
for N in (2, 3):
    for D in (8, 12, 18):
        for (lo, hi) in ((55, 80), (60, 88), (45, 70)):
            for (tlo, thi) in ((8, 50), (15, 55)):
                r = evalE(mk_mom(N, D, lo, hi, tlo, thi))
                if r:
                    rows.append(("MOM", f"N{N}D{D} {lo}-{hi} t{tlo}-{thi}", r))
# fade the spike (buy opposite)
for N in (2, 3):
    for D in (8, 12, 18, 25):
        for (lo, hi) in ((55, 85), (60, 92), (70, 95)):
            for (tlo, thi) in ((8, 50), (15, 55)):
                r = evalE(mk_mom(N, D, lo, hi, tlo, thi, fade=True))
                if r:
                    rows.append(("FADE", f"N{N}D{D} spk{lo}-{hi} t{tlo}-{thi}", r))
# favorite continuation
for (lo, hi) in ((78, 90), (82, 92), (85, 95), (70, 85)):
    for (tlo, thi) in ((20, 55), (30, 55), (40, 58)):
        r = evalE(mk_fav(lo, hi, tlo, thi))
        if r:
            rows.append(("FAV", f"{lo}-{hi} t{tlo}-{thi}", r))
# rising underdog (cheap & rising)
for N in (2, 3):
    for D in (5, 8):
        for (lo, hi) in ((15, 40), (20, 45)):
            r = evalE(mk_mom(N, D, lo, hi, 8, 55))
            if r:
                rows.append(("UDOG", f"N{N}D{D} {lo}-{hi}", r))

rows.sort(key=lambda x: x[2][2], reverse=True)
print(f"markets={len(MS)}")
print("family  config                      n    WR%   avg$/contract  total$")
for fam, cfg, (n, wr, avg, tot) in rows[:22]:
    print("%-5s   %-26s %4d  %4.0f%%   %+.4f       %+.2f" % (fam, cfg, n, wr, avg, tot))
