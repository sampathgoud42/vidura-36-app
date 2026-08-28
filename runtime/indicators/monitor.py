"""
btc.monitor — BTC spot-price meta-monitor for 15-minute binary trading.

Polls Coinbase BTC-USD spot every 15s into a 120-tick (~30 min) rolling
window.  Exposes a buy/sell/hold meta-signal that both the Kalshi and
Polymarket bots use to confirm or veto trade direction.

This module is the *single source of truth* for BTC directional logic.
Both bots import it identically — fixing logic here fixes both bots.

Signal pipeline (in evaluation order):

  1. CUSUM event filter (primary trigger).
     Maintains positive/negative cumulative log-return residuals against
     a running mean; fires when ``|S±| ≥ k · σ_EWMA`` of recent 15s log
     returns.  This is López de Prado's CUSUM filter from AFML Ch.2 — it
     solves the structural failure of static thresholds in calm BTC
     regimes by sampling events in volatility units, not absolute bps.

  2. 4-indicator confluence vote (legacy momentum stack).
     VIDYA fast/slow gap, ROC, Chande Momentum Oscillator, slope
     acceleration.  Lowered thresholds so the gates actually fire on
     BTC's normal 15s micro-noise — `GAP_THRESHOLD` floor dropped from
     0.0005 → 0.0001 and ``MIN_VOTES`` from 3 → 2.

  3. Final signal = agreement gate.
     * CUSUM + vote both directional & aligned          → strong signal
     * CUSUM directional, vote ambiguous (≤1 either side) → CUSUM signal
     * Vote directional ≥ MIN_VOTES, CUSUM neutral       → vote signal
     * Disagreement                                       → "hold"

Public API:
    monitor = BtcVidyaMonitor()
    monitor.start()
    sig = monitor.latestBtcVidyaSignal()    # most-recent non-hold (warm)
    sig = monitor.btcSignalByVoteDiff()     # never returns "hold"
    sig = monitor.btcSignalWithStrength()   # may return "strong_buy" / "strong_sell"
                                            # when CUSUM + vote agree this tick
    blocked = monitor.hasRecentStrongAgainst("yes")  # True if any recent
                                            # strong_sell within lookback (or
                                            # strong_buy when direction == "no")
    await monitor.stop()
"""
from __future__ import annotations

import asyncio
import math
import os
from collections import deque
from datetime import datetime
from typing import Literal, Optional
from zoneinfo import ZoneInfo

import aiohttp
import numpy as np

SignalT = Literal["buy", "sell", "strong_buy", "strong_sell", "hold"]

# Cold-start fallback — read at import time from the unified .env (or the
# per-platform .env when a subbot is launched standalone).  Valid values:
# "hold" (safest, blocks all BTC-gated trades during warmup), "buy", "sell".
_btc_cold_raw = os.getenv("BTC_COLD_START_DEFAULT", "sell").strip().lower()
BTC_COLD_START_DEFAULT: SignalT = (
    _btc_cold_raw if _btc_cold_raw in ("buy", "sell", "hold") else "hold"
)  # type: ignore[assignment]

_CST = ZoneInfo("America/Chicago")


def _cst_now() -> datetime:
    """Current time in Central (CST/CDT) — used for all log timestamps."""
    return datetime.now(_CST)


