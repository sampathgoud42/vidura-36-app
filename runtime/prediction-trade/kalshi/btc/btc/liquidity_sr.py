#!/usr/bin/env python3
"""
liquidity_sr.py — Python port of the Pine v6 indicator

    "24 HOURS / 5 MIN — Liquidity Support & Resistance (EMA 6-17)"

Same logic as the TradingView script, driven by Coinbase candles fetched with
``cb_btc_signal.fetch_candles_async``.  The Pine script's drawing/table code is
purely cosmetic and is *not* ported — what you get back instead are the values
those visuals were built from:

    1) POC LEVEL              -> result["poc"]  = {"price", "color", "weight"}
                                 color is "Green" (below price / support),
                                 "Red" (above price / resistance) or
                                 "Blue" (pivot, at price), matching the Pine
                                 line colors.
    2) S/R levels incl. POC   -> result["levels"]      (each tagged S1/R1/… and
                                 is_poc), plus flat helper lists
                                 result["supports"] / result["resistances"].
    3) biasTxt                -> result["bias_txt"]   (LONG-BIAS / SHORT-BIAS /
                                 AT LEVEL — … / NEUTRAL — no edge)
    4) sigDir/sigStop/sigTgt/sigTxt
                              -> result["sig_dir"], result["sig_stop"],
                                 result["sig_tgt"], result["sig_txt"]
    5) alertconditions        -> result["fire_long"], result["fire_short"],
                                 result["fire_win"], result["fire_loss"]
                                 (+ result["entry_label"] = the on-chart
                                 "@price  SL  TP  RR" text when an entry fires)

REPAINT NOTE (carried over from the Pine header): levels recompute from the
rolling window, so they MOVE as new bars arrive.  Only the CURRENT (last closed)
bar's trigger is actionable.  This is a rule executor, not a backtest.

The mechanical engine keeps ONE position at a time.  ``LiquiditySR`` is stateful
(``pos``/entry/stop/target persist across calls) so that ``fire_win`` /
``fire_loss`` can fire on a later bar than the entry — exactly like the Pine
``var`` state.  Call ``evaluate(df)`` once per freshly-closed bar, or use the
async :func:`run` helper which fetches + trims the live candle for you.

Usage (live, stateful):
    eng = LiquiditySR()
    res = asyncio.run(run(engine=eng))      # call again each 5-min bar close

Usage (one-shot snapshot, flat position):
    res = asyncio.run(run())                # fresh engine, pos starts flat
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

import aiohttp

try:                                    # standalone run from btc/
    from cb_btc_signal import (          # type: ignore[import-not-found]
        PRODUCT_ID,
        _GRAN_SECONDS,
        _parse_granularity,
        fetch_candles_async,
    )
except ImportError:                      # imported as part of the `btc` package
    from btc.cb_btc_signal import (      # type: ignore[no-redef]
        PRODUCT_ID,
        _GRAN_SECONDS,
        _parse_granularity,
        fetch_candles_async,
    )

# ───────────────────────── INPUTS (mirror Pine defaults) ──────────────────────
# Window & Cadence
LOOKBACK_HOURS = 8.0      # i_lookbackHours
RECALC_MINS    = 30       # i_recalcMins  (levels only recompute this often)
GRANULARITY    = "5m"     # chart timeframe

# Detection
BINS         = 80         # i_bins
NUM_LEVELS   = 6          # i_numLevels
MIN_GAP_PCT  = 0.12       # i_minGapPct
USE_VOL      = True       # i_useVol (else touch count)

# Scalp Bias
SHOW_EXTREMES = True      # i_showExtremes (24H/window high-low used as targets)
TARGET_VAL    = 1.0       # i_targetVal  (min room to opposite level, in unit)
PROX_PCT      = 0.08      # i_proxPct    (near-level threshold, %)
EMA_FAST      = 6         # i_emaFast
EMA_SLOW      = 17        # i_emaSlow

# Mechanical Entry / Stop Rules
ENABLE_TRIG  = True       # i_enableTrig
UNIT         = "ATR"      # i_unit  ("ATR" | "Percent" | "Points")
ATR_LEN      = 14         # i_atrLen
STOP_BUF_VAL = 0.5        # i_stopBufVal (beyond level, in unit)
MIN_RR       = 1.5        # i_minRR
REQ_MOM      = True       # i_reqMom (require momentum agreement)


# ────────────────────────────── MATH HELPERS ─────────────────────────────────
def _fmt(p: float) -> str:
    """str.tostring(x, format.mintick) for BTC-USD (0.01 tick) → 2 decimals."""
    return f"{p:.2f}"


def _ema_last(values, period: int) -> float:
    """ta.ema(source, period) — recursive EMA seeded with the first value."""
    alpha = 2.0 / (period + 1.0)
    e = values[0]
    for v in values[1:]:
        e = alpha * v + (1.0 - alpha) * e
    return e


def _atr_last(highs, lows, closes, period: int) -> float:
    """ta.atr(period) — Wilder's RMA of True Range (seeded with the SMA)."""
    n = len(closes)
    if n < 2:
        return 0.0
    trs = []
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    if len(trs) < period:
        return sum(trs) / len(trs) if trs else (highs[-1] - lows[-1])
    atr = sum(trs[:period]) / period                # Wilder seed = SMA
    for tr in trs[period:]:
        atr = (atr * (period - 1) + tr) / period
    return atr


