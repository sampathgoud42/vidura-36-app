"""Which entry survives a protective stop best? Compare candidate entries on
realistic $ with (a) stop30+ride and (b) no-stop ride. Reads kbtc-15.log +
kalshi/kbtc15_bids_*.log. Throwaway research."""
import glob
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
CROSS = 3
STOP = 30
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
        m["winc"] = 0 if ly > ln_ else 1
    return ms


MS = load()


def mom(N, D, lo, hi, tlo, thi):
    def pick(m):
        s = m["s"]
        n = len(s)
        for i in range(max(tlo, N), min(thi, n - 1)):
            for col in (0, 1):
                if s[i][col] - s[i - N][col] >= D and lo <= s[i][col] <= hi:
                    return col, i, s[i][col]
        return None
    return pick


def fav(lo, hi, tlo, thi):
    def pick(m):
        s = m["s"]
        n = len(s)
        for i in range(tlo, min(thi, n - 1)):
            for col in (0, 1):
                if lo <= s[i][col] <= hi:
                    return col, i, s[i][col]
        return None
    return pick


def run(pick, use_stop):
    pnl = []
    for m in MS:
        e = pick(m)
        if not e:
            continue
        col, i, B = e
        buy = min(B + CROSS, 97)
        s = m["s"]
        n = len(s)
        ex = None
        if use_stop:
            for j in range(i + 1, n):
                if s[j][col] <= B - STOP:
                    ex = max(s[j][col] - CROSS, 1)
                    break
        if ex is None:
            ex = 100 if m["winc"] == col else 0
        pnl.append((ex - buy) / 100.0)
    if len(pnl) < 30:
        return None
    n = len(pnl)
    w = sum(1 for p in pnl if p > 0)
    return n, w / n * 100, sum(pnl) / n, sum(pnl)


cands = [
    ("MOM N3D8 60-88 t8-50", mom(3, 8, 60, 88, 8, 50)),
    ("MOM N3D8 60-88 t15-55", mom(3, 8, 60, 88, 15, 55)),
    ("MOM N3D8 55-80 t15-55", mom(3, 8, 55, 80, 15, 55)),
    ("FAV 70-85 t20-55", fav(70, 85, 20, 55)),
    ("FAV 78-90 t20-55", fav(78, 90, 20, 55)),
    ("FAV 82-92 t20-55", fav(82, 92, 20, 55)),
    ("FAV 75-88 t15-55", fav(75, 88, 15, 55)),
]
print(f"markets={len(MS)}  (STOP={STOP}c)")
print("%-24s | %-26s | %s" % ("entry", "stop30+ride", "no-stop ride"))
for name, pick in cands:
    a = run(pick, True)
    b = run(pick, False)
    if a and b:
        print("%-24s | n%3d WR%2.0f%% avg%+.4f tot%+5.1f | WR%2.0f%% avg%+.4f tot%+5.1f"
              % (name, a[0], a[1], a[2], a[3], b[1], b[2], b[3]))
