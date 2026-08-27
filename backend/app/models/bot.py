from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.user import utcnow


class BotRun(Base):
    """One launched bot process (or mock run) and its lifecycle."""

    __tablename__ = "bot_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.user_id", ondelete="CASCADE"), index=True
    )
    bot_key: Mapped[str] = mapped_column(String(32), index=True)  # btc15 | btc60 | sports
    bot_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    script_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mode: Mapped[str] = mapped_column(String(16), default="paper")  # paper | live | mock
    status: Mapped[str] = mapped_column(String(16), default="running")
    # running | stopped | exited | failed
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    log_file: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="bot_runs")
