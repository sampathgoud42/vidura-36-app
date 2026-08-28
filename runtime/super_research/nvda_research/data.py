"""Data layer — pluggable connectors returning 5-minute NVDA bars in CST.

The backtest uses YFinanceConnector (free, ~60 days of 5m history, includes
extended hours for the pre-market levels). A RobinhoodConnector stub with the
same interface is provided for the live environment — swap it in without
touching the research code.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

import config as C

CACHE = Path(__file__).resolve().parent / "cache"
CACHE.mkdir(exist_ok=True)


class YFinanceConnector:
    """5m bars incl. extended hours; cached to disk per day so iterative
    research runs don't hammer the API."""

    def fetch(self, force: bool = False) -> pd.DataFrame:
        cache = CACHE / f"{C.TICKER}_5m.parquet"
        if cache.exists() and not force:
            df = pd.read_parquet(cache)
            # refresh if the cache is older than the last completed session
            if (pd.Timestamp.now(tz=C.TZ) - df.index[-1]) < pd.Timedelta(hours=12):
                return df
        import yfinance as yf
        raw = yf.download(C.TICKER, interval="5m", period="60d", prepost=True,
                          progress=False, auto_adjust=False)
        if raw is None or raw.empty:
            raise RuntimeError("yfinance returned no data")
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw.index = raw.index.tz_convert(C.TZ)
        df = raw[["Open", "High", "Low", "Close", "Volume"]].dropna()
        try:
            df.to_parquet(cache)
        except Exception:
            pass  # parquet engine missing -> just skip caching
        return df


class RobinhoodConnector:
    """Stub for the Robinhood environment. Implement fetch() with your
    connector's historicals call and return the same OHLCV frame (CST index).

        rh.get_stock_historicals("NVDA", interval="5minute", span="week")
    """

    def fetch(self, force: bool = False) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError(
            "wire your Robinhood connector here — must return a DataFrame with "
            "Open/High/Low/Close/Volume indexed by tz-aware CST timestamps")


def load_bars(force: bool = False) -> pd.DataFrame:
    return YFinanceConnector().fetch(force=force)
