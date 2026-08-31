"""The auto-trader: a watcher that opens managed positions on level crosses.

Built on the rebuild's own execution path rather than ported from the old
engine, and that is the whole point of the module. The legacy auto-trader
wrote straight to the old positions table with its own copy of the entry
logic, which means arming it here would have quietly bypassed every guard the
rebuild exists to provide: the cross-process lease, the idempotency key, the
already-held check, the working-order check, the 0DTE cutoff, and the
requirement that something is watching the stop.

An automated trader is the LAST place to accept a second, unguarded path to
the venue. It fires without anyone watching, so the guards matter more here
than on the manual button, not less. So this module decides WHEN to trade and
delegates the trading itself to orders.open_position -- the identical call the
manual desk makes, guards and all.

What it watches is the level-cross snapshot the levels watcher writes: a new
above_10min_high is a CALL, a new below_10min_low is a PUT, and the cross must
still hold after a confirmation delay before anything is placed. The delay is
not politeness -- it is what separates a real break from a one-tick wick, and
it is the "wait a few seconds and re-check" the operator asked for.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime

from app.domains.trading.risk import clock

logger = logging.getLogger(__name__)

# How long a cross must survive before it is traded. A level tagged and
# immediately reclaimed is noise; one that still holds after this is a break.
CONFIRM_SECONDS = 20

# How often the watcher looks. The levels snapshot is written on a 60s cadence,
# so polling faster only burns CPU re-reading the same file.
POLL_SECONDS = 15

_SIDE_FOR_CROSS = {
    "above_10min_high": "call",
    "below_10min_low": "put",
}


@dataclass
class Watcher:
    """One operator's armed auto-trader."""

    tenant_id: str
    tickers: list[str]
    strategy: str
    live: bool
    buy_pct: float
    tp_pct: float
    sl_pct: float
    tolerance_pct: float
    min_contracts: int
    delta_min: float
    delta_max: float
    armed_at: datetime
    # Crosses seen but not yet confirmed: (ticker, kind) -> first seen at.
    pending: dict[tuple[str, str], float] = field(default_factory=dict)
    # Crosses already traded today, so one break is one trade.
    done: set[tuple[str, str]] = field(default_factory=set)
    events: list[dict] = field(default_factory=list)
    placed: int = 0
    errors: int = 0
    stop_flag: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None

    def log(self, message: str) -> None:
        stamp = clock.now().strftime("%H:%M:%S")
        self.events.append({"at": stamp, "message": message})
        # Bounded: an armed watcher runs for hours and nobody reads the middle.
        del self.events[:-200]
        logger.info("autotrade[%s] %s", self.tenant_id[:8], message)

    def public(self) -> dict:
        return {
            "running": not self.stop_flag.is_set(),
            "strategy": self.strategy,
            "tickers": ",".join(self.tickers),
            "live": self.live,
            "armed_at": self.armed_at.isoformat(),
            "buy_pct": self.buy_pct, "tp_pct": self.tp_pct,
            "sl_pct": self.sl_pct, "min_contracts": self.min_contracts,
            "confirm_seconds": CONFIRM_SECONDS,
            "pending": [{"ticker": t, "cross": k,
                         "held_s": round(time.monotonic() - since, 1)}
                        for (t, k), since in self.pending.items()],
            "traded": [{"ticker": t, "cross": k} for t, k in sorted(self.done)],
            "placed": self.placed, "errors": self.errors,
            "events": self.events[-40:],
        }


_WATCHERS: dict[str, Watcher] = {}
_LOCK = threading.Lock()


class AutoTradeRefused(RuntimeError):
    """The watcher cannot be armed. Carries a reason the operator can act on."""


# ---- what the watcher reads ----------------------------------------------

