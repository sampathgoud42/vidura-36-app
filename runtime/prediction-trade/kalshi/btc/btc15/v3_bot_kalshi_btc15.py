#!/usr/bin/env python3
"""
v3_bot_kalshi_btc15.py — Kalshi BTC-15M bot, v3 (simplified).
=============================================================
Minimal, direct strategy built on the v1 infrastructure:

  • Direction — best-of-three of the Coinbase 5/10/15-min signals from
    ``btc.cb_btc_signal.run_analysis()`` ONLY (BUY→YES, SELL→NO,
    NEUTRAL→abstain; ties broken by overall_score, then the longest
    directional timeframe).  No settled-market input.
  • Entry — place the order IMMEDIATELY once the direction is confirmed AND
    the bid is inside the entry band [MIN_ENTRY_CENTS, MAX_ENTRY_CENTS].
  • Exit — if DO_YOU_HAVE_STOP_SELL=TRUE and MONITOR_SL_TRIGGER=TRUE, monitor
    the position and fire-sell when the target (TP) is met or the stop-loss
    (SL) is hit.  Otherwise place no protective orders and let it settle.

Kept pre-trade controls:
  • TRADE BEHAVIOUR  — CONTRACTS_PV_PCT sizing, TIME_SEC_TO_ORDER order window,
                       MAX_TRADES_PER_MARKET, DO_YOU_HAVE_STOP_SELL /
                       MONITOR_SL_TRIGGER exit behaviour.
  • PORTFOLIO LIMIT  — DO_NOT_BUY_IF_PORTFOLIO_BELOW (MIN-PV) +
                       TARGET_PORTFOLIO_PCT (TARGET-PV) halts.
  • LOSS RATE HALT   — MAX_LOSS_RATE profit-ratcheted PV-Returns floor.
  • TIME HALT        — trading-hours halt windows.

Everything else from v2 (BUY_SCORE, SELL_SCORE monitor, entry flip, bid logger,
proactive-TP, BtcVidyaMonitor voting) is intentionally removed.

Run:
    python v3_bot_kalshi_btc15.py
"""
from __future__ import annotations

import asyncio
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ── Make the shared btc/ package and the v1 module importable ────────────────
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))   # project root  → `import btc`
sys.path.insert(0, str(_HERE))          # kalshi/        → `import bot_kalshi_btc15`

# Separate v3 outputs for standalone runs (dispatcher env wins via setdefault).
os.environ.setdefault("BOT_CSV_PATH",   str(_HERE / "v3_trade_history.csv"))
os.environ.setdefault("BOT_LOG_PREFIX", "v3_kalshi_btc_15_")

import bot_kalshi_btc15 as v1                                # noqa: E402
from btc.cb_btc_signal import run_analysis as cb_run_analysis  # noqa: E402
from btc import BtcVidyaMonitor        # noqa: E402

# ── Reused v1 infrastructure ─────────────────────────────────────────────────
KalshiClient                = v1.KalshiClient
_bid_price                  = v1._bid_price
place_buy                   = v1.place_buy
await_fill                  = v1.await_fill
place_tp_sell               = v1.place_tp_sell
_tp_sl                      = v1._tp_sl
_fire_sale                  = v1._fire_sale
position_for                = v1.position_for
resting_orders              = v1.resting_orders
cancel_all                  = v1.cancel_all
portfolio_balance           = v1.portfolio_balance
init_csv                    = v1.init_csv
log_trade                   = v1.log_trade
compute_prediction_win_rate = v1.compute_prediction_win_rate
wait_for_market             = v1.wait_for_market
_in_halt_window             = v1._in_halt_window
_halt_and_shutdown          = v1._halt_and_shutdown
_RotatingLogFile            = v1._RotatingLogFile
_Tee                        = v1._Tee
_utc_now                    = v1._utc_now
_cst_now                    = v1._cst_now
determine_direction         = v1.determine_direction

DRY_RUN                       = v1.DRY_RUN
TIME_SEC_TO_ORDER             = v1.TIME_SEC_TO_ORDER
MIN_ENTRY_CENTS               = v1.MIN_ENTRY_CENTS
MAX_ENTRY_CENTS               = v1.MAX_ENTRY_CENTS
CONTRACTS_PV_PCT              = v1.CONTRACTS_PV_PCT
MAX_TRADES_PER_MARKET         = v1.MAX_TRADES_PER_MARKET
DO_NOT_BUY_IF_PORTFOLIO_BELOW = v1.DO_NOT_BUY_IF_PORTFOLIO_BELOW
HALT_TIMEZONE                 = v1.HALT_TIMEZONE
FIRE_SALE_CENTS               = v1.FIRE_SALE_CENTS
DO_YOU_HAVE_STOP_SELL         = v1.DO_YOU_HAVE_STOP_SELL
TARGET_PORTFOLIO_PCT          = v1.TARGET_PORTFOLIO_PCT
MAX_LOSS_RATE                 = v1.MAX_LOSS_RATE
get_day_start_portfolio       = v1.get_day_start_portfolio

# v3 exit gate: monitor + fire-sell only when TRUE (and DO_YOU_HAVE_STOP_SELL).
MONITOR_SL_TRIGGER            = os.getenv("MONITOR_SL_TRIGGER", "TRUE").upper() == "TRUE"

