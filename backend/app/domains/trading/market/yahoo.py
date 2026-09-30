"""Candles from Yahoo (yfinance), for BreakoutRadar.

Why not Tradier, as the rest of the desk does: Tradier has no Indian listings
at all, and for the US side a scan is ~500 names -- at Tradier's 120 market
requests a minute (60 on the sandbox) that is four to nine minutes per scan,
and its 15-minute history stops at 40 days, which leaves a 4-hour 50 EMA
mostly seed. Yahoo answers a batch in one call and keeps 60 days of 5m/15m,
730 of hourly and all of daily. The cost is that it is unofficial: it
throttles and renames without notice, which is why a failed chunk costs its
own tickers and nothing else.

What each timeframe fetches (enough for a converged 50 EMA plus a 20-candle
range):

    5m   5-minute bars, 5 days        15m  15-minute bars, 15 days
    1h   hourly bars, 60 days          4h   hourly bars, 180 days, folded
    1d   daily bars, 1 year (also the daily context for every timeframe)

Yahoo has no 4-hour bar either. Hourly bars are folded into 4-hour ones
anchored on each market's open -- 09:30 ET (09:30-13:30, 13:30-16:00) and
09:15 IST (09:15-13:15, 13:15-15:30) -- in exchange wall-clock time, so a
daylight-saving change moves nothing.
"""

from __future__ import annotations

import logging

import pandas as pd

from app.domains.trading.market import fundamentals

logger = logging.getLogger(__name__)

FETCH = {"5m": ("5m", "5d"), "15m": ("15m", "15d"), "1h": ("60m", "60d"),
         "4h": ("60m", "180d"), "1d": ("1d", "1y")}
DAILY = ("1d", "1y")
ZONE = {"US": "America/New_York", "INDIA": "Asia/Kolkata"}
SESSION = {"US": ("09:30", "16:00"), "INDIA": ("09:15", "15:30")}
ANCHOR = {"US": "9h30min", "INDIA": "9h15min"}
CHUNK = 80                  # tickers per download: Yahoo copes, memory stays flat


def yahoo_ticker(symbol: str, market: str) -> str:
    """How Yahoo spells a listing: BRK.B -> BRK-B; RELIANCE -> RELIANCE.NS."""
    if market == "INDIA":
        s = symbol.strip().upper()
        return s if s.endswith((".NS", ".BO")) else f"{s}.NS"
    return fundamentals.yahoo_symbol(symbol)


def _download(tickers: list[str], interval: str, period: str) -> pd.DataFrame:
    """One batch from Yahoo. The seam tests substitute: nothing else here
    reaches the network."""
    import yfinance as yf                   # deferred: a heavy import

    return yf.download(tickers=tickers, interval=interval, period=period,
                       group_by="ticker", auto_adjust=True, prepost=False,
                       threads=True, progress=False)


def split(raw: pd.DataFrame, tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Yahoo's batch frame -> one OHLCV frame per ticker (lowercase columns).

    A batch is a two-level column index, ticker by field; a lone ticker can
    come back flat. Either way a ticker with no rows is simply absent."""
    out: dict[str, pd.DataFrame] = {}
    if raw is None or raw.empty:
        return out
    if isinstance(raw.columns, pd.MultiIndex):
        level = next((i for i in range(raw.columns.nlevels)
                      if set(tickers) & set(raw.columns.get_level_values(i))), None)
        if level is None:
            return out
        for ticker in tickers:
            if ticker not in raw.columns.get_level_values(level):
                continue
            part = raw.xs(ticker, axis=1, level=level)
            out[ticker] = part
    elif len(tickers) == 1:
        out[tickers[0]] = raw
    cleaned = {}
    for ticker, part in out.items():
        part = part.rename(columns=lambda c: str(c).strip().lower())
        if "close" not in part.columns:
            continue
        part = part[[c for c in ("open", "high", "low", "close", "volume") if c in part.columns]]
        part = part[part["close"].notna()]
        if not part.empty:
            cleaned[ticker] = part
    return cleaned


def local(frame: pd.DataFrame, market: str, *, intraday: bool) -> pd.DataFrame:
    """Exchange wall-clock time without a zone; intraday bars inside the
    regular session only."""
    index = pd.DatetimeIndex(frame.index)
    if index.tz is not None:
        index = index.tz_convert(ZONE[market]).tz_localize(None)
    frame = frame.set_axis(index).sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    if intraday:
        start, end = SESSION[market]
        frame = frame.between_time(start, end, inclusive="left")
    return frame


def four_hour(frame: pd.DataFrame, market: str) -> pd.DataFrame:
    grouped = frame.resample("4h", offset=ANCHOR[market], label="left", closed="left")
    out = grouped.agg({"open": "first", "high": "max", "low": "min",
                       "close": "last", "volume": "sum"})
    return out[out["close"].notna()]


def _batches(symbols: list[str], market: str, interval: str, period: str,
             progress=None, done: int = 0, total: int | None = None,
             strict: bool = False) -> dict[str, pd.DataFrame]:
    total = total or len(symbols)
    by_yahoo = {yahoo_ticker(s, market): s for s in symbols}
    names = list(by_yahoo)
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(names), CHUNK):
        chunk = names[i:i + CHUNK]
        try:
            got = split(_download(chunk, interval, period), chunk)
        except Exception as exc:                        # noqa: BLE001
            if strict:
                raise
            logger.info("yahoo: %d tickers (%s %s) failed: %s: %s", len(chunk),
                        interval, period, type(exc).__name__, exc)
            got = {}
        for ticker, frame in got.items():
            out[by_yahoo[ticker]] = frame
        if progress:
            progress(done + min(i + CHUNK, len(names)), total)
    return out


def frames(market: str, symbols: list[str], interval: str, period: str, *,
           intraday: bool, progress=None) -> dict[str, pd.DataFrame]:
    """One download for a whole list, each ticker's frame in exchange time
    (intraday ones inside the regular session). A market's sweep of several
    timeframes shares these instead of fetching the same bars per timeframe."""
    raw = _batches(symbols, market, interval, period, progress=progress)
    return {s: local(f, market, intraday=intraday) for s, f in raw.items()}


def trim_days(frame: pd.DataFrame, market: str, days: int) -> pd.DataFrame:
    """The last `days` calendar days of an exchange-time frame: what Yahoo's
    own `{days}d` period would have returned from a longer download."""
    cut = pd.Timestamp.now(tz=ZONE[market]).tz_localize(None) - pd.Timedelta(days=days)
    return frame[frame.index >= cut]


def fetch(market: str, symbols: list[str], timeframe: str, progress=None, *,
          strict: bool = False) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """``(candles, daily)`` per symbol, both in exchange time. `progress` is
    called with (done, total) as batches land, across both downloads.

    A scan is lenient: a failed batch costs its own tickers. ``strict`` (one
    chart) raises instead, so an outage is reported as one rather than as a
    ticker with no candles."""
    interval, period = FETCH[timeframe]
    steps = len(symbols) * (1 if timeframe == "1d" else 2)
    daily_raw = _batches(symbols, market, *DAILY, progress=progress, total=steps,
                         strict=strict)
    daily = {s: local(f, market, intraday=False) for s, f in daily_raw.items()}
    if timeframe == "1d":
        return dict(daily), daily
    raw = _batches(symbols, market, interval, period, progress=progress,
                   done=len(symbols), total=steps, strict=strict)
    candles = {}
    for sym, frame in raw.items():
        frame = local(frame, market, intraday=True)
        candles[sym] = four_hour(frame, market) if timeframe == "4h" else frame
    return candles, daily