class BtcVidyaMonitor:
    """
    BTC spot monitor — CUSUM event filter + 4-indicator confluence.

    Tuning constants (15-min binaries, 15s polls):
      • Window      : 120 ticks (~30 min context)
      • Fast VIDYA  : 6  ticks  (~90 s)
      • Slow VIDYA  : 16 ticks  (~4 min)
      • CMO period  : 7  ticks
      • ROC window  : 8  ticks  (~2 min)
      • GAP floor   : 0.0001 (1 bp) — see commit history; old 0.0005
                       prevented gap from firing in calm BTC regimes
      • MIN_VOTES   : 2 (lowered from 3 — the four indicators are all
                       momentum and not independent; 2-of-4 + CUSUM
                       confirm is the new "high-confidence" bar)
      • CUSUM k     : 1.5 σ_EWMA (AFML default)
      • EWMA λ      : 0.94 (RiskMetrics default, ~20-tick half-life)
    """
    # ── Polling / window ──────────────────────────────────────────────────────
    POLL_INTERVAL_S    = 15
    WINDOW_SIZE        = 120
    COINBASE_URL       = "https://api.coinbase.com/v2/prices/BTC-USD/spot"

    # ── Vote-confluence constants ─────────────────────────────────────────────
    FAST_PERIOD        = 6
    SLOW_PERIOD        = 16
    CMO_PERIOD         = 7
    GAP_THRESHOLD      = 0.0001    # floor for vol-adaptive gap/ROC threshold
    ROC_WINDOW         = 8
    CMO_DECISION_LEVEL = 0.15
    MIN_VOTES          = 2

    # ── CUSUM event-filter constants ──────────────────────────────────────────
    CUSUM_K            = 1.5       # threshold in σ_EWMA units
    EWMA_LAMBDA        = 0.94      # RiskMetrics decay for realized-vol EWMA

    # ── Hourly-trend constants (btcSignalHourly) ──────────────────────────────
    HOURLY_SIZE        = 240       # 240 × 15s ≈ 1 hour of spot ticks
    HOURLY_THRESHOLD   = 0.0005    # 5 bp net change to call a clear direction

    def __init__(self) -> None:
        self.buf:               deque[float]      = deque(maxlen=self.WINDOW_SIZE)
        # Rolling ~1-hour spot buffer for btcSignalHourly().  Independent of
        # self.buf so the long-horizon trend isn't truncated by the 30-min
        # signal window.
        self.hourly_buf:        deque[float]      = deque(maxlen=self.HOURLY_SIZE)
        self.signal:            SignalT           = "hold"
        self.signal_history:    deque[str]        = deque(maxlen=self.WINDOW_SIZE)
        # Parallel history that records "strong_buy" / "strong_sell" on ticks
        # where CUSUM and the vote agree on the same non-hold direction,
        # otherwise mirrors signal_history.  Consumed only by
        # btcSignalWithStrength(); the existing methods keep using the
        # un-promoted signal_history so their return types are unchanged.
        self.strength_history:  deque[str]        = deque(maxlen=self.WINDOW_SIZE)
        self.last_strength:     SignalT           = "hold"
        self.last_price:        float | None      = None
        self.last_fast:         float | None      = None
        self.last_slow:         float | None      = None
        self.last_votes:        tuple[int, int]   = (0, 0)   # (buy, sell)
        self.last_cusum:        SignalT           = "hold"
        self._cusum_pos:        float             = 0.0
        self._cusum_neg:        float             = 0.0
        self._ewma_var:         float             = 0.0
        self._last_vote_diff_signal: SignalT      = "hold"
        self._task:             Optional[asyncio.Task] = None
        self._stop_event        = asyncio.Event()

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  Public signal queries used by the bots                              ║
    # ╚══════════════════════════════════════════════════════════════════════╝
    def btcSignalHourly(self) -> SignalT:
        """
        Long-horizon (~1 hour) directional bias.  NEVER returns "hold" — the
        v2 bot uses this as a tie-breaking vote (V4) in direction selection,
        so it must always commit to "buy" (→ YES) or "sell" (→ NO).

        Logic: net % change across the rolling hourly buffer (oldest vs
        newest).  |net| > HOURLY_THRESHOLD → that direction; inside the band
        → fall back to the raw sign of net; perfectly flat / no data →
        BTC_COLD_START_DEFAULT coerced away from "hold" (defaults to "buy").
        """
        prices = list(self.hourly_buf)
        if len(prices) < 2:
            base = BTC_COLD_START_DEFAULT
            return "buy" if base == "hold" else base  # type: ignore[return-value]
        first, last = prices[0], prices[-1]
        if first <= 0:
            return "buy"
        net = (last - first) / first
        if net > self.HOURLY_THRESHOLD:
            return "buy"
        if net < -self.HOURLY_THRESHOLD:
            return "sell"
        # Inside the dead band — use the raw sign so we never abstain.
        if net > 0:
            return "buy"
        if net < 0:
            return "sell"
        base = BTC_COLD_START_DEFAULT
        return "buy" if base == "hold" else base  # type: ignore[return-value]

    def latestBtcVidyaSignal(self, lookback: int = 20) -> SignalT:
        """
        Latest non-hold signal once ≥5 non-holds have accumulated;
        BTC_COLD_START_DEFAULT during warmup.
        """
        MIN_NON_HOLD = 5
        history = list(self.signal_history)
        if not history:
            return BTC_COLD_START_DEFAULT

        recent   = history[-lookback:] if lookback < len(history) else history
        non_hold = [s for s in recent if s != "hold"]
        if len(non_hold) < MIN_NON_HOLD and lookback < len(history):
            non_hold = [s for s in history if s != "hold"]
        if len(non_hold) >= MIN_NON_HOLD:
            return non_hold[-1]   # type: ignore[return-value]
        return BTC_COLD_START_DEFAULT

    def btcSignalWithStrength(self, lookback: int = 20) -> SignalT:
        """
        Latest signal *with* strength promotion.

        Returns one of:
            "strong_buy"  — most recent tick (within lookback) where CUSUM
                            and the 4-vote both fired "buy" on the same tick
            "strong_sell" — same, both fired "sell" on the same tick
            "buy" / "sell" — weaker (vote-only or CUSUM-only) directional
                             signal from the most recent non-hold tick
            "hold"         — only returned during warmup as
                             BTC_COLD_START_DEFAULT; once warm this method
                             always returns one of the four directional
                             variants above

        Implementation: walks ``strength_history`` (parallel to
        ``signal_history``) which records the promoted signal each tick.
        Mirrors ``latestBtcVidyaSignal()``'s warmup behavior: requires
        ``MIN_NON_HOLD = 5`` non-hold entries before returning a real
        signal, otherwise returns BTC_COLD_START_DEFAULT.
        """
        MIN_NON_HOLD = 5
        history = list(self.strength_history)
        if not history:
            return BTC_COLD_START_DEFAULT

        recent   = history[-lookback:] if lookback < len(history) else history
        non_hold = [s for s in recent if s != "hold"]
        if len(non_hold) < MIN_NON_HOLD and lookback < len(history):
            non_hold = [s for s in history if s != "hold"]
        if len(non_hold) >= MIN_NON_HOLD:
            return non_hold[-1]   # type: ignore[return-value]
        return BTC_COLD_START_DEFAULT

    def hasRecentStrongAgainst(self, direction: str, lookback: int = 20) -> bool:
        """
        Return True if any of the most-recent ``lookback`` entries in
        ``strength_history`` is a STRONG signal opposing ``direction``.

        Polarity (Kalshi YES/NO contracts):
            direction == "yes" → opposing strong signal = "strong_sell"
                                 (BTC strongly falling — bad to buy YES)
            direction == "no"  → opposing strong signal = "strong_buy"
                                 (BTC strongly rising  — bad to buy NO)

        Returns False if direction is neither "yes" nor "no", or if the
        strength_history buffer is empty (cold start / startup).
        """
        if direction == "yes":
            opposing = "strong_sell"
        elif direction == "no":
            opposing = "strong_buy"
        else:
            return False

        history = list(self.strength_history)
        if not history:
            return False
        recent = history[-lookback:] if lookback < len(history) else history
        return opposing in recent

    def btcSignalByVoteDiff(self, min_diff: int = 2) -> SignalT:
        """
        Vote-margin signal that never returns 'hold' — falls back to the
        most recent non-hold direction when margin < min_diff.  Returns
        BTC_COLD_START_DEFAULT during warmup (< 5 non-hold signals).
        """
        non_hold = [s for s in self.signal_history if s != "hold"]
        if len(non_hold) < 5:
            return BTC_COLD_START_DEFAULT

        buy_v, sell_v = self.last_votes
        if buy_v - sell_v >= min_diff:
            new_sig: SignalT = "buy"
        elif sell_v - buy_v >= min_diff:
            new_sig = "sell"
        else:
            new_sig = non_hold[-1]   # type: ignore[assignment]

        if new_sig != self._last_vote_diff_signal:
            ts = _cst_now().strftime("%H:%M:%S")
            print(f"  [BTC-DIFF {ts}] votes B/S={buy_v}/{sell_v}  "
                  f"{self._last_vote_diff_signal.upper()} → {new_sig.upper()}")
            self._last_vote_diff_signal = new_sig
        return new_sig

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  Internal — fetch + signal computation                               ║
    # ╚══════════════════════════════════════════════════════════════════════╝
    async def _fetch(self, session: aiohttp.ClientSession) -> float | None:
        try:
            async with session.get(
                self.COINBASE_URL,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as r:
                d = await r.json()
                return float(d["data"]["amount"])
        except Exception as e:
            print(f"  [BTC] fetch error: {e}")
            return None

    @staticmethod
    def _vidya(prices: np.ndarray, ema_period: int, cmo_period: int) -> float:
        """Variable Index Dynamic Average (Tushar Chande)."""
        n = len(prices)
        if n < max(ema_period, cmo_period) + 1:
            return float(prices[-1])
        alpha = 2.0 / (ema_period + 1)
        v     = float(prices[0])
        for i in range(1, n):
            start  = max(0, i - cmo_period)
            window = prices[start: i + 1]
            if len(window) < 2:
                cmo_abs = 0.0
            else:
                d  = np.diff(window)
                up = float(np.sum(np.where(d > 0,  d,  0)))
                dn = float(np.sum(np.where(d < 0, -d,  0)))
                cmo_abs = abs((up - dn) / (up + dn)) if (up + dn) > 0 else 0.0
            v = alpha * cmo_abs * float(prices[i]) + (1 - alpha * cmo_abs) * v
        return v

    def _update_cusum(self, log_ret: float) -> SignalT:
        """
        Symmetric CUSUM event filter (AFML Ch.2):

            S⁺_t = max(0, S⁺_{t-1} + r_t)
            S⁻_t = min(0, S⁻_{t-1} + r_t)

        Reset on threshold crossing.  EWMA realized-vol (RiskMetrics
        λ=0.94) sets the threshold ``h = CUSUM_K · σ_EWMA``.  Until vol
        has warmed up (<10 ticks), use a hard 5 bp threshold.
        """
        # EWMA variance update on squared log-return
        self._ewma_var = self.EWMA_LAMBDA * self._ewma_var + (1 - self.EWMA_LAMBDA) * (log_ret * log_ret)
        sigma = math.sqrt(self._ewma_var)
        h = max(self.CUSUM_K * sigma, 0.00005)   # 0.5 bp absolute floor

        self._cusum_pos = max(0.0, self._cusum_pos + log_ret)
        self._cusum_neg = min(0.0, self._cusum_neg + log_ret)

        if self._cusum_pos >= h:
            self._cusum_pos = 0.0     # reset on fire
            return "buy"
        if -self._cusum_neg >= h:
            self._cusum_neg = 0.0
            return "sell"
        return "hold"

    def _compute_signal(self) -> SignalT:
        """
        Combines CUSUM event filter (primary) with 4-indicator confluence vote.

        Returns:
            "buy"  / "sell"  — confluent or CUSUM-only directional event
            "hold"          — neutral or conflicting evidence
        """
        if len(self.buf) < self.SLOW_PERIOD + 2:
            return "hold"

        prices = np.array(self.buf, dtype=np.float64)
        n      = len(prices)

        # ── CUSUM trigger on the latest log return ────────────────────────────
        if len(self.buf) >= 2 and prices[-2] > 0:
            log_ret = math.log(prices[-1] / prices[-2])
            cusum_sig: SignalT = self._update_cusum(log_ret)
        else:
            cusum_sig = "hold"
        self.last_cusum = cusum_sig

        # ── I1: VIDYA fast/slow gap ───────────────────────────────────────────
        fast = self._vidya(prices, self.FAST_PERIOD, self.CMO_PERIOD)
        slow = self._vidya(prices, self.SLOW_PERIOD, self.CMO_PERIOD)
        self.last_fast = fast
        self.last_slow = slow
        if slow == 0:
            return "hold"
        gap = (fast - slow) / slow

        # Adaptive threshold — floor lowered to 1 bp.
        vol_window = min(20, n - 1)
        returns    = np.diff(prices[-vol_window - 1:]) / prices[-vol_window - 1: -1]
        vol        = float(np.std(returns)) if len(returns) >= 3 else 0.0001
        adaptive   = max(self.GAP_THRESHOLD, vol * 0.5)

        # ── I2: Rate of Change ────────────────────────────────────────────────
        roc_w = min(self.ROC_WINDOW, n - 1)
        roc   = (prices[-1] - prices[-roc_w - 1]) / prices[-roc_w - 1]

        # ── I3: Chande Momentum Oscillator ────────────────────────────────────
        cmo_w  = min(self.CMO_PERIOD * 2, n - 1)
        diffs  = np.diff(prices[-cmo_w - 1:])
        up_sum = float(np.sum(np.where(diffs > 0,  diffs, 0)))
        dn_sum = float(np.sum(np.where(diffs < 0, -diffs, 0)))
        cmo    = ((up_sum - dn_sum) / (up_sum + dn_sum)) if (up_sum + dn_sum) > 0 else 0.0

        # ── I4: Slope acceleration ────────────────────────────────────────────
        mid = n // 2
        if mid >= 3 and n - mid >= 3:
            slope_1h = float(np.polyfit(np.arange(mid),     prices[:mid], 1)[0])
            slope_2h = float(np.polyfit(np.arange(n - mid), prices[mid:], 1)[0])
            accel = slope_2h - slope_1h
        else:
            accel = 0.0

        buy_votes = sell_votes = 0
        if gap >  adaptive: buy_votes  += 1
        if gap < -adaptive: sell_votes += 1
        if roc >  adaptive: buy_votes  += 1
        if roc < -adaptive: sell_votes += 1
        if cmo >  self.CMO_DECISION_LEVEL: buy_votes  += 1
        if cmo < -self.CMO_DECISION_LEVEL: sell_votes += 1
        if accel > 0 and gap > 0: buy_votes  += 1
        if accel < 0 and gap < 0: sell_votes += 1

        self.last_votes = (buy_votes, sell_votes)

        # ── Combined decision ─────────────────────────────────────────────────
        vote_buy  = buy_votes  > self.MIN_VOTES and buy_votes  > sell_votes
        vote_sell = sell_votes > self.MIN_VOTES and sell_votes > buy_votes
        vote_sig: SignalT = "buy" if vote_buy else ("sell" if vote_sell else "hold")
        # ── Strength promotion (consumed by btcSignalWithStrength) ───────────
        # When CUSUM and the vote both fire on the same non-hold direction
        # this tick, record the promoted variant.  Otherwise mirror whatever
        # the regular agreement gate below will return (computed inline).
        if cusum_sig == vote_sig == "buy":
            print("[STRONG BUY] from BTC")
            self.last_strength = "strong_buy"
        elif cusum_sig == vote_sig == "sell":
            print("[STRONG SELL] from BTC")
            self.last_strength = "strong_sell"
        elif cusum_sig != "hold" and vote_sig != "hold":
            # Directional disagreement → hold (same as regular signal).
            self.last_strength = "hold"
        else:
            # Vote-only / CUSUM-only / both hold → mirror vote_sig.
            self.last_strength = vote_sig

        # Agreement gate:
        #   - CUSUM and vote both fire same way                → that direction
        #   - CUSUM fires, vote neutral or weak (no MIN_VOTES) → CUSUM direction
        #   - Vote fires, CUSUM neutral                        → vote direction
        #   - Disagreement                                     → hold
        if cusum_sig != "hold" and vote_sig != "hold":
            return cusum_sig if cusum_sig == vote_sig else "hold"
        #if cusum_sig != "hold":
        #    return cusum_sig
        else:
            return vote_sig

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  Background poll loop                                                ║
    # ╚══════════════════════════════════════════════════════════════════════╝
    async def _run_loop(self) -> None:
        async with aiohttp.ClientSession() as sess:
            while not self._stop_event.is_set():
                price = await self._fetch(sess)
                if price is not None:
                    self.buf.append(price)
                    self.hourly_buf.append(price)
                    self.last_price = price
                    self.signal = self._compute_signal()
                    self.signal_history.append(self.signal)
                    # last_strength is set as a side-effect of _compute_signal()
                    self.strength_history.append(self.last_strength)
                    # Only print actionable signals — skip HOLD lines so the
                    # log shows just BUY / SELL / STRONG_BUY / STRONG_SELL.
                    if self.signal != "hold" or self.last_strength != "hold":
                        ts     = _cst_now().strftime("%H:%M:%S")
                        fast_s = f"${self.last_fast:,.2f}" if self.last_fast else "N/A"
                        slow_s = f"${self.last_slow:,.2f}" if self.last_slow else "N/A"
                        print(f"  [BTC {ts}] spot=${price:,.2f}  "
                              f"fast={fast_s}  slow={slow_s}  "
                              f"votes B/S={self.last_votes[0]}/{self.last_votes[1]}  "
                              f"CUSUM={self.last_cusum.upper()}  "
                              f"buf={len(self.buf)}/{self.WINDOW_SIZE}  "
                              f"→ {self.signal.upper()}")
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.POLL_INTERVAL_S,
                    )
                except asyncio.TimeoutError:
                    pass

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run_loop())
            print(f"[BTC] Monitor started — polling Coinbase every {self.POLL_INTERVAL_S}s "
                  f"(CUSUM k={self.CUSUM_K}, MIN_VOTES>{self.MIN_VOTES})")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except asyncio.TimeoutError:
                self._task.cancel()
        print("[BTC] Monitor stopped")
