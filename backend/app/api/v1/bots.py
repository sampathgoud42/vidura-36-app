"""Bot control endpoints.

Literal spec paths (/bots/btc/*, /bots/sports/*) plus a shared core.  For
the BTC endpoints, ``bot`` selects btc15 (default) or btc60 since both live
under the /bots/btc umbrella.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.cloud import require_local_runtime
from app.core.config import get_settings
from app.core.database import get_db
from app.models import User
from app.schemas.bot import (
    BotInfo,
    BotLogsOut,
    BotRunOut,
    BotStartRequest,
    BotStatusOut,
    BotStopRequest,
)
from app.schemas.trade import PerformanceSummary, TradeHistoryPage, TradeOut
from app.services import bot_manager, ingest, reconcile as reconcile_svc
from app.services import trades as trades_svc
from app.services.bot_registry import BOTS, get_bot, registry_report

router = APIRouter(prefix="/bots", tags=["bots"])

BTC_KEYS = ("btc15", "btc60")
COMMODITY_KEYS = ("gold15", "silver15", "oil15")


def _user_or_404(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user


def _refresh_mirror(db: Session, user_id: str | None, bot_keys: list[str]) -> None:
    """Pull the bots' trade CSVs into the DB before answering a read.

    The trades table is a mirror of files the bots own, and it used to be
    refreshed only when someone pressed "sync" — so a position could be open
    for hours while Active Bets sat empty. TTL-guarded and non-fatal, so a
    polling UI does not re-parse constantly and a bad CSV still serves the
    rows already stored.
    """
    if not user_id:
        return  # unscoped query: no single user's files to refresh
    user = db.get(User, user_id)
    if user is None:
        return  # the read itself will return an empty page
    for key in bot_keys:
        ingest.auto_sync(db, user, key)


def _btc_key(bot: str) -> str:
    if bot not in BTC_KEYS:
        raise HTTPException(status_code=422, detail=f"bot must be one of {BTC_KEYS}")
    return bot


def _processes(bot_key: str) -> dict:
    """Every process running this bot, including ones the API never started."""
    try:
        found = bot_manager.find_bot_processes(bot_key)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"bot_key": bot_key, "count": len(found), "processes": found}


def _kill(db: Session, bot_key: str, pids: list[int] | None) -> dict:
    require_local_runtime(f"Killing {bot_key} processes")
    try:
        return bot_manager.kill_bot_processes(db, bot_key, pids=pids)
    except bot_manager.BotManagerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/btc/processes", operation_id="getBtcBotProcesses")
def btc_processes(bot: str = Query(default="btc15", description="btc15 or btc60")) -> dict:
    """Stray-process check: what is actually running on this machine."""
    return _processes(_btc_key(bot))


@router.post("/btc/kill", operation_id="killBtcBotProcesses")
def btc_kill(
    bot: str = Query(default="btc15"),
    pids: str | None = Query(default=None, description="comma-separated; omit to kill all"),
    db: Session = Depends(get_db),
) -> dict:
    """Kill every process running this BTC bot — including copies the API did
    not start. Use when a stray run blocks a start."""
    parsed = [int(p) for p in pids.split(",") if p.strip().isdigit()] if pids else None
    return _kill(db, _btc_key(bot), parsed)


@router.get("/sports/processes", operation_id="getSportsBotProcesses")
def sports_processes() -> dict:
    return _processes("sports")


@router.post("/sports/kill", operation_id="killSportsBotProcesses")
def sports_kill(
    pids: str | None = Query(default=None, description="comma-separated; omit to kill all"),
    db: Session = Depends(get_db),
) -> dict:
    parsed = [int(p) for p in pids.split(",") if p.strip().isdigit()] if pids else None
    return _kill(db, "sports", parsed)


@router.get("", operation_id="getBots", response_model=list[BotInfo])
def get_bots(db: Session = Depends(get_db)) -> list[BotInfo]:
    out = []
    for item in registry_report():
        runs = bot_manager.reconcile_runs(db, bot_key=item["key"])
        active = next((r for r in runs if r.status == "running"), None)
        out.append(
            BotInfo(
                **item,
                running=active is not None,
                active_run_id=active.id if active else None,
            )
        )
    return out


# --- shared handlers -------------------------------------------------------

def _status(db: Session, bot_key: str, user_id: str | None) -> BotStatusOut:
    runs = bot_manager.reconcile_runs(db, bot_key=bot_key, user_id=user_id)
    active = next((r for r in runs if r.status == "running"), None)
    return BotStatusOut(
        bot_key=bot_key,
        running=active is not None,
        runs=[BotRunOut.model_validate(r) for r in runs[:20]],
        # rides the status poll the pages already make, so the chip updates on
        # the same cadence as everything else and costs no extra request
        session=trades_svc.session_progress(db, active),
    )


def _start(db: Session, bot_key: str, payload: BotStartRequest) -> BotRunOut:
    require_local_runtime(f"Starting the {bot_key} bot")
    user = _user_or_404(db, payload.user_id)
    options = bot_manager.BotStartOptions(
        mode=payload.mode,
        sports=payload.sports,
        sport_settings=payload.sport_settings,
        parley=payload.parley.model_dump(exclude_none=True) if payload.parley else None,
        target_pct=payload.target_pct,
        tp_pct=payload.tp_pct,
        sl_pct=payload.sl_pct,
        bank_sl_pct=payload.bank_sl_pct,
        no_trade_times=payload.no_trade_times,
        bank=payload.bank,
        contracts=payload.contracts,
        kill_existing=payload.kill_existing,
    )
    try:
        run = bot_manager.start_bot(
            db, user, bot_key, version=payload.version, mode=payload.mode, options=options
        )
    except bot_manager.BotManagerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return BotRunOut.model_validate(run)


def _stop(db: Session, bot_key: str, payload: BotStopRequest) -> list[BotRunOut]:
    require_local_runtime(f"Stopping the {bot_key} bot")
    try:
        stopped = bot_manager.stop_bot(
            db, bot_key, user_id=payload.user_id, run_id=payload.run_id
        )
    except bot_manager.BotManagerError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return [BotRunOut.model_validate(r) for r in stopped]


def _logs(db: Session, bot_key: str, user_id: str | None, run_id: int | None, lines: int) -> BotLogsOut:
    runs = bot_manager.reconcile_runs(db, bot_key=bot_key, user_id=user_id)
    if run_id is not None:
        runs = [r for r in runs if r.id == run_id]
    if not runs:
        raise HTTPException(status_code=404, detail=f"No {bot_key} runs found")
    run = runs[0]
    return BotLogsOut(
        bot_key=bot_key,
        run_id=run.id,
        log_file=run.log_file,
        lines=bot_manager.tail_log(run, lines),
    )


# --- BTC endpoints ---------------------------------------------------------

@router.get("/btc/status", operation_id="getBtcBotStatus", response_model=list[BotStatusOut])
def btc_status(
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[BotStatusOut]:
    return [_status(db, key, user_id) for key in BTC_KEYS]


@router.post("/btc/start", operation_id="startBtcBot", response_model=BotRunOut, status_code=status.HTTP_201_CREATED)
def btc_start(
    payload: BotStartRequest,
    bot: str = Query(default="btc15", description="btc15 or btc60"),
    db: Session = Depends(get_db),
) -> BotRunOut:
    return _start(db, _btc_key(bot), payload)


@router.post("/btc/stop", operation_id="stopBtcBot", response_model=list[BotRunOut])
def btc_stop(
    payload: BotStopRequest,
    bot: str = Query(default="btc15", description="btc15 or btc60"),
    db: Session = Depends(get_db),
) -> list[BotRunOut]:
    return _stop(db, _btc_key(bot), payload)


@router.get("/btc/logs", operation_id="getBtcBotLogs", response_model=BotLogsOut)
def btc_logs(
    bot: str = Query(default="btc15"),
    user_id: str | None = Query(default=None),
    run_id: int | None = Query(default=None),
    lines: int = Query(default=100, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> BotLogsOut:
    return _logs(db, _btc_key(bot), user_id, run_id, lines)


@router.get("/btc/trades", operation_id="getBtcTrades", response_model=TradeHistoryPage)
def btc_trades(
    user_id: str | None = Query(default=None),
    bot: str | None = Query(default=None, description="filter: btc15 or btc60"),
    days: int | None = Query(default=None, ge=1, le=3660),
    mode: str = Query(default="live", pattern="^(live|paper|all)$",
                      description="live = real money only (default), paper, or all"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> TradeHistoryPage:
    keys = [_btc_key(bot)] if bot else list(BTC_KEYS)
    _refresh_mirror(db, user_id, keys)
    total, items = trades_svc.query_trades(
        db, user_id=user_id, bot_key=keys, days=days, mode=mode,
        limit=limit, offset=offset
    )
    return TradeHistoryPage(total=total, items=[TradeOut.model_validate(t) for t in items])


@router.post("/btc/sync-trades", operation_id="syncBtcTrades")
def btc_sync_trades(
    user_id: str = Query(...),
    bot: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict]:
    user = _user_or_404(db, user_id)
    keys = [_btc_key(bot)] if bot else list(BTC_KEYS)
    return [ingest.sync_trades(db, user, key) for key in keys]


# --- sports endpoints ------------------------------------------------------

@router.get("/sports/config", operation_id="getSportsBotConfig")
def sports_config(db: Session = Depends(get_db)) -> dict:
    """Non-secret sports engine configuration, served from the DB mirror of
    the tracked env file (ingested by the sync bridge; secret-looking keys
    are stripped at ingest)."""
    from app.services import super_research as super_svc

    settings = get_settings()
    config = super_svc.latest_payload(db, "sports_env")
    if config is None:
        super_svc._bridge_once(db)
        config = super_svc.latest_payload(db, "sports_env") or {}
    spec = get_bot("sports")
    return {
        "bot": spec.name,
        "versions": [v.version for v in spec.versions],
        "config": config,
        "paper_only_server": settings.paper_only,
    }


@router.get("/sports/status", operation_id="getSportsBotStatus", response_model=BotStatusOut)
def sports_status(
    user_id: str | None = Query(default=None), db: Session = Depends(get_db)
) -> BotStatusOut:
    return _status(db, "sports", user_id)


@router.post("/sports/start", operation_id="startSportsBot", response_model=BotRunOut, status_code=status.HTTP_201_CREATED)
def sports_start(payload: BotStartRequest, db: Session = Depends(get_db)) -> BotRunOut:
    return _start(db, "sports", payload)


@router.post("/sports/stop", operation_id="stopSportsBot", response_model=list[BotRunOut])
def sports_stop(payload: BotStopRequest, db: Session = Depends(get_db)) -> list[BotRunOut]:
    return _stop(db, "sports", payload)


@router.get("/sports/logs", operation_id="getSportsBotLogs", response_model=BotLogsOut)
def sports_logs(
    user_id: str | None = Query(default=None),
    run_id: int | None = Query(default=None),
    lines: int = Query(default=100, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> BotLogsOut:
    return _logs(db, "sports", user_id, run_id, lines)


@router.get("/sports/active-bets", operation_id="getSportsActiveBets", response_model=list[TradeOut])
def sports_active_bets(
    user_id: str | None = Query(default=None), db: Session = Depends(get_db)
) -> list[TradeOut]:
    _refresh_mirror(db, user_id, ["sports"])
    open_trades = trades_svc.active_trades(db, user_id=user_id, bot_key="sports")
    return [TradeOut.model_validate(t) for t in open_trades]


@router.post("/reconcile", operation_id="reconcileOpenTrades")
def reconcile_open_trades(
    user_id: str = Query(..., description="whose ledger to reconcile"),
    hours: int = Query(default=reconcile_svc.DEFAULT_STALE_HOURS, ge=1, le=720,
                       description="only rows open longer than this are checked"),
    apply: bool = Query(default=False,
                        description="false previews the plan; true writes it"),
    db: Session = Depends(get_db),
) -> dict:
    """Close ledger rows still `open` that Kalshi says are finished.

    Covers every family on the Kalshi account (btc15, btc60, btcperp, sports).
    A row is only touched when it is BOTH older than `hours` AND absent from
    the account's active positions; its P&L is then taken from fills +
    settlements, not from the bot's own estimate.

    Previews by default — it rewrites booked P&L, so seeing the plan and
    applying it are deliberately two calls.
    """
    require_local_runtime("Reconciling trades against Kalshi")
    user = _user_or_404(db, user_id)
    # Pull the CSVs in first: a row the bot closed but never synced should be
    # settled from its own ledger, not re-derived from the exchange.
    _refresh_mirror(db, user_id, ["btc15", "btc60", "sports", "parley", "gold15", "silver15", "oil15"])
    try:
        return reconcile_svc.reconcile(db, user, hours=hours, dry_run=not apply)
    except reconcile_svc.ReconcileError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:                      # noqa: BLE001
        # Kalshi API errors mid-pass surface as a gateway problem, not a 500;
        # per-row commits mean finished corrections are already saved.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail=f"exchange error mid-pass: {exc}") from exc


@router.get("/sports/performance", operation_id="getSportsPerformance", response_model=PerformanceSummary)
def sports_performance(
    user_id: str | None = Query(default=None),
    days: int | None = Query(default=None, ge=1, le=3660),
    mode: str = Query(default="live", pattern="^(live|paper|all)$",
                      description="must match the trade-history view, or the "
                                  "scoreboard totals a different set of rows than it lists"),
    db: Session = Depends(get_db),
) -> PerformanceSummary:
    _refresh_mirror(db, user_id, ["sports"])
    return trades_svc.performance(db, user_id=user_id, bot_key="sports", days=days, mode=mode)


@router.get("/sports/trades", operation_id="getSportsTrades", response_model=TradeHistoryPage)
def sports_trades(
    user_id: str | None = Query(default=None),
    days: int | None = Query(default=None, ge=1, le=3660),
    mode: str = Query(default="live", pattern="^(live|paper|all)$",
                      description="live = real money only (default), paper, or all"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> TradeHistoryPage:
    _refresh_mirror(db, user_id, ["sports"])
    total, items = trades_svc.query_trades(
        db, user_id=user_id, bot_key="sports", days=days, mode=mode,
        limit=limit, offset=offset
    )
    return TradeHistoryPage(total=total, items=[TradeOut.model_validate(t) for t in items])


@router.post("/sports/sync-trades", operation_id="syncSportsTrades")
def sports_sync_trades(user_id: str = Query(...), db: Session = Depends(get_db)) -> dict:
    user = _user_or_404(db, user_id)
    return ingest.sync_trades(db, user, "sports")


# --- parlay endpoints ------------------------------------------------------
# Its own spec path rather than a version of /bots/sports/*: it is a separate
# process with its own bankroll, ledger and CSV, and it can run alongside the
# sports bot. Sharing that path would have made "stop sports" ambiguous.

@router.get("/parley/processes", operation_id="getParleyBotProcesses")
def parley_processes() -> dict:
    return _processes("parley")


@router.post("/parley/kill", operation_id="killParleyBotProcesses")
def parley_kill(
    pids: str | None = Query(default=None, description="comma-separated; omit to kill all"),
    db: Session = Depends(get_db),
) -> dict:
    parsed = [int(p) for p in pids.split(",") if p.strip().isdigit()] if pids else None
    return _kill(db, "parley", parsed)


@router.get("/parley/status", operation_id="getParleyBotStatus", response_model=BotStatusOut)
def parley_status(
    user_id: str | None = Query(default=None), db: Session = Depends(get_db)
) -> BotStatusOut:
    return _status(db, "parley", user_id)


@router.post("/parley/start", operation_id="startParleyBot", response_model=BotRunOut,
             status_code=status.HTTP_201_CREATED)
def parley_start(payload: BotStartRequest, db: Session = Depends(get_db)) -> BotRunOut:
    return _start(db, "parley", payload)


@router.post("/parley/stop", operation_id="stopParleyBot", response_model=list[BotRunOut])
def parley_stop(payload: BotStopRequest, db: Session = Depends(get_db)) -> list[BotRunOut]:
    return _stop(db, "parley", payload)


@router.get("/parley/logs", operation_id="getParleyBotLogs", response_model=BotLogsOut)
def parley_logs(
    user_id: str | None = Query(default=None),
    run_id: int | None = Query(default=None),
    lines: int = Query(default=100, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> BotLogsOut:
    return _logs(db, "parley", user_id, run_id, lines)


@router.get("/parley/trades", operation_id="getParleyTrades", response_model=TradeHistoryPage)
def parley_trades(
    user_id: str | None = Query(default=None),
    days: int | None = Query(default=None, ge=1, le=3660),
    mode: str = Query(default="live", pattern="^(live|paper|all)$",
                      description="live = real money only (default), paper, or all"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> TradeHistoryPage:
    _refresh_mirror(db, user_id, ["parley"])
    total, items = trades_svc.query_trades(
        db, user_id=user_id, bot_key="parley", days=days, mode=mode,
        limit=limit, offset=offset
    )
    return TradeHistoryPage(total=total, items=[TradeOut.model_validate(t) for t in items])


@router.get("/parley/active-bets", operation_id="getParleyActiveBets", response_model=list[TradeOut])
def parley_active_bets(
    user_id: str | None = Query(default=None), db: Session = Depends(get_db)
) -> list[TradeOut]:
    _refresh_mirror(db, user_id, ["parley"])
    return [
        TradeOut.model_validate(t)
        for t in trades_svc.active_trades(db, user_id=user_id, bot_key="parley")
    ]


@router.post("/parley/sync-trades", operation_id="syncParleyTrades")
def parley_sync_trades(user_id: str = Query(...), db: Session = Depends(get_db)) -> dict:
    user = _user_or_404(db, user_id)
    return ingest.sync_trades(db, user, "parley")


# --- commodity endpoints (gold15, silver15) --------------------------------
# Same shape as the BTC umbrella: a single bot= query param selects gold15 or
# silver15 under the /bots/commodities/* path.

def _commodity_key(bot: str) -> str:
    if bot not in COMMODITY_KEYS:
        raise HTTPException(status_code=422, detail=f"bot must be one of {COMMODITY_KEYS}")
    return bot


@router.get("/commodities/processes", operation_id="getCommodityBotProcesses")
def commodity_processes(bot: str = Query(default="gold15", description="gold15 or silver15")) -> dict:
    return _processes(_commodity_key(bot))


@router.get("/commodities/signals", operation_id="getCommodityDmiSignals")
def commodity_signals(force: bool = Query(default=False)) -> dict:
    """Live gold/silver/oil DMI call-put readout — the v2 engine's signal,
    read-only, for the bot-station desk (no process control involved)."""
    from app.services.commodity_signals import commodities_snapshot

    return commodities_snapshot(force=force)


@router.post("/commodities/kill", operation_id="killCommodityBotProcesses")
def commodity_kill(
    bot: str = Query(default="gold15"),
    pids: str | None = Query(default=None, description="comma-separated; omit to kill all"),
    db: Session = Depends(get_db),
) -> dict:
    parsed = [int(p) for p in pids.split(",") if p.strip().isdigit()] if pids else None
    return _kill(db, _commodity_key(bot), parsed)


@router.get("/commodities/status", operation_id="getCommodityBotStatus", response_model=list[BotStatusOut])
def commodity_status(
    user_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[BotStatusOut]:
    return [_status(db, key, user_id) for key in COMMODITY_KEYS]


@router.post("/commodities/start", operation_id="startCommodityBot", response_model=BotRunOut,
             status_code=status.HTTP_201_CREATED)
def commodity_start(
    payload: BotStartRequest,
    bot: str = Query(default="gold15", description="gold15 or silver15"),
    db: Session = Depends(get_db),
) -> BotRunOut:
    return _start(db, _commodity_key(bot), payload)


@router.post("/commodities/stop", operation_id="stopCommodityBot", response_model=list[BotRunOut])
def commodity_stop(
    payload: BotStopRequest,
    bot: str = Query(default="gold15", description="gold15 or silver15"),
    db: Session = Depends(get_db),
) -> list[BotRunOut]:
    return _stop(db, _commodity_key(bot), payload)


@router.get("/commodities/logs", operation_id="getCommodityBotLogs", response_model=BotLogsOut)
def commodity_logs(
    bot: str = Query(default="gold15"),
    user_id: str | None = Query(default=None),
    run_id: int | None = Query(default=None),
    lines: int = Query(default=100, ge=1, le=2000),
    db: Session = Depends(get_db),
) -> BotLogsOut:
    return _logs(db, _commodity_key(bot), user_id, run_id, lines)


@router.get("/commodities/trades", operation_id="getCommodityTrades", response_model=TradeHistoryPage)
def commodity_trades(
    user_id: str | None = Query(default=None),
    bot: str | None = Query(default=None, description="filter: gold15 or silver15"),
    days: int | None = Query(default=None, ge=1, le=3660),
    mode: str = Query(default="live", pattern="^(live|paper|all)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> TradeHistoryPage:
    keys = [_commodity_key(bot)] if bot else list(COMMODITY_KEYS)
    _refresh_mirror(db, user_id, keys)
    total, items = trades_svc.query_trades(
        db, user_id=user_id, bot_key=keys, days=days, mode=mode,
        limit=limit, offset=offset
    )
    return TradeHistoryPage(total=total, items=[TradeOut.model_validate(t) for t in items])


@router.post("/commodities/sync-trades", operation_id="syncCommodityTrades")
def commodity_sync_trades(
    user_id: str = Query(...),
    bot: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict]:
    user = _user_or_404(db, user_id)
    keys = [_commodity_key(bot)] if bot else list(COMMODITY_KEYS)
    return [ingest.sync_trades(db, user, key) for key in keys]
