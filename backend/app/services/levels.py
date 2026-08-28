"""Index-basket level-cross watcher (SPY / QQQ / SPX) — service wrapper.

The engine is ``levels_watcher.py`` in the day-trade folder of the original
bot repo: it marks yesterday's RTH high/low, the post-market range and the
08:30–08:40 opening range each day, then flags the first 5-minute close that
crosses each level. It writes a UI snapshot to ``levels_status.json`` in its
own folder — this module reads that snapshot and starts/stops the watcher
process, nothing more. The engine itself is not duplicated here: the same
process also feeds the legacy intraday desk through day_trade.csv, so there
must be exactly one instance, running in the ORIGINAL folder.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from app.core.config import get_settings
from app.services.procs import iter_python_processes, terminate

logger = logging.getLogger(__name__)

_CHILD: subprocess.Popen | None = None

WATCHER = "levels_watcher.py"


class LevelsError(RuntimeError):
    pass


def _watcher_procs() -> list:
    procs = []
    for proc, cmdline in iter_python_processes():
        if any(WATCHER in (part or "") for part in cmdline):
            procs.append(proc)
    return procs


def status() -> dict:
    """Snapshot + liveness. The snapshot is a local file read; liveness is a
    python-process scan (procs.py keeps it cheap on Windows)."""
    settings = get_settings()
    snap = None
    path = settings.levels_dir / "levels_status.json"
    try:
        snap = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        pass  # watcher never ran here — the desk shows "not running"
    global _CHILD
    running = _CHILD is not None and _CHILD.poll() is None
    pid = _CHILD.pid if running else None
    if not running:
        found = _watcher_procs()
        running = bool(found)
        pid = found[0].pid if found else None
    return {"running": running, "pid": pid, "status": snap}


def start() -> dict:
    """Spawn the watcher detached (survives API restarts), 60s poll."""
    settings = get_settings()
    if not settings.levels_dir.is_dir():
        raise LevelsError(f"levels folder missing: {settings.levels_dir}")
    script = settings.levels_dir / WATCHER
    if not script.is_file():
        raise LevelsError(f"watcher script missing: {script}")
    if _watcher_procs():
        return {"started": False, "already": True}
    python = str(settings.super_python)  # needs yfinance/pandas, like the bots
    if not Path(python).is_file():
        python = sys.executable
    out = settings.levels_dir / "levels_watcher.out"
    creationflags = 0
    if os.name == "nt":
        DETACHED_PROCESS = 0x00000008
        creationflags = DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    global _CHILD
    with open(out, "a", encoding="utf-8", errors="replace") as log_handle:
        _CHILD = subprocess.Popen(
            [python, str(script)],
            cwd=str(settings.levels_dir),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            close_fds=True,
            creationflags=creationflags,
        )
    logger.info("Started levels watcher (pid %s)", _CHILD.pid)
    return {"started": True, "pid": _CHILD.pid}


def stop() -> dict:
    """Terminate every levels_watcher.py on the machine (there should be at
    most one — the day-trade desk reads the same instance)."""
    global _CHILD
    procs = _watcher_procs()
    gone = terminate(procs)
    _CHILD = None
    return {"stopped": gone, "count": len(gone)}
