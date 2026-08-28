"""Bot subprocess lifecycle: start, stop, status, logs.

Safety invariants enforced here (learned from real incidents in the source
repo — a 2026-07-02 double-launch corrupted a live ledger, and the legacy
bots default to powering the machine off on halt):

1. One running instance per (user, bot_key) — start returns 409 otherwise.
2. ``HALT_MACHINE_SHUTDOWN=FALSE`` is always forced.
3. While ``settings.paper_only`` is True (the default), every known
   paper/dry-run flag is forced on: DRY_RUN_MODE, BOT152_DRY_RUN,
   MAIN_PAPER; PERP_BUY stays off.
4. The subprocess env NEVER inherits KALSHI_* secrets from the API process;
   each bot family loads its own credentials from the user's folder.
"""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

try:  # psutil is local-runtime only (process control); absent in cloud images
    import psutil
except ImportError:  # pragma: no cover - exercised by the cloud image
    psutil = None
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import paths
from app.core.config import get_settings
from app.models import BotRun, User
from app.services import credentials as creds_svc
from app.services.bot_registry import BotSpec, BotVersion, get_bot, script_path

logger = logging.getLogger(__name__)

_LAUNCHER = Path(__file__).with_name("bot_launcher.py")

# Live process handles for runs started by THIS api process (run_id -> Popen).
_PROCESSES: dict[int, subprocess.Popen] = {}

# Serializes the check-then-launch section of start_bot: sync endpoints run
# concurrently in the threadpool, so without this two simultaneous start
# requests could both pass the single-instance check (TOCTOU).
_START_LOCK = threading.Lock()


class BotManagerError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _base_env(mode: str = "paper") -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("KALSHI")}
    env.update(
        {
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            # Never allow a bot halt to power off the host.
            "HALT_MACHINE_SHUTDOWN": "FALSE",
            "PERP_BUY": "FALSE",
            # Account-wide profit target OFF for every bot (user 07/30).
            # The account is shared, so scoring one bot against its joint
            # value is meaningless; targets are per-bot, on that bot's own
            # bankroll. _sports_env re-sets this only when sports asks.
            "TARGET_PORTFOLIO_PCT": "0",
        }
    )
    if mode == "live":
        # Only reachable when the server is unlocked (checked in start_bot).
        # The legacy bots default to paper, so live must be explicit.
        env.update(
            {
                "DRY_RUN_MODE": "FALSE",
                "BOT152_DRY_RUN": "FALSE",
                "MAIN_PAPER": "FALSE",
                "PARLEY_PAPER": "FALSE",
                "BOTGOLD_DRY_RUN": "FALSE",
                "BOTSILVER_DRY_RUN": "FALSE",
            }
        )
    else:
        env.update(
            {
                "DRY_RUN_MODE": "TRUE",   # btc15 v2-v4, btc60, sports secrets
                "BOT152_DRY_RUN": "TRUE",  # btc15 v5
                "MAIN_PAPER": "TRUE",      # sports main bot
                "PARLEY_PAPER": "TRUE",    # parlay bot
                "BOTGOLD_DRY_RUN": "TRUE",   # gold15
                "BOTSILVER_DRY_RUN": "TRUE",  # silver15
                # A paper parlay must not write to the exchange either. The
                # bot's own default CREATES the combined market so paper can
                # price against a real book — but creation is a POST, and
                # Kalshi caps creations at 5000/week. A freshly created combo
                # has an empty book anyway (nothing quotes it), so paper
                # prices the combo theoretically instead and touches nothing.
                "PARLEY_PAPER_CREATE_MARKET": "FALSE",
            }
        )
    return env


KNOWN_SPORTS = ("tennis", "baseball")


