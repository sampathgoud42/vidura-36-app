#!/usr/bin/env python
"""
bot_btc15_momentum.py — PAPER momentum bot for KXBTC15M (Kalshi 15-min BTC binaries).

Reuses v1's (bot_kalshi_btc15.py) fast-poll price-momentum signal — a deque of bid
prices fed to compute_signal (EMA3 vs EMA10 + OLS slope + uptick/downtick) — to enter,
then takes profit aggressively at +15%. PAPER ONLY (no orders); P&L is computed
specifically for the binary contracts (cents -> dollars). Self-stops after RUN_HOURS.

Aggressive: act on the first buy/sell signal, re-enter after each exit.
"""
from __future__ import annotations

import asyncio
import csv
import sys
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import bot_kalshi_btc15 as v1          # API client + compute_signal ONLY

KalshiClient = v1.KalshiClient

# ── params (paper; override via CLI args e.g. tp=0.15 stop=30 hours=3) ─────────
def _argf(key: str, default: float) -> float:
    for a in sys.argv[1:]:
        if a.lower().startswith(key + "="):
            try:
                return float(a.split("=", 1)[1])
            except ValueError:
                return default
    return default


POLL_S      = 0.5                          # fast poll (matches v1's 500ms cadence)
DEQUE_N     = 20                           # rolling window for compute_signal (needs >=16)
TP_PCT      = _argf("tp", 0.15)            # take profit at +TP% of entry
STOP_CENTS  = int(_argf("stop", 30))       # protective stop (caps the -100% tail; >=100 = ride)
CONTRACTS   = int(_argf("contracts", 10))  # paper size
CROSS       = int(_argf("cross", 2))       # cents crossed to fill
ENTRY_MIN   = int(_argf("entrymin", 0))    # only enter when the buy price is >= this
ENTRY_MAX   = int(_argf("entrymax", 100))  # ...and <= this (cap how expensive an entry)
RUN_HOURS   = _argf("hours", 3.0)          # self-stop after this long
EXPIRY_BUF  = 20                           # settle this many seconds before close
_T0 = time.time()


def _elapsed_h() -> float:
    return (time.time() - _T0) / 3600.0


def _log(msg: str) -> None:
    print(f"[{v1._cst_now():%H:%M:%S}] {msg}", flush=True)


# persistent trade log so 3h cycles ACCUMULATE (append; survives restarts)
TRADE_CSV = _HERE / "trade_history_mom_btc15.csv"
_CSV_COLS = ["ts", "ticker", "side", "buy", "sell", "reason", "tp_pct", "stop_c",
             "pnl_pct", "pnl_usd", "result"]


