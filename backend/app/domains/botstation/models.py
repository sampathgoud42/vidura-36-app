"""Bot station: supervised runs and the shared trade ledger.

Nothing here names a bot family. Adding a bot must not add a table, so the
ledger is bot-agnostic and the family-specific knowledge lives in the
adapter — which is the whole point of the onboarding contract.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, DateTime, Float, Index,
                        Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.base import Base, TenantOwned, Timestamped, tenant_fk


class BotRun(Base, TenantOwned, Timestamped):
    """One supervised bot process."""

    __tablename__ = "bot_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = tenant_fk()

    bot_key: Mapped[str] = mapped_column(String(32), nullable=False)
    bot_version: Mapped[str] = mapped_column(String(16), nullable=False)
    # Paper-only forces every dry-run flag on; the run records which it was,
    # so a ledger row can always be traced to a run that knows.
    mode: Mapped[str] = mapped_column(String(8), nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    pid: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime)
    exit_code: Mapped[int | None] = mapped_column(Integer)

    # Per BOT, not per account. The venue account is shared across bots, so
    # an account-wide floor let one bot's drawdown halt the others.
    bankroll: Mapped[float | None] = mapped_column(Float)
    target_pct: Mapped[float | None] = mapped_column(Float)
    stop_pct: Mapped[float | None] = mapped_column(Float)
    # Whatever else this bot's declared schema accepted.
    options_json: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("mode in ('paper','live')", name="mode_known"),
        CheckConstraint(
            "status in ('running','stopped','crashed','killed')",
            name="status_known"),
        Index("ix_bot_run_tenant_bot_started", "tenant_id", "bot_key", "started_at"),
    )


class BotTrade(Base, TenantOwned, Timestamped):
    """One trade a bot recorded, mirrored into the shared ledger."""

    __tablename__ = "bot_trade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = tenant_fk()

    bot_key: Mapped[str] = mapped_column(String(32), nullable=False)
    bot_version: Mapped[str | None] = mapped_column(String(16))
    run_id: Mapped[int | None] = mapped_column(Integer)

    # Deterministic, supplied by the adapter, so re-ingesting is idempotent.
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)

    ticker: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    contracts: Mapped[int | None] = mapped_column(Integer)
    entry_price: Mapped[float | None] = mapped_column(Float)
    exit_price: Mapped[float | None] = mapped_column(Float)
    realized_pnl: Mapped[float | None] = mapped_column(Float)

    # NULLABLE ON PURPOSE. 93 of sampath's v2 rows genuinely predate the
    # dry-run column and their mode is unknowable from the file. Unknown
    # stays unknown; it is never guessed, and the ledger surfaces the count
    # rather than laundering them into "paper".
    is_live: Mapped[bool | None] = mapped_column(Boolean)

    # Replaces stamps buried inside a JSON blob. Ingest refuses to overwrite
    # a row reconciliation has corrected, or the next auto-sync reverts it.
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime)
    fee_checked_at: Mapped[datetime | None] = mapped_column(DateTime)

    # The source record, preserved verbatim.
    raw: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("tenant_id", "bot_key", "external_id",
                         name="tenant_bot_external"),
        # The real vocabulary, profiled from the data rather than invented.
        # A Kalshi contract RESOLVES -- it does not merely close -- and the
        # ledger holds 244 won, 118 lost and 5 settled. Collapsing those into
        # "closed" would throw away the win/loss record, which is most of what
        # a prediction-market ledger is for. My first enum allowed only
        # open/closed/cancelled and the import failed against it, which is the
        # constraint doing its job.
        CheckConstraint(
            "status in ('open','closed','cancelled','won','lost','settled')",
            name="status_known"),
        Index("ix_bot_trade_tenant_bot_opened", "tenant_id", "bot_key", "opened_at"),
    )
