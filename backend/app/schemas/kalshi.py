from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class KalshiClientState(BaseModel):
    """Connection state returned by POST /users/{user_id}/kalshi-client."""

    user_id: str
    environment: str  # prod | demo
    api_key_id_masked: str
    authenticated: bool
    balance_cents: int | None = None
    exchange_active: bool | None = None
    trading_active: bool | None = None
    checked_at: datetime
    detail: str | None = None
