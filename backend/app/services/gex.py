"""flashAlpha gamma-exposure fetcher — ported from the FlashAlphaGEX_Daily
job (super_research/gex_daily.py) into the microservice.

Same contract as the original: one `/v1/stock/{ticker}/summary` call per
ticker, the raw payload archived per day, and a merged view with the same
field names the desk banner already reads (fetched_at / stale / tickers /
macro). Ported additions:

* every call is metered in the database (daily_snapshots kind='gex_quota'),
  because the FREE plan allows only FIVE requests per day and the 09:00 CST
  scheduled job spends two of them. The API refuses to fetch past
  ``settings.flashalpha_daily_cap`` (default 3) so a dashboard click can
  never starve the daily job;
* results land in the DB snapshot mirror (the serving source) and, when the
  legacy repo is present, in gex_daily.json + gex/<day>_<ticker>.json so the
  old stack keeps working;
* quota/network errors keep the previous good data and stamp ``stale: true``
  exactly like the original.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import DailySnapshot

logger = logging.getLogger(__name__)

_CST = ZoneInfo("America/Chicago")
BASE = "https://lab.flashalpha.com/v1/stock/{t}/summary"
QUOTA_KIND = "gex_quota"


class GexError(Exception):
    """Fetch could not be performed (missing key, quota exhausted, network)."""


class QuotaExhausted(GexError):
    pass


# --- credentials -----------------------------------------------------------

def api_key() -> str:
    """Key from TBOT_FLASHALPHA_API_KEY, else the legacy flashalpha.env."""
    settings = get_settings()
    if settings.flashalpha_api_key:
        return settings.flashalpha_api_key
    env_file = settings.super_dir / "flashalpha.env"
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("FLASHALPHA_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key:
                    return key
    except OSError:
        pass
    raise GexError(
        "no flashAlpha API key: set TBOT_FLASHALPHA_API_KEY or provide "
        f"{env_file}"
    )


# --- daily quota meter -----------------------------------------------------

def _today_cst() -> str:
    return datetime.now(_CST).date().isoformat()


def quota_state(db: Session) -> dict:
    """How many calls the API has spent today and what is left."""
    cap = get_settings().flashalpha_daily_cap
    day = _today_cst()
    row = db.scalar(
        select(DailySnapshot).where(
            DailySnapshot.kind == QUOTA_KIND, DailySnapshot.snapshot_date == day
        )
    )
    used = int((row.payload or {}).get("count", 0)) if row else 0
    return {
        "date": day,
        "used_by_api": used,
        "cap": cap,
        "remaining": max(0, cap - used),
        "plan_note": "flashAlpha FREE = 5 requests/day; this API is the only fetcher "
        "(the 09:00 CST Windows task was replaced by the in-process daily loop)",
    }


def latest_gex_date(db: Session) -> str | None:
    """snapshot_date of the newest stored GEX view (YYYY-MM-DD)."""
    row = db.scalar(
        select(DailySnapshot)
        .where(DailySnapshot.kind == "gex")
        .order_by(DailySnapshot.snapshot_date.desc())
        .limit(1)
    )
    return row.snapshot_date if row else None


def _record_calls(db: Session, n: int, tickers: list[str]) -> None:
    day = _today_cst()
    row = db.scalar(
        select(DailySnapshot).where(
            DailySnapshot.kind == QUOTA_KIND, DailySnapshot.snapshot_date == day
        )
    )
    stamp = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    if row is None:
        db.add(
            DailySnapshot(
                kind=QUOTA_KIND,
                snapshot_date=day,
                payload={"count": n, "calls": [{"at": stamp, "tickers": tickers}]},
                source_file="api:refreshGex",
            )
        )
    else:
        payload = dict(row.payload or {})
        payload["count"] = int(payload.get("count", 0)) + n
        calls = list(payload.get("calls") or [])
        calls.append({"at": stamp, "tickers": tickers})
        payload["calls"] = calls[-50:]
        row.payload = payload
        row.fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()


# --- fetch + extract (ported verbatim in shape) ----------------------------

def fetch_summary(ticker: str, key: str, *, timeout: float = 30.0) -> dict:
    req = urllib.request.Request(BASE.format(t=ticker), headers={"X-Api-Key": key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 429 is the quota wall; surface it distinctly so callers can stop.
        raise GexError(f"HTTP {exc.code} from flashAlpha for {ticker}") from exc
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise GexError(f"flashAlpha unreachable for {ticker}: {exc}") from exc
    if payload.get("status") == "ERROR":
        raise GexError(payload.get("error") or "flashAlpha API error")
    return payload


def extract(p: dict) -> dict:
    """Identical field set to gex_daily.py's extract()."""
    ex = p.get("exposure") or {}
    px = (p.get("price") or {}).get("last")
    flip = ex.get("gamma_flip")
    return {
        "as_of": p.get("as_of"),
        "price": round(px, 2) if isinstance(px, (int, float)) else px,
        "net_gex": ex.get("net_gex"),
        "regime": ex.get("regime"),
        "gamma_flip": round(flip, 2) if isinstance(flip, (int, float)) else None,
        # aggregate highest-GEX strikes; for SPY/QQQ gamma concentrates in the
        # next ~2 business days, so these act as the near-dated walls
        "call_wall": ex.get("call_wall"),
        "put_wall": ex.get("put_wall"),
        "gamma_note": (ex.get("interpretation") or {}).get("gamma"),
        "atm_iv": (p.get("volatility") or {}).get("atm_iv"),
        "pc_ratio_volume": (p.get("options_flow") or {}).get("pc_ratio_volume"),
    }


