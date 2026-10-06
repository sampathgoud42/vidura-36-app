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
from app.domains.botstation.parley.models import MAX_COMBO_LEGS
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
    """The crypto board on 2m/5m/10m/15m/30m DMI, from Coinbase. The signal is
    2m, 5m and 15m agreeing; 30m agreeing too is the confirmation (✓).

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


# ---- signal trades: a strip's CALL/PUT, bought on its 15-minute market ------
#
# Declared here, before every /{bot_key}/... route, so these literal paths are
# matched first: /{bot_key}/trades would otherwise read "signal-trade" as a
# bot. See domains/botstation/signal_trade.py for the trading rules.

class SignalPreviewRequest(BaseModel):
    asset: str = Field(min_length=1, max_length=16)
    # "call" | "put". Anything else -- the strip's "mixed" -- is not a signal,
    # and the preview says so rather than this model refusing it: the form
    # opens on mixed precisely to show that answer.
    signal: str | None = Field(default=None, max_length=8)
    confirms: bool = False


class SignalPlaceRequest(BaseModel):
    asset: str = Field(min_length=1, max_length=16)
    signal: str = Field(min_length=1, max_length=8)
    confirms: bool = False
    ticker: str = Field(min_length=3, max_length=64)
    contracts: int = Field(default=10, ge=1, le=100)
    # RISKY-BUY: bought whatever the bid, and nothing watches it.
    risky: bool = False


@router.post("/signal-trade/preview", operation_id="previewSignalTrade")
@deps.tenant_scoped
def signal_trade_preview(payload: SignalPreviewRequest,
                         tenant: Tenant = Depends(deps.current_tenant),
                         db: DbSession = Depends(deps.get_db)) -> dict:
    """What a signal would buy, right now: the asset's current fifteen-minute
    market, the side (CALL is YES, PUT is NO), its bid against the 35-70c
    range, the take-profit and stop-loss, and the cash on the shard it settles
    on. Sends nothing."""
    from app.domains.botstation import signal_trade
    from app.domains.botstation.venue import KalshiUnavailable

    cred = _kalshi_cred(db, tenant)
    try:
        return signal_trade.preview(cred, asset=payload.asset,
                                    signal=payload.signal,
                                    confirms=payload.confirms)
    except KalshiUnavailable as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from None
    except Exception:                                   # noqa: BLE001
        logger.info("signal trade preview: Kalshi unreachable for %s", tenant.slug)
        raise HTTPException(status_code=424,
                            detail="Kalshi could not be reached") from None


@router.post("/signal-trade/place", operation_id="placeSignalTrade")
@deps.tenant_scoped
def signal_trade_place(payload: SignalPlaceRequest,
                       idempotency_key: str | None = Header(
                           default=None, alias="Idempotency-Key"),
                       tenant: Tenant = Depends(deps.current_tenant),
                       db: DbSession = Depends(deps.get_db),
                       kr=Depends(deps.keyring)) -> dict:
    """Buy the confirmed signal at market and start watching it. REAL MONEY.

    Everything the form showed is checked again first -- the signal, the
    quarter, the bid range, the time left -- and a refusal says which.

    The Idempotency-Key is required and is the CONFIRMATION's: the form mints
    one when it opens and sends it on every attempt, so a retry after a lost
    response returns the first answer instead of buying twice."""
    from app.domains.botstation import signal_trade
    from app.domains.botstation.venue import KalshiUnavailable

    key = (idempotency_key or "").strip()
    if not 8 <= len(key) <= 64:
        raise HTTPException(status_code=422,
                            detail="an Idempotency-Key header (8-64 characters) "
                                   "is required to place a signal trade")
    cred = _kalshi_cred(db, tenant)
    tradier = None
    try:
        # The same credential the commodity board reads with, so the signal
        # re-checked here is the one the strip showed.
        tradier = tenants.load_credential(db, tenant.id, "tradier_sandbox", kr)
    except Exception:                                   # noqa: BLE001
        pass
    try:
        return signal_trade.place(
            db, cred, tenant=tenant, asset=payload.asset, signal=payload.signal,
            ticker=payload.ticker, contracts=payload.contracts,
            request_id=key, confirms=payload.confirms,
            tradier_cred=tradier, risky=payload.risky)
    except signal_trade.SignalTradeRefused as exc:
        return {"placed": False, "detail": str(exc)}
    except KalshiUnavailable as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from None


class Combo15Leg(BaseModel):
    ticker: str = Field(min_length=3, max_length=64)
    side: str = Field(pattern="^(yes|no)$")


class Combo15PlaceRequest(BaseModel):
    legs: list[Combo15Leg] = Field(min_length=2, max_length=MAX_COMBO_LEGS)
    # Default $5, at most $99: the form's own bounds, checked again here.
    stake_usd: float = Field(default=5, gt=0, le=99)


@router.post("/combo15/preview", operation_id="previewCombo15")
@deps.tenant_scoped
def combo15_preview(tenant: Tenant = Depends(deps.current_tenant),
                    db: DbSession = Depends(deps.get_db),
                    kr=Depends(deps.keyring)) -> dict:
    """Every fifteen-minute market a combo can hold right now, crypto and
    commodities: the quarter trading now, the side its DMI points, its quote,
    and whether it is ticked by default (DMI under five minutes old, CALL or
    PUT, bid 35-90c, at most 5c wide). Sends nothing."""
    from app.domains.botstation import combo15

    cred = _kalshi_cred(db, tenant)
    tradier = None
    try:
        # The credential the commodity board reads with, so the signals here
        # are the ones its strip shows.
        tradier = tenants.load_credential(db, tenant.id, "tradier_sandbox", kr)
    except Exception:                                   # noqa: BLE001
        pass
    try:
        return combo15.preview(cred, tradier_cred=tradier)
    except Exception:                                   # noqa: BLE001
        logger.info("combo15 preview: Kalshi unreachable for %s", tenant.slug)
        raise HTTPException(status_code=424,
                            detail="Kalshi could not be reached") from None


@router.post("/combo15/place", operation_id="placeCombo15")
@deps.tenant_scoped
def combo15_place(payload: Combo15PlaceRequest,
                  idempotency_key: str | None = Header(
                      default=None, alias="Idempotency-Key"),
                  tenant: Tenant = Depends(deps.current_tenant),
                  db: DbSession = Depends(deps.get_db)) -> dict:
    """Buy the ticked fifteen-minute legs as one combo. REAL MONEY.

    Each leg is read again first -- still open, more than a minute to run,
    quoted on its side -- and the combo collection must still host it. The
    Idempotency-Key is the confirmation's: a retry gets the first answer.

    Answers at once with {job, status}; the result is read from
    GET /combo15/place/{key} -- a combo is several Kalshi round trips and an
    RFQ wait, which outran the browser's timeout inside one request."""
    from app.domains.botstation import combo15

    key = (idempotency_key or "").strip()
    if not 8 <= len(key) <= 64:
        raise HTTPException(status_code=422,
                            detail="an Idempotency-Key header (8-64 characters) "
                                   "is required to place a combo")
    cred = _kalshi_cred(db, tenant)
    # Started, not awaited: the answer is read from /combo15/place/{key}.
    # See combo15.start_place for why a combo cannot sit inside one request.
    return combo15.start_place(cred, legs=[leg.model_dump() for leg in payload.legs],
                               stake_usd=payload.stake_usd, key=key,
                               owner=tenant.id, tenant_slug=tenant.slug)


