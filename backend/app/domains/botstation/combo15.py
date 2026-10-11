"""The fifteen-minute combo: one parlay across Kalshi's quarter-hour markets,
crypto and commodities alike, on the sides the Bot Station's DMI boards point.

Every fifteen-minute series a combo collection hosts is offered for the
quarter trading now -- one leg each, CALL as YES and PUT as NO -- and ticked
by default when all of these hold:

  * its DMI was read from a bar that began no more than FRESH_S ago;
  * its signal is CALL or PUT, not mixed;
  * that side's bid is within BID_MIN_C-BID_MAX_C, inclusive;
  * that side is no wider than MAX_SPREAD_C;
  * its quarter has more than MIN_SECONDS_LEFT to run.

Everything else is listed unticked, with the reason. A market whose signal
gives it no side, or whose quarter the collection does not host, cannot be
ticked at all; the rest can, by hand. The stake is one number,
DEFAULT_STAKE_USD unless changed, at most MAX_STAKE_USD, spent at the market
through the same RFQ the other combos use.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

FRESH_S = 5 * 60
BID_MIN_C, BID_MAX_C = 35, 90
MAX_SPREAD_C = 5
MIN_SECONDS_LEFT = 60
DEFAULT_STAKE_USD = 5.0
MAX_STAKE_USD = 99.0
BOT_KEY = "combo15"

_FIFTEEN = re.compile(r"^KX[A-Z]+15M$")


def _parse(stamp) -> datetime | None:
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def hosted_series(collection: dict) -> dict[str, set[str]]:
    """series -> the fifteen-minute events this collection hosts."""
    out: dict[str, set[str]] = {}
    for event in (collection or {}).get("events") or ():
        series = str(event).split("-", 1)[0]
        if _FIFTEEN.match(series):
            out.setdefault(series, set()).add(event)
    return out


def _collection(cred) -> dict | None:
    """The open collection hosting the most fifteen-minute events."""
    from app.domains.botstation.parley import engine

    best, best_n = None, 0
    for found in engine.open_collections(cred):
        n = sum(len(events) for events in hosted_series(found).values())
        if n > best_n:
            best, best_n = found, n
    return best


def _boards(tradier_cred) -> dict[str, dict]:
    """series -> the DMI row the Bot Station shows for it: the same cached
    snapshots the strips read, so the form agrees with the screen."""
    from app.domains.botstation import signal_trade
    from app.domains.trading.market import commodities, crypto

    rows: list[dict] = []
    for read in (lambda: crypto.snapshot(),
                 lambda: commodities.snapshot(tradier_cred, sandbox=True)):
        try:
            rows += read().get("rows") or []
        except Exception as exc:                        # noqa: BLE001
            logger.info("combo15: a DMI board did not answer: %s", type(exc).__name__)
    out: dict[str, dict] = {}
    for row in rows:
        spec = signal_trade.market_for(str(row.get("bot") or ""))
        if spec is not None:
            out[spec.series] = row
    return out


def _label(series: str) -> tuple[str, str, int]:
    """(label, category, catalogue order) -- the catalogue's, else the
    ticker's own name for a series it does not list (platinum, palladium)."""
    from app.domains.botstation import monitor

    for order, market in enumerate(monitor.MARKETS):
        if market.series == series:
            return market.label, market.category, order
    return series[2:-3].title(), "commodities", len(monitor.MARKETS)


