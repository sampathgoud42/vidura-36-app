"""One instance of a runtime script, and only one.

levels_watcher.py imports ``ensure_single`` from here. The module lived in the
original bot repo and was not brought over when the watcher was, so every
start from the desk died on its first line with ModuleNotFoundError -- the
LVL CROSS panel kept showing the last snapshot written before the move.

``ensure_single(names)`` exits quietly when another Python process is already
running one of ``names``. Its own ancestors are not "another": on Windows a
venv's python.exe is a launcher that starts the real interpreter as a child
with the same command line, so the parent always looks like a second copy.
Without psutil it does nothing -- the API's start() also refuses a second
watcher, so this is the belt to that braces, not the only guard.
"""

from __future__ import annotations

import os
import sys


def _ancestors() -> set[int]:
    import psutil

    out: set[int] = set()
    try:
        proc = psutil.Process(os.getpid())
        while proc is not None:
            out.add(proc.pid)
            proc = proc.parent()
    except psutil.Error:
        pass
    return out


def ensure_single(names: list[str]) -> None:
    try:
        import psutil
    except ImportError:
        return
    mine = _ancestors()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            if proc.info["pid"] in mine:
                continue
            if "python" not in (proc.info["name"] or "").lower():
                continue
            cmdline = proc.info["cmdline"] or []
            if any(name in (part or "") for part in cmdline for name in names):
                # A child of a running copy is that copy, not a second one --
                # but it is still running, so this one stands down either way.
                print(f"[guard] {names[0]} already running (pid {proc.info['pid']}) -- exiting",
                      flush=True)
                sys.exit(0)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
