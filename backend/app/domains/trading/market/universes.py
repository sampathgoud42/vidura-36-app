"""Which stocks a breakout scan looks at: S&P 500 + Nasdaq-100, or the Nifty 500.

Live first. The constituent lists are fetched from where they are published --
Wikipedia's tables for the two US indices, NSE's CSV for the Nifty 500 -- at
most once a day, and the last good copy is kept under var/universes/, so a
restart without a network scans the list it scanned yesterday. With neither,
the snapshot shipped beside this module is used. Every answer says which of
the three it is, because "scanned the Nifty 500" and "scanned a list that was
the Nifty 500 last year" are different claims.

A fetched list shorter than an index plausibly is (a page layout change, a
truncated download) is refused rather than scanned: a scan of half an index
looks exactly like a quiet market.
"""

from __future__ import annotations

import io
import json
import logging
import re
import threading
import time
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

SNAPSHOT = Path(__file__).with_name("universe_snapshot.json")

SOURCES = {
    "sp500": ["https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"],
    "nasdaq100": ["https://en.wikipedia.org/wiki/Nasdaq-100"],
    "nifty500": ["https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
                 "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv"],
}
NAMES = {"sp500": "S&P 500", "nasdaq100": "Nasdaq-100", "nifty500": "Nifty 500"}
MARKET_LISTS = {"US": ("sp500", "nasdaq100"), "INDIA": ("nifty500",)}
# Fewer than this and the fetch is not believed.
MINIMUM = {"sp500": 480, "nasdaq100": 95, "nifty500": 480}
PATTERN = {
    "sp500": re.compile(r"^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$"),
    "nasdaq100": re.compile(r"^[A-Z]{1,5}(?:\.[A-Z]{1,2})?$"),
    "nifty500": re.compile(r"^[A-Z0-9][A-Z0-9&-]{0,19}$"),
}
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) vidura36-breakout-radar",
           "Accept": "text/html,text/csv,*/*"}
RETRY_S = 6 * 3600      # after a failed live fetch, how long before trying again

_MEMO: dict[str, dict] = {}
_TRIED: dict[str, float] = {}
_LOCK = threading.Lock()


def _saved_path(name: str) -> Path:
    from app.core.config import get_settings

    return Path(get_settings().var_dir) / "universes" / f"{name}.json"


def _valid(name: str, symbols) -> list[str]:
    out, pattern = [], PATTERN[name]
    for raw in symbols:
        sym = str(raw).strip().upper()
        if pattern.match(sym) and sym not in out:
            out.append(sym)
    return out


def _fetch_live(name: str) -> list[str]:
    """The published list, or an exception. The seam tests substitute."""
    import pandas as pd
    import requests

    last_error: Exception | None = None
    for url in SOURCES[name]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
            if name == "nifty500":
                symbols = pd.read_csv(io.StringIO(r.text))["Symbol"].tolist()
            else:
                symbols = []
                for table in pd.read_html(io.StringIO(r.text)):
                    column = next((c for c in table.columns
                                   if str(c).strip().lower() in ("symbol", "ticker")), None)
                    if column is not None and len(table) >= MINIMUM[name]:
                        symbols = table[column].tolist()
                        break
            found = _valid(name, symbols)
            if len(found) >= MINIMUM[name]:
                return found
            last_error = ValueError(f"{url} listed {len(found)} symbols")
        except Exception as exc:                        # noqa: BLE001
            last_error = exc
    raise last_error or ValueError("no source answered")


def _snapshot(name: str) -> dict:
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return {"symbols": list(data[name]), "source": "snapshot", "as_of": data["as_of"]}


def members(name: str) -> dict:
    """``{"symbols", "source": live|saved|snapshot, "as_of"}`` for one index."""
    today = date.today().isoformat()
    with _LOCK:
        memo = _MEMO.get(name)
        if memo and (memo["source"] == "live" and memo["as_of"] == today
                     or time.time() - _TRIED.get(name, 0.0) < RETRY_S):
            return memo

    got = None
    try:
        symbols = _fetch_live(name)
        got = {"symbols": symbols, "source": "live", "as_of": today}
        try:
            path = _saved_path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(got), encoding="utf-8")
        except OSError as exc:
            logger.info("universes: could not save %s (%s)", name, exc)
    except Exception as exc:                            # noqa: BLE001
        logger.info("universes: live %s unavailable (%s: %s)", name,
                    type(exc).__name__, exc)
        try:
            saved = json.loads(_saved_path(name).read_text(encoding="utf-8"))
            if len(saved.get("symbols") or []) >= MINIMUM[name]:
                got = {**saved, "source": "saved"}
        except (OSError, ValueError):
            pass
        got = got or _snapshot(name)

    with _LOCK:
        _MEMO[name] = got
        _TRIED[name] = time.time()
    return got


def for_market(market: str) -> dict:
    """Every symbol a market's scan covers, in index order without repeats,
    and where each list came from."""
    lists = {name: members(name) for name in MARKET_LISTS[market]}
    symbols: list[str] = []
    seen: set[str] = set()
    for got in lists.values():
        for sym in got["symbols"]:
            if sym not in seen:
                seen.add(sym)
                symbols.append(sym)
    return {
        "name": " + ".join(NAMES[n] for n in lists),
        "symbols": symbols,
        "count": len(symbols),
        "lists": {n: {"source": g["source"], "as_of": g["as_of"], "count": len(g["symbols"])}
                  for n, g in lists.items()},
    }


def reset() -> None:
    with _LOCK:
        _MEMO.clear()
        _TRIED.clear()
