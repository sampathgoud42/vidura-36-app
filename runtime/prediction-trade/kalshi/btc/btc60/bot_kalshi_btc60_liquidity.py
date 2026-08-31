#!/usr/bin/env python3
"""
bot_kalshi_btc60_liquidity.py — Kalshi BTC HOURLY bot driven by LiquiditySR.
===========================================================================
A clone of ``bot_kalshi_btc60.py`` with the v3 direction engine and the
support/resistance level logic removed.  Direction comes purely from
``btc.liquidity_sr.get_entry_signal`` (the Pine "Liquidity S/R" mechanical
LONG/SHORT trigger).

Per hour (only while the current hour's market has > MIN_TIME_REMAINING_MIN
minutes left):

  1. Poll LiquiditySR.get_entry_signal (bounded to SIG_TIMEOUT_S = 5s).  When a
     LONG/SHORT fires, immediately read the live Coinbase price.
  2. LONG  → buy the strike just ABOVE the live price, direction_to_buy = "yes".
  3. SHORT → buy the strike just BELOW the live price, direction_to_buy = "no".
  4. Place the buy for KALSHI_CONTRACTS (at the current direction bid).
  5. Wait up to FILL_TIMEOUT_S (5 min) for the fill; otherwise cancel all
     pending orders and wait for the next hour's market.
  6. On fill, rest a sell at buy*(1+SELL_TP_PCT/100) (>= buy+5c) for the contracts.
  7. Monitor until the position is flat (sell filled) and log the trade.

Hourly series = KXBTCD (override via KALSHI_SERIES_60).  Reuses the v1
infrastructure (KalshiClient, order/fill/position helpers, CSV + rotating log).

Run:
    python bot_kalshi_btc60_liquidity.py
"""
from __future__ import annotations

import asyncio
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ── Make the shared btc/ package and the v1 module importable ─────────────────
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))   # project root → `import btc`
sys.path.insert(0, str(_HERE))          # kalshi/      → `import bot_kalshi_btc15`

# Separate outputs (set BEFORE importing v1 so its CSV/log binds here).
import os                                                        # noqa: E402
os.environ.setdefault("BOT_CSV_PATH",   str(_HERE / "btc60_liquidity_trade_history.csv"))
os.environ.setdefault("BOT_LOG_PREFIX", "kalshi_btc_60_liq_")

import bot_kalshi_btc15 as v1                       # noqa: E402  (infra)
from btc import BtcVidyaMonitor                     # noqa: E402  (live spot)
from btc.liquidity_sr import (                      # noqa: E402
    get_entry_signal,                               # LONG/SHORT entry signal
    run as lsr_run,                                 # full analysis (POC, S/R, bias)
)

# ── Reused v1 infrastructure ─────────────────────────────────────────────────
KalshiClient      = v1.KalshiClient
place_buy         = v1.place_buy
await_fill        = v1.await_fill
_bid_price        = v1._bid_price
place_tp_sell     = v1.place_tp_sell
_fire_sale        = v1._fire_sale
position_for      = v1.position_for
resting_orders    = v1.resting_orders
cancel_all        = v1.cancel_all
portfolio_balance = v1.portfolio_balance
_halt_and_shutdown = v1._halt_and_shutdown
init_csv          = v1.init_csv
log_trade         = v1.log_trade
_RotatingLogFile  = v1._RotatingLogFile
_Tee              = v1._Tee
_utc_now          = v1._utc_now
_cst_now          = v1._cst_now

DRY_RUN          = v1.DRY_RUN
KALSHI_CONTRACTS = v1.CONTRACTS                     # fallback size if PV unknown
CONTRACTS_PV_PCT = v1.CONTRACTS_PV_PCT             # size = this % of portfolio
DO_NOT_BUY_IF_PORTFOLIO_BELOW = v1.DO_NOT_BUY_IF_PORTFOLIO_BELOW   # MIN-PV floor
FIRE_SALE_CENTS  = v1.FIRE_SALE_CENTS

# ── btc60-liquidity config ───────────────────────────────────────────────────
def _cfg(name: str, default, cast=str):
    """Read env ``BTC60L_<name>`` (preferred) or bare ``<name>``, else default."""
    raw = os.getenv(f"BTC60L_{name}")
    if raw is None:
        raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return cast(raw.strip())
    except Exception:
        return default


