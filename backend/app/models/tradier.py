from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, false

from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import utcnow


class TradierPosition(Base):
    """One managed Tradier options position, from buy through TP/SL exit.

    DB-backed rather than in-memory on purpose: the stop-loss is a MONITOR
    (the TP is a resting order on the venue, the SL is not), so the monitor's
    working set must survive an API restart — otherwise a restart silently
    turns every open position into "TP or ride to zero".

    Status machine:
        pending   buy order placed, waiting for the fill
        open      filled; TP sell resting; SL monitored
        tp_filled TP sell filled — the win case
        sl_sold   SL breached: TP cancelled, position sold
        closed    manually closed from the desk
        failed    buy never filled / rejected; nothing at risk
    """

    __tablename__ = "tradier_positions"
    __table_args__ = (
        Index("ix_tradier_positions_status", "status"),
        Index("ix_tradier_positions_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36))
    sandbox: Mapped[bool] = mapped_column(Boolean, default=True)

    underlying: Mapped[str] = mapped_column(String(12))
    occ_symbol: Mapped[str] = mapped_column(String(32))
    option_type: Mapped[str] = mapped_column(String(4))       # call | put
    strike: Mapped[float] = mapped_column(Float)
    expiration: Mapped[str] = mapped_column(String(10))
    delta_at_entry: Mapped[float | None] = mapped_column(Float, nullable=True)

    contracts: Mapped[int] = mapped_column(Integer)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    tp_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    sl_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    tp_pct: Mapped[float] = mapped_column(Float, default=15.0)
    sl_pct: Mapped[float] = mapped_column(Float, default=30.0)
    buy_pct: Mapped[float] = mapped_column(Float, default=50.0)

    buy_order_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    tp_order_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    close_order_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # who decided this trade: "Manual" for desk buys, else the auto-trader's
    # strategy name (e.g. "10min_intraday_move")
    strategy: Mapped[str] = mapped_column(String(64), default="Manual",
                                          server_default="Manual")

    status: Mapped[str] = mapped_column(String(16), default="pending")
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    pnl_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    carry_over: Mapped[bool] = mapped_column(Boolean, default=False,
                                               server_default=false())
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    opened_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
