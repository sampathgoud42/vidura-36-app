"""Auto-trade: one watcher per user, running one of two strategies.

``ab_signal_options`` — A/B super signals into options.
  A new LONG signal buys a CALL, a SHORT buys a PUT, on that signal's own
  ticker, picked from the same delta band the desk uses by hand.

  The signal does NOT place the order. The chosen contract's BID is sampled
  and watched first: after 5 minutes (up to 10) it is bought only while that
  bid is rising or stable. A fading bid is not thrown away — the watcher
  keeps looking and takes it the moment the trailing 2-3 minute window turns
  steady again, giving up after ab_max_wait_s. Buying a premium that is
  already melting is the mistake this whole phase exists to prevent.

  Expirations run from today out to ab_dte_max (6) days. Same-day contracts
  are entered ONLY before ab_zero_dte_cutoff (13:00 CST) — checked twice,
  once so an observation that cannot finish in time never starts, and again
  at the moment of the order. TP 15% rests on the venue, SL 30% is the
  monitor loop, exactly as with a manual position.

  After an entry the ticker is on ab_cooldown_s (60 min): later signals for
  it are ignored, however good they look. The cooldown is read from the
  position ledger rather than watcher memory, so it survives a restart, and
  it is re-checked at the order — two observations on one ticker can ripen
  together, and the second must not slip through behind the first.

``10min_intraday_move`` — the original opening-range level-cross strategy.

Armed by the desk's AUTO TRADE button (which opens a form: strategy,
tickers, CST time window, buy/tp/sl %, min contracts). Every poll it reads
the level-cross snapshot (levels_watcher.py via services.levels) and, for
the configured tickers:

  * a NEW ``above_10min_high`` cross  ->  CALL candidate
  * a NEW ``below_10min_low``  cross  ->  PUT  candidate

Only crosses stamped inside the window (default 08:30-09:30 CST — the
opening-range play; the range itself is marked 08:30-08:40, crosses start
08:45) qualify. A candidate is NOT traded immediately: it waits confirm_s
(default 5 minutes), then the snapshot is read again and the trade fires
only if that level's latest signal is STILL the same — a flip back inside
the range cancels the candidate.

The order is the desk's normal managed position (tradier_bot.open_position)
pinned to TODAY's expiration (0DTE), sized by % of option buying power. If
that sizing lands below min_contracts the trade is SKIPPED (recorded, not
retried). TP rests on the venue and the SL is watched by the API's monitor
loop — exits need nothing from this module.

Defaults for every knob live in Settings under env prefix TBOT_TRADIER_*
(tradier_auto_strategy, tradier_auto_tickers, tradier_auto_window_open/
close, tradier_auto_confirm_s, tradier_auto_poll_s,
tradier_auto_min_contracts, and the desk-wide buy/tp/sl/delta defaults).

The watcher survives across days: each CST date it re-arms for the window
and trades each (date, ticker, level, bar) instance at most once. It runs
until stopped from the desk (or the API restarts — state is in-process by
design; re-arm is one click).
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings

logger = logging.getLogger(__name__)

CST = ZoneInfo("America/Chicago")

STRATEGIES = ("10min_intraday_move", "hot_tickers", "super_hot_tickers")
SIGNAL_SIDE = {"above_10min_high": "call", "below_10min_low": "put"}
# A/B super signals: the direction IS the option side.
AB_SIDE = {"LONG": "call", "SHORT": "put"}
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# ── A/B strategy: pure decision helpers (no I/O, unit-tested) ───────────────

def bid_trend(samples: list[float], *, tol_pct: float) -> str:
    """``rising`` | ``stable`` | ``falling`` | ``unknown`` for a bid series.

    Falling is not only "ended lower": a bid that spiked and gave the move
    back is fading too, which is exactly the entry this strategy exists to
    avoid. Anything inside the tolerance either way is stable.
    """
    pts = [float(x) for x in samples if x is not None and float(x) > 0]
    if len(pts) < 2:
        return "unknown"
    first, last, peak = pts[0], pts[-1], max(pts)
    up = first * (1 + tol_pct / 100.0)
    down = first * (1 - tol_pct / 100.0)
    # gave back more than twice the tolerance from the window's peak
    if last < peak * (1 - 2 * tol_pct / 100.0):
        return "falling"
    if last > up:
        return "rising"
    if last < down:
        return "falling"
    return "stable"


def choose_expiration(expirations, today, *, dte_max: int,
                      allow_zero_dte: bool) -> tuple[str | None, int | None]:
    """Nearest listed expiry within ``today .. today + dte_max``.

    0DTE is skipped entirely once the CST cutoff has passed — the operator's
    rule is that same-day contracts are only entered early, when there is
    still session left for the move to happen.
    """
    from datetime import date as _date

    best = None
    for e in expirations or []:
        try:
            d = _date.fromisoformat(str(e))
        except (TypeError, ValueError):
            continue
        dte = (d - today).days
        if dte < 0 or dte > dte_max:
            continue
        if dte == 0 and not allow_zero_dte:
            continue
        if best is None or dte < best[1]:
            best = (str(e), dte)
    return best if best else (None, None)


def ab_decision(obs: dict, *, now_mono: float, p: dict) -> tuple[str, str]:
    """``(action, why)`` for one observation — ``buy`` | ``wait`` | ``skip``.

    Phase 1 runs to observe_min_s and buys a bid that is rising or stable.
    A fading bid is not rejected outright: phase 2 keeps watching and takes
    it the moment the TRAILING stable window turns rising or stable, up to
    max_wait_s. That is the operator's "else wait for the bid to go up or be
    stable for 2-3 minutes".
    """
    samples = obs["samples"]                  # [(mono_ts, bid)]
    elapsed = now_mono - obs["started"]
    if len(samples) < 2:
        if elapsed > p["ab_max_wait_s"]:
            return "skip", "no usable bid samples"
        return "wait", "sampling"

    if elapsed < p["ab_observe_min_s"]:
        return "wait", f"observing {int(elapsed)}s/{p['ab_observe_min_s']}s"

    tol = p["ab_tol_pct"]
    whole = bid_trend([b for _, b in samples], tol_pct=tol)
    if elapsed <= p["ab_observe_max_s"]:
        if whole in ("rising", "stable"):
            return "buy", f"bid {whole} over {int(elapsed)}s"
        return "wait", f"bid {whole} — holding off"

    # phase 2: judge only the trailing window
    cutoff = now_mono - p["ab_stable_s"]
    recent = [b for ts, b in samples if ts >= cutoff]
    trailing = bid_trend(recent, tol_pct=tol)
    if trailing in ("rising", "stable") and len(recent) >= 2:
        return "buy", (f"bid {trailing} for the last "
                       f"{p['ab_stable_s'] // 60}m after fading")
    if elapsed > p["ab_max_wait_s"]:
        return "skip", f"bid never steadied within {p['ab_max_wait_s'] // 60}m"
    return "wait", f"bid {trailing} in the trailing window"

_WATCHERS: dict[str, dict] = {}      # user_id -> watcher record
_LOCK = threading.Lock()


class AutoTradeError(RuntimeError):
    pass


def _now_cst() -> datetime:
    return datetime.now(CST)


def _log_event(w: dict, msg: str) -> None:
    w["events"].insert(0, f"{_now_cst():%H:%M:%S} {msg}")
    del w["events"][40:]
    logger.info("auto-trade[%s]: %s", w["user_id"][:8], msg)


def _crosses(snapshot: dict | None, tickers: list[str]) -> list[dict]:
    """The tradeable crosses in a levels snapshot: one per ticker+level."""
    out = []
    for tkr in tickers:
        latest = ((snapshot or {}).get("tickers", {}).get(tkr) or {}).get("latest") or {}
        for level, s in latest.items():
            sig = (s or {}).get("signal")
            if sig in SIGNAL_SIDE:
                out.append({"ticker": tkr, "level": level, "signal": sig,
                            "time": (s or {}).get("time") or ""})
    return out


def _place(w: dict, cand: dict) -> None:
    """Confirmed candidate -> the desk's normal managed 0DTE position."""
    from app.core.database import SessionLocal
    from app.models import User
    from app.services import tradier_bot

    p = w["params"]
    side = SIGNAL_SIDE[cand["signal"]]
    use_zero_dte = p.get("zero_dte", True)
    expiration = f"{_now_cst():%Y-%m-%d}" if use_zero_dte else None
    db = SessionLocal()
    try:
        user = db.get(User, w["user_id"])
        if user is None:
            raise AutoTradeError("user vanished")
        pos = tradier_bot.open_position(
            db, user,
            symbol=cand["ticker"], side=side,
            buy_pct=p["buy_pct"], tolerance_pct=p["tolerance_pct"],
            delta_min=p["delta_min"], delta_max=p["delta_max"],
            tp_pct=p["tp_pct"], sl_pct=p["sl_pct"],
            expiration=expiration,
            min_contracts=p["min_contracts"],
            strategy=p["strategy"],
            live=p["live"],
            discount_pct=p.get("discount_pct", 0),
            zero_dte=use_zero_dte,
        )
        w["attempts"].append({
            "at": f"{_now_cst():%m-%d %H:%M:%S}", "ticker": cand["ticker"],
            "signal": cand["signal"], "side": side, "status": "placed",
            "position_id": pos.id, "occ_symbol": pos.occ_symbol,
            "contracts": pos.contracts,
        })
        _log_event(w, f"PLACED {cand['ticker']} {side.upper()} x{pos.contracts} "
                      f"({pos.occ_symbol}) from {cand['signal']}")
    except tradier_bot.TradierBotError as exc:
        skipped = "min_contracts" in str(exc)
        w["attempts"].append({
            "at": f"{_now_cst():%m-%d %H:%M:%S}", "ticker": cand["ticker"],
            "signal": cand["signal"], "side": side,
            "status": "skipped" if skipped else "failed",
            "error": str(exc)[:300],
        })
        _log_event(w, f"{'SKIPPED' if skipped else 'FAILED'} "
                      f"{cand['ticker']} {side.upper()}: {exc}")
    except Exception as exc:  # noqa: BLE001 — one bad order must not kill the watcher
        w["attempts"].append({
            "at": f"{_now_cst():%m-%d %H:%M:%S}", "ticker": cand["ticker"],
            "signal": cand["signal"], "side": side, "status": "failed",
            "error": str(exc)[:300],
        })
        _log_event(w, f"FAILED {cand['ticker']} {side.upper()}: {exc}")
    finally:
        db.close()


