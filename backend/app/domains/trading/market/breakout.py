"""BreakoutRadar's eight rules, and what a chart needs to show why a stock passed.

A stock qualifies only when all eight hold at once:

  1 consolidation  the N candles before the breakout candle sat in a tight
                   channel: (top - bottom) / bottom <= 12%, where the channel
                   is drawn on candle BODIES (the open/close bounds), not wicks
  2 penetration    the breakout candle closed >= 2% above that channel's top,
                   and the newest close is still above it -- a breakout that
                   has fallen back into its range is not one any more
  3 body           the breakout candle is a green body of >= 5% of its open on
                   4h/1d candles, >= 2.5% on 5m/15m/1h. Green because the rule
                   is about conviction: a candle that gapped far above the range
                   and sold off still closes "above" it, and that is a fade
  4 market cap     > $50M (US) or > Rs 3 crore (India). A cap that could not be
                   looked up is reported as unverified rather than failed: every
                   name in these universes is an index member far above either
  5 RVOL           the breakout candle's volume >= 1.5x the mean of the 20
                   candles before it (the candle itself is not in its own base),
                   with no upper cap
  6 liquidity      20-day average daily volume > 500,000 shares, over the last
                   20 COMPLETED sessions, so a half-traded today cannot drag it
  7 near a high    the price is within 10% of its 20-day, 50-day or all-time
                   high. The three are nested (20d <= 50d <= ATH), so "within 10%
                   of any" is exactly "within 10% of the 20-day high": the ATH
                   can never change the answer, and is not fetched for it
  8 trend          the price is above both its 20 and 50 EMA on the scan's own
                   timeframe (recursive EMAs, as charts draw them)

The breakout candle is the NEWEST of the last `breakout_within` candles (3 by
default: 0 = the latest) on which rules 1, 2, 3 and 5 all hold. With none, the
candle that came closest is reported, so a near miss can say which rule it
missed.

Pure: ``prepare`` turns bars into arrays once per sweep, and ``evaluate``
applies thresholds to them. The drawer's sliders re-run ``evaluate`` against
cached arrays -- nothing is downloaded again because a threshold moved.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace

import numpy as np
import pandas as pd

TIMEFRAMES = ("5m", "15m", "1h", "4h", "1d")
MARKETS = ("US", "INDIA")
LOW_TIMEFRAMES = {"5m", "15m", "1h"}          # rule 3's lower threshold
EMA_FAST, EMA_SLOW = 20, 50
RVOL_PERIOD = 20
ADV_DAYS = 20

RULES = ("consolidation", "penetration", "body", "market_cap", "rvol",
         "liquidity", "near_high", "trend")
RULE_LABELS = {
    "consolidation": "tight consolidation", "penetration": "close above range",
    "body": "candle body", "market_cap": "market cap", "rvol": "relative volume",
    "liquidity": "20-day avg volume", "near_high": "near a high", "trend": "above 20/50 EMA",
}
# Rs 3 crore = 3 x 10^7 rupees; $50M. Each is in its market's own currency,
# which is what Yahoo reports a listing's cap in.
CAP_FLOOR = {"US": 50e6, "INDIA": 3e7}
CURRENCY = {"US": "USD", "INDIA": "INR"}


@dataclass(frozen=True)
class Params:
    consolidation_bars: int = 20        # rule 1: N candles before the breakout
    max_range_pct: float = 12.0         # rule 1
    breakout_pct: float = 2.0           # rule 2
    min_body_pct: float | None = None   # rule 3: None = 5.0 on 4h/1d, 2.5 below
    min_market_cap: float | None = None  # rule 4: None = the market's floor
    min_rvol: float = 1.5               # rule 5
    min_adv: float = 500_000            # rule 6, shares
    near_high_pct: float = 10.0         # rule 7
    breakout_within: int = 3            # how recent the breakout candle must be

    LIMITS = {
        "consolidation_bars": (5, 120), "max_range_pct": (0.5, 100.0),
        "breakout_pct": (0.0, 50.0), "min_body_pct": (0.0, 50.0),
        "min_market_cap": (0.0, 1e14), "min_rvol": (0.0, 50.0),
        "min_adv": (0.0, 1e10), "near_high_pct": (0.0, 100.0),
        "breakout_within": (1, 10),
    }

    def __post_init__(self):
        for name, (lo, hi) in self.LIMITS.items():
            value = getattr(self, name)
            if value is None:
                continue
            if not isinstance(value, (int, float)) or not math.isfinite(value) \
                    or not lo <= value <= hi:
                raise ValueError(f"{name} must be between {lo:g} and {hi:g}")

    def body_threshold(self, timeframe: str) -> float:
        if self.min_body_pct is not None:
            return float(self.min_body_pct)
        return 2.5 if timeframe in LOW_TIMEFRAMES else 5.0

    def cap_threshold(self, market: str) -> float:
        if self.min_market_cap is not None:
            return float(self.min_market_cap)
        return CAP_FLOOR[market]

    def resolved(self, timeframe: str, market: str) -> dict:
        """Every threshold as it will actually be applied."""
        return {**{k: v for k, v in asdict(self).items()},
                "min_body_pct": self.body_threshold(timeframe),
                "min_market_cap": self.cap_threshold(market),
                "currency": CURRENCY[market]}

    def with_overrides(self, **given) -> "Params":
        return replace(self, **{k: v for k, v in given.items() if v is not None})


@dataclass(frozen=True)
class Series:
    """One ticker's candles at the scan timeframe, as arrays, plus the daily
    facts rules 6 and 7 read. Built once per sweep by ``prepare``."""

    ticker: str
    times: tuple[str, ...]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    ema_fast: np.ndarray
    ema_slow: np.ndarray
    vol_base: np.ndarray      # mean volume of the RVOL_PERIOD candles before each
    adv: float | None
    high20: float | None
    high50: float | None
    prev_close: float | None  # the session before the latest one


def _stamp(ts, daily: bool) -> str:
    ts = pd.Timestamp(ts)
    return ts.strftime("%Y-%m-%d") if daily else ts.strftime("%Y-%m-%dT%H:%M")


def prepare(ticker: str, bars: pd.DataFrame, daily: pd.DataFrame | None, *,
            timeframe: str) -> Series | None:
    """Arrays from OHLCV frames (columns open/high/low/close/volume, oldest
    first). None when there is nothing usable to screen."""
    if bars is None or bars.empty:
        return None
    frame = bars[["open", "high", "low", "close", "volume"]].astype(float)
    frame = frame[frame["close"].notna() & (frame["close"] > 0)]
    if frame.empty:
        return None
    frame = frame.assign(volume=frame["volume"].fillna(0.0),
                         open=frame["open"].fillna(frame["close"]))
    close = frame["close"]
    base = frame["volume"].rolling(RVOL_PERIOD, min_periods=RVOL_PERIOD).mean().shift(1)

    adv = high20 = high50 = prev_close = None
    days = daily if daily is not None else (frame if timeframe == "1d" else None)
    if days is not None and not days.empty:
        days = days[days["close"].notna()]
        settled = days.iloc[:-1]                # the latest session may be partial
        if len(settled) >= ADV_DAYS:
            adv = float(settled["volume"].iloc[-ADV_DAYS:].mean())
        if len(days) >= 1:
            high20 = float(days["high"].iloc[-20:].max())
            high50 = float(days["high"].iloc[-50:].max())
        if len(days) >= 2:
            prev_close = float(days["close"].iloc[-2])

    return Series(
        ticker=ticker,
        times=tuple(_stamp(t, timeframe == "1d") for t in frame.index),
        open=frame["open"].to_numpy(), high=frame["high"].to_numpy(),
        low=frame["low"].to_numpy(), close=close.to_numpy(),
        volume=frame["volume"].to_numpy(),
        ema_fast=close.ewm(span=EMA_FAST, adjust=False).mean().to_numpy(),
        ema_slow=close.ewm(span=EMA_SLOW, adjust=False).mean().to_numpy(),
        vol_base=base.to_numpy(),
        adv=adv, high20=high20, high50=high50, prev_close=prev_close)


def min_candles(params: Params) -> int:
    return max(params.consolidation_bars + 1, RVOL_PERIOD + 1, EMA_SLOW)


def _candidate(s: Series, b: int, params: Params, body_min: float) -> dict:
    n_bars = params.consolidation_bars
    bodies_top = np.maximum(s.open[b - n_bars:b], s.close[b - n_bars:b])
    bodies_low = np.minimum(s.open[b - n_bars:b], s.close[b - n_bars:b])
    top, bottom = float(bodies_top.max()), float(bodies_low.min())
    range_pct = 100.0 * (top - bottom) / bottom if bottom > 0 else math.inf
    size_pct = 100.0 * (s.close[b] - top) / top if top > 0 else -math.inf
    body_pct = 100.0 * (s.close[b] - s.open[b]) / s.open[b] if s.open[b] > 0 else -math.inf
    base = s.vol_base[b]
    rvol = float(s.volume[b] / base) if base and np.isfinite(base) and base > 0 else None
    checks = {
        "consolidation": range_pct <= params.max_range_pct,
        "penetration": size_pct >= params.breakout_pct and s.close[-1] > top,
        "body": body_pct >= body_min,
        "rvol": rvol is not None and rvol >= params.min_rvol,
    }
    return {"b": b, "checks": checks, "top": top, "bottom": bottom,
            "range_pct": range_pct, "size_pct": size_pct, "body_pct": body_pct,
            "rvol": rvol}


def _r(value, places: int = 2):
    if value is None:
        return None
    value = float(value)
    return round(value, places) if math.isfinite(value) else None


def evaluate(s: Series, params: Params, *, timeframe: str, market: str,
             market_cap: float | None = None) -> dict:
    """The eight rules for one ticker, each pass/fail, with the numbers behind
    them and the overlay a chart draws."""
    n = len(s.close)
    need = min_candles(params)
    if n < need:
        return {"ticker": s.ticker, "available": False, "passed": False,
                "reason": f"{n} candles; the rules need {need} "
                          f"({EMA_SLOW} EMA, {params.consolidation_bars}-candle range)"}

    body_min = params.body_threshold(timeframe)
    best = None
    for age in range(params.breakout_within):
        b = n - 1 - age
        if b - params.consolidation_bars < 0:
            break
        cand = _candidate(s, b, params, body_min)
        score = sum(cand["checks"].values())
        if score == len(cand["checks"]):
            best = cand
            break
        if best is None or score > sum(best["checks"].values()):
            best = cand

    price = float(s.close[-1])
    highs = [h for h in (s.high20, s.high50) if h]
    pct_from = {name: (100.0 * (price - h) / h if h else None)
                for name, h in (("high20", s.high20), ("high50", s.high50))}
    cap_floor = params.cap_threshold(market)
    rules = {
        **best["checks"],
        "market_cap": None if market_cap is None else market_cap > cap_floor,
        "liquidity": s.adv is not None and s.adv > params.min_adv,
        "near_high": bool(highs) and any(price >= h * (1 - params.near_high_pct / 100)
                                         for h in highs),
        "trend": price > s.ema_fast[-1] and price > s.ema_slow[-1],
    }
    rules = {k: (None if rules[k] is None else bool(rules[k])) for k in RULES}
    failed = [k for k in RULES if rules[k] is False]
    b = best["b"]
    start = b - params.consolidation_bars
    return {
        "ticker": s.ticker,
        "available": True,
        "passed": not failed,
        "rules": rules,
        "failed": failed,
        "price": _r(price, 4 if price < 1 else 2),
        "change_pct": _r(100.0 * (price - s.prev_close) / s.prev_close
                         if s.prev_close else None),
        "breakout_size_pct": _r(best["size_pct"]),
        "rvol": _r(best["rvol"]),
        "range_pct": _r(best["range_pct"]),
        "body_pct": _r(best["body_pct"]),
        "market_cap": _r(market_cap, 0),
        "adv": _r(s.adv, 0),
        "pct_from_high20": _r(pct_from["high20"]),
        "pct_from_high50": _r(pct_from["high50"]),
        "ema20": _r(s.ema_fast[-1], 4 if price < 1 else 2),
        "ema50": _r(s.ema_slow[-1], 4 if price < 1 else 2),
        "consolidation_high": _r(best["top"], 4),
        "consolidation_low": _r(best["bottom"], 4),
        "consolidation_start": s.times[start],
        "consolidation_end": s.times[b - 1],
        "breakout_candle_timestamp": s.times[b],
        "breakout_age": n - 1 - b,
        "as_of": s.times[-1],
    }


def chart(s: Series, params: Params, *, timeframe: str, market: str,
          market_cap: float | None = None, bars: int = 160) -> dict:
    """Candles with both EMAs and the breakout overlay, trimmed to the last
    `bars` candles -- always wide enough to show the consolidation window."""
    verdict = evaluate(s, params, timeframe=timeframe, market=market,
                       market_cap=market_cap)
    n = len(s.close)
    keep = max(bars, params.consolidation_bars + params.breakout_within + 10)
    lo = max(0, n - keep)
    places = 4 if s.close[-1] < 1 else 2
    candles = [{"t": s.times[i], "o": _r(s.open[i], places), "h": _r(s.high[i], places),
                "l": _r(s.low[i], places), "c": _r(s.close[i], places),
                "v": _r(s.volume[i], 0)} for i in range(lo, n)]
    return {
        "ticker": s.ticker, "timeframe": timeframe, "market": market,
        "candles": candles,
        "ema20": [_r(v, places) for v in s.ema_fast[lo:]],
        "ema50": [_r(v, places) for v in s.ema_slow[lo:]],
        "verdict": verdict,
        "consolidation_high": verdict.get("consolidation_high"),
        "consolidation_low": verdict.get("consolidation_low"),
        "consolidation_start": verdict.get("consolidation_start"),
        "consolidation_end": verdict.get("consolidation_end"),
        "breakout_candle_timestamp": verdict.get("breakout_candle_timestamp"),
    }