SERIES_60             = os.getenv("KALSHI_SERIES_60", "KXBTCD")
MIN_TIME_REMAINING_MIN = _cfg("MIN_TIME_REMAINING_MIN", 30, int)
# Max profit-booked trades per hourly market.  After a clean (flat, profit-
# booked) trade, re-enter the same market for another if the count is still
# below this and enough time (> MIN_TIME_REMAINING_MIN) remains.
MAX_TRADES_PER_MARKET = int(os.getenv("MAX_TRADES_PER_MARKET", "1"))
# Daily profit goal: capture portfolio value at startup; once PV reaches
# start * (1 + TARGET_PORTFOLIO_PCT/100), halt the bot (and shut down the PC
# only when HALT_MACHINE_SHUTDOWN=TRUE).  0 disables.
TARGET_PORTFOLIO_PCT  = float(os.getenv("TARGET_PORTFOLIO_PCT", "0"))
SIG_TIMEOUT_S         = _cfg("SIG_TIMEOUT_S", 5.0, float)   # <5s call
FILL_TIMEOUT_S        = _cfg("FILL_TIMEOUT_S", 1000, int)   # fill wait
# Take-profit sell = buy price * (1 + SELL_TP_PCT/100), floored so the sell is
# always at least SELL_MIN_MARGIN_CENTS above the buy (e.g. buy 50c +20% -> 60c).
SELL_TP_PCT           = _cfg("SELL_TP_PCT", 20.0, float)
SELL_MIN_MARGIN_CENTS = _cfg("SELL_MIN_MARGIN_CENTS", 5, int)


def _sell_cents_for(buy_cents: int) -> int:
    """TP sell price: buy * (1 + SELL_TP_PCT%), at least buy + margin, capped 99."""
    tp = round(buy_cents * (1 + SELL_TP_PCT / 100.0))
    tp = max(tp, buy_cents + SELL_MIN_MARGIN_CENTS)
    return min(tp, 99)
RECHECK_S             = _cfg("RECHECK_S", 10, int)
START_DELAY_S         = _cfg("START_DELAY_S", 5, int)
# Safety: flatten any leftover position this many minutes before close.
EXIT_BEFORE_CLOSE_MIN = _cfg("EXIT_BEFORE_CLOSE_MIN", 12, int)
# Pre-buy bid confirmation: sample the bid CONFIRM_TICKS times at
# CONFIRM_INTERVAL_S and require buy% (upticks) > sell% (downticks).
CONFIRM_TICKS         = _cfg("CONFIRM_TICKS", 440, int)
CONFIRM_INTERVAL_S    = _cfg("CONFIRM_INTERVAL_S", 0.5, float)
# Alt signal: if live BTC is within +-POC_PROXIMITY_USD of the LiquiditySR POC,
# trade it — POC Green (support) -> LONG, POC Red (resistance) -> SHORT.
POC_PROXIMITY_USD     = _cfg("POC_PROXIMITY_USD", 25.0, float)
# Order price band (cents): find_target_strike prefers a strike whose direction
# bid is in [BID_BAND_LO, BID_BAND_HI]; if a coarse strike grid skips the band,
# it falls back to the strike whose bid is CLOSEST to the band (so it always
# places rather than polling forever).
BID_BAND_LO           = _cfg("BID_BAND_LO", 30, int)
BID_BAND_HI           = _cfg("BID_BAND_HI", 45, int)
# Heartbeat: print LiquiditySR POC / S/R / Bias every this many seconds while
# working a market, until the buy order is placed.
LSR_HEARTBEAT_S       = _cfg("LSR_HEARTBEAT_S", 60.0, float)
# Buy-at-S/R-level signal: when enabled and live BTC is within
# +-SR_PROXIMITY_USD of the level, LONG near a support (Sn), SHORT near a
# resistance (Rn).  One toggle per level rank (S1/R1, S2/R2, S3/R3).
BUY_AT_SR1            = os.getenv("BUY_AT_SR_LEVELS_SR1", "false").strip().lower() == "true"
BUY_AT_SR2            = os.getenv("BUY_AT_SR_LEVELS_SR2", "false").strip().lower() == "true"
BUY_AT_SR3            = os.getenv("BUY_AT_SR_LEVELS_SR3", "false").strip().lower() == "true"
SR_PROXIMITY_USD      = _cfg("SR_PROXIMITY_USD", 10.0, float)
# S/R-level confirmation: after a match, live BTC must stay within
# +-SR_CONFIRM_TOL_USD of the level for SR_CONFIRM_DURATION_S, polled every
# SR_CONFIRM_POLL_S, before the signal is confirmed.
SR_CONFIRM_TOL_USD    = _cfg("SR_CONFIRM_TOL_USD", 35.0, float)
SR_CONFIRM_DURATION_S = _cfg("SR_CONFIRM_DURATION_S", 300, int)
SR_CONFIRM_POLL_S     = _cfg("SR_CONFIRM_POLL_S", 30, int)


def _strike_of(market: dict) -> float | None:
    raw = (market.get("strike_price") or market.get("floor_strike")
           or market.get("cap_strike"))
    try:
        return float(raw) if raw is not None else None
    except Exception:
        return None