def _compute_levels(highs, lows, vols, close, *, bins, num_levels,
                    min_gap_pct, use_vol):
    """
    Volume/touch-weighted price histogram → top ``num_levels`` price nodes with
    a minimum gap between them (Pine sections 1-3).  Returns:

        (picked, poc, win_hi, win_lo)

    ``picked`` is a list of ``(price, weight)`` ordered strongest-first.
    ``poc`` is the strongest ``(price, weight)`` or None.
    """
    win_hi = max(highs)
    win_lo = min(lows)
    rng = win_hi - win_lo
    if rng <= 0:
        return [], None, win_hi, win_lo

    bin_size = rng / bins
    counts = [0.0] * bins
    n = len(highs)

    # --- 2) histogram ---
    for i in range(n):
        if use_vol:
            v = vols[i]
            w = v if (v == v and v) else 1.0       # v==v guards NaN; 0 → 1.0
        else:
            w = 1.0
        low_b = max(0, min(bins - 1, int((lows[i] - win_lo) / bin_size)))
        high_b = max(0, min(bins - 1, int((highs[i] - win_lo) / bin_size)))
        span = high_b - low_b + 1
        per = w / span
        for b in range(low_b, high_b + 1):
            counts[b] += per

    # --- 3) pick top bins with minimum separation ---
    order = sorted(range(bins), key=lambda b: counts[b], reverse=True)
    min_gap = close * min_gap_pct / 100.0
    picked: list[tuple[float, float]] = []
    k = 0
    while len(picked) < num_levels and k < len(order):
        bi = order[k]
        price = win_lo + (bi + 0.5) * bin_size
        ok = counts[bi] > 0
        if ok and picked:
            for pp, _w in picked:
                if abs(price - pp) < min_gap:
                    ok = False
                    break
        if ok:
            picked.append((price, counts[bi]))
        k += 1

    # POC = strongest node among the picked levels (first max, like the Pine loop)
    poc = None
    best = -1.0
    for pp, ww in picked:
        if ww > best:
            best = ww
            poc = (pp, ww)

    return picked, poc, win_hi, win_lo


