"""Super-research: GEX, econ, earnings, the signal ledger, engine control.

This surface exists in the desk and did not exist in api_v2 at all. Every
/super/* call the frontend made fell through to the SPA catch-all, so the GEX
board, the econ strip, the earnings panel and both signal feeds rendered empty
with no error anywhere -- the worst failure mode there is, because "no signals
today" and "this endpoint was never built" look identical from the desk.

What this is NOT is a reimplementation. The vendor work -- the flashAlpha
fetch, the gamma maths, the yfinance earnings sweep, the ledger ingest --
already existed and was already real. Those services now read the research
domain's models, so this router composes them rather than restating them.

Access, which is the part that genuinely differs from the old app:

  read      any authenticated operator. Market facts are not operator data;
            a SPY gamma wall is the same number for everybody on the desk.
  write     admin only, and for a concrete reason in each case -- these
            endpoints spend a metered vendor budget (five flashAlpha calls a
            day for the whole desk), start detached OS processes, or rewrite
            the engine configs every ticker trades on. None of that is a
            per-operator preference, so none of it is a per-operator right.

The old app authorised none of this. It ran on one operator's laptop, so the
question "who is asking" had exactly one answer.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.api_v2 import deps
from app.tenancy.models import Tenant

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/super", tags=["research"])


def _svc():
    """The research service, imported lazily.

    It pulls in pandas, yfinance and the engine loader; a process that never
    touches research -- a bot runner, a migration -- should not pay for that
    at import time.
    """
    from app.services import super_research

    return super_research


def _not_found(what: str) -> HTTPException:
    return HTTPException(status_code=404, detail=what)


# ---- desk state -----------------------------------------------------------

@router.get("/state", operation_id="getSuperState")
@deps.tenant_scoped
def state(all: int | None = Query(default=None),
          tenant: Tenant = Depends(deps.current_tenant),
          db: DbSession = Depends(deps.get_db)) -> dict:
    """The whole research desk in one read: config, both feeds, gex, econ.

    Served from the database rather than from the engines' files, so a request
    never waits on a disk scan of the source tree and the desk keeps rendering
    while the engines are stopped.
    """
    return _svc().build_state(db, want_all=bool(all))


@router.get("/config", operation_id="getSuperConfig")
@deps.tenant_scoped
def get_config(tenant: Tenant = Depends(deps.current_tenant),
               db: DbSession = Depends(deps.get_db)) -> dict:
    cfg = _svc().config_from_db(db)
    if cfg is None:
        raise _not_found("no research config has been ingested yet")
    return cfg


class ConfigUpdate(BaseModel):
    enabled: dict[str, bool]


@router.post("/config", operation_id="setSuperConfig")
def set_config(payload: ConfigUpdate,
               tenant: Tenant = Depends(deps.require_admin),
               db: DbSession = Depends(deps.get_db)) -> dict:
    """Enable or disable tickers. Admin: it changes what the ENGINES do, for
    everyone, rather than what one operator sees."""
    try:
        _svc().write_enabled(db, payload.enabled)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500,
                            detail=f"config write failed: {exc}") from exc
    return {"ok": True}


# ---- supervisors ----------------------------------------------------------

@router.post("/on", operation_id="superOn")
def supervisors_on(tenant: Tenant = Depends(deps.require_admin)) -> dict:
    """Start the category supervisors. Detached, so they outlive this API."""
    try:
        return _svc().start_supervisors()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500,
                            detail=f"start failed: {exc}") from exc


class StopRequest(BaseModel):
    category: str | None = None


@router.post("/off", operation_id="superOff")
def supervisors_off(payload: StopRequest | None = None,
                    tenant: Tenant = Depends(deps.require_admin)) -> dict:
    return _svc().stop_supervisors(payload.category if payload else None)


@router.post("/regenerate", operation_id="regenerateEngines")
def regenerate(categories: str | None = Query(default=None),
               force: bool = Query(default=False),
               tenant: Tenant = Depends(deps.require_admin),
               db: DbSession = Depends(deps.get_db)) -> dict:
    """Re-run today's engines.

    Returns ``recent: true`` WITHOUT launching when the last run was under 24h
    ago, unless forced -- a second concurrent regenerate does not produce
    fresher signals, it produces two sets of processes writing one ledger.
    """
    cats = ([c.strip() for c in categories.split(",") if c.strip()]
            if categories else None)
    try:
        return _svc().regenerate_engines(cats, db=db, force=force)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500,
                            detail=f"regenerate failed: {exc}") from exc


@router.get("/regenerate/status", operation_id="getRegenerateStatus")
@deps.tenant_scoped
def regenerate_status(tenant: Tenant = Depends(deps.current_tenant),
                      db: DbSession = Depends(deps.get_db)) -> dict:
    return _svc().regenerate_status(db)


# ---- GEX ------------------------------------------------------------------

@router.get("/gex", operation_id="getGex")
@deps.tenant_scoped
def get_gex(tenant: Tenant = Depends(deps.current_tenant),
            db: DbSession = Depends(deps.get_db)) -> dict:
    """The stored gamma view.

    Never calls the vendor. Reading the board must not spend a budget of five
    calls a day, or the first operator to open the page would exhaust it.
    """
    view = _svc().gex_from_db(db)
    if view is None:
        raise _not_found("no GEX snapshot has been fetched yet")
    return view


@router.get("/gex/quota", operation_id="getGexQuota")
@deps.tenant_scoped
def gex_quota(tenant: Tenant = Depends(deps.current_tenant),
              db: DbSession = Depends(deps.get_db)) -> dict:
    from app.services import gex as gex_svc

    return gex_svc.quota_state(db)


@router.post("/gex/refresh", operation_id="refreshGex")
def gex_refresh(tickers: str | None = Query(default=None),
                persist: bool = Query(default=True),
                tenant: Tenant = Depends(deps.require_admin),
                db: DbSession = Depends(deps.get_db)) -> dict:
    """Spend flashAlpha quota to fetch live gamma.

    Admin, and metered: the free plan is FIVE requests a day for the whole
    desk. Exhausting it answers 429 rather than an empty board, so the
    operator can tell "we are out of budget" from "the vendor is down".
    """
    from app.services import gex as gex_svc

    try:
        return gex_svc.refresh(
            db, [t for t in tickers.split(",")] if tickers else None,
            persist=persist)
    except gex_svc.QuotaExhausted as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except gex_svc.GexError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/gex/reload", operation_id="reloadGex")
def gex_reload(tenant: Tenant = Depends(deps.require_admin),
               db: DbSession = Depends(deps.get_db)) -> dict:
    """Re-ingest what is already on disk. FREE -- spends no vendor quota."""
    svc = _svc()
    result = {"upserted": 0}
    if svc.get_settings().super_dir.is_dir():
        with svc._SYNC_LOCK:
            result = svc.sync_snapshots(db)
    view = svc.gex_from_db(db)
    if view is None:
        raise _not_found("no GEX snapshot has been fetched yet")
    return {"reloaded": True, "snapshots": result, "gex": view}


# ---- 0DTE gamma -----------------------------------------------------------

@router.get("/gex0dte", operation_id="getGex0dte")
@deps.tenant_scoped
def get_gex0dte(tenant: Tenant = Depends(deps.current_tenant),
                db: DbSession = Depends(deps.get_db)) -> dict:
    """The latest 0DTE view, with how stale it is and whether the pusher is
    alive.

    Staleness travels WITH the number rather than beside it: a gamma reading
    with no age is unreadable, because a four-hour-old one looks exactly like
    a fresh one on the board.
    """
    from app.services import gex0dte

    payload = _svc().latest_payload(db, "gex0dte")
    if payload is None:
        raise _not_found(
            "no 0DTE snapshot yet - press Update 0DTE to fetch one")
    payload.update(gex0dte.staleness(payload.get("fetched_at")))
    payload.update(gex0dte.pusher_state(db))
    return payload


class Gex0dteRefresh(BaseModel):
    payload: dict | None = None
    ticker: str = "SPY"
    # Per-cycle metadata from the browser pusher. Declared because pydantic
    # would otherwise drop it silently and the trail would vanish.
    client: dict | None = None


@router.post("/gex0dte/refresh", operation_id="refreshGex0dte")
@deps.tenant_scoped
def refresh_gex0dte(body: Gex0dteRefresh,
                    tenant: Tenant = Depends(deps.current_tenant),
                    db: DbSession = Depends(deps.get_db)) -> dict:
    """Store a chain, pushed from a browser tab or fetched here.

    Any operator rather than admin: this is the desk's own data path -- a tab
    the operator already has open pushes what it already sees -- and it costs
    no metered budget.
    """
    from app.services import gex0dte

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
    _svc().store_payload(db, "gex0dte", view, source="getgamma.io")
    gex0dte.record_hour(db, view)
    return view


class HeartbeatIn(BaseModel):
    session: str = "?"
    seq: int = 0
    ok: bool = False
    reason: str | None = None
    wall: int | None = None
    mono: int | None = None


@router.post("/gex0dte/heartbeat", operation_id="gex0dtePusherHeartbeat")
@deps.tenant_scoped
def gex0dte_heartbeat(body: HeartbeatIn,
                      tenant: Tenant = Depends(deps.current_tenant),
                      db: DbSession = Depends(deps.get_db)) -> dict:
    """Record that a push cycle happened, whatever its outcome.

    Strictly separate from the data path. Routing liveness through /refresh
    would make the SERVER call the vendor on every failed cycle, and would
    stamp a stalled feed as fresh -- the two things this design does not do.
    """
    from app.services import gex0dte

    gex0dte.record_heartbeat(db, body.session, body.seq, body.ok, body.reason,
                             body.wall, body.mono)
    return {"ok": True}


@router.get("/gex0dte/history", operation_id="getGex0dteHistory")
@deps.tenant_scoped
def gex0dte_history(date: str | None = Query(default=None),
                    tenant: Tenant = Depends(deps.current_tenant),
                    db: DbSession = Depends(deps.get_db)) -> dict:
    """One trading day, hour by hour.

    Every hour comes back; ones never captured read 0 and carry
    ``captured: false``, so a gap in the feed stays visible instead of passing
    for a flat market.
    """
    from app.services import gex0dte

    return gex0dte.history(db, date)


@router.get("/gex0dte/history/dates", operation_id="getGex0dteHistoryDates")
@deps.tenant_scoped
def gex0dte_history_dates(tenant: Tenant = Depends(deps.current_tenant),
                          db: DbSession = Depends(deps.get_db)) -> dict:
    from app.services import gex0dte

    return {"dates": gex0dte.history_dates(db)}


# ---- econ, earnings, quotes -----------------------------------------------

@router.get("/econ", operation_id="getEcon")
@deps.tenant_scoped
def get_econ(tenant: Tenant = Depends(deps.current_tenant),
             db: DbSession = Depends(deps.get_db)) -> dict:
    view = _svc().econ_from_db(db)
    if view is None:
        raise _not_found("no econ snapshot has been ingested yet")
    return view


@router.get("/earnings", operation_id="getEarnings")
@deps.tenant_scoped
def get_earnings(hours: int = Query(default=24, ge=1, le=168),
                 refresh: bool = Query(default=False),
                 tenant: Tenant = Depends(deps.current_tenant),
                 db: DbSession = Depends(deps.get_db)) -> dict:
    """Scheduled earnings inside the next `hours`.

    Keyless, so there is no budget to protect, but one sweep is ~100 HTTP
    calls -- cached for 12h so that polling it is cheap.
    """
    from app.services import earnings as earnings_svc

    try:
        return earnings_svc.get_earnings(db, hours=hours, force=refresh)
    except Exception as exc:                            # noqa: BLE001
        # An upstream outage must not 500 the desk.
        raise HTTPException(status_code=502,
                            detail=f"earnings lookup failed: {exc}") from exc


@router.get("/quote/{ticker}", operation_id="getTickerQuote")
@deps.tenant_scoped
def get_quote(ticker: str,
              tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """Live price and classic pivots for one ticker. Keyless, cached 60s."""
    from app.services import quotes

    try:
        return quotes.quote_for(ticker)
    except quotes.QuoteError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


# ---- engine targets -------------------------------------------------------

@router.get("/engine-pct", operation_id="getEnginePct")
@deps.tenant_scoped
def engine_pct(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """Per-category TP/SL targets, read from each ticker's own config.

    ``mixed: true`` means the tickers in a category disagree. Reported rather
    than averaged: an average would hide the disagreement, and a disagreement
    here usually means a folder was hand-edited.
    """
    from app.services import engine_pct as pct

    return pct.read_all()


class EnginePctUpdate(BaseModel):
    category: str
    tp_pct: float
    sl_pct: float | None = None


@router.post("/engine-pct", operation_id="setEnginePct")
def set_engine_pct(payload: EnginePctUpdate,
                   tenant: Tenant = Depends(deps.require_admin),
                   db: DbSession = Depends(deps.get_db)) -> dict:
    """Retarget every ticker in a category. Admin: it rewrites the config
    files the engines trade on, desk-wide."""
    from app.services import engine_pct as pct

    try:
        return pct.write_category(db, payload.category, payload.tp_pct,
                                  payload.sl_pct)
    except pct.PctError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500,
                            detail=f"config write failed: {exc}") from exc


@router.get("/engine-gates", operation_id="getEngineGates")
@deps.tenant_scoped
def engine_gates(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """The A/B admission gates.

    One pair for the whole desk rather than one per category -- they are
    module-level constants that every engine shares.
    """
    from app.services import engine_pct as pct

    try:
        return pct.read_gates()
    except pct.PctError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class EngineGatesUpdate(BaseModel):
    a_tpsl: float
    b_tpsl: float


@router.post("/engine-gates", operation_id="setEngineGates")
def set_engine_gates(payload: EngineGatesUpdate,
                     tenant: Tenant = Depends(deps.require_admin)) -> dict:
    from app.services import engine_pct as pct

    try:
        return pct.write_gates(payload.a_tpsl, payload.b_tpsl)
    except pct.PctError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500,
                            detail=f"write failed: {exc}") from exc


# ---- ticker onboarding ----------------------------------------------------

class AddTicker(BaseModel):
    category: str
    ticker: str
    label: str | None = None


@router.post("/tickers", operation_id="addSuperTicker")
def add_ticker(payload: AddTicker,
               tenant: Tenant = Depends(deps.require_admin),
               db: DbSession = Depends(deps.get_db)) -> dict:
    """Scaffold and register a ticker.

    Returns once the folder and registry entry exist; the 60-day build runs
    detached, so the caller polls its status rather than holding a request
    open for minutes.
    """
    from app.services import ticker_onboard as onboard

    try:
        return onboard.add_ticker(db, payload.category, payload.ticker,
                                  payload.label)
    except onboard.OnboardError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500,
                            detail=f"onboarding failed: {exc}") from exc


@router.get("/tickers/{ticker_id}/status", operation_id="getSuperTickerStatus")
@deps.tenant_scoped
def ticker_status(ticker_id: str,
                  tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    from app.services import ticker_onboard as onboard

    try:
        return onboard.bootstrap_status(ticker_id)
    except onboard.OnboardError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


# ---- the ledger -----------------------------------------------------------

@router.get("/signals", operation_id="getSuperSignals")
@deps.tenant_scoped
def signals(book: str | None = Query(default=None, pattern="^[abAB]$"),
            category: str | None = Query(default=None),
            ticker: str | None = Query(default=None),
            grade_min: int | None = Query(default=None, ge=2, le=5),
            days: int | None = Query(default=None, ge=1, le=3660),
            central: bool = Query(default=False),
            limit: int = Query(default=100, ge=1, le=2000),
            offset: int = Query(default=0, ge=0),
            tenant: Tenant = Depends(deps.current_tenant),
            db: DbSession = Depends(deps.get_db)) -> dict:
    total, items = _svc().query_signals(
        db, book=book, category=category, ticker=ticker, grade_min=grade_min,
        days=days, central=central, limit=limit, offset=offset)
    return {"total": total, "items": [
        {"id": s.id, "book": s.book, "category": s.category,
         "ticker": s.ticker, "direction": s.direction, "grade": s.grade,
         "combo": s.combo, "price": s.price, "accuracy_pct": s.accuracy_pct,
         "bar_time": s.bar_time,
         "logged_at": s.logged_at.isoformat() if s.logged_at else None,
         "archived": s.archived}
        for s in items]}


@router.get("/snapshots", operation_id="getDailySnapshots")
@deps.tenant_scoped
def snapshots(kind: str = Query(default="gex"),
              limit: int = Query(default=30, ge=1, le=366),
              tenant: Tenant = Depends(deps.current_tenant),
              db: DbSession = Depends(deps.get_db)) -> list[dict]:
    from app.domains.research.models import DailySnapshot

    rows = db.scalars(
        select(DailySnapshot)
        .where(DailySnapshot.kind == kind)
        .order_by(DailySnapshot.snapshot_date.desc())
        .limit(limit)).all()
    return [{"id": r.id, "kind": r.kind, "snapshot_date": r.snapshot_date,
             "payload": r.payload, "source_file": r.source_file,
             "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None}
            for r in rows]


# ---- ingest ---------------------------------------------------------------

@router.post("/sync", operation_id="syncSuperData")
def sync_all(include_archive: bool = Query(default=True),
             tenant: Tenant = Depends(deps.require_admin),
             db: DbSession = Depends(deps.get_db)) -> dict:
    """Force one full ingest pass now.

    The background loop runs the same pass continuously; this makes it happen
    immediately rather than doing anything the loop cannot.
    """
    return _svc().sync_everything(db, include_archive=include_archive,
                                  force=True)


@router.get("/sync/status", operation_id="getSuperSyncStatus")
@deps.tenant_scoped
def sync_status(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """Health of the ingest loop that guarantees generated signals land in
    the database."""
    return _svc().AUTO_SYNC_STATUS