def _macro(p: dict) -> dict | None:
    m = p.get("macro")
    if not m:
        return None
    return {
        "vix": (m.get("vix") or {}).get("value"),
        "vix_chg_pct": (m.get("vix") or {}).get("change_pct"),
        "vvix": (m.get("vvix") or {}).get("value"),
        "skew": (m.get("skew") or {}).get("value"),
        "move": (m.get("move") or {}).get("value"),
        "term": (m.get("vix_term_structure") or {}).get("structure"),
        "fear_greed": (m.get("fear_and_greed") or {}).get("score"),
    }


# --- the job ---------------------------------------------------------------

def refresh(db: Session, tickers: list[str] | None = None, *, persist: bool = True) -> dict:
    """Live-fetch GEX for *tickers* (default spy,qqq), quota-guarded.

    Returns {gex, calls_made, quota, errors}. Never raises for a per-ticker
    failure: previous data is retained and ``stale`` is set, as in the
    original job.

    ``persist=False`` is the ad-hoc lookup mode: the payload is still
    archived (gex_raw_<ticker>) and the call still metered, but the desk's
    merged SPY/QQQ snapshot and gex_daily.json are left untouched so a
    one-off ticker never pollutes the banner.
    """
    settings = get_settings()
    tickers = [t.strip().lower() for t in (tickers or settings.gex_tickers.split(",")) if t.strip()]
    if not tickers:
        raise GexError("no tickers requested")

    quota = quota_state(db)
    if len(tickers) > quota["remaining"]:
        raise QuotaExhausted(
            f"needs {len(tickers)} request(s) but only {quota['remaining']} of the "
            f"{quota['cap']} daily API calls remain (flashAlpha FREE = 5/day and the "
            "09:00 CST job spends 2). Use the free ↻ reload, or raise "
            "TBOT_FLASHALPHA_DAILY_CAP if you know the budget allows it."
        )

    key = api_key()

    # start from the last good snapshot so a failed ticker keeps its data
    from app.services import super_research as sr

    prev = sr.gex_from_db(db) or {}
    out = {
        "fetched_at": f"{datetime.now(_CST):%Y-%m-%d %H:%M:%S}",
        "stale": False,
        "tickers": dict(prev.get("tickers") or {}),
        "macro": prev.get("macro"),
    }

    archive_dir = settings.super_dir / "gex"
    errors: dict[str, str] = {}
    calls = 0
    for t in tickers:
        try:
            payload = fetch_summary(t, key)
            calls += 1
            day = (payload.get("as_of") or out["fetched_at"])[:10]
            out["tickers"][t.upper()] = extract(payload)
            macro = _macro(payload)
            if macro:
                out["macro"] = macro
            # DB archive of the raw payload (kind matches the ingest naming)
            _upsert_snapshot(db, f"gex_raw_{t}", day, payload, "api:refreshGex")
            # keep the legacy archive file too, when the repo is present
            if settings.super_dir.is_dir():
                try:
                    archive_dir.mkdir(exist_ok=True)
                    (archive_dir / f"{day}_{t}.json").write_text(
                        json.dumps(payload, indent=1), encoding="utf-8"
                    )
                except OSError as exc:
                    logger.warning("could not write gex archive for %s: %s", t, exc)
            logger.info(
                "GEX %s: net_gex %s (%s) flip %s walls %s/%s",
                t.upper(), out["tickers"][t.upper()]["net_gex"],
                out["tickers"][t.upper()]["regime"], out["tickers"][t.upper()]["gamma_flip"],
                out["tickers"][t.upper()]["call_wall"], out["tickers"][t.upper()]["put_wall"],
            )
        except GexError as exc:
            # a 4xx/429 still consumed a request on their side — count it
            calls += 1
            errors[t] = str(exc)
            logger.warning("GEX %s fetch failed (%s) — keeping previous data", t.upper(), exc)

    out["stale"] = bool(errors)
    if calls:
        _record_calls(db, calls, tickers)

    if persist:
        # the DB snapshot is what /super/gex and the desk banner serve
        _upsert_snapshot(db, "gex", out["fetched_at"][:10], out, "api:refreshGex")
        # mirror to the legacy file so gex_daily.py / the old desk agree
        if settings.super_dir.is_dir():
            try:
                (settings.super_dir / "gex_daily.json").write_text(
                    json.dumps(out, indent=1), encoding="utf-8"
                )
            except OSError as exc:
                logger.warning("could not write gex_daily.json: %s", exc)
        sr.invalidate_caches()
    else:
        # ad-hoc lookup: report ONLY what was asked for, leave the desk alone
        out["tickers"] = {
            t.upper(): out["tickers"][t.upper()]
            for t in tickers
            if t.upper() in out["tickers"]
        }
    return {
        "gex": out,
        "calls_made": calls,
        "errors": errors,
        "quota": quota_state(db),
    }


def _upsert_snapshot(db: Session, kind: str, date: str, payload: dict, source: str) -> None:
    row = db.scalar(
        select(DailySnapshot).where(
            DailySnapshot.kind == kind, DailySnapshot.snapshot_date == date
        )
    )
    if row is None:
        db.add(DailySnapshot(kind=kind, snapshot_date=date, payload=payload, source_file=source))
    else:
        row.payload = payload
        row.source_file = source
        row.fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