def preview(cred, *, tradier_cred=None, now: float | None = None) -> dict:
    """Every fifteen-minute market a combo can hold right now, with its side,
    its quote, how fresh its DMI is, and whether it is ticked by default."""
    from app.domains.botstation import signal_trade, venue

    collection = _collection(cred)
    if collection is None:
        return {"ok": False,
                "detail": "no combo collection hosts fifteen-minute markets right now"}
    hosted = hosted_series(collection)
    boards = _boards(tradier_cred)
    now = time.time() if now is None else now
    legs = []
    client = venue._client(cred)
    try:
        for series in sorted(hosted, key=lambda s: (_label(s)[2], s)):
            label, category, _order = _label(series)
            row = boards.get(series) or {}
            signal = (row.get("signal") or "").strip().lower() or None
            side = signal_trade.SIDE_FOR.get(signal or "")
            bar_time = row.get("bar_time")
            dmi_age = int(now - bar_time) if isinstance(bar_time, (int, float)) else None
            leg = {"series": series, "label": label, "category": category,
                   "signal": signal, "confirms": bool(row.get("m5_confirms")),
                   "side": side, "dmi_age_s": dmi_age, "ticker": None,
                   "event": None, "bid_c": None, "ask_c": None, "spread_c": None,
                   "left_s": None, "selectable": False, "default": False, "why": []}
            legs.append(leg)
            try:
                market = signal_trade.current_market(client, series)
            except Exception as exc:                    # noqa: BLE001
                leg["why"].append(f"Kalshi did not answer ({type(exc).__name__})")
                continue
            if market is None:
                leg["why"].append("no quarter open")
                continue
            close = _parse(market.get("close_time"))
            left = (close.timestamp() - now) if close else 0
            bid, ask = signal_trade.side_quote(market, side or "yes")
            leg.update(ticker=market.get("ticker"), event=market.get("event_ticker"),
                       bid_c=bid, ask_c=ask, left_s=int(left),
                       spread_c=(round(ask - bid, 1)
                                 if bid is not None and ask is not None else None))
            hosted_here = leg["event"] in hosted[series]
            if not hosted_here:
                leg["why"].append("this quarter is not in the combo collection")
            if side is None:
                leg["why"].append("mixed signal" if row else "no DMI signal")
            if dmi_age is None:
                leg["why"].append("DMI time unknown")
            elif dmi_age > FRESH_S:
                leg["why"].append(f"DMI {dmi_age // 60}m{dmi_age % 60:02d}s old")
            if bid is None or ask is None:
                leg["why"].append("not quoted")
            else:
                if not BID_MIN_C <= bid <= BID_MAX_C:
                    leg["why"].append(f"bid {bid:g}c outside {BID_MIN_C}-{BID_MAX_C}c")
                if ask - bid > MAX_SPREAD_C:
                    leg["why"].append(f"{ask - bid:g}c wide")
            if left <= MIN_SECONDS_LEFT:
                leg["why"].append(f"closes in {max(0, int(left))}s")
            leg["selectable"] = bool(hosted_here and side and bid is not None
                                     and ask is not None and left > MIN_SECONDS_LEFT)
            leg["default"] = leg["selectable"] and not leg["why"]
    finally:
        client.close()
    return {"ok": True, "collection": collection.get("collection_ticker"),
            "legs": legs, "stake_usd": DEFAULT_STAKE_USD,
            "max_stake_usd": MAX_STAKE_USD,
            "rule": {"fresh_s": FRESH_S, "bid_min_c": BID_MIN_C,
                     "bid_max_c": BID_MAX_C, "max_spread_c": MAX_SPREAD_C}}


# One answer per (operator, confirmation key): a double click or a retried
# request gets the first answer back rather than a second combo.
_ANSWERS: dict[tuple[str, str], dict] = {}
_PLACING = threading.Lock()


def place(cred, *, legs: list[dict], stake_usd: float, key: str, owner: str,
          tenant_slug: str = "") -> dict:
    """Buy the ticked legs as one combo, spending up to ``stake_usd``."""
    with _PLACING:
        held = _ANSWERS.get((owner, key))
        if held is not None:
            return {**held, "repeat": True}
        answer = _place(cred, legs=legs, stake_usd=stake_usd, key=key,
                        tenant_slug=tenant_slug)
        _ANSWERS[(owner, key)] = answer
        return answer