def _csv(row: dict) -> None:
    try:
        new = not TRADE_CSV.exists()
        with open(TRADE_CSV, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(_CSV_COLS)
            w.writerow([row.get(c, "") for c in _CSV_COLS])
    except Exception:
        pass


async def _poll(c: KalshiClient, ticker: str):
    """One GET -> (yes_cents, no_cents) or None."""
    try:
        d = await c.req("GET", f"/markets/{ticker}", params={"_": v1._ts_ms()})
        m = d.get("market", {})
    except Exception:
        return None

    def bid(side):
        r = m.get(f"{side}_bid_dollars")
        if r is not None and float(r) >= 0:
            return round(float(r) * 100)
        r = m.get(f"{side}_bid")
        if r is not None and float(r) >= 0:
            return round(float(r))
        return None
    yb, nb = bid("yes"), bid("no")
    return (yb, nb) if (yb is not None and nb is not None) else None


def _close_dt(mkt: dict):
    ct = mkt.get("close_time") or ""
    try:
        return datetime.fromisoformat(ct.replace("Z", "+00:00"))
    except Exception:
        return None


async def trade_market(c: KalshiClient, mkt: dict, stats: dict) -> None:
    ticker = mkt["ticker"]
    close_dt = _close_dt(mkt)
    yd: deque = deque(maxlen=DEQUE_N)        # YES bid (dollars) for the signal
    pos = None                                # {side, buy, tp, stop}
    last_yc = last_nc = 0
    _log(f"[MARKET] {ticker}" + (f" closes {close_dt.astimezone():%H:%M:%S}" if close_dt else ""))
    while True:
        if close_dt and v1._utc_now() >= close_dt - timedelta(seconds=EXPIRY_BUF):
            if pos:                                   # settle at resolution
                won = (pos["side"] == "yes" and last_yc > last_nc) or \
                      (pos["side"] == "no" and last_nc > last_yc)
                _close_trade(pos, 100 if won else 0, "SETTLE", stats)
            return
        b = await _poll(c, ticker)
        if b is None:
            await asyncio.sleep(POLL_S)
            continue
        yc, nc = b
        last_yc, last_nc = yc, nc
        yd.append(yc / 100.0)

        if pos is None:
            sig = v1.compute_signal(yd)
            if sig == "buy":                          # YES momentum up -> buy YES
                pos = _open("yes", 100 - nc, stats, ticker)     # pay YES ask = 100 - no_bid
            elif sig in ("sell", "strong_sell"):      # YES momentum down -> buy NO
                pos = _open("no", 100 - yc, stats, ticker)
        else:
            sell = yc if pos["side"] == "yes" else nc  # current sell-bid of held side
            if sell >= pos["tp"]:
                _close_trade(pos, sell, "TP", stats)
                pos = None
            elif sell <= pos["stop"]:
                _close_trade(pos, sell, "STOP", stats)
                pos = None
        await asyncio.sleep(POLL_S)


def _open(side: str, buy_cents: int, stats: dict, ticker: str) -> dict:
    buy = max(1, min(99, buy_cents + CROSS))
    tp = round(buy * (1 + TP_PCT))
    stop = buy - STOP_CENTS
    _log(f"  >>> BUY {side.upper()} x{CONTRACTS} @ {buy}c   TP={tp}c STOP={stop}c   ({ticker[-8:]})")
    return {"side": side, "buy": buy, "tp": tp, "stop": stop, "ticker": ticker}


def _close_trade(pos: dict, exit_cents: int, reason: str, stats: dict) -> None:
    sell = max(1, exit_cents - (CROSS if reason != "SETTLE" else 0))
    pnl_usd = (sell - pos["buy"]) / 100.0 * CONTRACTS         # btc15 cents -> $
    pnl_pct = (sell - pos["buy"]) / pos["buy"] * 100.0
    stats["n"] += 1
    stats["usd"] += pnl_usd
    if pnl_usd > 0:
        stats["wins"] += 1
    wr = stats["wins"] / stats["n"] * 100.0
    _log(f"  <<< {reason} {pos['side'].upper()} {pos['buy']}->{sell}c  "
         f"pnl={pnl_pct:+.0f}% (${pnl_usd:+.2f})  | trades={stats['n']} WR={wr:.0f}% "
         f"cum=${stats['usd']:+.2f}")
    _csv({"ts": f"{v1._cst_now():%Y-%m-%d %H:%M:%S}", "ticker": pos.get("ticker", ""),
          "side": pos["side"], "buy": pos["buy"], "sell": sell, "reason": reason,
          "tp_pct": TP_PCT, "stop_c": STOP_CENTS, "pnl_pct": round(pnl_pct, 1),
          "pnl_usd": round(pnl_usd, 2), "result": "win" if pnl_usd > 0 else "loss"})


async def run() -> None:
    print(f"[MOM-BTC15] PAPER  poll={POLL_S}s  signal=v1.compute_signal  TP+{TP_PCT*100:.0f}% "
          f"STOP-{STOP_CENTS}c  x{CONTRACTS}  aggressive  run={RUN_HOURS}h", flush=True)
    c = KalshiClient()
    stats = {"n": 0, "wins": 0, "usd": 0.0}
    last = None
    try:
        while _elapsed_h() < RUN_HOURS:
            try:
                mkt = await v1.wait_for_market(c, skip=last)
                await trade_market(c, mkt, stats)
                last = mkt["ticker"]
            except Exception as e:
                _log(f"[ERR] {e}")
                await asyncio.sleep(2)
    finally:
        print(f"\n[MOM-BTC15] DONE after {_elapsed_h():.2f}h  |  trades={stats['n']}  "
              f"WR={ (stats['wins']/stats['n']*100) if stats['n'] else 0:.0f}%  "
              f"cum=${stats['usd']:+.2f}", flush=True)
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
