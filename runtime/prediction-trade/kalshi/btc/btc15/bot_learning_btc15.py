#!/usr/bin/env python
"""
bot_learning_btc15.py — KXBTC15M bid-movement bot (data-driven, no signals).

This bot REUSES only the Kalshi API client/calls from bot_kalshi_btc15.py (v1):
auth + req, fresh-market detection, per-side bid reads, and the V2 order builder.
It deliberately IGNORES v1's signal/direction, pre-buy logic, and TP-sell monitor.

Strategy (derived purely from kbtc-15.log bid prices):
  Backtest of 486 KXBTC15M markets (yes/no bids every 15s) found a momentum-
  breakout that clears a +15% take-profit with >70% win rate:

    ENTRY  — a side's bid jumps >= 12c over 30s (2 samples), while that bid sits
             in the 55..80c band, during the mid-window (sample 15..55, i.e. ~3.75
             to ~13.75 min after we start watching the market). Buy that side.
    EXIT   — take-profit at +15% of the entry bid, OR hard stop at -20c, whichever
             first; force-flat just before the market closes.

    Backtest: 309 trades, 76.1% win rate, avg win +21.1%, net +6.3%/trade
              (stop -20c keeps losers off the -100% resolution outcome).

All thresholds are hard-coded below (no .env). Trading is DRY by default; pass
``live=true`` (or LEARN_LIVE=true) to place real orders.
"""

from __future__ import annotations

import asyncio
import csv
import glob
import json
import math
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import bot_kalshi_btc15 as v1          # API client + low-level calls ONLY

KalshiClient = v1.KalshiClient

# ── hard-coded strategy params (from the kbtc-15.log backtest) ──────────────────
POLL_S          = 15      # bid sampling cadence (matches the log: every 15s)
# Strategy: "bidlag" = buy the side BTC spot DECISIVELY favors while its Kalshi bid
# still lags (the only edge that survived no-lookahead research, +$0.05/contract,
# 73% WR). "momentum" = the legacy bid-breakout (no edge — kept for comparison).
STRATEGY        = "bidlag"
BIDLAG_DIST_MIN = 0.05    # |spot-strike|/strike % must exceed this (decisive move)
BIDLAG_BID_MAX  = 70      # ...while the spot-favored side's bid is still <= this (lagging)
# Entry (from realistic $ research: this config rides to resolution at +$0.029/contract):
MOMENTUM_WINDOW = 3       # samples (=45s) over which to measure the jump
MOMENTUM_JUMP   = 8       # >= this many cents up over the window => breakout entry
ENTRY_MIN       = 60      # only enter when the firing side's bid is in this band
ENTRY_MAX       = 88
ENTRY_T_LO      = 15      # earliest sample to enter (~3.75 min) - later entries survive the stop
ENTRY_T_HI      = 55      # latest sample index to enter (~13.75 min)
# Exit: ride toward RESOLUTION (no TP cap — that killed the edge) WITH a protective
# WIDE stop. Research: ride+stop30 = +$0.006/contract (62% WR) and caps the worst
# loss at ~-35% vs -100% no-stop; a tight stop (<=20c) gaps through and goes negative.
HOLD_TO_RESOLUTION = True   # ride to settlement (100/0) unless the protective stop trips
TP_PCT          = 0.15      # (legacy TP — NOT used in hold-to-resolution mode)
STOP_CENTS      = 30        # protective stop: exit if the bid falls this far below entry
CONTRACTS       = 10        # BASE size (small — modest edge, higher variance)
BUY_CROSS       = 3       # cross the spread up by this many cents to fill the buy
SELL_CROSS      = 3       # cross down by this many cents to fill the exit
EXPIRY_BUFFER_S = 20      # force-flat this many seconds before the market closes

# ── time-of-day sizing (from kbtc-15.log per-hour backtest, CST) ───────────────
# The strategy's historical win rate varies sharply by hour. We scale size:
#   WR > WR_2X   -> 2x base   (strong windows, e.g. 10:00 / 16:00 / 17:00)
#   WR < WR_HALF -> 0.5x base (weak windows, negative expectancy)
#   otherwise    -> 1x base
WR_2X   = 90              # hour win rate strictly above this -> double size
WR_HALF = 66             # hour win rate strictly below this -> half size
# CST hour -> historical win rate % of the strategy's entries in that hour.
HOUR_WR = {
    0: 61, 1: 86, 2: 69, 3: 88, 4: 70, 5: 84, 6: 61, 7: 79, 8: 89, 9: 68,
    10: 94, 11: 62, 12: 73, 13: 64, 14: 65, 15: 73, 16: 92, 17: 100, 18: 73,
    19: 83, 20: 58, 21: 85, 22: 44, 23: 54,
}