@router.get("/combo15/place/{key}", operation_id="getCombo15Placement")
@deps.tenant_scoped
def combo15_placement(key: str, tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """Where a combo placement stands: running, or done with its result."""
    from app.domains.botstation import combo15

    job = combo15.job_status(tenant.id, key.strip())
    if job is None:
        raise HTTPException(status_code=404, detail="no combo placement under that key")
    return job


@router.get("/signal-trades", operation_id="listSignalTrades")
@deps.tenant_scoped
def signal_trades(tenant: Tenant = Depends(deps.current_tenant),
                  db: DbSession = Depends(deps.get_db)) -> dict:
    """This operator's signal trades: the ones being watched, then the most
    recent finished ones, with what each one did."""
    from app.domains.botstation import signal_trade

    return {"trades": signal_trade.trades(db, tenant)}


# ---- Kalshi shards: where the account's cash sits, and moving it ------------
#
# Every 15-minute market settles on shard 2 and spends only that shard's cash.
# These read the balances per shard and move cash between them, inside the
# operator's own account. See domains/botstation/shards.py.

class ShardTransferRequest(BaseModel):
    usd: float = Field(gt=0, le=100_000)
    source_shard: int = Field(default=0, ge=0, le=100)
    destination_shard: int = Field(default=2, ge=0, le=100)


@router.get("/kalshi/shards", operation_id="getKalshiShards")
@deps.tenant_scoped
def kalshi_shards(tenant: Tenant = Depends(deps.current_tenant),
                  db: DbSession = Depends(deps.get_db)) -> dict:
    """Cash on each of this operator's Kalshi exchange shards, and the latest
    transfers between them (Kalshi's own included)."""
    from app.domains.botstation import shards
    from app.domains.botstation.venue import KalshiUnavailable

    cred = _kalshi_cred(db, tenant)
    try:
        return shards.snapshot(cred)
    except KalshiUnavailable as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from None
    except Exception:                                   # noqa: BLE001
        raise HTTPException(status_code=424,
                            detail="Kalshi could not be reached") from None


@router.post("/kalshi/shards/transfer", operation_id="transferKalshiShardCash")
@deps.tenant_scoped
def kalshi_shard_transfer(payload: ShardTransferRequest,
                          idempotency_key: str | None = Header(
                              default=None, alias="Idempotency-Key"),
                          tenant: Tenant = Depends(deps.current_tenant),
                          db: DbSession = Depends(deps.get_db)) -> dict:
    """Move cash between two of this operator's Kalshi shards. REAL MONEY,
    inside the operator's own account.

    The Idempotency-Key is the confirmation's: the exchange's transfer takes
    none of its own and is never retried, so this key is what keeps a repeated
    confirmation from moving the money twice."""
    from app.domains.botstation import shards
    from app.domains.botstation.venue import KalshiUnavailable

    key = (idempotency_key or "").strip()
    if not 8 <= len(key) <= 64:
        raise HTTPException(status_code=422,
                            detail="an Idempotency-Key header (8-64 characters) "
                                   "is required to move money")
    cred = _kalshi_cred(db, tenant)
    try:
        return shards.transfer(cred, usd=payload.usd, source=payload.source_shard,
                               destination=payload.destination_shard, key=key,
                               owner=tenant.id)
    except shards.TransferRefused as exc:
        return {"moved": False, "detail": str(exc)}
    except KalshiUnavailable as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from None


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

def _since_launch_for_running(db: DbSession, tenant: Tenant) -> dict:
    """Each running bot's EXCHANGE-side result since it was launched.

    Read here rather than inside lifecycle.status because this is the layer
    that holds a credential -- and read ONCE for every bot rather than per
    bot, because seven tiles asking Kalshi the same two questions on a
    ten-second poll is fourteen round trips for two answers.

    Best-effort throughout: an operator with no Kalshi credential, or an
    exchange having a bad minute, gets a station that still renders. The
    figure goes missing; nothing else does.
    """
    from app.domains.botstation import since_launch

    try:
        cred = tenants.load_credential(db, tenant.id, "kalshi",
                                       deps.keyring())
    except Exception:                                   # noqa: BLE001
        return {}

    runs = {}
    for config in registry.all_bots():
        run = lifecycle.running_run(db, tenant.id, config.key)
        if run is not None:
            runs[config.key] = (config, run.started_at, run.bankroll)
    if not runs:
        return {}
    try:
        return since_launch.for_running_bots(cred, cache_key=str(tenant.id),
                                             runs=runs)
    except Exception as exc:                            # noqa: BLE001
        logger.info("since-launch unavailable: %s: %s",
                    type(exc).__name__, exc)
        return {}


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
    out = {config.key: lifecycle.status(db, tenant_id=tenant.id,
                                        bot_key=config.key)
           for config in registry.all_bots()}
    for bot_key, figure in _since_launch_for_running(db, tenant).items():
        if bot_key in out:
            out[bot_key]["since_launch"] = figure
    return out


@router.get("/{bot_key}/status", operation_id="getBotStatus")
@deps.tenant_scoped
def bot_status(bot_key: str, tenant: Tenant = Depends(deps.current_tenant),
               db: DbSession = Depends(deps.get_db)) -> dict:
    _config_or_404(bot_key)
    out = lifecycle.status(db, tenant_id=tenant.id, bot_key=bot_key)
    # The same figure the station's combined poll carries, so a single-bot
    # request and the all-bots request never disagree about a percentage.
    figure = _since_launch_for_running(db, tenant).get(bot_key)
    if figure is not None:
        out["since_launch"] = figure
    return out


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
    min_legs: int = Field(default=5, ge=2, le=MAX_COMBO_LEGS)
    max_legs: int = Field(default=24, ge=2, le=MAX_COMBO_LEGS)
    min_leg_c: int = Field(default=67, ge=5, le=98)
    max_leg_c: int = Field(default=97, ge=6, le=99)
    min_volume_usd: float = Field(default=0, ge=0)
    # The two gates the long shot used to inherit from the regular parlay
    # engine. Omitted means the engine's own numbers -- 3c and 72h -- so the
    # default lives in one place rather than being restated here.
    max_spread_c: int | None = Field(default=None, ge=0, le=99)
    max_hours: int | None = Field(default=None, ge=1, le=720)
    # Every leg from its NO side, game props included. Every other gate above
    # -- price band, volume floor, spread, horizon -- applies as sent.
    no_side_only: bool = False
    # The sports to scan, as GET /bots/luck/sports names them. Omitted or
    # empty is every sport, including one that opened after they were listed.
    sports: list[str] | None = Field(default=None, max_length=60)


class LuckPlaceRequest(BaseModel):
    token: str
    # The legs the operator kept. Omitted means "all of them"; anything not
    # in the preview is refused rather than bought.
    tickers: list[str] | None = None
    min_usd: float = Field(default=5, gt=0, le=5000)
    max_usd: float = Field(default=7.5, gt=0, le=5000)
    min_legs: int = Field(default=5, ge=2, le=MAX_COMBO_LEGS)


def _kalshi_cred(db: DbSession, tenant: Tenant):
    try:
        return tenants.load_credential(db, tenant.id, "kalshi", deps.keyring())
    except Exception:                                   # noqa: BLE001
        raise HTTPException(
            status_code=424,
            detail="no Kalshi credential for this operator") from None


@router.post("/luck/preview", operation_id="previewLuckTicket")
@deps.tenant_scoped
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
                                 job_owner=tenant.id, owner=tenant.id,
                                 min_legs=payload.min_legs,
                                 max_legs=payload.max_legs,
                                 min_leg_c=payload.min_leg_c,
                                 max_leg_c=payload.max_leg_c,
                                 min_volume_usd=payload.min_volume_usd,
                                 max_spread_c=payload.max_spread_c,
                                 max_hours=payload.max_hours,
                                 no_side_only=payload.no_side_only,
                                 sports=[s[:40] for s in payload.sports or []]),
            "status": "running"}


