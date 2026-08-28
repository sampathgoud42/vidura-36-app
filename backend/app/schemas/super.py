from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SuperConfigUpdate(BaseModel):
    enabled: dict[str, bool] = Field(
        description="tickerId -> enabled flag, matched across all categories",
        examples=[{"spy": True, "btc": False}],
    )


class SuperStopRequest(BaseModel):
    category: str | None = Field(
        default=None, description="etf | stock | crypto; omit to stop all"
    )


class SuperSignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    book: str | None
    category: str | None
    ticker: str
    direction: str | None
    grade: str | None
    combo: str | None
    price: float | None
    accuracy_pct: float | None
    bar_time: str | None
    logged_at: datetime | None
    raw: dict | None


class SuperSignalPage(BaseModel):
    total: int
    items: list[SuperSignalOut]


class SnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    snapshot_date: str
    payload: dict
    source_file: str | None
    fetched_at: datetime