# ── self-optimization (every REOPT_HOURS, re-read bid logs + trades) ───────────
REOPT_HOURS       = 6              # re-optimize this often
MIN_HOUR_SAMPLES  = 12            # need this many trades in an hour to trust its stats (robustness)
MIN_BASE          = 10            # base-contract floor
MAX_BASE          = 40            # base-contract ceiling (caps "double on profit")
MAX_TRADE         = 80            # hard per-trade contract cap after the hour multiplier
SCALE_DOWN_USD    = 10.0          # if a 6h window loses more than this, halve base
# HOUR_MULT (hour -> multiplier, 0 = SKIP the hour) is learned by _reoptimize and
# persisted to STATE_PATH; until then it's empty and we fall back to _size_mult.
HOUR_MULT: dict = {}


def _size_mult(hour: int) -> float:
    wr = HOUR_WR.get(hour, 70)          # unknown hour -> treat as normal (1x)
    if wr > WR_2X:
        return 2.0
    if wr < WR_HALF:
        return 0.5
    return 1.0


def _sized_contracts(hour: int) -> tuple[int, float, int]:
    """(count, mult, hour_wr) for the current hour's time-boxed size.
    count==0 means SKIP (a learned negative-expectancy hour)."""
    wr = int(round(HOUR_WR.get(hour, 70)))
    mult = HOUR_MULT.get(hour, _size_mult(hour)) if HOUR_MULT else _size_mult(hour)
    count = min(MAX_TRADE, round(CONTRACTS * mult))
    return max(0, count), mult, wr

# Kalshi V2 create-order endpoint — hard-coded here (NOT read from .env) so order
# placement has no env dependency beyond the API credentials in v1.KalshiClient.
ORDER_PATH      = "/portfolio/events/orders"


def _parse_live() -> bool:
    for a in sys.argv[1:]:
        if a.lower().startswith("live="):
            return a.split("=", 1)[1].strip().lower() in ("1", "true", "yes", "y", "on")
    return os.getenv("LEARN_LIVE", "false").strip().lower() in ("1", "true", "yes", "y", "on")


DRY = not _parse_live()                # DRY by default; opt in to live with live=true


def _log(msg: str) -> None:
    print(f"[{v1._cst_now():%H:%M:%S}] {msg}", flush=True)


# ── persistent data for future optimization ───────────────────────────────────
# 1) every trade with P/L (append, survives restarts)  2) the 15s bid stream in the
#    same format as kbtc-15.log so the analysis scripts can re-derive the model.
TRADE_CSV = _HERE / ("trade_history_learn_btc15_paper.csv" if DRY
                     else "trade_history_learn_btc15.csv")
_CSV_COLS = ["date_time_CST", "ticker", "hour", "side", "entry_bid", "buy_price",
             "exit_bid", "sell_price", "contracts", "mult", "hour_wr", "reason",
             "pnl_pct", "pnl_dollars", "result"]


