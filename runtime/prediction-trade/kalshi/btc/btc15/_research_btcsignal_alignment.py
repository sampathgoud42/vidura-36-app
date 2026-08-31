"""Research: does aligning a BTC directional signal (from Coinbase price momentum)
with the binary's bid direction make money? We don't need to win every time — just
+EV when signal and bid agree.
Reads kbtc-15.log + kalshi/kbtc15_bids_*.log; pulls Coinbase 5m BTC history.
Throwaway research."""
import glob
import json
import re
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
CROSS = 3
MON = {'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
       'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12}
MKT = re.compile(r"\[(KXBTC15M-\d{2}[A-Z]{3}\d{6}-\d+)\]")
TK = re.compile(r"KXBTC15M-(\d{2})([A-Z]{3})(\d{2})(\d{4})-")
BID = re.compile(r"\['yes':\s*(\d+),\s*'no':\s*(\d+)\]")


def open_utc(ticker):
    t = TK.match(ticker)
    if not t:
        return None
    yy, mon, dd, hhmm = t.groups()
    # ticker time = expiry in US Eastern (EDT, UTC-4); open = expiry - 15 min
    exp = datetime(2000 + int(yy), MON[mon], int(dd), int(hhmm[:2]), int(hhmm[2:]),
                   tzinfo=timezone(timedelta(hours=-4))).astimezone(timezone.utc)
    return exp - timedelta(minutes=15)


def load_markets():
    files = [str(Path("kbtc-15.log"))] + sorted(glob.glob(str(HERE / "kbtc15_bids_*.log")))
    ms = []
    cur = None
    for fp in files:
        if not Path(fp).exists():
            continue
        for ln in Path(fp).read_text(encoding="utf-8", errors="replace").splitlines():
            m = MKT.search(ln)
            if m and "bid price live data" in ln:
                cur = {"tk": m.group(1), "s": []}
                ms.append(cur)
            elif "[bid-price]" in ln and cur is not None:
                b = BID.search(ln)
                if b:
                    cur["s"].append((int(b.group(1)), int(b.group(2))))
    out = []
    for m in ms:
        if len(m["s"]) < 12:
            continue
        m["open"] = open_utc(m["tk"])
        if not m["open"]:
            continue
        ly, ln_ = m["s"][-1]
        m["winc"] = 0 if ly > ln_ else 1
        out.append(m)
    return out


def fetch_coinbase(start, end):
    prices = {}
    cur = start
    while cur < end:
        ce = min(cur + timedelta(hours=24), end)
        u = ("https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=300"
             f"&start={cur.isoformat()}&end={ce.isoformat()}")
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "x"})
            for row in json.loads(urllib.request.urlopen(req, timeout=12).read()):
                prices[int(row[0])] = float(row[4])     # bar_start_unix -> close
        except Exception as e:
            print("  coinbase fetch err:", e)
        cur = ce
        time.sleep(0.34)
    return prices


def btc_signal(prices, t_utc, lookback_min=15, dead=0.0003):
    # STRICT no-lookahead: only use bars that CLOSED at/before open T.
    b = (int(t_utc.timestamp()) // 300) * 300
    now = prices.get(b - 300)                        # bar [b-300,b) closed at b <= T
    prev = prices.get(b - 300 - lookback_min * 60)
    if not now or not prev:
        return None
    r = (now - prev) / prev
    return "UP" if r > dead else ("DN" if r < -dead else None)


MS = load_markets()
lo = min(m["open"] for m in MS) - timedelta(hours=1)
hi = max(m["open"] for m in MS) + timedelta(hours=1)
print(f"markets={len(MS)}  fetching Coinbase {lo.date()}..{hi.date()} ...")
PRICES = fetch_coinbase(lo, hi)
print(f"coinbase 5m bars: {len(PRICES)}")


def ev(trades):
    if len(trades) < 15:
        return None
    n = len(trades)
    w = sum(1 for p in trades if p > 0)
    return n, w / n * 100, sum(trades) / n, sum(trades)


# For each market: BTC signal at open; bid-favored side at a mid sample; resolution.
DEC = 12          # decision sample (~3 min in) for the bid-favored side
allbid, aligned, against, sigonly = [], [], [], []
for m in MS:
    sig = btc_signal(PRICES, m["open"])
    if sig is None:
        continue
    s = m["s"]
    di = min(DEC, len(s) - 2)
    yb, nb = s[di]
    fav = 0 if yb > nb else 1            # bid-favored side (0=yes/up, 1=no/down)
    favbid = yb if fav == 0 else nb
    buy = min(favbid + CROSS, 97)
    pnl_fav = ((100 if m["winc"] == fav else 0) - buy) / 100.0
    allbid.append(pnl_fav)
    sigside = 0 if sig == "UP" else 1   # signal-implied side
    agree = (sigside == fav)
    (aligned if agree else against).append(pnl_fav)
    # signal-only: buy the side the BTC signal points to, at its bid
    sb = (yb if sigside == 0 else nb)
    sigonly.append(((100 if m["winc"] == sigside else 0) - min(sb + CROSS, 97)) / 100.0)

print("\n$ per contract, hold to resolution (buy at bid+%dc):" % CROSS)
for name, tr in (("ALL bid-favored (no signal)", allbid),
                 ("bid-favored & BTC signal AGREE", aligned),
                 ("bid-favored & BTC signal DISAGREE", against),
                 ("BTC-signal side only", sigonly)):
    r = ev(tr)
    if r:
        print(f"  {name:<34} n{r[0]:>4}  WR{r[1]:4.0f}%  avg${r[2]:+.4f}  tot${r[3]:+6.1f}")
    else:
        print(f"  {name:<34} (too few)")
