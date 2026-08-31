"""super_research endpoints.

Two routers share one implementation:

- ``router``       -> /api/v1/super/*   (canonical, documented)
- ``compat_router``-> /api/super/*      (byte-compatible with the legacy
  vite middleware so the existing SuperSite frontend keeps working when its
  /api/super calls are pointed at this backend)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.cloud import require_local_runtime
from app.core.config import get_settings
from app.core.database import get_db
from app.services import earnings as earnings_svc
from app.services import engine_pct
from app.services import gex0dte
from app.services import ticker_onboard as onboard
from app.schemas.super import (
    SnapshotOut,
    SuperConfigUpdate,
    SuperSignalPage,
    SuperSignalOut,
    SuperStopRequest,
)
from app.services import super_research as svc

router = APIRouter(prefix="/super", tags=["super-research"])
compat_router = APIRouter(prefix="/super", include_in_schema=False)


# --- state / control (vite-compatible shapes) ------------------------------

def _state(request: Request, db: Session) -> dict:
    want_all = request.query_params.get("all") in ("1", "true")
    return svc.build_state(db, want_all=want_all)


@router.get("/state", operation_id="getSuperState")
def get_state(request: Request, db: Session = Depends(get_db)) -> dict:
    """Full desk state served from SQLite (config mirror, signal rows,
    gex/econ snapshots) — the source repo is not needed at request time.
    Pass ?all=1 to include the archived ledger rows."""
    return _state(request, db)


@router.post("/on", operation_id="superOn")
def super_on() -> dict:
    """Start missing category supervisors (detached; they survive API
    restarts). Categories with zero enabled tickers are skipped."""
    require_local_runtime("Starting the signal supervisors")
    try:
        return svc.start_supervisors()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"start failed: {exc}")


@router.post("/off", operation_id="superOff")
def super_off(payload: SuperStopRequest | None = None) -> dict:
    """Stop supervisors (all, or one category). The legacy stack has no stop
    endpoint — this replaces `python bots.py stop`."""
    require_local_runtime("Stopping the signal supervisors")
    return svc.stop_supervisors(payload.category if payload else None)


@router.post("/config", operation_id="setSuperConfig")
def set_config(payload: SuperConfigUpdate, db: Session = Depends(get_db)) -> dict:
    try:
        svc.write_enabled(db, payload.enabled)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"config write failed: {exc}")
    return {"ok": True}


@router.get("/config", operation_id="getSuperConfig")
def get_config(db: Session = Depends(get_db)) -> dict:
    cfg = svc.config_from_db(db)
    if cfg is None:
        raise HTTPException(
            status_code=404,
            detail="no super_config in the database (sync once with the source repo present)",
        )
    return cfg


# --- ticker quotes ---------------------------------------------------------

@router.get("/quote/{ticker}", operation_id="getTickerQuote")
def get_quote(ticker: str) -> dict:
    """Live price + classic pivot points for a desk ticker (yfinance,
    keyless, cached 60s). Includes the TradingView chart URL."""
    from app.services import quotes

    try:
        return quotes.quote_for(ticker)
    except quotes.QuoteError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# --- GEX / econ ------------------------------------------------------------

@router.get("/gex", operation_id="getGex")
def get_gex(db: Session = Depends(get_db)) -> dict:
    """Latest merged GEX view, served from the DB snapshot mirror. This
    backend never calls the flashAlpha API — the 09:00 CST scheduled job
    owns the 5-requests/day free-tier budget."""
    gex = svc.gex_from_db(db)
    if gex is None:
        raise HTTPException(status_code=404, detail="no GEX snapshot in the database yet")
    return gex


@router.get("/econ", operation_id="getEcon")
def get_econ(db: Session = Depends(get_db)) -> dict:
    econ = svc.econ_from_db(db)
    if econ is None:
        raise HTTPException(status_code=404, detail="no econ snapshot in the database yet")
    return econ


@router.get("/gex0dte", operation_id="getGex0dte")
def get_gex0dte(db: Session = Depends(get_db)) -> dict:
    """Latest stored SPY 0DTE dealer-gamma view, with its own timestamp.

    Read-only and cheap: the desk polls this every minute and it never
    touches the vendor. Refreshing is an explicit POST.
    """
    payload = svc.latest_payload(db, "gex0dte")
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="no 0DTE snapshot yet — press Update 0DTE to fetch one",
        )
    payload.update(gex0dte.staleness(payload.get("fetched_at")))
    payload.update(gex0dte.pusher_state(db))
    return payload


class Gex0dteRefresh(BaseModel):
    """Give it a chain captured from a getgamma.io tab, or nothing to make the
    server try the vendor directly. No credentials either way — the endpoint
    needs none; its edge simply refuses non-browser clients."""

    payload: dict | None = None
    ticker: str = "SPY"
    # per-cycle metadata from the browser pusher; declared because pydantic
    # would otherwise drop it silently and the trail would vanish
    client: dict | None = None


@router.post("/gex0dte/refresh", operation_id="refreshGex0dte")
def refresh_gex0dte(body: Gex0dteRefresh, db: Session = Depends(get_db)) -> dict:
    raw = body.payload
    if raw is None:
        try:
            raw = gex0dte.fetch_live(ticker=body.ticker)
        except gex0dte.GammaError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        view = gex0dte.compute(raw)
    except gex0dte.GammaError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    svc.store_payload(db, "gex0dte", view, source="getgamma.io")
    gex0dte.record_hour(db, view)      # and into this hour's history slot
    return view


@router.get("/engine-pct", operation_id="getEnginePct")
def get_engine_pct() -> dict:
    """Per-category TP/SL race targets, read from each ticker's config.py.

    ``mixed: true`` means the tickers in that category disagree — reported
    rather than averaged, because it usually means a folder was hand-edited.
    """
    require_local_runtime("Reading the engine targets")
    return engine_pct.read_all()


class EnginePctUpdate(BaseModel):
    """Retarget one category. ``sl_pct`` defaults to ``tp_pct`` (symmetric)."""

    category: str
    tp_pct: float
    sl_pct: float | None = None


@router.post("/engine-pct", operation_id="setEnginePct")
def set_engine_pct(payload: EnginePctUpdate, db: Session = Depends(get_db)) -> dict:
    """Rewrite TP_PCT/SL_PCT for every ticker in a category.

    Takes effect on the next scan cycle. The engine-score cache is
    fingerprinted on tp/sl so it re-scores itself; the B-book candidate set is
    not re-discovered, which the response says explicitly.
    """
    require_local_runtime("Changing the engine targets")
    try:
        return engine_pct.write_category(db, payload.category, payload.tp_pct, payload.sl_pct)
    except engine_pct.PctError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"config write failed: {exc}") from exc


@router.get("/engine-gates", operation_id="getEngineGates")
def get_engine_gates() -> dict:
    """A-book / B-book tp-before-sl admission gates (desk-wide).

    These are module-level constants in engine_common.py shared by every
    ticker, so there is one pair of numbers, not one per category.
    """
    require_local_runtime("Reading the engine gates")
    try:
        return engine_pct.read_gates()
    except engine_pct.PctError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class EngineGatesUpdate(BaseModel):
    """``b_tpsl`` is the floor to emit at all; ``a_tpsl`` promotes to A-book."""

    a_tpsl: float
    b_tpsl: float


@router.post("/engine-gates", operation_id="setEngineGates")
def set_engine_gates(payload: EngineGatesUpdate) -> dict:
    """Set the A/B admission gates. Applies on the next scan; no re-scoring."""
    require_local_runtime("Changing the engine gates")
    try:
        return engine_pct.write_gates(payload.a_tpsl, payload.b_tpsl)
    except engine_pct.PctError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"write failed: {exc}") from exc


@router.get("/regenerate/status", operation_id="getRegenerateStatus")
def regenerate_status(db: Session = Depends(get_db)) -> dict:
    """Whether the last regenerate has finished — the launch itself is detached."""
    require_local_runtime("Reading regenerate status")
    return svc.regenerate_status(db)


class HeartbeatIn(BaseModel):
    """One push cycle reported by the browser pusher, successful or not."""

    session: str = "?"
    seq: int = 0
    ok: bool = False
    reason: str | None = None
    wall: int | None = None
    mono: int | None = None


@router.post("/gex0dte/heartbeat", operation_id="gex0dtePusherHeartbeat")
def gex0dte_heartbeat(body: HeartbeatIn, db: Session = Depends(get_db)) -> dict:
    """Record that a push cycle happened, whatever its outcome.

    Strictly separate from the data path: it never fetches the vendor, never
    stores a snapshot and never fills an hour slot. Routing liveness through
    /refresh would make the SERVER call getgamma on every failed cycle — the
    one thing this design does not do — and would stamp a stalled feed as
    fresh.
    """
    gex0dte.record_heartbeat(db, body.session, body.seq, body.ok, body.reason,
                             body.wall, body.mono)
    return {"ok": True}


class AddTickerRequest(BaseModel):
    """Onboard one ticker into an existing category, on the default engines."""

    category: str
    ticker: str
    label: str | None = None


@router.post("/tickers", operation_id="addSuperTicker")
def add_ticker(payload: AddTickerRequest, db: Session = Depends(get_db)) -> dict:
    """Scaffold, register and bootstrap a new ticker in a category.

    Returns as soon as the folder and registry entry exist; the B-book build
    (60 days of bars) runs detached, so poll ``/tickers/{id}/status`` for it.
    The supervisors pick the ticker up on their next cycle — they re-read the
    registry — and unconditionally after a restart.
    """
    require_local_runtime("Onboarding a ticker")
    try:
        return onboard.add_ticker(db, payload.category, payload.ticker, payload.label)
    except onboard.OnboardError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"onboarding failed: {exc}") from exc


@router.get("/tickers/{ticker_id}/status", operation_id="getSuperTickerStatus")
def ticker_status(ticker_id: str) -> dict:
    """Whether the background bootstrap has produced a playbook yet."""
    require_local_runtime("Reading onboarding status")
    try:
        return onboard.bootstrap_status(ticker_id)
    except onboard.OnboardError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/gex0dte/history", operation_id="getGex0dteHistory")
def get_gex0dte_history(
    date: str | None = Query(default=None, description="YYYY-MM-DD (CST); omit for today"),
    db: Session = Depends(get_db),
) -> dict:
    """Hourly SPY 0DTE net gamma for one trading day, 08:00-16:00 CST.

    All nine hours come back every time; ones never captured read 0 and carry
    ``captured: false``, so a quiet hour is distinguishable from a flat one.
    """
    return gex0dte.history(db, date)


@router.get("/gex0dte/history/dates", operation_id="getGex0dteHistoryDates")
def get_gex0dte_history_dates(db: Session = Depends(get_db)) -> dict:
    """Dates with at least one captured hour, newest first."""
    return {"dates": gex0dte.history_dates(db)}


@router.get("/earnings", operation_id="getEarnings")
def get_earnings(
    hours: int = Query(default=24, ge=1, le=168, description="look-ahead window"),
    refresh: bool = Query(default=False, description="force a re-sweep, ignoring the cache"),
    db: Session = Depends(get_db),
) -> dict:
    """Scheduled earnings for the large-cap universe inside the next `hours`.

    Keyless (yfinance) so there is no budget to protect, but a sweep is ~100
    HTTP calls — the result is cached in daily_snapshots and only refetched
    when older than 12h, so polling this is cheap.
    """
    try:
        return earnings_svc.get_earnings(db, hours=hours, force=refresh)
    except Exception as exc:  # upstream outage must not 500 the desk
        raise HTTPException(status_code=502, detail=f"earnings lookup failed: {exc}") from exc


@router.post("/regenerate", operation_id="regenerateEngines")
def regenerate(
    categories: str | None = Query(
        default=None, description="comma-separated: etf,stock,crypto,india; omit for all"
    ),
    force: bool = Query(
        default=False,
        description="launch even if the last regenerate was under 24h ago",
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Re-run every enabled engine for today (--once --backfill-today per
    category). Results land in the ledgers within minutes and the auto-sync
    loop stores them in SQLite; watch /super/sync/status.

    If the engines already regenerated in the past 24h, this returns
    ``recent: true`` without launching — pass ``force=true`` after the user
    confirms, or skip regeneration and turn on the live watcher instead."""
    require_local_runtime("Regenerating the engines")
    cats = [c.strip() for c in categories.split(",") if c.strip()] if categories else None
    try:
        return svc.regenerate_engines(cats, db=db, force=force)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"regenerate failed: {exc}")