def _sports_env(env: dict[str, str], options: "BotStartOptions") -> None:
    """Map per-sport options onto the main sports bot's env knobs."""
    if options.sports:
        bad = [s for s in options.sports if s not in KNOWN_SPORTS]
        if bad:
            raise BotManagerError(
                f"Unknown sport(s) {bad}; full-model sports are {list(KNOWN_SPORTS)}", 422
            )
        joined = ",".join(options.sports)
        env["MAIN_SPORTS_LIST"] = joined
        env["SPORTS_LIST"] = joined  # legacy v1/v2 bots read this name
    if options.contracts:
        # blanket size for every selected sport (sport_settings still wins)
        env["SPORT_CONTRACTS"] = str(options.contracts)
        for sport in (options.sports or KNOWN_SPORTS):
            env[f"{sport.upper()}_CONTRACTS"] = str(options.contracts)
    for sport, cfg in (options.sport_settings or {}).items():
        if sport not in KNOWN_SPORTS:
            raise BotManagerError(
                f"Unknown sport '{sport}' in sport_settings; use {list(KNOWN_SPORTS)}", 422
            )
        prefix = sport.upper()
        if cfg.contracts is not None:
            env[f"{prefix}_CONTRACTS"] = str(cfg.contracts)
        if cfg.bank is not None:
            env[f"{prefix}_BANK"] = f"{cfg.bank:g}"
        if cfg.model:
            # the vendored tennis adapter picks its predict_* module from this
            env[f"{prefix}_MODEL"] = cfg.model
    if options.bank_sl_pct is not None:
        # per-sport bank drawdown halt — the engine's own SportBook machinery
        # (<SPORT>_STOP_LOSS_PCT): realized loss >= bank * pct/100 halts that
        # sport's NEW buys while its open positions keep being managed. Per
        # sport rather than whole-bot on purpose: one sport's drawdown must
        # not stop the other sports mid-session.
        for sport in (options.sports or KNOWN_SPORTS):
            env[f"{sport.upper()}_STOP_LOSS_PCT"] = f"{options.bank_sl_pct:g}"
    if options.target_pct is not None:
        env["TARGET_PORTFOLIO_PCT"] = f"{options.target_pct:g}"


# The parlay bot only knows how to qualify a tennis leg — set/lead state is
# sport-specific and it ships one qualifier (_QUALIFIERS in the script). Any
# other sport would be discovered and then silently skipped every scan, so the
# choice is refused at launch rather than left to look like it took effect.
PARLEY_SPORTS = ("tennis",)


def _parley_env(env: dict[str, str], options: "BotStartOptions") -> None:
    """Map launch options onto the parlay bot's PARLEY_* knobs.

    Its risk keys go through the same SportConfig/SportBook the per-sport
    banks use, so bank/contracts/bank-stop mean exactly what they mean on the
    sports desk. Selection and execution are its own.
    """
    if options.sports:
        bad = [s for s in options.sports if s not in PARLEY_SPORTS]
        if bad:
            raise BotManagerError(
                f"Parlay legs are only qualified for {list(PARLEY_SPORTS)}; "
                f"got {bad}. Set/lead state is sport-specific — the bot ships "
                "one qualifier.",
                422,
            )
        env["PARLEY_SPORTS_LIST"] = ",".join(options.sports)
    if options.contracts:
        env["PARLEY_CONTRACTS"] = str(options.contracts)
    if options.bank is not None:
        env["PARLEY_BANK"] = f"{options.bank:g}"
    if options.bank_sl_pct is not None:
        # SportBook's own halt: realized session loss >= this % of the bank
        # stops NEW parlays while the open one stays managed.
        env["PARLEY_STOP_LOSS_PCT"] = f"{options.bank_sl_pct:g}"

    p = options.parley or {}
    # cents and counts, straight through — no percent translation. This bot
    # prices in cents (a 97c ceiling, a stop 20c under entry), and rendering
    # that as a percentage would be a knob that reads differently than it acts.
    mapping = {
        "min_prob_c": "PARLEY_MIN_PROB_C",
        "min_set": "PARLEY_MIN_SET",
        "lead_scope": "PARLEY_LEAD_SCOPE",
        "min_legs": "PARLEY_MIN_LEGS",
        "max_legs": "PARLEY_MAX_LEGS",
        "max_open": "PARLEY_MAX_OPEN",
        "slippage_c": "PARLEY_SLIPPAGE_C",
        "max_price_c": "PARLEY_MAX_PRICE_C",
        "tp_ceiling_c": "PARLEY_TP_CEILING_C",
        "stop_loss_c": "PARLEY_STOP_LOSS_C",
    }
    for field, key in mapping.items():
        value = p.get(field)
        if value is not None:
            env[key] = f"{value:g}" if isinstance(value, float) else str(value)
    if p.get("cooldown_min") is not None:
        env["PARLEY_COOLDOWN_S"] = str(int(round(float(p["cooldown_min"]) * 60)))
    if p.get("limit_fallback") is not None:
        # empty book + TRUE = rest a maker buy at the theoretical price
        env["PARLEY_LIMIT_FALLBACK"] = "TRUE" if p["limit_fallback"] else "FALSE"