def _ab_signals(p: dict) -> list[dict]:
    """New-first A/B super signals for the configured tickers and books."""
    from app.core.database import SessionLocal
    from app.services import super_research

    db = SessionLocal()
    try:
        _total, rows = super_research.query_signals(
            db, central=True, days=1, limit=200)
        out = []
        for r in rows:
            tkr = (r.ticker or "").upper()
            book = (r.book or "").upper()
            direction = (r.direction or "").upper()
            if tkr not in p["tickers"] or book not in p["ab_books"]:
                continue
            if direction not in AB_SIDE:
                continue
            out.append({"ticker": tkr, "book": book, "direction": direction,
                        "side": AB_SIDE[direction],
                        "logged_at": str(r.logged_at or ""),
                        "grade": r.grade, "id": r.id})
        return out
    finally:
        db.close()


def _ab_cooldown_left(w: dict, ticker: str) -> int:
    """Seconds until this strategy may trade ``ticker`` again, 0 if it may now.

    Read from the position ledger, not watcher memory: the cooldown has to
    outlive an API restart, and the rows are the only record of what was
    actually ordered. Rejected buys do not count — an order that never made
    it onto the book should not lock the ticker out for an hour.
    """
    from datetime import timezone as _tz

    from sqlalchemy import select as _select

    from app.core.database import SessionLocal
    from app.models.tradier import TradierPosition

    p = w["params"]
    window = p["ab_cooldown_s"]
    if window <= 0:
        return 0
    now = datetime.now(_tz.utc).replace(tzinfo=None)
    cutoff = now - timedelta(seconds=window)
    db = SessionLocal()
    try:
        last = db.scalar(
            _select(TradierPosition.opened_at)
            .where(TradierPosition.user_id == w["user_id"],
                   TradierPosition.underlying == ticker,
                   TradierPosition.strategy == p["strategy"],
                   TradierPosition.status != "failed",
                   TradierPosition.opened_at >= cutoff)
            .order_by(TradierPosition.opened_at.desc())
            .limit(1)
        )
    finally:
        db.close()
    if last is None:
        return 0
    return max(0, int(window - (now - last).total_seconds()))