# ────────────────────────────── ENGINE ───────────────────────────────────────
class LiquiditySR:
    """
    Stateful port of the indicator + mechanical entry/stop/target engine.

    Construct once, then call :meth:`evaluate` with a DataFrame of CLOSED
    candles (oldest→newest, columns open/high/low/close/volume, optional
    ``start``).  State persisted across calls:

        pos / e_price / e_stop / e_target   — open position (one at a time)
        cached levels / win hi-lo           — only recomputed every RECALC_MINS

    Returns a result dict (see module docstring) on every call.
    """

    def __init__(
        self,
        *,
        lookback_hours: float = LOOKBACK_HOURS,
        recalc_mins: int = RECALC_MINS,
        granularity: str = GRANULARITY,
        bins: int = BINS,
        num_levels: int = NUM_LEVELS,
        min_gap_pct: float = MIN_GAP_PCT,
        use_vol: bool = USE_VOL,
        show_extremes: bool = SHOW_EXTREMES,
        target_val: float = TARGET_VAL,
        prox_pct: float = PROX_PCT,
        ema_fast: int = EMA_FAST,
        ema_slow: int = EMA_SLOW,
        enable_trig: bool = ENABLE_TRIG,
        unit: str = UNIT,
        atr_len: int = ATR_LEN,
        stop_buf_val: float = STOP_BUF_VAL,
        min_rr: float = MIN_RR,
        req_mom: bool = REQ_MOM,
    ):
        self.lookback_hours = lookback_hours
        self.recalc_mins = recalc_mins
        self.granularity = granularity
        self.bins = bins
        self.num_levels = num_levels
        self.min_gap_pct = min_gap_pct
        self.use_vol = use_vol
        self.show_extremes = show_extremes
        self.target_val = target_val
        self.prox_pct = prox_pct
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.enable_trig = enable_trig
        self.unit = unit
        self.atr_len = atr_len
        self.stop_buf_val = stop_buf_val
        self.min_rr = min_rr
        self.req_mom = req_mom

        gran_enum = _parse_granularity(granularity)
        self.gran_s = _GRAN_SECONDS[gran_enum]
        tf_mins = self.gran_s / 60.0
        self.bars_in_window = max(1, int(lookback_hours * 60.0 / tf_mins))

        # ---- persistent position state (Pine `var`) ----
        self.pos: int = 0
        self.e_price: Optional[float] = None
        self.e_stop: Optional[float] = None
        self.e_target: Optional[float] = None

        # ---- cached levels (recalc cadence) ----
        self._levels: list[tuple[float, float]] = []
        self._poc: Optional[tuple[float, float]] = None
        self._win_hi: Optional[float] = None
        self._win_lo: Optional[float] = None
        self._last_calc_time: Optional[float] = None
        self._last_bar_time: Optional[float] = None

    # --- unit conversion (toAbs) ---
    def _to_abs(self, v: float, close: float, atr: float) -> float:
        if self.unit == "ATR":
            return v * atr
        if self.unit == "Percent":
            return close * v / 100.0
        return v                                    # Points

    def evaluate(self, df) -> dict:
        """Run the full indicator + engine for the last (confirmed) bar in ``df``."""
        need = max(self.ema_slow + 1, self.atr_len + 1, 2)
        if df is None or df.empty or len(df) < need:
            return self._empty_result()

        highs = df["high"].tolist()
        lows = df["low"].tolist()
        closes = df["close"].tolist()
        vols = df["volume"].tolist() if "volume" in df.columns else [0.0] * len(df)

        close = closes[-1]
        close1 = closes[-2]
        high = highs[-1]
        low = lows[-1]

        # bar identity (so repeated polls within one bar don't re-fire)
        if "start" in df.columns:
            cur_t = float(df["start"].iloc[-1])
        else:
            cur_t = float(len(df))
        new_bar = self._last_bar_time is None or cur_t != self._last_bar_time

        # ---- recalc levels (Pine doRecalc: on last bar, every recalc_mins) ----
        recalc_due = (
            self._last_calc_time is None
            or (cur_t - self._last_calc_time) >= self.recalc_mins * 60
        )
        if new_bar and recalc_due:
            w_h = highs[-self.bars_in_window:]
            w_l = lows[-self.bars_in_window:]
            w_v = vols[-self.bars_in_window:]
            picked, poc, win_hi, win_lo = _compute_levels(
                w_h, w_l, w_v, close,
                bins=self.bins, num_levels=self.num_levels,
                min_gap_pct=self.min_gap_pct, use_vol=self.use_vol,
            )
            self._levels = picked
            self._poc = poc
            self._win_hi = win_hi
            self._win_lo = win_lo
            self._last_calc_time = cur_t
        elif self._last_calc_time is None:
            # first call but somehow gated — compute anyway
            picked, poc, win_hi, win_lo = _compute_levels(
                highs[-self.bars_in_window:], lows[-self.bars_in_window:],
                vols[-self.bars_in_window:], close,
                bins=self.bins, num_levels=self.num_levels,
                min_gap_pct=self.min_gap_pct, use_vol=self.use_vol,
            )
            self._levels, self._poc = picked, poc
            self._win_hi, self._win_lo = win_hi, win_lo
            self._last_calc_time = cur_t

        levels = [p for p, _ in self._levels]
        win_hi = self._win_hi
        win_lo = self._win_lo

        # ---- momentum (every bar) ----
        ema_fast = _ema_last(closes, self.ema_fast)
        ema_slow = _ema_last(closes, self.ema_slow)
        mom_up = ema_fast > ema_slow and close > ema_fast
        mom_dn = ema_fast < ema_slow and close < ema_fast
        momentum = "UP" if mom_up else "DOWN" if mom_dn else "FLAT"

        atr = _atr_last(highs, lows, closes, self.atr_len)

        # ---- nearest support / resistance over stored levels ----
        sup_below = [lv for lv in levels if lv <= close]
        res_above = [lv for lv in levels if lv > close]
        n_sup = max(sup_below) if sup_below else None
        n_res = min(res_above) if res_above else None
        n_sup2 = max([lv for lv in levels if n_sup is not None and lv < n_sup],
                     default=None)
        n_res2 = min([lv for lv in levels if n_res is not None and lv > n_res],
                     default=None)

        dist_sup = (close - n_sup) if n_sup is not None else None
        dist_res = (n_res - close) if n_res is not None else None
        prox_abs = close * self.prox_pct / 100.0
        room_min = self._to_abs(self.target_val, close, atr)

        near_sup = dist_sup is not None and dist_sup <= prox_abs
        near_res = dist_res is not None and dist_res <= prox_abs
        room_long = dist_res is None or dist_res >= room_min
        room_short = dist_sup is None or dist_sup >= room_min

        long_bias = near_sup and mom_up and room_long
        short_bias = near_res and mom_dn and room_short
        at_level_no_edge = (near_sup or near_res) and not long_bias and not short_bias

        if long_bias:
            bias_txt = "LONG-BIAS (at support, mom up)"
        elif short_bias:
            bias_txt = "SHORT-BIAS (at resist, mom dn)"
        elif at_level_no_edge:
            bias_txt = "AT LEVEL — no momentum / tight room"
        else:
            bias_txt = "NEUTRAL — no edge"

        # ---- mechanical signal (sigDir / sigStop / sigTgt / sigTxt) ----
        buf = self._to_abs(self.stop_buf_val, close, atr)

        long_hold = (n_sup is not None and low <= n_sup and close > n_sup
                     and (not self.req_mom or mom_up))
        long_break = (n_res is not None and close > n_res and close1 <= n_res
                      and (not self.req_mom or mom_up))
        short_break = (n_sup is not None and close < n_sup and close1 >= n_sup
                       and (not self.req_mom or mom_dn))
        short_rej = (n_res is not None and high >= n_res and close < n_res
                     and (not self.req_mom or mom_dn))

        sig_dir = 0
        sig_stop: Optional[float] = None
        sig_tgt: Optional[float] = None
        sig_txt = ""
        if long_hold:
            sig_dir = 1
            sig_stop = n_sup - buf
            sig_tgt = win_hi if n_res is None else n_res
            sig_txt = "LONG (support hold)"
        elif short_rej:
            sig_dir = -1
            sig_stop = n_res + buf
            sig_tgt = win_lo if n_sup is None else n_sup
            sig_txt = "SHORT (resist reject)"
        elif long_break:
            sig_dir = 1
            sig_stop = n_res - buf
            sig_tgt = win_hi if n_res2 is None else n_res2
            sig_txt = "LONG (breakout)"
        elif short_break:
            sig_dir = -1
            sig_stop = n_sup + buf
            sig_tgt = win_lo if n_sup2 is None else n_sup2
            sig_txt = "SHORT (breakdown)"

        # ---- entries / exits (one position at a time; only on a NEW bar) ----
        fire_long = fire_short = fire_win = fire_loss = False
        entry_label: Optional[str] = None

        if new_bar:
            # ENTRY
            if (self.enable_trig and self.pos == 0 and sig_dir != 0
                    and sig_tgt is not None and sig_stop is not None):
                risk = abs(close - sig_stop)
                rew = abs(sig_tgt - close)
                if risk > 0 and rew / risk >= self.min_rr:
                    self.pos = sig_dir
                    self.e_price = close
                    self.e_stop = sig_stop
                    self.e_target = sig_tgt
                    fire_long = sig_dir == 1
                    fire_short = sig_dir == -1
                    entry_label = (
                        f"{sig_txt}\n@ {_fmt(self.e_price)}"
                        f"  SL {_fmt(self.e_stop)}"
                        f"  TP {_fmt(self.e_target)}"
                        f"  RR {rew / risk:.1f}"
                    )

            # EXIT (stop checked before target on the same bar = conservative)
            if self.pos != 0:
                if self.pos == 1:
                    hit_stop = low <= self.e_stop
                    hit_tgt = high >= self.e_target
                else:
                    hit_stop = high >= self.e_stop
                    hit_tgt = low <= self.e_target
                if hit_stop or hit_tgt:
                    win = not hit_stop
                    fire_win = win
                    fire_loss = not win
                    self.pos = 0
                    self.e_price = self.e_stop = self.e_target = None

            self._last_bar_time = cur_t

        # ---- build S/R output (incl. POC tag) ----
        poc_price = self._poc[0] if self._poc else None
        poc_weight = self._poc[1] if self._poc else None
        if poc_price is None:
            poc_color = None
        elif poc_price > close:
            poc_color = "Red"
        elif poc_price < close:
            poc_color = "Green"
        else:
            poc_color = "Blue"

        def _is_poc(lv: float) -> bool:
            return poc_price is not None and abs(lv - poc_price) < 1e-9

        supports = sorted([lv for lv in levels if lv < close], reverse=True)
        resistances = sorted([lv for lv in levels if lv > close])
        pivots = [lv for lv in levels if lv == close]

        levels_out = []
        for i, lv in enumerate(supports, start=1):
            levels_out.append({"label": f"S{i}", "price": round(lv, 2),
                               "type": "support", "is_poc": _is_poc(lv)})
        for i, lv in enumerate(resistances, start=1):
            levels_out.append({"label": f"R{i}", "price": round(lv, 2),
                               "type": "resistance", "is_poc": _is_poc(lv)})
        for lv in pivots:
            levels_out.append({"label": "P", "price": round(lv, 2),
                               "type": "pivot", "is_poc": _is_poc(lv)})

        position = None
        if self.pos != 0:
            position = {"dir": self.pos, "entry": round(self.e_price, 2),
                        "stop": round(self.e_stop, 2),
                        "target": round(self.e_target, 2)}

        return {
            "live_price": round(close, 2),
            "poc": (None if poc_price is None else
                    {"price": round(poc_price, 2), "color": poc_color,
                     "weight": round(poc_weight, 4)}),
            "levels": levels_out,
            "supports": [round(x, 2) for x in supports],
            "resistances": [round(x, 2) for x in resistances],
            "win_hi": None if win_hi is None else round(win_hi, 2),
            "win_lo": None if win_lo is None else round(win_lo, 2),
            "bias_txt": bias_txt,
            "near_sup": None if n_sup is None else round(n_sup, 2),
            "near_res": None if n_res is None else round(n_res, 2),
            "momentum": momentum,
            "sig_dir": sig_dir,
            "sig_stop": None if sig_stop is None else round(sig_stop, 2),
            "sig_tgt": None if sig_tgt is None else round(sig_tgt, 2),
            "sig_txt": sig_txt,
            "fire_long": fire_long,
            "fire_short": fire_short,
            "fire_win": fire_win,
            "fire_loss": fire_loss,
            "entry_label": entry_label,
            "position": position,
        }

    def _empty_result(self) -> dict:
        return {
            "live_price": 0.0, "poc": None, "levels": [], "supports": [],
            "resistances": [], "win_hi": None, "win_lo": None,
            "bias_txt": "NEUTRAL — no edge", "near_sup": None, "near_res": None,
            "momentum": "FLAT", "sig_dir": 0, "sig_stop": None, "sig_tgt": None,
            "sig_txt": "", "fire_long": False, "fire_short": False,
            "fire_win": False, "fire_loss": False, "entry_label": None,
            "position": None,
        }


