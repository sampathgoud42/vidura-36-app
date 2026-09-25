"""The auto-trader: a watcher that opens managed positions when a signal fires.

Three strategies, and the arm form offers exactly these (``STRATEGIES``):

``10min_intraday_move`` -- the level-cross watcher described below.

``super_signals`` -- the signal-agent desk's own signals, as they fire. The
operator picks signal types from the desk's ranking (/super-signals/rank: the
daily report's edge score for today, else yesterday, with every type whose
longest window disagrees left out) and the tickers to trade. A new LIVE signal
of a picked type on one of those tickers buys a CALL for a LONG and a PUT for
a SHORT -- only inside the CST window, only while the signal is minutes old
and still open, and at most once per ticker per hour. The list was picked from
one day's results, so the watcher disarms itself at that session's close.
Entries go through entry.open_managed, the manual BUY's own path, under an
idempotency key per signal.

``best_pairs`` -- the same watcher, matching on the report's best ticker +
signal pairs (/super-signals/best-pairs) instead: a new live signal trades only
when its signal type AND its ticker are one of the picked pairs. A pair is a
record on that one ticker -- poc_72h LONG has earned its place on TSLA, not on
every symbol it fires on. Every other rule is super_signals' own, the
idempotency key included, so a signal either strategy has acted on is never
bought again by the other.


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
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from datetime import time as dtime

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

# The strategies this watcher runs -- the arm form lists exactly these, so a
# strategy name can no longer label one behaviour while running another.
STRATEGIES = ("10min_intraday_move", "super_signals", "best_pairs")
# the strategies that trade the signal desk's live signals (_run_super)
SIGNAL_STRATEGIES = ("super_signals", "best_pairs")

# super_signals. The desk publishes each 5m bar about half a minute after it
# closes, so a 15s poll sees a signal within a minute of its candle.
SUPER_POLL_SECONDS = 15
# Older than this and the move the signal called has happened without us.
SUPER_MAX_AGE_S = 6 * 60
# One entry per ticker per hour, whichever picked signal fires on it: two
# signal types agreeing on SPY is one idea, not two positions.
SUPER_COOLDOWN_S = 60 * 60
SUPER_WINDOW = ("08:30", "14:30")
# agent|setup|grade|direction, as /super-signals/rank keys a signal type
_TYPE_KEY = re.compile(r"^[a-z_]+\|[^|\s]{1,80}\|[^|\s]{0,24}\|(LONG|SHORT)$")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_SYMBOL = re.compile(r"^[A-Z0-9.^-]{1,10}$")


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
    # --- super_signals / best_pairs ---
    signals: list[str] = field(default_factory=list)
    # best_pairs: the (type key, ticker) pairs picked from the desk's list
    pairs: set[tuple[str, str]] = field(default_factory=set)
    window_open: str = SUPER_WINDOW[0]
    window_close: str = SUPER_WINDOW[1]
    zero_dte: bool = False
    # Signal ids already looked at, so each one is judged exactly once.
    seen_ids: set[str] = field(default_factory=set)
    # ticker -> when this watcher last entered it (the cooldown).
    last_entry: dict[str, datetime] = field(default_factory=dict)
    trades: list[dict] = field(default_factory=list)
    feed: str = "starting"

    def log(self, message: str) -> None:
        stamp = clock.now().strftime("%H:%M:%S")
        self.events.append({"at": stamp, "message": message})
        # Bounded: an armed watcher runs for hours and nobody reads the middle.
        del self.events[:-200]
        logger.info("autotrade[%s] %s", self.tenant_id[:8], message)

    @property
    def label(self) -> str:
        """What its positions say they were opened by."""
        return f"Auto/{self.strategy}"

    def wants(self, row: dict) -> bool:
        """Whether a desk signal is one this watcher trades: for best_pairs one
        of its pairs -- that signal type on that ticker -- and for
        super_signals a picked type on any picked ticker."""
        if self.strategy == "best_pairs":
            return (type_key(row), row.get("ticker")) in self.pairs
        return type_key(row) in self.signals and row.get("ticker") in self.tickers

    def public(self) -> dict:
        out = self._public_common()
        if self.strategy in SIGNAL_STRATEGIES:
            out.update({
                "window": f"{self.window_open}-{self.window_close}",
                "zero_dte": self.zero_dte, "feed": self.feed,
                "trades": self.trades[-20:], "seen": len(self.seen_ids),
                "cooldown_min": SUPER_COOLDOWN_S // 60,
                "max_age_min": SUPER_MAX_AGE_S // 60,
            })
        if self.strategy == "super_signals":
            out["signals"] = list(self.signals)
        if self.strategy == "best_pairs":
            out["pairs"] = [{"type_key": k, "ticker": t} for k, t in sorted(self.pairs)]
        return out

    def _public_common(self) -> dict:
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


# ---- super_signals ----------------------------------------------------------

def type_key(row: dict) -> str:
    """The signal type a desk row belongs to, keyed as /super-signals/rank keys it."""
    return (f"{row.get('agent', '')}|{row.get('setup', '')}|{row.get('grade', '')}|"
            f"{row.get('direction', '')}")


def refusal(row: dict, *, now: datetime, window_open: str, window_close: str,
            last_entry: datetime | None = None, max_age_s: int = SUPER_MAX_AGE_S,
            cooldown_s: int = SUPER_COOLDOWN_S) -> str | None:
    """Why a signal of a picked type on a picked ticker is NOT traded, or None.

    Pure, so every rule is testable without a clock or a venue. Each one is
    the difference between trading the signal and trading a memory of it:
    catchup / backfill / reconcile rows were found after the fact, a resolved
    signal has already paid or failed, and an old one has already moved.
    """
    source = row.get("source") or "unknown"
    if source != "live":
        return f"found as {source}, not fired live"
    outcome = row.get("outcome") or "open"
    if outcome != "open":
        return f"already resolved ({outcome})"
    t = row.get("time") or ""
    if not (window_open <= t < window_close):
        return f"fired {t or '?'}, outside {window_open}-{window_close}"
    try:
        fired = datetime.combine(now.date(), dtime.fromisoformat(t), tzinfo=now.tzinfo)
    except ValueError:
        return f"unreadable signal time {t!r}"
    age = (now - fired).total_seconds()
    if age > max_age_s:
        return f"{int(age // 60)} min old -- older than {max_age_s // 60} min"
    if last_entry is not None:
        since = (now - last_entry).total_seconds()
        if since < cooldown_s:
            return (f"entered {row.get('ticker', '?')} {int(since // 60)} min ago -- "
                    f"cooldown, {int((cooldown_s - since) // 60) + 1} min left")
    return None


def _feed(watcher: Watcher, state: str) -> None:
    """Record the signal feed's state, logging only when it changes -- a service
    that is down for an hour is one line, not two hundred and forty."""
    if state != watcher.feed:
        watcher.feed = state
        watcher.log(f"signal desk: {state}")


def _enter(watcher: Watcher, row: dict, side: str):
    """One signal -> one managed position, through the manual BUY's own path.

    The idempotency key is the signal's own id, so no restart, re-arm or retry
    can act on the same signal twice -- and it is the same key for both signal
    strategies, so neither can buy a signal the other already has. A refusal
    records itself and releases the key, exactly as a refused manual order does.
    """
    from app.api_v2 import deps
    from app.domains.trading.execution import entry, idempotency
    from app.domains.trading.execution.orders import ExecutionRefused
    from app.platform.db.session import session_scope
    from app.tenancy import repository as tenants

    # Same-day contracts only before the auto-trader's 0DTE cutoff (11:50 CST,
    # earlier than a person's); after it the nearest later expiry, rather than a
    # refusal on every later signal. The order re-checks the cutoff itself.
    zero_dte = watcher.zero_dte and not clock.past_auto_zero_dte_cutoff()
    venue_name = "tradier" if watcher.live else "tradier_sandbox"
    with session_scope() as db:
        try:
            attempt = idempotency.begin(
                db, tenant_id=watcher.tenant_id, intent="open",
                payload={"signal": row["id"], "symbol": row["ticker"], "side": side,
                         "live": watcher.live, "strategy": watcher.label},
                client_key=f"auto-super:{row['id']}")
        except (idempotency.DuplicateRequest, idempotency.KeyReused):
            watcher.log(f"{row['ticker']}: this signal was already acted on -- skipped")
            return None
        try:
            try:
                cred = tenants.load_credential(db, watcher.tenant_id, venue_name,
                                               deps.keyring())
            except Exception:                           # noqa: BLE001
                # Never relay the venue's own text: a 401 body can carry the token.
                raise ExecutionRefused(
                    f"no usable {venue_name} credential for this operator") from None
            pos = entry.open_managed(
                db, tenant_id=watcher.tenant_id, cred=cred, symbol=row["ticker"],
                side=side, buy_pct=watcher.buy_pct, tp_pct=watcher.tp_pct,
                sl_pct=watcher.sl_pct, delta_min=watcher.delta_min,
                delta_max=watcher.delta_max, tolerance_pct=watcher.tolerance_pct,
                sandbox=not watcher.live, strategy=watcher.label,
                zero_dte=zero_dte, min_contracts=watcher.min_contracts)
        except Exception as exc:
            idempotency.fail(db, attempt, reason=str(exc)[:500])
            db.commit()              # the scope rolls back on the way out
            raise
        idempotency.succeed(db, attempt, result={"signal": row["id"], "position_id": pos.id,
                                                 "occ_symbol": pos.occ_symbol},
                            position_id=pos.id, venue_order_id=pos.buy_order_id)
        opened = {"position_id": pos.id, "occ_symbol": pos.occ_symbol,
                  "contracts": pos.contracts}
    watcher.placed += 1
    watcher.trades.append({"at": clock.now().strftime("%H:%M:%S"), "ticker": row["ticker"],
                           "side": side, "signal": type_key(row),
                           "signal_time": row.get("time"), **opened})
    watcher.log(f"{row['ticker']} {side}: opened {opened['contracts']} x {opened['occ_symbol']}"
                f" on {row.get('agent')} {row.get('setup')} {row.get('direction')}"
                f" @ {row.get('time')}")
    return opened


def _super_tick(watcher: Watcher, now: datetime, baseline_day: str | None) -> str | None:
    """One look at the desk. Returns the session whose backlog is baselined."""
    from app.domains.trading.execution.orders import ExecutionRefused
    from app.domains.trading.execution.leases import LeaseUnavailable
    from app.domains.trading.risk.validation import RiskRefused
    from app.services import super_signals as desk

    today = now.date().isoformat()
    try:
        payload = desk.get_json("/api/session")
    except desk.Unavailable as exc:
        _feed(watcher, f"unavailable -- {exc.detail}")
        return baseline_day
    if payload.get("date") != today:
        _feed(watcher, f"serving {payload.get('date')}, not today")
        return baseline_day
    _feed(watcher, "ok")
    rows = payload.get("signals") or []
    if baseline_day != today:
        # Everything already on the desk when the watcher arms -- or when a new
        # session begins -- is history, not a trigger: arming must never fire a
        # burst of entries on signals that were not watched fire.
        watcher.seen_ids = {r.get("id") for r in rows if r.get("id")}
        watcher.log(f"{len(watcher.seen_ids)} signal(s) already on the desk today "
                    f"-- history, not triggers")
        return today

    for row in sorted(rows, key=lambda r: (r.get("time") or "", r.get("id") or "")):
        sid = row.get("id")
        if not sid or sid in watcher.seen_ids:
            continue
        watcher.seen_ids.add(sid)            # judged once, whatever happens next
        if not watcher.wants(row):
            continue
        what = f"{row['ticker']} {row.get('agent')} {row.get('setup')} {row.get('direction')}"
        why_not = refusal(row, now=now, window_open=watcher.window_open,
                          window_close=watcher.window_close,
                          last_entry=watcher.last_entry.get(row["ticker"]))
        if why_not:
            watcher.log(f"{what} @ {row.get('time')}: not traded -- {why_not}")
            continue
        side = "call" if row.get("direction") == "LONG" else "put"
        before = watcher.last_entry.get(row["ticker"])
        # The cooldown starts BEFORE the order: two signals on one ticker in the
        # same pass must not both slip through behind each other.
        watcher.last_entry[row["ticker"]] = now
        try:
            if _enter(watcher, row, side) is None:
                _restore(watcher, row["ticker"], before)
        except (ExecutionRefused, RiskRefused, LeaseUnavailable) as exc:
            # Refused before the venue was touched: nothing was bought, so the
            # ticker is not on cooldown for it.
            _restore(watcher, row["ticker"], before)
            watcher.errors += 1
            watcher.log(f"{what}: refused -- {exc}")
        except Exception as exc:                        # noqa: BLE001
            # Unknown failure: an order may have gone out, so the cooldown stands.
            watcher.errors += 1
            watcher.log(f"{what}: failed -- {type(exc).__name__}: {exc}")
    return baseline_day


def _restore(watcher: Watcher, ticker: str, before: datetime | None) -> None:
    if before is None:
        watcher.last_entry.pop(ticker, None)
    else:
        watcher.last_entry[ticker] = before


def _run_super(watcher: Watcher) -> None:
    what = (f"{len(watcher.pairs)} best pair(s) on" if watcher.strategy == "best_pairs"
            else f"{len(watcher.signals)} signal type(s) for")
    watcher.log(f"armed on {what} {', '.join(watcher.tickers)} · "
                f"{watcher.window_open}-{watcher.window_close} CST"
                f" ({'LIVE' if watcher.live else 'paper'})")
    baseline_day: str | None = None
    saw_session = False
    while not watcher.stop_flag.is_set():
        try:
            now = clock.now()
            if clock.is_regular_session(now):
                saw_session = True
                baseline_day = _super_tick(watcher, now, baseline_day)
            elif saw_session and now.timetz().replace(tzinfo=None) >= clock.SESSION_CLOSE:
                # The list was picked from one day's results, and tomorrow ranks
                # differently -- so the watcher ends with the session it traded.
                watcher.log("session closed -- disarming; "
                            + ("the best pairs are re-ranked by today's report"
                               if watcher.strategy == "best_pairs"
                               else "the signal list was picked for today"))
                break
        except Exception as exc:                        # noqa: BLE001
            watcher.errors += 1
            watcher.log(f"watch loop error: {type(exc).__name__}: {exc}")
        watcher.stop_flag.wait(SUPER_POLL_SECONDS)
    watcher.stop_flag.set()
    with _LOCK:
        if _WATCHERS.get(watcher.tenant_id) is watcher:
            _WATCHERS.pop(watcher.tenant_id, None)
    watcher.log("disarmed")


# ---- the API --------------------------------------------------------------

def _check_super(wanted: list[str], signals: list[str], window_open: str,
                 window_close: str, **risk) -> None:
    """Refuse a super_signals arm at arm time, while someone is looking, rather
    than at 2pm inside a loop nobody is reading."""
    if not signals:
        raise AutoTradeRefused("pick at least one signal type to trade")
    bad = [k for k in signals if not _TYPE_KEY.match(k)]
    if bad:
        raise AutoTradeRefused(f"not a signal type: {bad[0][:80]}")
    odd = [t for t in wanted if not _SYMBOL.match(t)]
    if odd:
        raise AutoTradeRefused(f"tickers must be plain symbols like SPY, QQQ, SPX -- not {odd[0][:12]}")
    _check_window_and_risk(window_open, window_close, **risk)


def _listed_pairs() -> set[tuple[str, str]]:
    """The desk's best pairs as they stand -- what a best_pairs arm picks from."""
    from app.services import super_signals as desk

    try:
        body = desk.get_json("/api/best-pairs")
    except desk.Unavailable as exc:
        raise AutoTradeRefused(
            f"the signal desk cannot confirm the best pairs right now -- {exc.detail}") from None
    return {(str(p.get("type_key")), str(p.get("ticker"))) for p in body.get("pairs") or []}