def _ab_open_observation(w: dict, sig: dict) -> None:
    """Pick the contract this signal would trade and start sampling its bid."""
    from app.core.database import SessionLocal
    from app.models import User
    from app.services import tradier_bot

    p = w["params"]
    now = _now_cst()
    db = SessionLocal()
    try:
        user = db.get(User, w["user_id"])
        if user is None:
            raise AutoTradeError("user vanished")
        client = tradier_bot.client_for(user, live=p["live"])
        try:
            exps = client.expirations(sig["ticker"])
            # Do not even start a 0DTE observation that cannot finish before
            # the cutoff — it would only ever end in a skip.
            latest_decision = now + timedelta(seconds=p["ab_observe_max_s"])
            allow_zero = f"{latest_decision:%H:%M}" < p["ab_zero_dte_cutoff"]
            expiration, dte = choose_expiration(
                exps, now.date(), dte_max=p["ab_dte_max"],
                allow_zero_dte=allow_zero)
            if expiration is None:
                _log_event(w, f"no expiry within {p['ab_dte_max']}d for "
                              f"{sig['ticker']} (0DTE allowed: {allow_zero}) — skipped")
                return
            chain = client.chain(sig["ticker"], expiration)
            opt = tradier_bot.pick_contract(chain, sig["side"],
                                            p["delta_min"], p["delta_max"])
            if opt is None:
                _log_event(w, f"no {sig['side']} on {sig['ticker']} {expiration} "
                              f"in delta {p['delta_min']:g}-{p['delta_max']:g} — skipped")
                return
            bid = float(opt.get("bid") or 0)
        finally:
            client.close()
    except Exception as exc:                      # noqa: BLE001
        _log_event(w, f"could not stage {sig['ticker']}: {exc}")
        return
    finally:
        db.close()

    w["observing"].append({
        "ticker": sig["ticker"], "book": sig["book"], "side": sig["side"],
        "direction": sig["direction"], "occ_symbol": opt["symbol"],
        "expiration": expiration, "dte": dte,
        "started": time.monotonic(), "samples": [(time.monotonic(), bid)],
        "opened_clock": f"{now:%H:%M:%S}",
    })
    _log_event(w, f"{sig['book']}-book {sig['direction']} {sig['ticker']} -> "
                  f"{sig['side'].upper()} {opt['symbol']} ({dte}DTE) bid {bid:.2f} "
                  f"— observing {p['ab_observe_min_s'] // 60}-"
                  f"{p['ab_observe_max_s'] // 60}m")


