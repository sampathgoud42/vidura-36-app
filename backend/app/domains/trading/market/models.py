"""Stored scans: the Best Bets sheet and BreakoutRadar's results, in tables.

A sweep costs a minute or more of vendor calls -- sixty Tradier requests for
Best Bets, five hundred tickers from Yahoo per BreakoutRadar scan -- and until
now its result lived only in memory: every restart, and every first visit of
the day, started from an empty sheet and a wait. Here each combination's last
result is kept, so a sheet opens on it at once, stamped with when it ran.

TRUNCATE AND LOAD. A combination's rows are never updated in place: a scan
deletes every row of its combination and inserts the new ones, with the run
row that dates them, in ONE transaction. A reader sees the old scan or the new
one, never half of each, and a sweep that fails leaves the last good scan
standing rather than an empty table that reads as a quiet market.

MARKET DATA, NOT OPERATOR DATA, and so without a tenant -- the registry lists
all three by name. Best Bets screens one configured universe with one set of
rules, and BreakoutRadar judges the same Yahoo candles for everyone: the rows
are facts about the market, the same for every operator on a venue. The
operator's credential is only the pipe a sweep is read through, and copying
the result per tenant would mean N identical sweeps against a venue that
allows sixty requests a minute.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.base import Base, utcnow


class ScanRun(Base):
    """When one combination was last scanned, and what the scan said overall.

    ONE row per (kind, combo): "best_bets" by venue ("live", "sandbox"), and
    "breakout" by market and timeframe ("US:1d"). It is replaced along with
    the combination's rows, so its time is always the time of the rows beside
    it.
    """

    __tablename__ = "scan_run"
    __table_args__ = (
        UniqueConstraint("kind", "combo", name="uq_scan_run_kind_combo"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    combo: Mapped[str] = mapped_column(String(24), nullable=False)
    # The desk's day (Central time) the scan ran on: "has this combination
    # been scanned today" is the question the first sign-in asks.
    trade_date: Mapped[str] = mapped_column(String(10), nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    took_s: Mapped[float | None] = mapped_column(Float)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # "daily" (the day's first sign-in), "rescan" (someone asked), "first"
    # (a sheet opened on a combination never scanned).
    trigger: Mapped[str] = mapped_column(String(16), nullable=False, default="rescan")
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class BestBetsRow(Base):
    """One symbol of a Best Bets sweep, in the sheet's order."""

    __tablename__ = "scan_best_bets_row"
    __table_args__ = (
        Index("ix_scan_best_bets_row_venue_rank", "venue", "rank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    venue: Mapped[str] = mapped_column(String(8), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    setup: Mapped[str | None] = mapped_column(String(1))
    available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # The whole row as the sheet reads it: the screen's columns change more
    # often than this table should.
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    scanned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class BreakoutRow(Base):
    """One ticker of a BreakoutRadar scan: a breakout, or a near miss."""

    __tablename__ = "scan_breakout_row"
    __table_args__ = (
        Index("ix_scan_breakout_row_combo", "market", "timeframe", "section", "rank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    market: Mapped[str] = mapped_column(String(8), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(4), nullable=False)
    # "pass": all eight rules hold. "near": one rule short.
    section: Mapped[str] = mapped_column(String(8), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    ticker: Mapped[str] = mapped_column(String(24), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    scanned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
