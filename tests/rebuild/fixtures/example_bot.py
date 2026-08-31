"""A throwaway bot, onboarded the way the contract says a bot is onboarded.

This file IS the test. If onboarding a bot ever needs more than what is
written here — a new endpoint, a migration, an edit to a shared library, an
arm added to a dispatch switch — then the architecture has failed its primary
success criterion, and test_onboarding_bot.py says so by name.

Everything below is the complete cost of a new bot:
    1. one config entry   (EXAMPLE_BOT)
    2. one adapter class  (ExampleBotAdapter)
    3. nothing else       — discovery is automatic
"""

from __future__ import annotations

from app.domains.botstation.registry import BotConfig, BotVersion
from app.domains.botstation.adapters import BotAdapter, TradeRecord

# ---- 1. the config entry -------------------------------------------------

EXAMPLE_BOT = BotConfig(
    key="example15",
    name="Example 15-minute bot",
    category="example",
    cadence="15m",
    versions=(
        BotVersion("v1", "example/bot_example15.py", default=True),
    ),
    launch_style="env_customer",
    # The launch form renders itself from this. A new bot describes its own
    # options rather than getting a hand-written route and a hand-written
    # panel.
    options_schema={
        "bankroll": {"type": "number", "min": 1, "default": 50,
                     "label": "Bankroll"},
        "target_pct": {"type": "number", "min": 1, "max": 500, "default": 25,
                       "label": "Target %"},
        "contracts": {"type": "integer", "min": 1, "default": 1,
                      "label": "Contracts"},
    },
)


# ---- 2. the adapter ------------------------------------------------------

class ExampleBotAdapter(BotAdapter):
    """Maps this bot's own records onto the shared ledger.

    The only bot-specific knowledge in the system: how to read what this bot
    writes, and what its external id is. Everything else — lifecycle, status,
    logs, ledger, reconciliation — is shared.
    """

    config = EXAMPLE_BOT

    def external_id(self, record: dict) -> str:
        """Deterministic, so re-ingesting the same record is idempotent."""
        return f"example15:{record['ticker']}:{record['opened_at']}"

    def to_trade(self, record: dict) -> TradeRecord:
        return TradeRecord(
            external_id=self.external_id(record),
            ticker=record["ticker"],
            status=record["status"],
            opened_at=record["opened_at"],
            closed_at=record.get("closed_at"),
            contracts=int(record["contracts"]),
            entry_price=float(record["entry_price"]),
            exit_price=(float(record["exit_price"])
                        if record.get("exit_price") else None),
            realized_pnl=(float(record["realized_pnl"])
                          if record.get("realized_pnl") else None),
            # Unknown stays unknown. Never guessed.
            is_live=record.get("is_live"),
            raw=record,
        )
