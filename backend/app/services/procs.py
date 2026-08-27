"""Process helpers shared by the bot manager and the signal supervisors.

Windows note: ``psutil.process_iter(['cmdline'])`` reads the command line of
EVERY process (~8s for 300+ processes on this machine). Fetching names first
and reading cmdline only for python processes is ~140x faster.
"""

from __future__ import annotations

try:  # local-runtime only; absent in the slim cloud image
    import psutil
except ImportError:  # pragma: no cover - exercised by the cloud image
    psutil = None


def iter_python_processes():
    """Yield (proc, cmdline_list) for python processes only."""
    if psutil is None:
        return
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if not name.startswith("python"):
                continue
            cmdline = proc.cmdline()
        except psutil.Error:
            continue
        yield proc, cmdline


def terminate(procs, *, timeout: float = 6.0) -> list[int]:
    """Terminate then kill; returns the pids that actually went away."""
    if psutil is None or not procs:
        return []
    for p in procs:
        try:
            p.terminate()
        except psutil.Error:
            pass
    gone, alive = psutil.wait_procs(procs, timeout=timeout)
    for p in alive:
        try:
            p.kill()
        except psutil.Error:
            pass
    if alive:
        more, _ = psutil.wait_procs(alive, timeout=3)
        gone += more
    return [p.pid for p in gone]