from zoneinfo import ZoneInfo   # noqa: E402

# ── v3 tunables ──────────────────────────────────────────────────────────────
MARKET_LEN_S        = 900    # Kalshi BTC-15M cycle length (s)
MIN_TIME_TO_CLOSE_S = 470    # only open a trade with > this many seconds left
BAND_POLL_S         = 3      # band-wait poll cadence (s)
MON_POLL_S          = 2      # monitor poll cadence (s)
EXIT_DROP_CENTS     = 20     # fire-sell if the held side's bid drops below this

# Per-market bid-price recorder (for future analysis).
BID_MONITOR_LOG        = str(Path(os.getenv("BOT_LOG_DIR", ".")) / "bid_price_monitor.log")
BID_MONITOR_INTERVAL_S = 30   # record the chosen direction's bid every N s

# Direction-vote dead bands
V2_STRIKE_BUFFER      = 4.0   # ±$ for STEP-3 V2 live-vs-strike

def _market_opened(market: dict) -> datetime:
    ot = market.get("open_time", "")
    if ot:
        try:
            return datetime.fromisoformat(ot.replace("Z", "+00:00"))
        except Exception:
            pass
    return _utc_now()


def _strike_of(market: dict) -> float | None:
    raw = (market.get("strike_price") or market.get("floor_strike")
           or market.get("cap_strike"))
    try:
        return float(raw) if raw is not None else None
    except Exception:
        return None


async def bid_price_monitor(
    c: KalshiClient, ticker: str, direction: str, market_opened: datetime,
) -> None:
    """
    Background recorder for future analysis: append the chosen direction's live
    bid (cents) every BID_MONITOR_INTERVAL_S seconds for the rest of the 15-min
    market to BID_MONITOR_LOG.  Fire-and-forget; independent of the trade flow.
    File format:

        [<ticker>] [<dir>] bid price live data for every 30 seconds
        [bid-price] [<dir>] [HH:MM:SS] <cents>
        ...
        ------------------------------------------------------------ (block sep)
    """
    market_close = market_opened + timedelta(seconds=MARKET_LEN_S)
    try:
        with open(BID_MONITOR_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{ticker}] [{direction}] bid price live data for every "
                    f"{BID_MONITOR_INTERVAL_S} seconds\n")
            f.flush()
            while _utc_now() < market_close:
                bid = await _bid_price(c, ticker, direction)
                cents = int(round(bid * 100)) if bid is not None else "N/A"
                ts = _cst_now().strftime("%H:%M:%S")
                f.write(f"[bid-price] [{direction}] [{ts}] {cents}\n")
                f.flush()
                await asyncio.sleep(BID_MONITOR_INTERVAL_S)
            f.write("-" * 77 + "\n")
            f.flush()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        print(f"  [BID-MON] logger error for {ticker}: {e}")


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  DIRECTION — best of three Coinbase 5/10/15-min signals                 ║
# ╚════════════════════════════════════════════════════════════════════════════╝
def _cb_vote(sig_text: str) -> str:
    """BUY → 'yes', SELL → 'no', NEUTRAL/other → 'abstain'."""
    s = (sig_text or "").upper()
    if "BUY" in s:
        return "yes"
    if "SELL" in s:
        return "no"
    return "abstain"

async def determine_direction_v2(
    c: KalshiClient, btc: BtcVidyaMonitor, btc_to_beat: float | None,
) -> tuple[str, str | None]:
    """
    Direction = majority of four voters.  V1 and V4 always vote; V2 and V3
    may abstain.  Ties are broken by V4 (btcSignalHourly).

      V1  settled-market momentum  (determine_direction; always votes)
      V2  live BTC vs strike ±$15  (abstain inside the band)
      V3  btcSignalWithStrength    (buy/strong_buy→YES, sell/strong_sell→NO,
                                    hold→abstain)
      V4  btcSignalHourly          (buy→YES, sell→NO; NEVER abstains)

    Returns (direction, actual_direction_previous).
    """
    yes = no = 0

    # V1
    v1_dir, actual_prev = await determine_direction(c)
    if v1_dir == "yes":
        yes += 1
    else:
        no += 1

    # V2
    live = btc.last_price if btc else None
    v2 = "abstain"
    if live is not None and btc_to_beat is not None:
        if live > btc_to_beat + V2_STRIKE_BUFFER:
            v2 = "yes"; yes += 1
        elif live < btc_to_beat - V2_STRIKE_BUFFER:
            v2 = "no"; no += 1
    if(v2 == "abstain"):
      await asyncio.sleep(5)
      if live is not None and btc_to_beat is not None:
        if live > btc_to_beat + V2_STRIKE_BUFFER:
            v2 = "yes"; yes += 1
        elif live < btc_to_beat - V2_STRIKE_BUFFER:
            v2 = "no"; no += 1

    # V3
    strong = btc.btcSignalWithStrength() if btc else "hold"
    if strong in ("buy", "strong_buy"):
        v3 = "yes"; yes += 1
    elif strong in ("sell", "strong_sell"):
        v3 = "no"; no += 1
    else:
        v3 = "abstain"

    # V4 — hourly bias (never abstains, also the tie-breaker)
    hourly = btc.btcSignalHourly() if btc else "buy"
    v4 = "yes" if hourly == "buy" else "no"
    if v4 == "yes":
        yes += 1
    else:
        no += 1

    if yes > no:
        direction = "yes"
    elif no > yes:
        direction = "no"
    else:
        direction = v3   # tie → V3 (btcSignalWithStrength)

    print(f"  [DIR v2] Best-of-4 → {direction.upper()}  (YES={yes} NO={no})")
    print(f"  [DIR v2]   V1 settled={v1_dir.upper()}  "
          f"V2 strike={v2.upper()}  V3 strong={v3.upper()} ({strong.upper()})  "
          f"V4 hourly={v4.upper()} ({hourly.upper()})")
    return direction, actual_prev

