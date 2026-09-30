"""The day's first sign-in fills every stored scan, silently.

Best Bets and BreakoutRadar keep their last scan in tables (scan_store), and
until someone asks again that is what they show, stamped with when it ran. The
first sign-in of the desk's day (Central time) -- a login, or a desk opening
on a session that survived the night -- sweeps every combination not yet
scanned today:

    Best Bets      each venue the operator holds a credential for, live first
    BreakoutRadar  US then India, each on 1d, 5m, 15m, 1h and 4h

each landing the way a rescan does -- truncate and load, one combination at a
time -- so a sheet opened meanwhile shows the last scan marked refreshing,
never half of each. Nothing waits for it: the sign-in answers at once.

Two workers, one per vendor -- Tradier for Best Bets, Yahoo for BreakoutRadar
-- so the two run side by side while neither vendor sees more than one sweep
of ours at a time. "Scanned today" is read from the tables rather than kept in
memory, so a restart at noon does not sweep the morning's work again; memory
only spares the tables the question on every later sign-in of the day.

They start START_DELAY_S after the sign-in, not with it: the sign-in is the
moment the desk opens and asks for its charts, balances and positions, and
those should reach the API and the venue's rate allowance first.
"""

from __future__ import annotations

import logging
import threading

from app.core.config import get_settings
from app.domains.trading.risk import clock

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_SEEN: set[tuple[str, str]] = set()     # (desk day, tenant id): already started
_RUNNING: set[str] = set()              # "best_bets:<tenant id>", "breakout"
_THREADS: set[threading.Thread] = set()
_STOP = threading.Event()

START_DELAY_S = 20.0


def on_signin(tenant_id: str) -> bool:
    """Called by /auth/login and /auth/me. Free after an operator's first call
    of the day; True when it started a sweep."""
    if not tenant_id or not get_settings().daily_prescan:
        return False
    day = clock.today().isoformat()
    with _LOCK:
        if (day, tenant_id) in _SEEN:
            return False
        _SEEN.difference_update({seen for seen in _SEEN if seen[0] != day})
        _SEEN.add((day, tenant_id))
    # Best Bets per operator: a venue is swept through the credential of
    # whoever signs in, and an operator without one leaves it to another.
    # BreakoutRadar needs nobody's credential, so it runs once.
    started = _spawn(f"best_bets:{tenant_id}", _best_bets, tenant_id)
    return _spawn("breakout", _breakout) or started


def _spawn(name: str, target, *args) -> bool:
    with _LOCK:
        if name in _RUNNING:
            return False
        _RUNNING.add(name)
    kind = name.split(":")[0]

    def run() -> None:
        try:
            if _STOP.wait(START_DELAY_S):
                return
            target(*args)
        except Exception as exc:                        # noqa: BLE001
            logger.warning("daily scans: %s stopped: %s: %s", kind, type(exc).__name__, exc)
        finally:
            with _LOCK:
                _RUNNING.discard(name)
                _THREADS.discard(threading.current_thread())

    thread = threading.Thread(target=run, daemon=True, name=f"daily-{kind}")
    with _LOCK:
        _THREADS.add(thread)
    thread.start()
    return True


def _credential(tenant_id: str, live: bool):
    """The operator's Tradier credential for a venue, or None without one.
    Decrypted here, held for one sweep, and dropped with the thread."""
    from app.api_v2 import deps
    from app.platform.db.session import session_scope
    from app.tenancy import repository as tenants

    try:
        with session_scope() as db:
            return tenants.load_credential(db, tenant_id, "tradier" if live else "tradier_sandbox",
                                           deps.keyring())
    except Exception:                                   # noqa: BLE001
        return None


def _best_bets(tenant_id: str) -> None:
    from app.domains.trading.market import best_bets, scan_store

    for live in (True, False):
        venue = best_bets.venue_of(sandbox=not live)
        if venue in scan_store.scanned_today(scan_store.BEST_BETS):
            continue
        cred = _credential(tenant_id, live)
        if cred is None:
            continue
        best_bets.sweep_now(cred, sandbox=not live, trigger="daily")


def _breakout() -> None:
    from app.domains.trading.market import breakout, breakout_scan, scan_store

    def done(market: str):
        return lambda timeframe: scan_store.breakout_combo(market, timeframe) \
            in scan_store.scanned_today(scan_store.BREAKOUT)

    for market in breakout.MARKETS:
        todo = [tf for tf in breakout.TIMEFRAMES if not done(market)(tf)]
        if not todo:
            continue
        outcome = breakout_scan.sweep_market(market, todo, trigger="daily", skip=done(market))
        logger.info("daily scans: breakout %s -> %s", market,
                    ", ".join(f"{tf} {what}" for tf, what in outcome.items()))


def running() -> list[str]:
    with _LOCK:
        return sorted(name.split(":")[0] for name in _RUNNING)


def quiesce(timeout: float = 30.0) -> None:
    """Wait for the day's sweeps and forget who signed in (shutdown, tests).
    A sweep still waiting out its start delay does not start."""
    _STOP.set()
    with _LOCK:
        threads = list(_THREADS)
    for thread in threads:
        thread.join(timeout=timeout)
    with _LOCK:
        _THREADS.clear()
        _RUNNING.clear()
        _SEEN.clear()
    _STOP.clear()
