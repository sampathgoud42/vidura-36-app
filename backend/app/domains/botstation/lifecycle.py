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

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.botstation import registry
from app.domains.botstation.models import BotRun
from app.platform.db.base import utcnow

logger = logging.getLogger(__name__)


class BotBusy(RuntimeError):
    """Already running for this tenant."""


class BotNotStopped(RuntimeError):
    """A stop was asked for and the process is still there.

    Deliberately not silent. The alternative -- marking the row stopped
    anyway -- tells the operator their live bot is off while it keeps
    trading.
    """


class BotNotRunning(RuntimeError):
    pass


@dataclass(frozen=True)
class LaunchPlan:
    argv: list[str]
    cwd: str
    env: dict[str, str]


def running_run(db: Session, tenant_id: str, bot_key: str) -> BotRun | None:
    """The run that is ACTUALLY running, reconciling the row if it is not.

    The row records what was asked for; it is not evidence that anything is
    still alive. Nothing writes to it when a bot exits -- a crash, a kill, a
    reboot -- so it says "running" forever afterwards.

    Reconciled HERE rather than in status(), because every caller needs the
    same truth. When only status() checked, a bot that died on launch still
    blocked the next launch as "already running", and the operator had to
    happen to load a status panel before they could restart it. The
    single-instance guard was being enforced on behalf of a process that no
    longer existed.
    """
    run = db.scalar(select(BotRun).where(
        BotRun.tenant_id == tenant_id,
        BotRun.bot_key == bot_key,
        BotRun.status == "running",
    ))
    if run is not None and not process_alive(run.pid):
        run.status = "stopped"
        run.stopped_at = run.stopped_at or utcnow()
        db.commit()
        return None
    return run


def _clean_env(customer_dir: Path, log_dir: Path,
               customers_root: Path | None = None) -> dict[str, str]:
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
    _inject_venue_credentials(env, customer_dir)

    # Where the bots look for the operator's folder. They derive it from their
    # OWN location -- `_HERE.parents[2] / "customers"` -- which resolves to
    # runtime/customers, a directory that does not exist here; the real one is
    # customers/ at the project root. So every sports bot found no .env,
    # started with KALSHI_API_KEY_ID unset, and every venue call came back
    # 401 token_authentication_failure.
    #
    # It printed "auth will fail" at startup and said so plainly. Nobody could
    # see it, because the launcher was sending stdout to DEVNULL.
    #
    # Set rather than patched into the scripts: they already offer these
    # overrides, and an env var is the seam they published for exactly this.
    if customers_root is not None:
        env["SPORTS_CUSTOMERS_DIR"] = str(customers_root)
        env["BTC_CUSTOMERS_DIR"] = str(customers_root)

    # The database, as an ABSOLUTE url. A bot that reads the rebuild's own
    # tables -- parley v2 loads its Kalshi credential from them -- runs with
    # cwd set to the operator's folder, so a relative "sqlite:///./var/..."
    # re-resolves against THAT directory. The allowlist also meant the child
    # inherited no override at all and fell back to the default, which points
    # at the retired app.db.
    #
    # Either way the bot opened a database with no `tenant` table and died on
    # its first query. SQLite makes this worse than it sounds: pointed at a
    # path that does not exist it CREATES an empty file rather than failing,
    # so the error is a missing table rather than a missing database.
    from app.core.config import get_settings

    url = get_settings().database_url
    if url.startswith("sqlite:///") and ":memory:" not in url:
        raw = url[len("sqlite:///"):]
        url = "sqlite:///" + str(Path(raw).resolve())
    env["TBOT_DATABASE_URL_OVERRIDE"] = url

    # And the master key, without which a bot cannot decrypt the credential it
    # just read. Passed only because the rebuild's own bots need it; the
    # vendored ones ignore it.
    master = os.environ.get("TBOT_ENCRYPTION_MASTER_KEY")
    if master:
        env["TBOT_ENCRYPTION_MASTER_KEY"] = master
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


