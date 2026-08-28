"""Bot subprocess lifecycle: start, stop, status, logs, kill.

Safety invariants, all learned from real incidents in the source project and
all enforced HERE rather than in each bot:

  1. One running instance per (tenant, bot). A double-launch corrupted a live
     ledger once; a second start is refused with the run that already exists.
  2. HALT_MACHINE_SHUTDOWN is forced off. The vendored bots default to
     powering the machine down on halt.
  3. While the server is paper-only, every known dry-run flag is forced on and
     no live flag is honoured.
  4. The subprocess environment NEVER inherits credentials from this process.
     Each bot loads its own tenant credentials, which is what stops one
     operator keys reaching another operator bot.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.botstation import registry
from app.domains.botstation.models import BotRun
from app.platform.db.base import utcnow

logger = logging.getLogger(__name__)


class BotBusy(RuntimeError):
    """Already running for this tenant."""


class BotNotRunning(RuntimeError):
    pass


@dataclass(frozen=True)
class LaunchPlan:
    argv: list[str]
    cwd: str
    env: dict[str, str]


def running_run(db: Session, tenant_id: str, bot_key: str) -> BotRun | None:
    return db.scalar(select(BotRun).where(
        BotRun.tenant_id == tenant_id,
        BotRun.bot_key == bot_key,
        BotRun.status == "running",
    ))


def _clean_env(customer_dir: Path, log_dir: Path) -> dict[str, str]:
    """A deliberately minimal environment.

    Built from nothing rather than copied from os.environ and then pruned. A
    denylist is only as good as its last update, and the failure mode of
    forgetting an entry is one operator bot signing requests with another
    operator key. An allowlist fails closed instead.
    """
    keep = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "HOME",
            "USERPROFILE", "LANG", "LC_ALL", "TZ", "PYTHONIOENCODING")
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["PYTHONUNBUFFERED"] = "1"
    env["HALT_MACHINE_SHUTDOWN"] = "FALSE"          # invariant 2
    env["BOT_CUSTOMER_DIR"] = str(customer_dir)
    env["BOT_LOG_DIR"] = str(log_dir)
    return env


def _paper_flags(env: dict[str, str], paper_only: bool, mode: str) -> None:
    """Invariant 3.

    Paper-only sets every dry-run flag the vendored bots understand and never
    sets a live one. The bots disagree about which name they read, so all of
    them are set rather than the one we believe is current.
    """
    if paper_only or mode != "live":
        env["DRY_RUN_MODE"] = "TRUE"
        env["BOT152_DRY_RUN"] = "TRUE"
        env["MAIN_PAPER"] = "TRUE"
        env["PERP_BUY"] = "FALSE"
    else:
        env["DRY_RUN_MODE"] = "FALSE"
        env["MAIN_PAPER"] = "FALSE"


def launch_plan(config: registry.BotConfig, version: registry.BotVersion, *,
                tenant_slug: str, options: dict, mode: str,
                paper_only: bool) -> LaunchPlan:
    """Everything the subprocess will be handed, as data.

    Returned rather than executed, so it can be inspected without launching.
    That is what the self-containment check walks to prove no bot is pointed
    outside this project, which is how 158 launches into a sibling checkout
    were found.
    """
    from app.core.config import get_settings

    settings = get_settings()
    script = registry.script_path(config, version)
    customer_dir = settings.customers_root / tenant_slug
    log_dir = settings.var_dir / "logs" / tenant_slug

    env = _clean_env(customer_dir, log_dir)
    _paper_flags(env, paper_only, mode)
    for name, value in options.items():
        env[name.upper()] = (f"{value:g}" if isinstance(value, float)
                             else str(value))

    interpreter = str(settings.bot_python or sys.executable)
    argv = [interpreter, str(script)]
    cwd = str(customer_dir)

    # The three styles are the vendored scripts own conventions, not a design
    # of ours. Declaring which one a bot uses is cheaper than teaching every
    # bot a new one.
    if config.launch_style == "argv_customer":
        argv.append(tenant_slug)
    elif config.launch_style == "env_customer":
        env["BTC_CUSTOMER"] = tenant_slug
        env["BTC_CUSTOMERS_DIR"] = str(settings.customers_root)
        cwd = str(settings.source_repo)

    return LaunchPlan(argv=argv, cwd=cwd, env=env)


def start(db: Session, *, tenant_id: str, tenant_slug: str, bot_key: str,
          version: str | None = None, options: dict | None = None,
          mode: str = "paper", detach: bool = True) -> BotRun:
    from app.core.config import get_settings

    config = registry.get(bot_key)
    spec_version = config.version_or_default(version)

    existing = running_run(db, tenant_id, bot_key)
    if existing is not None:
        raise BotBusy(
            f"{bot_key} is already running for this operator (run "
            f"{existing.id}, started {existing.started_at:%Y-%m-%d %H:%M})")

    # version passed through: a model's own TP/SL defaults beat the bot's
    cleaned = registry.validate_options(config, options or {}, spec_version)
    settings = get_settings()
    if mode == "live" and settings.paper_only:
        raise ValueError(
            "this server is paper-only; a live bot cannot be started here")

    plan = launch_plan(config, spec_version, tenant_slug=tenant_slug,
                       options=cleaned, mode=mode,
                       paper_only=settings.paper_only)

    script = registry.script_path(config, spec_version)
    if not script.is_file():
        raise FileNotFoundError(
            f"{bot_key}/{spec_version.version}: script not found at {script}")

    Path(plan.env["BOT_LOG_DIR"]).mkdir(parents=True, exist_ok=True)
    pid = None
    if detach:
        proc = subprocess.Popen(plan.argv, cwd=plan.cwd, env=plan.env,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        pid = proc.pid

    live = mode == "live" and not settings.paper_only
    run = BotRun(tenant_id=tenant_id, bot_key=bot_key,
                 bot_version=spec_version.version,
                 mode="live" if live else "paper",
                 status="running", pid=pid, started_at=utcnow(),
                 bankroll=cleaned.get("bankroll"),
                 target_pct=cleaned.get("bank_tp_pct"),
                 stop_pct=cleaned.get("bank_sl_pct"),
                 options_json=json.dumps(cleaned, default=str))
    db.add(run)
    db.flush()
    logger.info("bot %s/%s started for %s (pid %s, %s)", bot_key,
                spec_version.version, tenant_slug, pid, run.mode)
    return run


def stop(db: Session, *, tenant_id: str, bot_key: str) -> BotRun:
    run = running_run(db, tenant_id, bot_key)
    if run is None:
        raise BotNotRunning(f"{bot_key} is not running for this operator")
    _terminate(run.pid)
    run.status = "stopped"
    run.stopped_at = utcnow()
    db.flush()
    return run


def kill(db: Session, *, tenant_id: str, bot_key: str) -> dict:
    """The escape hatch when a bot is wedged.

    No screen calls this, and the incident runbook needs it anyway. That is
    why it survived the Phase 4 review of uncalled endpoints instead of being
    deleted as dead.
    """
    runs = list(db.scalars(select(BotRun).where(
        BotRun.tenant_id == tenant_id, BotRun.bot_key == bot_key,
        BotRun.status == "running")).all())
    for run in runs:
        _terminate(run.pid, force=True)
        run.status = "killed"
        run.stopped_at = utcnow()
    db.flush()
    return {"bot_key": bot_key, "killed": [r.id for r in runs]}


def _terminate(pid: int | None, *, force: bool = False) -> None:
    if not pid:
        return
    try:
        import psutil

        proc = psutil.Process(pid)
        if force:
            proc.kill()
        else:
            proc.terminate()
    except Exception as exc:                            # noqa: BLE001
        # A process that is already gone is the outcome we wanted.
        logger.info("terminate %s: %s", pid, exc)


def status(db: Session, *, tenant_id: str, bot_key: str) -> dict:
    config = registry.get(bot_key)
    run = running_run(db, tenant_id, bot_key)
    return {
        "bot_key": bot_key,
        "name": config.name,
        "category": config.category,
        "running": run is not None,
        "run_id": run.id if run else None,
        "version": run.bot_version if run else None,
        "mode": run.mode if run else None,
        "pid": run.pid if run else None,
        "started_at": run.started_at if run else None,
    }


def logs(*, tenant_slug: str, bot_key: str, lines: int = 200) -> dict:
    """Tail this bot log for THIS operator.

    The path is built from the session tenant, never from a parameter. A log
    path assembled from caller input is the classic traversal, and bot logs
    are per-operator files on disk.
    """
    from app.core.config import get_settings

    registry.get(bot_key)          # unknown bot raises rather than tailing ""
    log_dir = get_settings().var_dir / "logs" / tenant_slug
    if not log_dir.is_dir():
        return {"bot_key": bot_key, "file": None, "lines": []}

    candidates = sorted((p for p in log_dir.glob(f"*{bot_key}*.log")),
                        key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return {"bot_key": bot_key, "file": None, "lines": []}

    newest = candidates[0]
    try:
        text = newest.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"bot_key": bot_key, "file": newest.name, "lines": [],
                "error": str(exc)}
    return {"bot_key": bot_key, "file": newest.name,
            "lines": text.splitlines()[-lines:]}


def processes(db: Session, *, tenant_id: str, bot_key: str) -> dict:
    runs = list(db.scalars(select(BotRun).where(
        BotRun.tenant_id == tenant_id, BotRun.bot_key == bot_key,
    ).order_by(BotRun.started_at.desc()).limit(20)).all())
    return {"bot_key": bot_key, "runs": [
        {"run_id": r.id, "status": r.status, "pid": r.pid, "mode": r.mode,
         "version": r.bot_version, "started_at": r.started_at,
         "stopped_at": r.stopped_at}
        for r in runs
    ]}
