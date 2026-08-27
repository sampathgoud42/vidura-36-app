"""Launch every bot-station bot in PAPER mode, watch it, and stop it.

This is the smoke test the bot station itself cannot be trusted to pass by
inspection: a registry entry can point at a real file that still dies on
import, or authenticates against nothing, or writes its ledger somewhere the
desk never reads. The only way to know is to run each one.

PAPER ONLY. Every launch goes through the same ``bot_manager.start_bot``
path the API endpoint uses, with ``mode="paper"``, which forces
DRY_RUN_MODE / MAIN_PAPER / PARLEY_PAPER / BOTGOLD_DRY_RUN / BOTSILVER_DRY_RUN
to the simulated side and refuses to run at all if the customer's own .env
contradicts it. No order is ever placed on the exchange.

    .venv\\Scripts\\python tools\\paper_smoke_bots.py [--user sampath]
                                                     [--hold 25]
                                                     [--only btc15,sports]

For each bot: start, hold it alive for --hold seconds, read back the status
the desk would show, tail its log, then stop it and confirm the process is
gone. Exit code 0 = every bot started, stayed up and stopped cleanly.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "backend"))

# Bot logs are UTF-8 and full of the engines' arrows and box glyphs; the
# Windows console is cp1252. Without this the tail below dies on the first
# one and the run reports a failure that never happened.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

# The whole point: a bot family, its default version, and the bots that need
# a launch option before they will do anything interesting.
ORDER = ["btc15", "btc60", "gold15", "silver15", "oil15", "sports", "parley"]


def tail(path: Path, n: int = 12) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except OSError:
        return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="sampath")
    ap.add_argument("--hold", type=int, default=25,
                    help="seconds to leave each bot running before stopping it")
    ap.add_argument("--only", default="",
                    help="comma-separated bot keys (default: all)")
    ap.add_argument("--all-versions", action="store_true",
                    help="run every registered version, not just each bot's "
                         "default - the older engines are still selectable "
                         "from the desk, so they still have to start")
    args = ap.parse_args()

    from app.core.config import get_settings
    from app.core.database import SessionLocal
    from app.models import BotRun, User
    from app.services import bot_manager
    from app.services.bot_registry import BOTS, get_bot

    settings = get_settings()
    print(f"project      {PROJECT}")
    print(f"runtime      {settings.source_repo}")
    print(f"customers    {settings.customers_root}")
    print(f"server mode  {'PAPER-ONLY (locked)' if settings.paper_only else 'live unlocked'}"
          f" - this run forces paper regardless\n")

    keys = [k.strip() for k in args.only.split(",") if k.strip()] or ORDER
    unknown = [k for k in keys if k not in BOTS]
    if unknown:
        print(f"unknown bot key(s): {unknown}; known: {list(BOTS)}")
        return 2

    db = SessionLocal()
    failures: list[str] = []
    try:
        user = db.query(User).filter(User.username == args.user).one_or_none()
        if user is None:
            print(f"no user '{args.user}' in the database")
            return 2
        print(f"user         {user.username}  {user.user_root_folder}\n")

        plan: list[tuple[str, str]] = []
        for key in keys:
            spec = get_bot(key)
            if args.all_versions:
                plan += [(key, v.version) for v in spec.versions]
            else:
                plan.append((key, spec.version_or_default(None).version))

        for key, version in plan:
            spec = get_bot(key)
            label = f"{key}/{version}"
            print(f"-- {label} " + "-" * (58 - len(label)))

            opts = bot_manager.BotStartOptions(mode="paper", kill_existing=True)
            if key in ("sports", "parley"):
                # Both refuse a sport they cannot model; name one explicitly
                # so the launch exercises the adapter rather than a default.
                opts.sports = ["tennis"]
                opts.contracts = 1
            try:
                run: BotRun = bot_manager.start_bot(
                    db, user, key, version=version, mode="paper", options=opts)
            except bot_manager.BotManagerError as exc:
                print(f"   START FAILED: {exc}")
                failures.append(f"{label}: start failed: {exc}")
                continue

            log_file = Path(run.log_file) if run.log_file else None
            print(f"   started      run {run.id}  pid {run.pid}  mode {run.mode}")
            if log_file:
                print(f"   log          {log_file}")

            time.sleep(args.hold)
            db.refresh(run)

            alive = bot_manager.process_alive(run.pid) if hasattr(
                bot_manager, "process_alive") else None
            procs = [p for p in bot_manager.find_bot_processes(key)
                     if p["pid"] == run.pid]
            still_up = bool(procs) if alive is None else alive
            print(f"   after {args.hold:>3}s   "
                  f"{'RUNNING' if still_up else 'EXITED EARLY'}")

            if log_file:
                lines = tail(log_file)
                if lines:
                    print("   log tail:")
                    for line in lines:
                        print(f"     | {line}")
                else:
                    print("   log tail:   (empty)")

            if not still_up:
                failures.append(f"{label}: exited before it was stopped")

            try:
                stopped = bot_manager.stop_bot(db, key, user_id=user.user_id)
                print(f"   stopped      {len(stopped)} run(s)")
            except bot_manager.BotManagerError as exc:
                print(f"   STOP FAILED: {exc}")
                failures.append(f"{label}: stop failed: {exc}")
                continue

            leftovers = [p for p in bot_manager.find_bot_processes(key)
                         if p["pid"] == run.pid]
            if leftovers:
                print(f"   LEFTOVER PROCESS: pid {run.pid} survived the stop")
                failures.append(f"{label}: process {run.pid} survived stop")
            else:
                print("   clean        no process left behind")
            print()
    finally:
        db.close()

    print("=" * 62)
    if failures:
        print(f"FAIL: {len(failures)} problem(s)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"PASS: {len(plan)} bot/version launch(es) ran in paper, stayed up "
          f"and stopped clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
