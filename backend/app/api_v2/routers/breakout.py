"""BreakoutRadar: breakout scans of the US and Indian markets.

    GET  /breakout/scan              the qualifying tickers for a market and timeframe
    GET  /breakout/chart/{ticker}    candles, both EMAs and the breakout overlay
    POST /breakout/alerts/send       relay one alert to Telegram or Discord

Every threshold of the eight rules is an optional query parameter, applied to
the cached scan on each read -- so the page's parameter drawer re-judges
without downloading anything. Fetching new candles happens only on
``refresh=true``, and in the background: the answer says `refreshing`, with
progress, until the sweep lands.

Market data, the same for every operator, so any signed-in operator may read
it. The alert relay stores nothing and is limited per operator.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi import Path as PathParam

from app.api_v2 import deps
from app.domains.trading.market import breakout, breakout_scan
from app.platform import notify
from app.tenancy.models import Tenant

router = APIRouter(prefix="/breakout", tags=["breakout"])

TICKER = r"^[A-Za-z0-9][A-Za-z0-9&.\-]{0,19}$"
ALERTS_PER_MINUTE = 20

_SENT: dict[str, deque] = {}
_SENT_LOCK = threading.Lock()


def _market(value: str) -> str:
    market = (value or "").strip().upper()
    if market not in breakout.MARKETS:
        raise HTTPException(status_code=422, detail="market must be US or INDIA")
    return market


def _timeframe(value: str) -> str:
    timeframe = (value or "").strip().lower()
    if timeframe not in breakout.TIMEFRAMES:
        raise HTTPException(status_code=422,
                            detail=f"timeframe must be one of {', '.join(breakout.TIMEFRAMES)}")
    return timeframe


def thresholds(
    consolidation_bars: int | None = Query(default=None, ge=5, le=120),
    max_range_pct: float | None = Query(default=None, ge=0.5, le=100),
    breakout_pct: float | None = Query(default=None, ge=0, le=50),
    min_body_pct: float | None = Query(default=None, ge=0, le=50),
    min_market_cap: float | None = Query(default=None, ge=0, le=1e14),
    min_rvol: float | None = Query(default=None, ge=0, le=50),
    min_adv: float | None = Query(default=None, ge=0, le=1e10),
    near_high_pct: float | None = Query(default=None, ge=0, le=100),
    breakout_within: int | None = Query(default=None, ge=1, le=10),
) -> breakout.Params:
    """The eight rules' thresholds; any left out keep the specification's."""
    try:
        return breakout.Params().with_overrides(
            consolidation_bars=consolidation_bars, max_range_pct=max_range_pct,
            breakout_pct=breakout_pct, min_body_pct=min_body_pct,
            min_market_cap=min_market_cap, min_rvol=min_rvol, min_adv=min_adv,
            near_high_pct=near_high_pct, breakout_within=breakout_within)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/scan", operation_id="getBreakoutScan")
@deps.tenant_scoped
def scan(market: str = Query(default="US"), timeframe: str = Query(default="1d"),
         refresh: bool = Query(default=False),
         params: breakout.Params = Depends(thresholds),
         tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """Tickers that pass all eight rules, freshest breakout first, plus the
    near misses (one rule short) and how many names each rule turned away --
    so an empty table says which rule emptied it."""
    return breakout_scan.scan(_market(market), _timeframe(timeframe), params,
                              refresh=refresh)


@router.get("/chart/{ticker}", operation_id="getBreakoutChart")
@deps.tenant_scoped
def chart(ticker: str = PathParam(pattern=TICKER), market: str = Query(default="US"),
          timeframe: str = Query(default="1d"),
          params: breakout.Params = Depends(thresholds),
          tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """Candles with the 20 and 50 EMA, the consolidation channel's bounds and
    window, and the breakout candle's timestamp."""
    mkt = _market(market)
    symbol = ticker.strip().upper()
    if mkt == "INDIA" and symbol.endswith((".NS", ".BO")):
        symbol = symbol.rsplit(".", 1)[0]
    try:
        out = breakout_scan.chart(mkt, symbol, _timeframe(timeframe), params)
    except Exception:                                   # noqa: BLE001
        raise HTTPException(status_code=502,
                            detail="Yahoo could not be reached for this chart") from None
    if out is None:
        raise HTTPException(status_code=404, detail=f"no candles for {symbol}")
    return out


@router.post("/alerts/send", operation_id="sendBreakoutAlert")
@deps.tenant_scoped
def send_alert(payload: Any = Body(default=None),
               tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """Relay one message: ``{"channel": "telegram", "token", "chat_id", "text"}``
    or ``{"channel": "discord", "webhook_url", "text"}``.

    The body is read by hand rather than by a model: a validation error echoes
    the offending input into the log, and here the input is a secret."""
    body = payload if isinstance(payload, dict) else {}

    def field(name: str) -> str | None:
        value = body.get(name)
        return value.strip() if isinstance(value, str) else None

    now = time.monotonic()
    with _SENT_LOCK:
        sent = _SENT.setdefault(tenant.id, deque())
        while sent and now - sent[0] > 60:
            sent.popleft()
        if len(sent) >= ALERTS_PER_MINUTE:
            raise HTTPException(status_code=429,
                                detail=f"at most {ALERTS_PER_MINUTE} alerts a minute")
        sent.append(now)
    try:
        return notify.send(field("channel") or "", text=field("text") or "",
                           token=field("token"), chat_id=field("chat_id"),
                           webhook_url=field("webhook_url"))
    except notify.NotifyError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None


def reset_for_tests() -> None:
    with _SENT_LOCK:
        _SENT.clear()
