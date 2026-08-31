from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BotKey = Literal["btc15", "btc60", "sports", "parley", "gold15", "silver15", "oil15", "manual"]


def to_naive_utc(value: datetime | None) -> datetime | None:
    """The DB stores naive-UTC; aware client datetimes must be converted,
    not silently stripped of their offset."""
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


class TradeCreate(BaseModel):
    bot_key: BotKey = "manual"
    bot_version: str | None = None
    external_id: str | None = None
    ticker: str = Field(min_length=1, max_length=128)
    market_title: str | None = None
    side: Literal["yes", "no"] | None = None
    action: Literal["buy", "sell"] = "buy"
    contracts: int = Field(ge=0, default=1)
    price_cents: float | None = Field(default=None, ge=0, le=100)
    cost_usd: float | None = None
    fees_usd: float | None = None
    pnl_usd: float | None = None
    status: str = "open"
    is_mock: bool = True
    # True = real money, False = paper, None = unknown (btc15 v2/v3/v4 write
    # both modes to one CSV with no distinguishing field).
    is_live: bool | None = None
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    raw: dict | None = None

    _naive_utc = field_validator("opened_at", "closed_at")(to_naive_utc)


class TradeOut(TradeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    opened_at: datetime
    created_at: datetime


class TradeHistoryPage(BaseModel):
    total: int
    items: list[TradeOut]


class PerformanceSummary(BaseModel):
    bot_key: str | None
    trades: int
    settled: int
    wins: int
    losses: int
    win_rate: float | None
    total_cost_usd: float
    total_pnl_usd: float
    by_status: dict[str, int]