def wants_live(cli_flag: bool = False) -> bool:
    """Is this process meant to trade for real.

    The reader for the flags _paper_flags writes, kept beside the writer so
    the two cannot drift. That drift is exactly what went wrong: the station
    launched a bot with mode="live" and DRY_RUN_MODE=FALSE, the run row said
    live, the launch banner said live -- and the bot itself announced "paper
    (no orders will be sent)" and sent none. It read the flag only to turn
    live OFF, never on, so a station launch could never be live.

    When DRY_RUN_MODE is set it DECIDES, because that is how the station
    speaks to a bot it started. When it is absent -- a hand run from a
    terminal -- the command-line flag decides.
    """
    raw = os.environ.get("DRY_RUN_MODE")
    if raw is None or raw.strip() == "":
        return bool(cli_flag)
    return raw.strip().upper() == "FALSE"


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

    env = _clean_env(customer_dir, log_dir, settings.customers_root)
    _paper_flags(env, paper_only, mode)
    for name, value in options.items():
        if isinstance(value, (dict, list)):
            # JSON, not str(). Python's repr of a dict uses single quotes and
            # True/False, which no JSON parser on the other side accepts --
            # the engine would receive something that looks like data and
            # fails to load.
            env[name.upper()] = json.dumps(value)
        elif isinstance(value, float):
            env[name.upper()] = f"{value:g}"
        else:
            env[name.upper()] = str(value)

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


# The keys a vendored bot reads straight from the environment, and whether the
# value names a file. Anything that names a file is made ABSOLUTE against the
# operator folder before it is handed over -- see _inject_venue_credentials.
_CREDENTIAL_KEYS = {
    "KALSHI_API_KEY_ID": False,
    "KALSHI_PRIVATE_KEY": True,
    "BASE_URI": False,
}


def _inject_venue_credentials(env: dict, customer_dir: Path) -> None:
    """Hand the bot its operator's exchange credential explicitly.

    The vendored bots call `load_dotenv()` with no argument, which searches
    upward from the CURRENT WORKING DIRECTORY. That works when a bot is run by
    hand from inside the operator folder, and not otherwise: launched by the
    station with cwd set to the runtime repo, the search walks right past
    customers/<slug>/.env and finds the project root instead. KALSHI_API_KEY_ID
    then resolves to "" and every signed request comes back 401
    token_authentication_failure -- which is exactly what btc15 did on five
    consecutive passes where the strategy had already said BUY.

    The path is made absolute for the same reason. `KALSHI_PRIVATE_KEY` is
    written as a bare `kalshi_private.pem`, relative to a cwd the operator
    folder no longer is.

    Reading the file here rather than teaching each bot a new convention: the
    environment is the seam they already publish, and an explicit value cannot
    be defeated by where the process happens to be started from. Nothing is
    logged -- these are secrets, and the point of the allowlist above is that
    one operator's key never reaches another operator's bot.
    """
    source = customer_dir / ".env"
    try:
        raw = source.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip().upper()
        if name not in _CREDENTIAL_KEYS:
            continue
        value = value.strip().strip('"').strip("'")
        if not value:
            continue
        if _CREDENTIAL_KEYS[name]:
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = customer_dir / candidate
            if not candidate.is_file():
                logger.warning("%s names %s, which is not there — the bot "
                               "will not be able to sign requests",
                               name, candidate)
                continue
            value = str(candidate)
        env[name] = value


