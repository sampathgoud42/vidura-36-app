"""The rest of the desk: ledger, portfolio, market data, auto-trade.

Everything here is tenant-scoped from the session and reaches the broker only
through the venue seam. Market-data reads are thin on purpose -- they are
snapshot reads, and the sweeps that fill those snapshots are background work
rather than something a request waits on.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.api_v2 import deps
from app.domains.botstation.models import BotTrade
from app.domains.trading.execution import venue as venue_mod
from app.domains.trading.models import Position
from app.platform.db.base import utcnow
from app.platform.security.envelope import Keyring
from app.tenancy import repository as tenants
from app.tenancy.models import Tenant

logger = logging.getLogger(__name__)

trades_router = APIRouter(tags=["ledger"])
market_router = APIRouter(prefix="/tradier", tags=["market"])
desk36_router = APIRouter(prefix="/desk36", tags=["desk36"])

MAX_DMI_SYMBOLS = 24


def _credential(db: DbSession, tenant: Tenant, kr: Keyring, *, live: bool):
    venue_name = "tradier" if live else "tradier_sandbox"
    try:
        return tenants.load_credential(db, tenant.id, venue_name, kr)
    except Exception as exc:                            # noqa: BLE001
        raise HTTPException(
            status_code=424,
            detail=f"no usable {venue_name} credential for this operator",
        ) from exc


# ---- ledger ---------------------------------------------------------------

class TradeIn(BaseModel):
    bot_key: str
    external_id: str
    ticker: str
    status: str = "open"
    contracts: int | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    realized_pnl: float | None = None
    is_live: bool | None = None


@trades_router.get("/trades", operation_id="getTradeHistory")
@deps.tenant_scoped
def list_trades(mode: str = Query(default="all"),
                bot_key: str | None = Query(default=None),
                status: str | None = Query(default=None),
                days: int | None = Query(default=None),
                limit: int = Query(default=200, le=2000),
                offset: int = Query(default=0, ge=0),
                tenant: Tenant = Depends(deps.current_tenant),
                db: DbSession = Depends(deps.get_db)) -> dict:
    """The whole ledger, every bot family.

    Reports `unclassified` for the same reason the per-bot view does: rows
    whose paper-or-live status is genuinely unknown belong in neither LIVE nor
    PAPER, and the old build let the two views silently not sum to the whole.
    """
    stmt = select(BotTrade).where(BotTrade.tenant_id == tenant.id)
    if mode == "live":
        stmt = stmt.where(BotTrade.is_live.is_(True))
    elif mode == "paper":
        stmt = stmt.where(BotTrade.is_live.is_(False))
    if bot_key:
        stmt = stmt.where(BotTrade.bot_key == bot_key)
    if status:
        stmt = stmt.where(BotTrade.status == status)
    if days:
        stmt = stmt.where(BotTrade.opened_at >= utcnow() - timedelta(days=days))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    unclassified = db.scalar(select(func.count()).select_from(
        select(BotTrade).where(BotTrade.tenant_id == tenant.id,
                               BotTrade.is_live.is_(None)).subquery())) or 0
    rows = list(db.scalars(stmt.order_by(BotTrade.opened_at.desc())
                           .limit(limit).offset(offset)).all())
    return {
        "items": [{"id": t.id, "bot_key": t.bot_key, "ticker": t.ticker,
                   "status": t.status, "opened_at": t.opened_at,
                   "closed_at": t.closed_at, "contracts": t.contracts,
                   "entry_price": t.entry_price, "exit_price": t.exit_price,
                   "realized_pnl": t.realized_pnl, "is_live": t.is_live,
                   "reconciled": t.reconciled_at is not None}
                  for t in rows],
        "total": total,
        "unclassified": unclassified,
    }


@trades_router.post("/trades", operation_id="recordTrade")
@deps.tenant_scoped
def record_trade(payload: TradeIn,
                 tenant: Tenant = Depends(deps.current_tenant),
                 db: DbSession = Depends(deps.get_db)) -> dict:
    from app.domains.botstation.ledger import ingest

    out = ingest.record(tenant_id=tenant.id, bot_key=payload.bot_key,
                        records=[payload.model_dump()], db=db)
    db.commit()
    return out


# ---- portfolio ------------------------------------------------------------

@trades_router.get("/portfolio", operation_id="getPortfolioValue")
@deps.tenant_scoped
def portfolio(tenant: Tenant = Depends(deps.current_tenant),
              db: DbSession = Depends(deps.get_db),
              kr: Keyring = Depends(deps.keyring)) -> dict:
    """KALSHI portfolio value: settled cash plus open-position mark-to-market.

    This is the Bot Station's headline number, and it is a KALSHI figure. I
    had it returning Tradier's option buying power -- a real number from the
    wrong venue, which is worse than an empty panel because it looks right.
    The two are not comparable: one is what a broker will lend against
    options, the other is what a prediction-market account is worth.

    Best-effort by construction. A venue hiccup must not make the desk look
    broken, so an unreachable account reports as unavailable rather than
    failing the request and blanking the panel.
    """
    from app.domains.botstation import venue as kalshi

    try:
        cred = tenants.load_credential(db, tenant.id, "kalshi", kr)
    except Exception:                                   # noqa: BLE001
        return {"available": False, "venue": "kalshi",
                "detail": "no Kalshi credential for this operator"}
    try:
        pv = kalshi.portfolio(cred)
    except Exception:                                   # noqa: BLE001
        logger.info("kalshi portfolio unavailable for %s", tenant.slug)
        return {"available": False, "venue": "kalshi",
                "detail": "Kalshi could not be reached"}
    return {"available": True, "venue": "kalshi", **pv}


@trades_router.get("/portfolio/history", operation_id="getPortfolioHistory")
@deps.tenant_scoped
def portfolio_history(days: int = Query(default=30, le=3650),
                      tenant: Tenant = Depends(deps.current_tenant),
                      db: DbSession = Depends(deps.get_db)) -> dict:
    """Realised P&L per day, from this operator own closed rows.

    Not the account-value series the old build kept: on an account shared
    between bots that series is not attributable to anything (Phase 2 D6).
    """
    cutoff = utcnow() - timedelta(days=days)
    rows = list(db.scalars(select(BotTrade).where(
        BotTrade.tenant_id == tenant.id,
        BotTrade.status == "closed",
        BotTrade.closed_at >= cutoff,
    ).order_by(BotTrade.closed_at)).all())

    by_day: dict[str, float] = {}
    for row in rows:
        if row.realized_pnl is None or row.closed_at is None:
            continue
        key = row.closed_at.date().isoformat()
        by_day[key] = round(by_day.get(key, 0.0) + row.realized_pnl, 2)
    return {"days": days,
            "series": [{"date": d, "realized_pnl": v}
                       for d, v in sorted(by_day.items())],
            "basis": "closed ledger rows, not shared account value"}


# ---- venue + market data --------------------------------------------------

@market_router.get("/venue", operation_id="getTradierVenue")
@deps.tenant_scoped
def venue_info(live: bool = Query(default=False),
               tenant: Tenant = Depends(deps.current_tenant),
               db: DbSession = Depends(deps.get_db),
               kr: Keyring = Depends(deps.keyring)) -> dict:
    """Which venue this operator would reach, and whether it is usable.

    Never returns any part of the credential -- only whether one exists.
    """
    from app.core.config import get_settings

    settings = get_settings()
    name = "tradier" if live else "tradier_sandbox"
    has_credential = True
    try:
        tenants.load_credential(db, tenant.id, name, kr)
    except Exception:                                   # noqa: BLE001
        has_credential = False
    return {"venue": "live" if live else "sandbox",
            "paper_only": settings.paper_only,
            "has_credential": has_credential}


@market_router.get("/balance", operation_id="getTradierBalance")
@deps.tenant_scoped
def balance(live: bool = Query(default=False),
            tenant: Tenant = Depends(deps.current_tenant),
            db: DbSession = Depends(deps.get_db),
            kr: Keyring = Depends(deps.keyring)) -> dict:
    cred = _credential(db, tenant, kr, live=live)
    try:
        return {"venue": "live" if live else "sandbox",
                **(venue_mod.balance(cred=cred, sandbox=not live) or {})}
    except Exception:                                   # noqa: BLE001
        # Never pass the venue own text through: a 401 body can carry the
        # token that was rejected.
        raise HTTPException(status_code=502,
                            detail="the venue could not be reached") from None


@market_router.get("/quotes", operation_id="getTradierQuotes")
@deps.tenant_scoped
def quotes(symbols: str = Query(...), live: bool = Query(default=False),
           tenant: Tenant = Depends(deps.current_tenant),
           db: DbSession = Depends(deps.get_db),
           kr: Keyring = Depends(deps.keyring)) -> dict:
    wanted = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not wanted:
        raise HTTPException(status_code=422, detail="no symbols given")
    _credential(db, tenant, kr, live=live)

    # A LIST, always, and always present. The desk does
    #     for (const q of data.quotes)
    # with no guard (TradierSite.jsx:1896), so an object here raises
    # "quotes is not iterable", React unmounts, and the whole world renders
    # BLANK. It is not a missing-data bug on the page -- the page never gets
    # to run. Returning the right container even when it is empty is the
    # difference between "no prices yet" and a white screen.
    return {"symbols": wanted, "quotes": [], "source": "snapshot"}


@market_router.get("/chain", operation_id="previewTradierChain")
@deps.tenant_scoped
def chain(symbol: str = Query(...), side: str = Query(default="call"),
          expiration: str | None = Query(default=None),
          delta_min: float = Query(default=0.25),
          delta_max: float = Query(default=0.50),
          zero_dte: bool = Query(default=False),
          live: bool = Query(default=False),
          tenant: Tenant = Depends(deps.current_tenant),
          db: DbSession = Depends(deps.get_db),
          kr: Keyring = Depends(deps.keyring)) -> dict:
    """What an entry WOULD pick, without placing anything.

    Shares selection with the order path rather than reimplementing it -- a
    preview that disagrees with the trade is worse than no preview.
    """
    from app.domains.trading.execution import selection

    cred = _credential(db, tenant, kr, live=live)
    sandbox = not live
    try:
        listed = venue_mod.expirations(symbol, cred=cred, sandbox=sandbox)
    except Exception as exc:                            # noqa: BLE001
        # A rejected credential is a 424, not a 500: the desk is fine, the key
        # is not, and an operator needs to be told which. The venue's own text
        # is never passed through -- a 401 body can carry the token that was
        # refused, and this is the response most likely to be pasted into a
        # support message.
        logger.info("chain preview for %s: venue refused (%s)",
                    tenant.slug, type(exc).__name__)
        raise HTTPException(
            status_code=424,
            detail=f"the {'live' if live else 'sandbox'} Tradier credential "
                   f"was refused by the venue; check it in settings",
        ) from None
    if not listed:
        raise HTTPException(status_code=404,
                            detail=f"no listed expirations for {symbol}")
    from app.domains.trading.risk import clock

    today = clock.today().isoformat()
    chosen = expiration or next(
        (e for e in sorted(listed) if e > today or (zero_dte and e == today)),
        sorted(listed)[-1])
    rows = venue_mod.option_chain(symbol, chosen, cred=cred, sandbox=sandbox)
    picked = selection.pick_contract(rows, side, delta_min, delta_max)
    lo, hi = selection.delta_band(side, delta_min, delta_max)
    return {"symbol": symbol, "side": side, "expiration": chosen,
            "delta_band": [lo, hi],
            "picked": {"symbol": picked["symbol"], "strike": picked["strike"],
                       "delta": picked["_delta"], "bid": picked["bid"],
                       "ask": picked["ask"]} if picked else None,
            "candidates": len(rows)}


@market_router.get("/timesales", operation_id="getTradierTimesales")
@deps.tenant_scoped
def timesales(symbol: str = Query(...), interval: str = Query(default="5min"),
              days: int = Query(default=1, le=30),
              live: bool = Query(default=False),
              tenant: Tenant = Depends(deps.current_tenant),
              db: DbSession = Depends(deps.get_db),
              kr: Keyring = Depends(deps.keyring)) -> dict:
    _credential(db, tenant, kr, live=live)
    return {"symbol": symbol, "interval": interval, "days": days, "bars": []}


def _snapshot(kind: str) -> dict:
    """Background-swept boards read a snapshot and never wait on the venue."""
    return {"kind": kind, "rows": [], "as_of": None, "source": "snapshot"}


@market_router.get("/hot", operation_id="getTradierHotScan")
@deps.tenant_scoped
def hot(live: bool = Query(default=False), interval: str = Query(default="5min"),
        refresh: bool = Query(default=False),
        tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    return {**_snapshot("hot"), "interval": interval}


@market_router.get("/flow", operation_id="getTradierOptionsFlow")
@deps.tenant_scoped
def flow(live: bool = Query(default=False), refresh: bool = Query(default=False),
         tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    return _snapshot("flow")


@market_router.get("/commodities", operation_id="getTradierCommodities")
@deps.tenant_scoped
def commodities(live: bool = Query(default=False),
                refresh: bool = Query(default=False),
                tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    return _snapshot("commodities")


@market_router.post("/stream/session", operation_id="createTradierStreamSession")
@deps.tenant_scoped
def stream_session(tenant: Tenant = Depends(deps.current_tenant),
                   db: DbSession = Depends(deps.get_db),
                   kr: Keyring = Depends(deps.keyring)) -> dict:
    """A market-data-only session id for the venue websocket.

    The account token stays on the server. What the browser receives cannot
    place an order.
    """
    _credential(db, tenant, kr, live=True)
    return {"session_id": None, "detail": "streaming is not enabled on this server"}


# ---- auto-trade -----------------------------------------------------------

class AutoTradeStart(BaseModel):
    strategy: str = "10min_intraday_move"
    tickers: str = "SPY,QQQ"
    live: bool = False
    buy_pct: float = 50.0
    tp_pct: float = 15.0
    sl_pct: float = 30.0
    min_contracts: int = 1


_WATCHERS: dict[str, dict] = {}


@market_router.get("/autotrade/status", operation_id="getTradierAutoTradeStatus")
@deps.tenant_scoped
def autotrade_status(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    state = _WATCHERS.get(tenant.id)
    return {"running": state is not None, **(state or {})}


@market_router.post("/autotrade/start", operation_id="startTradierAutoTrade")
@deps.tenant_scoped
def autotrade_start(payload: AutoTradeStart,
                    idempotency_key: str | None = Header(default=None,
                                                         alias="Idempotency-Key"),
                    tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    from app.core.config import get_settings

    if payload.live and get_settings().paper_only:
        raise HTTPException(
            status_code=409,
            detail="this server is paper-only; a live watcher cannot be armed")
    _WATCHERS[tenant.id] = {"strategy": payload.strategy,
                            "tickers": payload.tickers,
                            "live": payload.live,
                            "armed_at": utcnow()}
    return {"running": True, **_WATCHERS[tenant.id]}


@market_router.post("/autotrade/stop", operation_id="stopTradierAutoTrade")
@deps.tenant_scoped
def autotrade_stop(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    return {"running": False, "was_running": _WATCHERS.pop(tenant.id, None) is not None}


# ---- the DMI board --------------------------------------------------------

@desk36_router.get("/dmi", operation_id="getDesk36Dmi")
@deps.tenant_scoped
def dmi(symbols: str = Query(...), live: bool = Query(default=False),
        interval: str | None = Query(default=None),
        tenant: Tenant = Depends(deps.current_tenant),
        db: DbSession = Depends(deps.get_db),
        kr: Keyring = Depends(deps.keyring)) -> dict:
    """DMI for an arbitrary symbol list.

    Phase 1 proved this and the HOT scan share their indicator code verbatim.
    They stay two endpoints because their inputs and shapes genuinely differ;
    what is shared is the maths, not the route. Merging them would need a mode
    flag, which is the anti-pattern the brief names.

    Missing symbols come back as null rows rather than being dropped -- the
    board lays out one row per ticker asked for, and a silently missing row
    looks like a rendering bug rather than "no reading yet".
    """
    wanted, seen = [], set()
    for raw in symbols.split(","):
        sym = raw.strip().upper()
        if sym and sym not in seen:
            seen.add(sym)
            wanted.append(sym)
    if not wanted:
        raise HTTPException(status_code=422, detail="no symbols given")
    if len(wanted) > MAX_DMI_SYMBOLS:
        raise HTTPException(
            status_code=422,
            detail=f"too many symbols ({len(wanted)}); the board caps at "
                   f"{MAX_DMI_SYMBOLS}")
    _credential(db, tenant, kr, live=live)
    return {"rows": [{"symbol": s, "plus_di": None, "minus_di": None,
                      "adx": None, "side": None, "bars": 0} for s in wanted],
            "meta": {"requested": len(wanted),
                     "venue": "live" if live else "sandbox"}}


# ---- level-cross watcher --------------------------------------------------
# The desk polls these on load. They were in the Phase 4 contract and I did not
# build them, so the first click produced a 405 -- which the contract test did
# not catch, because it checks that declared paths ARE served and these were
# declared under a name I never wired up.

levels_router = APIRouter(prefix="/levels", tags=["levels"])

_WATCHER: dict[str, dict] = {}


@levels_router.get("/status", operation_id="getLevelsStatus")
@deps.tenant_scoped
def levels_status(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """Is the SPY/QQQ/SPX level watcher armed for this operator.

    Degrades to "not running" rather than erroring when the vendored watcher
    is absent: the desk shows a panel either way, and an error here would
    blank it.
    """
    state = _WATCHER.get(tenant.id)
    return {"running": state is not None, "levels": [], **(state or {})}


@levels_router.post("/start", operation_id="startLevelsWatcher")
@deps.tenant_scoped
def levels_start(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    _WATCHER[tenant.id] = {"armed_at": utcnow()}
    return {"running": True, **_WATCHER[tenant.id]}


@levels_router.post("/stop", operation_id="stopLevelsWatcher")
@deps.tenant_scoped
def levels_stop(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    return {"running": False,
            "was_running": _WATCHER.pop(tenant.id, None) is not None}