def _dir_bid_cents(market: dict, direction: str) -> int | None:
    """Bid (cents) for `direction` from a /markets list entry."""
    raw = market.get(f"{direction}_bid")
    if raw is not None:
        try:
            return int(round(float(raw)))
        except Exception:
            pass
    raw = market.get(f"{direction}_bid_dollars")
    if raw is not None:
        try:
            return int(round(float(raw) * 100))
        except Exception:
            pass
    return None


async def _open_hour_markets(c: KalshiClient) -> list[dict]:
    d = await c.req("GET", "/markets", params={
        "series_ticker": SERIES_60, "status": "open", "limit": 1000,
    })
    return d.get("markets", [])


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


_ET  = ZoneInfo("America/New_York")        # Eastern (handles EST/EDT)
_UTC = ZoneInfo("UTC")
_MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
        "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def _settlement_dt(now_et: datetime) -> datetime:
    """Top of the NEXT hour in Eastern (the current hour's settlement time).

    On the hour exactly (mm:ss == 00:00) → that same hour.
    """
    floored = now_et.replace(minute=0, second=0, microsecond=0)
    return floored if now_et == floored else floored + timedelta(hours=1)


def build_hour_event(now_utc: datetime | None = None) -> tuple[str, datetime]:
    """
    Autobuild the current KXBTCD hourly event ticker from the clock, plus its
    UTC close time.  The hour's contract settles at the NEXT top of the hour
    (Eastern), and the ticker suffix encodes that settlement date+hour:

        06/18/2026 01:15 ET  ->  KXBTCD-26JUN1802   (settles 02:00 ET = 06:00Z)
        06/18/2026 16:40 ET  ->  KXBTCD-26JUN1817   (settles 17:00 ET = 21:00Z)
        06/18/2026 23:30 ET  ->  KXBTCD-26JUN1900   (settles 00:00 ET next day)

    Format:  {SERIES_60}-{YY}{MON}{DD}{HH}  using the settlement datetime.
    Returns (event_ticker, close_time_utc).
    """
    now_utc = now_utc or _utc_now()
    settle_et = _settlement_dt(now_utc.astimezone(_ET))
    ticker = (f"{SERIES_60}-{settle_et.year % 100:02d}{_MON[settle_et.month - 1]}"
              f"{settle_et.day:02d}{settle_et.hour:02d}")
    return ticker, settle_et.astimezone(_UTC)


async def find_target_strike(
    c: KalshiClient, event: str, price: float, side: str,
) -> tuple[str, float, int | None, str] | None:
    """
    Find a strike whose ``direction`` bid is in [BID_BAND_LO, BID_BAND_HI].

    Considers EVERY strike in the event (BOTH sides of the live price), not just
    the directional side — so as price moves a strike on either side can come
    into band.  E.g. for NO: the strike just BELOW (OTM, cheap) and the strike
    just ABOVE (ITM, rich) are both polled, and whichever enters the band is
    taken (closest to the money on ties).

    Returns (ticker, strike, bid, direction) for an in-band strike, or None when
    nothing is in band yet — the caller keeps polling.  When nothing is in band
    it logs the two strikes bracketing the live price so the polling is visible.
    """
    direction = "yes" if side == "LONG" else "no"
    cands: list[tuple[float, dict, int]] = []   # (strike, market, bid)
    for m in await _open_hour_markets(c):
        if (m.get("event_ticker") or m.get("ticker")) != event:
            continue
        strike = _strike_of(m)
        if strike is None:
            continue
        bid = _dir_bid_cents(m, direction)
        if bid is None or bid <= 0:
            continue
        cands.append((strike, m, bid))
    if not cands:
        print(f"  [ENTRY60L] no {direction} strikes with a bid in {event} — polling.")
        return None

    in_band = [t for t in cands if BID_BAND_LO <= t[2] <= BID_BAND_HI]
    if in_band:
        strike, m, bid = min(in_band, key=lambda t: abs(t[0] - price))
        return m["ticker"], strike, bid, direction

    # Nothing in band → show the two strikes bracketing the live price so the
    # caller's polling is visible; price movement may bring one into band.
    below = [t for t in cands if t[0] < price]
    above = [t for t in cands if t[0] > price]
    parts = []
    if below:
        t = max(below, key=lambda x: x[0])      # nearest below
        parts.append(f"{t[1]['ticker']} {t[0]:,.0f}(below)={t[2]}c")
    if above:
        t = min(above, key=lambda x: x[0])      # nearest above
        parts.append(f"{t[1]['ticker']} {t[0]:,.0f}(above)={t[2]}c")
    print(f"  [ENTRY60L] no {direction} bid in {BID_BAND_LO}-{BID_BAND_HI}c yet — "
          f"polling: {', '.join(parts)}")
    return None


