"""Research tables: the signal ledger, daily snapshots, and the 0DTE chain.

None of these are tenant-owned, and that is a deliberate, defended choice
rather than an omission. Gamma exposure for SPY, the economic calendar, and
the earnings window are facts about the market; they do not differ per
operator, and copying them per tenant would mean N identical rows and N
identical vendor calls for one fact. The scope guarantee still holds: the
registry enumerates these as exceptions by name, so a future table that
quietly lacks a tenant_id fails the allowlist test instead of slipping past.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, DateTime, Float, Index, Integer,
                        String, UniqueConstraint)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.base import Base, utcnow


class ResearchSignal(Base):
    """One row per super-research signal, ingested from the engine feeds."""

    __tablename__ = "research_signal"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_research_signal_external"),
        Index("ix_research_signal_book_time", "book", "logged_at"),
        Index("ix_research_signal_ticker_time", "ticker", "logged_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # The dedupe key carried by the source row. UNIQUE, so re-ingesting a feed
    # that was appended to -- the normal case, since the engines only ever add
    # lines -- cannot double-count a signal.
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)
    book: Mapped[str | None] = mapped_column(String(8))
    category: Mapped[str | None] = mapped_column(String(64))
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str | None] = mapped_column(String(16))
    grade: Mapped[str | None] = mapped_column(String(16))
    combo: Mapped[str | None] = mapped_column(String(256))
    price: Mapped[float | None] = mapped_column(Float)
    accuracy_pct: Mapped[float | None] = mapped_column(Float)
    bar_time: Mapped[str | None] = mapped_column(String(64))
    logged_at: Mapped[datetime | None] = mapped_column(DateTime)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                                 default=utcnow)


class DailySnapshot(Base):
    """One JSON blob per (kind, date): 'gex' walls and regime, 'econ' calendar.

    UNIQUE on the pair, so a re-fetch on the same day overwrites that day
    rather than growing a pile of near-identical rows the desk would have to
    pick a winner from.
    """

    __tablename__ = "research_snapshot"
    __table_args__ = (
        UniqueConstraint("kind", "snapshot_date",
                         name="uq_research_snapshot_kind_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    snapshot_date: Mapped[str] = mapped_column(String(10), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_file: Mapped[str | None] = mapped_column(String(512))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                                 default=utcnow)


class Gex0dteHour(Base):
    """One net-gamma reading per CST trading hour.

    Keyed by (date, hour) rather than by push: the desk reads the day as a
    chain of hourly readings, and the last push inside an hour is the one
    closest to that hour's close. An hour never captured has NO row, and the
    reader renders the gap rather than interpolating it away -- a missing hour
    is information about the pusher, not a zero.
    """

    __tablename__ = "research_gex0dte_hour"
    __table_args__ = (
        UniqueConstraint("trade_date", "hour_cst",
                         name="uq_research_gex0dte_date_hour"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trade_date: Mapped[str] = mapped_column(String(10), nullable=False)
    hour_cst: Mapped[int] = mapped_column(Integer, nullable=False)
    ticker: Mapped[str] = mapped_column(String(12), nullable=False, default="SPY")
    net_gex: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    call_gex: Mapped[float | None] = mapped_column(Float)
    put_gex: Mapped[float | None] = mapped_column(Float)
    spot: Mapped[float | None] = mapped_column(Float)
    regime: Mapped[str | None] = mapped_column(String(8))
    flip: Mapped[float | None] = mapped_column(Float)
    call_wall: Mapped[float | None] = mapped_column(Float)
    put_wall: Mapped[float | None] = mapped_column(Float)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                                 default=utcnow)


class PusherHeartbeat(Base):
    """One row per push cycle of the browser-side 0DTE pusher, ok or not.

    APPEND-ONLY, unlike everything else here, and for a reason worth keeping:
    the snapshot tables upsert, so they hold no cadence at all -- "the last
    push landed at 14:40" is one mutable field with nothing behind it, and a
    gap cannot be resolved into "the tab died" versus "the tab was alive and
    every push was refused". Contiguous seq with ok=false means the timer ran
    and the push was rejected; a gap in seq means the timer stopped; seq
    restarting at 1 means a new document.
    """

    __tablename__ = "research_pusher_heartbeat"
    __table_args__ = (
        # Append-only is about how it is WRITTEN, not about tolerating the
        # same cycle twice. seq restarts at 1 per session and session is per
        # document, so the pair identifies one push cycle exactly. Without
        # this, re-ingesting the feed silently doubled every row and the
        # duplicates were indistinguishable from a pusher that really did fire
        # twice -- which is precisely the question this table exists to answer.
        UniqueConstraint("session", "seq",
                         name="uq_research_pusher_session_seq"),
        Index("ix_research_pusher_received", "received_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session: Mapped[str] = mapped_column(String(16), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(String(160))
    wall_ms: Mapped[int | None] = mapped_column(BigInteger)
    mono_ms: Mapped[int | None] = mapped_column(BigInteger)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False,
                                                  default=utcnow)
