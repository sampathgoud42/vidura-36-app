"""The bots that ship with this project.

Every one of these is a config entry and an adapter, exactly like a bot
somebody adds tomorrow. There is no privileged path for the built-ins -- if
there were, the onboarding contract would only be proven for the throwaway
test bot and not for anything real.

The vendored scripts under runtime/ are unchanged. They are the strategies,
which is the product; this file is the plumbing that launches them.
"""

from __future__ import annotations

import csv
from pathlib import Path

from app.domains.botstation.adapters import TradeRecord
from app.domains.botstation.registry import BotConfig, BotVersion, register

_BTC15 = "prediction-trade/kalshi/btc/btc15"
_BTC60 = "prediction-trade/kalshi/btc/btc60"
_SPORTS = "prediction-trade/kalshi/sports"
_COMMOD = "prediction-trade/kalshi/commodities"

# Options every Kalshi bot accepts. Declared once and shared by value, not by
# inheritance -- a bot that wants different bounds writes its own dict rather
# than overriding a base class nobody can see the shape of.
_RISK_OPTIONS = {
    "bankroll": {"type": "number", "min": 1, "default": 50,
                 "label": "Bankroll ($)"},
    "target_pct": {"type": "number", "min": 1, "max": 500, "default": 25,
                   "label": "Target (% of bankroll)"},
    "stop_pct": {"type": "number", "min": 1, "max": 100, "default": 50,
                 "label": "Bank stop-loss (%)"},
    "contracts": {"type": "integer", "min": 1, "default": 1,
                  "label": "Contracts per trade"},
}