def _bankroll_env(env: dict[str, str], options: "BotStartOptions") -> None:
    """Per-bot bankroll and a profit target measured ON THAT BANKROLL.

    Replaces the account-wide halts (user 07/30). The Kalshi account is shared
    across the sports, BTC and perp bots, so a floor or target on its joint
    portfolio value let one bot's drawdown stop the others. Each bot now gets
    its own capital and its own finish line:

        btc60  BTC_BANKROLL reseeds its ledger, BTC60_TARGET_PCT halts new
               entries once realized P&L has grown that ledger by the percent.

    Left deliberately unset when the caller passes nothing, so each engine
    keeps its own default.
    """
    if options.bank is not None:
        env["BTC_BANKROLL"] = f"{options.bank:g}"
    if options.target_pct is not None:
        # every BTC engine reads its family's name; each launch is its own
        # process, so the two never collide
        env["BTC15_TARGET_PCT"] = f"{options.target_pct:g}"
        env["BTC60_TARGET_PCT"] = f"{options.target_pct:g}"
        env["GOLD15_TARGET_PCT"] = f"{options.target_pct:g}"
        env["SILVER15_TARGET_PCT"] = f"{options.target_pct:g}"
    if options.bank_sl_pct is not None:
        # the capital-protection mirror of the target (user 08/03)
        env["BTC15_BANK_SL_PCT"] = f"{options.bank_sl_pct:g}"
        env["BTC60_BANK_SL_PCT"] = f"{options.bank_sl_pct:g}"
        env["GOLD15_BANK_SL_PCT"] = f"{options.bank_sl_pct:g}"
        env["SILVER15_BANK_SL_PCT"] = f"{options.bank_sl_pct:g}"
    if options.no_trade_times is not None:
        # quiet hours; an explicit empty string DISABLES the engines' default
        # windows, so None (not sent) and "" (cleared) mean different things
        env["NO_TRADE_TIMES"] = options.no_trade_times


# Knobs worth showing on the desk while a bot runs. Credentials and paths are
# deliberately absent — this is rendered in the browser.
_SHOWN_ENV = (
    "KALSHI_PROFIT_PCT", "BOT152_TP_PCT", "BTC60_TP_PCT",
    "KALSHI_STOP_PCT", "BTC60_SL_PCT",
    "DO_YOU_HAVE_STOP_SELL", "MONITOR_SL_TRIGGER",
    "KALSHI_CONTRACTS", "MAX_TRADES_PER_MARKET",
    "BTC_BANKROLL", "BTC15_TARGET_PCT", "BTC60_TARGET_PCT",
    "BTC15_BANK_SL_PCT", "BTC60_BANK_SL_PCT", "NO_TRADE_TIMES",
    "TARGET_PORTFOLIO_PCT", "DO_NOT_BUY_IF_PORTFOLIO_BELOW",
    "HALT_MACHINE_SHUTDOWN", "PAPER_TRADING",
    "PARLEY_SPORTS_LIST", "PARLEY_MIN_PROB_C", "PARLEY_MIN_SET",
    "PARLEY_LEAD_SCOPE", "PARLEY_MIN_LEGS", "PARLEY_MAX_LEGS",
    "PARLEY_MAX_OPEN", "PARLEY_COOLDOWN_S", "PARLEY_BANK",
    "PARLEY_CONTRACTS", "PARLEY_STOP_LOSS_PCT", "PARLEY_TP_CEILING_C",
    "PARLEY_STOP_LOSS_C", "PARLEY_SLIPPAGE_C", "PARLEY_MAX_PRICE_C",
    "PARLEY_LIMIT_FALLBACK", "PARLEY_PAPER",
    "BOTGOLD_DRY_RUN", "BOTGOLD_CONTRACTS", "BOTGOLD_SERIES",
    "BOTGOLD_MIN_CENTS", "BOTGOLD_MAX_CENTS", "BOTGOLD_TP_CENTS",
    "BOTSILVER_DRY_RUN", "BOTSILVER_CONTRACTS", "BOTSILVER_SERIES",
    "BOTSILVER_MIN_CENTS", "BOTSILVER_MAX_CENTS", "BOTSILVER_TP_CENTS",
)

# btc15 v5 has no stop-loss at all — "anything unsold rides to settlement".
# Same for every gold15/silver15/oil15 engine (v1's Yahoo score and v2's DMI
# engine both only ever place a take-profit sell, never a stop).
_NO_STOP_LOSS = {
    ("btc15", "v5"),
    ("gold15", "v1"), ("gold15", "v2"),
    ("silver15", "v1"), ("silver15", "v2"),
    ("oil15", "v1"), ("oil15", "v2"),
}


def _portfolio_at_start(user: User) -> dict | None:
    """Account value the moment this run began, or None if unreadable.

    Best-effort by construction: a Kalshi hiccup must never stop a bot from
    launching, so every failure here is swallowed and the run simply carries
    no baseline.

    Account-WIDE, and the account is shared with the other bots. So the delta
    against it is "what the account did while this bot ran", not "what this
    bot earned" — anything reading it has to say so, or it becomes a P&L
    figure that quietly credits one bot with another's trades.
    """
    try:
        from app.services import credentials, kalshi_client

        creds = credentials.load_kalshi_credentials(user.user_root_folder)
        client = kalshi_client.KalshiClient(
            creds.api_key_id, creds.private_key_path, creds.base_uri
        )
        try:
            pv = client.portfolio()
        finally:
            client.close()
        pv["at"] = datetime.now(timezone.utc).isoformat()
        return pv
    except Exception as exc:  # noqa: BLE001 - a baseline is a nicety, not a gate
        logger.info("no portfolio baseline for this run: %s", exc)
        return None


