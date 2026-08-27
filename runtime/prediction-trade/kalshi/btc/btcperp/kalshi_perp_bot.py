#!/usr/bin/env python3
"""
kalshi_perp_bot.py — Kalshi PERPETUALS (margin) bot, driven by crypto_signals.

Signal source: stock-trading/crypto_signals.py (Coinbase 24x7 engine).
  • discover_crypto() builds the priority signal table (refreshed periodically),
  • getTheSignalCrypto() returns the live LONG/SHORT hit for BTC.

Flow (BTC and ETH managed concurrently, each its own position):
  1. Read the symbol's signal (LONG / SHORT / none) from crypto_signals.
  2. On LONG/SHORT and no open position for that symbol → open in that direction,
     sized to (perp balance × PERP_PER_SYMBOL_PCT%) margin × PERP_LEVERAGE (6x).
  3. While holding: TP at +PERP_PROFIT_PCT% (default 3%) → close; OR if the signal
     flips to the OPPOSITE direction before TP → exit immediately (reduce-only).
  4. Log to trade_history_perp.csv; repeat.

Balance is the PERPETUAL (margin) account (/margin/balance), used only for sizing.
NO portfolio checks/halts.  NO fixed stop-loss — the opposite-signal flip is the
exit/protection.  POC/VIDYA signals removed.

⚠️  PERPS ARE LEVERAGED (6x here).  With DRY_RUN_MODE=FALSE this places REAL
    leveraged orders.  Test with DRY_RUN_MODE=TRUE first.

.env: PERP_SYMBOLS (BTC,ETH), PERP_PER_SYMBOL_PCT (50), PERP_LEVERAGE (6),
      PERP_PROFIT_PCT (3), DRY_RUN_MODE.

Run:  python kalshi/kalshi_perp_bot.py
"""
from __future__ import annotations

import asyncio
import csv
import math
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))                 # project root
sys.path.insert(0, str(_HERE))                        # kalshi/

import bot_kalshi_btc15 as v1                          # noqa: E402  (auth/infra)

# crypto_signals lives in the stock-trading/ folder; import is heavy (numpy/pandas/
# Coinbase) so guard it and fail loud.
try:
    sys.path.insert(0, str(_HERE.parent / "stock-trading"))
    import crypto_signals as cs                        # noqa: E402
    _HAS_CS = True
except Exception as _e:                                # pragma: no cover
    cs = None
    _HAS_CS = False
    print(f"[PERP] crypto_signals unavailable: {_e}")

KalshiClient       = v1.KalshiClient
_cst_now           = v1._cst_now

DRY_RUN            = v1.DRY_RUN

# ── config (.env) ─────────────────────────────────────────────────────────────
# NOTE: no portfolio checks/halts — balance is read only to size the position.
# Trade BTC and ETH perps concurrently, each sized to a share of the perp balance.
PERP_SYMBOLS         = [s.strip().upper() for s in
                        os.getenv("PERP_SYMBOLS", "BTC,ETH").split(",") if s.strip()]
# Each symbol sizes off the FULL available perp cash × the market's MAX leverage
# (leverage_estimate, e.g. BTC ~6x / ETH ~4.5x); whichever fires first uses the
# margin, the other is margin-limited until it closes.
LEVERAGE             = float(os.getenv("PERP_LEVERAGE", "6"))        # fallback if market has no estimate
SIZE_BUFFER          = float(os.getenv("PERP_SIZE_BUFFER", "0.97"))  # leave room for fees on full-cash sizing
PROFIT_PCT           = float(os.getenv("PERP_PROFIT_PCT", "3"))      # TP at +3%
STOP_PCT             = float(os.getenv("PERP_STOP_PCT", "10"))       # SL at -10%
RECHECK_S            = int(os.getenv("PERP_RECHECK_S", "15"))        # idle re-check
MONITOR_POLL_S       = int(os.getenv("PERP_MONITOR_POLL_S", "10"))   # mark-price poll
SIGNAL_POLL_S        = int(os.getenv("PERP_SIGNAL_POLL_S", "60"))    # signal-flip poll
DISCOVER_REFRESH_S   = int(float(os.getenv("PERP_DISCOVER_REFRESH_H", "6")) * 3600)
DISCOVER_HOURS       = int(os.getenv("PERP_DISCOVER_HOURS", "120"))  # discovery lookback (5 days)
MIN_SIGNALS_PER_DAY  = float(os.getenv("PERP_MIN_SIGNALS_PER_DAY", "3"))  # keep combos firing >= this/day
HEARTBEAT_S          = int(os.getenv("PERP_HEARTBEAT_S", "300"))     # log "no signal" at most this often
CSV_PERP             = _HERE / os.getenv("PERP_CSV", "trade_history_perp.csv")


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _parse_buy() -> bool:
    """BUY gate: when True the bot places live orders; when False it only emits
    signals (banners), no orders/flatten.  Set via CLI arg ``buy=true`` or env
    ``PERP_BUY``.  Defaults to FALSE (signals-only) so trading is opt-in."""
    for a in sys.argv[1:]:
        if a.lower().startswith("buy="):
            return _truthy(a.split("=", 1)[1])
    return _truthy(os.getenv("PERP_BUY", "false"))


