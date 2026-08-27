#!/usr/bin/env python3
"""
v2_bot_kalshi_btc15.py — Kalshi BTC-15M bot, v2 strategy.
=========================================================
A leaner, score-driven variant of bot_kalshi_btc15.py.  It REUSES the v1
module's battle-tested infrastructure (async Kalshi client, CSV/log helpers,
market discovery, order builders, price poller, compute_signal, TP/SL math,
fire-sale, portfolio helpers, trading-hours halt) and only re-implements the
pieces that differ in v2:

  • STEP 3  — direction = best of FOUR voters (V1 settled, V2 live-vs-strike,
              V3 btcSignalWithStrength, V4 btcSignalHourly).  Ties → V4.
  • Entry   — NO flipping.  If the entry scan says "sell" we simply re-poll
              the ORIGINAL direction up to 3 times, then skip the slot.
              Entry price = the cheapest confirmed in-band bid (cheaper =
              more TP headroom toward the 91¢ cap + smaller capital at risk;
              the 2026-06-01 log/CSV showed accepted entries clustered
              40–65¢ with no statistically usable price edge across only 6
              settled outcomes, so we optimise for cost, not a fitted price).
              Direction is REVALIDATED (best-of-4) at the moment of entry.
  • Sizing  — CONTRACTS_PV_PCT of portfolio; a desk-fixed size wins when
              KALSHI_CONTRACTS is set with CONTRACTS_PV_PCT=0 (user 08/03).
              The same contract count + avg_cents are reused everywhere
              until the market closes.
  • Monitor — monitor_trade_v2(): a SELL_SCORE accumulator fed by three
              market signals (MS1 bid-momentum, MS2 live-vs-strike,
              MS3 strong-signal) on a ~15s cadence, plus bid/time-based
              fire-sale rules.  SELL_SCORE resets every 90s.

Lotto trades are intentionally NOT implemented in this file.

Run:
    python v2_bot_kalshi_btc15.py
"""
from __future__ import annotations

import asyncio
import math
import os
import sys
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Make the shared btc/ package and the v1 module importable whether this
#    bot is launched standalone (cwd=kalshi/) or from the project root. ───────
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))   # project root  → `import btc`
sys.path.insert(0, str(_HERE))          # kalshi/        → `import bot_kalshi_btc15`

# Default to SEPARATE v2 outputs for standalone runs WITHOUT clobbering the
# dispatcher's env (setdefault only fills in when unset).  Must run BEFORE the
# v1 import because v1 binds CSV_FILE / log prefix at import time.
os.environ.setdefault("BOT_CSV_PATH",   str(_HERE / "v2_trade_history.csv"))
os.environ.setdefault("BOT_LOG_PREFIX", "v2_kalshi_btc_15_")

import bot_kalshi_btc15 as v1          # noqa: E402  (v1 infrastructure)
from btc import BtcVidyaMonitor        # noqa: E402

# ── Pull the bits we reuse into local names for readability ───────────────────
KalshiClient        = v1.KalshiClient
_bid_price          = v1._bid_price
compute_signal      = v1.compute_signal
_mk_order           = v1._mk_order
place_buy           = v1.place_buy
await_fill          = v1.await_fill
place_tp_sell       = v1.place_tp_sell
_tp_sl              = v1._tp_sl
_fire_sale          = v1._fire_sale
position_for        = v1.position_for
resting_orders      = v1.resting_orders
cancel_all          = v1.cancel_all
portfolio_balance   = v1.portfolio_balance
init_csv            = v1.init_csv
log_trade           = v1.log_trade
wait_for_market     = v1.wait_for_market
determine_direction = v1.determine_direction
flip                = v1.flip
_in_halt_window     = v1._in_halt_window
_halt_and_shutdown  = v1._halt_and_shutdown
_RotatingLogFile    = v1._RotatingLogFile
_Tee                = v1._Tee
_utc_now            = v1._utc_now
_cst_now            = v1._cst_now

DRY_RUN                       = v1.DRY_RUN
TIME_SEC_TO_ORDER             = v1.TIME_SEC_TO_ORDER
MIN_ENTRY_CENTS               = v1.MIN_ENTRY_CENTS
MAX_ENTRY_CENTS               = v1.MAX_ENTRY_CENTS
CONTRACTS_PV_PCT              = v1.CONTRACTS_PV_PCT
MAX_TRADES_PER_MARKET         = v1.MAX_TRADES_PER_MARKET
DO_NOT_BUY_IF_PORTFOLIO_BELOW = v1.DO_NOT_BUY_IF_PORTFOLIO_BELOW
HALT_TIMEZONE                 = v1.HALT_TIMEZONE
FIRE_SALE_CENTS               = v1.FIRE_SALE_CENTS
SELL_PCT_THRESHOLD            = v1.SELL_PCT_THRESHOLD
DO_YOU_HAVE_STOP_SELL         = v1.DO_YOU_HAVE_STOP_SELL
TARGET_PORTFOLIO_PCT          = v1.TARGET_PORTFOLIO_PCT
get_day_start_portfolio       = v1.get_day_start_portfolio

# v2-specific: only place sell orders (proactive-TP + SELL_SCORE/bid/time
# fire-sales) inside monitor_trade_v2 when TRUE.  When FALSE the monitor still
# runs and logs, but never triggers a sell — positions ride to settlement / the
# resting TP limit.  (.env is already loaded by the v1 import above.)
MONITOR_SL_TRIGGER            = os.getenv("MONITOR_SL_TRIGGER", "TRUE").upper() == "TRUE"

from zoneinfo import ZoneInfo

# ── v2 tunables ───────────────────────────────────────────────────────────────
MARKET_LEN_S          = 900    # Kalshi BTC-15M cycle length (s)
MIN_TIME_TO_CLOSE_S   = 470    # only place an order with > this many seconds left
ENTRY_RETRIES         = 6      # (unused) entry retries are now capped by the
                               # order window (TIME_SEC_TO_ORDER), not a count
POLL_MAX_TICKS        = 40     # max ticks for every entry poll_for_signal
POLL_WINDOW           = 20     # compute_signal window
POLL_SENTIMENT_SIZE   = 30     # full-decision sentiment buffer
POLL_EARLY_FLOOR      = 20     # early-exit math active once fill ≥ this

# Direction-vote dead bands
V2_STRIKE_BUFFER      = 4.0   # ±$ for STEP-3 V2 live-vs-strike

# Entry-scan flip: on a "sell" verdict, if BUY_SCORE for the chosen direction
# is below this, flip to the opposite direction (override) and continue.
FLIP_BUY_SCORE        = -10