# ────────────────────────────── DATA FETCH ───────────────────────────────────
def _trim_live(df, gran_s: int):
    """Drop the most recent candle if its bucket has not closed yet."""
    if df is None or df.empty or "start" not in df.columns:
        return df
    now = time.time()
    last_start = float(df["start"].iloc[-1])
    if now < last_start + gran_s:
        return df.iloc[:-1].reset_index(drop=True)
    return df


async def run(
    engine: Optional[LiquiditySR] = None,
    *,
    product_id: str = PRODUCT_ID,
    use_confirmed: bool = True,
    session: Optional[aiohttp.ClientSession] = None,
    verbose: bool = True,
) -> dict:
    """
    Fetch Coinbase candles, (optionally) drop the live bar, and evaluate the
    indicator + engine for the latest CLOSED bar.

    Pass a persistent ``engine`` to track an open position across calls; omit it
    for a stateless one-shot snapshot (position starts flat).
    """
    eng = engine or LiquiditySR()
    gran_enum = _parse_granularity(eng.granularity)
    gran_s = _GRAN_SECONDS[gran_enum]

    # Fetch enough bars for a full window + stable EMA/ATR, capped at 350.
    n_fetch = min(350, max(eng.bars_in_window + 30, 210))
    lookback_seconds = n_fetch * gran_s

    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()
    try:
        df = await fetch_candles_async(session, product_id, gran_enum, lookback_seconds)
    finally:
        if own_session:
            await session.close()

    if use_confirmed:
        df = _trim_live(df, gran_s)

    res = eng.evaluate(df)

    if verbose:
        _print_result(res)
    return res


