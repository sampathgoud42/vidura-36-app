"""The luck bot: the daily long-shot ticket, on demand.

Same construction as the 18:01 ticket -- scan every live market including
sub-events, keep what clears the bar, rank by dollar volume, take the top N
and buy the lot as one combined contract. The difference is only who asks for
it and when: this one is driven from the desk, previewed before it spends
anything, and confirmed by hand.

The SELECTION is not reimplemented here. The scanner lives in the runtime
parlay bot, and a second copy of "which markets are live and tradeable" would
drift from the scheduled ticket the first time either was touched -- and the
whole point of a preview is that it shows what the real thing will do.

Preview and place are separate calls with a cached hand-off, because a scan
takes a minute or two and nobody should sit through it twice to confirm one
order.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_RUNTIME = None

# A preview waiting to be confirmed. Held in memory on purpose: it is a
# proposal, not a record, and an unconfirmed one is worth nothing tomorrow.
_PREVIEWS: dict[str, dict] = {}
PREVIEW_TTL_S = 900


def _runtime():
    """The parlay bot's own scanner, imported once."""
    global _RUNTIME
    if _RUNTIME is not None:
        return _RUNTIME
    from app.core.config import get_settings

    root = get_settings().source_repo
    sports_dir = root / "prediction-trade" / "kalshi" / "sports"
    if str(sports_dir) not in sys.path:
        sys.path.insert(0, str(sports_dir))
    spec = importlib.util.spec_from_file_location(
        "parley_runtime", str(sports_dir / "v2_bot_kalshi_parley.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("parley_runtime", module)
    spec.loader.exec_module(module)
    _RUNTIME = module
    return module


def _sweep() -> None:
    now = time.time()
    for key in [k for k, v in _PREVIEWS.items() if v["expires"] < now]:
        _PREVIEWS.pop(key, None)


def preview(cred, *, min_legs: int = 5, max_legs: int = 24,
            min_leg_c: int = 60, min_volume_usd: float = 0.0,
            sports: list[str] | None = None) -> dict:
    """Choose the legs and describe them. Buys nothing, creates nothing.

    Returns a token the caller passes back to `place`. Nothing is created on
    the exchange here -- not even the combined market -- so a preview nobody
    confirms leaves no trace.
    """
    from app.domains.botstation.parley import engine, filters
    from app.domains.botstation.parley.models import ComboOrder

    runtime = _runtime()
    markets, scores = runtime._load_markets(
        cred, sports or [], include_sub_events=True)

    frac = max(1, int(min_leg_c)) / 100.0
    candidates, _rejected = filters.eligible_legs(
        markets, scores=scores, tracker=filters.PositionTracker(),
        tennis_min=frac, other_min=frac, soccer_min=frac)

    floor = max(0.0, float(min_volume_usd))
    if floor:
        candidates = [c for c in candidates if c.market.volume_usd >= floor]

    collection, candidates = runtime._daily_collection(cred, candidates)
    if not collection:
        return {"ok": False,
                "detail": "no open collection can host these legs"}

    candidates.sort(key=lambda c: (c.market.volume_usd, c.market.volume),
                    reverse=True)
    picked = candidates[:max(2, int(max_legs))]
    if len(picked) < int(min_legs):
        return {"ok": False, "scanned": len(markets),
                "detail": f"only {len(picked)} legs clear the bar, "
                          f"{min_legs} required"}

    combo = ComboOrder(legs=picked, allow_same_event=True)
    token = uuid.uuid4().hex
    _sweep()
    _PREVIEWS[token] = {
        "expires": time.time() + PREVIEW_TTL_S,
        "tickers": [c.ticker for c in picked],
        "collection": collection,
    }
    return {
        "ok": True,
        "token": token,
        "scanned": len(markets),
        "eligible": len(candidates),
        "collection": collection,
        "probability": round(combo.combined_probability, 6),
        "fair_c": engine.theoretical_price_c(combo),
        "legs": [{"ticker": c.ticker,
                  "outcome": c.market.outcome or c.ticker,
                  "market": c.market.title or c.ticker,
                  "event": c.market.event_ticker or "",
                  "sport": c.market.sport,
                  "price_c": c.market.yes_bid_c,
                  "volume_usd": round(c.market.volume_usd, 2)}
                 for c in picked],
        "expires_in_s": PREVIEW_TTL_S,
    }


def place(cred, token: str, *, tenant_slug: str = "",
          tickers: list[str] | None = None,
          min_usd: float = 5.0, max_usd: float = 7.5,
          min_legs: int = 5) -> dict:
    """Buy the previewed combo. Real money.

    Re-reads the board rather than trusting the preview's prices: a minute has
    passed, a leg may have moved or stopped being live, and buying a parlay on
    a price that no longer exists is the failure a preview is meant to
    prevent, not cause.
    """
    from app.domains.botstation.parley import engine, filters
    from app.domains.botstation.parley.models import ComboOrder

    _sweep()
    held = _PREVIEWS.get(token)
    if held is None:
        return {"placed": False,
                "detail": "that preview has expired -- take a fresh one"}

    # The operator may deselect legs. They may NEVER add one: a confirmation
    # that can introduce a leg is not a confirmation of what was shown, and
    # this endpoint spends money on whatever it is handed.
    offered = set(held["tickers"])
    if tickers is None:
        wanted = offered
    else:
        chosen = {t.strip() for t in tickers if t and t.strip()}
        unknown = chosen - offered
        if unknown:
            return {"placed": False,
                    "detail": f"{len(unknown)} leg(s) were not in the "
                              f"preview; take a fresh one"}
        wanted = chosen
    if len(wanted) < int(min_legs):
        return {"placed": False,
                "detail": f"{len(wanted)} legs selected, {min_legs} required"}

    runtime = _runtime()
    markets, scores = runtime._load_markets(cred, [], include_sub_events=True)
    # The price bar is deliberately wide here: these legs already passed it
    # once. What is being re-checked is that they are still LIVE and still
    # quoted, not whether they would be chosen again.
    candidates, _ = filters.eligible_legs(
        [m for m in markets if m.ticker in wanted], scores=scores,
        tracker=filters.PositionTracker(),
        tennis_min=0.01, other_min=0.01, soccer_min=0.01)

    if len(candidates) < int(min_legs):
        return {"placed": False,
                "detail": f"only {len(candidates)} of the previewed legs are "
                          f"still tradeable, {min_legs} required"}

    stake = max(0.01, float(min_usd))
    ceiling = max(stake, float(max_usd))
    escalation = round((ceiling / stake - 1.0) * 100.0, 2)

    picked = list(candidates)
    outcome: dict[str, Any] | None = None
    for _ in range(12):
        combo = ComboOrder(legs=picked, allow_same_event=True)
        try:
            outcome = engine.place_combo(
                cred, combo, held["collection"], dry_run=False,
                stake_usd=stake, escalation_pct=escalation,
                # AT MARKET, within the dollar range. The regular parlays
                # haggle -- they refuse a quote above fair value plus a few
                # cents -- because there they are hunting value. This is a
                # lottery ticket: what is being bought is $5 to $7.50 of it,
                # and the price only decides how many contracts that is.
                # Spending stays bounded by the stake either way, so the
                # ceiling would only ever turn a fill into no fill.
                slippage_c=engine.MAX_COMBO_PRICE_C)
            break
        except Exception as exc:                        # noqa: BLE001
            # The exchange names legs that say the same thing; drop the
            # thinner one and try again. Same rule the scheduled ticket uses.
            named = runtime._redundant_legs(str(exc))
            clash = [c for c in picked if c.ticker in named]
            if not named or len(clash) < 2 or len(picked) <= int(min_legs):
                return {"placed": False, "detail": str(exc)}
            drop = min(clash, key=lambda c: c.market.volume_usd)
            picked = [c for c in picked if c.ticker != drop.ticker]
            logger.info("luck: dropped %s as redundant (%d legs left)",
                        drop.ticker, len(picked))

    if outcome is None:
        return {"placed": False,
                "detail": "could not assemble a combo the exchange accepts"}

    # Spent, so the token is done whatever happened next -- a preview must
    # never be able to buy twice.
    _PREVIEWS.pop(token, None)
    if outcome.get("placed") and tenant_slug:
        from app.domains.botstation.ledger import entries
        entries.record_entry(
            tenant_slug=tenant_slug, bot_key="luck", bot_version="v1",
            ticker=outcome.get("combo_ticker") or "",
            external_id=(outcome.get("quote_id")
                         or outcome.get("order_id") or ""),
            contracts=outcome.get("contracts"),
            entry_price_c=outcome.get("filled_c") or outcome.get("limit_c"),
            is_live=True, raw=outcome)
    return {**outcome, "legs_used": len(picked)}


# ---- jobs -----------------------------------------------------------------
#
# A full scan takes over two minutes -- 48,000 markets across ~1,000 series --
# and the desk reaches this API through a Cloudflare tunnel that cuts an
# origin request at about 100 seconds. Holding the HTTP request open for the
# work therefore CANNOT be made to succeed by raising a timeout: the proxy
# ends it whatever the browser and the server agree between themselves.
#
# So the request starts the work and returns an id. The desk polls. This also
# means a reload mid-scan does not lose it, and the confirm step -- which
# scans again and may sit through a 60s stake escalation -- gets the same
# treatment for the same reason.
_JOBS: dict[str, dict] = {}
JOB_TTL_S = 1800


def _sweep_jobs() -> None:
    now = time.time()
    for key in [k for k, v in _JOBS.items()
                if v.get("done_at") and v["done_at"] + JOB_TTL_S < now]:
        _JOBS.pop(key, None)


def _run_job(job_id: str, fn, *args, **kwargs) -> None:
    try:
        result = fn(*args, **kwargs)
        _JOBS[job_id].update(status="done", result=result, done_at=time.time())
    except Exception as exc:                            # noqa: BLE001
        logger.warning("luck job %s failed: %s: %s",
                       job_id, type(exc).__name__, exc)
        _JOBS[job_id].update(status="failed", error=str(exc),
                             done_at=time.time())


def start(fn, *args, **kwargs) -> str:
    """Run one luck-bot call in the background. Returns its id."""
    import threading

    _sweep_jobs()
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {"status": "running", "started": time.time(),
                     "result": None, "error": None, "done_at": None}
    thread = threading.Thread(target=_run_job,
                              args=(job_id, fn, *args), kwargs=kwargs,
                              daemon=True)
    thread.start()
    return job_id


def job(job_id: str) -> dict | None:
    held = _JOBS.get(job_id)
    if held is None:
        return None
    out = {"status": held["status"],
           "elapsed_s": round(time.time() - held["started"], 1)}
    if held["status"] == "done":
        out["result"] = held["result"]
    elif held["status"] == "failed":
        out["error"] = held["error"]
    return out