def _init_csv() -> None:
    if not TRADE_CSV.exists():
        with open(TRADE_CSV, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(_CSV_COLS)


def _log_trade(row: dict) -> None:
    _init_csv()
    with open(TRADE_CSV, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([row.get(c, "") for c in _CSV_COLS])


def _bid_log_path() -> Path:
    return _HERE / f"kbtc15_bids_{v1._cst_now():%Y%m%d}.log"


def _bid_log(line: str) -> None:
    try:
        with open(_bid_log_path(), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── research data: (spot vs strike) mispricing dataset ─────────────────────────
# These markets are "BTC >= strike (the open price) in 15 min". Logging BTC spot +
# the strike + the bid each tick lets us later test whether spot-vs-strike predicts
# resolution better than the binary's own bid (the only path to a real edge).
_MODEL_COLS = ["ts", "ticker", "strike", "spot", "dist_pct", "secs_left", "yes_bid", "no_bid"]


def _model_log_path() -> Path:
    return _HERE / f"kbtc15_model_{v1._cst_now():%Y%m%d}.csv"


def _model_log(row: dict) -> None:
    p = _model_log_path()
    try:
        new = not p.exists()
        with open(p, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(_MODEL_COLS)
            w.writerow([row.get(c, "") for c in _MODEL_COLS])
    except Exception:
        pass


def _btc_spot() -> float:
    """Live BTC spot from Coinbase (plain HTTP, no auth). 0.0 on failure."""
    try:
        req = urllib.request.Request("https://api.coinbase.com/v2/prices/BTC-USD/spot",
                                     headers={"User-Agent": "kbtc15"})
        with urllib.request.urlopen(req, timeout=4) as r:
            return float(json.loads(r.read().decode())["data"]["amount"])
    except Exception:
        return 0.0


# ── self-optimization engine ──────────────────────────────────────────────────
STATE_PATH = _HERE / ("learn_btc15_state_paper.json" if DRY else "learn_btc15_state.json")
_MKT_RE = re.compile(r"\[(KXBTC15M-[^\]]+)\]")
_BID_RE = re.compile(r"\['yes':\s*(\d+),\s*'no':\s*(\d+)\]")
_TIME_RE = re.compile(r"\[(\d\d):(\d\d):(\d\d)\]")
_REOPT = {"last_cum": 0.0}        # cumulative $ at the previous re-optimization


def _bid_log_files() -> list:
    """All bid-price logs to learn from: the seed kbtc-15.log (repo root) + every
    daily log this bot has written."""
    files = []
    seed = _HERE.parent / "kbtc-15.log"
    if seed.exists():
        files.append(str(seed))
    files += sorted(glob.glob(str(_HERE / "kbtc15_bids_*.log")))
    return files


def _per_hour_stats() -> dict:
    """Replay the CURRENT entry/exit rules over all bid logs; return
    hour -> list of trade pnl fractions (bid-to-bid)."""
    markets = []
    for fp in _bid_log_files():
        cur = None
        try:
            lines = Path(fp).read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for ln in lines:
            if "bid price live data" in ln and _MKT_RE.search(ln):
                cur = {"s": []}
                markets.append(cur)
            elif "[bid-price]" in ln and cur is not None:
                b, t = _BID_RE.search(ln), _TIME_RE.search(ln)
                if b and t:
                    cur["s"].append((int(t.group(1)), int(b.group(1)), int(b.group(2))))
    by_hour: dict = {}
    for m in markets:
        s = m["s"]
        n = len(s)
        if n < 8:
            continue
        ly, ln_ = s[-1][1], s[-1][2]
        res = "yes" if ly > ln_ else "no"
        ent = False
        for i in range(max(ENTRY_T_LO, MOMENTUM_WINDOW), min(ENTRY_T_HI, n - 1)):
            if ent:
                break
            for col, name in ((1, "yes"), (2, "no")):
                cur_p = s[i][col]
                if cur_p - s[i - MOMENTUM_WINDOW][col] < MOMENTUM_JUMP or not (ENTRY_MIN <= cur_p <= ENTRY_MAX):
                    continue
                B = cur_p
                hour = s[i][0]
                buy = min(B + BUY_CROSS, 97)
                if HOLD_TO_RESOLUTION:           # ride to settlement, protective stop caps tail
                    ex = None
                    for j in range(i + 1, n):
                        px = s[j][col]
                        if STOP_CENTS and px <= B - STOP_CENTS:
                            ex = max(px - SELL_CROSS, 1)
                            break
                    if ex is None:
                        ex = 100 if res == name else 0
                else:
                    tppx = math.ceil(B * (1 + TP_PCT))
                    ex = None
                    for j in range(i + 1, n):
                        px = s[j][col]
                        if px >= tppx:
                            ex = px
                            break
                        if px <= B - STOP_CENTS:
                            ex = max(px - SELL_CROSS, 1)
                            break
                    if ex is None:
                        ex = 100 if res == name else 0
                by_hour.setdefault(hour, []).append((ex - buy) / 100.0)   # $ per contract
                ent = True
                break
    return by_hour


def _mult_from_stats(tr: list) -> float:
    """Per-hour multiplier from its $/contract history: skip losing hours, 2x for
    strong+profitable, 0.5x weak-but-positive, else 1x."""
    n = len(tr)
    if n < MIN_HOUR_SAMPLES:
        return 1.0
    wr = sum(1 for p in tr if p > 0) / n * 100
    avg = sum(tr) / n                     # $ per contract
    if avg <= 0:
        return 0.0                       # negative expectancy -> SKIP the hour
    if wr > WR_2X and avg > 0.03:
        return 2.0
    if wr < WR_HALF:
        return 0.5
    return 1.0


def _csv_cum_pnl() -> float:
    try:
        tot = 0.0
        with open(TRADE_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    tot += float(row.get("pnl_dollars") or 0)
                except ValueError:
                    pass
        return tot
    except Exception:
        return 0.0


def _save_state() -> None:
    try:
        STATE_PATH.write_text(json.dumps({
            "updated": f"{v1._cst_now():%Y-%m-%d %H:%M:%S}",
            "base_contracts": CONTRACTS,
            "hour_mult": {str(k): v for k, v in HOUR_MULT.items()},
            "hour_wr": {str(k): v for k, v in HOUR_WR.items()},
            "last_cum": _REOPT["last_cum"],
        }, indent=2), encoding="utf-8")
    except Exception as e:
        _log(f"[REOPT] state save failed: {e}")


def _load_state() -> bool:
    global CONTRACTS, HOUR_MULT, HOUR_WR
    try:
        d = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return False
    CONTRACTS = max(MIN_BASE, min(MAX_BASE, int(d.get("base_contracts", CONTRACTS))))
    HOUR_MULT = {int(k): float(v) for k, v in d.get("hour_mult", {}).items()}
    if d.get("hour_wr"):
        HOUR_WR = {int(k): float(v) for k, v in d["hour_wr"].items()}
    _REOPT["last_cum"] = float(d.get("last_cum", 0.0))
    return True


def _reoptimize() -> None:
    """Re-read all bid logs -> refresh per-hour multipliers (skip losing hours);
    scale base size by the last window's realized P/L (double on profit, halve on
    a big loss); persist. Called at startup and every REOPT_HOURS."""
    global HOUR_MULT, HOUR_WR, CONTRACTS
    bh = _per_hour_stats()
    new_mult, new_wr = {}, {}
    for h in range(24):
        tr = bh.get(h, [])
        if len(tr) >= MIN_HOUR_SAMPLES:
            new_mult[h] = _mult_from_stats(tr)
            new_wr[h] = round(sum(1 for p in tr if p > 0) / len(tr) * 100)
        else:                                   # too little data -> keep prior/default
            new_mult[h] = HOUR_MULT.get(h, _size_mult(h))
            new_wr[h] = round(HOUR_WR.get(h, 70))
    HOUR_MULT, HOUR_WR = new_mult, new_wr

    cum = _csv_cum_pnl()
    delta = cum - _REOPT["last_cum"]
    old_base = CONTRACTS
    if delta > 0:                               # profitable window -> grow size
        CONTRACTS = min(MAX_BASE, CONTRACTS * 2)
    elif delta < -SCALE_DOWN_USD:               # bad window -> cut size
        CONTRACTS = max(MIN_BASE, CONTRACTS // 2)
    _REOPT["last_cum"] = cum
    _save_state()

    two = sorted(h for h, m in HOUR_MULT.items() if m >= 2)
    skip = sorted(h for h, m in HOUR_MULT.items() if m == 0)
    half = sorted(h for h, m in HOUR_MULT.items() if m == 0.5)
    _log(f"[REOPT] base {old_base}->{CONTRACTS} (window P/L ${delta:+.2f}, cum ${cum:+.2f})  "
         f"2x={two}  1x=rest  0.5x={half}  SKIP={skip}")


async def _reoptimize_loop() -> None:
    while True:
        await asyncio.sleep(REOPT_HOURS * 3600)
        try:
            await asyncio.to_thread(_reoptimize)
        except Exception as e:
            _log(f"[REOPT] error: {e}")


def _parse_close(mkt: dict):
    ct = mkt.get("close_time") or mkt.get("expiration_time") or ""
    if not ct:
        return None
    try:
        return datetime.fromisoformat(ct.replace("Z", "+00:00"))
    except Exception:
        return None


async def _bids(c: KalshiClient, ticker: str):
    """(yes_cents, no_cents) or None — reuses v1's robust per-side bid reader."""
    yb = await v1._bid_price(c, ticker, "yes")
    nb = await v1._bid_price(c, ticker, "no")
    if yb is None or nb is None:
        return None
    return int(round(yb * 100)), int(round(nb * 100))


async def _place(c: KalshiClient, ticker: str, action: str, side: str, price_c: int,
                 count: int) -> None:
    """Place a buy/sell via v1's V2 order builder (honours DRY)."""
    price_c = max(1, min(99, int(price_c)))
    order = v1._mk_order(ticker, action, side, count, price_c)
    if DRY:
        _log(f"  [DRY] {action.upper()} {side.upper()} x{count} @ {price_c}c")
        return
    try:
        await c.req("POST", ORDER_PATH, body=order)
        _log(f"  [LIVE] {action.upper()} {side.upper()} x{count} @ {price_c}c — sent")
    except Exception as e:
        _log(f"  [ORDER] {action} {side} FAILED: {e}")


async def _enter(c: KalshiClient, ticker: str, side: str, bid_c: int, idx: int) -> dict:
    buy_px = min(bid_c + BUY_CROSS, 97)
    hour = v1._cst_now().hour
    count, mult, hwr = _sized_contracts(hour)          # time-boxed size
    exitnote = (f"ride+STOP{bid_c - STOP_CENTS}c" if HOLD_TO_RESOLUTION
                else f"TP{math.ceil(bid_c * (1 + TP_PCT))}c/STOP{bid_c - STOP_CENTS}c")
    _log(f"  >>> ENTER {side.upper()} bid={bid_c}c (idx {idx})  buy@{buy_px}c  "
         f"{exitnote}  | {hour:02d}:00 -> {mult:g}x = {count} contracts")
    await _place(c, ticker, "buy", side, buy_px, count)
    return {"ticker": ticker, "side": side, "entry_ref": bid_c, "buy_px": buy_px,
            "count": count, "hour": hour, "mult": mult, "hour_wr": hwr}


async def _exit(c: KalshiClient, ticker: str, pos: dict, bid_c: int, reason: str,
                stats: dict) -> None:
    sell_px = max(bid_c - SELL_CROSS, 1)
    await _place(c, ticker, "sell", pos["side"], sell_px, pos["count"])
    pnl = (bid_c - pos["entry_ref"]) / pos["entry_ref"] * 100.0
    pnl_usd = (sell_px - pos["buy_px"]) / 100.0 * pos["count"]   # real $ on order prices
    result = "win" if pnl > 0 else "loss"
    stats["n"] += 1
    stats["pnl"] += pnl
    stats["usd"] = stats.get("usd", 0.0) + pnl_usd
    if pnl > 0:
        stats["wins"] += 1
    wr = stats["wins"] / stats["n"] * 100.0
    _log(f"  <<< EXIT {reason} {pos['side'].upper()} x{pos['count']} bid={bid_c}c  "
         f"pnl={pnl:+.1f}% (${pnl_usd:+.2f})  | trades={stats['n']} WR={wr:.0f}% "
         f"avg={stats['pnl'] / stats['n']:+.1f}% cum=${stats['usd']:+.2f}")
    _log_trade({
        "date_time_CST": f"{v1._cst_now():%Y-%m-%d %H:%M:%S}", "ticker": ticker,
        "hour": pos["hour"], "side": pos["side"], "entry_bid": pos["entry_ref"],
        "buy_price": pos["buy_px"], "exit_bid": bid_c, "sell_price": sell_px,
        "contracts": pos["count"], "mult": pos["mult"], "hour_wr": pos["hour_wr"],
        "reason": reason, "pnl_pct": round(pnl, 2), "pnl_dollars": round(pnl_usd, 2),
        "result": result,
    })


async def _settle(c: KalshiClient, ticker: str, pos: dict, yc: int, nc: int,
                  stats: dict) -> None:
    """Hold-to-resolution close: NO sell order — the contract settles at 100/0 at
    expiry. P/L is settlement minus what we paid."""
    won = (pos["side"] == "yes" and yc > nc) or (pos["side"] == "no" and nc > yc)
    exit_px = 100 if won else 0
    pnl = (exit_px - pos["entry_ref"]) / pos["entry_ref"] * 100.0
    pnl_usd = (exit_px - pos["buy_px"]) / 100.0 * pos["count"]
    result = "win" if won else "loss"
    stats["n"] += 1
    stats["pnl"] += pnl
    stats["usd"] = stats.get("usd", 0.0) + pnl_usd
    if won:
        stats["wins"] += 1
    wr = stats["wins"] / stats["n"] * 100.0
    _log(f"  <<< SETTLE {pos['side'].upper()} x{pos['count']} -> {exit_px} "
         f"(paid {pos['buy_px']}c)  pnl={pnl:+.1f}% (${pnl_usd:+.2f})  | "
         f"trades={stats['n']} WR={wr:.0f}% cum=${stats['usd']:+.2f}")
    _log_trade({
        "date_time_CST": f"{v1._cst_now():%Y-%m-%d %H:%M:%S}", "ticker": ticker,
        "hour": pos["hour"], "side": pos["side"], "entry_bid": pos["entry_ref"],
        "buy_price": pos["buy_px"], "exit_bid": (yc if pos["side"] == "yes" else nc),
        "sell_price": exit_px, "contracts": pos["count"], "mult": pos["mult"],
        "hour_wr": pos["hour_wr"], "reason": "SETTLE", "pnl_pct": round(pnl, 2),
        "pnl_dollars": round(pnl_usd, 2), "result": result,
    })


async def trade_market(c: KalshiClient, mkt: dict, stats: dict) -> None:
    """Watch ONE market: sample bids, take the first momentum entry, manage to
    TP/stop (or force-flat at expiry). One trade per market (matches backtest)."""
    ticker = mkt["ticker"]
    close_dt = _parse_close(mkt)
    try:
        strike = float(mkt.get("floor_strike") or 0)     # "BTC >= strike in 15 min"
    except (TypeError, ValueError):
        strike = 0.0
    yes_hist: list[int] = []
    no_hist: list[int] = []
    pos = None
    skip_logged = False
    _log(f"[MARKET] watching {ticker}"
         + (f" (closes {close_dt.astimezone():%H:%M:%S})" if close_dt else ""))
    _bid_log(f"[{ticker}] [yes and no] bid price live data for every 15 seconds")
    while True:
        if close_dt and v1._utc_now() >= close_dt - timedelta(seconds=EXPIRY_BUFFER_S):
            if pos:
                if HOLD_TO_RESOLUTION:
                    await _settle(c, ticker, pos,
                                  yes_hist[-1] if yes_hist else 0,
                                  no_hist[-1] if no_hist else 0, stats)
                else:
                    last = (yes_hist[-1] if pos["side"] == "yes" else no_hist[-1]) if yes_hist else pos["entry_ref"]
                    await _exit(c, ticker, pos, last, "EXPIRY", stats)
            _log(f"[MARKET] {ticker} ending")
            return
        b = await _bids(c, ticker)
        if b is None:
            await asyncio.sleep(POLL_S)
            continue
        yc, nc = b
        yes_hist.append(yc)
        no_hist.append(nc)
        idx = len(yes_hist) - 1
        # persist the bid stream in kbtc-15.log format (for re-analysis)
        _bid_log(f"[bid-price] [{v1._cst_now():%H:%M:%S}] ['yes': {yc}, 'no':{nc}]")
        # BTC spot + research dataset (spot vs strike + time-left, alongside the bid)
        spot = 0.0
        dist = 0.0
        secs_left = (close_dt - v1._utc_now()).total_seconds() if close_dt else 0
        if strike > 0:
            spot = await asyncio.to_thread(_btc_spot)
            dist = (spot - strike) / strike * 100 if spot else 0.0
            _model_log({
                "ts": f"{v1._cst_now():%Y-%m-%d %H:%M:%S}", "ticker": ticker,
                "strike": round(strike, 2), "spot": round(spot, 2),
                "dist_pct": (round(dist, 4) if spot else ""),
                "secs_left": int(secs_left), "yes_bid": yc, "no_bid": nc,
            })
        jump = f"  dist{dist:+.3f}%" if (STRATEGY == "bidlag" and spot) else ""
        if STRATEGY != "bidlag" and idx >= MOMENTUM_WINDOW:
            dy = yc - yes_hist[-1 - MOMENTUM_WINDOW]
            dn = nc - no_hist[-1 - MOMENTUM_WINDOW]
            jump = f"  d30s yes{dy:+d} no{dn:+d}"
        _log(f"  [bid] idx={idx:>2} yes={yc:>3} no={nc:>3}{jump}"
             + (f"  [{pos['side'].upper()} @{pos['entry_ref']}c]" if pos else ""))

        if pos is None:
            hour = v1._cst_now().hour
            if STRATEGY == "bidlag":
                # buy the side spot decisively favors while its bid still lags
                if spot and abs(dist) >= BIDLAG_DIST_MIN:
                    side, sbid = ("yes", yc) if dist > 0 else ("no", nc)
                    if sbid <= BIDLAG_BID_MAX and _sized_contracts(hour)[0] >= 1:
                        pos = await _enter(c, ticker, side, sbid, idx)
            elif ENTRY_T_LO <= idx <= ENTRY_T_HI and idx >= MOMENTUM_WINDOW:
                if _sized_contracts(hour)[0] < 1:           # learned skip hour
                    if not skip_logged:
                        _log(f"  [SKIP] {hour:02d}:00 is time-boxed out (0x) — not trading this hour")
                        skip_logged = True
                else:
                    for side, hist, cur in (("yes", yes_hist, yc), ("no", no_hist, nc)):
                        if (cur - hist[-1 - MOMENTUM_WINDOW] >= MOMENTUM_JUMP
                                and ENTRY_MIN <= cur <= ENTRY_MAX):
                            pos = await _enter(c, ticker, side, cur, idx)
                            break
        else:
            cur = yc if pos["side"] == "yes" else nc
            B = pos["entry_ref"]
            if HOLD_TO_RESOLUTION:
                # ride to settlement, but a protective wide stop caps the tail
                if STOP_CENTS and cur <= B - STOP_CENTS:
                    await _exit(c, ticker, pos, cur, "STOP", stats)
                    return
            else:                                    # legacy TP/stop mode
                if cur >= math.ceil(B * (1 + TP_PCT)):
                    await _exit(c, ticker, pos, cur, "TP", stats)
                    return
                if cur <= B - STOP_CENTS:
                    await _exit(c, ticker, pos, cur, "STOP", stats)
                    return
        await asyncio.sleep(POLL_S)


async def run() -> None:
    exitdesc = (f"ride-to-resolution + stop-{STOP_CENTS}c" if HOLD_TO_RESOLUTION
                else f"TP+{TP_PCT*100:.0f}%/STOP-{STOP_CENTS}c")
    entrydesc = (f"BIDLAG |dist|>={BIDLAG_DIST_MIN}% & favbid<={BIDLAG_BID_MAX}c"
                 if STRATEGY == "bidlag"
                 else f"momentum +{MOMENTUM_JUMP}c/{MOMENTUM_WINDOW*POLL_S}s in {ENTRY_MIN}-{ENTRY_MAX}c")
    print(f"[LEARN-BTC15] series={v1.SERIES}  strategy={STRATEGY}  entry: {entrydesc}  "
          f"exit: {exitdesc}  size={CONTRACTS} x time-of-day  "
          f"{'DRY-RUN' if DRY else 'LIVE'}", flush=True)
    strong = [h for h in HOUR_WR if HOUR_WR[h] > WR_2X]
    weak = [h for h in HOUR_WR if HOUR_WR[h] < WR_HALF]
    print(f"[LEARN-BTC15] 2x hours(CST)={sorted(strong)}  0.5x hours={sorted(weak)}", flush=True)
    if DRY:
        print("[LEARN-BTC15] DRY by default — pass live=true (or LEARN_LIVE=true) to trade.",
              flush=True)
    _init_csv()
    print(f"[LEARN-BTC15] trade log -> {TRADE_CSV.name}  |  bid log -> {_bid_log_path().name}",
          flush=True)
    if _load_state():
        print(f"[LEARN-BTC15] restored learned state from {STATE_PATH.name} "
              f"(base={CONTRACTS})", flush=True)
    print(f"[LEARN-BTC15] self-optimizing every {REOPT_HOURS}h "
          f"(base capped {MIN_BASE}-{MAX_BASE}, per-trade cap {MAX_TRADE}); "
          f"running initial pass…", flush=True)
    _REOPT["last_cum"] = _csv_cum_pnl()         # baseline scaling to THIS run's CSV (no stale delta)
    await asyncio.to_thread(_reoptimize)        # learn from accumulated bid logs now
    c = KalshiClient()
    stats = {"n": 0, "wins": 0, "pnl": 0.0, "usd": 0.0}

    async def _trade_forever():
        last = None
        while True:
            mkt = await v1.wait_for_market(c, skip=last)
            await trade_market(c, mkt, stats)
            last = mkt["ticker"]

    try:
        await asyncio.gather(_trade_forever(), _reoptimize_loop())
    finally:
        try:
            await c.close()
        except Exception:
            pass


def main() -> None:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    asyncio.run(run())


if __name__ == "__main__":
    main()