def crosses(tickers: list[str]) -> list[dict]:
    """Level crosses stamped inside today's session, for the wanted tickers.

    Read from the levels watcher's own snapshot rather than recomputed here.
    Two independent implementations of "did SPY break its opening range" is
    exactly how a desk ends up with a chart and a trade that disagree.
    """
    from app.services import levels as levels_svc

    snapshot = (levels_svc.status() or {}).get("status") or {}
    wanted = {t.upper() for t in tickers}
    out = []
    for row in (snapshot.get("tickers") or snapshot.get("rows") or []):
        symbol = str(row.get("ticker") or row.get("symbol") or "").upper()
        if symbol not in wanted:
            continue
        for kind in _SIDE_FOR_CROSS:
            if row.get(kind):
                out.append({"ticker": symbol, "kind": kind,
                            "at": row.get(f"{kind}_at") or row.get("at"),
                            "price": row.get("price") or row.get("last")})
    return out


# ---- the loop -------------------------------------------------------------

def _place(watcher: Watcher, ticker: str, kind: str) -> None:
    """Open one managed position through the normal, guarded path."""
    from app.api_v2 import deps
    from app.domains.trading.execution import orders, selection
    from app.domains.trading.execution import venue as venue_mod
    from app.platform.db.session import session_scope
    from app.tenancy import repository as tenants

    side = _SIDE_FOR_CROSS[kind]
    with session_scope() as db:
        cred = tenants.load_credential(
            db, watcher.tenant_id,
            "tradier" if watcher.live else "tradier_sandbox", deps.keyring())

        pick = selection.pick_contract(
            ticker, side, cred=cred, sandbox=not watcher.live,
            delta_min=watcher.delta_min, delta_max=watcher.delta_max)
        if pick is None:
            watcher.log(f"{ticker} {side}: no contract in the delta band")
            return

        balance = venue_mod.balance(cred=cred, sandbox=not watcher.live) or {}
        contracts = selection.size_contracts(
            balance.get("option_buying_power") or 0.0, pick["ask"],
            buy_pct=watcher.buy_pct, tolerance_pct=watcher.tolerance_pct)
        if contracts < watcher.min_contracts:
            # Refused rather than rounded up. Sizing below the floor means the
            # account cannot carry this trade at the configured risk, and
            # taking it anyway would be trading a size nobody chose.
            watcher.log(
                f"{ticker} {side}: sized {contracts} < min {watcher.min_contracts}"
                f" — skipped")
            return

        orders.open_position(
            db, tenant_id=watcher.tenant_id, cred=cred, symbol=ticker,
            side=side, occ_symbol=pick["occ_symbol"],
            underlying=ticker, strike=pick["strike"],
            expiration=pick["expiration"], delta=pick.get("delta"),
            contracts=contracts, limit_price=pick["ask"],
            buy_pct=watcher.buy_pct, tolerance_pct=watcher.tolerance_pct,
            tp_pct=watcher.tp_pct, sl_pct=watcher.sl_pct,
            sandbox=not watcher.live, strategy=f"Auto/{watcher.strategy}")
    watcher.placed += 1
    watcher.log(f"{ticker} {side}: opened {contracts} x {pick['occ_symbol']}")


def _run(watcher: Watcher) -> None:
    watcher.log(f"armed on {', '.join(watcher.tickers)} "
                f"({'LIVE' if watcher.live else 'paper'})")
    while not watcher.stop_flag.is_set():
        try:
            if not clock.is_regular_session():
                # Outside the session there is nothing to break out of, and
                # the levels snapshot is yesterday's.
                watcher.stop_flag.wait(POLL_SECONDS)
                continue

            seen = {(c["ticker"], c["kind"]) for c in crosses(watcher.tickers)}

            # A cross that has gone away was a wick. Drop it so a later, real
            # break starts its confirmation window from scratch.
            for key in list(watcher.pending):
                if key not in seen:
                    watcher.pending.pop(key, None)
                    watcher.log(f"{key[0]} {key[1]}: reclaimed before confirm")

            now = time.monotonic()
            for key in seen:
                if key in watcher.done:
                    continue
                if key not in watcher.pending:
                    watcher.pending[key] = now
                    watcher.log(f"{key[0]} {key[1]}: seen, confirming for "
                                f"{CONFIRM_SECONDS}s")
                    continue
                if now - watcher.pending[key] < CONFIRM_SECONDS:
                    continue
                # Marked done BEFORE placing, not after. If the order raises
                # halfway through, a retry on the next tick would be a second
                # entry on the same break -- the duplicate this whole design
                # is built to prevent. One break is one attempt.
                watcher.done.add(key)
                watcher.pending.pop(key, None)
                try:
                    _place(watcher, key[0], key[1])
                except Exception as exc:                # noqa: BLE001
                    watcher.errors += 1
                    watcher.log(f"{key[0]} {key[1]}: refused — {exc}")
        except Exception as exc:                        # noqa: BLE001
            watcher.errors += 1
            watcher.log(f"watch loop error: {type(exc).__name__}: {exc}")
        watcher.stop_flag.wait(POLL_SECONDS)
    watcher.log("disarmed")