def _ab_place(w: dict, obs: dict, why: str) -> None:
    """A steady bid -> the desk's normal managed position on that contract."""
    from app.core.database import SessionLocal
    from app.models import User
    from app.services import tradier_bot

    p = w["params"]
    db = SessionLocal()
    try:
        user = db.get(User, w["user_id"])
        if user is None:
            raise AutoTradeError("user vanished")
        pos = tradier_bot.open_position(
            db, user,
            symbol=obs["ticker"], side=obs["side"],
            buy_pct=p["buy_pct"], tolerance_pct=p["tolerance_pct"],
            delta_min=p["delta_min"], delta_max=p["delta_max"],
            tp_pct=p["tp_pct"], sl_pct=p["sl_pct"],
            expiration=obs["expiration"],
            min_contracts=p["min_contracts"],
            strategy=p["strategy"],
            live=p["live"],
            discount_pct=p.get("discount_pct", 0),
        )
        w["attempts"].append({
            "at": f"{_now_cst():%m-%d %H:%M:%S}", "ticker": obs["ticker"],
            "signal": f"{obs['book']}-{obs['direction']}", "side": obs["side"],
            "status": "placed", "position_id": pos.id,
            "occ_symbol": pos.occ_symbol, "contracts": pos.contracts,
            "why": why,
        })
        _log_event(w, f"PLACED {obs['ticker']} {obs['side'].upper()} x{pos.contracts} "
                      f"({pos.occ_symbol}) — {why}")
    except tradier_bot.TradierBotError as exc:
        skipped = "min_contracts" in str(exc)
        w["attempts"].append({
            "at": f"{_now_cst():%m-%d %H:%M:%S}", "ticker": obs["ticker"],
            "signal": f"{obs['book']}-{obs['direction']}", "side": obs["side"],
            "status": "skipped" if skipped else "failed", "error": str(exc)[:300],
        })
        _log_event(w, f"{'SKIPPED' if skipped else 'FAILED'} {obs['ticker']}: {exc}")
    except Exception as exc:                      # noqa: BLE001
        _log_event(w, f"FAILED {obs['ticker']}: {exc}")
    finally:
        db.close()


def _run_ab(w: dict) -> None:
    """A/B super signal -> observed-bid options entry."""
    from app.core.database import SessionLocal
    from app.models import User
    from app.services import tradier_bot

    p = w["params"]
    baseline = False
    while not w["stop"].is_set():
        try:
            now = _now_cst()
            sigs = _ab_signals(p)

            # Everything already on the books when the watcher arms is
            # history, not a trigger — otherwise arming fires a burst of
            # stale entries.
            if not baseline:
                baseline = True
                w["seen"] = {(s["book"], s["ticker"], s["logged_at"]) for s in sigs}
                _log_event(w, f"armed on {'/'.join(sorted(p['ab_books']))}-book signals "
                              f"for {','.join(p['tickers'])} · 0DTE until "
                              f"{p['ab_zero_dte_cutoff']} CST, then up to "
                              f"{p['ab_dte_max']}DTE")

            for s in sigs:
                key = (s["book"], s["ticker"], s["logged_at"])
                if key in w["seen"]:
                    continue
                w["seen"].add(key)
                if any(o["ticker"] == s["ticker"] and o["side"] == s["side"]
                       for o in w["observing"]):
                    _log_event(w, f"already observing {s['ticker']} {s['side']} — ignored")
                    continue
                # Cheap gate first: no point sampling a bid for ten minutes
                # on a ticker this strategy is not allowed to enter yet.
                left = _ab_cooldown_left(w, s["ticker"])
                if left:
                    _log_event(w, f"{s['ticker']} on cooldown — {left // 60}m "
                                  f"{left % 60}s left, signal ignored")
                    continue
                _ab_open_observation(w, s)

            # sample every observation's bid, then decide
            if w["observing"]:
                db = SessionLocal()
                try:
                    user = db.get(User, w["user_id"])
                    client = tradier_bot.client_for(user, live=p["live"]) if user else None
                finally:
                    db.close()
                if client is not None:
                    try:
                        for obs in list(w["observing"]):
                            try:
                                q = client.quote(obs["occ_symbol"])
                                bid = float(q.get("bid") or 0)
                                if bid > 0:
                                    obs["samples"].append((time.monotonic(), bid))
                                    del obs["samples"][:-200]
                            except Exception as exc:      # noqa: BLE001
                                _log_event(w, f"{obs['ticker']} quote failed: {exc}")
                            action, why = ab_decision(obs, now_mono=time.monotonic(), p=p)
                            if action == "wait":
                                obs["why"] = why
                                continue
                            w["observing"].remove(obs)
                            if action == "skip":
                                w["attempts"].append({
                                    "at": f"{now:%m-%d %H:%M:%S}", "ticker": obs["ticker"],
                                    "signal": f"{obs['book']}-{obs['direction']}",
                                    "side": obs["side"], "status": "skipped",
                                    "error": why,
                                })
                                _log_event(w, f"DROPPED {obs['ticker']} — {why}")
                                continue
                            # last gates: both conditions can turn against us
                            # during the watch — the cutoff passes, or a
                            # sibling observation on this ticker just filled.
                            if obs["dte"] == 0 and f"{now:%H:%M}" >= p["ab_zero_dte_cutoff"]:
                                _log_event(w, f"DROPPED {obs['ticker']} 0DTE — past "
                                              f"{p['ab_zero_dte_cutoff']} CST cutoff")
                                continue
                            left = _ab_cooldown_left(w, obs["ticker"])
                            if left:
                                w["attempts"].append({
                                    "at": f"{now:%m-%d %H:%M:%S}", "ticker": obs["ticker"],
                                    "signal": f"{obs['book']}-{obs['direction']}",
                                    "side": obs["side"], "status": "skipped",
                                    "error": f"cooldown, {left // 60}m left",
                                })
                                _log_event(w, f"DROPPED {obs['ticker']} — cooldown, "
                                              f"{left // 60}m {left % 60}s left")
                                continue
                            _ab_place(w, obs, why)
                    finally:
                        client.close()
        except Exception as exc:                  # noqa: BLE001
            _log_event(w, f"watcher error: {exc}")
        w["stop"].wait(p["ab_sample_s"])
    _log_event(w, "stopped")