# Conviction gate (inside band_guard_v2).  After the price/BTC/signal gates
# pass, a ~30s BUY_SCORE scan must clear a price-tier threshold:
#   cheap bid (< $0.40)  → BUY_SCORE > BUY_SCORE_MIN
#   pricier bid (≥ $0.40)→ BUY_SCORE ≥ BUY_SCORE_MIN_PRICEY
BUY_SCORE_MIN         = 2      # cheap-bid conviction floor (strict >)
BUY_SCORE_MIN_PRICEY  = -2     # pricier-bid conviction floor (≥)
BUY_SCORE_PRICE_TIER  = 0.40   # bid (dollars) splitting cheap vs pricier

# Per-market bid-price logger (separate background recorder)
BID_MONITOR_LOG        = str(Path(os.getenv("BOT_LOG_DIR", ".")) / "bid_price_monitor.log")
BID_MONITOR_INTERVAL_S = 30    # record the chosen direction's bid every N s

# Monitor (SELL_SCORE) tunables
MON_MS1_TICKS         = 30     # MS1 inner scan: 30 ticks …
MON_MS1_INTERVAL_S    = 0.50   # … × 0.50s ≈ 15s per cycle
MON_MS2_DIR_BUFFER    = 2.0    # ±$ dead band for MS2 direction
MON_MS2_STEP_DOLLARS  = 10.0   # $ per ±1 score step
MON_MS2_STEP_CAP      = 10     # cap |MS2| score per cycle
MON_SELL_SCORE_FIRE   = 24  # ***********SELL_SCORE ≥ this (+ BTC against) → fire-sell *********TBD*********
MON_AGAINST_BUFFER    = 10.0   # ±$ for "BTC against ordered direction" check
MON_SCORE_RESET_S     = 90     # reset SELL_SCORE every N seconds
# Bid/time fire-sale rules (cents / seconds-remaining)
MON_HIGH_BID_LOCK     = 95     # bid > this → lock the win
MON_MIDLOW_BID_LO     = 40
MON_MIDLOW_BID_HI     = 60
MON_MIDLOW_TIME_S     = 90     # … with ≤ this many seconds left → cut
MON_MIDHI_BID_LO      = 60
MON_MIDHI_BID_HI      = 70
MON_MIDHI_TIME_S      = 45
MON_RIDE_BID          = 70     # bid > this with ≤ MON_MIDHI_TIME_S left → ride to settle


def _market_opened(market: dict) -> datetime:
    """Parse the market open_time into a tz-aware UTC datetime (fallback now)."""
    ot = market.get("open_time", "")
    if ot:
        try:
            return datetime.fromisoformat(ot.replace("Z", "+00:00"))
        except Exception:
            pass
    return _utc_now()


