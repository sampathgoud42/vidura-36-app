"""PREDICT-15: will BTC / ETH finish this Kalshi fifteen-minute window up?

Kalshi's KXBTC15M / KXETH15M ask one thing: is the CF Benchmarks BRTI
average over the 60 seconds before the close at least the average over the
60 seconds before the open (``floor_strike``)? So the question is never "where
is bitcoin going" -- it is "will the price be at or above THIS number at
THIS time", which is a digital option, and has a fair value:

    P(YES) = N( ln(S / K) / (sigma * sqrt(tau)) )

    S      the price now (Coinbase, a BRTI constituent)
    K      the market's strike (floor_strike)
    sigma  the standard deviation of one-minute log returns, last hour
    tau    minutes until the close

WHAT THE RESEARCH FOUND (2026-09-28 .. 10-19, 1,990 settled markets per
coin, walk-forward -- the numbers behind this module):

  * BEFORE the open nothing calls it. Momentum (1/5/15/60m), mean reversion,
    RSI, volatility, the last result, the other coin and the hour score 50-54%
    -- inside the noise. A twelve-feature logistic regression, trained on the
    first 60% and tested on the rest, made 51.5% on BTC and 54.7% on ETH. The
    one real effect, the last minute's move (~54%), is mechanical: the strike
    is a 60-second AVERAGE, so a price still rising starts above it -- which
    the formula above already prices through S/K.
  * INSIDE the window the formula is strong and calibrated: 61% right at
    T+1m, 64% at T+2m, 72% at T+5m, 81-85% at T+10m; when it said 62% YES,
    YES happened 63% of the time.
  * Being right is not an edge -- the market knows where the price is too.
    Against Kalshi's real minute-by-minute quotes (665 windows a coin, the
    last 7 days, taker fee included), buying whenever the model disagreed
    LOST 3-7% on both coins; late in the window (T+8m) it lost heavily, the
    market knowing the BRTI and the closing average better than Coinbase
    does. Kalshi's own mid is as accurate as the model early (T+1..3m:
    63-72%) and slightly better later (lower log-loss from T+5m).

So the CALL is a blend -- half model, half Kalshi mid for the first
BLEND_EARLY_MIN minutes, a quarter model after -- which scored at least as
well as either alone. The model by itself is the FAIR VALUE, and TRADE flags
only a disagreement of EDGE_MIN (10c) after the fee: the only margin that
was not negative on both coins, on samples too small to call proven.
Read-only: nothing here places an order.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

KALSHI = "https://api.elections.kalshi.com/trade-api/v2"
COINBASE = "https://api.exchange.coinbase.com"
# coin -> (Kalshi series, Coinbase product). BTC and ETH by default.
COINS = {"BTC": ("KXBTC15M", "BTC-USD"), "ETH": ("KXETH15M", "ETH-USD")}
DEFAULT_COINS = ("BTC", "ETH")
WINDOW_MIN = 15
SIGMA_MINUTES = 60
# Model minus the price you would pay, after the fee, before the panel says
# TRADE. Smaller margins lost money in the replay against real quotes.
EDGE_MIN = 0.10
# The call blends the model with Kalshi's mid: this weight on the model
# while the window is young, MODEL_WEIGHT_LATE after.
BLEND_EARLY_MIN = 4
MODEL_WEIGHT_EARLY, MODEL_WEIGHT_LATE = 0.5, 0.25
# A 15-minute window can be called a little too confidently in its tails
# (0.96 predicted vs 0.90 seen on BTC at T+5m); probabilities are kept off
# the last two percent either side.
P_FLOOR, P_CEIL = 0.02, 0.98
CACHE_S = 10
SIM_MAX_DAYS = 3

_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()
_sim_cache: dict[tuple, tuple[float, dict]] = {}


def _get(url: str, *, params: dict | None = None, timeout: float = 15.0):
    for attempt in range(4):
        r = requests.get(url, params=params, timeout=timeout)
        if r.status_code == 429 and attempt < 3:
            time.sleep(1.0 + attempt)
            continue
        r.raise_for_status()
        return r.json()
    return {}


def _f(v) -> float | None:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def _ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def fair_yes(spot: float, strike: float, sigma_1m: float, minutes_left: float) -> float:
    """The digital option: P(final >= strike). Clipped to [P_FLOOR, P_CEIL]."""
    if minutes_left <= 0:
        p = 1.0 if spot >= strike else 0.0
    elif not sigma_1m or sigma_1m <= 0:
        p = 0.5 if spot == strike else (1.0 if spot > strike else 0.0)
    else:
        p = ncdf(math.log(spot / strike) / (sigma_1m * math.sqrt(minutes_left)))
    return min(P_CEIL, max(P_FLOOR, p))


def fee(price: float) -> float:
    """Kalshi's taker fee per contract, in dollars: 7% of p(1-p), rounded up."""
    return math.ceil(0.07 * price * (1 - price) * 100 - 1e-9) / 100