async def determine_direction_v3(c: KalshiClient) -> tuple[str, float, int]:
    """
    Direction = best-of-three of the Coinbase 5/10/15-min signals — PURELY from
    cb_btc_signal.run_analysis() (no settled-market input).  Majority of yes/no
    wins; ties are broken by the overall_score sign, then by the longest
    directional timeframe (15m → 10m → 5m), defaulting to 'yes' if everything
    is neutral.

    Returns (direction, live_btc_value, overall_score).
    """
    try:
        sig = await cb_run_analysis(verbose=False)
    except Exception as e:
        print(f"  [DIR v3] cb_btc_signal failed: {e} — defaulting YES.")
        return "yes", 0.0, 0

    v5, v10, v15 = (_cb_vote(sig.get("5min")), _cb_vote(sig.get("10min")),
                    _cb_vote(sig.get("15min")))
    votes = (v5, v10, v15)
    yes, no = votes.count("yes"), votes.count("no")
    score = int(sig.get("overall_score", 0) or 0)
  
    if yes > no:
        direction, why = "yes", f"majority YES ({yes}/{no})"
    elif no > yes:
        direction, why = "no", f"majority NO ({no}/{yes})"
    else:
        score = int(sig.get("overall_score", 0) or 0)
        if score > 0:
            direction, why = "yes", f"tie → score {score:+d} → YES"
        elif score < 0:
            direction, why = "no", f"tie → score {score:+d} → NO"
        else:
            # score 0 → longest directional timeframe (15m → 10m → 5m), else YES
            fb = next((v for v in (v15, v10, v5) if v in ("yes", "no")), "yes")
            direction, why = fb, f"tie → score 0 → {fb.upper()} (15m→10m→5m)"

    live_btc = float(sig.get("live_btc_value", 0.0) or 0.0)
    print(f"  [DIR v3] best-of-3 → {direction.upper()}  ({why})")
    print(f"  [DIR v3]   5m={sig.get('5min')}  10m={sig.get('10min')}  "
          f"15m={sig.get('15min')}  score={score:+d}  "
          f"live=${live_btc:,.2f}")
    return direction, live_btc, score

async def determine_direction_mon(c: KalshiClient) -> tuple[str, float]:
    """
    Direction = best-of-three of the Coinbase 5/10/15-min signals — PURELY from
    cb_btc_signal.run_analysis() (no settled-market input).  Majority of yes/no
    wins; ties are broken by the overall_score sign, then by the longest
    directional timeframe (15m → 10m → 5m), defaulting to 'yes' if everything
    is neutral.

    Returns (direction, live_btc_value).
    """
    try:
        sig = await cb_run_analysis(verbose=False)
    except Exception as e:
        print(f"  [DIR v3] cb_btc_signal failed: {e} — defaulting YES.")
        return "yes", 0.0

    v5, v10, v15 = (_cb_vote(sig.get("5min")), _cb_vote(sig.get("10min")),
                    _cb_vote(sig.get("15min")))
    votes = (v5, v10, v15)
    yes, no = votes.count("yes"), votes.count("no")

    if yes > no:
        direction, why = "yes", f"majority YES ({yes}/{no})"
    elif no > yes:
        direction, why = "no", f"majority NO ({no}/{yes})"
    else:
        score = int(sig.get("overall_score", 0) or 0)
        if score > 0:
            direction, why = "yes", f"tie → score {score:+d} → YES"
        elif score < 0:
            direction, why = "no", f"tie → score {score:+d} → NO"
        else:
            # score 0 → longest directional timeframe (15m → 10m → 5m), else YES
            fb = next((v for v in (v15, v10, v5) if v in ("yes", "no")), "yes")
            direction, why = fb, f"tie → score 0 → {fb.upper()} (15m→10m→5m)"

    live_btc = float(sig.get("live_btc_value", 0.0) or 0.0)
    return direction, live_btc

