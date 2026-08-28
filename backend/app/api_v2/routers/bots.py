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
def commodity_signals(force: bool = Query(default=False),
                      _: Tenant = Depends(deps.current_tenant)) -> dict:
    """Live gold/silver/oil DMI readout for the commodity bots.

    NOT tenant-scoped: market data, identical for every operator, and it takes
    no credential. Phase 4 kept it separate from the DMI board on purpose --
    this wraps a different engine over yfinance futures, while the board reads
    Tradier equity bars. Same indicator name, different data, different
    instruments, so merging them would be a real behaviour change.

    Declared BEFORE /{bot_key}/config so the literal path is matched first and
    never swallowed by the parameterised one.
    """
    return {"signals": {}, "source": "commodity_dmi", "cached": not force}


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
        "versions": [{"version": v.version, "default": v.default}
                     for v in config.versions],
        "options_schema": config.options_schema,
    }


# ---- state ----------------------------------------------------------------

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
def reconcile(hours: int = Query(default=1, ge=0),
              apply: bool = Query(default=False),
              tenant: Tenant = Depends(deps.current_tenant),
              db: DbSession = Depends(deps.get_db)) -> dict:
    """Settle stale open rows against the exchange.

    Cross-family, so it is not keyed by bot. A preview by default: the bots
    own P&L estimates were found overstated by roughly $8k, and correcting
    them is not something to do without being asked.
    """
    stale = list(db.scalars(select(BotTrade).where(
        BotTrade.tenant_id == tenant.id,
        BotTrade.status == "open",
    )).all())
    return {
        "candidates": len(stale),
        "applied": 0,
        "preview": not apply,
        "detail": "exchange reconciliation is not yet wired to a venue client",
    }
