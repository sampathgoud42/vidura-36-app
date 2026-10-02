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
    # Float, not Integer: Kalshi sizes in 0.01-contract increments and a
    # dollar-budgeted parlay is fractional by construction (7.98, 40.20).
    # An integer column silently truncates that on any database stricter
    # than SQLite, and truncating a size is a wrong number, not a
    # rounding.
    contracts: Mapped[float | None] = mapped_column(Float)
    entry_price: Mapped[float | None] = mapped_column(Float)
    exit_price: Mapped[float | None] = mapped_column(Float)
    realized_pnl: Mapped[float | None] = mapped_column(Float)

    # What the desk shows, in the terms an operator thinks in. The columns
    # above are per-CONTRACT cents and a count; nobody reads a ledger that
    # way. These are the question, the side taken, and the CASH.
    #
    #   market_title  "NAD vs FED Winner?"
    #   outcome       "FED"
    #   entry_usd     what leaving the account cost, FEES INCLUDED
    #   exit_usd      what came back, fees deducted; null while open
    #   fees_usd      what the exchange took, kept separately so a P&L can
    #                 be explained rather than merely stated
    #
    # Stored rather than derived because fees are not a function of price and
    # count -- Kalshi charges its own way, and reconstructing them later from
    # a rounded price is how a ledger drifts from the statement.
    market_title: Mapped[str | None] = mapped_column(String(256))
    outcome: Mapped[str | None] = mapped_column(String(128))
    entry_usd: Mapped[float | None] = mapped_column(Float)
    exit_usd: Mapped[float | None] = mapped_column(Float)
    fees_usd: Mapped[float | None] = mapped_column(Float)

    # NULLABLE ON PURPOSE. 93 of sampath's v2 rows genuinely predate the
    # dry-run column and their mode is unknowable from the file. Unknown
    # stays unknown; it is never guessed, and the ledger surfaces the count
    # rather than laundering them into "paper".
    is_live: Mapped[bool | None] = mapped_column(Boolean)

    # Replaces stamps buried inside a JSON blob. Ingest refuses to overwrite
    # a row reconciliation has corrected, or the next auto-sync reverts it.
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime)
    fee_checked_at: Mapped[datetime | None] = mapped_column(DateTime)

    # How many sweeps have looked for this trade and found nothing -- no
    # position, no settlement, no fill. Counted rather than assumed, because
    # "the exchange has not caught up yet" and "this trade never existed" look
    # identical on any single pass and are only told apart by asking again.
    resolve_attempts: Mapped[int] = mapped_column(Integer, nullable=False,
                                                  server_default="0",
                                                  default=0)

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
            # not_found is a real outcome, not a missing one: the exchange
            # has been asked three times over eighteen hours and has no
            # position, settlement or fill for this ticker. Recording that is
            # honest; leaving the row open forever pretends somebody is still
            # waiting on an answer that is not coming.
            "status in ('open','closed','cancelled','won','lost','settled',"
            "'not_found')",
            name="status_known"),
        Index("ix_bot_trade_tenant_bot_opened", "tenant_id", "bot_key", "opened_at"),
    )


class SignalTrade(Base, TenantOwned, Timestamped):
    """One position taken by hand from a DMI signal on the Bot Station, on the
    asset's Kalshi fifteen-minute market, and watched until it is out.

    The row IS the watch. The background loop reads every ``watching`` row on
    each pass, so a trade survives a restart of this process: the take-profit
    and the stop-loss resume from here rather than from memory. Nothing rests
    on the exchange -- entries and exits are immediate-or-cancel -- so there is
    no order to reconcile against this row, only the position.
    """

    __tablename__ = "signal_trade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = tenant_fk()

    # The confirmation's own id, sent by the form. A confirmation that arrives
    # twice -- a double click, a retry after a dropped response -- is one
    # trade, not two; it is also the exchange's idempotency key for the buy.
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)

    asset: Mapped[str] = mapped_column(String(16), nullable=False)   # btc, gold15
    series: Mapped[str] = mapped_column(String(24), nullable=False)  # KXBTC15M
    ticker: Mapped[str] = mapped_column(String(64), nullable=False)
    signal: Mapped[str] = mapped_column(String(4), nullable=False)   # call | put
    # Whether 5m agreed when it was confirmed (the strip's check mark).
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    side: Mapped[str] = mapped_column(String(3), nullable=False)     # yes | no

    contracts: Mapped[float] = mapped_column(Float, nullable=False)  # asked for
    filled: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    entry_c: Mapped[float | None] = mapped_column(Float)
    tp_c: Mapped[float | None] = mapped_column(Float)
    sl_c: Mapped[float | None] = mapped_column(Float)
    # When the quarter closes: past it the position is left to settle.
    close_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    order_id: Mapped[str | None] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(16), nullable=False,
                                        default="watching")
    exited: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    exit_c: Mapped[float | None] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(String(255))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id", name="tenant_request"),
        CheckConstraint("side in ('yes','no')", name="side_known"),
        CheckConstraint("signal in ('call','put')", name="signal_known"),
        #   watching   held, take-profit and stop-loss live
        #   tp / sl    sold on that exit
        #   expired    still held when the quarter closed; left to settle
        #   closed     no longer held, and not by this desk (sold elsewhere)
        #   unfilled   the buy found nobody to sell to; nothing was bought
        #   unwatched  a RISKY buy: bought whatever the bid, and nothing
        #              watches it -- no take-profit, no stop-loss
        CheckConstraint(
            "status in ('watching','tp','sl','expired','closed','unfilled',"
            "'unwatched')",
            name="status_known"),
        Index("ix_signal_trade_tenant_status", "tenant_id", "status"),
    )