BUY = _parse_buy()

_STATE: dict = {"table": None}          # shared signal table (refreshed periodically)
_LAST_SCAN: dict = {}                   # per-symbol last heartbeat timestamp
_LAST_BANNER: dict = {}                 # per-symbol (direction, bar_time) last bannered


def _ticker_for(symbol: str) -> str:
    return f"KX{symbol}PERP"


_CSV_COLS = ["date_time_CST", "symbol", "side", "buy_price", "sell_price",
             "profit_loss_pct", "perp_balance", "max_loss_pct", "max_profit_pct"]


# ── helpers ───────────────────────────────────────────────────────────────────
def _pf(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _mark(m: dict) -> float:
    rp = m.get("reference_price") or {}
    return _pf(rp.get("price")) or _pf(m.get("price"))


def _bid(m: dict) -> float:
    return _pf(m.get("bid"))


def _ask(m: dict) -> float:
    return _pf(m.get("ask"))


def _tick(m: dict) -> float:
    return _pf(m.get("tick_size")) or 0.0001


def _max_leverage(m: dict) -> float:
    """Market's max usable leverage (from leverage_estimate), floored to the UI
    step, e.g. 4.5382 -> 4.5 (ETH), 6.0143 -> 6.0 (BTC).  Falls back to LEVERAGE."""
    lev = _pf(m.get("leverage_estimate")) or LEVERAGE
    return max(1.0, math.floor(lev * 10) / 10.0)


def _tick_decimals(tick: float) -> int:
    s = ("%.10f" % tick).rstrip("0")
    return len(s.split(".")[1]) if "." in s else 0


def _fmt_price(price: float, tick: float) -> str:
    """Round ``price`` to the market tick and format with the tick's decimals
    (Kalshi rejects extra precision, e.g. 6 decimals on a 0.0001 tick)."""
    tick = tick or 0.0001
    price = round(round(price / tick) * tick, 10)
    return f"{price:.{_tick_decimals(tick)}f}"


async def perp_balance(c: KalshiClient) -> float:
    """
    Funds in the PERPETUAL (margin) account in USD — from /margin/balance (NOT the
    main /portfolio/balance).  Uses total account_equity across subaccounts (the
    balance shown in the Kalshi perp account, e.g. $101.96); falls back to
    available_balance, then settled_funds.
    """
    d = await c.req("GET", "/margin/balance")
    subs = d.get("subaccount_balances", [])
    equity = sum(_pf(s.get("account_equity")) for s in subs)
    avail = sum(_pf(s.get("available_balance")) for s in subs)
    return equity or avail or _pf(d.get("settled_funds"))


async def perp_available(c: KalshiClient) -> float:
    """Deployable cash to open a NEW position (free margin) — sum of
    available_balance across subaccounts; falls back to settled_funds, then equity.
    This is what gets multiplied by leverage to size an entry (committing more than
    this is rejected for insufficient margin)."""
    d = await c.req("GET", "/margin/balance")
    subs = d.get("subaccount_balances", [])
    avail = sum(_pf(s.get("available_balance")) for s in subs)
    if avail > 0:
        return avail
    settled = _pf(d.get("settled_funds"))
    if settled > 0:
        return settled
    return sum(_pf(s.get("account_equity")) for s in subs)


def _init_csv() -> None:
    if not CSV_PERP.exists():
        with open(CSV_PERP, "w", newline="") as f:
            csv.writer(f).writerow(_CSV_COLS)


def _log_trade(symbol, side, buy_px, sell_px, pnl_pct, bal, max_loss, max_profit) -> None:
    ts = _cst_now().strftime("%Y-%m-%d %H:%M:%S")
    with open(CSV_PERP, "a", newline="") as f:
        csv.writer(f).writerow([
            ts, symbol, side, round(buy_px or 0, 2), round(sell_px or 0, 2),
            round(pnl_pct, 3), round(bal, 2),
            round(max_loss, 3), round(max_profit, 3),
        ])


# ── big block-letter signal banner ────────────────────────────────────────────
# 5-row block font (█ = filled); width is per-glyph, 1-space gap between glyphs.
_FONT = {
    "A": [" ███ ", "█   █", "█████", "█   █", "█   █"],
    "B": ["████ ", "█   █", "████ ", "█   █", "████ "],
    "C": [" ████", "█    ", "█    ", "█    ", " ████"],
    "D": ["████ ", "█   █", "█   █", "█   █", "████ "],
    "E": ["█████", "█    ", "███  ", "█    ", "█████"],
    "F": ["█████", "█    ", "███  ", "█    ", "█    "],
    "G": [" ████", "█    ", "█  ██", "█   █", " ████"],
    "H": ["█   █", "█   █", "█████", "█   █", "█   █"],
    "I": ["█████", "  █  ", "  █  ", "  █  ", "█████"],
    "K": ["█   █", "█  █ ", "███  ", "█  █ ", "█   █"],
    "L": ["█    ", "█    ", "█    ", "█    ", "█████"],
    "N": ["█   █", "██  █", "█ █ █", "█  ██", "█   █"],
    "O": [" ███ ", "█   █", "█   █", "█   █", " ███ "],
    "P": ["████ ", "█   █", "████ ", "█    ", "█    "],
    "R": ["████ ", "█   █", "████ ", "█  █ ", "█   █"],
    "S": [" ████", "█    ", " ███ ", "    █", "████ "],
    "T": ["█████", "  █  ", "  █  ", "  █  ", "  █  "],
    "U": ["█   █", "█   █", "█   █", "█   █", " ███ "],
    "V": ["█   █", "█   █", "█   █", " █ █ ", "  █  "],
    " ": ["   ", "   ", "   ", "   ", "   "],
}


def _render_big(text: str) -> list:
    """Render ``text`` as 5 rows of block letters (1-space gap between glyphs)."""
    rows = ["", "", "", "", ""]
    for ch in text.upper():
        g = _FONT.get(ch, _FONT[" "])
        for i in range(5):
            rows[i] += g[i] + " "
    return [r.rstrip() for r in rows]


def _signal_banner(direction: str, symbol: str, combo: str = "",
                   accuracy=None, when=None) -> str:
    """Big block-letter banner for a fired signal (▲ LONG / ▼ SHORT)."""
    d = (direction or "").upper()
    arrow = "▲" if d == "LONG" else "▼"
    big = _render_big(f"{d} {symbol}")
    width = max(max((len(r) for r in big), default=0), 56)
    bar = arrow * width
    meta1 = f"  {combo}".rstrip() if combo else ""
    if accuracy is not None:
        meta1 = f"{meta1}  |  acc {accuracy:.0f}%" if meta1 else f"  acc {accuracy:.0f}%"
    meta2 = "  bar "
    if when is not None:
        try:
            meta2 += f"{when:%m-%d-%Y %H:%M} CST"
        except Exception:
            meta2 += str(when)
    return "\n".join([""] + [bar] + big + [meta1, meta2.rstrip(), bar] + [""])


# ── crypto_signals integration ────────────────────────────────────────────────
def _discover_table():
    """Build the BTC/ETH signal priority table (heavy brute-force backtest).
    Returns the table or None (getTheSignalCrypto then uses its fallback table)."""
    if not _HAS_CS:
        return None
    try:
        print(f"  [DISCOVER] scanning last {DISCOVER_HOURS}h "
              f"(>= {MIN_SIGNALS_PER_DAY:g} signals/day) for {','.join(PERP_SYMBOLS)}…")
        table, _rep = cs.discover_crypto(PERP_SYMBOLS, hours=DISCOVER_HOURS,
                                         min_per_day=MIN_SIGNALS_PER_DAY, verbose=True)
        print(f"  [DISCOVER] {len(table)} priority combos for {','.join(PERP_SYMBOLS)}")
        return table
    except Exception as e:
        print(f"  [DISCOVER] error: {e} — will use fallback table")
        return None


async def _signal_hit(symbol: str, table):
    """Live signal HIT for ``symbol`` (object with .direction/.combo/.accuracy/
    .bar_time_cst) or None.  Runs the heavy crypto_signals scan in a worker thread
    so the event loop stays responsive (symbol loops + mark monitors keep ticking)."""
    if not _HAS_CS:
        return None
    try:
        hits = await asyncio.to_thread(cs.getTheSignalCrypto, [symbol],
                                       signals_table=table, verbose=False)
    except Exception as e:
        print(f"  [SIGNAL] {symbol} crypto_signals error: {e}")
        return None
    for h in hits:
        if symbol in (getattr(h, "tickers", []) or []):
            if (getattr(h, "direction", "") or "").upper() in ("LONG", "SHORT"):
                return h
    return None


async def _signal(symbol: str, table) -> Optional[str]:
    """Live signal direction for ``symbol``: 'LONG' | 'SHORT' | None."""
    h = await _signal_hit(symbol, table)
    d = (getattr(h, "direction", "") or "").upper() if h else ""
    return d if d in ("LONG", "SHORT") else None


async def _table_refresh_loop() -> None:
    """Rebuild the shared signal table every DISCOVER_REFRESH_S (in a thread)."""
    while True:
        await asyncio.sleep(DISCOVER_REFRESH_S)
        t = await asyncio.to_thread(_discover_table)
        if t:
            _STATE["table"] = t


# ── perp market / order helpers ───────────────────────────────────────────────
async def get_perp_market(c: KalshiClient, ticker: str) -> Optional[dict]:
    try:
        d = await c.req("GET", "/margin/markets", params={"limit": 1000})
    except Exception as e:
        print(f"  [PERP] markets fetch error: {e}")
        return None
    for m in d.get("markets", []):
        if m.get("ticker") == ticker:
            return m
    return None


async def place_perp_order(
    c: KalshiClient, ticker: str, side: str, count: int, price: float,
    *, tick: float = 0.0001, reduce_only: bool = False, tif: str = "immediate_or_cancel",
) -> Optional[dict]:
    """side = 'bid' (LONG/buy) | 'ask' (SHORT/sell).  price = $/contract (rounded to tick)."""
    px = _fmt_price(price, tick)
    body = {
        "ticker": ticker, "side": side, "count": f"{int(count):.2f}",
        "price": px, "time_in_force": tif,
        "self_trade_prevention_type": "taker_at_cross",
        "client_order_id": str(uuid.uuid4()),
    }
    if reduce_only:
        body["reduce_only"] = True
    tag = "[DRY] " if DRY_RUN else ""
    print(f"  {tag}[PERP ORDER] {side.upper()} x{count} @ ${px} reduce_only={reduce_only}")
    if DRY_RUN:
        return {"order_id": f"DRY-{uuid.uuid4().hex[:8]}",
                "average_fill_price": px,
                "fill_count": f"{int(count):.2f}", "status": "filled"}
    try:
        return await c.req("POST", "/margin/orders", body=body)
    except Exception as e:
        print(f"  [PERP ORDER] FAILED: {e}")
        return None


async def _monitor(c: KalshiClient, symbol: str, ticker: str, side: str,
                   count: int, entry_px: float) -> tuple[str, float, float, float, float]:
    """
    Hold a position and exit on the FIRST of: take-profit at +PROFIT_PCT,
    stop-loss at -STOP_PCT, or a signal flip to the opposite direction.
    Returns (result, exit_mark, pnl, max_p, max_l).
    """
    max_p, max_l, pnl_pct = 0.0, 0.0, 0.0
    opp = "SHORT" if side == "LONG" else "LONG"
    last_sig = time.time()
    while True:
        m = await get_perp_market(c, ticker)
        mark = _mark(m) if m else 0.0
        if mark > 0:
            pnl_pct = ((mark - entry_px) / entry_px * 100.0 if side == "LONG"
                       else (entry_px - mark) / entry_px * 100.0)
            max_p, max_l = max(max_p, pnl_pct), min(max_l, pnl_pct)
            print(f"  [MON {symbol}] {side} mark=${mark:.4f} entry=${entry_px:.4f} "
                  f"pnl={pnl_pct:+.2f}%  (TP+{PROFIT_PCT:.0f}% / SL-{STOP_PCT:.0f}%)")
            if pnl_pct >= PROFIT_PCT:
                return "TP", mark, pnl_pct, max_p, max_l
            if pnl_pct <= -STOP_PCT:
                print(f"  [SL {symbol}] pnl {pnl_pct:+.2f}% <= -{STOP_PCT:.0f}% — stopping out")
                return "SL", mark, pnl_pct, max_p, max_l
        if time.time() - last_sig >= SIGNAL_POLL_S:
            last_sig = time.time()
            if await _signal(symbol, _STATE["table"]) == opp:
                print(f"  [FLIP {symbol}] signal -> {opp} (opposite of {side}) — exiting")
                return "FLIP", mark, pnl_pct, max_p, max_l
        await asyncio.sleep(MONITOR_POLL_S)


async def _open_position(c: KalshiClient, ticker: str) -> Optional[tuple]:
    """Net open position for ``ticker`` across subaccounts → (side, count, avg_entry)
    or None.  Lets the bot ADOPT an existing position after a restart instead of
    orphaning it."""
    try:
        d = await c.req("GET", "/margin/positions")
    except Exception:
        return None
    total = cost = 0.0
    for p in d.get("positions", d.get("market_positions", [])):
        if p.get("market_ticker") != ticker:
            continue
        q = _pf(p.get("position") or p.get("position_fp"))
        if q == 0:
            continue
        total += q
        cost += q * _pf(p.get("entry_price"))
    if abs(total) < 1:
        return None
    side = "LONG" if total > 0 else "SHORT"
    return side, abs(int(round(total))), (cost / total if total else 0.0)


async def _sweep_close(c: KalshiClient, ticker: str, *, max_attempts: int = 12) -> None:
    """Reduce-only close the net position for ``ticker`` until flat.  Perp books are
    thin, so a single IOC fills only a few contracts — this re-checks and re-fires,
    pricing ~1% through the touch to sweep depth (reduce_only caps the fill at the
    open position, so the wider limit only improves fill, never overshoots)."""
    for _ in range(max_attempts):
        pos = await _open_position(c, ticker)
        if not pos:
            return
        side, count, entry = pos
        m = await get_perp_market(c, ticker)
        if side == "LONG":
            cs_, px = "ask", (_bid(m) * 0.99 if (m and _bid(m) > 0) else entry)
        else:
            cs_, px = "bid", (_ask(m) * 1.01 if (m and _ask(m) > 0) else entry)
        await place_perp_order(c, ticker, cs_, count, px,
                               tick=_tick(m) if m else 0.0001,
                               reduce_only=True, tif="immediate_or_cancel")
        await asyncio.sleep(1.5)


async def _close(c: KalshiClient, symbol: str, ticker: str, side: str, count: int,
                 exit_mark: float, result: str, pnl_pct: float, max_l: float, max_p: float) -> None:
    """Fully close the position (reduce-only sweep) and log the trade."""
    mc = await get_perp_market(c, ticker)
    close_px = (_bid(mc) if side == "LONG" else _ask(mc)) if mc else exit_mark
    if close_px <= 0:
        close_px = exit_mark
    print(f"  [{result} {symbol}] pnl={pnl_pct:+.2f}% — closing {count} @ ${close_px:.4f}")
    await _sweep_close(c, ticker)
    left = await _open_position(c, ticker)
    if left:
        print(f"  [{result} {symbol}] WARNING not fully closed: {left}")
    bal = await perp_balance(c)
    _log_trade(symbol, side, exit_mark, close_px, pnl_pct, bal, max_l, max_p)
    print(f"  [LOGGED {symbol}] {result} pnl={pnl_pct:+.2f}% bal=${bal:.2f}")


async def _trade_symbol(c: KalshiClient, symbol: str) -> None:
    """Independent position manager for one symbol: open on signal (full available
    cash × max leverage), manage to TP/SL/flip, close, repeat.  Runs concurrently
    per symbol.  (Pre-existing positions are flattened at startup by _flatten_all,
    so this always starts from a clean slate.)"""
    ticker = _ticker_for(symbol)
    while True:
        try:
            hit = await _signal_hit(symbol, _STATE["table"])
            sig = (getattr(hit, "direction", "") or "").upper() if hit else None
            if sig not in ("LONG", "SHORT"):
                now = time.time()
                if now - _LAST_SCAN.get(symbol, 0) >= HEARTBEAT_S:   # liveness heartbeat
                    print(f"  [scan {symbol} {_cst_now():%H:%M:%S}] no signal — waiting")
                    _LAST_SCAN[symbol] = now
                await asyncio.sleep(SIGNAL_POLL_S)
                continue
            bkey = (sig, str(getattr(hit, "bar_time_cst", "")))      # one banner per new bar
            if _LAST_BANNER.get(symbol) != bkey:
                print(_signal_banner(sig, symbol,
                                     combo=getattr(hit, "combo", ""),
                                     accuracy=getattr(hit, "accuracy", None),
                                     when=getattr(hit, "bar_time_cst", None)))
                _LAST_BANNER[symbol] = bkey
            if not BUY:                                              # signals-only: no orders
                await asyncio.sleep(SIGNAL_POLL_S)
                continue
            m = await get_perp_market(c, ticker)
            if m is None:
                print(f"  [PERP] {ticker} not found/inactive — waiting.")
                await asyncio.sleep(RECHECK_S)
                continue
            order_side = "bid" if sig == "LONG" else "ask"
            entry_px = _ask(m) if sig == "LONG" else _bid(m)        # cross the spread
            if entry_px <= 0:
                await asyncio.sleep(RECHECK_S)
                continue
            try:
                cash = await perp_available(c)
            except Exception as e:
                print(f"  [PERP] margin balance error: {e}")
                await asyncio.sleep(RECHECK_S)
                continue
            lev = _max_leverage(m)                                  # market max (BTC ~6, ETH ~4.5)
            notional = cash * SIZE_BUFFER * lev                     # available cash × max leverage
            count = max(1, math.floor(notional / entry_px))
            print(f"  [SIZE {symbol}] cash ${cash:.2f} × {lev:.1f}x = ${notional:.2f} ÷ "
                  f"${entry_px:.4f} = {count} contracts")
            resp = await place_perp_order(c, ticker, order_side, count, entry_px, tick=_tick(m))
            if resp is None:
                await asyncio.sleep(RECHECK_S)
                continue
            fill_px = _pf(resp.get("average_fill_price")) or entry_px
            print(f"  [ENTRY {symbol}] {sig} {count} @ ${fill_px:.4f}")

            result, exit_mark, pnl_pct, max_p, max_l = await _monitor(
                c, symbol, ticker, sig, count, fill_px)
            await _close(c, symbol, ticker, sig, count, exit_mark, result, pnl_pct, max_l, max_p)
            await asyncio.sleep(RECHECK_S)
        except Exception as e:
            print(f"  [PERP {symbol}] loop error: {e}")
            await asyncio.sleep(RECHECK_S)


async def _flatten_all(c: KalshiClient) -> None:
    """Close every open BTC/ETH perp position so each run starts from a clean slate
    (user policy: flatten on startup).  Uses _sweep_close so thin books still fully
    flatten; a leg in a non-default margin subaccount may need a manual close."""
    for symbol in PERP_SYMBOLS:
        ticker = _ticker_for(symbol)
        pos = await _open_position(c, ticker)
        if not pos:
            print(f"  [FLATTEN {symbol}] none open")
            continue
        side, count, entry = pos
        print(f"  [FLATTEN {symbol}] closing existing {side} {count} @ ~${entry:.4f}")
        await _sweep_close(c, ticker)
        left = await _open_position(c, ticker)
        if left:
            print(f"  [FLATTEN {symbol}] WARNING still open after sweep: {left} "
                  f"— close manually (likely a non-default subaccount).")
        else:
            print(f"  [FLATTEN {symbol}] flat")


# ── main ──────────────────────────────────────────────────────────────────────
async def run() -> None:
    mode = "TRADE (buy=true)" if BUY else "SIGNALS-ONLY (buy=false)"
    print(f"[PERP] symbols={','.join(PERP_SYMBOLS)}  signal=crypto_signals  mode={mode}  "
          f"TP+{PROFIT_PCT:.0f}% / SL-{STOP_PCT:.0f}%  max-leverage  full-cash/symbol  "
          f"exit-on-flip  DRY_RUN={DRY_RUN}")
    if not BUY:
        print("[PERP] buy=false — emitting signal banners only, NO orders/flatten. "
              "Pass buy=true (or PERP_BUY=true) to place orders.")
    if not _HAS_CS:
        print("[PERP] crypto_signals not importable — cannot run. Install stock-trading "
              "deps (numpy/pandas) and Coinbase creds, then retry.")
        return
    _init_csv()
    c = KalshiClient()
    if BUY:
        print("[PERP] flattening any existing BTC/ETH perp positions (clean-slate startup)…")
        await _flatten_all(c)
    _STATE["table"] = await asyncio.to_thread(_discover_table)
    try:
        await asyncio.gather(
            _table_refresh_loop(),
            *[_trade_symbol(c, s) for s in PERP_SYMBOLS],
        )
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
