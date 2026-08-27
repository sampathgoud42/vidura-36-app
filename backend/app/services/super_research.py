"""super_research service: state assembly, supervisor control, GEX/econ.

This ports the vite-middleware contract (web-app-main/vite.config.js) that
the SuperSite frontend already speaks, byte-compatible:

- every CSV-derived value stays a STRING (the frontend does exact string
  compares like ``hot === '1'`` and Number() coercion itself);
- econ/gex are BOM-tolerant verbatim file passthroughs, null when missing;
- worker rows: last 40 CSV lines, newest first, capped at 30, only for
  enabled tickers;
- central feeds: sorted DESC on ``logged_at_cst|bar_time_cst``, capped 150
  (2000 with all=1, which also merges the archive ledgers).

GEX safety: the flashAlpha key is FREE tier (5 requests/day; the 09:00
schtask uses 2). This module NEVER calls the flashAlpha API — it only reads
the JSON files the scheduled job produces.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:  # psutil is local-runtime only (process control); absent in cloud images
    import psutil
except ImportError:  # pragma: no cover - exercised by the cloud image
    psutil = None
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import DailySnapshot, SuperSignal

logger = logging.getLogger(__name__)

_CST = ZoneInfo("America/Chicago")

CATEGORY_SEQUENCE = ("etf", "stock", "crypto")

# Own spawned supervisors: category -> Popen. Machine-wide detection below
# also finds supervisors started by bots.py / schtask / vite.
_CHILDREN: dict[str, subprocess.Popen] = {}

# Cached machine-wide supervisor scan. The TTL exceeds the desk's 8s poll so
# a steady stream of clients cannot turn every request into a process walk.
_SCAN_TTL = 20.0
_SCAN_CACHE: dict = {"ts": 0.0, "running": {}}
_SCAN_LOCK = threading.Lock()

# Short cache of the assembled desk state: every open tab polls /super/state
# every 8s and they can all share one assembly.
_STATE_TTL = 4.0
_STATE_CACHE: dict = {"ts": 0.0, "key": None, "value": None}
_STATE_LOCK = threading.Lock()

# Sync endpoints run on the threadpool; serialize scan-then-spawn and the
# select-then-insert sync passes so concurrent requests cannot double-spawn
# supervisors or race the unique indexes.
_ON_LOCK = threading.Lock()
_SYNC_LOCK = threading.Lock()

# (mtime, size) per ingested file so the background loop skips unchanged
# files instead of re-upserting thousands of rows every minute.
_FILE_STATE: dict[str, tuple[float, int]] = {}

# Telemetry for the background loop, served by GET /super/sync/status.
AUTO_SYNC_STATUS: dict = {
    "enabled": False,
    "interval_s": None,
    "runs": 0,
    "errors": 0,
    "last_run_at": None,
    "last_error": None,
    "last_result": None,
}


def _file_changed(path: Path, *, force: bool) -> bool:
    """True if the file should be (re)ingested; records the new state."""
    try:
        stat = path.stat()
    except OSError:
        return False
    state = (stat.st_mtime, stat.st_size)
    if not force and _FILE_STATE.get(str(path)) == state:
        return False
    _FILE_STATE[str(path)] = state
    return True


# --- config file -----------------------------------------------------------

def config_path() -> Path:
    return get_settings().super_dir / "super_research.config"


def read_config() -> dict:
    raw = config_path().read_text(encoding="utf-8")
    return json.loads(raw.lstrip("﻿"))


def write_enabled(db: Session, enabled: dict[str, bool]) -> dict:
    """Apply {tickerId: bool} across all categories, preserving every other
    key. The DB mirror is the serving source; the file is also rewritten
    when the source repo is present because the supervisor bots read it."""
    cfg = config_from_db(db)
    if cfg is None:
        raise ValueError("no super_config in the database and no source repo to import it from")
    for cat in (cfg.get("categories") or {}).values():
        for t in cat.get("tickers") or []:
            if t.get("id") in enabled:
                t["enabled"] = bool(enabled[t["id"]])
    _upsert_singleton(db, "super_config", cfg, "api:setSuperConfig")
    db.commit()
    try:
        if config_path().parent.is_dir():
            # Byte-compatible with vite's JSON.stringify(cfg, null, 2) + '\n':
            # literal UTF-8 escapes-free text and LF endings even on Windows.
            config_path().write_text(
                json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
    except OSError as exc:
        logger.warning("config mirror updated but file write failed: %s", exc)
    invalidate_caches()  # next state must reflect the new toggles
    return cfg


def invalidate_caches() -> None:
    _SCAN_CACHE["ts"] = 0.0
    _STATE_CACHE.update(ts=0.0, key=None, value=None)


# --- file readers (string-preserving) --------------------------------------

def _read_csv_rows(path: Path) -> list[dict]:
    """DictReader keeps every value a string — required by the frontend."""
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            return [
                {k: (v if isinstance(v, str) else "") for k, v in row.items() if k}
                for row in csv.DictReader(fh)
            ]
    except OSError:
        return []


def read_worker_rows(path: Path, *, tail: int = 40, cap: int = 30) -> list[dict]:
    rows = _read_csv_rows(path)
    return list(reversed(rows[-tail:]))[:cap]


_EPOCH = datetime(1970, 1, 1)


def signal_sort_key(row: dict) -> tuple:
    """When a signal happened, as a real instant — for ordering ONLY.

    Every engine writes wall-clock into columns named ``*_cst``, but the India
    engine's clock is IST. Sorting those strings lexically put an 11:45 IST bar
    (01:15 CDT) above a genuinely newer 09:00 CDT one, because "11:45" > "09:00"
    as text. Normalise to UTC before comparing; the row itself is untouched, so
    the UI still shows each engine's own clock and label.
    """
    category = row.get("category")
    logged = _parse_cst((row.get("logged_at_cst") or "").strip(), category)
    bar = _parse_cst((row.get("bar_time_cst") or "").strip(), category)
    return (logged or bar or _EPOCH, bar or logged or _EPOCH)


def read_central_feed(name: str, *, want_all: bool = False) -> list[dict]:
    super_dir = get_settings().super_dir
    rows = _read_csv_rows(super_dir / name)
    if want_all:
        rows += _read_csv_rows(super_dir / "archive" / name)
    rows.sort(key=signal_sort_key, reverse=True)
    return rows[: 2000 if want_all else 150]


def read_json_file(path: Path) -> dict | None:
    """BOM-tolerant JSON passthrough; None when missing/unparsable —
    the frontend treats null as 'not built yet'."""
    try:
        return json.loads(path.read_text(encoding="utf-8").lstrip("﻿"))
    except (OSError, json.JSONDecodeError):
        return None


def read_gex() -> dict | None:
    return read_json_file(get_settings().super_dir / "gex_daily.json")


def read_econ() -> dict | None:
    return read_json_file(get_settings().super_dir / "econ_today.json")


# --- supervisor liveness / control -----------------------------------------

def iter_python_processes():
    """Yield (proc, cmdline_list) for python processes only.

    Critical for performance on Windows: ``process_iter(['cmdline'])`` reads
    the command line of EVERY process (~8s for 300+ processes on this
    machine). Fetching names first and reading cmdline only for the handful
    of python processes is ~140x faster (~0.06s).
    """
    if psutil is None:
        return
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if not name.startswith("python"):
                continue
            cmdline = proc.cmdline()
        except psutil.Error:
            continue
        yield proc, cmdline


def _scan_running(force: bool = False) -> dict[str, int]:
    """category -> pid for any python running super_signal_bot.py, however
    it was started (bots.py, schtask, vite, or us).

    Single-flight + TTL cached: concurrent /super/state requests (the desk
    polls every 8s, and every open tab polls) must never each start their
    own scan.
    """
    now = time.monotonic()
    if not force and now - _SCAN_CACHE["ts"] < _SCAN_TTL:
        return _SCAN_CACHE["running"]
    with _SCAN_LOCK:
        # Another thread may have refreshed while we waited for the lock.
        now = time.monotonic()
        if not force and now - _SCAN_CACHE["ts"] < _SCAN_TTL:
            return _SCAN_CACHE["running"]
        running: dict[str, int] = {}
        for proc, cmdline in iter_python_processes():
            if "super_signal_bot.py" not in " ".join(cmdline):
                continue
            for i, arg in enumerate(cmdline):
                if arg == "--category" and i + 1 < len(cmdline):
                    running.setdefault(cmdline[i + 1], proc.info["pid"])
        _SCAN_CACHE.update(ts=time.monotonic(), running=running)
        return running


def _category_liveness(key: str, running: dict[str, int]) -> tuple[bool, int | None]:
    child = _CHILDREN.get(key)
    if child is not None and child.poll() is None:
        return True, running.get(key, child.pid)
    if key in running:
        return True, running[key]
    return False, None


def start_supervisors() -> dict:
    """POST /super/on: for each category with >=1 enabled ticker and no live
    supervisor, spawn one detached (bots.py-style, so it survives an API
    restart). Categories with zero enabled tickers are skipped; a category
    that fails to spawn is reported without aborting the rest (vite parity)."""
    settings = get_settings()
    try:
        cfg = read_config()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise OSError(
            f"supervisors need the source repo on this host (config unreadable: {exc})"
        ) from exc
    started: list[str] = []
    already: list[str] = []
    failed: dict[str, str] = {}
    with _ON_LOCK:
        running = _scan_running(force=True)
        for key, cat in (cfg.get("categories") or {}).items():
            if not any(t.get("enabled") for t in cat.get("tickers") or []):
                continue
            live, _pid = _category_liveness(key, running)
            if live:
                already.append(key)
                continue
            try:
                python = str(settings.super_python)
                if not Path(python).is_file():
                    python = sys.executable
                bot = settings.super_dir / (cat.get("bot") or "super_signal_bot.py")
                if not bot.is_file():
                    raise OSError(f"bot script missing: {bot}")
                out = settings.super_dir / f"super_{key}.out"
                creationflags = 0
                if os.name == "nt":
                    DETACHED_PROCESS = 0x00000008
                    creationflags = DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                with open(out, "a", encoding="utf-8", errors="replace") as log_handle:
                    proc = subprocess.Popen(
                        [python, str(bot), "--category", key, "--poll", "60"],
                        cwd=str(settings.super_dir),
                        stdout=log_handle,
                        stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL,
                        close_fds=True,
                        creationflags=creationflags,
                    )
                _CHILDREN[key] = proc
                started.append(key)
                logger.info("Started super supervisor %s (pid %s)", key, proc.pid)
            except OSError as exc:
                failed[key] = str(exc)
                logger.warning("Could not start super supervisor %s: %s", key, exc)
        invalidate_caches()
    result = {"started": started, "already": already, "sequence": started + already}
    if failed:
        result["failed"] = failed
    return result


REGEN_RECENT_HOURS = 24


def last_regenerate(db: Session) -> datetime | None:
    """When the engines were last regenerated through this API (naive UTC)."""
    row = db.scalar(
        select(DailySnapshot)
        .where(DailySnapshot.kind == "regen")
        .order_by(DailySnapshot.fetched_at.desc())
        .limit(1)
    )
    return row.fetched_at if row else None


def _stamp_regenerate(db: Session, launched: dict) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    date = now.date().isoformat()
    row = db.scalar(
        select(DailySnapshot).where(
            DailySnapshot.kind == "regen", DailySnapshot.snapshot_date == date
        )
    )
    payload = {"at": now.isoformat(), "launched": launched}
    if row is None:
        db.add(DailySnapshot(kind="regen", snapshot_date=date, payload=payload, source_file=None))
    else:
        row.payload = payload
        row.fetched_at = now
    db.commit()


def regenerate_status(db: Session) -> dict:
    """Whether the last regenerate has finished, so a caller can wait on it.

    ``regenerate_engines`` launches one DETACHED supervisor per category and
    returns immediately, so "it was launched" is all the API knew. This checks
    the recorded PIDs against the live process table.

    Matched on cmdline, not PID alone: a bare PID check would call a recycled
    PID "still regenerating" forever, or — worse — call an unrelated process
    our own job and report success once IT exits.
    """
    row = db.scalar(
        select(DailySnapshot)
        .where(DailySnapshot.kind == "regen")
        .order_by(DailySnapshot.fetched_at.desc())
        .limit(1)
    )
    if row is None or not (row.payload or {}).get("launched"):
        return {"launched_at": None, "running": [], "finished": [], "done": True}

    launched: dict = row.payload["launched"]
    running, finished = [], []
    try:
        import psutil
    except ImportError:          # cloud image has no psutil; cannot observe
        return {"launched_at": row.payload.get("at"), "running": [],
                "finished": list(launched), "done": True, "observable": False}

    for cat, pid in launched.items():
        alive = False
        try:
            proc = psutil.Process(int(pid))
            cmd = " ".join(proc.cmdline())
            alive = "super_signal_bot.py" in cmd and f"--category {cat}" in cmd
        except (psutil.Error, ValueError, TypeError):
            alive = False
        (running if alive else finished).append(cat)

    return {
        "launched_at": row.payload.get("at"),
        "running": running,
        "finished": finished,
        "done": not running,
        "observable": True,
    }


def regenerate_engines(
    categories: list[str] | None = None, *, db: Session | None = None, force: bool = False
) -> dict:
    """Kick one detached ``--once --backfill-today`` pass per category: every
    worker re-emits today's signals and the supervisor aggregates them into
    the central ledgers. The API's auto-sync loop then stores the results in
    SQLite. Returns the spawned pids; progress is visible via /super/state
    and /super/sync/status.

    If the last regenerate through this API was under 24h ago and ``force``
    is not set, nothing is launched — the caller gets ``recent: true`` so the
    UI can confirm ("signals are fresh — go straight to the watcher?")."""
    settings = get_settings()
    if not settings.super_dir.is_dir():
        raise OSError("engine regeneration needs the source repo on this host")
    if db is not None and not force:
        last = last_regenerate(db)
        if last is not None:
            age_h = (datetime.now(timezone.utc).replace(tzinfo=None) - last).total_seconds() / 3600
            if age_h < REGEN_RECENT_HOURS:
                return {
                    "recent": True,
                    "last_regenerate_at": last.isoformat(),
                    "hours_ago": round(age_h, 1),
                    "launched": {},
                    "skipped": {},
                }
    cfg = read_config()
    launched: dict[str, int] = {}
    skipped: dict[str, str] = {}
    with _ON_LOCK:
        for key, cat in (cfg.get("categories") or {}).items():
            if categories and key not in categories:
                continue
            if not any(t.get("enabled") for t in cat.get("tickers") or []):
                skipped[key] = "no enabled tickers"
                continue
            try:
                python = str(settings.super_python)
                if not Path(python).is_file():
                    python = sys.executable
                bot = settings.super_dir / (cat.get("bot") or "super_signal_bot.py")
                if not bot.is_file():
                    raise OSError(f"bot script missing: {bot}")
                out = settings.super_dir / f"super_{key}_regen.out"
                creationflags = 0
                if os.name == "nt":
                    DETACHED_PROCESS = 0x00000008
                    creationflags = DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                with open(out, "a", encoding="utf-8", errors="replace") as log_handle:
                    proc = subprocess.Popen(
                        [python, str(bot), "--category", key, "--once", "--backfill-today"],
                        cwd=str(settings.super_dir),
                        stdout=log_handle,
                        stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL,
                        close_fds=True,
                        creationflags=creationflags,
                    )
                launched[key] = proc.pid
            except OSError as exc:
                skipped[key] = str(exc)
    if db is not None and launched:
        _stamp_regenerate(db, launched)
    return {"launched": launched, "skipped": skipped}


def stop_supervisors(category: str | None = None) -> dict:
    """Stop supervisors by cmdline match, mirroring `python bots.py stop`:
    matches super_signal_bot.py AND stray _intraday_bot.py workers (full
    stop only), and kills each supervisor's child tree so in-flight workers
    do not linger past their parent."""
    victims: list[psutil.Process] = []
    seen: set[int] = set()
    for proc, cmdline in iter_python_processes():
        joined = " ".join(cmdline)
        is_supervisor = "super_signal_bot.py" in joined
        is_worker = "_intraday_bot.py" in joined
        if not is_supervisor and not (is_worker and category is None):
            continue
        if is_supervisor and category is not None:
            cat = None
            for i, arg in enumerate(cmdline):
                if arg == "--category" and i + 1 < len(cmdline):
                    cat = cmdline[i + 1]
            if cat != category:
                continue
        if proc.pid in seen:
            continue
        seen.add(proc.pid)
        victims.append(proc)
        if is_supervisor:
            try:
                for child in proc.children(recursive=True):
                    if child.pid not in seen:
                        seen.add(child.pid)
                        victims.append(child)
            except psutil.Error:
                pass
    stopped: list[dict] = []
    for proc in victims:
        try:
            cmd = " ".join(proc.cmdline())[-120:]
            proc.terminate()
            stopped.append({"pid": proc.pid, "cmdline": cmd})
        except psutil.Error:
            continue
    if victims:
        _, alive = psutil.wait_procs(victims, timeout=5)
        for p in alive:
            try:
                p.kill()
            except psutil.Error:
                pass
    if category is None:
        _CHILDREN.clear()
    else:
        _CHILDREN.pop(category, None)
    invalidate_caches()
    return {"stopped": stopped}


def _safe_proc(pid: int) -> psutil.Process | None:
    try:
        return psutil.Process(pid)
    except psutil.Error:
        return None


# --- state assembly ---------------------------------------------------------

def build_state(db: Session, *, want_all: bool = False) -> dict:
    """Assemble the desk state — served entirely from SQLite (config mirror,
    signal rows, gex/econ snapshots) so the source repo is not required at
    request time. Shared across concurrent pollers via a short TTL cache."""
    now = time.monotonic()
    if _STATE_CACHE["key"] == want_all and now - _STATE_CACHE["ts"] < _STATE_TTL:
        return _STATE_CACHE["value"]
    with _STATE_LOCK:
        now = time.monotonic()
        if _STATE_CACHE["key"] == want_all and now - _STATE_CACHE["ts"] < _STATE_TTL:
            return _STATE_CACHE["value"]
        value = _build_state_uncached(db, want_all=want_all)
        _STATE_CACHE.update(ts=time.monotonic(), key=want_all, value=value)
        return value


def _feed_from_db(db: Session, book: str, *, want_all: bool) -> list[dict]:
    """Central A/B feed served from super_signals rows (raw preserves the
    all-string CSV contract). Archived rows appear only with all=1."""
    stmt = (
        select(SuperSignal)
        .where(SuperSignal.book == book, SuperSignal.external_id.like("central:%"))
        .order_by(SuperSignal.logged_at.desc().nullslast())
        .limit(2000 if want_all else 150)
    )
    if not want_all:
        stmt = stmt.where(SuperSignal.archived.is_(False))
    rows = [dict(s.raw or {}) for s in db.scalars(stmt).all()]
    # Newest first by real instant, not by wall-clock text — the India engine
    # writes IST into the *_cst columns (see signal_sort_key).
    rows.sort(key=signal_sort_key, reverse=True)
    return rows


def _worker_rows_from_db(db: Session, ticker_id: str, *, cap: int = 30) -> list[dict]:
    stmt = (
        select(SuperSignal)
        .where(SuperSignal.external_id.like(f"worker:{ticker_id}:%"))
        .order_by(SuperSignal.logged_at.desc().nullslast())
        .limit(cap)
    )
    return [dict(s.raw or {}) for s in db.scalars(stmt).all()]


def _build_state_uncached(db: Session, *, want_all: bool = False) -> dict:
    cfg = latest_payload(db, "super_config")
    if cfg is None:
        _bridge_once(db)
        cfg = latest_payload(db, "super_config")
    if cfg is None:
        return {
            "error": "config unreadable: no super_config mirror in the database "
            "(run POST /super/sync once while the source repo is present)"
        }

    running = _scan_running()
    categories = []
    abook: list[dict] = []
    for key, cat in (cfg.get("categories") or {}).items():
        live, pid = _category_liveness(key, running)
        tickers = []
        for t in cat.get("tickers") or []:
            enabled = bool(t.get("enabled"))
            rows: list[dict] = []
            if enabled:
                rows = _worker_rows_from_db(db, t.get("id") or "")
                for row in rows:
                    if row.get("book") == "A":
                        abook.append({**row, "src": t.get("label"), "cat": key})
            tickers.append(
                {
                    "id": t.get("id"),
                    "label": t.get("label"),
                    "rules": t.get("rules"),
                    "img": t.get("img"),
                    "enabled": enabled,
                    "live": live and enabled,
                    "rows": rows,
                }
            )
        categories.append(
            {
                "key": key,
                "label": cat.get("label"),
                "session": cat.get("session") or "rth",
                "live": live,
                "pid": pid,
                "tickers": tickers,
            }
        )
    # newest first ACROSS categories: an IST bar time is not comparable to a
    # CST one as text, so compare the UTC instants instead
    abook.sort(key=signal_sort_key, reverse=True)

    return {
        "abookOnTop": cfg.get("abookOnTop") is not False,
        "categories": categories,
        "abook": abook,
        "aFeed": _feed_from_db(db, "A", want_all=want_all),
        "bFeed": _feed_from_db(db, "B", want_all=want_all),
        "econ": econ_from_db(db),
        "gex": gex_from_db(db),
    }


def gex_from_db(db: Session) -> dict | None:
    payload = latest_payload(db, "gex")
    if payload is None:
        _bridge_once(db)
        payload = latest_payload(db, "gex")
    return payload


def econ_from_db(db: Session) -> dict | None:
    payload = latest_payload(db, "econ")
    if payload is None:
        _bridge_once(db)
        payload = latest_payload(db, "econ")
    return payload


def config_from_db(db: Session) -> dict | None:
    cfg = latest_payload(db, "super_config")
    if cfg is None:
        _bridge_once(db)
        cfg = latest_payload(db, "super_config")
    return cfg


# --- SQLite history: signals + daily snapshots ------------------------------

# The engines all write wall-clock into columns named ``*_cst``, but the India
# engine's clock is IST, not Central: a BANKNIFTY row carries
# stop_deadline_cst=15:30, which is the NSE close (15:30 IST), and its bar
# times sit inside 09:15-15:30 IST. Parsing those as Central shifted every
# India signal ~10.5h into the future, so they sorted above genuinely newer US
# signals in the "past 24h, latest first" A-book — an 01:15 CDT Indian bar
# appearing above a 09:00 CDT US one.
_IST = ZoneInfo("Asia/Kolkata")
_CATEGORY_TZ = {"india": _IST}


def signal_tz(category: str | None):
    """Wall-clock zone the engine for ``category`` writes in."""
    return _CATEGORY_TZ.get((category or "").strip().lower(), _CST)


def _parse_cst(value: str, category: str | None = None) -> datetime | None:
    """Parse an engine wall-clock string to naive UTC.

    ``category`` selects the source zone; omitting it keeps the historical
    Central assumption, which is correct for every non-India engine.
    """
    tz = signal_tz(category)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            aware = datetime.strptime(value.strip(), fmt).replace(tzinfo=tz)
            return aware.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            continue
    return None


def _float_or_none(value) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def sync_signals(db: Session, *, include_archive: bool = True, force: bool = True) -> dict:
    """Ingest central A/B ledgers (+ archive) into the super_signals table.

    Ledger rows are updated in place when outcomes resolve, so this upserts
    on a stable external_id and refreshes outcome-bearing fields. With
    ``force=False`` files whose mtime+size are unchanged are skipped.
    """
    settings = get_settings()
    files = [
        (settings.super_dir / "a_signals.csv", "A"),
        (settings.super_dir / "b_signals.csv", "B"),
    ]
    if include_archive:
        files += [
            (settings.super_dir / "archive" / "a_signals.csv", "A"),
            (settings.super_dir / "archive" / "b_signals.csv", "B"),
        ]
    inserted = updated = 0
    report: dict[str, dict] = {}
    for path, book in files:
        if not path.is_file() or not _file_changed(path, force=force):
            continue
        is_archive = path.parent.name == "archive"
        rows = _read_csv_rows(path)
        file_ins = file_upd = 0
        # Pre-merge duplicate keys within the file (last row wins): the
        # ledgers can carry two rows for the same second+ticker+signal, and
        # the session is autoflush=False so a same-key SELECT would not see
        # a pending insert from an earlier row.
        merged: dict[str, dict] = {}
        for row in rows:
            ticker = (row.get("ticker") or "").strip()
            logged = (row.get("logged_at_cst") or "").strip()
            if not ticker or not logged:
                continue
            # bar_time_cst is part of the identity: two DISTINCT signals for
            # the same ticker+signal can flush in the same second when they
            # come from different bars (real occurrence in b_signals.csv).
            external_id = (
                f"central:{book}:{logged}:{ticker}:"
                f"{(row.get('bar_time_cst') or '').strip()}:"
                f"{(row.get('signal') or '')[:100]}"
            )
            merged[external_id] = row
        for external_id, row in merged.items():
            ticker = (row.get("ticker") or "").strip()
            logged = (row.get("logged_at_cst") or "").strip()
            mapped = {
                "book": book,
                "category": (row.get("category") or "").strip() or None,
                "ticker": ticker,
                "direction": (row.get("direction") or "").strip() or None,
                "grade": (row.get("eng_hot") or "").strip() or None,
                "combo": (row.get("signal") or "").strip() or None,
                "price": _float_or_none(row.get("signal_price")),
                "accuracy_pct": _float_or_none(row.get("acc_strict_pct")),
                "bar_time": (row.get("bar_time_cst") or "").strip() or None,
                "logged_at": _parse_cst(logged, row.get("category")),
                "archived": is_archive,
                "raw": {k: v for k, v in row.items() if k},
            }
            existing = db.scalar(
                select(SuperSignal).where(SuperSignal.external_id == external_id)
            )
            if existing is None:
                db.add(SuperSignal(external_id=external_id, **mapped))
                file_ins += 1
            else:
                # outcome/outcome_at/repeats/hot live in raw and resolve later;
                # a row seen in the archive file has rotated out of the live feed
                changed = existing.raw != mapped["raw"]
                if is_archive and not existing.archived:
                    existing.archived = True
                    changed = True
                if changed:
                    existing.raw = mapped["raw"]
                    file_upd += 1
        db.commit()
        inserted += file_ins
        updated += file_upd
        report[str(path)] = {"rows": len(rows), "inserted": file_ins, "updated": file_upd}
    return {"inserted": inserted, "updated": updated, "files": report}


def sync_worker_signals(db: Session, *, force: bool = True) -> dict:
    """Ingest every per-ticker worker CSV (the raw engine signals) so ALL
    signals the service generates are stored, not just the merged central
    ledgers. Worker CSVs are append-only, so this pass is insert-only with
    a preloaded id set — cheap enough to run every minute.
    """
    settings = get_settings()
    try:
        cfg = read_config()
    except (OSError, ValueError, json.JSONDecodeError):
        return {"inserted": 0, "files": {}, "error": "config unreadable"}
    inserted = 0
    report: dict[str, dict] = {}
    for cat_key, cat in (cfg.get("categories") or {}).items():
        for t in cat.get("tickers") or []:
            tid = t.get("id") or ""
            path = settings.super_dir / (t.get("path") or "") / (t.get("csv") or "")
            if not tid or not path.is_file() or not _file_changed(path, force=force):
                continue
            rows = _read_csv_rows(path)
            existing_ids = set(
                db.scalars(
                    select(SuperSignal.external_id).where(
                        SuperSignal.external_id.like(f"worker:{tid}:%")
                    )
                ).all()
            )
            file_ins = 0
            for row in rows:
                logged = (row.get("logged_at_cst") or "").strip()
                if not logged:
                    continue
                # engine/tf are absent in the legacy BTC worker header — the
                # empty strings still yield a stable, unique identity.
                external_id = (
                    f"worker:{tid}:{logged}:{(row.get('bar_time_cst') or '').strip()}:"
                    f"{(row.get('engine') or '').strip()}:{(row.get('tf') or '').strip()}:"
                    f"{(row.get('signal') or '')[:80]}"
                )
                if external_id in existing_ids:
                    continue
                existing_ids.add(external_id)
                db.add(
                    SuperSignal(
                        external_id=external_id,
                        book=(row.get("book") or "").strip() or None,
                        category=cat_key,
                        ticker=(t.get("label") or tid).upper(),
                        direction=(row.get("direction") or "").strip() or None,
                        grade=None,  # grading happens at ledger level (eng_hot)
                        combo=(row.get("signal") or "").strip() or None,
                        price=_float_or_none(row.get("signal_price")),
                        accuracy_pct=_float_or_none(row.get("acc_strict_pct")),
                        bar_time=(row.get("bar_time_cst") or "").strip() or None,
                        logged_at=_parse_cst(logged, cat_key),
                        raw={k: v for k, v in row.items() if k},
                    )
                )
                file_ins += 1
            db.commit()
            inserted += file_ins
            report[str(path)] = {"rows": len(rows), "inserted": file_ins}
    return {"inserted": inserted, "files": report}


def sync_config_mirror(db: Session) -> int:
    """Mirror super_research.config into the DB so every read endpoint
    works without the runtime folder on disk."""
    count = 0
    try:
        cfg = read_config()
    except (OSError, ValueError, json.JSONDecodeError):
        cfg = None
    if cfg is not None:
        count += _upsert_singleton(db, "super_config", cfg, "super_research.config")

    db.commit()
    return count


def _upsert_singleton(db: Session, kind: str, payload: dict, source: str) -> int:
    """Non-daily mirror rows use the fixed snapshot_date 'current'."""
    row = db.scalar(
        select(DailySnapshot).where(
            DailySnapshot.kind == kind, DailySnapshot.snapshot_date == "current"
        )
    )
    if row is None:
        db.add(DailySnapshot(kind=kind, snapshot_date="current", payload=payload, source_file=source))
        return 1
    if row.payload != payload:
        row.payload = payload
        row.source_file = source
        row.fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
        return 1
    return 0


def latest_payload(db: Session, kind: str) -> dict | None:
    row = db.scalar(
        select(DailySnapshot)
        .where(DailySnapshot.kind == kind)
        .order_by(DailySnapshot.fetched_at.desc())
        .limit(1)
    )
    return row.payload if row else None


def store_payload(db: Session, kind: str, payload: dict, *, source: str | None = None) -> None:
    """Upsert today's snapshot for ``kind`` (one row per kind+date)."""
    from datetime import datetime as _dt

    date = _dt.now(_CST).strftime("%Y-%m-%d")
    row = db.scalar(
        select(DailySnapshot).where(
            DailySnapshot.kind == kind, DailySnapshot.snapshot_date == date
        )
    )
    if row is None:
        db.add(DailySnapshot(kind=kind, snapshot_date=date, payload=payload,
                             source_file=source))
    else:
        row.payload = payload
        row.source_file = source
        row.fetched_at = _dt.now(timezone.utc).replace(tzinfo=None)
    db.commit()