def sigma_from(closes: list[float]) -> float | None:
    rets = [math.log(b / a) for a, b in zip(closes, closes[1:]) if a and b]
    if len(rets) < 20:
        return None
    mean = sum(rets) / len(rets)
    return math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))


def blend(p_model: float, yes_bid: float | None, yes_ask: float | None,
          minutes_in: float) -> float:
    """The call's probability: the model with Kalshi's mid, weighted by how far
    into the window it is. No quote, the model alone."""
    if yes_bid is None or yes_ask is None or not 0 < yes_bid <= yes_ask < 1:
        return p_model
    w = MODEL_WEIGHT_EARLY if minutes_in <= BLEND_EARLY_MIN else MODEL_WEIGHT_LATE
    return min(P_CEIL, max(P_FLOOR, w * p_model + (1 - w) * (yes_bid + yes_ask) / 2))


def best_side(p_yes: float, yes_bid: float | None, yes_ask: float | None) -> dict:
    """Which side the model would buy at the live quote, and its edge after
    the fee. YES costs the YES ask; NO costs 1 - the YES bid."""
    out = {"side": None, "price": None, "edge": None}
    cands = []
    if yes_ask is not None and 0.01 <= yes_ask <= 0.99:
        cands.append(("YES", yes_ask, p_yes - yes_ask - fee(yes_ask)))
    if yes_bid is not None and 0.01 <= yes_bid <= 0.99:
        no = round(1 - yes_bid, 4)
        cands.append(("NO", no, (1 - p_yes) - no - fee(no)))
    if cands:
        side, price, edge = max(cands, key=lambda c: c[2])
        out.update(side=side, price=price, edge=round(edge, 4))
    return out


# ---- live ------------------------------------------------------------------

def _market(series: str) -> dict | None:
    """The open window: the open market that closes soonest."""
    d = _get(f"{KALSHI}/markets", params={"series_ticker": series, "status": "open", "limit": 20})
    ms = [m for m in d.get("markets") or [] if m.get("close_time")]
    return min(ms, key=lambda m: m["close_time"]) if ms else None


def _bars(product: str, minutes: int) -> list[list]:
    end = datetime.now(timezone.utc)
    rows = _get(f"{COINBASE}/products/{product}/candles",
                params={"granularity": 60, "start": (end - timedelta(minutes=minutes)).isoformat(),
                        "end": end.isoformat()})
    return sorted(rows or [], key=lambda r: r[0])     # [t, low, high, open, close, volume]


def _spot(product: str) -> float | None:
    return _f(_get(f"{COINBASE}/products/{product}/ticker").get("price"))


