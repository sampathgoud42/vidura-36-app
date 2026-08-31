#!/usr/bin/env python
"""
levels_watcher.py — intraday level-cross watcher for the index basket (SPY, QQQ, SPX).

Marks three level sets per ticker each day (all times CST):
  * yesterday_high / yesterday_low   — from yesterday's RTH session 08:30–15:00
  * postmarket_high / postmarket_low — from the extended session 15:01 → 08:29
    (SPX via ^GSPC has no extended hours, so it only gets the other two sets)
  * 10min_high / 10min_low           — today's opening range 08:30–08:40
    (available once the clock passes 08:40)

Then watches completed 5-minute candles: the FIRST close that crosses a level
(previous close on one side, this close on the other) appends a row to
day_trade.csv (scanner="levels", combo=e.g. "above_10min_high" LONG /
"below_yesterday_low" SHORT) — one row per crossing instance only.

State (last processed bar, latest signal per level) persists in
levels_state.json so restarts never re-emit old crossings, and a UI snapshot
is written to levels_status.json (served by the web-app backend so the live
desk can show the latest cross per level).

Usage:
    python levels_watcher.py                # loop, poll 60s
    python levels_watcher.py --poll 120
    python levels_watcher.py --once         # one scan then exit (testing)
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime, time as dtime
from pathlib import Path

import pandas as pd
import yfinance as yf

CST = "America/Chicago"
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

CSV_PATH = ROOT / "day_trade.csv"
CSV_COLS = ["logged_at_cst", "scanner", "direction", "ticker", "combo",
            "accuracy_pct", "bar_time_cst", "median_target",
            "price", "pct", "status"]
STATE_PATH = ROOT / "levels_state.json"
STATUS_PATH = ROOT / "levels_status.json"

TICKERS = {"SPY": "SPY", "QQQ": "QQQ", "SPX": "^GSPC"}


def now_cst() -> pd.Timestamp:
    return pd.Timestamp.now(tz=CST)


def log(msg: str) -> None:
    print(f"[levels {now_cst():%H:%M:%S}] {msg}", flush=True)


def fetch(sym: str) -> pd.DataFrame:
    df = yf.download(sym, interval="5m", period="5d", prepost=True,
                     progress=False, auto_adjust=False)
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = df.index.tz_convert(CST)
    return df


def compute_levels(df: pd.DataFrame, today) -> dict:
    """The three marked ranges (see module docstring)."""
    lv = {}
    if df.empty:
        return lv
    rth_mask = [(dtime(8, 30) <= ts.time() < dtime(15, 0)) for ts in df.index]
    rth = df[rth_mask]
    prev_days = sorted({ts.date() for ts in rth.index if ts.date() < today})
    if prev_days:
        y = prev_days[-1]
        yb = rth[[ts.date() == y for ts in rth.index]]
        if not yb.empty:
            lv["yesterday_high"] = round(float(yb["High"].max()), 2)
            lv["yesterday_low"] = round(float(yb["Low"].min()), 2)
        start = pd.Timestamp(datetime.combine(y, dtime(15, 1)), tz=CST)
        end = pd.Timestamp(datetime.combine(today, dtime(8, 30)), tz=CST)
        pm = df[(df.index >= start) & (df.index < end)]
        if not pm.empty:  # SPX/^GSPC has no EH bars -> set simply absent
            lv["postmarket_high"] = round(float(pm["High"].max()), 2)
            lv["postmarket_low"] = round(float(pm["Low"].min()), 2)
    if now_cst().time() >= dtime(8, 40):
        f10 = df[[ts.date() == today and dtime(8, 30) <= ts.time() < dtime(8, 40)
                  for ts in df.index]]
        if not f10.empty:
            lv["10min_high"] = round(float(f10["High"].max()), 2)
            lv["10min_low"] = round(float(f10["Low"].min()), 2)
    return lv


def csv_append(rows) -> None:
    new = not CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(CSV_COLS)
        for r in rows:
            w.writerow(r)


def scan_ticker(tkr: str, df: pd.DataFrame, levels: dict, tstate: dict) -> list:
    """Emit one signal per completed-5m-close crossing of each marked level."""
    if df.empty or not levels:
        return []
    today_iso = now_cst().date().isoformat()
    closes = df["Close"].dropna()
    bars = closes[[ts.date().isoformat() == today_iso for ts in closes.index]]
    if bars.empty:
        return []
    # drop the still-forming bar (its 5-min window hasn't closed yet)
    if bars.index[-1] + pd.Timedelta(minutes=5) > now_cst():
        bars = bars.iloc[:-1]
    if bars.empty:
        return []

    last_seen = tstate.get("last_bar", "")
    prev_close = tstate.get("prev_close")
    sigs = []
    for ts, close in bars.items():
        iso = ts.isoformat()
        if iso <= last_seen:
            prev_close = float(close)
            continue
        c = float(close)
        if prev_close is not None:
            for name, val in levels.items():
                sig = None
                if prev_close <= val < c:
                    sig = (f"above_{name}", "LONG")
                elif prev_close >= val > c:
                    sig = (f"below_{name}", "SHORT")
                if sig:
                    sigs.append({"time": ts, "ticker": tkr,
                                 "signal": sig[0], "dir": sig[1], "level": name})
        prev_close = c
        tstate["last_bar"] = iso
    tstate["prev_close"] = prev_close
    return sigs


def jload(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def jsave(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def cycle(state: dict) -> None:
    today = now_cst().date()
    day_key = today.isoformat()
    if state.get("day") != day_key:  # fresh day -> fresh crossing state
        state.clear()
        state["day"] = day_key
    status = {"updated": f"{now_cst():%Y-%m-%d %H:%M:%S} CST", "tickers": {}}

    for tkr, sym in TICKERS.items():
        try:
            df = fetch(sym)
        except Exception as e:
            log(f"{tkr} fetch failed: {e}")
            continue
        levels = compute_levels(df, today)
        tstate = state.setdefault(tkr, {})
        sigs = scan_ticker(tkr, df, levels, tstate)

        latest = tstate.setdefault("latest", {})
        rows = []
        for s in sigs:
            bar_hm = f"{s['time']:%H:%M}"
            rows.append([f"{now_cst():%Y-%m-%d %H:%M:%S}", "levels", s["dir"],
                         tkr, s["signal"], "", f"{s['time']:%Y-%m-%d %H:%M}", "", "", "", ""])
            # latest cross per LEVEL — a new signal from the same level overrides
            latest[s["level"]] = {"signal": s["signal"], "dir": s["dir"], "time": bar_hm}
            log(f"SIGNAL {tkr} {s['signal']} @ {bar_hm} CST")
        if rows:
            csv_append(rows)
        status["tickers"][tkr] = {"levels": levels, "latest": latest}

    jsave(STATE_PATH, state)
    jsave(STATUS_PATH, status)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    from bot_guard import ensure_single
    ensure_single(["levels_watcher.py"])

    ap = argparse.ArgumentParser(description="intraday level-cross watcher (SPY/QQQ/SPX)")
    ap.add_argument("--poll", type=int, default=60)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()

    log(f"start | tickers {list(TICKERS)} | poll {a.poll}s | csv={CSV_PATH.name}")
    state = jload(STATE_PATH)
    while True:
        try:
            cycle(state)
        except Exception as e:
            log(f"cycle error: {e}")
        if a.once:
            break
        time.sleep(a.poll)


if __name__ == "__main__":
    main()
