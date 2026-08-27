from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Trade
from app.schemas.trade import PerformanceSummary, TradeCreate

WIN_STATUSES = {"won", "win"}
LOSS_STATUSES = {"lost", "loss"}
SETTLED_STATUSES = WIN_STATUSES | LOSS_STATUSES | {"settled", "closed"}


def record_trade(db: Session, user_id: str, payload: TradeCreate) -> Trade:
    data = payload.model_dump(exclude_none=True)
    # A manually recorded trade always states its mock flag, so its mode is
    # known — derive is_live from it rather than leaving it NULL, which the
    # ledger would read as "unknown" and hide from the default LIVE view.
    data.setdefault("is_live", not data.get("is_mock", True))
    trade = Trade(user_id=user_id, **data)
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


def query_trades(
    db: Session,
    *,
    user_id: str | None = None,
    bot_key: str | list[str] | None = None,
    bot_version: str | None = None,
    status: str | None = None,
    days: int | None = None,
    mode: str = "all",
    limit: int = 100,
    offset: int = 0,
) -> tuple[int, list[Trade]]:
    """``mode``: 'live' = real money only, 'paper' = simulated only, 'all' =
    everything. Rows whose mode is unknown (is_live NULL) appear only under
    'all', so a live-only ledger never quietly includes an unverified trade."""
    stmt = select(Trade)
    if mode == "live":
        stmt = stmt.where(Trade.is_live.is_(True))
    elif mode == "paper":
        stmt = stmt.where(Trade.is_live.is_(False))
    if user_id:
        stmt = stmt.where(Trade.user_id == user_id)
    if isinstance(bot_key, list):
        stmt = stmt.where(Trade.bot_key.in_(bot_key))
    elif bot_key:
        stmt = stmt.where(Trade.bot_key == bot_key)
    if bot_version:
        stmt = stmt.where(Trade.bot_version == bot_version)
    if status:
        stmt = stmt.where(Trade.status == status)
    if days:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
        stmt = stmt.where(Trade.opened_at >= cutoff)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(Trade.opened_at.desc()).limit(limit).offset(offset)
    return total, list(db.scalars(stmt).all())


def active_trades(db: Session, *, user_id: str | None = None, bot_key: str | None = None) -> list[Trade]:
    stmt = select(Trade).where(Trade.status == "open")
    if user_id:
        stmt = stmt.where(Trade.user_id == user_id)
    if bot_key:
        stmt = stmt.where(Trade.bot_key == bot_key)
    return list(db.scalars(stmt.order_by(Trade.opened_at.desc())).all())


def session_progress(db: Session, run) -> dict | None:
    """Realized bankroll progress for one RUNNING bot session.

    Sums the P&L of trades this run opened and has since closed, and expresses
    it against the bankroll typed at launch: "+0.2% of a $50 bank, target 50%".

    Scoped three ways, each protecting the number from a specific lie:
      - opened_at >= run.started_at — an earlier session's trades are not this
        session's progress;
      - settled statuses only — an open position has no realized P&L yet, and
        the user asked for progress AFTER each close;
      - is_live must match the run's mode — a paper run's wins must not count
        toward a live bankroll target, and rows whose mode is unknown count
        toward neither.

    The bankroll is the recorded launch config, not the live account balance:
    the account is shared across bots, so only the typed bank makes the
    percentage mean "this bot, this session".
    """
    if run is None or run.status != "running":
        return None
    extra = run.extra or {}
    bank = extra.get("bank")
    if bank is None and extra.get("sport_settings"):
        # sports records per-sport banks; the session bankroll is their sum
        banks = [v.get("bank") for v in extra["sport_settings"].values() if v.get("bank")]
        bank = round(sum(banks), 2) if banks else None

    want_live = run.mode == "live"
    stmt = select(Trade).where(
        Trade.user_id == run.user_id,
        Trade.bot_key == run.bot_key,
        Trade.opened_at >= run.started_at,
        Trade.status.in_(tuple(SETTLED_STATUSES)),
        Trade.is_live.is_(want_live),
    )
    rows = list(db.scalars(stmt).all())
    pnl = round(sum(r.pnl_usd or 0.0 for r in rows), 2)
    return {
        "trades_closed": len(rows),
        "pnl_usd": pnl,
        "bank": bank,
        "bankroll_pct": round(pnl / bank * 100, 2) if bank else None,
        "target_pct": extra.get("target_pct"),
    }


def performance(
    db: Session, *, user_id: str | None = None, bot_key: str | None = None,
    days: int | None = None, mode: str = "live",
) -> PerformanceSummary:
    """Aggregate over the SAME rows the trade-history view shows.

    ``mode`` defaults to 'live' to match the history endpoint. It used to fall
    through to query_trades' 'all', so the summary card counted paper trades
    while the table beneath it listed only live ones — two different totals
    for one panel, which is exactly how a scoreboard stops being trustworthy.
    """
    _, trades = query_trades(
        db, user_id=user_id, bot_key=bot_key, days=days, mode=mode,
        limit=100_000, offset=0,
    )
    by_status: dict[str, int] = {}
    wins = losses = settled = 0
    total_cost = total_pnl = 0.0
    for t in trades:
        by_status[t.status] = by_status.get(t.status, 0) + 1
        if t.status in WIN_STATUSES:
            wins += 1
        elif t.status in LOSS_STATUSES:
            losses += 1
        if t.status in SETTLED_STATUSES:
            settled += 1
        total_cost += t.cost_usd or 0.0
        total_pnl += t.pnl_usd or 0.0
    decided = wins + losses
    return PerformanceSummary(
        bot_key=bot_key,
        trades=len(trades),
        settled=settled,
        wins=wins,
        losses=losses,
        win_rate=round(wins / decided, 4) if decided else None,
        total_cost_usd=round(total_cost, 2),
        total_pnl_usd=round(total_pnl, 2),
        by_status=by_status,
    )