def _check_pairs(pairs: list[dict] | None, window_open: str, window_close: str,
                 **risk) -> set[tuple[str, str]]:
    """The picked (type key, ticker) pairs, refused at arm time unless every one
    is well formed AND still on the desk's list. The list is rewritten after
    each report, so a form loaded before 15:00 may hold a pair that has since
    dropped off; that is said, not traded."""
    picked = list(dict.fromkeys(
        (str((p or {}).get("type_key") or "").strip(), str((p or {}).get("ticker") or "").strip().upper())
        for p in (pairs or [])))
    if not picked:
        raise AutoTradeRefused("pick at least one best pair to trade")
    bad = [k for k, _ in picked if not _TYPE_KEY.match(k)]
    if bad:
        raise AutoTradeRefused(f"not a signal type: {bad[0][:80]}")
    odd = [t for _, t in picked if not _SYMBOL.match(t)]
    if odd:
        raise AutoTradeRefused(f"a pair's ticker must be a plain symbol like TSLA -- not {odd[0][:12]}")
    _check_window_and_risk(window_open, window_close, **risk)
    listed = _listed_pairs()
    gone = [f"{t} {k}" for k, t in picked if (k, t) not in listed]
    if gone:
        raise AutoTradeRefused(
            f"{len(gone)} pick(s) no longer on the best-pairs list, which is rewritten after "
            f"each report -- reload the form: {', '.join(gone[:3])}")
    return set(picked)


