"""The loops that have to run whether or not anybody is looking at the desk.

Two of them, and the first one is the reason this module exists at all:

  risk monitor   sweeps every operator's live positions, records fills, arms
                 exits, and fires the monitored stop. It also writes the
                 heartbeat that the order path checks before accepting a new
                 entry.
  reconciler     closes ledger rows the bots opened and never finished,
                 against what actually happened at Kalshi.

``monitor.sweep_all_tenants`` existed and was called by NOTHING. The risk
heartbeat table had zero rows in it, which is exactly what a monitor that has
never run looks like -- and the consequence is not subtle: no monitored stop
could fire, and every open position was unwatched between the moment it was
armed and the moment somebody happened to load a page. The function was
written, tested and simply never started.

So both loops start with the application and stop with it. Failures are
logged and the loop continues: a monitor that exits on the first bad
credential is a monitor that is not running, which is the state this module
was written to end.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

# How often each loop runs. The monitor is the tighter of the two because it
# is what stands between a position and an unbounded loss; reconciliation is
# bookkeeping and nothing gets worse while it waits.
MONITOR_INTERVAL_S = 10
# Six hours, matching the age a row must reach before the sweeper will judge
# it. Running more often than the floor only re-asks a question whose answer
# cannot have changed -- every row young enough to be skipped is still young
# enough to be skipped fifteen minutes later.
#
# The loop calls its work BEFORE its first sleep, so this also runs once on
# every app start, which is when an operator most wants the ledger squared up.
RECONCILE_INTERVAL_S = 6 * 3600


class _Loop:
    """One named background loop, restartable and joinable.

    Joinable matters: these hold database sessions, and anything that tears
    the process state down -- a test, a shutdown -- has to be able to wait for
    them rather than pull the database out from underneath.
    """

    def __init__(self, name: str, interval_s: float, work) -> None:
        self.name = name
        self.interval_s = interval_s
        self.work = work
        self.stop_flag = threading.Event()
        self.thread: threading.Thread | None = None
        self.runs = 0
        self.errors = 0
        self.last_error: str | None = None

    def _run(self) -> None:
        logger.info("background loop %s started (every %ss)",
                    self.name, self.interval_s)
        while not self.stop_flag.is_set():
            try:
                self.work()
                self.runs += 1
            except Exception as exc:                    # noqa: BLE001
                # Never fatal. A loop that exits on an error is worse than a
                # loop that logs one, because nothing announces the exit.
                self.errors += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("background loop %s: %s", self.name,
                               self.last_error)
            self.stop_flag.wait(self.interval_s)
        logger.info("background loop %s stopped", self.name)

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self.stop_flag.clear()
        self.thread = threading.Thread(target=self._run, name=self.name,
                                       daemon=True)
        self.thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self.stop_flag.set()
        if self.thread is not None:
            self.thread.join(timeout=timeout)

    def state(self) -> dict:
        return {"running": self.thread is not None and self.thread.is_alive(),
                "interval_s": self.interval_s, "runs": self.runs,
                "errors": self.errors, "last_error": self.last_error}


def _sweep_stops() -> None:
    from app.domains.trading.risk import monitor

    monitor.sweep_all_tenants()


def _sweep_ledger() -> None:
    from app.domains.botstation import reconcile

    reconcile.sweep_all_tenants(apply=True)


_LOOPS: dict[str, _Loop] = {}


def start_all() -> None:
    """Start both loops. Idempotent, so a reload does not double them up."""
    if not _LOOPS:
        _LOOPS["risk-monitor"] = _Loop("risk-monitor", MONITOR_INTERVAL_S,
                                       _sweep_stops)
        _LOOPS["reconciler"] = _Loop("reconciler", RECONCILE_INTERVAL_S,
                                     _sweep_ledger)
    for loop in _LOOPS.values():
        loop.start()


def stop_all(timeout: float = 10.0) -> None:
    for loop in _LOOPS.values():
        loop.stop(timeout=timeout)


def status() -> dict:
    return {name: loop.state() for name, loop in _LOOPS.items()}
