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
    cred = _credential(db, tenant, kr, live=live)

    try:
        rows = venue_mod.quotes(wanted, cred=cred, sandbox=not live)
    except Exception:                                   # noqa: BLE001
        logger.info("quotes unavailable for %s", tenant.slug)
        rows = []

    # A LIST, always, and always present. The desk does
    #     for (const q of data.quotes)
    # with no guard (TradierSite.jsx:1896), so an object here raises
    # "quotes is not iterable", React unmounts, and the whole world renders
    # BLANK -- the page never gets to run at all. Returning the right
    # container even when empty is the difference between "no prices yet" and
    # a white screen.
    by_symbol = {str(q.get("symbol", "")).upper(): q for q in rows}
    out = []
    for sym in wanted:
        q = by_symbol.get(sym)
        if q is None:
            # Present but null rather than absent: the ticker rail lays out one
            # row per symbol asked for, and a dropped row reads as a rendering
            # bug rather than "no quote".
            out.append({"symbol": sym, "last": None, "bid": None, "ask": None,
                        "change": None, "change_percentage": None,
                        "volume": None, "available": False})
            continue
        out.append({
            "symbol": sym,
            "description": q.get("description"),
            "last": q.get("last"), "bid": q.get("bid"), "ask": q.get("ask"),
            "open": q.get("open"), "high": q.get("high"), "low": q.get("low"),
            "close": q.get("close"), "prevclose": q.get("prevclose"),
            "change": q.get("change"),
            "change_percentage": q.get("change_percentage"),
            "volume": q.get("volume"), "available": True,
        })
    return {"symbols": wanted, "quotes": out,
            "venue": "live" if live else "sandbox",
            "source": "tradier"}


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
    cred = _credential(db, tenant, kr, live=live)
    from app.domains.trading.market import indicators

    try:
        native, factor = indicators.source_interval(interval)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    try:
        bars = venue_mod.timesales(
            symbol.upper(), cred=cred, interval=native, sandbox=not live,
            start=indicators.start_date(interval))
        bars = indicators.aggregate(bars, factor)
    except Exception:                                   # noqa: BLE001
        logger.info("timesales unavailable for %s/%s", tenant.slug, symbol)
        bars = []
    return {"symbol": symbol.upper(), "interval": interval, "days": days,
            "native_interval": native, "bars": bars,
            "venue": "live" if live else "sandbox"}


def _scan(cred, symbols: list[str], interval: str, *, sandbox: bool,
          gate: bool) -> list[dict]:
    """DMI over a list of symbols, through the ONE indicator implementation.

    ``gate`` is the only difference between the HOT board and the DMI board:
    HOT shows names that clear a trend threshold, DMI shows whatever was
    asked for. Same maths, same bars, one filter -- which is why Phase 4 kept
    them as separate endpoints sharing code rather than merging them behind a
    mode flag.
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.core.config import get_settings
    from app.domains.trading.market import indicators

    settings = get_settings()
    native, factor = indicators.source_interval(interval)
    start = indicators.start_date(interval)

    def one(symbol: str) -> dict:
        try:
            bars = venue_mod.timesales(symbol, cred=cred, interval=native,
                                       sandbox=sandbox, start=start)
            reading = indicators.dmi(indicators.aggregate(bars, factor))
        except Exception:                               # noqa: BLE001
            # An unknown or illiquid ticker is an ordinary outcome on a board
            # the operator types into. One bad symbol must not empty the rest.
            reading = None
        return {"symbol": symbol, "plus_di": (reading or {}).get("plus_di"),
                "minus_di": (reading or {}).get("minus_di"),
                "adx": (reading or {}).get("adx"),
                "side": (reading or {}).get("side"),
                "bars": (reading or {}).get("bars", 0)}

    workers = max(1, min(settings.tradier_flow_workers, len(symbols)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(one, symbols))

    if not gate:
        return rows
    lo_adx = settings.tradier_hot_min_adx
    min_pdi = settings.tradier_hot_min_pdi
    ratio = settings.tradier_hot_di_ratio
    keep = []
    for r in rows:
        p, m, adx = r["plus_di"], r["minus_di"], r["adx"]
        if p is None or m is None or adx is None or adx < lo_adx:
            continue
        strong, weak = (p, m) if p >= m else (m, p)
        if strong < min_pdi or weak <= 0 or strong / weak < ratio:
            continue
        keep.append(r)
    keep.sort(key=lambda r: r["adx"], reverse=True)
    return keep


@market_router.get("/hot", operation_id="getTradierHotScan")
@deps.tenant_scoped
def hot(live: bool = Query(default=False), interval: str = Query(default="5min"),
        refresh: bool = Query(default=False),
        tenant: Tenant = Depends(deps.current_tenant),
        db: DbSession = Depends(deps.get_db),
        kr: Keyring = Depends(deps.keyring)) -> dict:
    """Names whose trend clears the desk's gates, on the chosen bar."""
    from app.core.config import get_settings

    settings = get_settings()
    universe = [s.strip().upper()
                for s in settings.tradier_hot_universe.split(",") if s.strip()]
    try:
        cred = _credential(db, tenant, kr, live=live)
        rows = _scan(cred, universe, interval, sandbox=not live, gate=True)
    except HTTPException:
        raise
    except Exception:                                   # noqa: BLE001
        logger.info("hot scan unavailable for %s", tenant.slug)
        rows = []
    return {"kind": "hot", "rows": rows, "interval": interval,
            "scanned": len(universe), "source": "tradier",
            "venue": "live" if live else "sandbox"}