def _strike_of(market: dict) -> float | None:
    raw = (market.get("strike_price")
           or market.get("floor_strike")
           or market.get("cap_strike"))
    try:
        return float(raw) if raw is not None else None
    except Exception:
        return None


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  STEP 3 (v2) — BEST OF FOUR DIRECTION VOTERS                            ║
# ╚════════════════════════════════════════════════════════════════════════════╝
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


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  ENTRY SIGNAL SCAN (v2) — 40-tick poll w/ both-direction early-exit     ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def poll_entry_signal_v2(
    c: KalshiClient, ticker: str, direction: str, *,
    btc: BtcVidyaMonitor,
    interval_s: float = 0.50,
    window: int = POLL_WINDOW,
    max_ticks: int = POLL_MAX_TICKS,
    sentiment_size: int = POLL_SENTIMENT_SIZE,
    sell_pct: float = SELL_PCT_THRESHOLD,
    early_floor: int = POLL_EARLY_FLOOR,
) -> str:
    """
    Sentiment scan of the CURRENT direction's bid stream.  Returns "buy"
    (direction looks healthy) or "sell" (direction's price is sinking).
    Never returns "hold": on inconclusive max-ticks it falls back to the BTC
    strong signal mapped to this contract's polarity.

    Early-exit (mathematical short-circuit, BOTH directions) is active once
    the sentiment buffer fill ≥ early_floor and < sentiment_size:
      • max-possible sell_ratio < sell_pct   → "buy"  (SELL unreachable)
      • sells / sentiment_size  > sell_pct   → "sell" (SELL guaranteed)
    """
    buf: deque[float] = deque(maxlen=window)
    sentiment: deque[str] = deque(maxlen=sentiment_size)

    for tick in range(1, max_ticks + 1):
        fetch = asyncio.create_task(_bid_price(c, ticker, direction))
        timer = asyncio.create_task(asyncio.sleep(interval_s))
        price = await fetch
        await timer
        if price is None:
            continue
        buf.append(price)
        sig = compute_signal(buf)
        if sig == "strong_sell":
            print(f"    [POLLv2 {tick:03d}] {direction} STRONG_SELL → SELL")
            return "sell"
        if sig == "sell":
            sentiment.append("sell")
        elif sig == "buy":
            sentiment.append("buy")

        sells = sum(1 for s in sentiment if s == "sell")
        fill  = len(sentiment)

        if early_floor <= fill < sentiment_size:
            max_ratio = (sells + (sentiment_size - fill)) / sentiment_size
            if max_ratio < sell_pct:
                print(f"    [POLLv2 {tick:03d}] ⚡ SELL unreachable "
                      f"(max {max_ratio:.0%} < {sell_pct:.0%}) → BUY")
                return "buy"
            min_ratio = sells / sentiment_size
            if min_ratio > sell_pct:
                print(f"    [POLLv2 {tick:03d}] ⚡ SELL guaranteed "
                      f"(min {min_ratio:.0%} > {sell_pct:.0%}) → SELL")
                return "sell"

        if fill >= sentiment_size:
            sell_ratio = sells / fill
            verdict = "sell" if sell_ratio > sell_pct else "buy"
            print(f"    [POLLv2 {tick:03d}] full sentiment "
                  f"sell={sell_ratio:.0%} → {verdict.upper()}")
            return verdict

    # Inconclusive — fall back to whether BTC favours THIS direction.
    # NOTE: the verdict is "is `direction` healthy?", NOT BTC's yes/no lean.
    #   BTC buy/strong_buy   → favours YES
    #   BTC sell/strong_sell → favours NO
    #   BTC hold             → neutral
    # If BTC favours our direction (or is neutral) → "buy" (proceed); only a
    # BTC signal OPPOSING our direction returns "sell" (skip).  The previous
    # code mapped BTC sell → "sell" regardless of direction, which wrongly
    # skipped NO entries when BTC was bearish (i.e. when BTC *agreed* with NO).
    s = btc.btcSignalWithStrength() if btc else "hold"
    if s in ("buy", "strong_buy"):
        btc_favored: str | None = "yes"
    elif s in ("sell", "strong_sell"):
        btc_favored = "no"
    else:
        btc_favored = None
    fb = "sell" if (btc_favored is not None and btc_favored != direction) else "buy"
    print(f"    [POLLv2 ---] max_ticks exhausted → BTC {s.upper()} favours "
          f"{(btc_favored or 'NEUTRAL').upper()} vs dir {direction.upper()} "
          f"→ {fb.upper()}")
    return fb


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  BAND GUARD (v2) — cheapest in-band entry + direction revalidation      ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def band_guard_v2(
    c: KalshiClient, ticker: str, direction: str, *,
    btc: BtcVidyaMonitor, btc_to_beat: float | None, market_opened: datetime,
    is_flipped: bool = False,
) -> tuple[bool, int, int]:
    """
    Wait for a good IN-BAND entry on ``direction``.  Prefers the cheaper half
    of the band early (more TP headroom, less capital at risk); relaxes to the
    full band once the market is > 70% through the order window.

    Gate order at each poll: price band → BTC-favours-direction → Kalshi
    signal → BUY_SCORE conviction (~30s scan, price-tiered).  Only when ALL
    gates pass does it re-fetch the LATEST bid and return it as
    planning_to_buy (the price may have drifted during the BUY_SCORE scan).

    ``is_flipped`` — set True when ``direction`` is a deliberate entry-scan
    flip (BUY_SCORE for the original side was very negative).  A flip overrides
    the consensus, so the BTC-favours-direction gate is BYPASSED; the price
    band, Kalshi signal, and BUY_SCORE gates still apply.

    Returns (ok, planning_to_buy_cents, buy_score).  ok=False → skip slot.
    """
    band_lo = MIN_ENTRY_CENTS
    band_hi = MAX_ENTRY_CENTS
    preferred_hi = min(band_hi, band_lo + (band_hi - band_lo) // 2)
    buf: deque[float] = deque(maxlen=POLL_WINDOW)

    while True:
        age = (_utc_now() - market_opened).total_seconds()
        if age > TIME_SEC_TO_ORDER:
            print(f"  [BANDv2] window expired ({age:.0f}s) — skip slot.")
            return False, 0, 0

        peek = await _bid_price(c, ticker, direction)
        if peek is None:
            await asyncio.sleep(3)
            continue
        buf.append(peek)
        bid_c = int(round(peek * 100))

        sig    = compute_signal(buf) if len(buf) >= 16 else "hold"
        btc_s  = btc.latestBtcVidyaSignal() if btc else "hold"
        btc_ok = ((direction == "yes" and btc_s == "buy") or
                  (direction == "no"  and btc_s == "sell"))
        # A deliberate flip overrides the BTC-favours-direction gate.
        btc_gate = True if is_flipped else btc_ok
        in_band      = band_lo <= bid_c <= band_hi
        in_preferred = band_lo <= bid_c <= preferred_hi
        relaxed      = age > TIME_SEC_TO_ORDER * 0.70   # accept full band late

        # Acceptable price zone: preferred half early, full band late.
        price_ok = in_preferred or (relaxed and in_band)
        sig_ok   = sig not in ("sell", "strong_sell")

        if price_ok and btc_gate and sig_ok:
            # ── Revalidate direction before committing (skipped on a flip) ─
            #if not is_flipped:
            #    confirmed, _ = await determine_direction_v2(c, btc, btc_to_beat)
            #   if confirmed != direction:
            #        print(f"  [BANDv2] ✗ direction changed "
            #              f"{direction.upper()}→{confirmed.upper()} at entry — "
             #             f"skip slot.")
            #        return False, 0
            # ── Conviction gate: BUY_SCORE (~30s scan), price-tiered ───────
            _bscore = await compute_buy_score(c, ticker, direction,
                                              btc=btc, btc_to_beat=btc_to_beat)
            _cheap  = peek < BUY_SCORE_PRICE_TIER
            _conv   = ((_bscore > BUY_SCORE_MIN and _cheap) or
                       (_bscore >= BUY_SCORE_MIN_PRICEY and not _cheap))
            if not _conv:
                print(f"  [BANDv2] BUY_SCORE {_bscore:+d} fails conviction "
                      f"(bid={bid_c}¢, cheap={_cheap}) — keep waiting.")
                await asyncio.sleep(3)
                continue

            # All gates passed — return the LATEST bid (price may have drifted
            # during the ~30s BUY_SCORE scan).
            _latest   = await _bid_price(c, ticker, direction)
            _latest_c = int(round(_latest * 100)) if _latest is not None else bid_c
            _tag = "FLIP " if is_flipped else ""
            print(f"  [BANDv2] ✓ {_tag}entry @ {_latest_c}¢  BUY_SCORE={_bscore:+d}  "
                  f"(band {band_lo}-{band_hi}, pref ≤{preferred_hi}, "
                  f"relaxed={relaxed})  BTC={btc_s.upper()}  sig={sig.upper()}")
            return True, _latest_c, _bscore

        print(f"  [BANDv2] ⏳ {direction} bid={bid_c}¢ "
              f"[band:{'Y' if in_band else 'N'} pref:{'Y' if in_preferred else 'N'}]"
              f"  BTC={btc_s.upper()}[{'Y' if btc_ok else 'N'}]"
              f"{' (flip-override)' if is_flipped else ''}  "
              f"sig={sig.upper()}  age={age:.0f}s")
        await asyncio.sleep(3)


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  MONITOR (v2) — SELL_SCORE accumulator + bid/time fire-sale rules       ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def _ms1_sell_ratio(
    c: KalshiClient, ticker: str, ordered_direction: str,
    ticks: int = MON_MS1_TICKS, interval_s: float = MON_MS1_INTERVAL_S,
) -> float:
    """MS1: 30-tick × 0.5s (~15s) scan of the ordered side's bid stream.
    Returns the sell ratio = sells / (sells + buys)  (0.5 if no signal)."""
    buf: deque[float] = deque(maxlen=20)
    sells = buys = 0
    for _ in range(ticks):
        fetch = asyncio.create_task(_bid_price(c, ticker, ordered_direction))
        timer = asyncio.create_task(asyncio.sleep(interval_s))
        p = await fetch
        await timer
        if p is None:
            continue
        buf.append(p)
        s = compute_signal(buf)
        if s in ("sell", "strong_sell"):
            sells += 1
        elif s == "buy":
            buys += 1
    tot = sells + buys
    return (sells / tot) if tot else 0.5


def _ms1_score(sell_ratio: float) -> int:
    if sell_ratio < 0.30:
        return -2
    if sell_ratio < 0.45:
        return -1
    if sell_ratio < 0.55:
        return 0
    if sell_ratio <= 0.70:
        return 1
    return 2


def _ms2_score(live: float | None, strike: float | None, ordered: str) -> tuple[int, str]:
    """MS2: live BTC vs strike.  Same side as ordered → negative (hold),
    opposite → positive (sell).  ±MON_MS2_STEP_DOLLARS per ±1 step, capped."""
    if live is None or strike is None:
        return 0, "abstain"
    diff = live - strike
    if diff > MON_MS2_DIR_BUFFER:
        d = "yes"
    elif diff < -MON_MS2_DIR_BUFFER:
        d = "no"
    else:
        return 0, "abstain"
    steps = min(MON_MS2_STEP_CAP, int(abs(diff) // MON_MS2_STEP_DOLLARS))
    score = -steps if d == ordered else steps
    return score, d


def _ms3_score(strong: str, ordered: str) -> tuple[int, str]:
    """MS3: btcSignalWithStrength.  Matches ordered → negative; opposes →
    positive.  strong variants weigh 10, plain weigh 3."""
    mapping = {
        "strong_buy":  ("yes", 10),
        "strong_sell": ("no", 10),
        "buy":         ("yes", 3),
        "sell":        ("no", 3),
    }
    if strong not in mapping:
        return 0, "abstain"
    d, mag = mapping[strong]
    score = -mag if d == ordered else mag
    return score, d


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  BUY_SCORE — one-shot pre-order buy-confidence scan (~30s)              ║
# ╚════════════════════════════════════════════════════════════════════════════╝
# Buy-side mirror of the monitor's SELL_SCORE.  Unlike the monitor (which
# loops continuously), this runs ONCE for ~30s right before placing the order
# and prints the score.  Higher BUY_SCORE = more confidence in the direction.
BUY_SCAN_TICKS    = 60     # 60 ticks …
BUY_SCAN_INTERVAL = 0.50   # … × 0.50s ≈ 30s scan


def _bs1_score(buy_ratio: float) -> int:
    """BS1: buy-momentum (mirror of _ms1_score on the buy ratio)."""
    if buy_ratio < 0.30:
        return -2
    if buy_ratio < 0.45:
        return -1
    if buy_ratio < 0.55:
        return 0
    if buy_ratio <= 0.70:
        return 1
    return 2


async def compute_buy_score(
    c: KalshiClient, ticker: str, direction: str, *,
    btc: BtcVidyaMonitor, btc_to_beat: float | None,
    ticks: int = BUY_SCAN_TICKS, interval_s: float = BUY_SCAN_INTERVAL,
) -> int:
    """
    Compute & print a BUY_SCORE for ``direction`` from a single ~30s scan.
    Buy-oriented mirror of the SELL_SCORE signals:

      BS1  ~30s bid-momentum scan → buy ratio (buys / directional)
              >70% +2 | 55-70% +1 | 45-55% 0 | 30-45% -1 | <30% -2
      BS2  live BTC vs strike — BTC on our side → +steps, against → -steps
              (sign-flipped _ms2_score; ±$ per 10pt, capped)
      BS3  btcSignalWithStrength — matches direction → +, opposes → -
              (sign-flipped _ms3_score; strong ±10, plain ±3)

    Returns the integer BUY_SCORE (higher = more confident).  Informational
    only — does not gate order placement.
    """
    # BS1 — ~30s momentum scan of the direction's bid stream.
    sell_ratio = await _ms1_sell_ratio(c, ticker, direction,
                                       ticks=ticks, interval_s=interval_s)
    buy_ratio  = 1.0 - sell_ratio
    bs1 = _bs1_score(buy_ratio)

    # BS2 — live-vs-strike, flipped to a buy bias.
    live = btc.last_price if btc else None
    ms2, ms2_dir = _ms2_score(live, btc_to_beat, direction)
    bs2 = -ms2

    # BS3 — strong signal, flipped to a buy bias.
    strong = btc.btcSignalWithStrength() if btc else "hold"
    ms3, _ = _ms3_score(strong, direction)
    bs3 = -ms3

    score = int(bs1 + bs2 + bs3)
    print(f"  [BUY_SCORE] {direction.upper()} = {score:+d}  "
          f"BS1 buy={buy_ratio:.0%}({bs1:+d})  "
          f"BS2 {ms2_dir}({bs2:+d})  BS3 {strong.upper()}({bs3:+d})  "
          f"(~{ticks * interval_s:.0f}s scan)")
    return score


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  PER-MARKET BID-PRICE LOGGER (separate background recorder)             ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def bid_price_monitor(
    c: KalshiClient, ticker: str, direction: str, market_opened: datetime,
) -> None:
    """
    Independent recorder: append the CHOSEN direction's live bid (cents) every
    BID_MONITOR_INTERVAL_S seconds for the rest of the 15-min market to
    ``BID_MONITOR_LOG``.  Runs as a fire-and-forget background task — does not
    interact with the trade flow.  File format:

        [<ticker>] [<dir>] bid price live data for every 30 seconds
        [bid-price] [<dir>] [HH:MM:SS] <cents>
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


async def monitor_trade_v2(
    c: KalshiClient, ticker: str, ordered_direction: str, *,
    btc: BtcVidyaMonitor,
    btc_to_beat: float | None,
    entry_total: float,
    avg_cents: int,
    buy_contracts: int,
    tp_cents: int,
    sl_total: float,
    market_opened: datetime,
    btc_spot_at_buy: float | None,
    actual_direction_previous: str | None,
) -> str:
    """
    v2 position monitor.  Accumulates SELL_SCORE from MS1/MS2/MS3 every ~15s
    and exits on score + bid/time rules.  Logs the trade itself (one CSV row)
    and returns the exit reason.
    """
    market_close = market_opened + timedelta(seconds=MARKET_LEN_S)
    SELL_SCORE = 0
    score_reset_at = _utc_now()

    print(f"  [MONv2] ordered={ordered_direction.upper()}  entry=${entry_total:.2f} "
          f"({buy_contracts}×{avg_cents}¢)  TP {tp_cents}¢  SL ${sl_total:.2f}  "
          f"close={market_close.strftime('%H:%M:%S')}Z")

    async def _finish(result: str, exit_cents: int, do_fire: bool) -> str:
        """Common exit: optional fire-sale, then log + return."""
        if do_fire:
            try:
                await cancel_all(c)
                await asyncio.sleep(1)
                pos = await position_for(c, ticker)
                cn = pos["contracts"] if (pos and pos["contracts"] > 0) else buy_contracts
                await _fire_sale(c, ticker, ordered_direction, cn)
                await asyncio.sleep(2)
            except Exception as e:
                print(f"  [MONv2] fire-sale failed: {e}")
        exit_total = (exit_cents / 100.0) * buy_contracts
        try:
            pv_after = await portfolio_balance(c)
            _, adp = await determine_direction(c)
        except Exception:
            pv_after, adp = 0.0, actual_direction_previous
        try:
            log_trade(
                ticker=ticker, mode="BUY", direction=ordered_direction,
                contracts=buy_contracts, entry=avg_cents,
                exit_=exit_total, pnl=exit_total - entry_total,
                result=result, pv=pv_after,
                btc_to_beat=btc_to_beat, btc_spot_at_buy=btc_spot_at_buy,
                btc_spot_at_sell=(btc.last_price if btc else None),
                actual_direction_previous=adp,
            )
        except Exception as e:
            print(f"  [MONv2] log_trade failed: {e}")
        print(f"  [MONv2] EXIT {result}  exit≈{exit_cents}¢  "
              f"pnl≈${exit_total - entry_total:+.2f}")
        return result

    # Wait briefly for the position to appear.
    for _ in range(12):
        pos = await position_for(c, ticker)
        if pos and pos["contracts"] > 0:
            break
        await asyncio.sleep(5)

    while True:
        # ── TAKE-PROFIT detection (TP limit sell filled on the book) ─────────
        pos = await position_for(c, ticker)
        if pos is None or pos["contracts"] == 0:
            pending = await resting_orders(c, ticker)
            if not pending:
                return await _finish("V2_TAKE_PROFIT", tp_cents, do_fire=False)
            else:
                print(f"  [MONv2] position closed but order still resting "
                      f"({len(pending)}) — cancelling + finishing as TAKE_PROFIT.")
                await cancel_all(c)
                return await _finish("V2_TAKE_PROFIT", tp_cents, do_fire=False)

        # ── PROACTIVE TAKE-PROFIT (fixes stuck/unmatched resting TP) ─────────
        # A resting limit sell only fills when a *crossing* order arrives, so a
        # TP at 49¢ can sit unfilled even while the live bid is 67¢ (latency /
        # thin book / quote that never sent a marketable order through).  If we
        # still hold the (non-runner) position AND the live bid is at/above our
        # TP, the resting limit is effectively stuck — cancel it and SELL INTO
        # THE BID with a marketable order (fire-sale fills at the resting bid,
        # i.e. ≥ TP, never worse).
        _tp_bid = await _bid_price(c, ticker, ordered_direction)
        _tp_bid_c = int(round(_tp_bid * 100)) if _tp_bid is not None else None
        if (MONITOR_SL_TRIGGER
                and pos and pos["contracts"] > 0
                and _tp_bid_c is not None and _tp_bid_c >= tp_cents+2
                and DO_YOU_HAVE_STOP_SELL) :
            _sell_n = pos["contracts"]
            print(f"  [MONv2] PROACTIVE-TP: bid {_tp_bid_c}¢ ≥ TP {tp_cents}¢ but "
                  f"still holding {pos['contracts']} — resting TP not matched; "
                  f"selling {_sell_n} into the bid.")
            try:
                await cancel_all(c)
                await asyncio.sleep(1)
                await _fire_sale(c, ticker, ordered_direction, _sell_n)
                await asyncio.sleep(2)
            except Exception as e:
                print(f"  [MONv2] proactive-TP sell failed: {e}")
            return await _finish("V2_TP_ACTIVE", _tp_bid_c, do_fire=False)

        # ── Reset SELL_SCORE every 90s ───────────────────────────────────────
        if (_utc_now() - score_reset_at).total_seconds() >= MON_SCORE_RESET_S:
            print(f"  [MONv2] SELL_SCORE reset ({SELL_SCORE} → 0)")
            SELL_SCORE = 0
            score_reset_at = _utc_now()

        # ── MS1 (blocks ~15s) ────────────────────────────────────────────────
        ms1_ratio = await _ms1_sell_ratio(c, ticker, ordered_direction)
        s1 = _ms1_score(ms1_ratio)

        # ── MS2 / MS3 (instant reads) ────────────────────────────────────────
        live = btc.last_price if btc else None
        s2, ms2_dir = _ms2_score(live, btc_to_beat, ordered_direction)
        strong = btc.btcSignalWithStrength() if btc else "hold"
        s3, ms3_dir = _ms3_score(strong, ordered_direction)
        if((avg_cents < 35) and s2 >=10):
          s2 = s2/2
        SELL_SCORE += s1 + s2 + s3

        # ── Latest bid + timing for the exit rules ───────────────────────────
        bid = await _bid_price(c, ticker, ordered_direction)
        print(f"  [MONv2] live_bid_price={bid}  "
             f"  ordered_direction={ordered_direction}  ")
        bid_c = int(round(bid * 100)) if bid is not None else None
        time_remaining = max(0.0, (market_close - _utc_now()).total_seconds())

        # "BTC against ordered" (±$10 dead band)
        against = False
        if live is not None and btc_to_beat is not None:
            if ordered_direction == "yes" and live < btc_to_beat - MON_AGAINST_BUFFER:
                against = True
            elif ordered_direction == "no" and live > btc_to_beat + MON_AGAINST_BUFFER:
                against = True

        print(f"  [MONv2] SELL_SCORE={SELL_SCORE}  "
              f"MS1 sell={ms1_ratio:.0%}({s1:+d})  "
              f"MS2 {ms2_dir}({s2:+d})  MS3 {strong.upper()}({s3:+d})  "
              f"bid={bid_c}¢  t_left={time_remaining:.0f}s  against={against}")

        # ── Exit rules (first match wins) ────────────────────────────────────
        # The sell-triggering exits below are gated by MONITOR_SL_TRIGGER:
        # when FALSE the monitor never fire-sells (positions ride to settlement
        # / the resting TP limit), it only keeps observing + logging.
        if MONITOR_SL_TRIGGER and SELL_SCORE >= MON_SELL_SCORE_FIRE and against:
            print(f"  [MONv2] SELL_SCORE {SELL_SCORE} ≥ {MON_SELL_SCORE_FIRE} "
                  f"AND BTC against — fire-sell.")
            return await _finish("V2_SELL_SCORE", (bid_c or FIRE_SALE_CENTS), do_fire=True)

        if MONITOR_SL_TRIGGER and bid_c is not None and bid_c > MON_HIGH_BID_LOCK:
            print(f"  [MONv2] bid {bid_c}¢ > {MON_HIGH_BID_LOCK}¢ — lock the win.")
            return await _finish("V2_HIGH_BID_LOCK", bid_c, do_fire=True)

        if (MONITOR_SL_TRIGGER and bid_c is not None
                and MON_MIDLOW_BID_LO <= bid_c <= MON_MIDLOW_BID_HI
                and time_remaining <= MON_MIDLOW_TIME_S):
            print(f"  [MONv2] bid {bid_c}¢ in {MON_MIDLOW_BID_LO}-{MON_MIDLOW_BID_HI} "
                  f"with {time_remaining:.0f}s left — cut.")
            return await _finish("V2_LATE_MIDLOW_CUT", bid_c, do_fire=True)

        if (MONITOR_SL_TRIGGER and bid_c is not None
                and MON_MIDHI_BID_LO <= bid_c <= MON_MIDHI_BID_HI
                and time_remaining <= MON_MIDHI_TIME_S):
            print(f"  [MONv2] bid {bid_c}¢ in {MON_MIDHI_BID_LO}-{MON_MIDHI_BID_HI} "
                  f"with {time_remaining:.0f}s left — cut.")
            return await _finish("V2_LATE_MIDHI_CUT", bid_c, do_fire=True)

        if (bid_c is not None and bid_c > MON_RIDE_BID
                and time_remaining <= MON_MIDHI_TIME_S):
            print(f"  [MONv2] bid {bid_c}¢ > {MON_RIDE_BID}¢ with "
                  f"{time_remaining:.0f}s left — ride to settlement.")
            # No fire-sale: leave the TP sell resting and let it settle.
            return await _finish("V2_RIDE_SETTLE", (bid_c or 0), do_fire=False)

        # Market essentially over with no rule hit → stop monitoring.
        if time_remaining <= 1:
            print(f"  [MONv2] market closing — stop monitor, ride to settlement.")
            return await _finish("V2_SETTLE", (bid_c or 0), do_fire=False)

        # else continue monitoring (MS1 already consumed ~15s this cycle)


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  MAIN LOOP (v2)                                                          ║
# ╚════════════════════════════════════════════════════════════════════════════╝
# ── true P&L reconcile (user 08/03) ──────────────────────────────────────────
# The CSV's pnl at order time is the EXPECTED figure (limit price as exit).
# On every market rollover — e.g. at 16:00 for the 15:45 market — ask the
# exchange what actually happened (fills + settlement) and correct the row.
# Fills-only truth: sells − buys − fees + settlement revenue, priced on the
# token we HELD; a fill's own 'side' is order matching, not our holding.
_RECON_MAX_TRIES = 3      # settlement revenue can lag the close by a minute


def _recon_read_csv(ticker: str):
    """(all rows incl. header, matching data-row indexes, pnl col, dir col)."""
    import csv as _csv

    p = Path(v1.CSV_FILE)
    if not p.is_file():
        return None
    with p.open(newline="", encoding="utf-8") as f:
        rows = list(_csv.reader(f))
    if not rows:
        return None
    hdr = rows[0]
    try:
        i_tk, i_pnl, i_dir = hdr.index("ticker"), hdr.index("pnl"), hdr.index("direction")
    except ValueError:
        return None
    hits = [i for i in range(1, len(rows))
            if len(rows[i]) > i_tk and rows[i][i_tk] == ticker]
    return rows, hits, i_pnl, i_dir


async def _exchange_pnl(c, ticker: str, side: str):
    """(realized pnl, fill count) for one market, or (None, 0) if no fills yet.

    Kalshi records every fill as the token the account ACQUIRED — a sell of
    yes comes back ``side=no`` at the complementary price. So each fill is a
    cash OUTFLOW of count x fill_side_price + fee, matched yes/no pairs
    auto-redeem for $1, and settlement revenue covers whatever was held to
    the end. The previous held-side arithmetic inverted every NO trade's
    P&L (found 2026-08-05: booked +8.31 on a -9.69 loss). ``side`` is kept
    for signature compatibility; the fill's own side is authoritative.
    """
    d = await c.req("GET", "/portfolio/fills", params={"ticker": ticker, "limit": 200})
    fills = d.get("fills", [])
    if not fills:
        return None, 0
    cash = yes_cnt = no_cnt = 0.0
    for fx in fills:
        cnt = float(fx.get("count_fp") or fx.get("count") or 0)
        tok = (fx.get("side") or "yes").lower()
        px = float(fx.get("no_price_dollars" if tok == "no" else "yes_price_dollars") or 0)
        fee = float(fx.get("fee_cost") or 0)
        cash -= cnt * px + fee
        if tok == "no":
            no_cnt += cnt
        else:
            yes_cnt += cnt
    cash += min(yes_cnt, no_cnt)          # $1 auto-redemption per matched pair
    d = await c.req("GET", "/portfolio/settlements", params={"ticker": ticker, "limit": 20})
    n_sett = 0
    for s in d.get("settlements", []):
        if ticker in (s.get("ticker"), s.get("market_ticker")):
            cash += float(s.get("revenue") or 0) / 100.0
            n_sett += 1
    if abs(yes_cnt - no_cnt) > 1e-6 and n_sett == 0:
        # Contracts rode to settlement but the settlement record has not
        # posted yet (it lags the close by minutes). Returning None makes
        # _reconcile_prev_market retry next rollover instead of booking a
        # ride-to-settlement WINNER as a full loss and debiting the bankroll.
        return None, len(fills)
    return round(cash, 2), len(fills)


async def _reconcile_prev_market(c, ticker: str) -> bool:
    """Correct the previous market's CSV pnl from the exchange.

    Returns True when this ticker needs no further attempts (updated, already
    accurate, never traded, or unattributable) and False to retry next
    rollover — fills/settlement can lag the close.
    """
    got = _recon_read_csv(ticker)
    if got is None:
        return True
    _rows, hits, _i_pnl, i_dir = got
    if not hits:
        return True                       # never traded that market
    if len(hits) > 1:
        # one net exchange figure cannot be split across several rows without
        # inventing an allocation — say so instead of corrupting the ledger
        print(f"  [TRUEPNL] {ticker}: {len(hits)} CSV rows share the ticker - "
              f"net exchange P&L not attributable, leaving as logged")
        return True
    side = _rows[hits[0]][i_dir] if len(_rows[hits[0]]) > i_dir else "yes"
    try:
        pnl, n_fills = await _exchange_pnl(c, ticker, side)
    except Exception as e:                                    # noqa: BLE001
        print(f"  [TRUEPNL] {ticker}: exchange fetch failed ({e}) - will retry")
        return False
    if pnl is None:
        return False                      # fills not visible yet — retry

    # Re-read AFTER the awaits: the monitor could have appended a row while
    # the fills call was in flight, and rewriting from the stale copy would
    # silently drop it.
    got = _recon_read_csv(ticker)
    if got is None:
        return True
    rows, hits, i_pnl, _ = got
    if len(hits) != 1:
        return True
    row = rows[hits[0]]
    old = row[i_pnl] if len(row) > i_pnl else ""
    try:
        old_f = float(old or 0)
    except ValueError:
        old_f = 0.0
    if abs(pnl - old_f) < 0.005:
        print(f"  [TRUEPNL] {ticker}: CSV pnl {old or '0'} matches the exchange")
        return True
    row[i_pnl] = f"{pnl:.2f}"
    import csv as _csv

    tmp = Path(str(v1.CSV_FILE) + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        _csv.writer(f).writerows(rows)
    os.replace(tmp, v1.CSV_FILE)
    print(f"  [TRUEPNL] {ticker}: pnl {old or '0'} -> {pnl:.2f} "
          f"({n_fills} fill(s) + settlement - exchange truth)")
    # The bankroll ledger accrued the ESTIMATED pnl when the trade was logged
    # (log_trade -> BANKROLL.settle). Settle only the CORRECTION, so the
    # ledger sums to the exchange's number without counting the trade twice.
    # Applied in the same pass that rewrites the row: the row-change test
    # above is what makes this exactly-once across retries.
    _delta = round(pnl - old_f, 2)
    if _delta:
        v1.BANKROLL.settle(_delta)
    return True


async def run() -> None:
    _log_fh    = _RotatingLogFile()
    sys.stdout = _Tee(sys.__stdout__, _log_fh)
    sys.stderr = _Tee(sys.__stderr__, _log_fh)
    print(f"[LOG] v2 session started — logging to {_log_fh.name}")
    print(f"[CFG] DRY_RUN={DRY_RUN}  CONTRACTS_PV_PCT={CONTRACTS_PV_PCT}  "
          f"band={MIN_ENTRY_CENTS}-{MAX_ENTRY_CENTS}¢  "
          f"TIME_SEC_TO_ORDER={TIME_SEC_TO_ORDER}  "
          f"MONITOR_SL_TRIGGER={MONITOR_SL_TRIGGER}")

    init_csv()
    c = KalshiClient()
    btc = BtcVidyaMonitor()
    btc.start()

    current_ticker: str | None = None
    # Most recent pre-order BUY_SCORE (signed).  Kept at run() scope so it
    # persists across the loop and can feed future placement/exit logic.
    last_buy_score: int = 0
    # Live references to background bid-price loggers (one per market) so they
    # aren't garbage-collected while running.
    _bid_tasks: set = set()
    # markets whose CSV pnl still needs the exchange's number: [(ticker, tries)]
    _recon_pending: list = []
    try:
        while True:
            market        = await wait_for_market(c, skip=current_ticker)
            # ── settle the books for the market(s) just left (user 08/03):
            # at 16:00 this reconciles the 15:45 market's pnl from fills.
            if current_ticker:
                _recon_pending.append((current_ticker, 0))
            _still: list = []
            for _tk, _tries in _recon_pending:
                try:
                    _done = await _reconcile_prev_market(c, _tk)
                except Exception as _e:                       # noqa: BLE001
                    print(f"  [TRUEPNL] {_tk}: reconcile crashed ({_e})")
                    _done = True          # never let bookkeeping stall trading
                if not _done and _tries + 1 < _RECON_MAX_TRIES:
                    _still.append((_tk, _tries + 1))
            _recon_pending = _still
            ticker        = market["ticker"]
            current_ticker = ticker
            market_opened = _market_opened(market)
            market_close  = market_opened + timedelta(seconds=MARKET_LEN_S)
            btc_to_beat   = _strike_of(market)

            print(f"\n{'═' * 64}\n  MARKET : {ticker}"
                  f"   (up to {MAX_TRADES_PER_MARKET} trade(s))\n{'═' * 64}")

            # ── BANK-TARGET (common bot contract, user 08/03): stop once
            # realized P&L has grown THIS bot's bankroll by the target
            # percent. Checked at market start, where the position is flat —
            # stopping mid-market would strand an open position.
            if v1.BANKROLL.target_reached():
                await _halt_and_shutdown(
                    c, ticker, reason_tag="BANK-TARGET HALT",
                    reason_msg=(f"TP reached on bank: ${v1.BANKROLL.balance:.2f} "
                                f"= +{v1.BTC15_TARGET_PCT:.0f}% on "
                                f"${v1.BANKROLL.start:.2f} — stopping."),
                )
                return
            if v1.BANKROLL.sl_reached():
                await _halt_and_shutdown(
                    c, ticker, reason_tag="BANK-SL HALT",
                    reason_msg=(f"SL HIT on Bank: ${v1.BANKROLL.balance:.2f} "
                                f"<= -{v1.BTC15_BANK_SL_PCT:.0f}% on "
                                f"${v1.BANKROLL.start:.2f} — stopping."),
                )
                return

            # ── Per-market halt: trading-hours (same logic as v1) ────────────
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

            # ══ Inner loop: up to MAX_TRADES_PER_MARKET trades per market ════
            for trade_no in range(1, MAX_TRADES_PER_MARKET + 1):
                # ── NO-TRADE window (user 08/03): stay alive, enter nothing.
                _ntw = v1._in_no_trade_window()
                if _ntw is not None:
                    print(f"  [NO-TRADE] local time inside "
                          f"{_ntw[0]:%H:%M}-{_ntw[1]:%H:%M} - no entries this "
                          f"market; monitoring only")
                    break
                # Time-to-close gate (top): stop trading this market when late.
                _ttc = (market_close - _utc_now()).total_seconds()
                if _ttc <= MIN_TIME_TO_CLOSE_S:
                    print(f"  [TIME-GATE] {_ttc:.0f}s to close ≤ "
                          f"{MIN_TIME_TO_CLOSE_S}s — no more trades this market; "
                          f"waiting for next market.")
                    break

                print(f"\n  ── Trade {trade_no}/{MAX_TRADES_PER_MARKET} on {ticker} "
                      f"({_ttc:.0f}s to close) ──")

                # Portfolio + MIN-PV halt (fresh each trade for accurate sizing).
                pv = await portfolio_balance(c)
                print(f"  Portfolio: ${pv:.2f}")
                if pv < DO_NOT_BUY_IF_PORTFOLIO_BELOW:
                    await _halt_and_shutdown(
                        c, ticker, reason_tag="MIN-PV HALT",
                        reason_msg=(f"Portfolio ${pv:.2f} < "
                                    f"${DO_NOT_BUY_IF_PORTFOLIO_BELOW} — halting."),
                    )
                    return

                # TARGET-PV halt: once today's portfolio hits the daily profit
                # target, stop trading and (if HALT_MACHINE_SHUTDOWN=TRUE) shut
                # down.  Day-start baseline is persisted per CST date so a
                # restart resumes the same target.  0 disables.
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

                # ── STEP 3 → ENTRY → BAND GUARD (BUY_SCORE conviction inside) ─
                # band_guard_v2 now owns the BUY_SCORE conviction gate and
                # waits internally until every gate passes, then returns the
                # latest bid as planning_to_buy.  `_ready` flags a confirmed
                # setup.
                _ready          = False
                direction       = "yes"
                actual_prev     = None
                planning_to_buy = 0
                _buy_contracts  = 0
                last_buy_score  = 0

                # ── STEP 3: best-of-4 direction ──────────────────────────────
                direction, actual_prev = await determine_direction_v2(c, btc, btc_to_beat)

                # ── Entry scan (one pass) ────────────────────────────────────
                # On a "sell" verdict, check BUY_SCORE for the chosen direction.
                # If it's very negative (≤ FLIP_BUY_SCORE), the opposite side is
                # the better bet → flip and override the direction.  Either way
                # we proceed to the band guard with the CORRECT direction.
                _flipped = False
                verdict = await poll_entry_signal_v2(c, ticker, direction, btc=btc)
                if verdict == "sell":
                    _entry_bs = await compute_buy_score(
                        c, ticker, direction, btc=btc, btc_to_beat=btc_to_beat)
                    if _entry_bs <= FLIP_BUY_SCORE:
                        _old = direction
                        direction = flip(direction)
                        _flipped = True
                        print(f"  [ENTRYv2] sell verdict + BUY_SCORE "
                              f"{_entry_bs:+d} ≤ {FLIP_BUY_SCORE} — FLIP "
                              f"{_old.upper()} → {direction.upper()}.")
                    else:
                        print(f"  [ENTRYv2] sell verdict but BUY_SCORE "
                              f"{_entry_bs:+d} > {FLIP_BUY_SCORE} — keep "
                              f"{direction.upper()}.")

                # ── Launch the per-market bid-price logger (once per market) ──
                # Records the CHOSEN direction's bid every 30s for the rest of
                # the 15-min market → bid_price_monitor.log.  Background task,
                # independent of whether this slot actually trades.
                if trade_no == 1:
                    _bt = asyncio.create_task(
                        bid_price_monitor(c, ticker, direction, market_opened))
                    _bid_tasks.add(_bt)
                    _bt.add_done_callback(_bid_tasks.discard)
                    print(f"  [BID-MON] recording {direction.upper()} bid every "
                          f"{BID_MONITOR_INTERVAL_S}s → {BID_MONITOR_LOG}")

                # ── Band guard: price/BTC/signal/BUY_SCORE gates → latest bid ─
                # On a deliberate flip, the BTC gate is bypassed inside.
                ok, planning_to_buy, last_buy_score = await band_guard_v2(
                    c, ticker, direction, btc=btc,
                    btc_to_beat=btc_to_beat, market_opened=market_opened,
                    is_flipped=_flipped,
                )
                if ok:
                    # ── BTC strong-signal block (same gate as v1 STEP 5f) ────
                    if btc.hasRecentStrongAgainst(direction, lookback=20):
                        _opp = "strong_sell" if direction == "yes" else "strong_buy"
                        print(f"  [STRONG-BLOCK] recent {_opp.upper()} — refuse to "
                              f"buy {direction.upper()}. Skip slot.")
                    else:
                        # ── Time-to-close gate (post band-wait) ──────────────
                        _ttc2 = (market_close - _utc_now()).total_seconds()
                        if _ttc2 <= MIN_TIME_TO_CLOSE_S:
                            print(f"  [TIME-GATE] only {_ttc2:.0f}s to close after "
                                  f"band wait (need > {MIN_TIME_TO_CLOSE_S}s) — "
                                  f"no order.")
                        else:
                            # ── Sizing: FIXED contracts (common bot contract,
                            # user 08/03). %-of-PV sizing removed desk-wide:
                            # the contracts the operator typed are the
                            # contracts bought, every engine, every trade.
                            _buy_contracts = max(1, v1.CONTRACTS)
                            print(f"  [SIZE] fixed {_buy_contracts} contracts "
                                  f"(KALSHI_CONTRACTS)  |  "
                                  f"BUY_SCORE={last_buy_score:+d}")
                            _ready = True

                if not _ready:
                    await asyncio.sleep(3)
                    continue   # skip slot → next trade / market

                # ── Place buy @ planning_to_buy, WAIT until filled ───────────
                resp = await place_buy(c, ticker, direction,
                                       buy_at_cents=planning_to_buy,
                                       contracts=_buy_contracts)
                if resp is None:
                    await asyncio.sleep(5)
                    continue
                odata = resp.get("order", {})

                filled = await await_fill(c, ticker, timeout=300)
                if not filled:
                    print("  [FILL] not filled in 180s — cancel + skip slot.")
                    await cancel_all(c)
                    await asyncio.sleep(3)
                    continue

                btc_spot_at_buy = btc.last_price

                # ── avg_cents (same formula as v1), reused everywhere ────────
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

                # ── TP sell + monitor (only after a confirmed fill) ──────────
                # The TP limit sell is placed ONLY when DO_YOU_HAVE_STOP_SELL=
                # TRUE.  The monitor ALWAYS runs once filled — it manages the
                # exit (SELL_SCORE + bid/time rules + proactive-TP) in BOTH
                # modes.  (`filled` is already guaranteed True here; the code
                # above `continue`s on a non-fill.)
                if filled:
                    # Give the fill a moment to register before reading position.
                    await asyncio.sleep(10)
                    pos = await position_for(c, ticker)
                    real_contracts = pos["contracts"] if (pos and pos["contracts"] > 0) else _buy_contracts

                    # Only place the TP sell when a real position exists.
                    _have_position = pos is not None and pos["contracts"] > 0
                    if DO_YOU_HAVE_STOP_SELL and _have_position:
                        await place_tp_sell(c, ticker, direction,
                                            real_contracts, tp_cents)
                    elif not _have_position:
                        print(f"  [TP] No position found after fill — skipping TP "
                              f"sell; monitor_trade_v2 still runs.")
                    else:
                        print(f"  [TP] DO_YOU_HAVE_STOP_SELL=False — no TP sell "
                              f"placed; monitor_trade_v2 manages the exit.")

                    # ── v2 monitor (always runs once filled) ─────────────────
                    await monitor_trade_v2(
                        c, ticker, direction, btc=btc, btc_to_beat=btc_to_beat,
                        entry_total=entry_total, avg_cents=avg_cents,
                        buy_contracts=_buy_contracts, tp_cents=tp_cents, sl_total=sl_total,
                        market_opened=market_opened, btc_spot_at_buy=btc_spot_at_buy,
                        actual_direction_previous=actual_prev,
                    )

                await asyncio.sleep(5)
            # ── end inner trade loop → outer loop fetches next market ────────
    finally:
        # Cancel any in-flight bid-price loggers.
        for _t in list(_bid_tasks):
            _t.cancel()
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