@router.post("/gex/refresh", operation_id="refreshGex")
def refresh_gex(
    tickers: str | None = Query(
        default=None, description="comma-separated, default spy,qqq — ONE API call each"
    ),
    persist: bool = Query(
        default=True,
        description="false = ad-hoc lookup: metered and archived, but the desk's "
        "SPY/QQQ snapshot and gex_daily.json are left untouched",
    ),
    db: Session = Depends(get_db),
) -> dict:
    """LIVE-fetch gamma exposure from flashAlpha (ported FlashAlphaGEX_Daily
    logic) and store it as the new snapshot.

    Spends real API quota: the FREE plan allows 5 requests/day. Calls are
    metered in the DB and refused past TBOT_FLASHALPHA_DAILY_CAP. Use
    POST /super/gex/reload (free) when you only need to re-read what is
    already stored."""
    from app.services import gex as gex_svc

    try:
        return gex_svc.refresh(
            db,
            [t for t in tickers.split(",")] if tickers else None,
            persist=persist,
        )
    except gex_svc.QuotaExhausted as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except gex_svc.GexError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/gex/quota", operation_id="getGexQuota")
def gex_quota(db: Session = Depends(get_db)) -> dict:
    """How much flashAlpha budget the API has spent today."""
    from app.services import gex as gex_svc

    return gex_svc.quota_state(db)


