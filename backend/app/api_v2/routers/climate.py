"""Climate: the daily rain board for Kalshi's KXRAIN cities.

Read and refresh are open to any signed-in operator: the board is a fact
about the weather, the same for everybody, and the refresh replaces one shared
table (climate.rain_forecast, archived to rain_forecast_hist first). Trading is
the operator's own: it spends their Kalshi account and needs their credential.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

from app.api_v2 import deps
from app.tenancy import repository as tenants
from app.tenancy.models import Tenant

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/climate", tags=["climate"])


@router.get("/rain-forecast", operation_id="getRainForecast")
@deps.tenant_scoped
def rain_forecast(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """Today's call per city, as of the last refresh, each with how its
    earlier calls settled."""
    from app.domains.climate import rain

    return rain.board()


@router.post("/rain-forecast/refresh", operation_id="refreshRainForecast")
@deps.tenant_scoped
def rain_forecast_refresh(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """Read every source again and TRUNCATE AND LOAD the board. Archives the
    rows it replaces and fills in the outcome of any finished day. Takes
    20-60 seconds; a second refresh while one runs is refused, not queued."""
    from app.domains.climate import rain

    try:
        summary = rain.refresh()
    except rain.RefreshBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except Exception as exc:                            # noqa: BLE001
        logger.warning("rain refresh failed: %s", exc)
        raise HTTPException(status_code=424,
                            detail=f"the refresh failed: {exc}") from None
    return {**rain.board(), "refresh": summary}


@router.get("/rain-forecast/quote", operation_id="getRainQuote")
@deps.tenant_scoped
def rain_quote(ticker: str = Query(min_length=8, max_length=40),
               tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """The market's live prices, for the trade form."""
    from app.domains.climate import rain

    if not rain.TICKER_RE.match(ticker):
        raise HTTPException(status_code=422, detail="not a KXRAIN market")
    try:
        return rain.market(ticker)
    except Exception:                                   # noqa: BLE001
        raise HTTPException(status_code=424,
                            detail="Kalshi could not be reached") from None


class RainTradeRequest(BaseModel):
    ticker: str = Field(min_length=8, max_length=40)
    side: str = Field(pattern="^(yes|no)$")
    contracts: int = Field(ge=1, le=500)
    # The most the operator will pay per contract on that side, in cents.
    price_c: int = Field(ge=1, le=99)


@router.post("/rain-forecast/trade", operation_id="placeRainTrade")
@deps.tenant_scoped
def rain_trade(payload: RainTradeRequest,
               idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
               tenant: Tenant = Depends(deps.current_tenant),
               db: DbSession = Depends(deps.get_db)) -> dict:
    """Buy YES or NO on one city's rain market. REAL MONEY.

    A limit order at ``price_c`` for the chosen side: it fills at the ask if
    the ask is at or under the limit, and rests on the book otherwise. The
    market is read again first and an order on a closed one is refused. The
    Idempotency-Key is the confirmation's, so a retry is the same order."""
    from app.domains.botstation import venue
    from app.domains.climate import rain

    key = (idempotency_key or "").strip()
    if not 8 <= len(key) <= 64:
        raise HTTPException(status_code=422,
                            detail="an Idempotency-Key header (8-64 characters) "
                                   "is required to place a rain trade")
    if not rain.TICKER_RE.match(payload.ticker):
        raise HTTPException(status_code=422, detail="not a KXRAIN market")
    try:
        cred = tenants.load_credential(db, tenant.id, "kalshi", deps.keyring())
    except Exception:                                   # noqa: BLE001
        raise HTTPException(status_code=424,
                            detail="no Kalshi credential for this operator") from None
    try:
        live = rain.market(payload.ticker)
    except Exception:                                   # noqa: BLE001
        raise HTTPException(status_code=424, detail="Kalshi could not be reached") from None
    if live.get("status") not in ("active", "open"):
        return {"placed": False, "detail": f"the market is {live.get('status')}, not open"}
    try:
        order = venue.place_order(cred, ticker=payload.ticker, count=payload.contracts,
                                  side=payload.side, action="buy",
                                  price_c=payload.price_c,
                                  client_order_id=f"rain-{key}"[:64])
    except venue.KalshiUnavailable as exc:
        return {"placed": False, "detail": str(exc)}
    logger.info("rain trade %s: %s %s x%d @ %dc", tenant.slug, payload.ticker,
                payload.side, payload.contracts, payload.price_c)
    return {"placed": True, "order": order, "market": live}