def _trade_target_env(env: dict[str, str], options: "BotStartOptions") -> None:
    """PER-TRADE profit target, % over entry — for EVERY bot family.

    Deliberately outside _sports_env: that one only runs for the sports bot,
    so anything set there never reaches a BTC launch.

    The BTC engines each express take-profit differently, so set all three
    knobs and let the one the chosen engine reads win — the names do not
    collide, and an engine that ignores its knob is unaffected:
        btc15 v2/v3/v4 : KALSHI_PROFIT_PCT  (already env-driven)
        btc15 v5       : BOT152_TP_PCT      (else a flat 90c sell)
        btc60 both     : BTC60_TP_PCT       (fable5 also pins its learner)
    """
    if options.tp_pct is not None:
        pct = f"{options.tp_pct:g}"
        env["KALSHI_PROFIT_PCT"] = pct
        env["BOT152_TP_PCT"] = pct
        env["BTC60_TP_PCT"] = pct

    # PER-TRADE stop loss, % below entry. Same shape as the target above:
    #     btc15 v2/v3/v4 : KALSHI_STOP_PCT (shared _tp_sl, already env-driven)
    #     btc60 both     : BTC60_SL_PCT    (burst percent-instead-of-15c,
    #                                       fable5 pins its learner)
    # btc15 v5 is deliberately absent — it HAS no stop loss ("anything unsold
    # rides to settlement"), so there is no knob to set and inventing one
    # would be a UI that lies. start_bot() rejects the combination instead.
    if options.sl_pct is not None:
        pct = f"{options.sl_pct:g}"
        env["KALSHI_STOP_PCT"] = pct
        env["BTC60_SL_PCT"] = pct
        # v2/v3/v4 only run the stop monitor when both switches are on, and a
        # user who typed a stop means to have one.
        env["DO_YOU_HAVE_STOP_SELL"] = "TRUE"
        env["MONITOR_SL_TRIGGER"] = "TRUE"


class BotStartOptions:
    """Normalized start options passed through from the request schema."""

    def __init__(
        self, mode: str = "paper", sports=None, sport_settings=None, target_pct=None,
        contracts=None, kill_existing: bool = False, tp_pct=None, sl_pct=None,
        bank=None, bank_sl_pct=None, no_trade_times=None, parley=None,
    ):
        self.mode = mode
        self.sports = sports
        self.sport_settings = sport_settings
        self.parley = parley or {}
        self.target_pct = target_pct
        self.tp_pct = tp_pct
        self.sl_pct = sl_pct
        self.bank_sl_pct = bank_sl_pct
        self.no_trade_times = no_trade_times
        self.bank = bank
        self.contracts = contracts
        self.kill_existing = kill_existing


