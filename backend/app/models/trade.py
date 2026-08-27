from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import utcnow


class Trade(Base):
    """Unified trade ledger across every bot (BTC 15m/60m, sports, manual/mock).

    Bot CSV histories are ingested into this superset schema; bot-specific
    extras ride along in ``raw``.
    """

    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_user_bot_time", "user_id", "bot_key", "opened_at"),
        Index("ix_trades_external", "bot_key", "external_id", unique=False),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id", ondelete="CASCADE"), index=True
    )
    bot_key: Mapped[str] = mapped_column(String(32))  # btc15 | btc60 | sports | manual
    bot_version: Mapped[str | None] = mapped_column(String(16), nullable=True)  # v1..v5
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)  # order id / CSV row key
    ticker: Mapped[str] = mapped_column(String(128))
    market_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    side: Mapped[str | None] = mapped_column(String(8), nullable=True)  # yes | no
    action: Mapped[str] = mapped_column(String(8), default="buy")  # buy | sell
    contracts: Mapped[int] = mapped_column(Integer, default=0)
    price_cents: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    fees_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")
    # open | won | lost | settled | closed | canceled
    is_mock: Mapped[bool] = mapped_column(Boolean, default=True)
    # Real money or not. NULL = unknown: btc15 v2/v3/v4 write paper and live
    # rows to one CSV with no distinguishing field, and calling those "paper"
    # would hide real trades from the ledger's default LIVE view.
    is_live: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="trades")