def _print_result(r: dict) -> None:
    print(f"Live BTC      : ${r['live_price']:,.2f}")
    if r["poc"]:
        print(f"POC           : {r['poc']['price']:,.2f} ({r['poc']['color']})")

    def _join(kind):
        s = ", ".join(
            f"{x['label']}={x['price']:,.2f}" + (" *POC" if x["is_poc"] else "")
            for x in r["levels"] if x["type"] == kind)
        return s or "(none)"

    print(f"Resistances   : {_join('resistance')}")
    print(f"Supports      : {_join('support')}")
    print(f"24H Hi / Lo   : "
          f"{('n/a' if r['win_hi'] is None else format(r['win_hi'], ',.2f'))} / "
          f"{('n/a' if r['win_lo'] is None else format(r['win_lo'], ',.2f'))}")
    print(f"Bias          : {r['bias_txt']}  (mom {r['momentum']})")
    print(f"Signal        : dir={r['sig_dir']:+d} "
          f"stop={r['sig_stop']} tgt={r['sig_tgt']} "
          f"{r['sig_txt'] or '(none)'}")
    fires = [name for name, on in (
        ("LONG", r["fire_long"]), ("SHORT", r["fire_short"]),
        ("TARGET", r["fire_win"]), ("STOP", r["fire_loss"])) if on]
    print(f"Alerts        : {', '.join(fires) if fires else '(none)'}")
    if r["entry_label"]:
        print("Entry label   :\n  " + r["entry_label"].replace("\n", "\n  "))


