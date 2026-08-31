from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class BotVersionInfo(BaseModel):
    version: str
    script: str
    exists: bool
    default: bool = False


class BotInfo(BaseModel):
    key: str
    name: str
    category: str  # btc | sports
    cadence: str | None = None
    versions: list[BotVersionInfo]
    running: bool
    active_run_id: int | None = None


class SportSettings(BaseModel):
    """Per-sport tuning for the main sports bot (maps to <SPORT>_* env)."""

    contracts: int | None = Field(default=None, ge=1, le=1000, description="contracts per order")
    bank: float | None = Field(default=None, ge=0, description="session bankroll $ (0 = unlimited)")
    model: str | None = Field(
        default=None,
        pattern="^v[1-6]$",
        description="prediction model version for this sport (tennis: v1-v6). "
        "Omit it to get the default, v5 — the forensics-validated 50-62c "
        "whitelist. Naming any other model also hands it the 68-84c band from "
        "kaslhi_sports.env, which only v5 ignores.",
        examples=["v5"],
    )


class ParleySettings(BaseModel):
    """Parlay-bot tuning (maps to PARLEY_* env).

    Deliberately in cents and counts rather than percentages: this bot prices
    in cents — a 97c take-profit ceiling, a stop 20c under entry — so a
    percent knob would read differently than it acts. Bankroll, contracts and
    the bank stop come from the shared top-level fields, since they go through
    the same SportConfig/SportBook the per-sport banks use.
    """

    min_prob_c: int | None = Field(
        default=None, ge=50, le=99,
        description="a leg needs a YES price strictly ABOVE this (80 = 'odds > 80%')",
        examples=[80],
    )
    min_set: int | None = Field(
        default=None, ge=1, le=5, description="match must be at least in this set",
        examples=[2],
    )
    lead_scope: str | None = Field(
        default=None, pattern="^(current|second|off)$",
        description="which set the above-threshold participant must LEAD: "
                    "current (the set in progress) | second | off (price only)",
        examples=["current"],
    )
    min_legs: int | None = Field(
        default=None, ge=2, le=12,
        description="fewer qualifying legs than this → no parlay (2 is also the "
                    "exchange's own collection minimum)",
    )
    max_legs: int | None = Field(
        default=None, ge=0, le=12, description="0 = take every qualifying live match"
    )
    max_open: int | None = Field(default=None, ge=1, le=10, description="concurrent open parlays")
    cooldown_min: float | None = Field(
        default=None, ge=0, le=1440,
        description="minimum gap between two parlays, minutes (PARLEY_COOLDOWN_S)",
        examples=[15],
    )
    slippage_c: int | None = Field(
        default=None, ge=0, le=20,
        description="cents crossed above the ask. The V2 order API has no market "
                    "order type, so a market order is sent as a marketable "
                    "immediate-or-cancel at ask + this.",
    )
    max_price_c: int | None = Field(
        default=None, ge=2, le=99, description="never pay more than this per combo contract"
    )
    tp_ceiling_c: int | None = Field(
        default=None, ge=2, le=99, description="resting take-profit sell, in cents"
    )
    stop_loss_c: int | None = Field(
        default=None, ge=0, le=99,
        description="entry-relative stop: exit once the bid is this many cents "
                    "under the entry (0 disables)",
    )
    limit_fallback: bool | None = Field(
        default=None,
        description="A freshly created combined market has an EMPTY book, so a "
                    "market order fills nothing and the bot takes no position. "
                    "True instead rests a good-till-cancelled maker buy at the "
                    "theoretical price (the product of the leg probabilities).",
    )


