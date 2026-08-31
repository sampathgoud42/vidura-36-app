"""Recording a trade at the moment a bot ENTERS it.

The other half of reconcile.py, whose docstring states the contract this
module exists to keep: "A bot records a trade when it ENTERS. It cannot record
the outcome, because the outcome happens later." Reconciliation only ever
CLOSES rows -- it has nothing to find if nothing opened one.

That is precisely what went wrong. The v2/v6 engines place real orders and
write nothing anywhere: no CSV for the adapter to read, no call to the ingest
endpoint. bot_trade stayed empty through live fills, the reconciler swept an
empty table every fifteen minutes, and the desk's trade history showed nothing
while money was moving. Every bot before them wrote a CSV that something else
ingested, so the gap only appeared with engines that talk to the exchange
directly.

Shared rather than per-bot on purpose: this is one row shape, and a second
copy would drift the first time either engine was touched -- the same reason
the ingest module refuses to know a bot's name.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.domains.botstation.models import BotTrade
from app.platform.db.session import session_scope
from app.tenancy.models import Tenant

logger = logging.getLogger(__name__)


def record_entry(*, tenant_slug: str, bot_key: str, bot_version: str | None,
                 ticker: str, external_id: str,
                 contracts: float | None = None,
                 entry_price_c: float | None = None,
                 market_title: str | None = None,
                 outcome: str | None = None,
                 entry_usd: float | None = None,
                 fees_usd: float | None = None,
                 is_live: bool | None = None,
                 raw: dict | None = None,
                 opened_at: datetime | None = None) -> bool:
    """Open one ledger row. True when a row was written.

    Idempotent by (tenant, bot, external_id), which is the exchange's own
    order or quote id: a retried pass, a restart mid-flight, or two engines
    reporting the same fill produce one row, not several. Recording a trade
    twice is worse than not recording it -- a duplicate is indistinguishable
    from a real second position in every figure downstream.

    Never raises. A bookkeeping failure must not take down a bot that is
    holding a live position; it is logged loudly and the caller carries on.
    """
    if not external_id:
        logger.warning("refusing to record %s on %s with no external id -- "
                       "an unkeyed row cannot be deduplicated or reconciled",
                       bot_key, ticker)
        return False
    try:
        with session_scope() as db:
            tenant = db.scalar(select(Tenant).where(
                Tenant.slug == tenant_slug.strip().lower()))
            if tenant is None:
                logger.warning("no operator %r to record a trade against",
                               tenant_slug)
                return False
            existing = db.scalar(select(BotTrade).where(
                BotTrade.tenant_id == tenant.id,
                BotTrade.bot_key == bot_key,
                BotTrade.external_id == external_id))
            if existing is not None:
                return False
            db.add(BotTrade(
                tenant_id=tenant.id, bot_key=bot_key,
                bot_version=bot_version, external_id=external_id,
                ticker=ticker, status="open",
                opened_at=opened_at or datetime.now(timezone.utc).replace(
                    tzinfo=None),
                # CENTS, matching the buy_price the CSV adapters have always
                # fed this column. Reconciliation replaces the estimate with
                # the exchange's own numbers later.
                entry_price=entry_price_c,
                contracts=contracts,
                market_title=market_title,
                outcome=outcome,
                # What actually left the account. Fees are ADDED here rather
                # than tracked beside the cost, because "what did this trade
                # cost me" is the question the desk asks and the answer is
                # never the contract price alone.
                entry_usd=(None if entry_usd is None
                           else round(float(entry_usd)
                                      + float(fees_usd or 0.0), 4)),
                fees_usd=fees_usd,
                is_live=is_live,
                raw=json.dumps(raw, default=str) if raw else None))
        return True
    except Exception as exc:                            # noqa: BLE001
        logger.warning("could not record %s %s (%s: %s)",
                       bot_key, ticker, type(exc).__name__, exc)
        return False