@market_router.get("/flow", operation_id="getTradierOptionsFlow")
@deps.tenant_scoped
def flow(live: bool = Query(default=False), refresh: bool = Query(default=False),
         tenant: Tenant = Depends(deps.current_tenant),
         db: DbSession = Depends(deps.get_db),
         kr: Keyring = Depends(deps.keyring)) -> dict:
    """The day's heaviest option contracts, with open-interest change.

    I had this returning an empty list with available:false on the grounds
    that a chain sweep is too slow for a request. The sweep IS too slow for a
    request -- so it runs behind one. The board answers from the last good
    snapshot and refreshes in the background, which is what the old app did
    and what makes the panel usable at all.
    """
    from app.domains.trading.market import flow as flow_mod

    cred = _credential(db, tenant, kr, live=live)
    try:
        got = flow_mod.snapshot(tenant.id, cred, sandbox=not live,
                                force=refresh)
    except Exception:                                   # noqa: BLE001
        logger.info("options flow unavailable for %s", tenant.slug)
        return {"kind": "flow", "rows": [],
                "meta": {"stale": True, "refreshing": False},
                "detail": "the venue could not be reached"}
    return {"kind": "flow", **got}


@market_router.get("/commodities", operation_id="getTradierCommodities")
@deps.tenant_scoped
def commodities(live: bool = Query(default=False),
                interval: str = Query(default="5min"),
                refresh: bool = Query(default=False),
                tenant: Tenant = Depends(deps.current_tenant),
                db: DbSession = Depends(deps.get_db),
                kr: Keyring = Depends(deps.keyring)) -> dict:
    """Gold, silver and oil, through the same board the bots read."""
    from app.domains.trading.market import commodities as commod

    cred = None
    try:
        cred = tenants.load_credential(
            db, tenant.id, "tradier" if live else "tradier_sandbox", kr)
    except Exception:                                   # noqa: BLE001
        pass
    try:
        snap = commod.snapshot(cred, interval=interval, sandbox=not live,
                               force=refresh)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    return {"kind": "commodities", **snap}


# The ticker strip, in render order.
#
# Tradier quotes SPX and VIX as indices directly, but has no symbol for the Dow
# itself (DJI is unmatched) -- DIA, the SPDR Dow ETF, is the tradable proxy,
# labelled DOW so the strip reads the way an operator expects.
#
# BTC is not a Tradier instrument at all: the market socket carries equities
# and indices, so nothing here can make it tick. It rides along as a POLLED
# entry instead, flagged so the browser refreshes it itself rather than
# waiting for a tick that will never come. Marking it rather than dropping it
# is the difference between "bitcoin updates differently" and "bitcoin is
# frozen".
STREAM_SYMBOLS = [
    {"label": "QQQ", "symbol": "QQQ"},
    {"label": "SPY", "symbol": "SPY"},
    {"label": "SPX", "symbol": "SPX"},
    {"label": "VIX", "symbol": "VIX"},
    {"label": "DOW", "symbol": "DIA"},
    {"label": "BTC", "symbol": "BTC", "stream": False},
]
STREAMED = [s for s in STREAM_SYMBOLS if s.get("stream", True)]
POLLED = [s for s in STREAM_SYMBOLS if not s.get("stream", True)]


@market_router.post("/stream/session", operation_id="createTradierStreamSession")
@deps.tenant_scoped
def stream_session(tenant: Tenant = Depends(deps.current_tenant),
                   db: DbSession = Depends(deps.get_db),
                   kr: Keyring = Depends(deps.keyring)) -> dict:
    """A market-data-only session id for the venue websocket.

    The account token stays on the server. What the browser receives cannot
    place an order.
    """
    cred = _credential(db, tenant, kr, live=True)
    try:
        data = venue_mod.market_session(cred=cred)
    except Exception:                                   # noqa: BLE001
        logger.info("stream session unavailable for %s", tenant.slug)
        raise HTTPException(
            status_code=502,
            detail="the venue would not open a market session") from None

    # Seeded in STREAM_SYMBOLS order. The strip renders in the order it is
    # handed, so this list is the single place that order is decided.
    seed = []
    try:
        rows = venue_mod.quotes([s["symbol"] for s in STREAMED], cred=cred,
                                sandbox=False)
        by_symbol = {str(q.get("symbol", "")).upper(): q for q in rows}
    except Exception:                                   # noqa: BLE001
        # A missing seed costs the first paint, not the stream: the socket
        # fills the strip within a second of connecting.
        by_symbol = {}
    for entry in STREAM_SYMBOLS:
        quote = by_symbol.get(entry["symbol"])
        seed.append({**entry,
                     "last": (quote or {}).get("last"),
                     "change": (quote or {}).get("change"),
                     "change_percentage": (quote or {}).get("change_percentage")})

    return {
        "sessionid": data.get("sessionid"),
        "url": data.get("url"),
        "ws_url": "wss://ws.tradier.com/v1/markets/events",
        "symbols": STREAMED,
        "polled": [s["symbol"] for s in POLLED],
        "seed": seed,
        "venue": "live",
    }