def _check_window_and_risk(window_open: str, window_close: str, *, buy_pct: float,
                           tp_pct: float, sl_pct: float, delta_min: float, delta_max: float,
                           min_contracts: int) -> None:
    from app.domains.trading.risk.validation import RiskRefused, validate_entry

    if not (_HHMM.match(window_open) and _HHMM.match(window_close)) or window_open >= window_close:
        raise AutoTradeRefused("the window must be HH:MM to HH:MM (CST), start before end")
    try:
        validate_entry(side="call", buy_pct=buy_pct, tp_pct=tp_pct, sl_pct=sl_pct)
    except RiskRefused as exc:
        raise AutoTradeRefused(str(exc)) from None
    if not (0 < delta_min < delta_max <= 1):
        raise AutoTradeRefused("the delta range must be 0 < min < max <= 1")
    if min_contracts < 1:
        raise AutoTradeRefused("min contracts must be at least 1")


def start(tenant_id: str, *, tickers: str, strategy: str, live: bool,
          buy_pct: float, tp_pct: float, sl_pct: float, tolerance_pct: float,
          min_contracts: int, delta_min: float, delta_max: float,
          signals: list[str] | None = None, pairs: list[dict] | None = None,
          window_open: str | None = None, window_close: str | None = None,
          zero_dte: bool = False) -> dict:
    """Arm the watcher for one operator. One per operator, never two."""
    from app.core.config import get_settings
    from app.domains.trading.risk import heartbeat

    if live and get_settings().paper_only:
        raise AutoTradeRefused(
            "this server is paper-only; a live watcher cannot be armed")

    if strategy not in STRATEGIES:
        raise AutoTradeRefused(f"unknown strategy '{strategy}' -- this server runs "
                               f"{', '.join(STRATEGIES)}")

    w_open = (window_open or SUPER_WINDOW[0]).strip()
    w_close = (window_close or SUPER_WINDOW[1]).strip()
    risk = {"buy_pct": buy_pct, "tp_pct": tp_pct, "sl_pct": sl_pct, "delta_min": delta_min,
            "delta_max": delta_max, "min_contracts": min_contracts}
    picked: list[str] = []
    chosen: set[tuple[str, str]] = set()
    if strategy == "best_pairs":
        # A pair names its own ticker, so the form's ticker field plays no part.
        chosen = _check_pairs(pairs, w_open, w_close, **risk)
        wanted = sorted({t for _, t in chosen})
    else:
        wanted = [t.strip().upper() for t in tickers.split(",") if t.strip()]
        if not wanted:
            raise AutoTradeRefused("name at least one ticker to watch")
        picked = list(dict.fromkeys(str(k).strip() for k in (signals or []) if str(k).strip()))
        if strategy == "super_signals":
            _check_super(wanted, picked, w_open, w_close, **risk)

    # Refuse to arm if nothing is watching stops. An unattended trader that
    # can open positions whose stop nobody monitors is the worst combination
    # available, and it is better to refuse at arm time -- when someone is
    # looking -- than at 2pm inside a loop nobody is reading.
    if not heartbeat.is_fresh(tenant_id):
        if get_settings().enforce_stop_watchdog:
            raise AutoTradeRefused(
                "stop monitoring is not running for this operator; the watcher "
                "will not arm while stops are unwatched")
        # Same override as the order path. An UNATTENDED trader with an
        # unwatched stop is the worst combination this system can be put in,
        # so it is said at WARNING every time one arms this way.
        logger.warning(
            "tenant %s: arming an unattended watcher while stop monitoring is "
            "stale -- TBOT_ENFORCE_STOP_WATCHDOG is off", tenant_id)

    with _LOCK:
        existing = _WATCHERS.get(tenant_id)
        if existing is not None and not existing.stop_flag.is_set():
            raise AutoTradeRefused("a watcher is already armed for this "
                                   "operator; stop it before arming another")
        watcher = Watcher(
            tenant_id=tenant_id, tickers=wanted, strategy=strategy, live=live,
            buy_pct=buy_pct, tp_pct=tp_pct, sl_pct=sl_pct,
            tolerance_pct=tolerance_pct, min_contracts=min_contracts,
            delta_min=delta_min, delta_max=delta_max, armed_at=clock.now(),
            signals=picked, pairs=chosen, window_open=w_open, window_close=w_close,
            zero_dte=bool(zero_dte))
        _WATCHERS[tenant_id] = watcher

    # Warm the modules the loop imports lazily, on THIS thread: two threads
    # importing the same package at once can deadlock on Python's import lock
    # and kill the watcher silently before its first poll.
    from app.domains.trading.execution import entry, idempotency  # noqa: F401
    from app.services import super_signals as _desk  # noqa: F401

    loop = _run_super if strategy in SIGNAL_STRATEGIES else _run
    thread = threading.Thread(target=loop, args=(watcher,),
                              name=f"autotrade-{tenant_id[:8]}", daemon=True)
    watcher.thread = thread
    thread.start()
    return _answer(watcher.public(), active=True)


