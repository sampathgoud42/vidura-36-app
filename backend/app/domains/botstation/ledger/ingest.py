"""Bot records into the shared ledger.

There is no per-family branching here, and that absence is the point. The old
ingest had an eight-arm switch on bot_key -- the "orchestration dispatch
switch" the onboarding contract forbids editing -- because each family's CSV
had its own shape. The adapter now owns that translation, so this module never
learns a bot's name.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.botstation import registry
from app.domains.botstation.models import BotTrade
from app.platform.db.session import session_scope

logger = logging.getLogger(__name__)


def _as_datetime(value) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    # Bots write timestamps in whatever their author reached for. Try the
    # shapes actually seen in the files rather than guessing a single one.
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        logger.debug("unparseable timestamp %r", value)
        return None


def record(*, tenant_id: str, bot_key: str, records: list[dict],
           db: Session | None = None, bot_version: str | None = None,
           run_id: int | None = None) -> dict:
    """Upsert this bot's records. Idempotent by external id."""
    if db is not None:
        return _record_on(db, tenant_id, bot_key, records, bot_version, run_id)
    with session_scope() as own:
        return _record_on(own, tenant_id, bot_key, records, bot_version, run_id)


def _record_on(db: Session, tenant_id: str, bot_key: str, records: list[dict],
               bot_version: str | None, run_id: int | None) -> dict:
    adapter = registry.adapter_for(bot_key)
    inserted = updated = skipped = 0

    for raw in records:
        trade = adapter.to_trade(raw)
        existing = db.scalar(select(BotTrade).where(
            BotTrade.tenant_id == tenant_id,
            BotTrade.bot_key == bot_key,
            BotTrade.external_id == trade.external_id,
        ))

        if existing is not None:
            # Reconciliation priced this row from the exchange's own fills.
            # The bot's estimate must never overwrite that -- without this
            # lock the next auto-sync reverts every correction, which is how
            # roughly $8k of overstated P&L survived as long as it did.
            if existing.reconciled_at is not None:
                skipped += 1
                continue
            _apply(existing, trade)
            updated += 1
            continue

        row = BotTrade(tenant_id=tenant_id, bot_key=bot_key,
                       bot_version=bot_version, run_id=run_id,
                       external_id=trade.external_id)
        _apply(row, trade)
        db.add(row)
        inserted += 1

    db.flush()
    return {"inserted": inserted, "updated": updated,
            "skipped_reconciled": skipped, "total": len(records)}


def _apply(row: BotTrade, trade) -> None:
    row.ticker = trade.ticker
    row.status = trade.status
    row.opened_at = _as_datetime(trade.opened_at)
    row.closed_at = _as_datetime(trade.closed_at)
    row.contracts = trade.contracts
    row.entry_price = trade.entry_price
    row.exit_price = trade.exit_price
    row.realized_pnl = trade.realized_pnl
    # Unknown stays unknown, and is never inferred from anything else here.
    row.is_live = trade.is_live
    row.raw = json.dumps(trade.raw, default=str) if trade.raw else None