@router.post("/luck/place", operation_id="placeLuckTicket")
@deps.tenant_scoped
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
                                 job_owner=tenant.id, owner=tenant.id,
                                 tenant_slug=tenant.slug,
                                 tickers=payload.tickers,
                                 min_usd=payload.min_usd,
                                 max_usd=payload.max_usd,
                                 min_legs=payload.min_legs),
            "status": "running"}


@router.get("/luck/job/{job_id}", operation_id="getLuckJob")
@deps.tenant_scoped
def luck_job(job_id: str,
             tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """How a preview or a placement is getting on -- for the operator who
    started it. Another operator's job id is not found, exactly as a job that
    never existed: a result can hold legs, stakes and fills."""
    from app.domains.botstation import luck

    out = luck.job(job_id, owner=tenant.id)
    if out is None:
        raise HTTPException(status_code=404,
                            detail="no such job — it may have expired")
    return out


class LuckScheduleTicket(LuckPreviewRequest):
    """The ticket a scheduled run builds: the preview's settings and the
    spend range placing takes."""
    min_usd: float = Field(default=5, gt=0, le=5000)
    max_usd: float = Field(default=7.5, gt=0, le=5000)


class LuckScheduleRequest(BaseModel):
    enabled: bool
    # The form's settings, saved as the ticket the schedule places. Needed to
    # switch it on the first time; omitted, the saved ticket is kept.
    config: LuckScheduleTicket | None = None


@router.get("/luck/schedule", operation_id="getLuckSchedule")
@deps.tenant_scoped
def luck_schedule_get(tenant: Tenant = Depends(deps.current_tenant),
                      db: DbSession = Depends(deps.get_db)) -> dict:
    """The operator's scheduled Luck parley: on or off, the ticket it places,
    when it next runs (9:00 and 18:00 Chicago time) and its latest runs."""
    from app.domains.botstation import luck_schedule

    return luck_schedule.get_state(db, tenant.id)


@router.put("/luck/schedule", operation_id="setLuckSchedule")
@deps.tenant_scoped
def luck_schedule_set(payload: LuckScheduleRequest,
                      tenant: Tenant = Depends(deps.current_tenant),
                      db: DbSession = Depends(deps.get_db)) -> dict:
    """Switch the scheduled Luck parley on or off, and set its ticket.

    Real money while it is on: at each slot, with at least the ticket's most
    spend on the combo shards, a ticket is built and placed in the
    background, with nobody there to confirm it.
    """
    from app.domains.botstation import luck_schedule

    config = None
    if payload.config is not None:
        if payload.config.max_legs < payload.config.min_legs:
            raise HTTPException(status_code=422, detail="max legs is below min legs")
        if payload.config.max_usd < payload.config.min_usd:
            raise HTTPException(status_code=422, detail="max spend is below min spend")
        config = payload.config.model_dump()
        config["sports"] = [s.strip().lower()[:40] for s in config.get("sports") or []
                            if s and s.strip()]
    try:
        return luck_schedule.set_state(db, tenant.id, enabled=payload.enabled,
                                       config=config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/luck/sports", operation_id="getLuckSports")
@deps.tenant_scoped
def luck_sports(tenant: Tenant = Depends(deps.current_tenant),
                db: DbSession = Depends(deps.get_db)) -> dict:
    """The sports with something open now, for the ticket's sport picker.

    Market data read through the operator's own key; it names nobody.
    """
    from app.domains.botstation import luck

    cred = _kalshi_cred(db, tenant)
    try:
        return {"sports": luck.sports_in_play(cred)}
    except Exception:                                   # noqa: BLE001
        raise HTTPException(
            status_code=424,
            detail="Kalshi could not be reached for the sports list") from None


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