def predict(coin: str) -> dict:
    coin = coin.upper()
    series, product = COINS[coin]
    now = datetime.now(timezone.utc)
    m = _market(series)
    if not m:
        return {"coin": coin, "error": f"no open {series} market"}
    strike = _f(m.get("floor_strike"))
    close = _ts(m["close_time"]); opened = _ts(m["open_time"])
    left = max(0.0, (close - now).total_seconds() / 60)
    spot = _spot(product)
    sigma = sigma_from([r[4] for r in _bars(product, SIGMA_MINUTES + 5)])
    yes_bid, yes_ask = _f(m.get("yes_bid_dollars")), _f(m.get("yes_ask_dollars"))
    out = {"coin": coin, "ticker": m["ticker"], "series": series, "title": m.get("title"),
           "open_time": m["open_time"], "close_time": m["close_time"],
           "minutes_left": round(left, 2), "minutes_in": round((now - opened).total_seconds() / 60, 2),
           "spot": spot, "strike": strike, "sigma_1m": sigma,
           "yes_bid": yes_bid, "yes_ask": yes_ask, "at": now.isoformat(timespec="seconds")}
    if strike is None or spot is None:
        out["error"] = "the strike or the price could not be read"
        return out
    p = fair_yes(spot, strike, sigma or 0.0, left)
    minutes_in = max(0.0, (now - opened).total_seconds() / 60)
    p_call = blend(p, yes_bid, yes_ask, minutes_in)
    side = best_side(p, yes_bid, yes_ask)
    dist = (spot / strike - 1) * 100
    move = (sigma or 0) * math.sqrt(max(left, 0.01)) * 100
    out.update(p_yes=round(p_call, 4), p_model=round(p, 4), call="YES" if p_call >= 0.5 else "NO",
               confidence=("high" if abs(p_call - 0.5) >= 0.25
                           else "medium" if abs(p_call - 0.5) >= 0.1 else "low"),
               market_yes=round(((yes_bid or 0) + (yes_ask or 0)) / 2, 4) if yes_ask is not None else None,
               trade=bool(side["edge"] is not None and side["edge"] >= EDGE_MIN),
               trade_side=side["side"], trade_price=side["price"], edge=side["edge"],
               reason=(f"{coin} {spot:,.2f} is {abs(dist):.3f}% {'above' if dist >= 0 else 'below'} the "
                       f"strike {strike:,.2f} with {left:.1f} min left; a typical move in that time is "
                       f"±{move:.3f}%, so the model's fair P(YES) is {p:.0%}"
                       + (f"; with Kalshi's mid the call is {p_call:.0%}." if p_call != p else ".")
                       + (f" Kalshi YES {yes_bid:.2f}/{yes_ask:.2f}." if yes_ask is not None else "")
                       + (f" Best side {side['side']} at {side['price']:.2f}: edge {side['edge']:+.2f} "
                          f"after fee{' -- TRADE' if side['edge'] >= EDGE_MIN else ''}."
                          if side["edge"] is not None else "")))
    return out