def defaults() -> dict:
    """What the arm form prefills, and the strategies it may offer."""
    return {
        "strategy": STRATEGIES[0], "strategies": list(STRATEGIES),
        "tickers": "SPY,QQQ,SPX", "window_open": "08:30", "window_close": "09:30",
        "super_window_open": SUPER_WINDOW[0], "super_window_close": SUPER_WINDOW[1],
        "buy_pct": 50.0, "tolerance_pct": 25.0, "tp_pct": 15.0, "sl_pct": 30.0,
        "delta_min": 0.35, "delta_max": 0.65, "min_contracts": 1,
        "confirm_s": CONFIRM_SECONDS,
        # the auto-trader's own, earlier cutoff -- what the form tells the operator
        "zero_dte_cutoff": clock.AUTO_ZERO_DTE_CUTOFF.strftime("%H:%M"),
        "super_poll_s": SUPER_POLL_SECONDS,
        "super_max_age_min": SUPER_MAX_AGE_S // 60,
        "super_cooldown_min": SUPER_COOLDOWN_S // 60,
    }


def _answer(body: dict, *, active: bool) -> dict:
    """Every answer carries the form's defaults and ``active``, which is what both
    desks read -- without them the 36 Trades sheet waited forever for settings
    and neither desk could show an armed watcher, or disarm one."""
    return {**body, "active": active, "strategies": list(STRATEGIES),
            "defaults": defaults()}


def stop(tenant_id: str) -> dict:
    with _LOCK:
        watcher = _WATCHERS.pop(tenant_id, None)
    if watcher is None:
        return _answer({"running": False, "was_running": False}, active=False)
    watcher.stop_flag.set()
    return _answer({"running": False, "was_running": True, "placed": watcher.placed},
                   active=False)


def status(tenant_id: str) -> dict:
    with _LOCK:
        watcher = _WATCHERS.get(tenant_id)
    if watcher is None or watcher.stop_flag.is_set():
        return _answer({"running": False}, active=False)
    return _answer(watcher.public(), active=True)


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
