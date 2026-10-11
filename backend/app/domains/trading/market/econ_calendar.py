"""News & Events: the US economic calendar that moves markets.

Read from the Apify actor ``bigdavidson/us-economic-calendar``, which builds
the calendar from the agencies' own schedules -- BLS (CPI, PPI, jobs, JOLTS),
BEA (GDP, PCE, trade), Census (retail sales, housing), DOL (jobless claims),
the Fed (FOMC decisions, minutes, Beige Book) and Treasury (auctions) -- with
release times in ET and UTC, importance, status, and actual / previous values
once released.

WHEN
Daily at 08:15 CT on weekdays, before the open, and on demand from the desk's
refresh. One calendar for the whole desk: it is the same for every operator,
so it is fetched once and stored in var/econ_calendar.json, not per tenant.

WHAT IT COSTS
The actor bills per run ($0.005) and per calendar row ($0.002): the window
here -- yesterday through two weeks ahead, medium and high importance -- is
typically 8-20 rows, a few cents. A refresh while one is running is refused,
not queued, so a double-click is one run.

THE KEY
APIFY_API_KEY, from the environment or the first customer folder's .env that
has one (customers/<name>/.env). It is sent to api.apify.com and nowhere else,
and never logged or returned.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ACTOR = "bigdavidson~us-economic-calendar"
RUN_URL = f"https://api.apify.com/v2/acts/{ACTOR}/run-sync-get-dataset-items"
INPUT = {"dateFrom": "-1d", "dateTo": "+14d", "importance": "medium",
         "includeActuals": True}
CT = ZoneInfo("America/Chicago")
DAILY_AT = time(8, 15)
POLL_S = 300
RUN_TIMEOUT_S = 180

_lock = threading.Lock()


class CalendarUnavailable(RuntimeError):
    """The calendar could not be fetched; the reason is safe to show."""


class RefreshBusy(RuntimeError):
    pass


def _path():
    from app.core.config import get_settings

    return get_settings().var_dir / "econ_calendar.json"


def _api_key() -> str | None:
    key = os.environ.get("APIFY_API_KEY") or os.environ.get("TBOT_APIFY_API_KEY")
    if key:
        return key.strip()
    from dotenv import dotenv_values

    from app.core.config import get_settings

    root = get_settings().customers_root
    try:
        folders = sorted(p for p in root.iterdir() if p.is_dir())
    except OSError:
        return None
    for folder in folders:
        env = folder / ".env"
        if env.is_file():
            value = (dotenv_values(env).get("APIFY_API_KEY") or "").strip()
            if value:
                return value
    return None


def _row(item: dict) -> dict:
    keep = ("id", "event", "event_key", "category", "agency", "release_name", "period",
            "release_date_et", "release_time_et", "release_datetime_et",
            "release_datetime_utc", "importance", "status", "date_confirmed", "actual",
            "previous", "unit", "actual_vintage", "actual_series", "actual_note",
            "source_url", "notes")
    row = {k: item.get(k) for k in keep}
    # When it lands on the desk's own clock.
    when = item.get("release_datetime_utc") or item.get("release_datetime_et")
    try:
        row["release_ct"] = datetime.fromisoformat(str(when).replace("Z", "+00:00")) \
            .astimezone(CT).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        row["release_ct"] = None
    return row


def refresh(trigger: str = "on demand") -> dict:
    """Run the actor now and store what it returns. Raises CalendarUnavailable
    with a reason fit for the screen, or RefreshBusy if a run is underway."""
    import requests

    if not _lock.acquire(blocking=False):
        raise RefreshBusy("the calendar is already being fetched")
    try:
        key = _api_key()
        if not key:
            raise CalendarUnavailable("no APIFY_API_KEY found in the environment or a customer .env")
        try:
            r = requests.post(RUN_URL, params={"token": key, "timeout": RUN_TIMEOUT_S - 30},
                              json=INPUT, timeout=RUN_TIMEOUT_S)
        except requests.RequestException as exc:
            raise CalendarUnavailable(f"Apify could not be reached ({type(exc).__name__})") from None
        if r.status_code >= 400:
            # The status only: an error body can echo the request, token and all.
            raise CalendarUnavailable(f"Apify answered HTTP {r.status_code}")
        try:
            items = r.json()
        except ValueError:
            raise CalendarUnavailable("Apify answered with something that is not JSON") from None
        if not isinstance(items, list):
            raise CalendarUnavailable("Apify answered without a list of calendar rows")
        events = [_row(i) for i in items if i.get("row_type") != "notice"]
        events.sort(key=lambda e: e.get("release_datetime_utc") or "")
        notices = [i.get("notes") for i in items if i.get("row_type") == "notice" and i.get("notes")]
        now = datetime.now(timezone.utc)
        snap = {"fetched_at": now.isoformat(timespec="seconds"),
                "fetched_ct": now.astimezone(CT).strftime("%Y-%m-%d %H:%M"),
                "trigger": trigger, "window": dict(INPUT), "source": f"apify:{ACTOR}",
                "events": events, "notices": notices}
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snap, indent=1), encoding="utf-8")
        tmp.replace(path)
        logger.info("econ calendar: %d events (%s)", len(events), trigger)
        return snap
    finally:
        _lock.release()


def snapshot() -> dict:
    """The stored calendar, or an empty one that says it has never run."""
    try:
        snap = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        snap = {"fetched_at": None, "events": [], "notices": []}
    snap["refreshing"] = _lock.locked()
    snap["daily_at_ct"] = DAILY_AT.strftime("%H:%M")
    return snap


def sweep(now: datetime | None = None) -> bool:
    """The 08:15 CT weekday run: once a day, on the first pass at or after
    08:15 -- so a server started at 09:00 still fetches that morning."""
    now = (now or datetime.now(timezone.utc)).astimezone(CT)
    if now.weekday() >= 5 or now.time() < DAILY_AT:
        return False
    last = snapshot().get("fetched_ct") or ""
    if last.startswith(now.date().isoformat()) and last[11:16] >= DAILY_AT.strftime("%H:%M"):
        return False
    try:
        refresh(trigger=f"daily {DAILY_AT:%H:%M} CT")
        return True
    except (CalendarUnavailable, RefreshBusy) as exc:
        logger.warning("econ calendar daily run: %s", exc)
        return False
