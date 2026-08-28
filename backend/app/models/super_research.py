from __future__ import annotations

from datetime import datetime

from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, Float, Index,
                        Integer, String)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.user import utcnow


class SuperSignal(Base):
    """One row per super_research signal (A-book / B-book ledgers and the
    per-ticker intraday feeds), ingested from the CSVs for queryable history."""

    __tablename__ = "super_signals"
    __table_args__ = (
        Index("ix_super_signals_book_time", "book", "logged_at"),
        Index("ix_super_signals_ticker_time", "ticker", "logged_at"),
        Index("ix_super_signals_external", "external_id", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    external_id: Mapped[str] = mapped_column(String(256))  # dedupe key from CSV row
    book: Mapped[str | None] = mapped_column(String(8), nullable=True)  # A | B
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ticker: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)  # LONG | SHORT
    grade: Mapped[str | None] = mapped_column(String(16), nullable=True)  # eng_hot 2/3/4 etc
    combo: Mapped[str | None] = mapped_column(String(256), nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    bar_time: Mapped[str | None] = mapped_column(String(64), nullable=True)  # CST as recorded
    logged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # True when the row came from (or has rotated into) the weekly archive
    # ledger — the live feeds exclude archived rows unless ?all=1.
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DailySnapshot(Base):
    """Daily JSON blobs (GEX walls/regime, econ calendar) kept as history.

    kind: 'gex' | 'econ'. One row per (kind, snapshot_date); the latest row
    is what /super/state embeds, older rows are queryable history.
    """

    __tablename__ = "daily_snapshots"
    __table_args__ = (Index("ix_daily_snapshots_kind_date", "kind", "snapshot_date", unique=True),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16))
    snapshot_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    source_file: Mapped[str | None] = mapped_column(String(512), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Gex0dteHour(Base):
    """One SPY 0DTE net-gamma reading per CST trading hour.

    The desk reads the day as a chain (+500M >> +420M >> ...), so history is
    kept per (date, hour) rather than per push, and the last reading inside an
    hour wins — it is the one closest to that hour's close. Hours never
    captured have no row at all, and the API renders them as 0, so a gap in
    the day stays visible instead of silently collapsing.
    """

    __tablename__ = "gex0dte_hourly"
    __table_args__ = (
        Index("ix_gex0dte_hourly_date_hour", "trade_date", "hour_cst", unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_date: Mapped[str] = mapped_column(String(10))   # YYYY-MM-DD, CST
    hour_cst: Mapped[int] = mapped_column(Integer)        # 8..16
    ticker: Mapped[str] = mapped_column(String(12), default="SPY")
    net_gex: Mapped[float] = mapped_column(Float, default=0.0)
    call_gex: Mapped[float | None] = mapped_column(Float, nullable=True)
    put_gex: Mapped[float | None] = mapped_column(Float, nullable=True)
    spot: Mapped[float | None] = mapped_column(Float, nullable=True)
    regime: Mapped[str | None] = mapped_column(String(8), nullable=True)
    flip: Mapped[float | None] = mapped_column(Float, nullable=True)
    call_wall: Mapped[float | None] = mapped_column(Float, nullable=True)
    put_wall: Mapped[float | None] = mapped_column(Float, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PusherHeartbeat(Base):
    """One row per push CYCLE of the browser-side 0DTE pusher, ok or not.

    The snapshot tables are upserts — one row per day, one per hour — so the
    database holds no cadence at all: "the last push landed at 14:40" is a
    single mutable field with nothing behind it. That is why a 24-minute gap
    on 2026-07-30 could not be resolved into "the tab died" versus "the tab
    was alive and every push was refused". This table is append-only for
    exactly that reason.

    Read it as: gaps in ``seq`` mean the timer stopped; contiguous ``seq``
    with ok=false means the timer ran and the push was rejected; ``seq``
    restarting at 1 means a new document (reload, discard, or re-click).
    """

    __tablename__ = "pusher_heartbeats"
    __table_args__ = (
        Index("ix_pusher_heartbeats_received", "received_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session: Mapped[str] = mapped_column(String(16))   # per-document id
    seq: Mapped[int] = mapped_column(Integer)          # cycle number in session
    ok: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    wall_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mono_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
