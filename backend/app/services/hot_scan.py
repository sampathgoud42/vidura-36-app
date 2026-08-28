"""HOT: which of the large caps are in a strong, one-sided trend right now.

The desk question this answers: of the top-100 names, which ones is the
directional-movement system saying are TRENDING hard enough to be worth an
option — not merely drifting, and not chopping — and which way.

Three gates, all on Wilder's 14-period DMI/ADX, read in both directions
(user 08/17):

    CALL    +DI  >  25   and  +DI >= -DI x 2   and  ADX > 34
    PUT     -DI  >  25   and  -DI >= +DI x 2   and  ADX > 34

Symmetric because the system is: DMI measures up-moves and down-moves the
same way, so a name whose -DI dominates is exactly as tradable as one whose
+DI does, in the opposite direction. Both sides can never pass at once —
each demands its own DI be at least twice the other.

The middle one is the interesting gate. +DI above -DI is a crossover, which
happens constantly and reverses just as often; TWICE -DI is a different claim
— that the buyers are not being answered. ADX then says the market agrees:
above 34 is a strong trend by Wilder's own reading, well past the usual 20-25
"trend exists" line.

The arithmetic is a port of the desk chart's adxCompute, deliberately line for
line. If the two drifted, a name could be HOT here and show no B marker on its
own chart, which is worse than having no scanner at all.

Cost is why this caches: one timesales call per symbol, so a 100-name sweep is
100 calls. A request never waits for it — the last good snapshot comes back
immediately and a stale one refreshes in the background.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings

logger = logging.getLogger(__name__)

CST = ZoneInfo("America/Chicago")

# user_id -> {"at": monotonic, "day": ..., "rows": [...], "meta": {...}}
_CACHE: dict[str, dict] = {}
_REFRESHING: set[str] = set()
_LOCK = threading.Lock()


# What the desk may ask for, in the vendor's own spelling. All four are served
# natively by /markets/timesales — nothing here is resampled from finer bars,
# which would invent a bar boundary the charts do not share.
INTERVALS = ("5min", "15min", "30min", "1h")


def _today() -> str:
    return f"{datetime.now(CST):%Y-%m-%d}"


def universe() -> list[str]:
    s = get_settings()
    return [t.strip().upper() for t in s.tradier_hot_universe.split(",") if t.strip()]


def days_for(interval: str) -> int:
    """Lookback for this granularity.

    A coarser bar needs a longer window to reach the same count: 40 days of
    hourly bars is the same 200-ish readings as 5 days of 5-minute ones. Ask
    for 5 days of hourly and the ADX comes back built mostly from its seed.
    """
    s = get_settings()
    table = {}
    for part in s.tradier_hot_days_by_interval.split(","):
        if ":" in part:
            key, _, val = part.partition(":")
            try:
                table[key.strip()] = int(val)
            except ValueError:
                continue
    return table.get(interval, 5)


# ── Wilder DMI/ADX ──────────────────────────────────────────────────────────

def _wilder(src: list[float], period: int) -> list[float | None]:
    """Seed with a sum over the first `period`, then decay by 1/period.

    Not a moving average of the last `period` values — Wilder's own smoothing,
    which is what every charting package draws and therefore the only version
    whose numbers match the ones on screen.
    """
    out: list[float | None] = []
    acc = 0.0
    for i, v in enumerate(src):
        if i < period:
            acc += v
            out.append(acc if i == period - 1 else None)
        else:
            acc = acc - acc / period + v
            out.append(acc)
    return out


def dmi(bars: list[dict], period: int = 14, slope_lb: int = 0) -> dict | None:
    """Latest {plus_di, minus_di, adx, dxs, adx_slope} for these bars, or None.

    ``bars`` are dicts with high/low/close. Needs 2*period+2 of them: the ADX
    is an average of DX values that are themselves smoothed, so a short series
    produces a number that is mostly its own seed.

    When ``slope_lb`` > 0, ``adx_slope`` is ``adx[-1] - adx[-(1+slope_lb)]``,
    measuring whether the trend is strengthening (>0) or fading (<0).
    ``dxs`` is the signed directional efficiency: (+DI - -DI)/(+DI + -DI), in
    [-1, 1]. Its absolute value says how one-sided the move is, regardless of
    whether it is up or down.
    """
    n = len(bars)
    if n < period * 2 + 2:
        return None

    tr: list[float] = []
    plus_dm: list[float] = []
    minus_dm: list[float] = []
    for i in range(1, n):
        h, low = float(bars[i]["high"]), float(bars[i]["low"])
        pc = float(bars[i - 1]["close"])
        ph, pl = float(bars[i - 1]["high"]), float(bars[i - 1]["low"])
        tr.append(max(h - low, abs(h - pc), abs(low - pc)))
        up = h - ph
        down = pl - low
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)

    s_tr = _wilder(tr, period)
    s_p = _wilder(plus_dm, period)
    s_m = _wilder(minus_dm, period)

    plus_di: list[float | None] = []
    minus_di: list[float | None] = []
    dx: list[float | None] = []
    for i in range(len(tr)):
        if s_tr[i] is None or s_tr[i] == 0:
            plus_di.append(None)
            minus_di.append(None)
            dx.append(None)
            continue
        pdi = 100.0 * (s_p[i] / s_tr[i])
        mdi = 100.0 * (s_m[i] / s_tr[i])
        plus_di.append(pdi)
        minus_di.append(mdi)
        total = pdi + mdi
        dx.append(0.0 if total == 0 else 100.0 * (abs(pdi - mdi) / total))

    first = next((i for i, v in enumerate(dx) if v is not None), None)
    if first is None or first + period > len(dx):
        return None
    adx: list[float | None] = [None] * len(dx)
    adx[first + period - 1] = sum(dx[first:first + period]) / period
    for i in range(first + period, len(dx)):
        adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    if plus_di[-1] is None or minus_di[-1] is None or adx[-1] is None:
        return None

    pdi_last = plus_di[-1]
    mdi_last = minus_di[-1]
    total = pdi_last + mdi_last
    dxs = (pdi_last - mdi_last) / total if total > 0 else 0.0

    adx_slope = 0.0
    if slope_lb > 0:
        prior_idx = len(adx) - 1 - slope_lb
        if prior_idx >= 0 and adx[prior_idx] is not None:
            adx_slope = adx[-1] - adx[prior_idx]

    return {
        "plus_di": pdi_last, "minus_di": mdi_last, "adx": adx[-1],
        "dxs": dxs, "adx_slope": adx_slope,
    }


def hot_side(reading: dict, s=None) -> str | None:
    """'call', 'put', or None — the same three gates read in both directions.

    The gates are symmetric because the system is: DMI measures up-moves and
    down-moves the same way, so a name whose -DI dominates is exactly as
    tradable as one whose +DI does, in the opposite direction. Up buys a call,
    down buys a put (user 08/17).

    Both can never pass at once: each demands its own DI be at least twice the
    other, and that pair of claims has no solution.
    """
    s = s or get_settings()
    pdi, mdi, adx = reading["plus_di"], reading["minus_di"], reading["adx"]
    if adx <= s.tradier_hot_min_adx:
        return None
    if pdi > s.tradier_hot_min_pdi and pdi >= mdi * s.tradier_hot_di_ratio:
        return "call"
    if mdi > s.tradier_hot_min_pdi and mdi >= pdi * s.tradier_hot_di_ratio:
        return "put"
    return None


def is_hot(reading: dict, s=None) -> bool:
    """Legacy call-side helper — the upside gates only."""
    return hot_side(reading, s) == "call"


def superhot_side(reading: dict, s=None) -> str | None:
    """'call', 'put', or None — the SUPERHOT tier, period-9 DMI with five gates.

    Inspired by cross-sectional ADX/DMI research: shorter period (halves the
    lag), ADX as a band (not just a floor — above the ceiling is exhaustion),
    positive ADX slope (trend is strengthening), and directional efficiency
    (|DXS| measures how one-sided the move is, not just whether DI crossed).
    """
    s = s or get_settings()
    pdi = reading["plus_di"]
    mdi = reading["minus_di"]
    adx = reading["adx"]
    dxs = reading.get("dxs", 0)
    adx_slope = reading.get("adx_slope", 0)

    if adx < s.tradier_superhot_min_adx or adx > s.tradier_superhot_max_adx:
        return None
    if adx_slope <= 0:
        return None
    if abs(dxs) < s.tradier_superhot_min_dxs:
        return None
    if pdi > s.tradier_superhot_min_pdi and pdi >= mdi * s.tradier_superhot_di_ratio:
        return "call"
    if mdi > s.tradier_superhot_min_pdi and mdi >= pdi * s.tradier_superhot_di_ratio:
        return "put"
    return None


def _superhot_score(reading: dict) -> float:
    """Rank superhot names by directional efficiency * trend acceleration.

    NOT ADX descending — that selects the names whose move is already most
    complete. The score favours names where the trend is strengthening
    (adx_slope) and one side is dominating (|dxs|), which is where the
    next move is, not where the last one was.
    """
    return abs(reading.get("dxs", 0)) * max(reading.get("adx_slope", 0), 0.01)


# ── the sweep ───────────────────────────────────────────────────────────────

def _regular_session(rows: list[dict]) -> list[dict]:
    """09:30-16:00 only — the same slice the desk chart draws.

    Extended-hours bars are thin and gappy, and a gap is a large true range,
    so leaving them in inflates ADX. The chart drops them; if the scanner did
    not, a name could rank HOT here on overnight noise and show no marker on
    its own chart.
    """
    out = []
    for r in rows:
        hm = str(r.get("time") or "")[11:16]
        if "09:30" <= hm <= "16:00":
            out.append(r)
    return out


def _bars(client, symbol: str, interval: str, days: int) -> list[dict]:
    start = (datetime.now(CST) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
    rows = client.timesales(symbol, interval, start=start)
    rows = [r for r in rows
            if r.get("high") is not None and r.get("low") is not None
            and r.get("close") is not None]
    return _regular_session(rows)


def _scan_symbol(client, symbol: str, interval: str, days: int) -> dict | None:
    try:
        bars = _bars(client, symbol, interval, days)
    except Exception as exc:                              # noqa: BLE001
        logger.debug("hot scan %s: %s", symbol, exc)
        return None
    reading = dmi(bars)
    if reading is None:
        return None
    last = bars[-1]
    side = hot_side(reading)
    pdi, mdi = reading["plus_di"], reading["minus_di"]
    if side == "put":
        ratio = round(mdi / pdi, 2) if pdi > 0 else None
    else:
        ratio = round(pdi / mdi, 2) if mdi > 0 else None

    s = get_settings()
    sh_reading = dmi(bars, period=s.tradier_superhot_di_period,
                     slope_lb=s.tradier_superhot_slope_lb)
    sh_side = superhot_side(sh_reading, s) if sh_reading else None
    sh_score = round(_superhot_score(sh_reading), 4) if sh_reading and sh_side else 0

    row = {
        "symbol": symbol,
        "side": side,                       # call | put | None
        "plus_di": round(pdi, 2),
        "minus_di": round(mdi, 2),
        "adx": round(reading["adx"], 2),
        "di_ratio": ratio,
        "last": last.get("close"),
        "bars": len(bars),
    }
    if sh_reading:
        row["sh_side"] = sh_side
        row["sh_pdi"] = round(sh_reading["plus_di"], 2)
        row["sh_mdi"] = round(sh_reading["minus_di"], 2)
        row["sh_adx"] = round(sh_reading["adx"], 2)
        row["sh_dxs"] = round(sh_reading["dxs"], 3)
        row["sh_slope"] = round(sh_reading["adx_slope"], 2)
        row["sh_score"] = sh_score
    return row


def _refresh(user, live: bool, interval: str) -> dict:
    from app.services.tradier_bot import client_for

    s = get_settings()
    syms = universe()
    days = days_for(interval)
    started = time.time()
    client = client_for(user, live=live)
    rows: list[dict] = []
    try:
        with ThreadPoolExecutor(max_workers=s.tradier_flow_workers) as pool:
            for got in pool.map(
                lambda sym: _scan_symbol(client, sym, interval, days),
                syms,
            ):
                if got is not None:
                    rows.append(got)
    finally:
        client.close()

    hot = [r for r in rows if r["side"] is not None]
    hot.sort(key=lambda r: (r["adx"], r["di_ratio"] or 0), reverse=True)

    superhot = [r for r in rows if r.get("sh_side") is not None
                and r.get("sh_adx", 0) >= 36
                and ((r["sh_side"] == "call" and r.get("sh_pdi", 0) >= 25)
                     or (r["sh_side"] == "put" and r.get("sh_mdi", 0) >= 25))]
    superhot.sort(key=lambda r: r.get("sh_score", 0), reverse=True)
    superhot = superhot[:10]

    return {
        "rows": hot,
        "superhot": superhot,
        "meta": {
            "day": _today(),
            "interval": interval,
            "days": days,
            "scanned": len(syms),
            "with_readings": len(rows),
            "hot": len(hot),
            "calls": sum(1 for r in hot if r["side"] == "call"),
            "puts": sum(1 for r in hot if r["side"] == "put"),
            "superhot": len(superhot),
            "sh_calls": sum(1 for r in superhot if r["sh_side"] == "call"),
            "sh_puts": sum(1 for r in superhot if r["sh_side"] == "put"),
            "gates": {
                "min_di": s.tradier_hot_min_pdi,
                "di_ratio": s.tradier_hot_di_ratio,
                "min_adx": s.tradier_hot_min_adx,
            },
            "sh_gates": {
                "di_period": s.tradier_superhot_di_period,
                "min_adx": s.tradier_superhot_min_adx,
                "max_adx": s.tradier_superhot_max_adx,
                "min_dxs": s.tradier_superhot_min_dxs,
                "slope_lb": s.tradier_superhot_slope_lb,
            },
            "took_s": round(time.time() - started, 1),
            "venue": "live" if live else "sandbox",
            "at": f"{datetime.now(CST):%H:%M:%S}",
        },
    }


def _refresh_async(user, live: bool, interval: str) -> None:
    uid = user.user_id
    with _LOCK:
        if uid in _REFRESHING:
            return
        _REFRESHING.add(uid)

    def run():
        try:
            got = _refresh(user, live, interval)
            _CACHE[uid] = {"at": time.monotonic(), "day": got["meta"]["day"],
                           "interval": interval, **got}
        except Exception as exc:                          # noqa: BLE001
            logger.warning("hot scan refresh failed: %s", exc)
            cached = _CACHE.get(uid)
            if cached is not None:
                cached["error"] = str(exc)[:200]
        finally:
            with _LOCK:
                _REFRESHING.discard(uid)

    threading.Thread(target=run, daemon=True, name=f"hotscan-{uid[:8]}").start()


def snapshot(user, *, live: bool = False, interval: str | None = None,
             force: bool = False) -> dict:
    """Last good HOT snapshot; refreshes in the background when stale.

    Returns immediately either way — the first call of a session comes back
    empty with ``refreshing: true`` rather than blocking for 100 calls.
    """
    s = get_settings()
    interval = interval or s.tradier_hot_interval
    uid = user.user_id
    cached = _CACHE.get(uid)
    fresh = (cached is not None
             and cached.get("day") == _today()
             and cached.get("interval") == interval
             and time.monotonic() - cached["at"] < s.tradier_hot_ttl_s)
    if force or not fresh:
        _refresh_async(user, live, interval)
    with _LOCK:
        refreshing = uid in _REFRESHING
    if cached is None or cached.get("interval") != interval:
        return {"rows": [], "superhot": [],
                "meta": {"day": _today(), "interval": interval},
                "refreshing": refreshing, "age_s": None}
    return {
        "rows": cached["rows"],
        "superhot": cached.get("superhot", []),
        "meta": cached["meta"],
        "error": cached.get("error"),
        "refreshing": refreshing,
        "age_s": int(time.monotonic() - cached["at"]),
    }


# ── Commodities scan (Gold / Silver / WTI — binary-trading signals) ────────

COMMODITY_TICKERS = {
    "GLD": "Gold",
    "SLV": "Silver",
    "USO": "Crude Oil",
}

# API Ninjas commodity names — free tier rotates weekly, so each ticker has
# a list of fallbacks: try until one returns 200.
_NINJA_NAMES = {
    "GLD": ["micro_gold", "gold"],
    "SLV": ["micro_silver", "silver"],
    "USO": ["crude_oil", "brent_crude_oil", "natural_gas"],
}

_COMM_CACHE: dict[str, dict] = {}
_COMM_LOCK = threading.Lock()
_COMM_TTL = 55  # just under 60s frontend poll; manual refresh bypasses

# Off-hours bar accumulator: builds 1-min OHLC bars from polled API Ninjas
# prices so DMI can run even when Tradier has no data.
# Structure: { commodity_name: { "current": {open,high,low,close,minute},
#                                 "bars": [completed 1-min bars] } }
_NINJA_BARS: dict[str, dict] = {}
_NINJA_MAX_BARS = 200  # rolling window


def _is_tradier_hours() -> bool:
    """True during Mon-Fri 08:30-15:00 CST (Tradier market hours)."""
    now = datetime.now(CST)
    wd = now.weekday()  # 0=Mon … 6=Sun
    if wd >= 5:  # Saturday or Sunday
        return False
    hhmm = f"{now:%H:%M}"
    return "08:30" <= hhmm < "15:00"


def _fetch_ninja_price(names: list[str]) -> tuple[float | None, str | None]:
    """Try each name until one returns 200. Returns (price, matched_name)."""
    import httpx

    s = get_settings()
    key = s.apininjas_api_key
    if not key:
        return None, None
    for name in names:
        try:
            resp = httpx.get(
                "https://api.api-ninjas.com/v1/commodityprice",
                params={"name": name},
                headers={"X-Api-Key": key},
                timeout=10,
            )
            if resp.status_code == 400:
                continue
            resp.raise_for_status()
            data = resp.json()
            p = None
            if isinstance(data, dict):
                p = data.get("price")
            elif isinstance(data, list) and data:
                p = data[0].get("price")
            if p is not None:
                return float(p), data.get("name") or name
        except Exception as exc:  # noqa: BLE001
            logger.debug("API Ninjas %s: %s", name, exc)
    return None, None


def _ninja_accumulate(symbol: str, price: float) -> None:
    """Add a price tick to the off-hours bar accumulator."""
    now = datetime.now(CST)
    minute_key = f"{now:%Y-%m-%d %H:%M}"

    if symbol not in _NINJA_BARS:
        _NINJA_BARS[symbol] = {"current": None, "bars": []}

    acc = _NINJA_BARS[symbol]
    cur = acc["current"]

    if cur is None or cur["minute"] != minute_key:
        if cur is not None:
            acc["bars"].append({
                "time": cur["minute"],
                "open": cur["open"], "high": cur["high"],
                "low": cur["low"], "close": cur["close"],
            })
            if len(acc["bars"]) > _NINJA_MAX_BARS:
                acc["bars"] = acc["bars"][-_NINJA_MAX_BARS:]
        acc["current"] = {
            "minute": minute_key,
            "open": price, "high": price, "low": price, "close": price,
        }
    else:
        cur["close"] = price
        if price > cur["high"]:
            cur["high"] = price
        if price < cur["low"]:
            cur["low"] = price


_NINJA_THREAD: threading.Thread | None = None
_NINJA_STOP = threading.Event()


def _ninja_poll_loop() -> None:
    """Background thread: poll API Ninjas every 60s during off-hours to
    accumulate 1-min bars so DMI is ready when the user checks."""
    while not _NINJA_STOP.is_set():
        if not _is_tradier_hours():
            for sym, names in _NINJA_NAMES.items():
                price, _ = _fetch_ninja_price(names)
                if price is not None:
                    _ninja_accumulate(sym, price)
        _NINJA_STOP.wait(60)


def _ensure_ninja_thread() -> None:
    global _NINJA_THREAD
    if _NINJA_THREAD is not None and _NINJA_THREAD.is_alive():
        return
    _NINJA_STOP.clear()
    _NINJA_THREAD = threading.Thread(
        target=_ninja_poll_loop, daemon=True, name="ninja-comm-poll")
    _NINJA_THREAD.start()
    logger.info("commodity bar accumulator started (60s poll)")


def _aggregate_nmin(bars: list[dict], n: int) -> list[dict]:
    """Merge consecutive 1-min bars into n-min bars."""
    out = []
    i = 0
    while i + n - 1 < len(bars):
        chunk = bars[i : i + n]
        out.append({
            "time": chunk[0].get("time"),
            "open": chunk[0].get("open"),
            "high": max(float(b["high"]) for b in chunk),
            "low": min(float(b["low"]) for b in chunk),
            "close": chunk[-1].get("close"),
            "volume": sum(b.get("volume") or 0 for b in chunk),
        })
        i += n
    return out


def _aggregate_2min(bars: list[dict]) -> list[dict]:
    return _aggregate_nmin(bars, 2)


def _commodity_side(reading: dict) -> str | None:
    """Call/put based on DI dominance — no gates, just which side is bigger."""
    if reading is None:
        return None
    pdi, mdi = reading["plus_di"], reading["minus_di"]
    if pdi > mdi:
        return "call"
    if mdi > pdi:
        return "put"
    return None


def _fill_dmi_row(row: dict, bars_1m: list[dict]) -> None:
    """Compute 1m, 2m and 5m DMI and fill the row dict in place."""
    bars_2m = _aggregate_nmin(bars_1m, 2)
    bars_5m = _aggregate_nmin(bars_1m, 5)
    r1 = dmi(bars_1m, period=9, slope_lb=3)
    r2 = dmi(bars_2m, period=9, slope_lb=3)
    r5 = dmi(bars_5m, period=9, slope_lb=3)
    row["bars_1m"] = len(bars_1m)
    row["bars_2m"] = len(bars_2m)
    row["bars_5m"] = len(bars_5m)
    if r1:
        row["m1_side"] = _commodity_side(r1)
        row["m1_pdi"] = round(r1["plus_di"], 2)
        row["m1_mdi"] = round(r1["minus_di"], 2)
        row["m1_adx"] = round(r1["adx"], 2)
        row["m1_dxs"] = round(r1["dxs"], 3)
        row["m1_slope"] = round(r1["adx_slope"], 2)
    if r2:
        row["m2_side"] = _commodity_side(r2)
        row["m2_pdi"] = round(r2["plus_di"], 2)
        row["m2_mdi"] = round(r2["minus_di"], 2)
        row["m2_adx"] = round(r2["adx"], 2)
        row["m2_dxs"] = round(r2["dxs"], 3)
        row["m2_slope"] = round(r2["adx_slope"], 2)
    if r5:
        row["m5_side"] = _commodity_side(r5)
        row["m5_pdi"] = round(r5["plus_di"], 2)
        row["m5_mdi"] = round(r5["minus_di"], 2)
        row["m5_adx"] = round(r5["adx"], 2)
        row["m5_dxs"] = round(r5["dxs"], 3)
        row["m5_slope"] = round(r5["adx_slope"], 2)
    sides = [row.get("m1_side"), row.get("m2_side"), row.get("m5_side")]
    sides = [s for s in sides if s]
    row["signal"] = sides[0] if (len(sides) >= 2 and len(set(sides)) == 1) else None


def _scan_commodity_tradier(client, symbol: str) -> dict | None:
    """Market-hours scan via Tradier timesales."""
    try:
        start = (datetime.now(CST) - timedelta(days=2)).strftime("%Y-%m-%d %H:%M")
        raw = client.timesales(symbol, "1min", start=start)
        bars_1m = _regular_session([
            r for r in raw
            if r.get("high") is not None and r.get("low") is not None
            and r.get("close") is not None
        ])
    except Exception as exc:  # noqa: BLE001
        logger.debug("commodity scan (tradier) %s: %s", symbol, exc)
        return None
    if not bars_1m:
        return None
    row = {
        "symbol": symbol,
        "label": COMMODITY_TICKERS.get(symbol, symbol),
        "last": bars_1m[-1].get("close"),
        "source": "tradier",
    }
    _fill_dmi_row(row, bars_1m)
    return row


def _scan_commodity_ninja(symbol: str) -> dict | None:
    """Off-hours scan via API Ninjas + accumulated bars."""
    ninja_names = _NINJA_NAMES.get(symbol)
    if not ninja_names:
        return None
    price, matched = _fetch_ninja_price(ninja_names)
    if price is None:
        return None
    _ninja_accumulate(symbol, price)
    acc = _NINJA_BARS.get(symbol, {})
    bars_1m = list(acc.get("bars", []))
    cur = acc.get("current")
    if cur:
        bars_1m.append({
            "time": cur["minute"],
            "open": cur["open"], "high": cur["high"],
            "low": cur["low"], "close": cur["close"],
        })
    row = {
        "symbol": symbol,
        "label": COMMODITY_TICKERS.get(symbol, symbol),
        "last": price,
        "source": "apininjas",
        "ninja_name": matched,
    }
    if len(bars_1m) >= 22:
        _fill_dmi_row(row, bars_1m)
    else:
        row["bars_1m"] = len(bars_1m)
        row["bars_2m"] = len(bars_1m) // 2
        row["signal"] = None
    return row


def commodities_scan(user, *, live: bool = False, force: bool = False) -> dict:
    uid = user.user_id
    with _COMM_LOCK:
        cached = _COMM_CACHE.get(uid)
        if (not force and cached is not None
                and time.monotonic() - cached["at"] < _COMM_TTL):
            return {
                "rows": cached["rows"],
                "meta": cached["meta"],
                "age_s": int(time.monotonic() - cached["at"]),
            }

    use_tradier = _is_tradier_hours()
    if not use_tradier:
        _ensure_ninja_thread()
    started = time.time()
    rows: list[dict] = []

    if use_tradier:
        from app.services.tradier_bot import client_for
        client = client_for(user, live=live)
        try:
            for sym in COMMODITY_TICKERS:
                got = _scan_commodity_tradier(client, sym)
                if got is not None:
                    rows.append(got)
        finally:
            client.close()
    else:
        for sym in COMMODITY_TICKERS:
            got = _scan_commodity_ninja(sym)
            if got is not None:
                rows.append(got)

    source = "tradier" if use_tradier else "apininjas"
    meta = {
        "day": _today(),
        "source": source,
        "scanned": len(COMMODITY_TICKERS),
        "with_readings": len(rows),
        "took_s": round(time.time() - started, 1),
        "venue": "live" if (use_tradier and live) else source,
        "at": f"{datetime.now(CST):%H:%M:%S}",
    }
    with _COMM_LOCK:
        _COMM_CACHE[uid] = {"at": time.monotonic(), "rows": rows, "meta": meta}
    return {"rows": rows, "meta": meta, "age_s": 0}