async def confirm_bid_not_dropping(
    c: KalshiClient, ticker: str, direction: str, *,
    ticks: int = CONFIRM_TICKS, interval_s: float = CONFIRM_INTERVAL_S,
) -> tuple[bool, float, float]:
    """
    Confirm the `direction` bid is NOT dropping before we buy, mirroring the v1
    uptick/downtick gate: sample the bid ``ticks`` times at ``interval_s``
    seconds and require buy% (upticks) > sell% (downticks).

    Returns (ok, buy_pct, sell_pct).  ``ok`` is False if too few samples.
    """
    prices: list[float] = []
    for _ in range(ticks):
        p = await _bid_price(c, ticker, direction)
        if p is not None:
            prices.append(p)
        await asyncio.sleep(interval_s)
    if len(prices) < 2:
        return False, 0.0, 0.0
    up = sum(1 for i in range(len(prices) - 1) if prices[i + 1] > prices[i])
    dn = sum(1 for i in range(len(prices) - 1) if prices[i + 1] < prices[i])
    moves = len(prices) - 1
    buy_pct = up / moves * 100.0
    sell_pct = dn / moves * 100.0
    return (buy_pct >= sell_pct), buy_pct, sell_pct


async def _flatten(c: KalshiClient, ticker: str, direction: str) -> None:
    """Cancel resting orders and fire-sell any open position on `ticker`."""
    try:
        await cancel_all(c)
        await asyncio.sleep(1)
        pos = await position_for(c, ticker)
        if pos and pos["contracts"] > 0:
            print(f"  [FLAT] fire-selling {pos['contracts']} on {ticker}")
            await _fire_sale(c, ticker, direction, pos["contracts"])
            await asyncio.sleep(2)
    except Exception as e:
        print(f"  [FLAT] failed: {e}")


async def _wait_flat(c: KalshiClient, ticker: str, direction: str,
                     deadline: datetime) -> str:
    """
    Wait until the position AND resting orders are both zero on `ticker`
    (i.e. the 55c sell filled).  If still holding at ``deadline``, cancel all
    orders and FIRE-SELL the position.

    Returns "FLAT", "DEADLINE_FIRESELL", or "DEADLINE_NO_POSITION".
    """
    while _utc_now() < deadline:
        pos = await position_for(c, ticker)
        pending = await resting_orders(c, ticker)
        n = pos["contracts"] if pos else 0
        if n == 0 and not pending:
            print(f"  [MON60L] flat on {ticker} — position 0, no resting orders.")
            return "FLAT"
        print(f"  [MON60L] holding {n}, resting {len(pending)}  "
              f"(deadline {deadline.strftime('%H:%MZ')}) — waiting ...")
        await asyncio.sleep(RECHECK_S)

    pos = await position_for(c, ticker)
    n = pos["contracts"] if pos else 0
    if n > 0:
        print(f"  [MON60L] deadline ({deadline.strftime('%H:%MZ')}) — active "
              f"{n} on {ticker}; cancel all + fire-sell.")
        await _flatten(c, ticker, direction)
        return "DEADLINE_FIRESELL"
    print(f"  [MON60L] deadline ({deadline.strftime('%H:%MZ')}) — no active "
          f"position on {ticker}; cancelling any resting orders only.")
    try:
        await cancel_all(c)
    except Exception as e:
        print(f"  [MON60L] cancel_all failed: {e}")
    return "DEADLINE_NO_POSITION"


def _sr_level_side(price, supports, resistances, *, tol, sr1, sr2, sr3):
    """
    Buy-at-S/R-level signal.  Returns (side, label, level):
      LONG  when `price` is within `tol` of an enabled support  (S1/S2/S3),
      SHORT when `price` is within `tol` of an enabled resistance (R1/R2/R3).
    `supports`/`resistances` are nearest-first (index 0 = S1/R1).  Lower ranks
    are checked first; returns (None, None, None) if nothing is in range.
    """
    for i, on in enumerate((sr1, sr2, sr3)):
        if not on:
            continue
        if i < len(supports) and abs(price - supports[i]) <= tol:
            return "LONG", f"S{i + 1}", supports[i]
        if i < len(resistances) and abs(price - resistances[i]) <= tol:
            return "SHORT", f"R{i + 1}", resistances[i]
    return None, None, None


async def confirm_sr_hold(btc, level: float, side: str, *,
                          tol: float = SR_CONFIRM_TOL_USD,
                          duration_s: int = SR_CONFIRM_DURATION_S,
                          poll_s: int = SR_CONFIRM_POLL_S) -> bool:
    """
    Confirm an S/R-level signal by watching the live BTC price for ``duration_s``
    (sampled every ``poll_s``).  The break is DIRECTIONAL — the favourable side
    never breaks it:

        LONG  (support) → broke only if price FALLS more than ``tol`` BELOW level.
        SHORT (resist)  → broke only if price RISES more than ``tol`` ABOVE level.

    Returns True if it holds the whole window, False the moment it breaks.
    """
    deadline = _utc_now() + timedelta(seconds=duration_s)
    while _utc_now() < deadline:
        px = btc.last_price if btc is not None else None
        if px is None:
            await asyncio.sleep(poll_s)
            continue
        # adverse move = distance in the UNfavourable direction only
        adverse = (level - px) if side == "LONG" else (px - level)
        broke = adverse > tol
        print(f"  [SR-CONFIRM] {side} live ${px:,.0f} adverse ${adverse:,.0f} "
              f"vs level ${level:,.0f} (tol ${tol:.0f}) -> "
              f"{'BROKE' if broke else 'OK'}")
        if broke:
            return False
        await asyncio.sleep(poll_s)
    return True