class BotStartRequest(BaseModel):
    user_id: str
    version: str | None = Field(default=None, examples=["v2"])
    # 'paper' is always the default; 'live' additionally requires the server
    # to be unlocked with TBOT_PAPER_ONLY=false (403 otherwise).
    mode: str = Field(default="paper", pattern="^(paper|mock|live)$")
    # --- sports-bot options (ignored by btc bots) ---
    sports: list[str] | None = Field(
        default=None,
        description="active sports for the main bot, e.g. ['tennis','baseball']",
        examples=[["tennis", "baseball"]],
    )
    sport_settings: dict[str, SportSettings] | None = Field(
        default=None,
        description="per-sport contracts/bank, keyed by sport name",
        examples=[{"tennis": {"contracts": 20, "bank": 300}}],
    )
    parley: ParleySettings | None = Field(
        default=None,
        description="parlay-bot selection and execution knobs (ignored by every "
                    "other bot). Its sports list reuses `sports` — but only "
                    "tennis has a leg qualifier, so anything else is refused.",
    )
    target_pct: float | None = Field(
        default=None, ge=0, le=1000,
        description="profit target % on the bankroll/portfolio (TARGET_PORTFOLIO_PCT); bot halts when reached",
    )
    tp_pct: float | None = Field(
        default=None, gt=0, le=500,
        description=(
            "PER-TRADE profit target, % over the entry price — distinct from "
            "target_pct, which is a whole-session halt. Routed to whichever knob "
            "the chosen BTC engine reads: KALSHI_PROFIT_PCT (btc15 v2/v3/v4), "
            "BOT152_TP_PCT (btc15 v5), BTC60_TP_PCT (btc60 fable5/burst). On "
            "btc60 fable5 it also pins the learner so the target cannot drift."
        ),
        examples=[15],
    )
    sl_pct: float | None = Field(
        default=None, gt=0, lt=100,
        description=(
            "PER-TRADE stop loss, % BELOW the entry price. Routed to "
            "KALSHI_STOP_PCT (btc15 v2/v3/v4, which share one _tp_sl) and "
            "BTC60_SL_PCT (btc60 burst uses a percent instead of its fixed 15c "
            "offset; fable5 pins its learner so the stop cannot drift). Setting "
            "it also turns the v2/v3/v4 stop monitor on. Rejected for btc15 v5, "
            "which has no stop loss by design — it holds to settlement. Must be "
            "under 100: a 100% stop is the position going to zero."
        ),
        examples=[30],
    )
    bank_sl_pct: float | None = Field(
        default=None, gt=0, lt=100,
        description=(
            "Bank STOP-LOSS, % below the bank typed at launch — the "
            "capital-protection mirror of target_pct. bank=100, target_pct=50, "
            "bank_sl_pct=20: the bot stops at 150 (TP reached on bank) or at "
            "80 (SL HIT on Bank). Routed to BTC15_BANK_SL_PCT / "
            "BTC60_BANK_SL_PCT."
        ),
        examples=[20],
    )
    no_trade_times: str | None = Field(
        default=None, max_length=200,
        pattern=r"^$|^\s*\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}"
                r"(\s*,\s*\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2})*\s*$",
        description=(
            "Quiet hours in HALT_TIMEZONE local time, comma-separated "
            "HH:MM-HH:MM ranges (end before start wraps midnight). The bot "
            "stays RUNNING — monitors and TP management continue — but enters "
            "no NEW trade inside a window. Engines default to "
            "'17:00-19:30,05:00-08:00'; send an empty string to disable."
        ),
        examples=["17:00-19:30, 05:00-08:00"],
    )
    bank: float | None = Field(
        default=None, gt=0, le=1_000_000,
        description=(
            "Bankroll for THIS bot, in dollars. Risk is per bot, not on the "
            "shared Kalshi account: btc60 reseeds its own ledger from this and "
            "target_pct is then measured on it. Sports uses sport_settings[].bank."
        ),
        examples=[250],
    )
    kill_existing: bool = Field(
        default=False,
        description="kill any process already running this bot — including copies "
        "the API did not start (orphans, legacy scheduler, manual launches) — "
        "then start fresh",
    )
    contracts: int | None = Field(
        default=None, ge=1, le=1000,
        description="fixed contracts per order (BTC bots: KALSHI_CONTRACTS/BOT152_CONTRACTS; "
        "sports: applied to every selected sport unless sport_settings overrides it)",
    )


class BotStopRequest(BaseModel):
    user_id: str | None = None
    run_id: int | None = None


class BotRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    bot_key: str
    bot_version: str | None
    script_path: str | None
    pid: int | None
    mode: str
    status: str
    exit_code: int | None
    log_file: str | None
    extra: dict | None = None
    started_at: datetime
    stopped_at: datetime | None


class BotStatusOut(BaseModel):
    bot_key: str
    running: bool
    runs: list[BotRunOut]
    # Realized bankroll progress of the ACTIVE run: trades it opened and has
    # since closed, as % of the bank typed at launch, vs its target_pct.
    # None when idle or when the run predates config recording.
    session: dict | None = None


class BotLogsOut(BaseModel):
    bot_key: str
    run_id: int | None
    log_file: str | None
    lines: list[str]
