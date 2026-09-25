"""Who is auto-trading the signal desk for an operator, across processes.

Two things can trade the desk's live signals for one operator: the desk's own
watcher (ARM AUTO TRADE -> super_signals or best_pairs, a thread inside the
API) and the standalone bot (backend/bot_best_pair, its own process). Both
enter through the same guarded path under the same per-signal idempotency key,
so one signal can never be bought twice. What that key cannot see is two
traders acting on DIFFERENT signals for the same idea -- two positions on TSLA
ten minutes apart -- or one signal bought at whichever size the process that
looked first was configured with.

So one of them owns the desk per operator at a time. The claim is a row in
execution_lease -- the cross-process mutex the order path already uses -- that
the owner renews while it runs. An owner that dies stops renewing, and the
claim expires on its own after TTL_S: a crashed bot must not lock the desk's
arm button out until somebody notices.

The per-ticker cooldown is shared the same way. It is read from the positions
table (recent_entries), so "one entry per ticker per hour" holds across both,
whichever of them opened the last one.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from app.domains.trading.execution import leases
from app.domains.trading.models import ExecutionLease, Position
from app.domains.trading.risk import clock
from app.platform.db.base import utcnow
from app.platform.db.session import session_factory

RESOURCE = "autotrade:signal-desk"
# The owner renews on every poll (15s), so two minutes is eight missed renewals
# -- long enough to ride out a slow order, short enough that a crashed owner
# frees the desk before an operator has finished wondering why.
TTL_S = 120

# What the signal-desk traders label their positions, and so what the shared
# cooldown counts. Manual buys and the level-cross watcher are not in it: they
# are not "the same signal idea arriving again".
SIGNAL_LABELS = ("Auto/super_signals", "Auto/best_pairs", "Auto/bot_best_pair")


@dataclass(frozen=True)
class Owner:
    """The current claim, as the desk shows it."""

    holder: str
    since: datetime          # naive UTC, the database's convention
    until: datetime

    def _part(self, i: int) -> str:
        parts = self.holder.split(":", 3)
        return parts[i] if len(parts) > i else ""

    @property
    def kind(self) -> str:
        """``desk`` for the API's own watcher, ``bot_best_pair`` for the bot."""
        return self._part(0)

    @property
    def detail(self) -> str:
        """The desk watcher's strategy, or the bot's venue (paper / live)."""
        return self._part(1)

    def describe(self) -> str:
        if self.kind == "desk":
            return f"the desk's own auto-trader ({self.detail or 'armed'})"
        who = f"{self.kind} ({self.detail})" if self.detail else self.kind
        return f"{who}, pid {self._part(2)} on {self._part(3) or '?'}"

    def public(self) -> dict:
        return {"holder": self.holder, "kind": self.kind, "detail": self.detail,
                "pid": self._part(2), "host": self._part(3),
                "describe": self.describe(),
                "since": self.since.replace(tzinfo=UTC).isoformat(),
                "until": self.until.replace(tzinfo=UTC).isoformat()}


def holder_name(kind: str, detail: str = "", *, instance: int | None = None) -> str:
    """kind:detail:pid[.instance]:host.

    The pid comes before the hostname because the column is 64 characters: a
    long hostname may be cut, the pid never is, and two processes on one
    machine must never share a name. ``instance`` tells apart two claims made
    by one process -- the desk arms a new watcher per arm, and the thread of
    the one before must not release the claim of the one after."""
    pid = f"{os.getpid()}.{instance}" if instance is not None else str(os.getpid())
    return f"{kind}:{detail}:{pid}:{socket.gethostname()}"[:64]


def _key(tenant_id: str) -> str:
    return leases.resource_key(tenant_id, RESOURCE)


def _owner(row: ExecutionLease | None) -> Owner | None:
    if row is None:
        return None
    return Owner(holder=row.holder, since=row.acquired_at, until=row.expires_at)


def claim(tenant_id: str, holder: str, *, ttl_s: int = TTL_S) -> Owner | None:
    """Take the desk for ``holder``, or renew it. None when it is ours now;
    otherwise the owner that has it.

    Each step is a single conditional statement, so there is no gap between
    deciding the desk is free and taking it: renew a claim we hold, take over
    one that has expired, else insert -- and a lost insert race is the
    primary key refusing the second row, not a check that happened to pass.
    """
    key = _key(tenant_id)
    db = session_factory()()
    try:
        now = utcnow()
        until = now + timedelta(seconds=ttl_s)
        taken = db.execute(
            update(ExecutionLease)
            .where(ExecutionLease.resource_key == key, ExecutionLease.holder == holder)
            .values(expires_at=until)).rowcount
        if not taken:
            taken = db.execute(
                update(ExecutionLease)
                .where(ExecutionLease.resource_key == key,
                       ExecutionLease.expires_at <= now)
                .values(holder=holder, acquired_at=now, expires_at=until)).rowcount
        if not taken and db.get(ExecutionLease, key) is None:
            try:
                with db.begin_nested():
                    db.add(ExecutionLease(resource_key=key, tenant_id=tenant_id,
                                          holder=holder, acquired_at=now,
                                          expires_at=until))
                taken = 1
            except IntegrityError:
                taken = 0
        if taken:
            db.commit()
            return None
        db.rollback()
        return _owner(db.get(ExecutionLease, key))
    finally:
        db.close()


def release(tenant_id: str, holder: str) -> None:
    """Give the desk up -- only if it is still ours. A claim that expired and
    was taken over belongs to its new owner, and deleting it would hand the
    desk to a third process while the second is still trading."""
    db = session_factory()()
    try:
        db.execute(delete(ExecutionLease).where(
            ExecutionLease.resource_key == _key(tenant_id),
            ExecutionLease.holder == holder))
        db.commit()
    finally:
        db.close()


def current(tenant_id: str) -> Owner | None:
    """Who owns the desk right now, or None. An expired claim owns nothing."""
    db = session_factory()()
    try:
        row = db.get(ExecutionLease, _key(tenant_id))
        if row is None or row.expires_at <= utcnow():
            return None
        return _owner(row)
    finally:
        db.close()


def recent_entries(tenant_id: str, tickers, *, within_s: int) -> dict[str, datetime]:
    """When each ticker was last entered by a signal-desk trader -- the desk's
    watcher or the bot, paper or live -- inside the last ``within_s`` seconds,
    as desk-clock times ready for the cooldown to compare."""
    wanted = sorted({str(t).upper() for t in tickers or () if t})
    if not wanted:
        return {}
    db = session_factory()()
    try:
        rows = db.execute(
            select(Position.underlying, func.max(Position.opened_at))
            .where(Position.tenant_id == tenant_id,
                   Position.strategy.in_(SIGNAL_LABELS),
                   Position.underlying.in_(wanted),
                   Position.opened_at >= utcnow() - timedelta(seconds=within_s))
            .group_by(Position.underlying)).all()
    finally:
        db.close()
    return {ticker: at.replace(tzinfo=UTC).astimezone(clock.DESK_TZ)
            for ticker, at in rows if at is not None}