def entry_from_result(res: dict) -> dict | None:
    """
    Pull the LONG/SHORT entry out of an ``evaluate()`` / ``run()`` result, or
    None when no mechanical trigger fired on that bar.  Returns:

        {"side": "LONG"|"SHORT", "sig_txt", "entry", "sl", "tp", "rr", "label"}

    ``label`` is the exact multi-line text the Pine ``label.new`` draws, e.g.:

        LONG (support hold)
        @ 64010.00  SL 63992.43  TP 64500.00  RR 27.9
    """
    if not (res.get("fire_long") or res.get("fire_short")):
        return None
    side = "LONG" if res.get("fire_long") else "SHORT"
    pos = res.get("position") or {}
    entry = pos.get("entry", res.get("live_price"))
    sl = pos.get("stop", res.get("sig_stop"))
    tp = pos.get("target", res.get("sig_tgt"))
    rr = None
    if sl is not None and tp is not None and entry is not None and entry != sl:
        rr = round(abs(tp - entry) / abs(entry - sl), 1)
    # Rebuild the label if the engine didn't keep it (e.g. same-bar stop-out).
    label = res.get("entry_label")
    if label is None and None not in (entry, sl, tp, rr):
        label = (f"{res.get('sig_txt', '')}\n@ {_fmt(entry)}"
                 f"  SL {_fmt(sl)}  TP {_fmt(tp)}  RR {rr:.1f}")
    return {
        "side": side,
        "sig_txt": res.get("sig_txt", ""),
        "entry": entry, "sl": sl, "tp": tp, "rr": rr,
        "label": label,
    }


async def get_entry_signal(
    engine: Optional[LiquiditySR] = None,
    *,
    product_id: str = PRODUCT_ID,
    use_confirmed: bool = True,
    session: Optional[aiohttp.ClientSession] = None,
    verbose: bool = False,
) -> dict | None:
    """
    LONG/SHORT entry for the latest CLOSED bar — the Python equivalent of the
    Pine ``alertcondition(fireLong/fireShort)`` plus the entry label.

    Returns the dict from :func:`entry_from_result` (``side`` / ``sl`` / ``tp`` /
    ``rr`` / ``label`` …), or None when no mechanical trigger fired.  Fetches
    Coinbase candles and evaluates once; call it per closed 5-min bar.

    Pass a persistent ``engine`` to respect one-position-at-a-time state; omit it
    for a stateless "is there a signal right now?" check (position starts flat).
    """
    res = await run(engine=engine, product_id=product_id,
                    use_confirmed=use_confirmed, session=session, verbose=verbose)
    sig = entry_from_result(res)
    if verbose:
        print("\nEntry signal: "
              + (sig["label"] if sig else "(no mechanical trigger on the last bar)"))
    return sig