async def _lsr_heartbeat(stop_event: asyncio.Event, btc=None,
                         period_s: float = LSR_HEARTBEAT_S) -> None:
    """Print LIVE price + LiquiditySR POC / S/R / Bias every ``period_s``."""
    while not stop_event.is_set():
        try:
            lsr = await lsr_run(verbose=False)
            live = (btc.last_price if (btc is not None and btc.last_price)
                    else lsr.get("live_price"))
            live_str = f"{live:,.0f}" if live else "n/a"
            poc = lsr.get("poc")
            poc_str = (f"{poc['price']:,.0f} ({poc['color']})" if poc else "n/a")
            sr_str = ", ".join(
                f"{x['label']}={x['price']:,.0f}" + (" *POC" if x["is_poc"] else "")
                for x in lsr.get("levels", [])) or "n/a"
            print(f"  [LSR] LIVE: {live_str} **POC : {poc_str}** S/R : {{{sr_str}}}")
            print(f"  [LSR] Bias: {lsr.get('bias_txt')}")
        except Exception as e:
            print(f"  [LSR] heartbeat error: {e}")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=period_s)
        except asyncio.TimeoutError:
            pass


async def _stop_heartbeat(task, stop_event) -> None:
    """Signal + cancel a running heartbeat task (no-op if already None)."""
    if stop_event is not None:
        stop_event.set()
    if task is not None:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  MAIN LOOP                                                               ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def run() -> None:
    _log_fh    = _RotatingLogFile()
    sys.stdout = _Tee(sys.__stdout__, _log_fh)
    sys.stderr = _Tee(sys.__stderr__, _log_fh)
    print(f"[LOG] btc60-liquidity session started — logging to {_log_fh.name}")
    print(f"[CFG] series={SERIES_60}  size={CONTRACTS_PV_PCT}%PV  "
          f"tp=+{SELL_TP_PCT:.0f}%(min+{SELL_MIN_MARGIN_CENTS}c)  "
          f"min-time={MIN_TIME_REMAINING_MIN}min  "
          f"fill-timeout={FILL_TIMEOUT_S}s  DRY_RUN={DRY_RUN}")

    init_csv()
    c = KalshiClient()
    btc = BtcVidyaMonitor()
    btc.start()

    # Daily profit goal — capture starting portfolio value and the target.
    try:
        starting_pv = await portfolio_balance(c)
    except Exception as e:
        print(f"[PV] start balance fetch failed: {e}")
        starting_pv = 0.0
    target_pv = (starting_pv * (1 + TARGET_PORTFOLIO_PCT / 100.0)
                 if (TARGET_PORTFOLIO_PCT > 0 and starting_pv > 0) else None)
    print(f"[PV] start ${starting_pv:.2f}" + (
        f"  target ${target_pv:.2f} (+{TARGET_PORTFOLIO_PCT:.0f}%) → halt"
        f"{' + shutdown' if v1.HALT_MACHINE_SHUTDOWN else ''}"
        if target_pv else "  (TARGET_PORTFOLIO_PCT disabled)"))

    event_done: set[str] = set()         # markets finished trading for the hour
    event_trades: dict[str, int] = {}    # profit-booked trades per market
    _hb_task = None
    _hb_stop = None
    try:
        while True:
            # stop any heartbeat left over from a prior iteration
            await _stop_heartbeat(_hb_task, _hb_stop)
            _hb_task = _hb_stop = None
            # ── current hour = autobuilt from the clock (settles next :00 ET) ─
            event, event_close = build_hour_event()
            now = _utc_now()
            remaining = (event_close - now).total_seconds()

            # Finished with this market for the hour → wait for it to roll.
            if event in event_done:
                await asyncio.sleep(min(60, max(5, remaining + 2)))
                continue

            # Not enough time left in this hour → wait for the next hour.
            if remaining <= MIN_TIME_REMAINING_MIN * 60:
                print(f"[MARKET60L] {event} has {remaining/60:.1f} min left "
                      f"(<= {MIN_TIME_REMAINING_MIN}) — waiting for next hour.")
                await asyncio.sleep(min(60, max(5, remaining + 2)))
                continue

            # Trade cap reached for this market → done.
            n_done = event_trades.get(event, 0)
            if n_done >= MAX_TRADES_PER_MARKET:
                print(f"[MARKET60L] {event} hit MAX_TRADES_PER_MARKET "
                      f"({MAX_TRADES_PER_MARKET}) — waiting for next hour.")
                event_done.add(event)
                await asyncio.sleep(min(60, max(5, remaining + 2)))
                continue

            print(f"[MARKET60L] current event {event} (closes "
                  f"{event_close.strftime('%Y-%m-%d %H:%MZ')}, "
                  f"{remaining/60:.1f} min left, trade "
                  f"{n_done + 1}/{MAX_TRADES_PER_MARKET})")
            await asyncio.sleep(START_DELAY_S)

            # Heartbeat: print LSR POC/S-R/Bias every LSR_HEARTBEAT_S seconds
            # until the buy order is placed for this market.
            _hb_stop = asyncio.Event()
            _hb_task = asyncio.create_task(_lsr_heartbeat(_hb_stop, btc=btc))

            # ── Entry window: poll LiquiditySR until a LONG/SHORT fires ──────
            traded = False
            buy_resp = None
            target_ticker: str | None = None
            target_strike: float | None = None
            direction_to_buy: str | None = None
            buy_price = 0
            _buy_contracts = KALSHI_CONTRACTS
            current_btc_price: float | None = None
            signal_source: str | None = None     # which signal triggered the buy

            while (event_close - _utc_now()).total_seconds() > MIN_TIME_REMAINING_MIN * 60:
                # (1) mechanical LONG/SHORT signal, bounded to < 5s
                try:
                    sig = await asyncio.wait_for(
                        get_entry_signal(verbose=False), timeout=SIG_TIMEOUT_S)
                except asyncio.TimeoutError:
                    print("  [SIG] LiquiditySR timed out (>5s) — retrying.")
                    sig = None
                except Exception as e:
                    print(f"  [SIG] LiquiditySR error: {e}")
                    sig = None

                # live Coinbase price (needed by both the signal and POC rule)
                current_btc_price = btc.last_price or (sig.get("entry") if sig else None)

                # LiquiditySR context: 1) POC, 2) S/R levels (incl. POC), 3) bias.
                poc = None
                lsr = None
                sups: list = []
                ress: list = []
                poc_str = sr_str = "n/a"
                try:
                    lsr = await lsr_run(verbose=False)
                    poc = lsr.get("poc")
                    sups = lsr.get("supports", [])
                    ress = lsr.get("resistances", [])
                    poc_str = (f"{poc['price']:,.0f} ({poc['color']})"
                               if poc else "n/a")
                    sr_str = ", ".join(
                        f"{x['label']}={x['price']:,.0f}"
                        + (" *POC" if x["is_poc"] else "")
                        for x in lsr.get("levels", [])) or "n/a"
                except Exception as e:
                    print(f"  [LSR] context error: {e}")

                if current_btc_price is None and poc:
                    current_btc_price = poc["price"]
                if current_btc_price is None:
                    await asyncio.sleep(RECHECK_S)
                    continue

                # Decide direction: mechanical entry first, else POC-proximity.
                #   live within +-POC_PROXIMITY_USD of POC → Green=LONG, Red=SHORT
                side = None
                signal_source = None
                if sig:
                    side = sig["side"]                   # "LONG" | "SHORT"
                    signal_source = "MECHANICAL"
                    print(f"  [SIG] {sig['label'].splitlines()[0]}  "
                          f"(live ${current_btc_price:,.0f})")
                elif poc and abs(current_btc_price - poc["price"]) <= POC_PROXIMITY_USD:
                    if poc["color"] == "Green":
                        side = "LONG"
                    elif poc["color"] == "Red":
                        side = "SHORT"
                    if side:
                        signal_source = "POC"
                        print(f"  [POC] live ${current_btc_price:,.0f} within "
                              f"${POC_PROXIMITY_USD:.0f} of POC {poc['price']:,.0f} "
                              f"({poc['color']}) → {side}")

                # 3rd signal — buy at S/R levels (S1/R1, S2/R2, S3/R3) when
                # the matching BUY_AT_SR_LEVELS_SRn toggle is enabled.
                if side is None and (BUY_AT_SR1 or BUY_AT_SR2 or BUY_AT_SR3):
                    _sr_side, _sr_lbl, _sr_lvl = _sr_level_side(
                        current_btc_price, sups, ress, tol=SR_PROXIMITY_USD,
                        sr1=BUY_AT_SR1, sr2=BUY_AT_SR2, sr3=BUY_AT_SR3)
                    if _sr_side:
                        print(f"  [SR] live ${current_btc_price:,.0f} within "
                              f"${SR_PROXIMITY_USD:.0f} of {_sr_lbl} ${_sr_lvl:,.0f}"
                              f" → {_sr_side} [SR{_sr_lbl[1:]}] — confirming "
                              f"±${SR_CONFIRM_TOL_USD:.0f} hold for "
                              f"{SR_CONFIRM_DURATION_S // 60}min …")
                        # Confirm the level holds (price stays within +-tol for
                        # the window) before committing to the S/R signal.
                        if await confirm_sr_hold(btc, _sr_lvl, _sr_side):
                            side = _sr_side
                            signal_source = f"SR{_sr_lbl[1:]}"   # S1/R1 → SR1
                            print(f"  [SR] {signal_source} confirmed → {side}")
                        else:
                            print("  [SR] level did not hold — signal rejected.")

                if side is None:
                    await asyncio.sleep(RECHECK_S)
                    continue

                print(f"  [LSR] POC : {poc_str}")
                print(f"  [LSR] S/R : {sr_str}")
                print(f"  [LSR] Bias: {lsr.get('bias_txt') if lsr else 'n/a'}")
                # (2/3) poll strikes on BOTH sides of the live price until one's
                # direction bid lands in BID_BAND (30-45c); take that one.
                found = await find_target_strike(c, event, current_btc_price, side)
                if found is None:
                    await asyncio.sleep(RECHECK_S)
                    continue
                target_ticker, target_strike, bid, direction_to_buy = found
                rel = "above" if target_strike > current_btc_price else "below"
                print(f"  [ENTRY60L] {side} → {direction_to_buy.upper()} "
                      f"{target_ticker} strike={target_strike:,.0f} ({rel} "
                      f"${current_btc_price:,.0f})  bid={bid}c (in band)")
                # Getting support and resistance levels -old
                #sr24 = await get_support_resistance("24h", "5m", verbose=False)
                #sr1  = await get_support_resistance("1h", "1m", verbose=False)
                #supports    = [sr24["S1"], sr24["S2"], sr24["S3"],
               #            sr1["S1"],  sr1["S2"],  sr1["S3"]]
                #resistances = [sr24["R1"], sr24["R2"], sr24["R3"],
               #            sr1["R1"],  sr1["R2"],  sr1["R3"]]
              #  print(f"  [SR60] supports={[s for s in supports if s]}")
               # print(f"  [SR60] resistances={[r for r in resistances if r]}")
              
                # (4) find_target_strike already chose the best-available strike
                # (in band, else closest-to-band) — proceed at its bid.
                buy_price = bid

                # Confirm the bid is not dropping before committing: 50 ticks @
                # 1s, require buy% (upticks) > sell% (downticks) — the v1 gate.
                ok, buy_pct, sell_pct = await confirm_bid_not_dropping(
                    c, target_ticker, direction_to_buy)
                print(f"  [CONFIRM] {target_ticker} {direction_to_buy} bid over "
                      f"{CONFIRM_TICKS} ticks: buy={buy_pct:.0f}% sell={sell_pct:.0f}% "
                      f"-> {'OK' if ok else 'DROPPING'}")
                if not ok:
                    # buy% <= sell% → bid is dropping; loop back to the top of
                    # the while, i.e. retry from wait_for(get_entry_signal()).
                    print("  [ENTRY60L] bid dropping (buy% <= sell%) — "
                          "retrying from get_entry_signal.")
                    continue

                # (4) size via CONTRACTS_PV_PCT of portfolio value (like the
                # other bots): contracts = PV% * pv / price-per-contract.
                pv = await portfolio_balance(c)
                # MIN-PV stop: never open a new position once the portfolio has
                # fallen below the floor — cancel, flatten, and (if enabled) halt.
                if pv < DO_NOT_BUY_IF_PORTFOLIO_BELOW:
                    await _halt_and_shutdown(
                        c, target_ticker, reason_tag="MIN-PV HALT",
                        reason_msg=(f"Portfolio ${pv:.2f} < "
                                    f"${DO_NOT_BUY_IF_PORTFOLIO_BELOW} — halting."))
                    return
                _peek = max(0.01, buy_price / 100.0)
                _buy_contracts = max(1, math.ceil(
                    (CONTRACTS_PV_PCT / 100.0 * pv) / _peek))
                print(f"  [SIZE60L] {CONTRACTS_PV_PCT}% of ${pv:.2f} / "
                      f"{_peek:.2f} = {_buy_contracts} contracts")

                # order being initiated → stop the LSR heartbeat
                await _stop_heartbeat(_hb_task, _hb_stop)
                _hb_task = _hb_stop = None
                buy_resp = await place_buy(c, target_ticker, direction_to_buy,
                                           buy_at_cents=buy_price+3,
                                           contracts=_buy_contracts)
                if buy_resp is None:
                    await asyncio.sleep(RECHECK_S)
                    continue
                await asyncio.sleep(15)
                # (5) wait up to 5 min for the fill, else cancel + next hour
                if await await_fill(c, target_ticker, timeout=FILL_TIMEOUT_S):
                    traded = True
                else:
                    print(f"  [ENTRY60L] buy not filled in {FILL_TIMEOUT_S}s "
                          f"— cancel all & wait for next hour.")
                    await cancel_all(c)
                break  # one entry attempt per hour
              
                if await await_fill(c, target_ticker, timeout=FILL_TIMEOUT_S):
                    traded = True
                else:
                    print(f"  [ENTRY60L] buy not filled in {FILL_TIMEOUT_S}s "
                          f"— cancel all & wait for next hour.")
                    await cancel_all(c)
                break  # one entry attempt per hour
            if not traded:
                # entry window expired with no fill / no signal → done this hour
                event_done.add(event)
                await _stop_heartbeat(_hb_task, _hb_stop)
                _hb_task = _hb_stop = None
                await asyncio.sleep(5)
                continue

            # ── (6) rest a sell at 55c for the same contracts ───────────────
            odata = (buy_resp or {}).get("order", {})
            fill_cost = round(float(odata.get("taker_fill_cost_dollars", "0"))
                              + float(odata.get("taker_fees_dollars", "0")), 4)
            if fill_cost < 0.5:
                fill_cost = round((buy_price / 100.0) * _buy_contracts, 4)
            entry_total = fill_cost
            avg_cents = int(round(float(fill_cost / _buy_contracts), 2) * 100)

            pos = await position_for(c, target_ticker)
            real_contracts = (pos["contracts"] if (pos and pos["contracts"] > 0)
                              else _buy_contracts)
            sell_cents = _sell_cents_for(buy_price+2)
            print(f"  Entry: {real_contracts} x {avg_cents}c = ${entry_total:.2f}  "
                  f"|  Sell @ {sell_cents}c (+{SELL_TP_PCT:.0f}% of {buy_price}c)")
            await place_tp_sell(c, target_ticker, direction_to_buy,
                                real_contracts, sell_cents)

            # ── (7) monitor until flat, log the trade ───────────────────────
            deadline = event_close - timedelta(minutes=EXIT_BEFORE_CLOSE_MIN)
            flat_reason = await _wait_flat(c, target_ticker, direction_to_buy,
                                           deadline)
            if flat_reason == "DEADLINE_FIRESELL":
                exit_cents, result = FIRE_SALE_CENTS, "BTC60LIQ_DEADLINE_FIRESELL"
            else:
                exit_cents, result = sell_cents, "BTC60LIQ_SELL"

            pv_after = None
            try:
                pv_after = await portfolio_balance(c)
                exit_total = (exit_cents / 100.0) * real_contracts
                log_trade(
                    ticker=target_ticker, mode="BUY", direction=direction_to_buy,
                    contracts=real_contracts, entry=avg_cents,
                    exit_=exit_total, pnl=exit_total - entry_total,
                    result=result, pv=pv_after,
                    btc_to_beat=target_strike, btc_spot_at_buy=current_btc_price,
                    btc_spot_at_sell=btc.last_price,
                    signal_source=signal_source,
                )
            except Exception as e:
                print(f"  [LOG60L] log_trade failed: {e}")

            # ── TARGET_PORTFOLIO_PCT — daily goal reached → halt (and shut down
            #    only when HALT_MACHINE_SHUTDOWN=TRUE) ─────────────────────────
            if target_pv is not None and pv_after is not None and pv_after >= target_pv:
                await _halt_and_shutdown(
                    c, target_ticker, reason_tag="TARGET-PV HALT",
                    reason_msg=(f"PV ${pv_after:.2f} >= target ${target_pv:.2f} "
                                f"(+{TARGET_PORTFOLIO_PCT:.0f}% of start "
                                f"${starting_pv:.2f}) — goal reached."))
                return

            # ── MAX_TRADES_PER_MARKET bookkeeping ───────────────────────────
            if flat_reason == "DEADLINE_FIRESELL":
                # forced exit (no profit booked) → stop trading this market
                event_done.add(event)
            else:
                # profit booked → count it; re-enter only if under the cap AND
                # enough time remains, else mark this market done.
                event_trades[event] = event_trades.get(event, 0) + 1
                rem_now = (event_close - _utc_now()).total_seconds()
                if (event_trades[event] >= MAX_TRADES_PER_MARKET
                        or rem_now <= MIN_TIME_REMAINING_MIN * 60):
                    event_done.add(event)
                else:
                    print(f"[MARKET60L] {event} trade {event_trades[event]} booked, "
                          f"{rem_now/60:.1f} min left — looking for another.")

            await asyncio.sleep(5)
    finally:
        await _stop_heartbeat(_hb_task, _hb_stop)
        try:
            await btc.stop()
        except Exception:
            pass
        try:
            await c.close()
        except Exception:
            pass
        try:
            _log_fh.close()
        except Exception:
            pass


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
