"""Trading domain: positions, the execution-safety tables, and signals."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (Boolean, CheckConstraint, DateTime, Float, ForeignKey,
                        Index, Integer, String, Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.base import Base, TenantOwned, Timestamped, tenant_fk


def _uuid() -> str:
    return str(uuid.uuid4())


class Position(Base, TenantOwned, Timestamped):
    """An options position and both of its exits."""

    __tablename__ = "position"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = tenant_fk()

    # Paper and live must never be confusable. Sandbox is the default
    # everywhere, so reaching the real account is always a deliberate act.
    venue_sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # The LONG-TERM (SIM) venue: a paper position held by the in-house
    # simulator (execution.sim), not by Tradier's sandbox. Always with
    # venue_sandbox true -- it is never the real account.
    simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                            server_default="0")

    underlying: Mapped[str] = mapped_column(String(16), nullable=False)
    occ_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    option_type: Mapped[str] = mapped_column(String(4), nullable=False)
    strike: Mapped[float] = mapped_column(Float, nullable=False)
    expiration: Mapped[str] = mapped_column(String(10), nullable=False)

    # SIGNED. A call's delta runs 0..+1 and a put's 0..-1; storing the
    # magnitude recorded every put as positive and made a vendor sign flip
    # undetectable.
    delta_at_entry: Mapped[float | None] = mapped_column(Float)

    contracts: Mapped[int] = mapped_column(Integer, nullable=False)
    buy_pct: Mapped[float] = mapped_column(Float, nullable=False)
    tolerance_pct: Mapped[float] = mapped_column(Float, nullable=False, default=25.0)

    entry_price: Mapped[float | None] = mapped_column(Float)
    tp_pct: Mapped[float] = mapped_column(Float, nullable=False)
    sl_pct: Mapped[float] = mapped_column(Float, nullable=False)
    tp_price: Mapped[float | None] = mapped_column(Float)
    sl_price: Mapped[float | None] = mapped_column(Float)

    buy_order_id: Mapped[str | None] = mapped_column(String(64))
    # How the buy was priced (selection.ORDER_TYPES): smart, market, or limit
    # -- the mark less discount_pct. Null on rows placed before these existed.
    order_type: Mapped[str | None] = mapped_column(String(8))
    # The buy's own limit; null for a market order.
    limit_price: Mapped[float | None] = mapped_column(Float)
    discount_pct: Mapped[float | None] = mapped_column(Float)
    # When a limit that has not filled is withdrawn (UTC, like opened_at).
    buy_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    tp_order_id: Mapped[str | None] = mapped_column(String(64))
    # New in the rebuild: the stop that rests AT THE VENUE, so it survives
    # this process dying. Null means only the monitored stop is protecting
    # this position, which stop_protection then says out loud.
    stop_order_id: Mapped[str | None] = mapped_column(String(64))
    stop_protection: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending")

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    strategy: Mapped[str] = mapped_column(String(64), nullable=False, default="Manual")
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    opened_at: Mapped[datetime | None] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    exit_price: Mapped[float | None] = mapped_column(Float)
    # Derived, but stored: the ledger sorts and aggregates on it.
    pnl_usd: Mapped[float | None] = mapped_column(Float)

    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("option_type in ('call','put')", name="option_type_known"),
        CheckConstraint(
            "status in ('pending','open','tp_filled','sl_filled','closed','failed')",
            name="status_known"),
        CheckConstraint(
            "stop_protection in ('pending','venue_resting','monitored_only')",
            name="stop_protection_known"),
        CheckConstraint("contracts > 0", name="contracts_positive"),
        CheckConstraint("tp_pct > 0", name="tp_positive"),
        CheckConstraint("sl_pct > 0 and sl_pct < 100", name="sl_in_range"),
        # The monitor's hot path, every 10 seconds.
        Index("ix_position_tenant_status", "tenant_id", "status"),
        # Guard 3: does this tenant already hold this contract?
        Index("ix_position_tenant_symbol_status",
              "tenant_id", "occ_symbol", "status"),
    )


class ExecutionAttempt(Base, TenantOwned, Timestamped):
    """What makes a duplicate order impossible to express.

    The row is written BEFORE the venue is called. A repeat submit hits the
    uniqueness constraint and returns this attempt's stored outcome instead
    of placing a second order. Check-then-act is a race; this is not.
    """

    __tablename__ = "execution_attempt"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = tenant_fk()

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    # Absorbs retries from clients that send no key: a hash of tenant,
    # contract, side, quantity and a short time bucket.
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)

    intent: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="in_flight")
    position_id: Mapped[int | None] = mapped_column(Integer)
    venue_order_id: Mapped[str | None] = mapped_column(String(64))
    response_json: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        # Scoped per tenant on purpose. A global key space would let one
        # operator's retry return another operator's order.
        UniqueConstraint("tenant_id", "idempotency_key", name="tenant_key"),
        UniqueConstraint("tenant_id", "request_fingerprint",
                         name="tenant_fingerprint"),
        CheckConstraint(
            "intent in ('open','open_contract','close','sweep','set_target',"
            "'carry_over','bot_start','bot_stop','bot_kill','bot_sync')",
            name="intent_known"),
        CheckConstraint("status in ('in_flight','succeeded','failed')",
                        name="status_known"),
    )


class ExecutionLease(Base):
    """A mutex that holds across processes.

    Today's guard is an in-process threading.Lock, which two uvicorn workers
    do not share — and two have run at once on this machine. Taken inside a
    BEGIN IMMEDIATE transaction, SQLite's single-writer semantics make this a
    real lock for every process on one machine.

    Not TenantOwned: the resource key already carries the tenant, and a lease
    is transient bookkeeping rather than operator data.
    """

    __tablename__ = "execution_lease"

    resource_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    holder: Mapped[str] = mapped_column(String(64), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # A crashed holder must not lock its contract out until someone notices.
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class RiskHeartbeat(Base, TenantOwned):
    """The stop's own watchdog.

    A stop-loss that exists only inside a running loop is not a risk control.
    This is what lets the order path refuse an entry when nobody is watching,
    and what /readiness reports to ops.
    """

    __tablename__ = "risk_heartbeat"

    # A real foreign key, not just a column that happens to hold a tenant id.
    # It was NOT NULL and scope-enforced but unreferenced, so a heartbeat could
    # outlive the operator it described -- and a stale row for a deleted tenant
    # reads as "recently swept" to the guard that refuses entries.
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenant.id", ondelete="CASCADE"),
        primary_key=True)
    last_pass_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime)
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


class Signal(Base, Timestamped):
    """Super-research signals: market data, identical for every operator.

    THE ONLY MODEL IN THE SCHEMA WITHOUT A TENANT. The exemption is
    enumerated in the registry rather than implied, so adding a second one is
    a visible decision instead of an accident.
    """

    __tablename__ = "signal"
    __tenant_scoped__ = False

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book: Mapped[str] = mapped_column(String(8), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    ticker: Mapped[str] = mapped_column(String(24), nullable=False)
    side: Mapped[str | None] = mapped_column(String(8))
    grade: Mapped[float | None] = mapped_column(Float)
    logged_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    raw: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("book", "external_id", name="book_external"),
        # Feeds sort descending and cap; this is that query.
        Index("ix_signal_book_logged", "book", "logged_at"),
    )


class PositionRollover(Base, TenantOwned, Timestamped):
    """A position held over the close: one row per position per session.

    Written at the close (risk.rollover) for every position marked to carry
    -- bought on a 7+ day expiry, or carried by hand -- that is still open
    with neither its target nor its stop hit. It is the record of what was
    held overnight and in what state: the closing bid, the unrealised P&L,
    and whether both exits were still resting at the venue to protect it.
    """

    __tablename__ = "position_rollover"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = tenant_fk()
    position_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("position.id", ondelete="CASCADE"), nullable=False)
    # The session it was held over, CST: 2026-10-05 means into 10-06.
    rolled_on: Mapped[str] = mapped_column(String(10), nullable=False)
    venue_sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False)
    underlying: Mapped[str] = mapped_column(String(16), nullable=False)
    occ_symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    option_type: Mapped[str] = mapped_column(String(4), nullable=False)
    strike: Mapped[float] = mapped_column(Float, nullable=False)
    expiration: Mapped[str] = mapped_column(String(10), nullable=False)
    days_left: Mapped[int] = mapped_column(Integer, nullable=False)
    contracts: Mapped[int] = mapped_column(Integer, nullable=False)
    entry_price: Mapped[float | None] = mapped_column(Float)
    close_bid: Mapped[float | None] = mapped_column(Float)
    unrealised_usd: Mapped[float | None] = mapped_column(Float)
    tp_price: Mapped[float | None] = mapped_column(Float)
    sl_price: Mapped[float | None] = mapped_column(Float)
    tp_order_id: Mapped[str | None] = mapped_column(String(64))
    stop_order_id: Mapped[str | None] = mapped_column(String(64))
    # The exits as the venue reported them at the close: open, filled, ...
    tp_status: Mapped[str | None] = mapped_column(String(24))
    stop_status: Mapped[str | None] = mapped_column(String(24))
    stop_protection: Mapped[str] = mapped_column(String(16), nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("tenant_id", "position_id", "rolled_on", name="one_roll_per_session"),
        Index("ix_position_rollover_tenant_day", "tenant_id", "rolled_on"),
    )


# ---- the LONG-TERM (SIM) venue -----------------------------------------------
# An in-house paper broker (execution.sim): an operator's simulated cash,
# holdings and orders, filled against real Tradier quotes. Labelled
# "LONG-TERM (SIM)" everywhere it shows -- it is never presented as a real
# account.

class SimAccount(Base, TenantOwned, Timestamped):
    """One operator's simulated account, and whether it is the paper venue
    their board trades (``active``) rather than Tradier's sandbox."""

    __tablename__ = "sim_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = tenant_fk()
    label: Mapped[str] = mapped_column(String(32), nullable=False, default="LONG-TERM (SIM)")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cash: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # what it was seeded with, and when -- the account's own history
    seeded_equity: Mapped[float | None] = mapped_column(Float)
    seeded_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("tenant_id", name="one_sim_account_per_tenant"),)


class SimHolding(Base, TenantOwned, Timestamped):
    """A simulated holding: shares (asset "equity") or an option contract."""

    __tablename__ = "sim_holding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = tenant_fk()
    asset: Mapped[str] = mapped_column(String(8), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)   # ticker or OCC
    underlying: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    avg_price: Mapped[float] = mapped_column(Float, nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (UniqueConstraint("tenant_id", "symbol", name="one_sim_holding_per_symbol"),)


class SimOrder(Base, TenantOwned, Timestamped):
    """A simulated order. Its id is the order id the desk sees."""

    __tablename__ = "sim_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = tenant_fk()
    asset: Mapped[str] = mapped_column(String(8), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    underlying: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    order_type: Mapped[str] = mapped_column(String(8), nullable=False)
    price: Mapped[float | None] = mapped_column(Float)
    stop_price: Mapped[float | None] = mapped_column(Float)
    duration: Mapped[str] = mapped_column(String(4), nullable=False, default="day")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    avg_fill_price: Mapped[float | None] = mapped_column(Float)
    exec_quantity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    realized: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(String(255))
    filled_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (Index("ix_sim_order_tenant_status", "tenant_id", "status"),)