async def determine_direction_flip(c: KalshiClient) -> tuple[str, float]:
    """
    Direction = best-of-three of the Coinbase 5/10/15-min signals — PURELY from
    cb_btc_signal.run_analysis() (no settled-market input).  Majority of yes/no
    wins; ties are broken by the overall_score sign, then by the longest
    directional timeframe (15m → 10m → 5m), defaulting to 'yes' if everything
    is neutral.

    Returns (direction, live_btc_value).
    """
    try:
        sig = await cb_run_analysis(verbose=False)
    except Exception as e:
        print(f"  [DIR v3] cb_btc_signal failed: {e} — defaulting YES.")
        return "yes", 0.0

    v5, v10, v15 = (_cb_vote(sig.get("5min")), _cb_vote(sig.get("10min")),
                    _cb_vote(sig.get("15min")))
    votes = (v5, v10, v15)
    yes, no = votes.count("yes"), votes.count("no")

    if yes > no:
        direction, why = "yes", f"majority YES ({yes}/{no})"
    elif no > yes:
        direction, why = "no", f"majority NO ({no}/{yes})"
    else:
        score = int(sig.get("overall_score", 0) or 0)
        if score > 0:
            direction, why = "yes", f"tie → score {score:+d} → YES"
        elif score < 0:
            direction, why = "no", f"tie → score {score:+d} → NO"
        else:
            # score 0 → longest directional timeframe (15m → 10m → 5m), else YES
            fb = next((v for v in (v15, v10, v5) if v in ("yes", "no")), "yes")
            direction, why = fb, f"tie → score 0 → {fb.upper()} (15m→10m→5m)"

    live_btc = float(sig.get("live_btc_value", 0.0) or 0.0)
    return direction, live_btc
# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  BAND WAIT — place as soon as the bid is in the entry band              ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def band_wait(
    c: KalshiClient, ticker: str, direction: str, market_opened: datetime,
) -> tuple[bool, int, str]:
    """
    Poll the bid for ``direction`` and return (True, bid_cents, direction) as
    soon as it falls inside [MIN_ENTRY_CENTS, MAX_ENTRY_CENTS].  Returns
    (False, 0, direction) if the order window (TIME_SEC_TO_ORDER) expires first.
    """
    while True:
        age = (_utc_now() - market_opened).total_seconds()
        direction2, live_btc = await determine_direction_flip(c)
        print(f"  [LIVE vs PREDICT] ::{direction2} vs {direction}")
        if(direction2 !=direction):
           direction = direction2
           print(f"  [FLIP] FLIPPED direction ({direction}.")
        if age > TIME_SEC_TO_ORDER:
            print(f"  [BAND] window expired ({age:.0f}s) — skip slot.")
            return False, 0, direction
        bid = await _bid_price(c, ticker, direction)
        if bid is None:
            await asyncio.sleep(BAND_POLL_S)
            continue
        bid_c = int(round(bid * 100))
        if MIN_ENTRY_CENTS <= bid_c <= MAX_ENTRY_CENTS:
            print(f"  [BAND] ✓ {direction.upper()} bid {bid_c}¢ in band "
                  f"[{MIN_ENTRY_CENTS}-{MAX_ENTRY_CENTS}] — placing order.")
            return True, bid_c, direction
        print(f"  [BAND] ⏳ {direction.upper()} bid {bid_c}¢ outside "
              f"[{MIN_ENTRY_CENTS}-{MAX_ENTRY_CENTS}]  age={age:.0f}s")
        if (MIN_ENTRY_CENTS <= bid_c <= 75) and age > 500:
            print(f"  [BAND UP75] ✓ {direction.upper()} bid {bid_c}¢ in band "
                  f"[{MIN_ENTRY_CENTS}-75] — placing order.")
            return True, bid_c, direction
        if (MIN_ENTRY_CENTS <= bid_c <= 70) and age > 300:
            print(f"  [BAND UP65] ✓ {direction.upper()} bid {bid_c}¢ in band "
                  f"[{MIN_ENTRY_CENTS}-70] — placing order.")
            return True, bid_c, direction
        await asyncio.sleep(BAND_POLL_S)


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  EXIT-DROP MONITOR — fire-sell if the bid crashes below a floor         ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def monitor_trade_exit_drop(
    c: KalshiClient, ticker: str, direction: str, market_opened: datetime,
    contracts: int, *, drop_cents: int = EXIT_DROP_CENTS, poll_s: float = MON_POLL_S,
) -> str:
    """
    Crash-protection watcher for ``ticker`` / ``direction``: if the live bid
    for that side drops BELOW ``drop_cents`` while a position is held, cancel
    any resting orders and FIRE-SELL ``contracts`` (the ordered size).

    Loops every ``poll_s`` seconds until the floor is breached, the position
    closes, or the 15-min market closes.  Returns the exit reason:
        "V3_EXIT_DROP"   — bid breached the floor → fire-sold
        "NO_POSITION"    — position already gone (nothing to protect)
        "V3_NO_DROP"     — market closed without breaching the floor
    """
    market_close = market_opened + timedelta(seconds=MARKET_LEN_S)
    print(f"  [EXIT-DROP] watching {direction.upper()} on {ticker} ({contracts}) — "
          f"fire-sell if bid < {drop_cents}¢")
    while _utc_now() < market_close:
        pos = await position_for(c, ticker)
        if pos is None or pos["contracts"] == 0:
            return "NO_POSITION"

        bid   = await _bid_price(c, ticker, direction)
        bid_c = int(round(bid * 100)) if bid is not None else None
        if bid_c is not None and bid_c <= drop_cents:
            _sell_n = min(contracts, pos["contracts"])
            print(f"  [EXIT-DROP] bid {bid_c}¢ < {drop_cents}¢ — fire-selling "
                  f"{_sell_n} {direction.upper()}.")
            try:
                await cancel_all(c)
                await asyncio.sleep(1)
                await _fire_sale(c, ticker, direction, _sell_n)
                await asyncio.sleep(2)
            except Exception as e:
                print(f"  [EXIT-DROP] fire-sell failed: {e}")
            return "V3_EXIT_DROP"

        await asyncio.sleep(poll_s)
    return "V3_NO_DROP"


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  MONITOR — fire-sell on target (TP) or stop-loss (SL)                   ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def monitor_trade_v3(
    c: KalshiClient, ticker: str, direction: str, *,
    entry_total: float, avg_cents: int, buy_contracts: int,
    tp_cents: int, sl_total: float, market_opened: datetime,
    btc_to_beat: float | None, btc_spot_at_buy: float | None,
) -> str:
    """
    Poll the position; exit on TARGET (bid ≥ tp_cents, or the resting TP limit
    fills) or STOP-LOSS (live value ≤ sl_total).  Logs exactly one CSV row and
    returns the exit reason.
    """
    market_close = market_opened + timedelta(seconds=MARKET_LEN_S)
    if(tp_cents>88):
      tp_cents = 88
      # sl_total = int(round(88*buy_contracts)/100)
    print(f"  [MONv3] {direction.upper()}  entry=${entry_total:.2f} "
          f"({buy_contracts}×{avg_cents}¢)  TP {tp_cents}¢  SL ${sl_total:.2f}")

    # Extremes of the live bid (dollars) seen while holding — used to derive
    # MAX_LOSS_PCT (worst drawdown vs entry) and MAX_PROFIT_PCT (best gain vs
    # entry) for CSV tuning.  Read by _log via closure; updated in the loop.
    _min_bid: float | None = None
    _max_bid: float | None = None

    async def _log(result: str, exit_cents: int) -> str:
        exit_total = (exit_cents / 100.0) * buy_contracts
        try:
            pv_after = await portfolio_balance(c)
        except Exception:
            pv_after = 0.0
        # MAX_LOSS_PCT  = (avg − lowest bid) / avg × 100   (drawdown, ≥0 worse)
        # MAX_PROFIT_PCT = (highest bid − avg) / avg × 100  (peak gain, ≥0 better)
        max_loss_pct = max_profit_pct = None
        if avg_cents > 0:
            if _min_bid is not None:
                max_loss_pct = (avg_cents - _min_bid * 100) / avg_cents * 100
            if _max_bid is not None:
                max_profit_pct = (_max_bid * 100 - avg_cents) / avg_cents * 100
        try:
            log_trade(
                ticker=ticker, mode="BUY", direction=direction,
                contracts=buy_contracts, entry=avg_cents,
                exit_=exit_total, pnl=exit_total - entry_total,
                result=result, pv=pv_after, btc_to_beat=btc_to_beat,
                btc_spot_at_buy=btc_spot_at_buy, btc_spot_at_sell=None,
                max_loss_pct=max_loss_pct, max_profit_pct=max_profit_pct,
            )
        except Exception as e:
            print(f"  [MONv3] log_trade failed: {e}")
        _ml = f"{max_loss_pct:.1f}%" if max_loss_pct is not None else "n/a"
        _mp = f"{max_profit_pct:.1f}%" if max_profit_pct is not None else "n/a"
        print(f"  [MONv3] EXIT {result}  exit≈{exit_cents}¢  "
              f"pnl≈${exit_total - entry_total:+.2f}  "
              f"MAX_LOSS={_ml}  MAX_PROFIT={_mp}")
        return result

    # Wait for the position to appear.
    for _ in range(12):
        pos = await position_for(c, ticker)
        if pos and pos["contracts"] > 0:
            break
        await asyncio.sleep(5)

    while True:
        curr_direction, live_btc = await determine_direction_mon(c)
        pos = await position_for(c, ticker)
        # Position closed → resting TP limit filled.
        if pos is None or pos["contracts"] == 0:
            pending = await resting_orders(c, ticker)
            if pending:
                await cancel_all(c)
            return await _log("V3_TAKE_PROFIT", tp_cents)

        contracts  = pos["contracts"]
        bid        = await _bid_price(c, ticker, direction)
        if bid is not None:
            if _min_bid is None or bid < _min_bid:
                _min_bid = bid
            if _max_bid is None or bid > _max_bid:
                _max_bid = bid
        bid_c      = int(round(bid * 100)) if bid is not None else None
        live_value = (bid * contracts) if bid is not None else None
        t_left     = max(0.0, (market_close - _utc_now()).total_seconds())

        # TARGET met → fire-sell to lock the win.
        if bid_c is not None and bid_c > tp_cents:
            print(f"  [MONv3] TARGET met (bid {bid_c}¢ ≥ TP {tp_cents}¢) — fire-sell.")
            await cancel_all(c)
            await asyncio.sleep(1)
            await _fire_sale(c, ticker, direction, contracts)
            await asyncio.sleep(2)
            return await _log("V3_TAKE_PROFIT", bid_c)

        # STOP-LOSS hit → fire-sell.
        if live_value is not None and live_value <= sl_total and curr_direction != direction:
            print(f"  [MONv3] STOP-LOSS (value ${live_value:.2f} ≤ SL ${sl_total:.2f}) "
                  f"— fire-sell.")
            await cancel_all(c)
            await asyncio.sleep(1)
            await _fire_sale(c, ticker, direction, contracts)
            await asyncio.sleep(2)
            return await _log("V3_STOP_LOSS", (bid_c or FIRE_SALE_CENTS))
        # Market closing → stop monitoring, ride to settlement.
        if t_left <= 1:
            return await _log("V3_SETTLE", (bid_c or 0))
        _val_s = f"${live_value:.2f}" if live_value is not None else "N/A"
        print(f"  [MONv3] bid={bid_c}¢ X TP={tp_cents}¢  cur_val={_val_s}    "
              f"SL=${sl_total:.2f}  t_left={t_left:.0f}s  "
              f"LIVE X BEAT = ={live_btc} X {btc_to_beat}  "
              f"{curr_direction} XX {direction}")
        yes_diff = 0
        no_diff = 0
        if(direction == 'yes'):
           yes_diff = live_btc - btc_to_beat
        else:
           no_diff = btc_to_beat - live_btc
          
        if bid_c is not None and bid_c > 80:
            print(f"  [MONv3] SAFE TARGET met (bid {bid_c}¢ ≥ TP {tp_cents}¢) — fire-sell.")
            await cancel_all(c)
            await asyncio.sleep(1)
            await _fire_sale(c, ticker, direction, contracts)
            await asyncio.sleep(2)
            return await _log("V3_TAKE_PROFIT", bid_c)

        if bid_c is not None and bid_c > avg_cents+2 and curr_direction != direction:
              print(f"  [MONv3] TARGET met (bid {bid_c}¢ ≥ TP {tp_cents}¢) — fire-sell.")
              await cancel_all(c)
              await asyncio.sleep(1)
              await place_tp_sell(c, ticker, direction, buy_contracts, avg_cents+4)
              #await _fire_sale(c, ticker, direction, contracts)
              await asyncio.sleep(2)
              return await _log("V3_SAFE_EXIT", bid_c)
        if bid_c is not None and curr_direction != direction:
            if((direction == 'yes') and  (yes_diff < -20)) or ((direction == 'no') and  (no_diff < -20)):
                print(f"  [MONv3] DIRECTION CHANGED fire-sell.")
                await cancel_all(c)
                await asyncio.sleep(1)
                await _fire_sale(c, ticker, direction, contracts)
                await asyncio.sleep(2)
                return await _log("V3_LOSS_FLIPPED_DIRECTION", bid_c)

        await asyncio.sleep(MON_POLL_S)

# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  MAIN LOOP (v3)                                                          ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def run() -> None:
    _log_fh    = _RotatingLogFile()
    sys.stdout = _Tee(sys.__stdout__, _log_fh)
    sys.stderr = _Tee(sys.__stderr__, _log_fh)
    print(f"[LOG] v3 session started — logging to {_log_fh.name}")
    print(f"[CFG] DRY_RUN={DRY_RUN}  CONTRACTS_PV_PCT={CONTRACTS_PV_PCT}  "
          f"band={MIN_ENTRY_CENTS}-{MAX_ENTRY_CENTS}¢  "
          f"TIME_SEC_TO_ORDER={TIME_SEC_TO_ORDER}  "
          f"DO_YOU_HAVE_STOP_SELL={DO_YOU_HAVE_STOP_SELL}  "
          f"MONITOR_SL_TRIGGER={MONITOR_SL_TRIGGER}")

    init_csv()
    c = KalshiClient()
    btc = BtcVidyaMonitor()
    btc.start()
    current_ticker: str | None = None
    # Live references to background bid-price loggers (one per market) so they
    # aren't garbage-collected while running.
    _bid_tasks: set = set()
    try:
        while True:
            market         = await wait_for_market(c, skip=current_ticker)
            # ── BANK-TARGET (common bot contract, user 08/03): flat here, so
            # stopping cannot strand a position.
            if v1.BANKROLL.target_reached():
                await _halt_and_shutdown(
                    c, market["ticker"], reason_tag="BANK-TARGET HALT",
                    reason_msg=(f"TP reached on bank: ${v1.BANKROLL.balance:.2f} "
                                f"= +{v1.BTC15_TARGET_PCT:.0f}% on "
                                f"${v1.BANKROLL.start:.2f} — stopping."),
                )
                return
            if v1.BANKROLL.sl_reached():
                await _halt_and_shutdown(
                    c, market["ticker"], reason_tag="BANK-SL HALT",
                    reason_msg=(f"SL HIT on Bank: ${v1.BANKROLL.balance:.2f} "
                                f"<= -{v1.BTC15_BANK_SL_PCT:.0f}% on "
                                f"${v1.BANKROLL.start:.2f} — stopping."),
                )
                return
            ticker         = market["ticker"]
            current_ticker = ticker
            market_opened  = _market_opened(market)
            market_close   = market_opened + timedelta(seconds=MARKET_LEN_S)
            btc_to_beat    = _strike_of(market)

            print(f"\n{'═' * 64}\n  MARKET : {ticker}"
                  f"   (up to {MAX_TRADES_PER_MARKET} trade(s))\n{'═' * 64}")

            # ── TIME HALT (trading hours) ────────────────────────────────────
            _local_now = datetime.now(ZoneInfo(HALT_TIMEZONE))
            _win = _in_halt_window(_local_now.time())
            if _win is not None:
                await _halt_and_shutdown(
                    c, ticker, reason_tag="TRADING-HOURS HALT",
                    reason_msg=(f"Local {_local_now.strftime('%H:%M')} "
                                f"({HALT_TIMEZONE}) inside halt window "
                                f"{_win[0].strftime('%H:%M')}–{_win[1].strftime('%H:%M')}."),
                )
                return

            for trade_no in range(1, MAX_TRADES_PER_MARKET + 1):
                # ── NO-TRADE window (user 08/03): stay alive, enter nothing.
                _ntw = v1._in_no_trade_window()
                if _ntw is not None:
                    print(f"  [NO-TRADE] local time inside "
                          f"{_ntw[0]:%H:%M}-{_ntw[1]:%H:%M} - no entries this "
                          f"market; monitoring only")
                    break
                # Order-window time gate.
                _ttc = (market_close - _utc_now()).total_seconds()
                if _ttc <= MIN_TIME_TO_CLOSE_S:
                    print(f"  [TIME-GATE] {_ttc:.0f}s to close ≤ {MIN_TIME_TO_CLOSE_S}s "
                          f"— next market.")
                    break

                print(f"\n  ── Trade {trade_no}/{MAX_TRADES_PER_MARKET} on {ticker} "
                      f"({_ttc:.0f}s to close) ──")

                pv = await portfolio_balance(c)
                print(f"  Portfolio: ${pv:.2f}")

                # ── LOSS RATE HALT (profit-ratcheted PV-Returns floor) ───────
                _wr = compute_prediction_win_rate()
                _gain_str = _wr.get("pv_returns") or ""
                _gain_pct = float(_gain_str.strip().rstrip("%")) if _gain_str else 0.0
                if _wr.get("pv_total", 0) > 0:
                    print(f"  [WIN RATE] SUCCESS {_wr['rate']:.1f}%  "
                          f"LOSS {_wr['loss_rate']:.1f}%  PV Returns {_gain_str or 'n/a'}")
                if _gain_pct > 100:
                    _halt_floor = MAX_LOSS_RATE - 275
                elif _gain_pct > 75:
                    _halt_floor = MAX_LOSS_RATE - 175
                elif _gain_pct > 50:
                    _halt_floor = MAX_LOSS_RATE - 75
                else:
                    _halt_floor = -MAX_LOSS_RATE
                if _gain_pct < _halt_floor:
                    await _halt_and_shutdown(
                        c, ticker, reason_tag="LOSS-RATE HALT",
                        reason_msg=(f"PV Returns {_gain_str} < floor "
                                    f"{_halt_floor}% — halting."),
                    )
                    return

                # ── PORTFOLIO LIMIT: MIN-PV ──────────────────────────────────
                if pv < DO_NOT_BUY_IF_PORTFOLIO_BELOW:
                    await _halt_and_shutdown(
                        c, ticker, reason_tag="MIN-PV HALT",
                        reason_msg=(f"Portfolio ${pv:.2f} < "
                                    f"${DO_NOT_BUY_IF_PORTFOLIO_BELOW} — halting."),
                    )
                    return

                # ── PORTFOLIO LIMIT: TARGET-PV ───────────────────────────────
                if TARGET_PORTFOLIO_PCT > 0:
                    _day_start_pv = get_day_start_portfolio(pv)
                    _target_pv    = _day_start_pv * (1 + TARGET_PORTFOLIO_PCT / 100.0)
                    _gain_today   = (((pv - _day_start_pv) / _day_start_pv * 100.0)
                                     if _day_start_pv > 0 else 0.0)
                    print(f"  [TARGET-PV] day-start=${_day_start_pv:.2f}  "
                          f"target=${_target_pv:.2f} (+{TARGET_PORTFOLIO_PCT:.0f}%)  "
                          f"today={_gain_today:+.2f}%")
                    if pv >= _target_pv:
                        await _halt_and_shutdown(
                            c, ticker, reason_tag="TARGET-PV HALT",
                            reason_msg=(f"HIT — ${pv:.2f} ≥ target "
                                        f"${_target_pv:.2f}. No new orders."),
                        )
                        return

                # ── DIRECTION (best-of-3 Coinbase signals) ───────────────────
                direction2, actual_prev = await determine_direction_v2(c, btc, btc_to_beat)
                direction3, live_btc, overall_score = await determine_direction_v3(c)
                if (direction2 != direction3):
                   await asyncio.sleep(7)
                   direction, live_btc, overall_score = await determine_direction_v3(c)
                   if (direction != direction3):
                       await asyncio.sleep(35)
                       direction, live_btc, overall_score = await determine_direction_v3(c)
                   elif (overall_score < 1 and direction == "yes"):
                        await asyncio.sleep(35)
                        direction, live_btc, overall_score = await determine_direction_v3(c)
                   elif (overall_score > 0 and direction == "no"):
                       await asyncio.sleep(35)
                       direction, live_btc, overall_score = await determine_direction_v3(c)
                   else:
                      direction = direction2
                   if (overall_score < 1 and direction == "yes"):
                       await asyncio.sleep(60)
                       direction, live_btc, overall_score = await determine_direction_v3(c)
                   if (overall_score >= 1 and direction == "no"):
                       await asyncio.sleep(60)
                       direction, live_btc, overall_score = await determine_direction_v3(c)
                else:
                      direction = direction3   
                # ── Bid-price recorder (once per market, for future analysis) ─
                if trade_no == 1:
                    _bt = asyncio.create_task(
                        bid_price_monitor(c, ticker, direction, market_opened))
                    _bid_tasks.add(_bt)
                    _bt.add_done_callback(_bid_tasks.discard)
                    print(f"  [BID-MON] recording {direction.upper()} bid every "
                          f"{BID_MONITOR_INTERVAL_S}s → {BID_MONITOR_LOG}")

                # ── ENTRY: wait for bid in band → place immediately ──────────
                ok, planning_to_buy, direction_new = await band_wait(c, ticker, direction, market_opened)
                direction = direction_new
                if not ok:
                    await asyncio.sleep(3)
                    continue

                # ── Sizing: FIXED contracts (common bot contract, user
                # 08/03). %-of-PV sizing removed desk-wide: the contracts the
                # operator typed are the contracts bought.
                _buy_contracts = max(1, v1.CONTRACTS)
                print(f"  [SIZE] fixed {_buy_contracts} contracts (KALSHI_CONTRACTS)")

                # ── Place buy immediately, wait for fill ─────────────────────
                resp = await place_buy(c, ticker, direction,
                                       buy_at_cents=planning_to_buy+10,
                                       contracts=_buy_contracts)
                if resp is None:
                    await asyncio.sleep(5)
                    continue
                odata = resp.get("order", {})

                if not await await_fill(c, ticker, timeout=300):
                    print("  [FILL] not filled — cancel + skip slot.")
                    await cancel_all(c)
                    await asyncio.sleep(3)
                    continue

                # ── avg_cents + TP/SL (same formula as v1) ───────────────────
                cost_str = odata.get("taker_fill_cost_dollars", "0")
                fee_str  = odata.get("taker_fees_dollars", "0")
                fill_cost = round(float(cost_str) + float(fee_str), 4)
                if fill_cost < 0.5:
                    fill_cost = round((max(1, planning_to_buy - 4) / 100) * _buy_contracts, 4)
                entry_total = fill_cost
                avg_cents = int(round(float(fill_cost / _buy_contracts), 2) * 100)
                tp_cents, sl_total = _tp_sl(avg_cents, _buy_contracts)
                print(f"  Entry: {_buy_contracts} × {avg_cents}¢ = ${entry_total:.2f}  "
                      f"|  TP {tp_cents}¢  |  SL ${sl_total:.2f}")

                # ── Exit handling ────────────────────────────────────────────
                if DO_YOU_HAVE_STOP_SELL and MONITOR_SL_TRIGGER:
                    await asyncio.sleep(10)   # let the fill register
                    pos = await position_for(c, ticker)
                    real_contracts = (pos["contracts"]
                                      if (pos and pos["contracts"] > 0) else _buy_contracts)
                    # if pos and pos["contracts"] > 0:
                    #     await place_tp_sell(c, ticker, direction, real_contracts, tp_cents)
                    await monitor_trade_v3(
                        c, ticker, direction,
                        entry_total=entry_total, avg_cents=avg_cents,
                        buy_contracts=_buy_contracts, tp_cents=tp_cents, sl_total=sl_total,
                        market_opened=market_opened, btc_to_beat=btc_to_beat,
                        btc_spot_at_buy=live_btc,
                    )
                else:
                    # No protective orders / monitor — log the entry and let it
                    # settle naturally.
                    await cancel_all(c)
                    await asyncio.sleep(1)
                    await place_tp_sell(c, ticker, direction, _buy_contracts, 95)
                    print(f"  [EXIT] DO_YOU_HAVE_STOP_SELL={DO_YOU_HAVE_STOP_SELL} / "
                          f"MONITOR_SL_TRIGGER={MONITOR_SL_TRIGGER} — no monitor; "
                          f" BEAT: >> {btc_to_beat} :: {direction}")
                    #pv_after = await portfolio_balance(c)
                    # Crash protection while riding to settlement: fire-sell if
                    # the held side's bid drops below EXIT_DROP_CENTS.
                   # _drop_reason = await monitor_trade_exit_drop( c, ticker, direction, market_opened, _buy_contracts)
                    pv_after = await portfolio_balance(c)
                    log_trade(
                        ticker=ticker, mode="BUY", direction=direction,
                        contracts=_buy_contracts, entry=avg_cents,
                        exit_=0.0, pnl=0.0,
                        result= "V3_NO_MONITOR",
                        pv=pv_after,
                        btc_to_beat=btc_to_beat, btc_spot_at_buy=live_btc,
                        btc_spot_at_sell=None,
                    )

                await asyncio.sleep(5)
            # ── end inner trade loop → next market ───────────────────────────
    finally:
        # Cancel any in-flight bid-price loggers.
        for _t in list(_bid_tasks):
            _t.cancel()
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
