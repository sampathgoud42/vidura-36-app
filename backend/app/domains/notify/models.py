"""Super Signals to Telegram: each operator's feed, and what it has posted."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.base import Base, TenantOwned, Timestamped, tenant_fk


class TelegramFeed(Base, TenantOwned, Timestamped):
    """Where an operator's new Super Signals are posted, and whether they are.

    One row per operator and channel: "vidura" posts only the ⭐⭐⭐👍 signals,
    "super" every one (super_telegram.CHANNELS). The bot token is not here: it is a credential
    (venue 'telegram'), sealed like every other key the desk holds. Only
    signals that appear after ``enabled_at`` are posted -- switching the feed
    on must not empty a whole session's backlog into the channel.
    """

    __tablename__ = "telegram_feed"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = tenant_fk()
    channel: Mapped[str] = mapped_column(String(16), nullable=False, default="vidura",
                                         server_default="vidura")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Telegram's id for the chat: -100... for a channel, or @name.
    chat_id: Mapped[str | None] = mapped_column(String(64))
    chat_title: Mapped[str | None] = mapped_column(String(128))
    # The other posts, each its own switch: the half-hourly HOT boards, and
    # the SUPERHOT alerts. ``enabled`` stays the Super Signals switch.
    post_hot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                           server_default=false())
    post_superhot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                server_default=false())
    posted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_post_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Safe to show: never the token (notify's errors carry none).
    last_error: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        UniqueConstraint("tenant_id", "channel", name="one_feed_per_channel"),
    )


class TelegramPost(Base, TenantOwned, Timestamped):
    """One Super Signal posted to an operator's Telegram feed -- the record
    that keeps it from being posted again, across passes and restarts."""

    __tablename__ = "telegram_post"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = tenant_fk()
    # The desk's own id: agent|ticker|setup|direction|session time.
    signal_id: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "signal_id", name="one_post_per_signal"),
        Index("ix_telegram_post_tenant_created", "tenant_id", "created_at"),
    )
