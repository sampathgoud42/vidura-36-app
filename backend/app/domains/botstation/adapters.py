"""The plug point: what a new bot has to write, and nothing else.

The whole onboarding contract rests on this file being small. A bot author
supplies a config entry and one class implementing this interface; everything
around it -- lifecycle, status, logs, the ledger, reconciliation, the eight
HTTP operations -- is shared and already exists.

What deliberately is NOT here: anything about HOW a bot trades. The adapter
translates between a bot's own records and the shared ledger. Strategy stays
in the vendored script, because the strategies are the product and the
plumbing is not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class TradeRecord:
    """One trade, in the shape the shared ledger understands.

    ``is_live`` is Optional and that is load-bearing: 93 of sampath's v2 rows
    genuinely predate the flag that would say. Unknown stays unknown. A bot
    that guesses here is a bot that mislabels real money as paper.
    """

    external_id: str
    ticker: str
    status: str
    opened_at: datetime | str | None = None
    closed_at: datetime | str | None = None
    contracts: int | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    realized_pnl: float | None = None
    is_live: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class BotAdapter(Protocol):
    """Everything the shared machinery needs to know about one bot family."""

    config: Any

    def external_id(self, record: dict) -> str:
        """A DETERMINISTIC id for this record.

        Ingest upserts on it, so re-running must be idempotent. Derive it from
        the record's own content -- never from a row counter, a timestamp of
        when we read it, or anything else that changes between runs.
        """
        ...

    def to_trade(self, record: dict) -> TradeRecord:
        """Map one of this bot's records onto the shared ledger shape."""
        ...


def is_adapter(obj: Any) -> bool:
    """Duck-typed rather than isinstance: an adapter is what it can do.

    Requiring a base class would mean a bot author importing from a shared
    library, which is exactly what the onboarding contract forbids.
    """
    return all(callable(getattr(obj, name, None))
               for name in ("external_id", "to_trade"))