# ---- the API --------------------------------------------------------------

def start(tenant_id: str, *, tickers: str, strategy: str, live: bool,
          buy_pct: float, tp_pct: float, sl_pct: float, tolerance_pct: float,
          min_contracts: int, delta_min: float, delta_max: float) -> dict:
    """Arm the watcher for one operator. One per operator, never two."""
    from app.core.config import get_settings
    from app.domains.trading.risk import heartbeat

    if live and get_settings().paper_only:
        raise AutoTradeRefused(
            "this server is paper-only; a live watcher cannot be armed")

    wanted = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not wanted:
        raise AutoTradeRefused("name at least one ticker to watch")

    # Refuse to arm if nothing is watching stops. An unattended trader that
    # can open positions whose stop nobody monitors is the worst combination
    # available, and it is better to refuse at arm time -- when someone is
    # looking -- than at 2pm inside a loop nobody is reading.
    if not heartbeat.is_fresh(tenant_id):
        raise AutoTradeRefused(
            "stop monitoring is not running for this operator; the watcher "
            "will not arm while stops are unwatched")

    with _LOCK:
        existing = _WATCHERS.get(tenant_id)
        if existing is not None and not existing.stop_flag.is_set():
            raise AutoTradeRefused("a watcher is already armed for this "
                                   "operator; stop it before arming another")
        watcher = Watcher(
            tenant_id=tenant_id, tickers=wanted, strategy=strategy, live=live,
            buy_pct=buy_pct, tp_pct=tp_pct, sl_pct=sl_pct,
            tolerance_pct=tolerance_pct, min_contracts=min_contracts,
            delta_min=delta_min, delta_max=delta_max, armed_at=clock.now())
        _WATCHERS[tenant_id] = watcher

    thread = threading.Thread(target=_run, args=(watcher,),
                              name=f"autotrade-{tenant_id[:8]}", daemon=True)
    watcher.thread = thread
    thread.start()
    return watcher.public()


def stop(tenant_id: str) -> dict:
    with _LOCK:
        watcher = _WATCHERS.pop(tenant_id, None)
    if watcher is None:
        return {"running": False, "was_running": False}
    watcher.stop_flag.set()
    return {"running": False, "was_running": True, "placed": watcher.placed}


def status(tenant_id: str) -> dict:
    with _LOCK:
        watcher = _WATCHERS.get(tenant_id)
    if watcher is None or watcher.stop_flag.is_set():
        return {"running": False}
    return watcher.public()


def quiesce(timeout: float = 10.0) -> None:
    """Disarm every watcher and wait for its loop to leave the database alone.

    An armed watcher opens a session on each pass. Tearing the process state
    down underneath one is how a test ends up unable to delete its own
    database file, and how a shutdown ends up interrupting an order.
    """
    with _LOCK:
        watchers = list(_WATCHERS.values())
        _WATCHERS.clear()
    for watcher in watchers:
        watcher.stop_flag.set()
    for watcher in watchers:
        if watcher.thread is not None:
            watcher.thread.join(timeout=timeout)
