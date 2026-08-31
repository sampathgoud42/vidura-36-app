#!/usr/bin/env python3
"""
baseball4cast_scraper.py — sports4cast.com MLB win-probability scraper.
=======================================================================
Scrapes the prediction data behind https://sports4cast.com/4casts/baseball4cast/
and writes ``baseball_data.csv`` next to this file:

    date_time,match,team1,team2,team1_pct,team2_pct
    2026-07-12 22:40,Miami Marlins vs Pittsburgh Pirates,Miami Marlins,Pittsburgh Pirates,45.1,54.9

Column semantics: team1 = AWAY, team2 = HOME (matching the Kalshi "Away vs
Home" title order used across the bots); date_time is UTC; pcts are the
site's model win probabilities (team1_pct + team2_pct = 100).

How it scrapes (no browser needed): the site page is bot-challenged, but its
predictions widget loads data via a public signing endpoint —
    GET sports4cast.com/wp-json/baseball/v1/signed-urls?files[]=fixtures
      → {"fixtures": "<signed storage.googleapis.com URL, 60s expiry>"}
    GET <signed url>  → fixtures JSON (home/away/home_win/away_win/date/time_utc)

Used by prediction_baseball_v1.predict_scalp as a BUY gate (team must have
>= BASEBALL_4CAST_MIN_PCT, default 50) and scheduled DAILY AT 8:15 AM CST by
the bots (bot_kalshi_main via the baseball adapter, bot_kalshi_sports_v2
directly).  Also runnable standalone / from Task Scheduler:

    python baseball4cast_scraper.py
"""
from __future__ import annotations

import asyncio
import csv
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

_HERE = Path(__file__).resolve().parent
CSV_PATH = Path(os.getenv("BASEBALL_4CAST_CSV", str(_HERE / "baseball_data.csv")))
SIGN_URL = "https://sports4cast.com/wp-json/baseball/v1/signed-urls"
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
_REFERER = "https://widgets.sports4cast.com/baseball/website/predictions-widget.html"
_CST = ZoneInfo("America/Chicago")

# daily scrape time (CST) — user rule 07/12: every day at 8:15 AM CST
SCRAPE_HOUR = int(os.getenv("BASEBALL_4CAST_HOUR", "8"))
SCRAPE_MINUTE = int(os.getenv("BASEBALL_4CAST_MINUTE", "15"))
# startup freshness: re-scrape at bot start if the CSV is older than this
MAX_AGE_H = float(os.getenv("BASEBALL_4CAST_MAX_AGE_H", "20"))

_CSV_COLS = ["date_time", "match", "team1", "team2", "team1_pct", "team2_pct"]


def fetch_fixtures(timeout: int = 30) -> list:
    """Fixture dicts from the sports4cast signing endpoint (raises on failure)."""
    s = requests.Session()
    s.headers.update({"User-Agent": _UA, "Referer": _REFERER})
    r = s.get(SIGN_URL, params={"files[]": "fixtures"}, timeout=timeout)
    r.raise_for_status()
    url = (r.json() or {}).get("fixtures")
    if not url:
        raise RuntimeError(f"signed-urls returned no fixtures url: {r.text[:200]}")
    d = s.get(url, timeout=timeout)
    d.raise_for_status()
    fx = d.json()
    items = fx.get("fixtures") if isinstance(fx, dict) else fx
    if not isinstance(items, list):
        raise RuntimeError(f"unexpected fixtures payload shape: {type(fx).__name__}")
    return items