@router.post("/gex/reload", operation_id="reloadGex")
def reload_gex(db: Session = Depends(get_db)) -> dict:
    """Re-ingest gex_daily.json from disk (when the source repo is present)
    and serve the latest DB snapshot. Deliberately does NOT call the
    flashAlpha API (free tier is 5 requests/day, owned by the 09:00 CST
    scheduled job)."""
    result = {"upserted": 0}
    if svc.get_settings().super_dir.is_dir():
        with svc._SYNC_LOCK:
            result = svc.sync_snapshots(db)
    gex = svc.gex_from_db(db)
    if gex is None:
        raise HTTPException(status_code=404, detail="no GEX snapshot in the database yet")
    return {"reloaded": True, "snapshots": result, "gex": gex}


@router.post("/econ/refresh", operation_id="refreshEcon")
def refresh_econ() -> dict:
    """Regenerate econ_today.json (keyless: hardcoded calendar + one
    yfinance yields fetch, cached per day by the script itself)."""
    require_local_runtime("Refreshing econ data")
    settings = get_settings()
    if not settings.super_dir.is_dir():
        raise HTTPException(
            status_code=503, detail="econ refresh needs the source repo on this host"
        )
    python = str(settings.super_python)
    if not Path(python).is_file():
        python = sys.executable
    try:
        proc = subprocess.run(
            [python, str(settings.super_dir / "econ_events.py")],
            cwd=str(settings.super_dir),
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=502, detail=f"econ refresh failed: {exc}")
    econ = svc.read_econ()
    return {"ok": proc.returncode == 0, "econ": econ}