def _poc_of(highs, lows, vols, *, bins: int = BINS, use_vol: bool = USE_VOL):
    """
    Point of Control over the given bars — the single highest volume/time price
    bin, exactly like the Pine ``pocForBars`` helper.  Returns the bin-center
    price (2dp) or None when the range is flat/empty.
    """
    if not highs or not lows:
        return None
    hi, lo = max(highs), min(lows)
    rng = hi - lo
    if rng <= 0:
        return None
    bin_size = rng / bins
    counts = [0.0] * bins
    for i in range(len(highs)):
        if use_vol:
            v = vols[i]
            w = v if (v == v and v) else 1.0       # v==v guards NaN; 0 → 1.0
        else:
            w = 1.0
        lb = max(0, min(bins - 1, int((lows[i] - lo) / bin_size)))
        hb = max(0, min(bins - 1, int((highs[i] - lo) / bin_size)))
        per = w / (hb - lb + 1)
        for b in range(lb, hb + 1):
            counts[b] += per
    mi = max(range(bins), key=lambda b: counts[b])
    return round(lo + (mi + 0.5) * bin_size, 2)


# The fixed POC lookback windows (hours), matching the multi-window POC panel.
POC_WINDOWS_H = (1, 2, 4, 6, 8, 12, 16, 24, 32, 48, 72)


async def get_1_2_4_6_8_12_16_24_32_48_72_POC(
    *,
    product_id: str = PRODUCT_ID,
    bins: int = BINS,
    use_vol: bool = USE_VOL,
    session: Optional[aiohttp.ClientSession] = None,
    verbose: bool = False,
) -> dict[int, Optional[float]]:
    """
    BTC Point of Control (highest volume/time price node) over each of the
    1, 2, 4, 6, 8, 12, 16, 24, 32, 48 and 72-hour windows — same per-window POC
    as the Pine ``pocForBars`` multi-window panel.

    Coinbase caps a request at 350 candles, so windows ≤ 24h use 5-min candles
    (288 candles for 24h) and windows > 24h use 15-min candles (288 for 72h).

    Returns:
        dict ``{hours: poc_price}`` (poc rounded 2dp, or None on no data),
        e.g. ``{1: 63245.5, 2: 63203.3, ..., 72: 62584.7}``.

    >>> pocs = await get_1_2_4_6_8_12_16_24_32_48_72_POC()
    """
    own = session is None
    s = session or aiohttp.ClientSession()
    try:
        g5 = _parse_granularity("5m")          # FIVE_MINUTE  (300s)
        g15 = _parse_granularity("15m")        # FIFTEEN_MINUTE (900s)
        # 5m covers the ≤24h windows (288 candles); 15m covers ≤72h (288 candles).
        df5 = await fetch_candles_async(s, product_id, g5, (24 * 12 + 5) * _GRAN_SECONDS[g5])
        df15 = await fetch_candles_async(s, product_id, g15, (72 * 4 + 5) * _GRAN_SECONDS[g15])

        out: dict[int, Optional[float]] = {}
        for h in POC_WINDOWS_H:
            df, per_hr = (df5, 12) if h <= 24 else (df15, 4)
            if df is None or df.empty:
                out[h] = None
                continue
            n = h * per_hr
            win = df.iloc[-n:] if len(df) >= n else df
            out[h] = _poc_of(win["high"].tolist(), win["low"].tolist(),
                             win["volume"].tolist(), bins=bins, use_vol=use_vol)

        if verbose:
            print("Multi-window POC (BTC):")
            for h in POC_WINDOWS_H:
                p = out[h]
                print(f"  {h:>2}h : {('n/a' if p is None else format(p, ',.2f'))}")
        return out
    finally:
        if own:
            await s.close()


if __name__ == "__main__":
    _res = asyncio.run(run())
    _sig = entry_from_result(_res)
    print("\nEntry signal: "
          + (_sig["label"] if _sig else "(no mechanical trigger on the last bar)"))
