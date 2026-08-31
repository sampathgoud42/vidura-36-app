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

# Every knob a bot launch accepts, declared once and shared BY VALUE rather
# than by inheritance -- a bot that wants different bounds writes its own dict
# instead of overriding a base class nobody can see the shape of.
#
# Two different levels of risk live here and the names say which is which:
#
#   tp_pct / sl_pct              per TRADE, against the entry price
#   bank_tp_pct / bank_sl_pct    per BANKROLL, against the bot own capital
#
# They were conflated in the old build -- "target_pct" meant the bankroll one
# and "stop loss" meant the trade one, in the same form. Two things called
# roughly the same thing, doing different jobs, one of which halts the bot.
_RISK_OPTIONS = {
    # --- per-trade exits ---------------------------------------------------
    "tp_pct": {"type": "number", "min": 0.1, "max": 500, "default": 15,
               "label": "Take-profit (% per trade)", "group": "Per trade"},
    "sl_pct": {"type": "number", "min": 0.1, "max": 99, "default": 30,
               "label": "Stop-loss (% per trade)", "group": "Per trade"},
    "contracts": {"type": "integer", "min": 1, "max": 500, "default": 1,
                  "label": "Contracts per trade", "group": "Per trade"},

    # --- bankroll ----------------------------------------------------------
    "bankroll": {"type": "number", "min": 1, "default": 50,
                 "label": "Bankroll ($)", "group": "Bankroll"},
    "bank_tp_pct": {"type": "number", "min": 1, "max": 1000, "default": 25,
                    "label": "Halt on bankroll gain (%)", "group": "Bankroll"},
    "bank_sl_pct": {"type": "number", "min": 1, "max": 100, "default": 50,
                    "label": "Halt on bankroll loss (%)", "group": "Bankroll"},

    # --- when it may trade -------------------------------------------------
    # A bot with no curfew trades overnight, which for the sports and BTC
    # families is exactly what it is FOR. So the range is optional and empty
    # means "no curfew" rather than "never".
    "time_start": {"type": "string", "default": "", "format": "HH:MM",
                   "label": "Trade from (CST)", "group": "Schedule"},
    "time_end": {"type": "string", "default": "", "format": "HH:MM",
                 "label": "Trade until (CST)", "group": "Schedule"},
    "no_trade_times": {"type": "string", "default": "",
                       "label": "Blackout windows (CST, comma separated)",
                       "group": "Schedule"},
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


# Parlay construction, on top of the shared risk options. These are real
# schema entries rather than constants because the launch form renders itself
# from the schema -- a version default for a key the schema does not know is
# silently DROPPED by effective_defaults, which is how "max 5 legs" can look
# configured while nothing reads it.
# The luck bot's form. It is not launched like the others -- there is no
# process to start -- so these are the numbers its PREVIEW and PLACE calls
# take, rendered from the same schema every other bot uses.
_LUCK_OPTIONS = {
    "min_legs": {"type": "integer", "min": 2, "max": 24, "default": 5,
                 "label": "Minimum legs", "group": "Ticket"},
    "max_legs": {"type": "integer", "min": 2, "max": 24, "default": 24,
                 "label": "Maximum legs", "group": "Ticket"},
    "min_leg_c": {"type": "integer", "min": 5, "max": 98, "default": 60,
                  "label": "Minimum leg price (c)", "group": "Ticket"},
    "min_volume_usd": {"type": "number", "min": 0, "default": 0,
                       "label": "Minimum leg volume ($)", "group": "Ticket"},
    "min_usd": {"type": "number", "min": 1, "max": 5000, "default": 5,
                "label": "Spend at least ($)", "group": "Ticket"},
    "max_usd": {"type": "number", "min": 1, "max": 5000, "default": 7.5,
                "label": "Spend at most ($)", "group": "Ticket"},
}

_PARLEY_OPTIONS = {
    # Everything the other bots take EXCEPT a contract count: a parlay is
    # sized by what it may spend, not by how many of it to buy.
    **{k: v for k, v in _RISK_OPTIONS.items() if k != "contracts"},
    # The budget for ONE parlay. The engine buys as many contracts as this
    # covers at the limit it is about to rest, and none if it cannot cover
    # one -- it never rounds up past the budget, because a stake that can be
    # exceeded is not a stake. Combo prices move with the legs (a 5-leg
    # parlay at 91c and one at 45c are both normal), so a fixed count spends
    # a different amount every pass while this spends the same.
    "stake_usd": {"type": "number", "min": 1, "max": 5000, "default": 12,
                  "label": "Dollars per parlay", "group": "Per trade"},
    "min_legs": {"type": "integer", "min": 2, "max": 5, "default": 2,
                 "label": "Minimum legs per combo", "group": "Parlay"},
    "max_legs": {"type": "integer", "min": 2, "max": 5, "default": 5,
                 "label": "Maximum legs per combo", "group": "Parlay"},
    "max_combos": {"type": "integer", "min": 1, "max": 20, "default": 1,
                   "label": "Combos per pass", "group": "Parlay"},
    # How far over the parlay's theoretical price we will go. A maker prices
    # a combo above the product of its legs -- that spread is their pay for
    # correlation risk -- so a ceiling at fair value never trades.
    # How many OPEN parlays may share one match. Every parlay holding it wins
    # or loses together, so this is the dial on correlated risk.
    "max_per_event": {"type": "integer", "min": 1, "max": 5, "default": 2,
                      "label": "Max parlays per match",
                      "group": "Parlay"},
    # If a parlay does not execute, raise the stake once by this much and try
    # again. A maker who will not fill a small ticket often fills a larger
    # one. The cap is on the whole escalation, not per step -- 0 turns it off.
    "escalation_pct": {"type": "number", "min": 0, "max": 100, "default": 30,
                       "label": "Raise stake by up to (%) if unfilled",
                       "group": "Parlay"},
    "fill_wait_s": {"type": "integer", "min": 5, "max": 600, "default": 60,
                    "label": "Seconds to wait before raising it",
                    "group": "Parlay"},
    # The daily long-shot ticket: one parlay a day, many legs, small stake.
    # A separate book from the regular parlays in both directions.
    "daily_enabled": {"type": "boolean", "default": False,
                      "label": "Daily long-shot ticket",
                      "group": "Daily ticket"},
    "daily_at": {"type": "string", "default": "17:30",
                 "label": "Time (HH:MM)", "group": "Daily ticket"},
    "daily_tz": {"type": "string", "default": "America/Chicago",
                 "label": "Timezone", "group": "Daily ticket"},
    "daily_stake_usd": {"type": "number", "min": 1, "max": 5000, "default": 5,
                        "label": "$ for the daily ticket",
                        "group": "Daily ticket"},
    "daily_max_legs": {"type": "integer", "min": 2, "max": 24, "default": 24,
                       "label": "Max legs", "group": "Daily ticket"},
    "daily_min_c": {"type": "integer", "min": 5, "max": 98, "default": 60,
                    "label": "Minimum leg price (c)",
                    "group": "Daily ticket"},
    "daily_min_legs": {"type": "integer", "min": 2, "max": 24, "default": 5,
                       "label": "Minimum legs", "group": "Daily ticket"},
    "daily_escalation_pct": {"type": "number", "min": 0, "max": 100,
                             "default": 50,
                             "label": "Raise stake by up to (%)",
                             "group": "Daily ticket"},
    "slippage_c": {"type": "integer", "min": 0, "max": 25, "default": 5,
                   "label": "Pay up to N cents over fair value",
                   "group": "Parlay"},
    "min_lead": {"type": "integer", "min": 1, "max": 6, "default": 2,
                 "label": "Tennis: games clear in the current set",
                 "group": "Parlay"},
    "tennis_min_pct": {"type": "number", "min": 50, "max": 99, "default": 85,
                       "label": "Tennis: minimum implied (%)",
                       "group": "Parlay"},
    "other_min_pct": {"type": "number", "min": 50, "max": 99, "default": 85,
                      "label": "Other sports: minimum implied (%)",
                      "group": "Parlay"},
    # Soccer sits lower on its own: a soccer side at 82c is genuinely ahead,
    # where the same price in a two-player sport usually means the match is
    # still live in a way the odds have not settled on.
    "soccer_min_pct": {"type": "number", "min": 50, "max": 99, "default": 80,
                       "label": "Soccer: minimum implied (%)",
                       "group": "Parlay"},
    # The ceiling, which a floor cannot substitute for: raising the floor
    # admits MORE near-certainties, not fewer. Above this the outcome is
    # decided and the leg adds cost rather than probability.
    "max_leg_pct": {"type": "number", "min": 51, "max": 99, "default": 98,
                    "label": "Maximum implied per leg (%)",
                    "group": "Parlay"},
    # Blank means DISCOVER one. The engine reads Kalshi's open collections and
    # picks whichever can host the most of this pass's legs -- the broad
    # cross-sport ones carry ~2400 events, the single-game ones carry three.
    # Naming a ticker here pins it instead, which is only useful for testing:
    # a hard-coded collection goes stale the moment Kalshi rotates them.
    "collection": {"type": "string", "default": "",
                   "label": "Kalshi collection (blank = auto-discover)",
                   "group": "Parlay"},
    # How often a pass runs. Ten minutes rather than one: the states this
    # engine trades on -- a set won and two games clear -- last for many
    # minutes, so a faster loop re-reads the same scoreboard and spends a
    # chain sweep per ticker doing it.
    # 72, not 24, and the difference is not a preference -- it is what the
    # feed does. Kalshi sets close_ts well AFTER the event: a college football
    # game played today closes in ~55h, and the earliest close among live legs
    # measured across a full scan was 49.8h. At 24h this admitted nothing at
    # all and the bot sat idle; 72h is the smallest horizon that takes today's
    # and tomorrow's fixtures while still excluding a stage-race market
    # closing three weeks out.
    "max_hours_to_expiry": {"type": "integer", "min": 1, "max": 720,
                            "default": 72,
                            "label": "Drop legs closing later than (hours)",
                            "group": "Parlay"},
    "max_spread_c": {"type": "integer", "min": 1, "max": 50, "default": 3,
                     "label": "Maximum bid/ask spread (cents)",
                     "group": "Parlay"},
    "check_every_min": {"type": "integer", "min": 1, "max": 120, "default": 10,
                        "label": "Check combos every (minutes)",
                        "group": "Parlay"},
    # Empty means EVERY sport that is in play, which is the useful default:
    # the operator should not have to name a sport for the bot to notice a
    # match happening in it. Naming sports narrows the scan.
    "sports": {"type": "json", "default": [],
               "label": "Sports to draw legs from (empty = all live)",
               "group": "Parlay"},
    # v1's own knobs, in the cents and counts that engine reads. Declared so a
    # v1 launch is not refused on its options; v2 ignores them, because its
    # thresholds are the tennis_min_pct / other_min_pct pair above.
    "parley": {"type": "json", "default": {},
               "label": "Engine knobs (v1 only)", "group": "Parlay (v1)"},
}

# The multi-sport bot picks WHICH sports to trade and sizes each one
# separately, so those are real options rather than constants. Structured, and
# declared as such: the desk has always posted them as a list and an object,
# and they were the fields the individual launch form was refused on.
_SPORTS_OPTIONS = {
    **_RISK_OPTIONS,
    "sports": {"type": "json", "default": ["tennis", "baseball"],
               "label": "Sports to trade", "group": "Sports"},
    "sport_settings": {"type": "json", "default": {},
                       "label": "Per-sport contracts and bank",
                       "group": "Sports"},
}

# BTC-15 adds v6's own gates on top of the shared risk options. Real schema
# entries, so the launch form renders them and a version default for one of
# them is not silently dropped.
_BTC15_OPTIONS = {
    **_RISK_OPTIONS,
    "min_price_c": {"type": "integer", "min": 1, "max": 99, "default": 40,
                    "label": "v6: minimum entry price (cents)",
                    "group": "Entry"},
    "max_price_c": {"type": "integer", "min": 1, "max": 99, "default": 70,
                    "label": "v6: maximum entry price (cents)",
                    "group": "Entry"},
    "entry_open_s": {"type": "integer", "min": 0, "max": 900, "default": 60,
                     "label": "v6: window opens (seconds after market open)",
                     "group": "Entry"},
    "entry_close_s": {"type": "integer", "min": 1, "max": 900, "default": 300,
                      "label": "v6: window closes (seconds after market open)",
                      "group": "Entry"},
}

def _bot(key, name, category, cadence, versions, launch_style,
         filename="", options=None, extra=None) -> tuple[BotConfig, object]:
    config = BotConfig(key=key, name=name, category=category, cadence=cadence,
                       versions=versions, launch_style=launch_style,
                       options_schema=options or dict(_RISK_OPTIONS),
                       extra=extra or {})
    adapter = type(f"{key.title()}Adapter", (_CsvLedgerAdapter,),
                   {"config": config, "filename": filename})()
    return config, adapter


BUILTIN = [
    _bot("btc15", "Kalshi BTC 15-minute bot", "btc", "15m",
         (BotVersion("v2", f"{_BTC15}/v2_bot_kalshi_btc15.py", default=True),
          BotVersion("v3", f"{_BTC15}/v3_bot_kalshi_btc15.py"),
          BotVersion("v4", f"{_BTC15}/v4_bot_kalshi_btc15.py"),
          BotVersion("v5", f"{_BTC15}/v5_bot_btc_15_2.py"),
          # v6 takes no view of its own: it trades the quarter-hour only when
          # BTC, ETH and SOL all point the same way on the desk's crypto
          # board -- the same module the CRYPTO panel renders from. Its own
          # take-profit and stop differ from the other engines, which is
          # exactly what option_defaults is for.
          BotVersion("v6", f"{_BTC15}/v6_bot_kalshi_btc15.py",
                     option_defaults={"tp_pct": 20, "sl_pct": 40,
                                      "min_price_c": 40, "max_price_c": 70,
                                      "entry_open_s": 60,
                                      "entry_close_s": 300})),
         "cwd_customer", "v2_trade_history.csv", options=_BTC15_OPTIONS),
    _bot("btc60", "Kalshi BTC 60-minute bot", "btc", "60m",
         (BotVersion("fable5", f"{_BTC60}/bot_kalshi_btc60_fable5.py", default=True),
          BotVersion("burst", f"{_BTC60}/bot_kalshi_btc60_burst.py")),
         "env_customer"),
    _bot("sports", "Kalshi multi-sport bot", "sports", "live-match",
         (BotVersion("main", f"{_SPORTS}/bot_kalshi_main.py", default=True),
          BotVersion("v1", f"{_SPORTS}/bot_kalshi_sports_v1.py"),
          BotVersion("v2", f"{_SPORTS}/bot_kalshi_sports_v2.py")),
         "argv_customer", "trade_history_main.csv",
         options=_SPORTS_OPTIONS),
    _bot("parley", "Kalshi live-sport parlay bot", "sports", "live-match",
         (BotVersion("v1", f"{_SPORTS}/bot_kalshi_parley.py"),
          # v2 raises the bar on both axes: tennis needs 90% AND a real score
          # state (1-0 up and two games clear in set 2, or 2-0 and two clear
          # in set 3), everything else needs 91% on the bid. Legs are
          # deduplicated by EVENT against live exchange positions and
          # partitioned into DISJOINT combos of 2-5, so one outcome can never
          # sit in two parlays at once.
          BotVersion("v2", f"{_SPORTS}/v2_bot_kalshi_parley.py", default=True,
                     option_defaults={"min_legs": 2, "max_legs": 5,
                                      "max_combos": 1, "stake_usd": 5,
                                      "check_every_min": 10})),
         "argv_customer", "paper_parley.csv", options=_PARLEY_OPTIONS),
    # On demand only: the desk previews a ticket and confirms it. There is no
    # script and no process -- launching it would be meaningless -- so it is
    # registered for its NAME, its options and its trade history, and the
    # station drives it through /bots/luck/preview and /bots/luck/place.
    _bot("luck", "Luck bot", "sports", "on-demand",
         (BotVersion("v1", f"{_SPORTS}/v2_bot_kalshi_parley.py", default=True),),
         "argv_customer", "paper_parley.csv", options=_LUCK_OPTIONS),
    _bot("gold15", "Kalshi Gold 15-minute bot", "commodities", "15m",
         (BotVersion("v1", f"{_COMMOD}/gold15/bot_kalshi_gold15.py"),
          BotVersion("v2", f"{_COMMOD}/gold15/v2_bot_kalshi_gold15.py", default=True)),
         # Kalshi publishes no price series to compute an indicator from, so
         # the signal comes from the liquid ETF that tracks the same
         # underlying. Declared here as CONFIG: a fourth commodity bot names
         # its proxy and appears on the board with no code change.
         "cwd_customer",
         # board_order, because the board is read left to right and the
         # registry is sorted by KEY -- which put oil between gold and
         # silver for no reason an operator would recognise. Declared
         # here rather than sorted in the board, so a fourth commodity
         # bot chooses its own slot without touching that code.
         extra={"proxy_symbol": "GLD", "board_order": 1}),
    _bot("silver15", "Kalshi Silver 15-minute bot", "commodities", "15m",
         (BotVersion("v1", f"{_COMMOD}/silver15/bot_kalshi_silver15.py"),
          BotVersion("v2", f"{_COMMOD}/silver15/v2_bot_kalshi_silver15.py", default=True)),
         # Kalshi publishes no price series to compute an indicator from, so
         # the signal comes from the liquid ETF that tracks the same
         # underlying. Declared here as CONFIG: a fourth commodity bot names
         # its proxy and appears on the board with no code change.
         "cwd_customer",
         extra={"proxy_symbol": "SLV", "board_order": 2}),
    _bot("oil15", "Kalshi WTI Oil 15-minute bot", "commodities", "15m",
         (BotVersion("v1", f"{_COMMOD}/oil15/bot_kalshi_oil15.py"),
          BotVersion("v2", f"{_COMMOD}/oil15/v2_bot_kalshi_oil15.py", default=True)),
         # Kalshi publishes no price series to compute an indicator from, so
         # the signal comes from the liquid ETF that tracks the same
         # underlying. Declared here as CONFIG: a fourth commodity bot names
         # its proxy and appears on the board with no code change.
         "cwd_customer",
         extra={"proxy_symbol": "USO", "board_order": 3}),
]


def register_all() -> None:
    """Idempotent: re-registering a bot is a no-op rather than an error, so a
    second create_app() in one process (which is what a test does) does not
    fall over."""
    from app.domains.botstation import registry

    for config, adapter in BUILTIN:
        if config.key not in {c.key for c in registry.all_bots()}:
            register(config, adapter)