def predict_all(coins=DEFAULT_COINS, *, force: bool = False) -> dict:
    key = ",".join(coins)
    with _lock:
        hit = _cache.get(key)
        if hit and not force and time.time() - hit[0] < CACHE_S:
            return hit[1]
    rows = []
    for c in coins:
        try:
            rows.append(predict(c))
        except Exception as exc:                        # noqa: BLE001
            logger.info("predict15 %s: %s", c, exc)
            rows.append({"coin": c.upper(), "error": f"{type(exc).__name__}: {exc}"[:200]})
    out = {"rows": rows, "edge_min": EDGE_MIN,
           "model": "digital option on price vs strike, blended with Kalshi's mid",
           "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with _lock:
        _cache[key] = (time.time(), out)
    return out


# ---- the simulator -----------------------------------------------------------

def _settled(series: str, since: datetime) -> list[dict]:
    rows, cursor = [], None
    while True:
        p = {"series_ticker": series, "status": "settled", "limit": 1000,
             "min_close_ts": int(since.timestamp())}
        if cursor:
            p["cursor"] = cursor
        d = _get(f"{KALSHI}/markets", params=p, timeout=30)
        rows += [m for m in d.get("markets") or [] if m.get("result") in ("yes", "no")]
        cursor = d.get("cursor")
        if not cursor:
            return sorted(rows, key=lambda m: m["open_time"])


def _closes_1m(product: str, start: datetime, end: datetime) -> dict[int, float]:
    out: dict[int, float] = {}
    t = start
    while t < end:
        u = min(end, t + timedelta(minutes=300))
        for r in _get(f"{COINBASE}/products/{product}/candles",
                      params={"granularity": 60, "start": t.isoformat(), "end": u.isoformat()}) or []:
            out[int(r[0])] = float(r[4])
        t = u
        time.sleep(0.1)
    return out


def _quote_at(series: str, m: dict, minute: int) -> tuple[float | None, float | None]:
    o = int(_ts(m["open_time"]).timestamp()); c = int(_ts(m["close_time"]).timestamp())
    d = _get(f"{KALSHI}/series/{series}/markets/{m['ticker']}/candlesticks",
             params={"start_ts": o, "end_ts": c, "period_interval": 1})
    for cs in d.get("candlesticks") or []:
        if round((cs["end_period_ts"] - o) / 60) == minute:
            return (_f((cs.get("yes_bid") or {}).get("close_dollars")),
                    _f((cs.get("yes_ask") or {}).get("close_dollars")))
    return None, None


def simulate(coin: str = "BTC", *, days: float = 1, minute: int = 2,
             edge_min: float = EDGE_MIN) -> dict:
    """Replay real settled windows the way a bot would trade them.

    For each window of the last ``days``: at ``minute`` after the open, the
    model's P(YES) from the Coinbase price then and the hour before it; the
    real Kalshi YES bid/ask at that minute; buy the better side when it beats
    the quote by ``edge_min`` after the fee; settle on Kalshi's own result.
    Every input is what was knowable at that minute.
    """
    coin = coin.upper()
    days = max(0.25, min(float(days), SIM_MAX_DAYS))
    minute = max(0, min(int(minute), WINDOW_MIN - 1))
    key = (coin, days, minute, round(edge_min, 4))
    hit = _sim_cache.get(key)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    series, product = COINS[coin]
    now = datetime.now(timezone.utc)
    markets = _settled(series, now - timedelta(days=days))
    if not markets:
        return {"coin": coin, "error": "no settled markets in that window"}
    first = _ts(markets[0]["open_time"]) - timedelta(minutes=SIGMA_MINUTES + 5)
    closes = _closes_1m(product, first, _ts(markets[-1]["close_time"]))

    calls = right = trades = wins = 0
    pnl = spent = 0.0
    rows = []
    for m in markets:
        opened = _ts(m["open_time"]); strike = _f(m.get("floor_strike"))
        at = int((opened + timedelta(minutes=minute - 1)).timestamp()) if minute else \
            int((opened - timedelta(minutes=1)).timestamp())
        hist = [closes.get(int((opened - timedelta(minutes=k)).timestamp()))
                for k in range(SIGMA_MINUTES + 1, 0, -1)]
        spot = closes.get(at)
        sigma = sigma_from([h for h in hist if h])
        if strike is None or spot is None or sigma is None:
            continue
        p = fair_yes(spot, strike, sigma, WINDOW_MIN - minute)
        yes = m["result"] == "yes"
        try:
            bid, ask = _quote_at(series, m, minute or 1)
            time.sleep(0.05)
        except Exception:                               # noqa: BLE001
            bid = ask = None
        pc = blend(p, bid, ask, minute)
        calls += 1
        right += (pc >= 0.5) == yes
        row = {"ticker": m["ticker"], "open_time": m["open_time"], "p_yes": round(pc, 3),
               "p_model": round(p, 3), "call": "YES" if pc >= 0.5 else "NO",
               "result": m["result"].upper(), "right": (pc >= 0.5) == yes}
        side = best_side(p, bid, ask)
        row.update(yes_bid=bid, yes_ask=ask, side=side["side"], price=side["price"], edge=side["edge"])
        if side["edge"] is not None and side["edge"] >= edge_min:
            won = (side["side"] == "YES") == yes
            cost = side["price"] + fee(side["price"])
            trades += 1; wins += won; pnl += (1.0 if won else 0.0) - cost; spent += cost
            row.update(traded=True, won=won, pnl=round((1.0 if won else 0.0) - cost, 4))
        rows.append(row)
    out = {"coin": coin, "days": days, "minute": minute, "edge_min": edge_min,
           "windows": calls, "accuracy": round(right / calls, 4) if calls else None,
           "trades": trades, "win_rate": round(wins / trades, 4) if trades else None,
           "pnl_per_contract": round(pnl, 2), "roi": round(pnl / spent, 4) if spent else None,
           "rows": rows[-96:],
           "note": ("Each trade is one $1 contract at the real Kalshi quote that minute, plus the "
                    "taker fee, settled on Kalshi's result. Paper only.")}
    _sim_cache[key] = (time.time(), out)
    return out
