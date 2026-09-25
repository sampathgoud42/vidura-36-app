"""Start the best-pairs bot, or check that it could start.

Every refusal happens here, before the first pass, while someone is looking --
not at 10:40 inside a loop nobody is reading:

  exit 2   the configuration, the operator, their Tradier key, or a live
           request on a paper-only server
  exit 3   another bot_best_pair is already trading this operator
  exit 4   the database is not the desk's, or not migrated to head
"""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import signal
import sys
from pathlib import Path

from bot_best_pair import config

logger = logging.getLogger("bot_best_pair")

EXIT_CONFIG, EXIT_RUNNING, EXIT_DATABASE = 2, 3, 4


def _console_logging() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)-7s %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")
    for noisy in ("urllib3", "requests", "alembic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _file_logging(log_dir: Path, operator: str) -> Path:
    """var/logs/bot_best_pair-<operator>.log, rotated, beside the desk's own logs."""
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"bot_best_pair-{''.join(c for c in operator if c.isalnum() or c in '-_')}.log"
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5,
                                                   encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    logging.getLogger().addHandler(handler)
    return path


def _refuse(code: int, message: str) -> int:
    for line in message.splitlines():
        logger.error(line)
    return code


def _schema_problem() -> str | None:
    from app.platform.db import migrations

    try:
        current, head = migrations.current_revision(), migrations.head_revision()
    except Exception as exc:                            # noqa: BLE001
        return f"cannot read the database: {type(exc).__name__}: {exc}"
    if current != head:
        return (f"the database is at schema {current}, head is {head}. Start the desk once "
                f"(start.bat / ./start.sh) -- it migrates -- then start this bot. It will not "
                f"trade on a schema it does not know.")
    return None


def _operator(cfg: config.BotConfig):
    """The operator's tenant, after proving their Tradier key decrypts. Returns
    (tenant, None) or (None, why not)."""
    from app.api_v2 import deps
    from app.platform.db.session import session_scope
    from app.platform.security.envelope import MasterKeyMissing
    from app.tenancy import repository as tenants

    with session_scope() as db:
        tenant = tenants.by_slug(db, cfg.operator)
        if tenant is None or tenant.status != "active":
            known = sorted(t.slug for t in tenants.list_all(db) if t.status == "active")
            return None, (f"no active operator '{cfg.operator}' in this database; "
                          f"active operators: {', '.join(known) or 'none'}")
        try:
            tenants.load_credential(db, tenant.id, cfg.venue, deps.keyring())
        except MasterKeyMissing:
            return None, ("TBOT_ENCRYPTION_MASTER_KEY is not set in the project .env, so "
                          "the operator's Tradier key cannot be read")
        except tenants.TenantNotFound:
            return None, (f"{cfg.operator} has no {cfg.venue} credential -- add it on the "
                          f"desk, or set BOT_BEST_PAIR_LIVE to the venue they do have")
        except Exception as exc:                        # noqa: BLE001
            # Never relay the exception text: it may carry key material.
            return None, (f"{cfg.operator}'s {cfg.venue} credential could not be decrypted "
                          f"with this master key ({type(exc).__name__})")
        return tenant, None


def _check(bot, cfg: config.BotConfig) -> int:
    """--check: everything short of trading."""
    from app.domains.trading.execution import signal_owner
    from app.domains.trading.risk import clock
    from app.services import super_signals as desk

    from bot_best_pair.bot import describe_pair, parse_pairs

    owner = signal_owner.current(bot.tenant_id)
    logger.info("signal desk  %s", owner.describe() + " holds it" if owner else "free")
    logger.info("desk monitor %s", "running" if bot._desk_monitor_running()
                else f"not running at {cfg.desk_url} -- this bot would sweep stops itself"
                if cfg.own_monitor else f"not running at {cfg.desk_url}")
    try:
        body = desk.get_json("/api/best-pairs", cfg.minimums() or None)
    except desk.Unavailable as exc:
        return _refuse(EXIT_CONFIG, f"the signal desk cannot list the best pairs: {exc.detail}")
    pairs, dropped = parse_pairs(body, cfg)
    logger.info("best pairs   %d of %s meet %s (the %s report)", len(pairs), body.get("total", "?"),
                cfg.describe_minimums(), body.get("session", "?"))
    for p in pairs:
        logger.info("  %s", describe_pair(p))
    for why in dropped:
        logger.warning("  not traded: %s", why)
    logger.info("check done at %s CST -- nothing was traded", clock.now().strftime("%H:%M"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bot_best_pair",
        description="Auto-trade the daily report's best ticker + signal pairs on Tradier.")
    parser.add_argument("--check", action="store_true",
                        help="check the settings, the operator, the database and the signal "
                             "desk, list today's pairs, and exit without trading")
    parser.add_argument("--env-file", type=Path, default=config.ENV_FILE,
                        help=f"settings file (default {config.ENV_FILE.name} beside the bot)")
    args = parser.parse_args(argv)

    # The desk runs from the project root, so a relative path in the project
    # .env must resolve from there for the bot too.
    os.chdir(config.PROJECT_ROOT)
    db_url = config.prepare_platform_env()
    _console_logging()

    try:
        cfg = config.load(file=args.env_file)
    except config.ConfigError as exc:
        return _refuse(EXIT_CONFIG, f"{args.env_file}:\n{exc}")

    from app.core.config import get_settings

    settings = get_settings()
    log_path = _file_logging(settings.log_dir, cfg.operator)
    logger.info("bot_best_pair -- %s", cfg.source)
    for line in cfg.banner():
        logger.info("  %s", line)
    logger.info("  database     %s", db_url)
    logger.info("  signal desk  %s", settings.super_signals_url)
    logger.info("  log          %s", log_path)

    if cfg.live and settings.paper_only:
        return _refuse(EXIT_CONFIG, "BOT_BEST_PAIR_LIVE=true, but this server is paper-only "
                                    "(TBOT_PAPER_ONLY) -- a live bot cannot start")
    problem = _schema_problem()
    if problem:
        return _refuse(EXIT_DATABASE, problem)
    tenant, why = _operator(cfg)
    if tenant is None:
        return _refuse(EXIT_CONFIG, why)

    from app.domains.trading.execution import signal_owner

    from bot_best_pair.bot import NAME, AlreadyRunning, Bot

    bot = Bot(cfg, tenant_id=tenant.id)
    if args.check:
        return _check(bot, cfg)

    def _duplicate(why: str) -> int:
        return _refuse(EXIT_RUNNING, f"{why}. One bot per operator: stop that one first "
                                     f"(if it crashed, its claim expires within "
                                     f"{signal_owner.TTL_S // 60} minutes).")

    # Before the first pass, not during it: a duplicate must not so much as
    # sweep a stop. The pass checks again, for two bots started together.
    owner = signal_owner.current(tenant.id)
    if owner is not None and owner.kind == NAME:
        return _duplicate(f"{owner.describe()} is already trading best pairs for "
                          f"{cfg.operator}")

    def _stop(signum, _frame) -> None:
        logger.info("stopping (signal %s) -- positions already open stay managed", signum)
        bot.stop_flag.set()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _stop)

    logger.info("running as %s -- Ctrl-C stops it", bot.holder)
    try:
        bot.run()
    except AlreadyRunning as exc:
        return _duplicate(str(exc))
    logger.info("stopped")
    return 0