def _launch_plan(
    spec: BotSpec, version: BotVersion, user: User, options: BotStartOptions
) -> tuple[list[str], Path, dict[str, str]]:
    """Build (argv, cwd, env) for a bot start honoring each family's contract."""
    settings = get_settings()
    script = script_path(spec, version)
    if not script.is_file():
        raise BotManagerError(f"Bot script missing on disk: {script}", 503)

    user_root = paths.normalize_root(user.user_root_folder)
    if not user_root.is_dir():
        raise BotManagerError(f"User root folder does not exist: {user_root}", 409)

    python = str(settings.bot_python or Path(sys.executable))
    argv = [python, str(_LAUNCHER), str(script)]
    env = _base_env(options.mode)

    trade_dir = user_root / "trade_history"
    log_dir = user_root / "logs"
    trade_dir.mkdir(exist_ok=True)
    log_dir.mkdir(exist_ok=True)

    # Portfolio-floor halt is OFF for every mode (user 07/30). The btc15
    # family defaults to halting whenever the SHARED account's portfolio value
    # drops under $100 — but the account is shared with the sports and perp
    # bots, so one bot's drawdown silently stopped the others, and a small
    # balance stopped everything. Risk is now expressed per bot as a bankroll
    # plus a target on that bankroll, not as a floor on the joint account.
    # NOT setdefault: an inherited value from the operator's shell must not
    # quietly re-arm the halt.
    env["DO_NOT_BUY_IF_PORTFOLIO_BELOW"] = "0"

    if spec.launch_style == "cwd_customer":
        # btc15 family: CWD supplies .env + PEM.  Redirect its outputs into
        # the user's folder so multi-user runs never collide on shared files.
        cwd = user_root
        env.setdefault("BOT_CSV_PATH", str(trade_dir / f"{version.version}_trade_history.csv"))
        env.setdefault("BOT_LOG_DIR", str(log_dir))
        env.setdefault("BOT152_CSV_PATH", str(trade_dir / "bot_btc_15_2_trades.csv"))
        if spec.key == "gold15":
            env.setdefault("BOTGOLD_CSV_PATH", str(trade_dir / f"{version.version}_bot_gold15_trades.csv"))
            env.setdefault("BOTGOLD_LOG_PATH", str(log_dir / f"{version.version}_gold-15.log"))
            if options.contracts:
                env["BOTGOLD_CONTRACTS"] = str(options.contracts)
        elif spec.key == "silver15":
            env.setdefault("BOTSILVER_CSV_PATH", str(trade_dir / f"{version.version}_bot_silver15_trades.csv"))
            env.setdefault("BOTSILVER_LOG_PATH", str(log_dir / f"{version.version}_silver-15.log"))
            if options.contracts:
                env["BOTSILVER_CONTRACTS"] = str(options.contracts)
        elif spec.key == "oil15":
            env.setdefault("BOTOIL_CSV_PATH", str(trade_dir / f"{version.version}_bot_oil15_trades.csv"))
            env.setdefault("BOTOIL_LOG_PATH", str(log_dir / f"{version.version}_oil-15.log"))
            if options.contracts:
                env["BOTOIL_CONTRACTS"] = str(options.contracts)
        if options.contracts:
            # common bot contract: contracts is a FIXED size everywhere —
            # every %-of-PV sizing path was removed from the engines (08/03),
            # so there is no CONTRACTS_PV_PCT to zero out any more
            env["KALSHI_CONTRACTS"] = str(options.contracts)
            env["BOT152_CONTRACTS"] = str(options.contracts)
    elif spec.launch_style == "env_customer":
        # btc60 family: resolves paths from __file__, customer via env.
        cwd = script.parent
        env["BTC_CUSTOMERS_DIR"] = str(user_root.parent)
        env["BTC_CUSTOMER"] = user_root.name
        if options.contracts:
            env["KALSHI_CONTRACTS"] = str(options.contracts)
    elif spec.launch_style == "argv_customer":
        # sports family: customer name as argv[1] + SPORTS_* env pins.
        cwd = script.parent
        argv.append(user_root.name)
        env["SPORTS_CUSTOMERS_DIR"] = str(user_root.parent)
        env["SPORTS_CUSTOMER"] = user_root.name
        env_file = user_root / ".env"
        if env_file.is_file():
            env["KALSHI_SPORTS_SECRETS"] = str(env_file)
        env.setdefault("SPORT_LOG_DIR", str(log_dir))
        # Pin per-bot CSV outputs into the user's folder (matched by ingest).
        env.setdefault("MAIN_TRADE_CSV", str(trade_dir / "trade_history_main.csv"))
        env.setdefault("MAIN_PAPER_CSV", str(trade_dir / "paper_trades_main.csv"))
        env.setdefault("BASEBALL_TRADE_CSV", str(trade_dir / "trade_history_baseball.csv"))
        if spec.key == "parley":
            # The parlay bot imports the sports engine, so it wants the pins
            # above — but its own knobs are PARLEY_*, and _sports_env's
            # MAIN_SPORTS_LIST/<SPORT>_* would land on the engine's config
            # instead of on it.
            #
            # Its CSV and combination ledger are named for the mode it runs
            # in, and mode is decided here, so both are pinned here too —
            # a paper run must never write over the live ledger.
            paper = options.mode != "live"
            env.setdefault(
                "PARLEY_TRADE_CSV",
                str(trade_dir / ("paper_parley.csv" if paper else "trade_history_parley.csv")),
            )
            env.setdefault(
                "PARLEY_LEDGER",
                str(trade_dir / ("parley_ledger_paper.json" if paper else "parley_ledger.json")),
            )
            _parley_env(env, options)
        else:
            _sports_env(env, options)
    else:  # pragma: no cover - registry misconfiguration
        raise BotManagerError(f"Unknown launch style {spec.launch_style}", 500)
    # family-independent options go last so no launch style can skip them
    _trade_target_env(env, options)
    _bankroll_env(env, options)
    return argv, cwd, env


def _pid_alive(run: BotRun) -> bool:
    proc = _run_process(run)
    if proc is None:
        return False
    try:
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        # Inconclusive — report alive rather than allow a double start.
        return True


