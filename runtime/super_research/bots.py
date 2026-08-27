#!/usr/bin/env python
"""bots.py start|stop — control the three super-signal category supervisors.

Used by the web-app schedule (web-app-main/schedule/start_webapp.cmd and
stop_webapp.cmd) so starting/stopping the web app also starts/stops every
backend bot:

    python bots.py start   # start etf/stock/crypto supervisors (skip running)
    python bots.py stop    # kill all supervisors + any transient ticker workers

Each supervisor is launched DETACHED so it survives after this script (and the
scheduled task) exits. Stop matches by command line, so it also catches
supervisors that were started from the desk's "turn on live desk" button.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # super_research/
BOT = HERE / "super_signal_bot.py"
PY = sys.executable
CATS = ["etf", "stock", "crypto"]

DETACHED_PROCESS = 0x00000008 if os.name == "nt" else 0
# Windows-only process flags: zero elsewhere (non-zero creationflags raise
# ValueError on POSIX)
_NT = os.name == "nt"
CREATE_NEW_PROCESS_GROUP = 0x00000200 if _NT else 0
CREATE_NO_WINDOW = 0x08000000 if _NT else 0


def _proc_lines(pattern: str) -> list[str]:
    """Command lines of python processes matching pattern, cross-platform."""
    if _NT:
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                 f"Where-Object {{ $_.CommandLine -match '{pattern}' }} | "
                 "ForEach-Object { $_.CommandLine }"],
                capture_output=True, text=True, timeout=30,
                creationflags=CREATE_NO_WINDOW).stdout
        except Exception:
            out = ""
        return out.splitlines()
    try:
        out = subprocess.run(["ps", "-eo", "pid,command"],
                             capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return []
    return [ln for ln in out.splitlines() if re.search(pattern, ln)]


def _running_categories() -> set[str]:
    running = set()
    for line in _proc_lines(r"super_signal_bot\.py"):
        m = re.search(r"--category\s+(\w+)", line)
        if m:
            running.add(m.group(1))
    return running


def start() -> None:
    running = _running_categories()
    for c in CATS:
        if c in running:
            print(f"super-{c}: already running")
            continue
        log = open(HERE / f"super_{c}.out", "a", encoding="utf-8")
        kwargs = {"cwd": str(HERE), "stdout": log, "stderr": subprocess.STDOUT,
                  "close_fds": True}
        if _NT:
            kwargs["creationflags"] = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True     # POSIX detach
        subprocess.Popen([PY, str(BOT), "--category", c, "--poll", "60"], **kwargs)
        print(f"super-{c}: started")


def stop() -> None:
    if _NT:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
             "Where-Object { $_.CommandLine -match 'super_signal_bot\\.py|_intraday_bot\\.py' } | "
             "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"],
            capture_output=True, text=True, timeout=30,
            creationflags=CREATE_NO_WINDOW)
    else:
        for line in _proc_lines(r"super_signal_bot\.py|_intraday_bot\.py"):
            m = re.match(r"\s*(\d+)", line)
            if m:
                try:
                    os.kill(int(m.group(1)), signal.SIGTERM)
                except OSError:
                    pass
    print("supervisors + workers stopped")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "start":
        start()
    elif cmd == "stop":
        stop()
    else:
        print("usage: bots.py start|stop")
        sys.exit(2)