def _hot_place(w: dict, ticker: str, side: str, *, tag: str = "HOT") -> int | None:
    """Place a limit order for a HOT/SUPERHOT-scan ticker. Returns position id."""
    from app.core.database import SessionLocal
    from app.models import User
    from app.services import tradier_bot

    p = w["params"]
    discount = p.get("discount_pct", 0)
    use_zero_dte = p.get("zero_dte", True)
    expiration = f"{_now_cst():%Y-%m-%d}" if use_zero_dte else None
    db = SessionLocal()
    try:
        user = db.get(User, w["user_id"])
        if user is None:
            raise AutoTradeError("user vanished")
        pos = tradier_bot.open_position(
            db, user,
            symbol=ticker, side=side,
            buy_pct=p["buy_pct"], tolerance_pct=p["tolerance_pct"],
            delta_min=p["delta_min"], delta_max=p["delta_max"],
            tp_pct=p["tp_pct"], sl_pct=p["sl_pct"],
            expiration=expiration,
            min_contracts=p["min_contracts"],
            strategy=p["strategy"],
            live=p["live"],
            discount_pct=discount,
            cancel_after_s=1800,
            zero_dte=use_zero_dte,
        )
        w["attempts"].append({
            "at": f"{_now_cst():%m-%d %H:%M:%S}", "ticker": ticker,
            "signal": f"{tag.lower()}-{side}", "side": side, "status": "placed",
            "position_id": pos.id, "occ_symbol": pos.occ_symbol,
            "contracts": pos.contracts,
        })
        label = f"−{discount}% limit" if discount else "market"
        _log_event(w, f"PLACED {ticker} {side.upper()} x{pos.contracts} "
                      f"({pos.occ_symbol}) — {tag}, {label}")
        return pos.id
    except tradier_bot.TradierBotError as exc:
        skipped = "min_contracts" in str(exc)
        w["attempts"].append({
            "at": f"{_now_cst():%m-%d %H:%M:%S}", "ticker": ticker,
            "signal": f"{tag.lower()}-{side}", "side": side,
            "status": "skipped" if skipped else "failed",
            "error": str(exc)[:300],
        })
        _log_event(w, f"{'SKIPPED' if skipped else 'FAILED'} {ticker} {side.upper()}: {exc}")
    except Exception as exc:  # noqa: BLE001
        w["attempts"].append({
            "at": f"{_now_cst():%m-%d %H:%M:%S}", "ticker": ticker,
            "signal": f"{tag.lower()}-{side}", "side": side, "status": "failed",
            "error": str(exc)[:300],
        })
        _log_event(w, f"FAILED {ticker} {side.upper()}: {exc}")
    finally:
        db.close()
    return None


def _check_limit_retries(w: dict, signal_checker) -> None:
    """Cancel/retry logic for unfilled limit orders after 30 min.

    ``signal_checker(ticker) -> side | None`` re-evaluates whether the ticker
    still qualifies — returns the option side if yes, None if no.
    """
    from app.core.database import SessionLocal
    from app.models.tradier import TradierPosition

    tracking = w.get("limit_tracking", [])
    if not tracking:
        return
    db = SessionLocal()
    try:
        still_pending = []
        for entry in tracking:
            pos = db.get(TradierPosition, entry["position_id"])
            if pos is None:
                continue
            if pos.status == "pending" and pos.entry_price is None:
                still_pending.append(entry)
                continue
            if pos.status == "failed":
                side = signal_checker(entry["ticker"])
                if side:
                    _log_event(w, f"RETRY {entry['ticker']} — limit order "
                                  f"timed out, signal still active")
                    w.get("traded_today", set()).discard(entry["ticker"])
                else:
                    _log_event(w, f"NO RETRY {entry['ticker']} — limit timed "
                                  f"out, signal gone")
        w["limit_tracking"] = still_pending
    finally:
        db.close()


