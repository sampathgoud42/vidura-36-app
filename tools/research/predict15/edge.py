"""predict-15 research C: does the in-window model beat Kalshi's actual prices?"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

D = Path(sys.argv[1]); DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 7
K = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = {"BTC": "KXBTC15M", "ETH": "KXETH15M"}


def ncdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def fee(p):           # Kalshi taker fee per contract, dollars
    return math.ceil(0.07 * p * (1 - p) * 100) / 100


def quotes(coin, m):
    cache = D / f"{coin}_quotes.json"
    got = json.loads(cache.read_text()) if cache.exists() else {}
    todo = [r for r in m.itertuples() if r.ticker not in got]
    for i, r in enumerate(todo):
        o = int(r.open_time.timestamp()); c = int(r.close_time.timestamp())
        for _ in range(6):
            x = requests.get(f"{K}/series/{SERIES[coin]}/markets/{r.ticker}/candlesticks",
                             params={"start_ts": o, "end_ts": c, "period_interval": 1}, timeout=30)
            if x.status_code == 429:
                time.sleep(1.5); continue
            break
        rows = {}
        if x.ok:
            for cs in x.json().get("candlesticks") or []:
                k = round((cs["end_period_ts"] - o) / 60)
                a = (cs.get("yes_ask") or {}).get("close_dollars"); b = (cs.get("yes_bid") or {}).get("close_dollars")
                rows[k] = [float(a) if a else None, float(b) if b else None]
        got[r.ticker] = rows
        if i % 100 == 0:
            cache.write_text(json.dumps(got))
        time.sleep(0.08)
    cache.write_text(json.dumps(got))
    return got


for coin in ("BTC", "ETH"):
    m = pd.read_csv(D / f"{coin}_markets.csv", parse_dates=["open_time", "close_time"])
    m = m[m["result"].isin(["yes", "no"])].sort_values("open_time")
    m = m[m["open_time"] >= m["open_time"].max() - pd.Timedelta(days=DAYS)].reset_index(drop=True)
    b = pd.read_csv(D / f"{coin}_1m.csv", parse_dates=["t"]).set_index("t").sort_index()
    b = b[~b.index.duplicated()]
    b = b.reindex(pd.date_range(b.index.min(), b.index.max(), freq="1min")).ffill()
    vol60 = np.log(b["close"]).diff().rolling(60).std()
    q = quotes(coin, m)
    print(f"\n=== {coin}: {len(m)} markets with Kalshi quotes ===")
    for k in (1, 2, 3, 5, 8):
        for edge in (0.0, 0.03, 0.05, 0.10):
            n = wins = 0; pnl = 0.0; spent = 0.0
            for r in m.itertuples():
                qq = q.get(r.ticker, {}).get(str(k))
                tk = r.open_time + pd.Timedelta(minutes=k - 1)
                if not qq or qq[0] is None or qq[1] is None or tk not in b.index:
                    continue
                ask, bid = qq
                s = b["close"][tk]; sig = vol60[r.open_time - pd.Timedelta(minutes=1)] * math.sqrt(15 - k)
                if not sig or math.isnan(sig):
                    continue
                p = ncdf(math.log(s / r.strike) / sig)
                yes = r.result == "yes"
                if p - ask > edge and 0.02 <= ask <= 0.98:
                    cost = ask + fee(ask); won = yes
                elif (1 - p) - (1 - bid) > edge and 0.02 <= bid <= 0.98:
                    cost = (1 - bid) + fee(1 - bid); won = not yes
                else:
                    continue
                n += 1; wins += won; pnl += (1.0 if won else 0.0) - cost; spent += cost
            if n:
                print(f"  T+{k}m edge>{edge:.2f}: trades={n:4d} win={wins / n:.3f} "
                      f"P&L per $1 contract={pnl:+.2f} total, {pnl / n:+.4f}/trade, ROI={pnl / spent:+.3%}")