def _spawn_detached(plan, sink, creationflags: int, start_new_session: bool):
    """Start the bot so it outlives whatever launched it.

    On Windows the console flags are only half the job. Every process also
    belongs to the JOB OBJECT of its creator, and a job configured to kill on
    close takes every member down with it -- DETACHED_PROCESS and a new
    process group do not exempt anything, because neither says anything about
    jobs. Terminals, task runners, CI agents and IDE run panes routinely
    create such jobs, so a bot launched from one dies the moment that window
    is closed, with no error in its log and its run row still reading
    "running". CREATE_BREAKAWAY_FROM_JOB is the only flag that leaves.

    A job may forbid breakaway, and then CreateProcess fails outright rather
    than falling back -- so the flag is attempted and dropped if refused. A
    bot that runs inside the job is worth much more than no bot at all; it is
    simply tied to the lifetime of the thing that started it.
    """
    def _go(flags: int):
        return subprocess.Popen(plan.argv, cwd=plan.cwd, env=plan.env,
                                stdout=sink, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, close_fds=True,
                                creationflags=flags,
                                start_new_session=start_new_session)

    if os.name != "nt":
        return _go(creationflags)

    CREATE_BREAKAWAY_FROM_JOB = 0x01000000
    try:
        return _go(creationflags | CREATE_BREAKAWAY_FROM_JOB)
    except OSError as exc:
        logger.info("this job forbids breakaway (%s); the bot will stop when "
                    "the process that launched the desk does", exc)
        return _go(creationflags)


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

    # The bot runs IN its operator's folder, so a missing one is a
    # configuration problem with a name -- not the NotADirectoryError from
    # deep inside subprocess that this used to surface as a bare
    # "could not start <bot>", which says nothing anyone can act on.
    if not Path(plan.cwd).is_dir():
        raise FileNotFoundError(
            f"no folder for operator {tenant_slug!r} at {plan.cwd} — a bot "
            f"runs in its operator's directory, so create it (with that "
            f"operator's credentials) before launching")

    log_dir = Path(plan.env["BOT_LOG_DIR"])
    log_dir.mkdir(parents=True, exist_ok=True)

    # Where a launch failure goes. Both streams used to be sent to DEVNULL, so
    # a bot that died on its very first import -- which every sports bot did,
    # for months -- left no trace anywhere: no file, no line in the API log,
    # and a run row that still said "running". The desk showed a live bot that
    # had been dead since the instant it launched.
    #
    # Appended, not truncated: a bot that crash-loops writes the same first
    # error each time, and overwriting keeps only the last one while hiding
    # that it happened four times.
    launch_log = log_dir / f"{bot_key}_{spec_version.version}_launch.log"

    pid = None
    if detach:
        with open(launch_log, "a", encoding="utf-8", errors="replace") as sink:
            marker = ("live" if mode == "live" else "paper")
            sink.write(
                f"\n=== {utcnow().isoformat()} launching "
                f"{bot_key}/{spec_version.version} for {tenant_slug} "
                f"({marker}) ===\n")
            sink.flush()
            # DETACHED. Without this the bot shares the API's console and
            # process group, so a signal aimed at the server reached it too
            # and restarting the server silently stopped every running bot --
            # including a LIVE one holding positions. This module's docstring
            # says bots "survive API restarts"; the flags that make that true
            # were never passed. The levels watcher next door has had them all
            # along, which is what made the difference visible.
            #
            # What these flags do NOT do is make the bot stop being the API's
            # child in the process table. On Windows nothing can: the parent
            # is recorded at creation. So `taskkill /T` on the API still
            # reaches every bot, and appctl must stop the API without it --
            # see `_terminate` in tools/appctl.py, which is the other half of
            # this guarantee and the half that was missing.
            creationflags = 0
            start_new_session = False
            if os.name == "nt":
                DETACHED_PROCESS = 0x00000008
                creationflags = (DETACHED_PROCESS
                                 | subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                # POSIX equivalent: leave the API's process group so a signal
                # sent to the server does not reach the bot.
                start_new_session = True
            proc = _spawn_detached(plan, sink, creationflags, start_new_session)
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
    outcome = _terminate(run.pid)
    if not outcome.get("stopped"):
        # The row is NOT marked stopped. Saying a bot stopped when its
        # process is still running is the one report that puts an operator at
        # ease about a live bot that is still placing orders.
        raise BotNotStopped(
            f"{bot_key} would not stop: {outcome.get('detail')}. Its process "
            f"is still running -- use kill to force it")
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


# How long a bot gets to shut down cleanly before it is killed outright.
TERMINATE_GRACE_S = 8


def _terminate(pid: int | None, *, force: bool = False) -> dict:
    """End that process AND everything it started, and say whether it worked.

    Three things were wrong here, all on the path that stops a LIVE trading
    bot:

      It signalled only the recorded pid.  The bots spawn children -- the
      sports bot runs scrapers -- and those kept running after the parent
      died. Stopping a live bot left five processes trading.

      It never waited or checked.  terminate() returns immediately, so the
      call reported success without knowing whether anything had exited.

      It caught Exception and called it success.  NoSuchProcess genuinely IS
      the outcome we want; AccessDenied is a failure to stop a bot that is
      placing real orders, and the two were indistinguishable.

    Children are signalled BEFORE the parent: kill a supervisor first and its
    children are reparented, which loses the handle on them.
    """
    if not pid:
        return {"stopped": True, "detail": "no pid recorded"}
    try:
        import psutil
    except ImportError:                                 # pragma: no cover
        return {"stopped": False, "detail": "psutil unavailable"}

    try:
        parent = psutil.Process(int(pid))
    except psutil.NoSuchProcess:
        return {"stopped": True, "detail": "already gone"}
    except psutil.Error as exc:
        return {"stopped": False, "detail": f"{type(exc).__name__}"}

    try:
        family = parent.children(recursive=True) + [parent]
    except psutil.NoSuchProcess:
        return {"stopped": True, "detail": "already gone"}

    for proc in family:
        try:
            proc.kill() if force else proc.terminate()
        except psutil.NoSuchProcess:
            continue
        except psutil.Error as exc:
            logger.warning("stop %s: could not signal %s: %s", pid, proc.pid,
                           type(exc).__name__)

    gone, alive = psutil.wait_procs(family, timeout=TERMINATE_GRACE_S)
    if alive:
        # It was asked and would not go. Escalate rather than report success:
        # a bot that ignores a stop is still placing orders.
        for proc in alive:
            try:
                proc.kill()
            except psutil.Error:
                pass
        gone2, alive = psutil.wait_procs(alive, timeout=TERMINATE_GRACE_S)

    if alive:
        return {"stopped": False,
                "detail": f"{len(alive)} process(es) survived: "
                          f"{[p.pid for p in alive]}"}
    return {"stopped": True, "processes": len(family)}


def process_alive(pid: int | None) -> bool:
    """Is that process actually there.

    The run ROW is a record of what was asked for; it is not evidence that
    anything is still running. A bot that exits -- crash, kill, reboot --
    leaves the row saying "running" forever, because nothing writes to it on
    the way out.
    """
    if not pid:
        return False
    try:
        import psutil

        return psutil.pid_exists(int(pid))
    except Exception:                                   # noqa: BLE001
        # Cannot tell. Claiming it is alive is the more dangerous of the two
        # wrong answers, because it is the one that hides a dead bot.
        return False


def status(db: Session, *, tenant_id: str, bot_key: str) -> dict:
    config = registry.get(bot_key)
    run = running_run(db, tenant_id, bot_key)
    # Checked against the OS, not merely read off the row. Reporting the row
    # meant a bot that died on launch showed as running on the Bot Station,
    # with no way to tell it apart from one that was working.
    # running_run has already reconciled a dead row, so anything it returns is
    # a process that genuinely exists.
    alive = run is not None
    return {
        "bot_key": bot_key,
        "name": config.name,
        "category": config.category,
        "running": alive,
        "run_id": run.id if run else None,
        "version": run.bot_version if run else None,
        "mode": run.mode if run else None,
        "pid": run.pid if run else None,
        "started_at": run.started_at if run else None,
        # The Bot Station reads runs[] and session{}, not these flat fields.
        # It takes the tile's LIVE/PAPER badge from runs[].mode, so a status
        # without them left `run` undefined and every running bot fell through
        # to PAPER -- a live bot displayed as paper, and its start time and
        # session P&L were blank.
        "runs": _recent_runs(db, tenant_id, bot_key),
        "session": _session(db, tenant_id, run),
        # When nothing is running, say what happened to the LAST attempt.
        # "not running" straight after a launch the operator watched succeed
        # is the least useful thing this endpoint could tell them, and it is
        # exactly the state a bot that dies on startup leaves behind.
        **({} if alive else _last_attempt(db, tenant_id, bot_key)),
    }


def _recent_runs(db: Session, tenant_id: str, bot_key: str,
                 limit: int = 5) -> list[dict]:
    """This bot's recent runs, newest first.

    ``extra.config`` carries the launch's own numbers rather than the bot's
    defaults, because the tile compares live session P&L against the target
    and stop that THIS run was started with.
    """
    rows = db.scalars(select(BotRun).where(
        BotRun.tenant_id == tenant_id,
        BotRun.bot_key == bot_key,
    ).order_by(BotRun.id.desc()).limit(limit)).all()
    return [{
        "run_id": row.id,
        "status": row.status,
        "mode": row.mode,
        "bot_version": row.bot_version,
        "started_at": row.started_at,
        "stopped_at": row.stopped_at,
        "extra": {"config": {"bankroll": row.bankroll,
                             "target_pct": row.target_pct,
                             "bank_sl_pct": row.stop_pct}},
    } for row in rows]


def _session(db: Session, tenant_id: str, run: BotRun | None) -> dict | None:
    """What this run has made so far, against the bank it was launched with.

    None when nothing is running: an idle bot has no session, and reporting
    a zero would render as "flat" rather than "not started".
    """
    if run is None:
        return None
    from app.domains.botstation.models import BotTrade

    # Matched on BOT AND START TIME, not on run_id. run_id is never set on a
    # trade: the bot process is not told which run it is -- the row is created
    # after the spawn, so there is no id to hand it -- and every session
    # therefore summed zero rows and reported a flat $0.00 while the bot was
    # making money. The window is exact enough: a bot has one run at a time,
    # so "this bot's trades since this run started" IS this run's trades.
    scope = (BotTrade.tenant_id == tenant_id,
             BotTrade.bot_key == run.bot_key)
    if run.started_at is not None:
        scope = (*scope, BotTrade.opened_at >= run.started_at)

    opened, realised, staked = db.execute(
        select(func.count(BotTrade.id),
               func.coalesce(func.sum(BotTrade.realized_pnl), 0.0),
               func.coalesce(func.sum(BotTrade.entry_usd), 0.0))
        .where(*scope)).one()
    closed = db.scalar(select(func.count(BotTrade.id))
                       .where(*scope, BotTrade.closed_at.is_not(None))) or 0
    won = db.scalar(select(func.count(BotTrade.id))
                    .where(*scope, BotTrade.status == "won")) or 0

    pnl = round(float(realised or 0.0), 2)
    bankroll = run.bankroll or 0
    return {
        "pnl_usd": pnl,
        # What the tile actually prints. Absent before, which is why it read
        # "undefined closed".
        "trades": int(opened or 0),
        "trades_closed": int(closed),
        "trades_open": max(0, int(opened or 0) - int(closed)),
        "won": int(won),
        "lost": max(0, int(closed) - int(won)),
        "staked_usd": round(float(staked or 0.0), 2),
        # Percent OF THE BANK this run was launched with, which is what the
        # target and stop are expressed in. Null rather than 0 when the launch
        # named no bank -- a percentage of nothing is not zero percent.
        "bankroll_pct": (round(pnl / bankroll * 100, 2) if bankroll else None),
        "target_pct": run.target_pct,
        "bank_sl_pct": run.stop_pct,
    }


def _last_attempt(db: Session, tenant_id: str, bot_key: str) -> dict:
    previous = db.scalar(select(BotRun).where(
        BotRun.tenant_id == tenant_id,
        BotRun.bot_key == bot_key,
    ).order_by(BotRun.id.desc()))
    if previous is None:
        return {}
    return {
        "last_run_id": previous.id,
        "last_started_at": previous.started_at,
        "last_stopped_at": previous.stopped_at,
        "last_version": previous.bot_version,
        # The distinction the operator needs: a bot they stopped is not the
        # same news as one that exited on its own.
        "exited_on_its_own": bool(previous.stopped_at
                                  and previous.exit_code is None),
        "log_hint": f"{bot_key}_{previous.bot_version}_launch.log",
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