def _run_hot(w: dict) -> None:
    """HOT tickers strategy: intersect 5min and 15min HOT lists, buy at discount."""
    from app.models import User
    from app.services import hot_scan as hot_svc

    p = w["params"]
    traded_today: set[str] = set()
    w["traded_today"] = traded_today
    w["limit_tracking"] = []
    current_day: str | None = None
    while not w["stop"].is_set():
        try:
            now = _now_cst()
            today = f"{now:%Y-%m-%d}"
            hhmm = f"{now:%H:%M}"

            if current_day != today:
                current_day = today
                traded_today.clear()
                w["limit_tracking"] = []
                _log_event(w, f"armed for {today} · window "
                              f"{p['window_open']}-{p['window_close']} CST · HOT tickers")

            if hhmm >= "15:00":
                _log_event(w, "market closed (15:00 CST) — auto-shutting off")
                w["stop"].set()
                break

            if not (p["window_open"] <= hhmm < p["window_close"]):
                w["stop"].wait(p["poll_s"])
                continue

            from app.core.database import SessionLocal
            db = SessionLocal()
            try:
                user = db.get(User, w["user_id"])
                if user is None:
                    _log_event(w, "user vanished — stopping")
                    break
                snap_5 = hot_svc.snapshot(user, live=p["live"], interval="5min")
                snap_15 = hot_svc.snapshot(user, live=p["live"], interval="15min")
            finally:
                db.close()

            tickers_5 = {r["symbol"]: r["side"] for r in snap_5.get("rows", [])
                         if r.get("side")}
            tickers_15 = {r["symbol"]: r["side"] for r in snap_15.get("rows", [])
                          if r.get("side")}

            def hot_signal(ticker):
                s5 = tickers_5.get(ticker)
                s15 = tickers_15.get(ticker)
                return s5 if (s5 and s15 and s5 == s15) else None

            if p.get("discount_pct", 0) > 0:
                _check_limit_retries(w, hot_signal)

            common = set(tickers_5.keys()) & set(tickers_15.keys())
            for ticker in sorted(common):
                if ticker in traded_today:
                    continue
                side_5 = tickers_5[ticker]
                side_15 = tickers_15[ticker]
                if side_5 != side_15:
                    _log_event(w, f"skipped {ticker} — 5min={side_5} vs 15min={side_15}")
                    continue
                traded_today.add(ticker)
                _log_event(w, f"HOT intersection: {ticker} {side_5.upper()} "
                              f"(5min+15min agree)")
                pid = _hot_place(w, ticker, side_5)
                if pid and p.get("discount_pct", 0) > 0:
                    w["limit_tracking"].append({"position_id": pid, "ticker": ticker})

        except Exception as exc:  # noqa: BLE001
            _log_event(w, f"watcher error: {exc}")
        w["stop"].wait(p["poll_s"])
    _log_event(w, "stopped")


def _run_superhot(w: dict) -> None:
    """SUPERHOT tickers strategy: pick top N superhot, buy at configured discount."""
    from app.models import User
    from app.services import hot_scan as hot_svc

    p = w["params"]
    top_n = p.get("top_n", 3)
    traded_today: set[str] = set()
    w["traded_today"] = traded_today
    w["limit_tracking"] = []
    current_day: str | None = None
    while not w["stop"].is_set():
        try:
            now = _now_cst()
            today = f"{now:%Y-%m-%d}"
            hhmm = f"{now:%H:%M}"

            if current_day != today:
                current_day = today
                traded_today.clear()
                w["limit_tracking"] = []
                _log_event(w, f"armed for {today} · window "
                              f"{p['window_open']}-{p['window_close']} CST · "
                              f"SUPERHOT top {top_n}")

            if hhmm >= "15:00":
                _log_event(w, "market closed (15:00 CST) — auto-shutting off")
                w["stop"].set()
                break

            if not (p["window_open"] <= hhmm < p["window_close"]):
                w["stop"].wait(p["poll_s"])
                continue

            from app.core.database import SessionLocal
            db = SessionLocal()
            try:
                user = db.get(User, w["user_id"])
                if user is None:
                    _log_event(w, "user vanished — stopping")
                    break
                snap = hot_svc.snapshot(user, live=p["live"], interval="5min")
            finally:
                db.close()

            sh_rows = snap.get("superhot", [])[:top_n]
            sh_lookup = {r["symbol"]: r["sh_side"] for r in snap.get("superhot", [])
                         if r.get("sh_side")}

            def sh_signal(ticker):
                return sh_lookup.get(ticker)

            if p.get("discount_pct", 0) > 0:
                _check_limit_retries(w, sh_signal)

            for row in sh_rows:
                ticker = row["symbol"]
                side = row.get("sh_side")
                if not side or ticker in traded_today:
                    continue
                traded_today.add(ticker)
                _log_event(w, f"SUPERHOT #{len(traded_today)}: {ticker} "
                              f"{side.upper()} (score {row.get('sh_score', 0):.4f})")
                pid = _hot_place(w, ticker, side, tag="SUPERHOT")
                if pid and p.get("discount_pct", 0) > 0:
                    w["limit_tracking"].append({"position_id": pid, "ticker": ticker})

        except Exception as exc:  # noqa: BLE001
            _log_event(w, f"watcher error: {exc}")
        w["stop"].wait(p["poll_s"])
    _log_event(w, "stopped")


def _run(w: dict) -> None:
    from app.services import levels as levels_svc

    p = w["params"]
    baseline_day = None
    while not w["stop"].is_set():
        try:
            now = _now_cst()
            today = f"{now:%Y-%m-%d}"
            hhmm = f"{now:%H:%M}"

            if hhmm >= "15:00":
                _log_event(w, "market closed (15:00 CST) — auto-shutting off")
                w["stop"].set()
                break

            snap = levels_svc.status().get("status")
            crosses = _crosses(snap, p["tickers"])

            # a new CST day: whatever is in the snapshot predates today's
            # window, so it is baseline, not signal
            if baseline_day != today:
                baseline_day = today
                w["seen"] = {(today, c["ticker"], c["level"], c["time"])
                             for c in crosses}
                w["pending"] = []
                _log_event(w, f"armed for {today} · window "
                              f"{p['window_open']}-{p['window_close']} CST")

            # detect NEW crosses inside the window
            for c in crosses:
                key = (today, c["ticker"], c["level"], c["time"])
                if key in w["seen"]:
                    continue
                w["seen"].add(key)
                if (not (p["window_open"] <= c["time"] < p["window_close"])
                        or hhmm >= p["window_close"]):
                    _log_event(w, f"ignored {c['ticker']} {c['signal']} @ {c['time']} "
                                  f"(outside {p['window_open']}-{p['window_close']})")
                    continue
                confirm_at = time.monotonic() + p["confirm_s"]
                w["pending"].append({**c, "confirm_at": confirm_at,
                                     "confirm_clock": f"{now + timedelta(seconds=p['confirm_s']):%H:%M:%S}"})
                _log_event(w, f"candidate {c['ticker']} {c['signal']} @ {c['time']} "
                              f"— confirming at +{p['confirm_s'] // 60}m")

            # confirm due candidates against the CURRENT snapshot
            due = [x for x in w["pending"] if time.monotonic() >= x["confirm_at"]]
            for cand in due:
                w["pending"].remove(cand)
                latest = ((snap or {}).get("tickers", {}).get(cand["ticker"]) or {}
                          ).get("latest") or {}
                still = (latest.get(cand["level"]) or {}).get("signal") == cand["signal"]
                if still:
                    _place(w, cand)
                else:
                    _log_event(w, f"dropped {cand['ticker']} {cand['signal']} — signal "
                                  "changed during confirmation")
        except Exception as exc:  # noqa: BLE001
            _log_event(w, f"watcher error: {exc}")
        w["stop"].wait(p["poll_s"])
    _log_event(w, "stopped")


