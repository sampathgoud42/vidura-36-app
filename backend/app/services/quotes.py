"""Live ticker quotes + classic pivot points via yfinance (keyless).

Serves the Super Signals ticker popup: current price, prior completed
session OHLC, and floor-trader pivots computed from it. Results are cached
for 60s per ticker so popup reopens and multiple viewers do not hammer
Yahoo.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Desk ticker -> (yfinance symbol, TradingView symbol). Anything not listed
# maps to itself for both.
SYMBOL_MAP: dict[str, tuple[str, str]] = {
    "SPX": ("^GSPC", "SPX"),
    "VIX": ("^VIX", "VIX"),
    "BTC": ("BTC-USD", "BTCUSD"),
    "NIFTY": ("^NSEI", "NSE:NIFTY"),
    "BANKNIFTY": ("^NSEBANK", "NSE:BANKNIFTY"),
}

TV_CHART_BASE = "https://www.tradingview.com/chart/OI0ZrHVM/?symbol="

_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 60.0
_LOCK = threading.Lock()


class QuoteError(Exception):
    pass


def _round(v, nd=2):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _pivots(high: float, low: float, close: float) -> dict:
    """Classic floor-trader pivots from the prior completed session."""
    p = (high + low + close) / 3
    rng = high - low
    return {
        "P": _round(p),
        "R1": _round(2 * p - low),
        "R2": _round(p + rng),
        "R3": _round(high + 2 * (p - low)),
        "S1": _round(2 * p - high),
        "S2": _round(p - rng),
        "S3": _round(low - 2 * (high - p)),
    }


def _fetch(ticker: str) -> dict:
    import yfinance as yf  # deferred: heavy import, only when quotes are used

    yf_symbol, tv_symbol = SYMBOL_MAP.get(ticker, (ticker, ticker))
    t = yf.Ticker(yf_symbol)
    hist = t.history(period="7d", interval="1d")
    if hist is None or len(hist) == 0:
        raise QuoteError(f"no market data for {ticker} ({yf_symbol})")

    # Prior COMPLETED session for pivots: if the last bar is today's (still
    # forming while the market trades), step back one row.
    last_bar_date = hist.index[-1].date()
    today_local = datetime.now(hist.index[-1].tzinfo).date() if hist.index[-1].tzinfo else datetime.utcnow().date()
    prior_idx = -2 if (last_bar_date == today_local and len(hist) >= 2) else -1
    prior = hist.iloc[prior_idx]
    prior_date = str(hist.index[prior_idx].date())

    price = None
    try:
        price = _round(t.fast_info.last_price)
    except Exception:
        pass
    if price is None:
        price = _round(hist.iloc[-1]["Close"])
    prev_close = _round(prior["Close"])
    change = _round(price - prev_close) if price is not None and prev_close else None
    change_pct = _round(100 * change / prev_close) if change is not None and prev_close else None

    currency = None
    try:
        currency = t.fast_info.currency
    except Exception:
        pass

    intraday = _intraday_block(t, price)

    return {
        "ticker": ticker,
        "yf_symbol": yf_symbol,
        "tv_symbol": tv_symbol,
        "tv_url": TV_CHART_BASE + tv_symbol,
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": change_pct,
        "currency": currency or "USD",
        "prior_session": {
            "date": prior_date,
            "open": _round(prior["Open"]),
            "high": _round(prior["High"]),
            "low": _round(prior["Low"]),
            "close": _round(prior["Close"]),
        },
        # Classic floor-trader pivots from the prior completed session —
        # the standard intraday levels for the current/next session.
        "pivots": _pivots(float(prior["High"]), float(prior["Low"]), float(prior["Close"])),
        **intraday,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _intraday_block(t, price: float | None) -> dict:
    """Session VWAP + the 10-minute state for the intraday desk.

    - vwap: sum(typical*volume)/sum(volume) over the latest session's 5m
      bars (None for volume-less indices).
    - ten_min: price vs the last COMPLETED 10-minute window (the last two
      fully-closed 5m bars): above_10min / below_10min / within_10min.
    """
    out = {"vwap": None, "vwap_dist_pct": None, "ten_min": None}
    try:
        bars = t.history(period="1d", interval="5m")
        if bars is None or len(bars) == 0:
            return out
        # Drop the still-forming bar: its window contains "now".
        last_ts = bars.index[-1]
        now = datetime.now(last_ts.tzinfo) if last_ts.tzinfo else datetime.utcnow()
        closed = bars.iloc[:-1] if (now - last_ts).total_seconds() < 300 else bars

        vol = closed["Volume"].sum() if "Volume" in closed else 0
        if vol and vol > 0:
            typical = (closed["High"] + closed["Low"] + closed["Close"]) / 3
            vwap = float((typical * closed["Volume"]).sum() / vol)
            out["vwap"] = _round(vwap)
            if price and vwap:
                out["vwap_dist_pct"] = _round(100 * (price - vwap) / vwap)

        if len(closed) >= 2 and price is not None:
            window = closed.iloc[-2:]
            hi = float(window["High"].max())
            lo = float(window["Low"].min())
            state = "above_10min" if price > hi else "below_10min" if price < lo else "within_10min"
            out["ten_min"] = {
                "state": state,
                "high": _round(hi),
                "low": _round(lo),
                "as_of": str(window.index[-1]),
            }
    except Exception as exc:  # intraday extras must never sink the quote
        logger.debug("intraday block failed: %s", exc)
    return out


_BATCH_CACHE: dict[str, tuple[float, list[dict]]] = {}
_BATCH_TTL = 30.0


def batch_quotes(tickers: list[str]) -> list[dict]:
    """Lightweight last/prev-close for many tickers in ONE Yahoo download.

    Fallback path for the Tradier desk's ticker rail when the account has no
    Tradier keys (or Tradier does not know a symbol). Yahoo's daily bar for
    today tracks the live price during the session, so last close == last.
    """
    import yfinance as yf  # deferred: heavy import

    keys = [t.strip().upper() for t in tickers if t.strip()]
    if not keys:
        return []
    cache_key = ",".join(keys)
    now = time.monotonic()
    hit = _BATCH_CACHE.get(cache_key)
    if hit and now - hit[0] < _BATCH_TTL:
        return hit[1]

    yf_syms = [SYMBOL_MAP.get(t, (t, t))[0] for t in keys]
    data = yf.download(yf_syms, period="5d", interval="1d", group_by="ticker",
                       progress=False, threads=True, auto_adjust=False)
    out: list[dict] = []
    for ticker, yf_sym in zip(keys, yf_syms):
        price = prev = None
        try:
            frame = data[yf_sym] if len(yf_syms) > 1 else data
            closes = frame["Close"].dropna()
            if len(closes) >= 1:
                price = _round(closes.iloc[-1])
            if len(closes) >= 2:
                prev = _round(closes.iloc[-2])
        except Exception as exc:  # one bad symbol must not sink the rail
            logger.debug("batch quote failed for %s: %s", ticker, exc)
        change = _round(price - prev) if price is not None and prev else None
        out.append({
            "symbol": ticker,
            "price": price,
            "prev_close": prev,
            "change": change,
            "change_pct": _round(100 * change / prev) if change is not None and prev else None,
            "source": "yfinance",
        })
    _BATCH_CACHE[cache_key] = (time.monotonic(), out)
    return out


def quote_for(ticker: str) -> dict:
    """Cached quote+pivots for a desk ticker (single-flight per process)."""
    key = ticker.strip().upper()
    if not key or not key.replace("-", "").replace("^", "").isalnum():
        raise QuoteError(f"invalid ticker '{ticker}'")
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and time.monotonic() - hit[0] < _CACHE_TTL:
            return hit[1]
        try:
            data = _fetch(key)
        except QuoteError:
            raise
        except Exception as exc:
            raise QuoteError(f"quote fetch failed for {key}: {exc}") from exc
        _CACHE[key] = (time.monotonic(), data)
        return data
