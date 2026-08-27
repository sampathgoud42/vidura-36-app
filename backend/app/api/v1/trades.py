from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_user_or_404
from app.core.database import get_db
from app.models import User
from app.schemas.trade import TradeCreate, TradeHistoryPage, TradeOut
from app.services import trades as svc

router = APIRouter(prefix="/users/{user_id}/trades", tags=["trades"])


@router.post(
    "",
    operation_id="recordTrade",
    response_model=TradeOut,
    status_code=status.HTTP_201_CREATED,
)
def record_trade(
    payload: TradeCreate,
    user: User = Depends(get_user_or_404),
    db: Session = Depends(get_db),
) -> TradeOut:
    trade = svc.record_trade(db, user.user_id, payload)
    return TradeOut.model_validate(trade)


@router.get("", operation_id="getTradeHistory", response_model=TradeHistoryPage)
def get_trades(
    bot_key: str | None = Query(default=None),
    bot_version: str | None = Query(default=None),
    trade_status: str | None = Query(default=None, alias="status"),
    days: int | None = Query(default=None, ge=1, le=3660),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_user_or_404),
    db: Session = Depends(get_db),
) -> TradeHistoryPage:
    total, items = svc.query_trades(
        db,
        user_id=user.user_id,
        bot_key=bot_key,
        bot_version=bot_version,
        status=trade_status,
        days=days,
        limit=limit,
        offset=offset,
    )
    return TradeHistoryPage(total=total, items=[TradeOut.model_validate(t) for t in items])