def _place(cred, *, legs: list[dict], stake_usd: float, key: str,
           tenant_slug: str) -> dict:
    from app.domains.botstation import signal_trade, venue
    from app.domains.botstation.parley import engine
    from app.domains.botstation.parley.models import (MAX_COMBO_LEGS,
                                                      ComboCandidate,
                                                      ComboOrder, MarketState)

    stake = float(stake_usd or 0)
    if not 0 < stake <= MAX_STAKE_USD:
        return {"placed": False,
                "detail": f"the stake must be above $0 and at most ${MAX_STAKE_USD:.0f}"}
    picks: dict[str, str] = {}
    for leg in legs or []:
        ticker = str(leg.get("ticker") or "").strip()
        side = str(leg.get("side") or "").strip().lower()
        if not _FIFTEEN.match(ticker.split("-", 1)[0]) or side not in ("yes", "no"):
            return {"placed": False, "detail": f"{ticker or 'a leg'} is not a "
                                               "fifteen-minute market on YES or NO"}
        picks[ticker] = side
    if not 2 <= len(picks) <= MAX_COMBO_LEGS:
        return {"placed": False,
                "detail": f"a combo takes 2 to {MAX_COMBO_LEGS} legs, not {len(picks)}"}

    now = time.time()
    chosen = []
    client = venue._client(cred)
    try:
        for ticker, side in picks.items():
            raw = signal_trade._market(client, ticker)
            close = _parse((raw or {}).get("close_time"))
            if not raw or close is None or close.timestamp() - now <= MIN_SECONDS_LEFT:
                return {"placed": False,
                        "detail": f"{ticker} has closed or is about to -- build again"}
            state = MarketState.from_kalshi(raw, sport="fifteen-minute", live=True)
            if side == "no":
                state = state.as_no()
                if state is None:
                    return {"placed": False, "detail": f"{ticker} is not quoted on NO"}
            chosen.append(ComboCandidate(market=state))
    finally:
        client.close()

    collection = _collection(cred)
    hosted = {e for events in hosted_series(collection).values() for e in events}
    if not collection or any(c.event_ticker not in hosted for c in chosen):
        return {"placed": False,
                "detail": "the combo collection no longer hosts every leg -- build again"}
    try:
        outcome = engine.place_combo(
            cred, ComboOrder(legs=chosen), collection["collection_ticker"],
            dry_run=False, stake_usd=stake, escalation_pct=0.0,
            # At the market, within the stake: the RFQ is sized in dollars,
            # so the price decides how many contracts the stake buys.
            slippage_c=engine.MAX_COMBO_PRICE_C,
            idempotency_key=f"c15-{key}"[:64])
    except Exception as exc:                            # noqa: BLE001
        logger.warning("combo15 refused: %s", exc)
        return {"placed": False, "detail": f"Kalshi did not take the combo: {exc}"[:300]}
    if outcome.get("placed") and tenant_slug:
        from app.domains.botstation.ledger import entries

        entries.record_entry(
            tenant_slug=tenant_slug, bot_key=BOT_KEY, bot_version="v1",
            ticker=outcome.get("combo_ticker") or "",
            external_id=(outcome.get("quote_id") or outcome.get("order_id")
                         or f"c15-{key}"),
            contracts=outcome.get("contracts"),
            entry_price_c=outcome.get("filled_c") or outcome.get("limit_c"),
            is_live=True, raw=outcome)
    return {**outcome, "legs_used": len(chosen)}


# ---- placing in the background ---------------------------------------------
# A combo is several Kalshi round trips -- each leg re-read, the collection,
# the combo market, an RFQ that waits up to six seconds for a maker, the
# accept, the fill read back -- and on a slow afternoon that ran past the
# browser's 30 seconds. The phone then gave up and said the API was down
# while the order was still being worked. So the request only STARTS the
# job and returns; the sheet asks for the answer until it is there. The
# job is keyed by the confirmation's key, so a second tap or a retry finds
# the job already running instead of starting another.
_JOBS: dict[tuple[str, str], dict] = {}
_JOBS_LOCK = threading.Lock()
JOB_KEEP_S = 30 * 60


def _public(job: dict) -> dict:
    out = {"job": job["key"], "status": job["status"],
           "elapsed_s": round((job.get("ended") or time.time()) - job["started"], 1)}
    if job["status"] == "done":
        out["result"] = job["result"]
    return out


def start_place(cred, *, legs: list[dict], stake_usd: float, key: str, owner: str,
                tenant_slug: str = "") -> dict:
    """Start placing the combo and return at once: {job, status, ...}."""
    now = time.time()
    with _JOBS_LOCK:
        for k in [k for k, j in _JOBS.items() if now - j["started"] > JOB_KEEP_S]:
            _JOBS.pop(k, None)
        job = _JOBS.get((owner, key))
        if job is not None:
            return _public(job)
        job = {"key": key, "status": "running", "started": now, "result": None}
        _JOBS[(owner, key)] = job

    def run() -> None:
        try:
            result = place(cred, legs=legs, stake_usd=stake_usd, key=key,
                           owner=owner, tenant_slug=tenant_slug)
        except Exception as exc:                        # noqa: BLE001
            logger.warning("combo15 job failed: %s: %s", type(exc).__name__, exc)
            result = {"placed": False, "detail": f"the combo could not be placed: {exc}"[:300]}
        with _JOBS_LOCK:
            job.update(status="done", result=result, ended=time.time())

    threading.Thread(target=run, name=f"combo15-{key[:8]}", daemon=True).start()
    return _public(job)


def job_status(owner: str, key: str) -> dict | None:
    with _JOBS_LOCK:
        job = _JOBS.get((owner, key))
        return _public(job) if job is not None else None


def reset_for_tests() -> None:
    _ANSWERS.clear()
    _JOBS.clear()