def reconcile_runs(db: Session, *, bot_key: str | None = None, user_id: str | None = None) -> list[BotRun]:
    """Sync DB rows with real process state; returns matching runs, newest first."""
    stmt = select(BotRun).order_by(BotRun.started_at.desc())
    if bot_key:
        stmt = stmt.where(BotRun.bot_key == bot_key)
    if user_id:
        stmt = stmt.where(BotRun.user_id == user_id)
    runs = list(db.scalars(stmt).all())
    dirty = False
    for run in runs:
        if run.status != "running":
            continue
        proc = _PROCESSES.get(run.id)
        if proc is not None:
            code = proc.poll()
            if code is not None:
                run.status = "exited" if code == 0 else "failed"
                run.exit_code = code
                run.stopped_at = _utcnow()
                _PROCESSES.pop(run.id, None)
                dirty = True
        elif not _pid_alive(run):
            run.status = "exited"
            run.stopped_at = _utcnow()
            dirty = True
    if dirty:
        db.commit()
    return runs


def running_run(db: Session, bot_key: str, user_id: str) -> BotRun | None:
    runs = reconcile_runs(db, bot_key=bot_key, user_id=user_id)
    for run in runs:
        if run.status == "running":
            return run
    return None


def _check_paper_conflict(user: User) -> None:
    """The bots load the customer .env with override=True, so a stray
    DRY_RUN_MODE=FALSE in the user's folder would silently re-enable live
    trading underneath a requested PAPER run.  Refuse to start instead."""
    try:
        creds = creds_svc.load_kalshi_credentials(user.user_root_folder)
    except creds_svc.CredentialsError:
        return  # no .env at all -> nothing can override our paper flags
    from dotenv import dotenv_values

    values = {k: (v or "") for k, v in dotenv_values(creds.env_file).items()}
    for key in ("DRY_RUN_MODE", "BOT152_DRY_RUN", "MAIN_PAPER", "PARLEY_PAPER",
                "BOTGOLD_DRY_RUN", "BOTSILVER_DRY_RUN"):
        raw = values.get(key, "").strip().upper()
        if raw in ("FALSE", "0", "NO"):
            raise BotManagerError(
                f"{creds.env_file.name} sets {key}={raw}, which would override "
                "this server's paper-only mode inside the bot process. Remove "
                "the line or set it to TRUE before starting.",
                409,
            )