# --- SQLite history --------------------------------------------------------

@router.post("/sync", operation_id="syncSuperData")
def sync_all(
    include_archive: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict:
    """Full forced ingest of every signal source (central ledgers, worker
    CSVs, gex/econ snapshots) into SQLite. The background auto-sync loop
    runs the same pass continuously; this endpoint forces one now."""
    return svc.sync_everything(db, include_archive=include_archive, force=True)


@router.get("/sync/status", operation_id="getSuperSyncStatus")
def sync_status() -> dict:
    """Health of the background ingest loop that guarantees every generated
    signal lands in the database."""
    return svc.AUTO_SYNC_STATUS


@router.get("/signals", operation_id="getSuperSignals", response_model=SuperSignalPage)
def get_signals(
    book: str | None = Query(default=None, pattern="^[abAB]$"),
    category: str | None = Query(default=None),
    ticker: str | None = Query(default=None),
    grade_min: int | None = Query(default=None, ge=2, le=5, description="min eng_hot grade"),
    days: int | None = Query(default=None, ge=1, le=3660),
    central: bool = Query(default=False,
                          description="only merged A/B ledger rows (no per-engine worker rows)"),
    limit: int = Query(default=100, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> SuperSignalPage:
    total, items = svc.query_signals(
        db,
        book=book,
        category=category,
        ticker=ticker,
        grade_min=grade_min,
        days=days,
        central=central,
        limit=limit,
        offset=offset,
    )
    return SuperSignalPage(total=total, items=[SuperSignalOut.model_validate(s) for s in items])


@router.get("/snapshots", operation_id="getDailySnapshots", response_model=list[SnapshotOut])
def get_snapshots(
    kind: str = Query(default="gex", examples=["gex", "econ", "gex_raw_spy"]),
    limit: int = Query(default=30, ge=1, le=366),
    db: Session = Depends(get_db),
) -> list[SnapshotOut]:
    from sqlalchemy import select

    from app.models import DailySnapshot

    rows = db.scalars(
        select(DailySnapshot)
        .where(DailySnapshot.kind == kind)
        .order_by(DailySnapshot.snapshot_date.desc())
        .limit(limit)
    ).all()
    return [SnapshotOut.model_validate(r) for r in rows]


# --- legacy-compatible aliases (/api/super/*) ------------------------------

@compat_router.get("/state")
def compat_state(request: Request, db: Session = Depends(get_db)) -> dict:
    return _state(request, db)


@compat_router.post("/on")
def compat_on() -> dict:
    return svc.start_supervisors()


@compat_router.post("/config")
def compat_config(payload: SuperConfigUpdate, db: Session = Depends(get_db)) -> dict:
    svc.write_enabled(db, payload.enabled)
    return {"ok": True}