def write_csv(path: Path = CSV_PATH) -> int:
    """Scrape and (re)write the CSV — one row per fixture with a model
    probability, all dates in the feed (past rows keep history harmless;
    the gate filters by date).  Returns the number of rows written."""
    items = fetch_fixtures()
    rows = []
    for it in items:
        home, away = it.get("home"), it.get("away")
        hw, aw = it.get("home_win"), it.get("away_win")
        if not home or not away or hw is None or aw is None:
            continue
        dt = f"{it.get('date', '')} {it.get('time_utc') or ''}".strip()
        rows.append({
            "date_time": dt,
            "match": f"{away} vs {home}",              # Kalshi order: Away vs Home
            "team1": away, "team2": home,
            "team1_pct": round(float(aw) * 100, 1),
            "team2_pct": round(float(hw) * 100, 1),
        })
    if not rows:
        raise RuntimeError("scrape produced 0 rows — feed empty or schema changed")
    rows.sort(key=lambda r: r["date_time"])
    tmp = path.with_suffix(".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_COLS)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)
    print(f"[4CAST] wrote {len(rows)} fixtures -> {path}  "
          f"({datetime.now(_CST):%Y-%m-%d %H:%M:%S} CST)")
    return len(rows)


# ── gate lookup (used by prediction_baseball_v1) ──────────────────────────────
_cache: dict = {"mtime": None, "rows": []}


def _load_rows(path: Path = CSV_PATH) -> list:
    """CSV rows, cached by file mtime (cheap to call every evaluation)."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []
    if _cache["mtime"] != mtime:
        try:
            with open(path, newline="", encoding="utf-8") as f:
                _cache["rows"] = list(csv.DictReader(f))
            _cache["mtime"] = mtime
        except Exception:
            return _cache["rows"]
    return _cache["rows"]


def _name_match(a: str, b: str) -> bool:
    """Loose team-name match: Kalshi short names ("New York Y", "Chicago C")
    vs the feed's full names ("New York Yankees", "Chicago Cubs")."""
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a or not b:
        return False
    return a in b or b in a


def team_pct(team_name: str, path: Path = CSV_PATH) -> "float | None":
    """
    The sports4cast win %% for ``team_name`` in TODAY'S game (today or
    tomorrow by the CST calendar — late UTC starts roll past midnight).
    None when the team has no game in the data (e.g. NPB/LMB — the feed is
    MLB-only) or the CSV is missing/stale for these dates.
    """
    rows = _load_rows(path)
    if not rows:
        return None
    today = datetime.now(_CST).date()
    ok_dates = {str(today), str(today + timedelta(days=1))}
    for r in rows:
        if str(r.get("date_time", ""))[:10] not in ok_dates:
            continue
        if _name_match(team_name, r.get("team1", "")):
            try:
                return float(r.get("team1_pct"))
            except (TypeError, ValueError):
                return None
        if _name_match(team_name, r.get("team2", "")):
            try:
                return float(r.get("team2_pct"))
            except (TypeError, ValueError):
                return None
    return None


def csv_age_hours(path: Path = CSV_PATH) -> "float | None":
    try:
        return (time.time() - path.stat().st_mtime) / 3600.0
    except OSError:
        return None


def updated_today(path: Path = CSV_PATH) -> bool:
    """True if the CSV's last-modified date is TODAY's CST calendar date —
    the launch freshness test (user 07/13): data must be scraped for the given
    day, so the first launch each day re-scrapes and later launches skip."""
    try:
        mt = datetime.fromtimestamp(path.stat().st_mtime, _CST).date()
    except OSError:
        return False
    return mt == datetime.now(_CST).date()


# ── scheduling (in-bot: every day at 8:15 AM CST) ─────────────────────────────
def seconds_until_next_scrape(now: "datetime | None" = None) -> float:
    now = now or datetime.now(_CST)
    nxt = now.replace(hour=SCRAPE_HOUR, minute=SCRAPE_MINUTE, second=0, microsecond=0)
    if nxt <= now:
        nxt += timedelta(days=1)
    return (nxt - now).total_seconds()


async def ensure_fresh(force: bool = False) -> bool:
    """Ensure baseball_data.csv holds TODAY's data (user 07/13): scrape now (in
    a thread — requests is sync) unless the CSV was already updated today (CST)
    or ``force``.  Never raises; returns True if data is usable."""
    age = csv_age_hours()
    if not force and updated_today():
        print(f"[4CAST] baseball_data.csv already scraped today "
              f"({age:.1f}h ago) — up to date, skipping scrape")
        return True
    why = ("missing" if age is None else "not from today")
    print(f"[4CAST] baseball_data.csv {why} — scraping today's fixtures …")
    try:
        await asyncio.to_thread(write_csv)
        return True
    except Exception as e:
        print(f"[4CAST] scrape failed: {e} — "
              + ("using existing (stale) CSV" if age is not None else
                 "NO data (gate will fail open per BASEBALL_4CAST_REQUIRE)"),
              file=sys.stderr)
        return age is not None


async def daily_scrape_task() -> None:
    """Background loop: scrape every day at SCRAPE_HOUR:SCRAPE_MINUTE CST."""
    while True:
        wait = seconds_until_next_scrape()
        print(f"[4CAST] next scrape in {wait / 3600:.1f}h "
              f"(daily {SCRAPE_HOUR:02d}:{SCRAPE_MINUTE:02d} CST)")
        await asyncio.sleep(wait)
        await ensure_fresh(force=True)


def main() -> None:
    write_csv()


if __name__ == "__main__":
    main()