def sync_everything(db: Session, *, include_archive: bool = True, force: bool = True) -> dict:
    """One pass over every signal source: central ledgers, worker CSVs,
    gex/econ snapshots, config mirrors. Callers must hold no session-level
    locks; this serializes on _SYNC_LOCK itself."""
    with _SYNC_LOCK:
        result = {
            "signals": sync_signals(db, include_archive=include_archive, force=force),
            "workers": sync_worker_signals(db, force=force),
            "snapshots": sync_snapshots(db),
            "mirrors": sync_config_mirror(db),
        }
    invalidate_caches()
    return result


def _bridge_once(db: Session) -> None:
    """Lazy ingest bridge: when the DB has no mirror yet but the source repo
    is present, pull everything in before serving. Harmless no-op when the
    repo is gone — that is the fully-detached mode."""
    if get_settings().super_dir.is_dir():
        try:
            sync_everything(db, force=False)
        except Exception:  # serving must not die on a broken bridge
            logger.exception("ingest bridge failed")


def sync_snapshots(db: Session) -> dict:
    """Upsert today's gex/econ JSON plus the per-day raw GEX archive into
    daily_snapshots (local file reads only — never touches flashAlpha)."""
    settings = get_settings()
    count = 0

    def upsert(kind: str, date: str, payload: dict, source: str) -> None:
        nonlocal count
        row = db.scalar(
            select(DailySnapshot).where(
                DailySnapshot.kind == kind, DailySnapshot.snapshot_date == date
            )
        )
        if row is None:
            db.add(
                DailySnapshot(
                    kind=kind, snapshot_date=date, payload=payload, source_file=source
                )
            )
            count += 1
        elif row.payload != payload:
            row.payload = payload
            row.source_file = source
            count += 1

    gex = read_gex()
    if gex and gex.get("fetched_at"):
        upsert("gex", str(gex["fetched_at"])[:10], gex, "gex_daily.json")
    econ = read_econ()
    if econ and econ.get("date"):
        upsert("econ", str(econ["date"]), econ, "econ_today.json")
    gex_dir = settings.super_dir / "gex"
    if gex_dir.is_dir():
        for f in sorted(gex_dir.glob("*.json")):
            # files are named <YYYY-MM-DD>_<ticker>.json
            stem_parts = f.stem.split("_", 1)
            if len(stem_parts) != 2:
                continue
            date, ticker = stem_parts
            payload = read_json_file(f)
            if payload is not None:
                upsert(f"gex_raw_{ticker}", date, payload, f.name)
    db.commit()
    return {"upserted": count}


def query_signals(
    db: Session,
    *,
    book: str | None = None,
    category: str | None = None,
    ticker: str | None = None,
    grade_min: int | None = None,
    days: int | None = None,
    central: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[SuperSignal]]:
    from datetime import timedelta

    from sqlalchemy import func

    stmt = select(SuperSignal)
    if central:
        # only the merged A/B ledger rows — the per-engine worker rows would
        # show every signal 2-4 times (once per confirming horizon)
        stmt = stmt.where(SuperSignal.external_id.like("central:%"))
    if book:
        stmt = stmt.where(SuperSignal.book == book.upper())
    if category:
        stmt = stmt.where(SuperSignal.category == category)
    if ticker:
        stmt = stmt.where(SuperSignal.ticker == ticker.upper())
    if grade_min is not None:
        stmt = stmt.where(SuperSignal.grade.in_([str(g) for g in range(grade_min, 9)]))
    if days:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        stmt = stmt.where(SuperSignal.logged_at >= cutoff)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(SuperSignal.logged_at.desc().nullslast()).limit(limit).offset(offset)
    return total, list(db.scalars(stmt).all())
