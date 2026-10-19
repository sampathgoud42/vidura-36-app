"""Research data for predict-15: settled Kalshi 15m markets + Coinbase 1m bars."""
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

OUT = Path(sys.argv[1])
DAYS = int(sys.argv[2]) if len(sys.argv) > 2 else 21
K = "https://api.elections.kalshi.com/trade-api/v2"
CB = "https://api.exchange.coinbase.com/products/{p}/candles"
COINS = {"BTC": ("KXBTC15M", "BTC-USD"), "ETH": ("KXETH15M", "ETH-USD")}
now = datetime.now(timezone.utc)
since = now - timedelta(days=DAYS)


def markets(series):
    rows, cursor = [], None
    while True:
        p = {"series_ticker": series, "status": "settled", "limit": 1000,
             "min_close_ts": int(since.timestamp())}
        if cursor:
            p["cursor"] = cursor
        for _ in range(5):
            r = requests.get(f"{K}/markets", params=p, timeout=30)
            if r.status_code == 429:
                time.sleep(2); continue
            r.raise_for_status(); break
        d = r.json()
        for m in d.get("markets") or []:
            rows.append({"ticker": m["ticker"], "open_time": m["open_time"], "close_time": m["close_time"],
                         "strike": m.get("floor_strike"), "final": m.get("expiration_value"),
                         "result": m.get("result"), "volume": m.get("volume_fp")})
        cursor = d.get("cursor")
        if not cursor:
            return pd.DataFrame(rows)


def candles(product):
    out, end = [], now
    while end > since - timedelta(hours=6):
        start = end - timedelta(minutes=300)
        for _ in range(5):
            r = requests.get(CB.format(p=product), params={
                "granularity": 60, "start": start.isoformat(), "end": end.isoformat()}, timeout=30)
            if r.status_code == 429:
                time.sleep(1); continue
            r.raise_for_status(); break
        out += r.json()
        end = start
        time.sleep(0.12)
    df = pd.DataFrame(out, columns=["t", "low", "high", "open", "close", "volume"]).drop_duplicates("t")
    df["t"] = pd.to_datetime(df["t"], unit="s", utc=True)
    return df.sort_values("t").reset_index(drop=True)


OUT.mkdir(parents=True, exist_ok=True)
for coin, (series, product) in COINS.items():
    m = markets(series)
    m.to_csv(OUT / f"{coin}_markets.csv", index=False)
    print(coin, "markets", len(m), m["result"].value_counts().to_dict())
    c = candles(product)
    c.to_csv(OUT / f"{coin}_1m.csv", index=False)
    print(coin, "bars", len(c), c["t"].min(), c["t"].max())