def start(user_id: str, *, buy_pct: float | None = None,
          tolerance_pct: float | None = None,
          tp_pct: float | None = None, sl_pct: float | None = None,
          delta_min: float | None = None, delta_max: float | None = None,
          strategy: str | None = None, tickers: str | list[str] | None = None,
          window_open: str | None = None, window_close: str | None = None,
          min_contracts: int | None = None, live: bool = False,
          books: str | list[str] | None = None,
          dte_max: int | None = None,
          zero_dte_cutoff: str | None = None,
          cooldown_min: int | None = None,
          discount_pct: float | None = None,
          top_n: int | None = None,
          zero_dte: bool = True) -> dict:
    s = get_settings()
    params = {
        "strategy": (strategy or s.tradier_auto_strategy).strip(),
        # Sandbox unless the desk explicitly armed LIVE. Never persisted:
        # a restarted watcher comes back on paper.
        "live": bool(live),
        "buy_pct": s.tradier_buy_pct if buy_pct is None else buy_pct,
        # buy_pct is a target; this is how far either side of it a whole
        # number of contracts may land (see tradier_bot.size_contracts).
        "tolerance_pct": (s.tradier_size_tolerance_pct
                          if tolerance_pct is None else tolerance_pct),
        "tp_pct": s.tradier_tp_pct if tp_pct is None else tp_pct,
        "sl_pct": s.tradier_sl_pct if sl_pct is None else sl_pct,
        "delta_min": s.tradier_delta_min if delta_min is None else delta_min,
        "delta_max": s.tradier_delta_max if delta_max is None else delta_max,
        "window_open": (window_open or s.tradier_auto_window_open).strip(),
        "window_close": (window_close or s.tradier_auto_window_close).strip(),
        "min_contracts": (s.tradier_auto_min_contracts
                          if min_contracts is None else int(min_contracts)),
        "confirm_s": s.tradier_auto_confirm_s,
        "poll_s": max(5, s.tradier_auto_poll_s),
        # --- ab_signal_options ---
        "ab_sample_s": max(5, s.tradier_ab_sample_s),
        "ab_observe_min_s": s.tradier_ab_observe_min_s,
        "ab_observe_max_s": s.tradier_ab_observe_max_s,
        "ab_stable_s": s.tradier_ab_stable_s,
        "ab_max_wait_s": s.tradier_ab_max_wait_s,
        "ab_tol_pct": s.tradier_ab_tol_pct,
        "ab_dte_max": (s.tradier_ab_dte_max if dte_max is None else int(dte_max)),
        "ab_zero_dte_cutoff": (zero_dte_cutoff
                               or s.tradier_ab_zero_dte_cutoff).strip(),
        "ab_cooldown_s": (s.tradier_ab_cooldown_s if cooldown_min is None
                          else int(cooldown_min) * 60),
        "discount_pct": discount_pct if discount_pct is not None else 0,
        "top_n": top_n if top_n is not None else 3,
        "zero_dte": bool(zero_dte),
    }
    raw_books = books if books is not None else s.tradier_ab_books
    if isinstance(raw_books, str):
        raw_books = raw_books.split(",")
    params["ab_books"] = [b.strip().upper() for b in raw_books if b.strip()]
    raw = tickers if tickers is not None else s.tradier_auto_tickers
    if isinstance(raw, str):
        raw = raw.split(",")
    params["tickers"] = [t.strip().upper() for t in raw if t.strip()]

    if params["strategy"] == "hot_tickers":
        params["delta_min"] = 0.30
        params["delta_max"] = 0.50
        if discount_pct is None:
            params["discount_pct"] = 10
        params["tickers"] = params["tickers"] or ["HOT"]

    if params["strategy"] == "super_hot_tickers":
        params["delta_min"] = 0.30
        params["delta_max"] = 0.50
        if discount_pct is None:
            params["discount_pct"] = 10
        if buy_pct is None:
            params["buy_pct"] = 30
        params["tickers"] = params["tickers"] or ["SUPERHOT"]

    if params["strategy"] not in STRATEGIES:
        raise AutoTradeError(f"unknown strategy '{params['strategy']}' "
                             f"(supported: {', '.join(STRATEGIES)})")
    if not params["tickers"]:
        raise AutoTradeError("at least one ticker is required")
    if params["strategy"] not in ("hot_tickers", "super_hot_tickers") and any(
            not re.match(r"^[A-Z0-9^.\-]{1,10}$", t) for t in params["tickers"]):
        raise AutoTradeError("tickers must be plain symbols like SPY, QQQ, SPX")
    for k in ("window_open", "window_close"):
        if not _HHMM.match(params[k]):
            raise AutoTradeError(f"{k} must be HH:MM (24h CST)")
    if params["window_open"] >= params["window_close"]:
        raise AutoTradeError("window_open must be before window_close")
    if not (0 < params["buy_pct"] <= 100):
        raise AutoTradeError("buy_pct must be in (0, 100]")
    if not (0 <= params["tolerance_pct"] <= 100):
        raise AutoTradeError("tolerance_pct must be in [0, 100]")
    if not (0 < params["delta_min"] < params["delta_max"] <= 1):
        raise AutoTradeError("need 0 < delta_min < delta_max <= 1")
    if params["min_contracts"] < 1:
        raise AutoTradeError("min_contracts must be >= 1")

    with _LOCK:
        existing = _WATCHERS.get(user_id)
        if existing and existing["thread"].is_alive() and not existing["stop"].is_set():
            existing["params"] = params
            _log_event(existing, "params updated (already armed)")
            return status(user_id)
        w = {
            "user_id": user_id,
            "params": params,
            "stop": threading.Event(),
            "seen": set(), "pending": [], "observing": [],
            "attempts": [], "events": [],
            "started_at": f"{_now_cst():%m-%d %H:%M:%S}",
        }
        # Warm every module the watcher thread imports lazily, on THIS thread,
        # before it starts. Two threads importing app.models at the same
        # moment raise _DeadlockError from Python's import lock — which kills
        # the watcher outright, silently, before its first poll.
        from app.models import User            # noqa: F401
        from app.models.tradier import TradierPosition  # noqa: F401
        from app.services import levels, super_research, tradier_bot  # noqa: F401
        from app.services import hot_scan as _hot_svc  # noqa: F401

        if params["strategy"] == "hot_tickers":
            loop = _run_hot
        elif params["strategy"] == "super_hot_tickers":
            loop = _run_superhot
        else:
            loop = _run
        w["thread"] = threading.Thread(target=loop, args=(w,), daemon=True,
                                       name=f"autotrade-{user_id[:8]}")
        _WATCHERS[user_id] = w
        w["thread"].start()
    return status(user_id)