def start_bot(
    db: Session,
    user: User,
    bot_key: str,
    *,
    version: str | None = None,
    mode: str = "paper",
    options: BotStartOptions | None = None,
) -> BotRun:
    spec = get_bot(bot_key)
    ver = spec.version_or_default(version)
    options = options or BotStartOptions(mode=mode)
    options.mode = mode

    # Refuse rather than silently drop it: accepting a stop for an engine that
    # has none would leave the desk showing "SL 30%" over a bot that rides
    # every loser to settlement.
    if options.sl_pct is not None and (bot_key, ver.version) in _NO_STOP_LOSS:
        raise BotManagerError(
            f"{bot_key} {ver.version} has no stop loss — it holds to settlement by "
            "design. Start it without a stop, or pick another version.",
            400,
        )

    if options.kill_existing:
        # explicit "take over": clear anything already running this bot,
        # including processes the API never started
        kill_bot_processes(db, bot_key)

    if mode == "live":
        if get_settings().paper_only:
            raise BotManagerError(
                "Live trading is locked: this server runs with TBOT_PAPER_ONLY=true. "
                "Set TBOT_PAPER_ONLY=false and restart the API to enable live mode.",
                403,
            )
    else:
        # Paper runs must stay paper even if the customer .env says otherwise.
        _check_paper_conflict(user)

    with _START_LOCK:
        existing = running_run(db, bot_key, user.user_id)
        if existing is not None:
            raise BotManagerError(
                f"Bot {bot_key} already running for user {user.username} (run {existing.id}). "
                "Stop it, or start with kill_existing=true to take over.",
                409,
            )

        # A copy the API never started (orphan from a previous instance, the
        # legacy scheduler, or a manual launch) is invisible to the DB check
        # above. Two bots on one Kalshi account corrupted a live ledger once,
        # so refuse rather than silently double-run.
        stray = [p for p in find_bot_processes(bot_key) if p["pid"] not in _tracked_pids(db, bot_key)]
        if stray:
            listed = ", ".join(f"pid {p['pid']} ({p['script']})" for p in stray[:4])
            raise BotManagerError(
                f"{len(stray)} {bot_key} process(es) already running outside this API: "
                f"{listed}. Start with kill_existing=true to take over, or stop them first.",
                409,
            )

        argv, cwd, env = _launch_plan(spec, ver, user, options)

        settings = get_settings()
        ts = _utcnow().strftime("%Y%m%d_%H%M%S")
        safe_user = re.sub(r"[^A-Za-z0-9_-]", "_", user.username)[:64]
        log_file = settings.log_dir / f"{bot_key}_{ver.version}_{safe_user}_{ts}.log"

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

        log_handle = open(log_file, "a", encoding="utf-8", errors="replace")
        try:
            proc = subprocess.Popen(
                argv,
                cwd=str(cwd),
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except OSError as exc:
            raise BotManagerError(f"Failed to launch bot process: {exc}", 500) from exc
        finally:
            log_handle.close()  # child holds its own handle

        # Fail fast on immediate crashes (bad .env, lock conflict, import
        # error) instead of reporting a phantom "running" row.
        time.sleep(1.0)
        code = proc.poll()
        if code is not None and code != 0:
            tail = ""
            try:
                tail = "\n".join(
                    log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]
                )
            except OSError:
                pass
            raise BotManagerError(
                f"Bot process exited immediately with code {code}. Last log lines:\n{tail}", 502
            )

        extra: dict = {"argv": argv[2:], "cwd": str(cwd)}
        if options.sports:
            extra["sports"] = options.sports
        if options.sport_settings:
            extra["sport_settings"] = {
                k: {"contracts": v.contracts, "bank": v.bank, "model": v.model}
                for k, v in options.sport_settings.items()
            }
        if options.target_pct is not None:
            extra["target_pct"] = options.target_pct
        if options.tp_pct is not None:
            extra["tp_pct"] = options.tp_pct
        if options.sl_pct is not None:
            extra["sl_pct"] = options.sl_pct
        if options.bank is not None:
            extra["bank"] = options.bank
        if options.parley:
            extra["parley"] = options.parley
        # What the process ACTUALLY got, for the desk to show while it runs.
        # Built from the resolved env rather than the request, so a knob this
        # engine never received cannot appear as though it were in force.
        extra["config"] = {
            "mode": mode,
            "version": ver.version,
            "tp_pct": options.tp_pct,
            "sl_pct": options.sl_pct,
            "bank": options.bank,
            "bank_sl_pct": options.bank_sl_pct,
            "no_trade_times": options.no_trade_times,
            "contracts": options.contracts,
            "target_pct": options.target_pct,
            "env": {k: env[k] for k in _SHOWN_ENV if k in env},
            # Account baseline, so the desk can show "PV then -> PV now".
            # Read AFTER the process is confirmed alive: a start that failed
            # should not leave a baseline implying a session that never ran.
            "pv_at_start": _portfolio_at_start(user),
        }
        run = BotRun(
            user_id=user.user_id,
            bot_key=bot_key,
            bot_version=ver.version,
            script_path=str(script_path(spec, ver)),
            pid=proc.pid,
            mode=mode,
            status="running",
            log_file=str(log_file),
            extra=extra,
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        _PROCESSES[run.id] = proc
    logger.info("Started %s %s for %s (pid %s)", bot_key, ver.version, user.username, proc.pid)
    return run


def _tracked_pids(db: Session, bot_key: str) -> set[int]:
    """pids of runs this API considers alive for the bot."""
    return {
        r.pid
        for r in reconcile_runs(db, bot_key=bot_key)
        if r.status == "running" and r.pid is not None
    }


def find_bot_processes(bot_key: str) -> list[dict]:
    """Every python process running ANY version of this bot, whether we
    started it or not.

    Catches the dangerous cases the DB cannot see: an orphan left by a
    previous API instance, one launched by the legacy scheduler/bots.py, or
    a copy started by hand. Two of these against one Kalshi account is how
    a live ledger got corrupted before, so the API surfaces them.
    """
    from app.services.procs import iter_python_processes

    spec = get_bot(bot_key)
    names = {Path(v.rel_script).name for v in spec.versions}
    matched: dict[int, tuple] = {}
    for proc, cmdline in iter_python_processes():
        joined = " ".join(cmdline)
        script = next((n for n in names if n in joined), None)
        if script:
            matched[proc.pid] = (proc, joined, script)

    # On Windows the venv launcher re-execs a real interpreter, so the same
    # bot shows up twice (parent + child). Report only the roots — killing a
    # root takes its children with it.
    out: list[dict] = []
    for pid, (proc, joined, script) in matched.items():
        try:
            parent = proc.parent()
            if parent is not None and parent.pid in matched:
                continue
        except psutil.Error:
            pass
        try:
            started = datetime.fromtimestamp(proc.create_time(), tz=timezone.utc)
            age_s = int((datetime.now(timezone.utc) - started).total_seconds())
        except psutil.Error:
            age_s = None
        out.append(
            {
                "pid": proc.pid,
                "script": script,
                "age_seconds": age_s,
                "cmdline": joined[-200:],
            }
        )
    return out


def kill_bot_processes(
    db: Session, bot_key: str, *, pids: list[int] | None = None
) -> dict:
    """Kill every process running this bot (optionally only the given pids),
    including ones the API never started, and reconcile the DB rows."""
    from app.services import procs as procs_mod

    if psutil is None:
        raise BotManagerError("process control is unavailable in this deployment", 503)

    found = find_bot_processes(bot_key)
    targets = [p for p in found if pids is None or p["pid"] in pids]
    if not targets:
        return {"bot_key": bot_key, "killed": [], "found": found}

    victims = []
    for t in targets:
        try:
            proc = psutil.Process(t["pid"])
        except psutil.Error:
            continue
        victims.append(proc)
        try:  # take the children too (workers, spawned helpers)
            victims.extend(proc.children(recursive=True))
        except psutil.Error:
            pass

    killed = procs_mod.terminate(victims)

    # any DB run whose pid we just killed is no longer running
    for run in reconcile_runs(db, bot_key=bot_key):
        if run.status == "running" and run.pid in killed:
            run.status = "stopped"
            run.stopped_at = _utcnow()
            _PROCESSES.pop(run.id, None)
    db.commit()
    logger.info("killed %s process(es) for %s: %s", len(killed), bot_key, killed)
    return {
        "bot_key": bot_key,
        "killed": killed,
        "found": [t for t in targets],
    }


def stop_bot(db: Session, bot_key: str, *, user_id: str | None = None, run_id: int | None = None) -> list[BotRun]:
    """Stop running processes for the bot: graceful break first (so bot
    finally-blocks can cancel resting orders and release lock files), then a
    hard terminate of the whole tree."""
    runs = reconcile_runs(db, bot_key=bot_key, user_id=user_id)
    targets = [r for r in runs if r.status == "running" and (run_id is None or r.id == run_id)]
    if not targets:
        raise BotManagerError(f"No running {bot_key} bot to stop", 404)
    for run in targets:
        _terminate_tree(run)
        run.status = "stopped"
        run.stopped_at = _utcnow()
        extra = dict(run.extra or {})
        watchdogs = _find_watchdogs(bot_key)
        if watchdogs:
            # The btc60 bots have an optional detached PowerShell watchdog
            # that relaunches them ~30s after a kill. Never kill a process we
            # did not start — surface it instead.
            extra["warning"] = (
                f"External watchdog process(es) alive (pids {watchdogs}); they may "
                "relaunch this bot outside API control. Stop the watchdog manually."
            )
        run.extra = extra
        _PROCESSES.pop(run.id, None)
    db.commit()
    return targets


def _find_watchdogs(bot_key: str) -> list[int]:
    if bot_key != "btc60" or psutil is None:
        return []
    # The watchdog is a PowerShell script, so this walk cannot use the
    # python-only fast path; names are cheap, cmdline is read selectively.
    pids = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if not (name.startswith("powershell") or name.startswith("pwsh")):
                continue
            if "watchdog_btc60" in " ".join(proc.cmdline()):
                pids.append(proc.info["pid"])
        except psutil.Error:
            continue
    return pids


def _run_process(run: BotRun):
    """Resolve the run's psutil process, guarding against PID reuse."""
    if run.pid is None or psutil is None:
        return None
    try:
        proc = psutil.Process(run.pid)
    except psutil.Error:
        return None
    try:
        started = run.started_at.replace(tzinfo=timezone.utc)
        if proc.create_time() > started.timestamp() + 60:
            return None  # PID was recycled by an unrelated process
    except psutil.Error:
        pass  # inconclusive: treat as ours (fail-closed against double start)
    return proc


def _terminate_tree(run: BotRun) -> None:
    parent = _run_process(run)
    if parent is None:
        return
    procs = [parent]
    try:
        procs += parent.children(recursive=True)
    except psutil.Error:
        pass
    # Graceful phase: CTRL_BREAK to the process group lets asyncio bots run
    # their finally blocks (cancel orders, release PID locks).
    if os.name == "nt":
        try:
            os.kill(parent.pid, signal.CTRL_BREAK_EVENT)
            parent.wait(timeout=8)
        except (OSError, psutil.Error):
            pass
    survivors = [p for p in procs if p.is_running()]
    for p in survivors:
        try:
            p.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(survivors, timeout=5)
    for p in alive:
        try:
            p.kill()
        except psutil.Error:
            pass


def tail_log(run: BotRun, lines: int = 100) -> list[str]:
    if not run.log_file:
        return []
    path = Path(run.log_file)
    if not path.is_file():
        return []
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return content[-lines:]