# ---- auto-trade -----------------------------------------------------------

class AutoTradeStart(BaseModel):
    strategy: str = "10min_intraday_move"
    tickers: str = "SPY,QQQ"
    live: bool = False
    buy_pct: float = 50.0
    tp_pct: float = 15.0
    sl_pct: float = 30.0
    tolerance_pct: float = 25.0
    min_contracts: int = 1
    delta_min: float = 0.35
    delta_max: float = 0.65


@market_router.get("/autotrade/status", operation_id="getTradierAutoTradeStatus")
@deps.tenant_scoped
def autotrade_status(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    from app.domains.trading.execution import autotrade

    return autotrade.status(tenant.id)


@market_router.post("/autotrade/start", operation_id="startTradierAutoTrade")
@deps.tenant_scoped
def autotrade_start(payload: AutoTradeStart,
                    idempotency_key: str | None = Header(default=None,
                                                         alias="Idempotency-Key"),
                    tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """Arm the auto-trader.

    It was an in-memory dict that recorded "running: true" and watched
    nothing -- the worst possible shape for this particular feature, because
    the operator reasonably believes an armed trader is working. It now runs
    a real loop, and every entry it makes goes through the SAME guarded path
    as the manual button rather than a second copy of the entry logic.
    """
    from app.domains.trading.execution import autotrade

    try:
        return autotrade.start(
            tenant.id, tickers=payload.tickers, strategy=payload.strategy,
            live=payload.live, buy_pct=payload.buy_pct, tp_pct=payload.tp_pct,
            sl_pct=payload.sl_pct, tolerance_pct=payload.tolerance_pct,
            min_contracts=payload.min_contracts, delta_min=payload.delta_min,
            delta_max=payload.delta_max)
    except autotrade.AutoTradeRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


@market_router.post("/autotrade/stop", operation_id="stopTradierAutoTrade")
@deps.tenant_scoped
def autotrade_stop(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    from app.domains.trading.execution import autotrade

    return autotrade.stop(tenant.id)


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
    cred = _credential(db, tenant, kr, live=live)
    from app.core.config import get_settings

    iv = interval or get_settings().tradier_hot_interval
    try:
        rows = _scan(cred, wanted, iv, sandbox=not live, gate=False)
    except Exception:                                   # noqa: BLE001
        logger.info("dmi board unavailable for %s", tenant.slug)
        rows = [{"symbol": s, "plus_di": None, "minus_di": None, "adx": None,
                 "side": None, "bars": 0} for s in wanted]
    return {"rows": rows,
            "meta": {"requested": len(wanted), "interval": iv,
                     "venue": "live" if live else "sandbox"}}


# ---- level-cross watcher --------------------------------------------------
# The desk polls these on load. They were in the Phase 4 contract and I did not
# build them, so the first click produced a 405 -- which the contract test did
# not catch, because it checks that declared paths ARE served and these were
# declared under a name I never wired up.

levels_router = APIRouter(prefix="/levels", tags=["levels"])

@levels_router.get("/status", operation_id="getLevelsStatus")
@deps.tenant_scoped
def levels_status(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """The SPY/QQQ/SPX level watcher: is it running, and what does it see.

    One watcher for the whole desk rather than one per operator: it computes
    opening ranges from public prices, which are the same numbers for
    everybody. Per-operator state here would be N processes deriving one fact.

    Degrades to "not running" rather than erroring when the watcher has never
    been started -- the desk shows this panel either way, and an error here
    blanks it.
    """
    from app.services import levels as levels_svc

    try:
        return levels_svc.status()
    except Exception:                                   # noqa: BLE001
        logger.info("levels watcher status unavailable")
        return {"running": False, "pid": None, "status": None}


@levels_router.post("/start", operation_id="startLevelsWatcher")
@deps.tenant_scoped
def levels_start(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    from app.services import levels as levels_svc

    try:
        return levels_svc.start()
    except levels_svc.LevelsError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@levels_router.post("/stop", operation_id="stopLevelsWatcher")
@deps.tenant_scoped
def levels_stop(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    from app.services import levels as levels_svc

    return levels_svc.stop()
