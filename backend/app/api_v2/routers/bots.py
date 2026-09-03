"""Bot station: eight operations, keyed by bot_key.

This file replaces 37 endpoints with 11. Four families each owned a
near-identical block -- status, start, stop, logs, trades, sync, processes,
kill -- differing only in which key tuple they iterated. Keyed by bot_key they
are the same eight routes, and a new bot needs none of them.

Nothing here names a bot family. If it did, adding a bot would mean editing
this file, which is the thing the onboarding contract forbids.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.api_v2 import deps
from app.domains.botstation import lifecycle, registry
from app.domains.botstation.models import BotTrade
from app.domains.trading.execution import idempotency
from app.tenancy import repository as tenants
from app.tenancy.models import Tenant

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/bots", tags=["bots"])


class StartRequest(BaseModel):
    version: str | None = None
    mode: str = "paper"
    # Free-form: validated against the BOT's own declared schema, not against
    # a model here. A field list here would have to grow for every new bot.
    model_config = {"extra": "allow"}


class StopRequest(BaseModel):
    model_config = {"extra": "allow"}


def _config_or_404(bot_key: str) -> registry.BotConfig:
    try:
        return registry.get(bot_key)
    except registry.UnknownBot as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


# ---- registry -------------------------------------------------------------

@router.get("", operation_id="listBots")
def list_bots(_: Tenant = Depends(deps.current_tenant)) -> list[dict]:
    return registry.report()


@router.get("/commodities/signals", operation_id="getCommodityDmiSignals")
@deps.tenant_scoped
def commodity_signals(interval: str = Query(default="5min"),
                      live: bool = Query(default=False),
                      force: bool = Query(default=False),
                      tenant: Tenant = Depends(deps.current_tenant),
                      db: DbSession = Depends(deps.get_db),
                      kr=Depends(deps.keyring)) -> dict:
    """Gold, silver and oil DMI for the commodity bots.

    Inside 08:30-15:00 CST Mon-Fri the reading comes from Tradier bars on the
    ETF that tracks each underlying (GLD, SLV, USO), through the SAME indicator
    the desk uses -- so the board and the bot agree about what the market is
    doing. Outside that window those ETFs are shut and their last bar is
    stale, so the futures engine answers instead.

    Every row says which source produced it. An operator looking at a gold
    signal at 7pm needs to know it came from futures rather than a closed ETF:
    they are not the same number and they do not move together overnight.

    Tenant-scoped because it now spends a credential. It did not before, which
    is why Phase 4 listed it as unscoped -- reading the venue changed that, and
    the isolation guard is what noticed.

    Declared BEFORE /{bot_key}/config so the literal path matches first and is
    never swallowed by the parameterised one.
    """
    from app.domains.trading.market import commodities

    cred = None
    try:
        cred = tenants.load_credential(
            db, tenant.id, "tradier" if live else "tradier_sandbox", kr)
    except Exception:                                   # noqa: BLE001
        # No credential is not an error here: the off-hours engine needs none,
        # and a board that 424s at 7pm would be refusing to show the data it
        # can actually get.
        pass

    try:
        return commodities.snapshot(cred, interval=interval,
                                    sandbox=not live, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/crypto/signals", operation_id="getCryptoDmiSignals")
@deps.tenant_scoped
def crypto_signals(force: bool = Query(default=False),
                   tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """BTC, ETH, SOL, DOGE and XRP on 1m/2m/5m DMI, from Coinbase.

    No credential: Coinbase's candle feed is public, so this spends nothing
    and needs nothing from the operator. It still requires a session, because
    who may read the desk is a separate question from what the data costs.

    Declared BEFORE /{bot_key}/config so the literal path matches first and is
    never swallowed by the parameterised one.
    """
    from app.domains.trading.market import crypto

    try:
        return crypto.snapshot(force=force)
    except Exception:                                   # noqa: BLE001
        logger.info("crypto board unavailable")
        return {"rows": [], "meta": {"source": "unavailable", "scanned": 0},
                "age_s": None}


@router.get("/{bot_key}/config", operation_id="getBotConfig")
def bot_config(bot_key: str,
               _: Tenant = Depends(deps.current_tenant)) -> dict:
    """What the launch form renders itself from.

    Without this a new bot would still need a hand-written UI panel, which is
    the difference between onboarding costing two files and costing six.
    """
    config = _config_or_404(bot_key)
    return {
        "bot_key": config.key,
        "name": config.name,
        "category": config.category,
        "cadence": config.cadence,
        "launch_style": config.launch_style,
        # Each MODEL carries its own resolved values, not just its name. btc15
        # v2 and v5 are different engines with different risk profiles, so a
        # form that showed one take-profit for the whole bot would be showing
        # a number that is wrong for at least one of them.
        "versions": [
            {"version": v.version, "default": v.default,
             "defaults": registry.effective_defaults(config, v)}
            for v in config.versions
        ],
        "options_schema": config.options_schema,
    }


# ---- state ----------------------------------------------------------------

@router.get("/statuses", operation_id="getAllBotStatuses")
@deps.tenant_scoped
def all_statuses(tenant: Tenant = Depends(deps.current_tenant),
                 db: DbSession = Depends(deps.get_db)) -> dict:
    """Every bot's status in ONE request, keyed by bot.

    The station shows seven bots and polls every ten seconds. Asked one at a
    time that is seven concurrent requests and seven database sessions every
    tick, which is most of the desk's steady-state load -- and it was a real
    part of what exhausted the connection pool.

    Declared BEFORE /{bot_key}/status so the literal path matches first and is
    never read as a bot named "statuses".
    """
    return {config.key: lifecycle.status(db, tenant_id=tenant.id,
                                         bot_key=config.key)
            for config in registry.all_bots()}


@router.get("/{bot_key}/status", operation_id="getBotStatus")
@deps.tenant_scoped
def bot_status(bot_key: str, tenant: Tenant = Depends(deps.current_tenant),
               db: DbSession = Depends(deps.get_db)) -> dict:
    _config_or_404(bot_key)
    return lifecycle.status(db, tenant_id=tenant.id, bot_key=bot_key)


@router.get("/{bot_key}/logs", operation_id="getBotLogs")
@deps.tenant_scoped
def bot_logs(bot_key: str, lines: int = Query(default=200, le=5000),
             tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    _config_or_404(bot_key)
    # tenant.slug, never a parameter: the log path is built from the session.
    return lifecycle.logs(tenant_slug=tenant.slug, bot_key=bot_key, lines=lines)


@router.get("/{bot_key}/processes", operation_id="getBotProcesses")
@deps.tenant_scoped
def bot_processes(bot_key: str, tenant: Tenant = Depends(deps.current_tenant),
                  db: DbSession = Depends(deps.get_db)) -> dict:
    _config_or_404(bot_key)
    return lifecycle.processes(db, tenant_id=tenant.id, bot_key=bot_key)


# ---- ledger ---------------------------------------------------------------

def _trades_query(tenant_id: str, bot_key: str, *, mode: str | None = None,
                  status: str | None = None, days: int | None = None):
    stmt = select(BotTrade).where(BotTrade.tenant_id == tenant_id,
                                  BotTrade.bot_key == bot_key)
    if mode == "live":
        stmt = stmt.where(BotTrade.is_live.is_(True))
    elif mode == "paper":
        stmt = stmt.where(BotTrade.is_live.is_(False))
    if status:
        stmt = stmt.where(BotTrade.status == status)
    if days:
        from datetime import timedelta
        from app.platform.db.base import utcnow
        stmt = stmt.where(BotTrade.opened_at >= utcnow() - timedelta(days=days))
    return stmt


@router.get("/{bot_key}/trades", operation_id="getBotTrades")
@deps.tenant_scoped
def bot_trades(bot_key: str,
               mode: str = Query(default="all"),
               status: str | None = Query(default=None),
               days: int | None = Query(default=None),
               limit: int = Query(default=200, le=2000),
               offset: int = Query(default=0, ge=0),
               tenant: Tenant = Depends(deps.current_tenant),
               db: DbSession = Depends(deps.get_db)) -> dict:
    """The ledger, per bot.

    ``unclassified`` is reported rather than hidden. Rows whose paper-or-live
    status is genuinely unknown appear under neither LIVE nor PAPER -- which
    is right, because an unverified row must not be counted as real money --
    but the old build left the two views silently not summing to the whole.
    Saying how many are unaccounted for is the honest version of the same
    rule (Phase 2 D5).
    """
    _config_or_404(bot_key)
    stmt = _trades_query(tenant.id, bot_key, mode=mode, status=status, days=days)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    unclassified = db.scalar(select(func.count()).select_from(
        _trades_query(tenant.id, bot_key, status=status, days=days)
        .where(BotTrade.is_live.is_(None)).subquery())) or 0

    rows = list(db.scalars(stmt.order_by(BotTrade.opened_at.desc())
                           .limit(limit).offset(offset)).all())
    return {
        "bot_key": bot_key,
        "items": [_trade_out(t) for t in rows],
        "total": total,
        "unclassified": unclassified,
    }


@router.get("/{bot_key}/active-bets", operation_id="getBotActiveBets")
@deps.tenant_scoped
def bot_active_bets(bot_key: str, tenant: Tenant = Depends(deps.current_tenant),
                    db: DbSession = Depends(deps.get_db)) -> dict:
    _config_or_404(bot_key)
    rows = list(db.scalars(_trades_query(tenant.id, bot_key, status="open")
                           .order_by(BotTrade.opened_at.desc())).all())
    return {"bot_key": bot_key, "items": [_trade_out(t) for t in rows]}


@router.get("/{bot_key}/performance", operation_id="getBotPerformance")
@deps.tenant_scoped
def bot_performance(bot_key: str, days: int = Query(default=30, le=3650),
                    mode: str = Query(default="all"),
                    tenant: Tenant = Depends(deps.current_tenant),
                    db: DbSession = Depends(deps.get_db)) -> dict:
    """Realised P&L over this bot's OWN ledger rows.

    Deliberately not the account-value delta the old build used. The venue
    account is shared across bots, so that number credited one bot with
    another trades -- its own docstring said so (Phase 2 D6).
    """
    _config_or_404(bot_key)
    stmt = _trades_query(tenant.id, bot_key, mode=mode, status="closed",
                         days=days)
    rows = list(db.scalars(stmt).all())
    realised = [r.realized_pnl for r in rows if r.realized_pnl is not None]
    wins = [p for p in realised if p > 0]
    return {
        "bot_key": bot_key,
        "days": days,
        "mode": mode,
        "closed_trades": len(rows),
        "priced_trades": len(realised),
        "realized_pnl": round(sum(realised), 2) if realised else 0.0,
        "win_rate": round(len(wins) / len(realised), 4) if realised else None,
        "basis": "this bot own ledger rows, not the shared account value",
    }


def _trade_out(t: BotTrade) -> dict:
    return {
        "id": t.id, "external_id": t.external_id, "ticker": t.ticker,
        "status": t.status, "opened_at": t.opened_at, "closed_at": t.closed_at,
        "contracts": t.contracts, "entry_price": t.entry_price,
        "exit_price": t.exit_price, "realized_pnl": t.realized_pnl,
        # None means genuinely unknown, and is never rendered as False.
        "is_live": t.is_live,
        "reconciled": t.reconciled_at is not None,
        "bot_version": t.bot_version,
    }


# ---- actions --------------------------------------------------------------

@router.post("/{bot_key}/start", operation_id="startBot")
@deps.tenant_scoped
def start_bot(bot_key: str, payload: StartRequest,
              idempotency_key: str | None = Header(default=None,
                                                   alias="Idempotency-Key"),
              tenant: Tenant = Depends(deps.current_tenant),
              db: DbSession = Depends(deps.get_db)) -> dict:
    config = _config_or_404(bot_key)
    body = payload.model_dump()
    options = {k: v for k, v in body.items() if k not in ("version", "mode")}

    try:
        attempt = idempotency.begin(db, tenant_id=tenant.id, intent="bot_start",
                                    payload={"bot": bot_key, **body},
                                    client_key=idempotency_key)
    except idempotency.DuplicateRequest as dup:
        db.commit()
        return idempotency.stored_result(dup.attempt) or {"bot_key": bot_key}
    except idempotency.KeyReused as exc:
        db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from None

    try:
        run = lifecycle.start(db, tenant_id=tenant.id, tenant_slug=tenant.slug,
                              bot_key=bot_key, version=payload.version,
                              options=options, mode=payload.mode)
        result = {"bot_key": bot_key, "run_id": run.id, "mode": run.mode,
                  "version": run.bot_version, "pid": run.pid,
                  "started_at": run.started_at}
        idempotency.succeed(db, attempt, result=result)
        db.commit()
        return result
    except lifecycle.BotBusy as exc:
        idempotency.fail(db, attempt, reason=str(exc))
        db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except (ValueError, KeyError) as exc:
        # Includes options that violate the bot own declared schema.
        idempotency.fail(db, attempt, reason=str(exc))
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except FileNotFoundError as exc:
        idempotency.fail(db, attempt, reason=str(exc))
        db.commit()
        raise HTTPException(status_code=424, detail=str(exc)) from None
    except Exception as exc:                            # noqa: BLE001
        idempotency.fail(db, attempt, reason=str(exc))
        db.commit()
        logger.exception("start %s failed", bot_key)
        raise HTTPException(status_code=500,
                            detail=f"could not start {bot_key}") from None


class LaunchEntry(BaseModel):
    bot_key: str
    version: str | None = None
    mode: str = "paper"
    # Per-bot overrides. Anything omitted falls through to the shared block,
    # then to the model's own defaults, then to the bot's.
    options: dict = Field(default_factory=dict)


class MultiLaunchRequest(BaseModel):
    bots: list[LaunchEntry] = Field(min_length=1, max_length=20)
    # Set once at the centre and applied to every bot that does not override
    # it -- which is the point of launching from one place.
    shared_options: dict = Field(default_factory=dict)
    mode: str = "paper"


@router.post("/launch", operation_id="launchBots")
@deps.tenant_scoped
def launch_bots(payload: MultiLaunchRequest,
                idempotency_key: str | None = Header(default=None,
                                                     alias="Idempotency-Key"),
                tenant: Tenant = Depends(deps.current_tenant),
                db: DbSession = Depends(deps.get_db)) -> dict:
    """Start several bots from one place, with per-bot overrides.

    Every bot is attempted, and one failure does NOT abandon the rest. A
    partial launch reported honestly is better than an all-or-nothing that
    silently starts three of five and then rolls back two that are already
    holding positions -- there is no rollback for an order that has been
    placed.

    Options resolve in four layers, outermost last:
        bot schema default -> model default -> shared_options -> per-bot
    """
    for entry in payload.bots:
        _config_or_404(entry.bot_key)

    started, failed = [], []
    for entry in payload.bots:
        options = {**payload.shared_options, **entry.options}
        mode = entry.mode if entry.mode != "paper" else payload.mode
        try:
            run = lifecycle.start(db, tenant_id=tenant.id,
                                  tenant_slug=tenant.slug,
                                  bot_key=entry.bot_key, version=entry.version,
                                  options=options, mode=mode)
            started.append({"bot_key": entry.bot_key, "run_id": run.id,
                            "version": run.bot_version, "mode": run.mode})
        except lifecycle.BotBusy as exc:
            failed.append({"bot_key": entry.bot_key, "reason": str(exc),
                           "already_running": True})
        except (ValueError, KeyError, FileNotFoundError) as exc:
            failed.append({"bot_key": entry.bot_key, "reason": str(exc)})
        except Exception as exc:                        # noqa: BLE001
            logger.exception("multi-launch: %s", entry.bot_key)
            failed.append({"bot_key": entry.bot_key, "reason": str(exc)})

    db.commit()
    return {"requested": len(payload.bots), "started": started,
            "failed": failed,
            "all_started": not failed}


@router.post("/{bot_key}/stop", operation_id="stopBot")
@deps.tenant_scoped
def stop_bot(bot_key: str, payload: StopRequest | None = None,
             tenant: Tenant = Depends(deps.current_tenant),
             db: DbSession = Depends(deps.get_db)) -> dict:
    _config_or_404(bot_key)
    try:
        run = lifecycle.stop(db, tenant_id=tenant.id, bot_key=bot_key)
    except lifecycle.BotNotRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except lifecycle.BotNotStopped as exc:
        # 409, and the row is left saying "running", because it is. Reporting
        # success here would tell the operator a live bot is off while it
        # keeps placing orders.
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from None
    db.commit()
    return {"bot_key": bot_key, "run_id": run.id, "stopped_at": run.stopped_at}


@router.post("/{bot_key}/kill", operation_id="killBot")
@deps.tenant_scoped
def kill_bot(bot_key: str, tenant: Tenant = Depends(deps.current_tenant),
             db: DbSession = Depends(deps.get_db)) -> dict:
    _config_or_404(bot_key)
    out = lifecycle.kill(db, tenant_id=tenant.id, bot_key=bot_key)
    db.commit()
    return out


@router.post("/{bot_key}/sync", operation_id="syncBotTrades")
@deps.tenant_scoped
def sync_bot(bot_key: str, tenant: Tenant = Depends(deps.current_tenant),
             db: DbSession = Depends(deps.get_db)) -> dict:
    """Pull this bot own records into the shared ledger.

    The adapter reads them; this route does not know their shape.
    """
    _config_or_404(bot_key)
    adapter = registry.adapter_for(bot_key)
    reader = getattr(adapter, "read_records", None)
    if reader is None:
        return {"bot_key": bot_key, "synced": 0,
                "detail": "this bot does not publish records to sync"}

    from app.domains.botstation.ledger import ingest

    records = reader(tenant_slug=tenant.slug)
    out = ingest.record(tenant_id=tenant.id, bot_key=bot_key,
                        records=records, db=db)
    db.commit()
    return {"bot_key": bot_key, **out}


@router.post("/reconcile", operation_id="reconcileBotTrades")
@deps.tenant_scoped
def reconcile(apply: bool = Query(default=True),
              tenant: Tenant = Depends(deps.current_tenant),
              db: DbSession = Depends(deps.get_db)) -> dict:
    """Close open ledger rows against what actually happened at Kalshi.

    A bot records a trade when it ENTERS and cannot record the outcome, so an
    open row means "nobody has looked since" rather than "still running".
    This asks the exchange: positions first (a non-zero holding means the
    trade really is live and is left alone), then settlements, then fills.

    Applies by default. Preview with ``apply=false``. It used to be the other
    way round -- on the grounds that rewriting P&L the operator has been
    reading deserves a confirmation -- but a reconciler nobody presses leaves
    the ledger permanently wrong, which is the failure it exists to prevent.
    """
    from app.domains.botstation import reconcile as reconciler
    from app.tenancy import repository as tenants

    try:
        cred = tenants.load_credential(db, tenant.id, "kalshi", deps.keyring())
    except Exception:                                   # noqa: BLE001
        raise HTTPException(
            status_code=424,
            detail="no Kalshi credential for this operator") from None
    try:
        return reconciler.resolve_open_trades(db, tenant.id, cred, apply=apply)
    except Exception:                                   # noqa: BLE001
        logger.info("reconcile: venue unreachable for %s", tenant.slug)
        raise HTTPException(
            status_code=424,
            detail="Kalshi could not be reached; nothing was changed") from None


class LuckPreviewRequest(BaseModel):
    min_legs: int = Field(default=5, ge=2, le=24)
    max_legs: int = Field(default=24, ge=2, le=24)
    min_leg_c: int = Field(default=60, ge=5, le=98)
    max_leg_c: int = Field(default=98, ge=6, le=99)
    min_volume_usd: float = Field(default=0, ge=0)
    # The two gates the long shot used to inherit from the regular parlay
    # engine. Omitted means the engine's own numbers -- 3c and 72h -- so the
    # default lives in one place rather than being restated here.
    max_spread_c: int | None = Field(default=None, ge=0, le=99)
    max_hours: int | None = Field(default=None, ge=1, le=720)


class LuckPlaceRequest(BaseModel):
    token: str
    # The legs the operator kept. Omitted means "all of them"; anything not
    # in the preview is refused rather than bought.
    tickers: list[str] | None = None
    min_usd: float = Field(default=5, gt=0, le=5000)
    max_usd: float = Field(default=7.5, gt=0, le=5000)
    min_legs: int = Field(default=5, ge=2, le=24)


def _kalshi_cred(db: DbSession, tenant: Tenant):
    try:
        return tenants.load_credential(db, tenant.id, "kalshi", deps.keyring())
    except Exception:                                   # noqa: BLE001
        raise HTTPException(
            status_code=424,
            detail="no Kalshi credential for this operator") from None


@router.post("/luck/preview", operation_id="previewLuckTicket")
def luck_preview(payload: LuckPreviewRequest,
                 tenant: Tenant = Depends(deps.current_tenant),
                 db: DbSession = Depends(deps.get_db)) -> dict:
    """Choose the legs and show them. Spends nothing.

    Deliberately separate from placing. This scans the whole live board, which
    takes a minute, and an operator asked to confirm a 20-leg parlay should be
    looking at the actual legs rather than at a promise about them.
    """
    from app.domains.botstation import luck

    if payload.max_legs < payload.min_legs:
        raise HTTPException(status_code=422,
                            detail="max legs is below min legs")
    cred = _kalshi_cred(db, tenant)
    # Started, not awaited. The scan runs past the tunnel's ~100s ceiling, so
    # a request that waits for it is killed by the proxy no matter what the
    # browser's timeout says.
    return {"job_id": luck.start(luck.preview, cred,
                                 min_legs=payload.min_legs,
                                 max_legs=payload.max_legs,
                                 min_leg_c=payload.min_leg_c,
                                 max_leg_c=payload.max_leg_c,
                                 min_volume_usd=payload.min_volume_usd,
                                 max_spread_c=payload.max_spread_c,
                                 max_hours=payload.max_hours),
            "status": "running"}


@router.post("/luck/place", operation_id="placeLuckTicket")
def luck_place(payload: LuckPlaceRequest,
               tenant: Tenant = Depends(deps.current_tenant),
               db: DbSession = Depends(deps.get_db)) -> dict:
    """Buy the previewed ticket. REAL MONEY.

    Takes a preview token rather than a set of legs: the operator confirms the
    thing they were shown, and a request that names its own legs would be a
    different order wearing the preview's approval.
    """
    from app.domains.botstation import luck

    if payload.max_usd < payload.min_usd:
        raise HTTPException(status_code=422,
                            detail="max $ is below min $")
    cred = _kalshi_cred(db, tenant)
    # Also a job: placing re-scans the board and may sit through a stake
    # escalation, which is longer than the preview, not shorter.
    return {"job_id": luck.start(luck.place, cred, payload.token,
                                 tenant_slug=tenant.slug,
                                 tickers=payload.tickers,
                                 min_usd=payload.min_usd,
                                 max_usd=payload.max_usd,
                                 min_legs=payload.min_legs),
            "status": "running"}


@router.get("/luck/job/{job_id}", operation_id="getLuckJob")
def luck_job(job_id: str,
             _: Tenant = Depends(deps.current_tenant)) -> dict:
    """How a preview or a placement is getting on."""
    from app.domains.botstation import luck

    out = luck.job(job_id)
    if out is None:
        raise HTTPException(status_code=404,
                            detail="no such job — it may have expired")
    return out


# The windows the desk reports P&L over. Hours, because a trading day is not
# a calendar one and "today" means different things either side of midnight.
PNL_WINDOWS = (("3h", 3), ("6h", 6), ("24h", 24),
               ("7d", 24 * 7), ("30d", 24 * 30), ("60d", 24 * 60))


@router.get("/event-log", operation_id="getTradeEventLog")
def trade_event_log(limit: int = Query(default=200, ge=1, le=2000),
                    bot_key: str | None = Query(default=None),
                    tenant: Tenant = Depends(deps.current_tenant),
                    db: DbSession = Depends(deps.get_db)) -> dict:
    """Every trade this operator's bots placed, and what it made.

    One row per trade in the terms an operator reads: which bot, which
    market, which side, what it cost, what came back, how it ended. Entry is
    cash out INCLUDING fees and exit is cash back with fees already taken, so
    exit minus entry is the money -- no separate fee column to reconcile in
    your head.

    P&L is banded by how long ago a trade CLOSED, not when it opened: a
    30-day-old position that resolved an hour ago belongs to the last hour's
    result, which is the question "how am I doing today" actually asks.
    """
    from datetime import timedelta

    from app.platform.db.base import utcnow

    rows = db.scalars(
        select(BotTrade)
        .where(BotTrade.tenant_id == tenant.id,
               *( [BotTrade.bot_key == bot_key] if bot_key else [] ))
        .order_by(BotTrade.opened_at.desc().nullslast(), BotTrade.id.desc())
        .limit(limit)).all()

    def money(value) -> float | None:
        return None if value is None else round(float(value), 2)

    OPEN = {"open"}
    WON = {"won"}
    LOST = {"lost"}

    def label(row: BotTrade) -> str:
        if row.status in OPEN:
            return "OPEN"
        if row.status in WON:
            return "WON"
        if row.status in LOST:
            return "LOST"
        return (row.status or "").upper()

    entries = [{
        "id": row.id,
        "bot": (row.bot_key or "").upper(),
        "version": row.bot_version,
        "market": row.market_title or row.ticker,
        "outcome": row.outcome or "",
        "ticker": row.ticker,
        "entry": money(row.entry_usd),
        "exit": money(row.exit_usd),
        "status": label(row),
        "pnl": money(row.realized_pnl),
        "contracts": row.contracts,
        "is_live": row.is_live,
        "opened_at": row.opened_at,
        "closed_at": row.closed_at,
    } for row in rows]

    # The windows are computed over the WHOLE ledger, not over the page the
    # desk happens to be showing -- a 30-day figure taken from the newest 200
    # rows is not a 30-day figure.
    now = utcnow()
    windows = {}
    for name, hours in PNL_WINDOWS:
        since = now - timedelta(hours=hours)
        closed = db.execute(
            select(func.count(BotTrade.id),
                   func.sum(BotTrade.realized_pnl),
                   func.sum(BotTrade.entry_usd))
            .where(BotTrade.tenant_id == tenant.id,
                   BotTrade.closed_at.is_not(None),
                   BotTrade.closed_at >= since,
                   *( [BotTrade.bot_key == bot_key] if bot_key else [] ))
        ).one()
        won = db.scalar(
            select(func.count(BotTrade.id))
            .where(BotTrade.tenant_id == tenant.id,
                   BotTrade.closed_at >= since,
                   BotTrade.status == "won",
                   *( [BotTrade.bot_key == bot_key] if bot_key else [] ))) or 0
        settled, pnl, staked = closed[0] or 0, closed[1], closed[2]
        windows[name] = {
            "settled": settled,
            "won": won,
            "lost": max(0, settled - won),
            "pnl": money(pnl) if pnl is not None else 0.0,
            "staked": money(staked) if staked is not None else 0.0,
            "roi_pct": (round(float(pnl) / float(staked) * 100, 2)
                        if pnl is not None and staked else None),
        }

    open_rows = [e for e in entries if e["status"] == "OPEN"]
    return {
        "trades": entries,
        "windows": windows,
        "open_count": len(open_rows),
        "open_staked": money(sum(e["entry"] or 0 for e in open_rows)),
    }


@router.get("/runs", operation_id="getBotRuns")
def bot_runs(limit: int = Query(default=40, ge=1, le=400),
             tenant: Tenant = Depends(deps.current_tenant),
             db: DbSession = Depends(deps.get_db)) -> dict:
    """Every launch and stop, from the run table.

    The desk kept this list in the BROWSER -- appended whenever a tab happened
    to notice a status change -- so it was empty on a new machine, wrong after
    a reload, and silent about anything that happened while nobody was
    watching. A bot exiting on its own at 3am is precisely the event that log
    exists for, and precisely the one a client-side list could never record.

    P&L per run is summed from the trades that bot opened during it, the same
    window the session tile uses.
    """
    from app.domains.botstation.models import BotRun

    runs = db.scalars(
        select(BotRun)
        .where(BotRun.tenant_id == tenant.id)
        .order_by(BotRun.id.desc())
        .limit(limit)).all()

    out = []
    for run in runs:
        scope = [BotTrade.tenant_id == tenant.id,
                 BotTrade.bot_key == run.bot_key]
        if run.started_at is not None:
            scope.append(BotTrade.opened_at >= run.started_at)
        if run.stopped_at is not None:
            scope.append(BotTrade.opened_at <= run.stopped_at)
        trades, pnl = db.execute(
            select(func.count(BotTrade.id),
                   func.coalesce(func.sum(BotTrade.realized_pnl), 0.0))
            .where(*scope)).one()
        out.append({
            "run_id": run.id,
            "bot": (run.bot_key or "").upper(),
            "bot_key": run.bot_key,
            "version": run.bot_version,
            "mode": run.mode,
            "status": run.status,
            "started_at": run.started_at,
            "stopped_at": run.stopped_at,
            # The distinction that matters at a glance: a bot the operator
            # stopped is not the same news as one that exited by itself.
            "exited_on_its_own": bool(run.stopped_at and run.exit_code is None
                                      and run.status != "stopped"),
            "exit_code": run.exit_code,
            "bankroll": run.bankroll,
            "trades": int(trades or 0),
            "pnl": round(float(pnl or 0.0), 2),
        })
    return {"runs": out}