def stop(user_id: str) -> dict:
    with _LOCK:
        w = _WATCHERS.get(user_id)
        if w:
            w["stop"].set()
    return status(user_id)


def defaults() -> dict:
    """What the arm form should prefill (Settings, env TBOT_TRADIER_*)."""
    s = get_settings()
    return {
        "strategy": s.tradier_auto_strategy,
        "strategies": list(STRATEGIES),
        "tickers": s.tradier_auto_tickers,
        "window_open": s.tradier_auto_window_open,
        "window_close": s.tradier_auto_window_close,
        "buy_pct": s.tradier_buy_pct,
        "tolerance_pct": s.tradier_size_tolerance_pct,
        "tp_pct": s.tradier_tp_pct,
        "sl_pct": s.tradier_sl_pct,
        "min_contracts": s.tradier_auto_min_contracts,
        "confirm_s": s.tradier_auto_confirm_s,
        "live": False,
        "books": s.tradier_ab_books,
        "dte_max": s.tradier_ab_dte_max,
        "zero_dte_cutoff": s.tradier_ab_zero_dte_cutoff,
        "cooldown_min": s.tradier_ab_cooldown_s // 60,
        "observe_min_s": s.tradier_ab_observe_min_s,
        "observe_max_s": s.tradier_ab_observe_max_s,
        "stable_s": s.tradier_ab_stable_s,
        "discount_pct": 0,
        "top_n": 3,
    }


def status(user_id: str) -> dict:
    w = _WATCHERS.get(user_id)
    if w is None:
        return {"active": False, "defaults": defaults()}
    p = w["params"]
    return {
        "active": w["thread"].is_alive() and not w["stop"].is_set(),
        "started_at": w["started_at"],
        "params": {k: v for k, v in p.items()},
        "strategy": p["strategy"],
        "window": f"{p['window_open']}-{p['window_close']} CST",
        "tickers": p["tickers"],
        "pending": [{k: x[k] for k in ("ticker", "signal", "time", "confirm_clock")}
                    for x in w["pending"]],
        # contracts whose bid is being watched before committing
        "observing": [{
            "ticker": o["ticker"], "side": o["side"], "book": o["book"],
            "direction": o["direction"], "occ_symbol": o["occ_symbol"],
            "expiration": o["expiration"], "dte": o["dte"],
            "since": o["opened_clock"], "samples": len(o["samples"]),
            "bid": (o["samples"][-1][1] if o["samples"] else None),
            "first_bid": (o["samples"][0][1] if o["samples"] else None),
            "why": o.get("why", "sampling"),
        } for o in w.get("observing", [])],
        "attempts": w["attempts"][-20:],
        "events": w["events"][:12],
        "paper": get_settings().paper_only,
        "defaults": defaults(),
    }