class _CsvLedgerAdapter:
    """Reads a bot own trade CSV and maps it onto the shared ledger.

    The CSVs stay bot-owned and read-only. Phase 2 kept them that way
    deliberately: removing them means changing the vendored bots, which is
    outside this rebuild.
    """

    config: BotConfig
    filename: str = ""
    ticker_field: str = "ticker"

    def _path(self, tenant_slug: str) -> Path:
        from app.core.config import get_settings
        return (get_settings().customers_root / tenant_slug /
                "trade_history" / self.filename)

    def external_id(self, record: dict) -> str:
        """Deterministic, from the record own content.

        Ticker plus opening timestamp. Real ledgers DO contain duplicate
        tickers across days, which is why the timestamp is part of it, and a
        row counter is not -- a counter changes the moment a row is inserted
        anywhere earlier in the file.
        """
        stamp = (record.get("timestamp") or record.get("ts")
                 or record.get("opened_at") or "")
        return f"{self.config.key}:{record.get(self.ticker_field, '')}:{stamp}"

    @staticmethod
    def _num(value) -> float | None:
        if value is None:
            return None
        text = str(value).strip().replace("%", "").replace("$", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _live(record: dict) -> bool | None:
        """Paper or live, or genuinely unknown.

        The v2 CSV carries a dry-run column on rows written after it was
        added and nothing at all on the 231/93 split before it. Absent means
        UNKNOWN and is returned as None -- never guessed, never defaulted to
        paper, because a real-money row labelled paper is a lie the ledger
        would then repeat forever.
        """
        for field in ("dry_run", "DRY_RUN_MODE", "is_live", "mode"):
            if field in record and str(record[field]).strip():
                raw = str(record[field]).strip().upper()
                if field in ("dry_run", "DRY_RUN_MODE"):
                    return raw not in ("TRUE", "1", "YES")
                if field == "is_live":
                    return raw in ("TRUE", "1", "YES")
                return raw == "LIVE"
        return None

    def to_trade(self, record: dict) -> TradeRecord:
        closed = record.get("ts_close") or record.get("closed_at")
        return TradeRecord(
            external_id=self.external_id(record),
            ticker=str(record.get(self.ticker_field, "")),
            status=str(record.get("status") or
                       ("closed" if closed else "open")).lower(),
            opened_at=record.get("timestamp") or record.get("ts"),
            closed_at=closed,
            contracts=int(self._num(record.get("contracts")) or 0) or None,
            entry_price=self._num(record.get("entry_price")
                                  or record.get("buy_price")),
            exit_price=self._num(record.get("exit_price")
                                 or record.get("pv_close")),
            realized_pnl=self._num(record.get("pnl")
                                   or record.get("realized_pnl")),
            is_live=self._live(record),
            raw=dict(record),
        )

    def read_records(self, *, tenant_slug: str) -> list[dict]:
        path = self._path(tenant_slug)
        if not self.filename or not path.is_file():
            return []
        with path.open(newline="", encoding="utf-8-sig", errors="replace") as fh:
            return [row for row in csv.DictReader(fh)
                    if any((v or "").strip() for v in row.values())]


def _bot(key, name, category, cadence, versions, launch_style,
         filename="", options=None) -> tuple[BotConfig, object]:
    config = BotConfig(key=key, name=name, category=category, cadence=cadence,
                       versions=versions, launch_style=launch_style,
                       options_schema=options or dict(_RISK_OPTIONS))
    adapter = type(f"{key.title()}Adapter", (_CsvLedgerAdapter,),
                   {"config": config, "filename": filename})()
    return config, adapter


BUILTIN = [
    _bot("btc15", "Kalshi BTC 15-minute bot", "btc", "15m",
         (BotVersion("v2", f"{_BTC15}/v2_bot_kalshi_btc15.py", default=True),
          BotVersion("v3", f"{_BTC15}/v3_bot_kalshi_btc15.py"),
          BotVersion("v4", f"{_BTC15}/v4_bot_kalshi_btc15.py"),
          BotVersion("v5", f"{_BTC15}/v5_bot_btc_15_2.py")),
         "cwd_customer", "v2_trade_history.csv"),
    _bot("btc60", "Kalshi BTC 60-minute bot", "btc", "60m",
         (BotVersion("fable5", f"{_BTC60}/bot_kalshi_btc60_fable5.py", default=True),
          BotVersion("burst", f"{_BTC60}/bot_kalshi_btc60_burst.py")),
         "env_customer"),
    _bot("sports", "Kalshi multi-sport bot", "sports", "live-match",
         (BotVersion("main", f"{_SPORTS}/bot_kalshi_main.py", default=True),
          BotVersion("v1", f"{_SPORTS}/bot_kalshi_sports_v1.py"),
          BotVersion("v2", f"{_SPORTS}/bot_kalshi_sports_v2.py")),
         "argv_customer", "trade_history_main.csv"),
    _bot("parley", "Kalshi live-sport parlay bot", "sports", "live-match",
         (BotVersion("v1", f"{_SPORTS}/bot_kalshi_parley.py", default=True),),
         "argv_customer", "paper_parley.csv"),
    _bot("gold15", "Kalshi Gold 15-minute bot", "commodities", "15m",
         (BotVersion("v1", f"{_COMMOD}/gold15/bot_kalshi_gold15.py"),
          BotVersion("v2", f"{_COMMOD}/gold15/v2_bot_kalshi_gold15.py", default=True)),
         "cwd_customer"),
    _bot("silver15", "Kalshi Silver 15-minute bot", "commodities", "15m",
         (BotVersion("v1", f"{_COMMOD}/silver15/bot_kalshi_silver15.py"),
          BotVersion("v2", f"{_COMMOD}/silver15/v2_bot_kalshi_silver15.py", default=True)),
         "cwd_customer"),
    _bot("oil15", "Kalshi WTI Oil 15-minute bot", "commodities", "15m",
         (BotVersion("v1", f"{_COMMOD}/oil15/bot_kalshi_oil15.py"),
          BotVersion("v2", f"{_COMMOD}/oil15/v2_bot_kalshi_oil15.py", default=True)),
         "cwd_customer"),
]


def register_all() -> None:
    """Idempotent: re-registering a bot is a no-op rather than an error, so a
    second create_app() in one process (which is what a test does) does not
    fall over."""
    from app.domains.botstation import registry

    for config, adapter in BUILTIN:
        if config.key not in {c.key for c in registry.all_bots()}:
            register(config, adapter)
