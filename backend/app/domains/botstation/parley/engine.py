"""The parlay engine: live markets in, combined orders out.

One pass is: read what we already hold, read what is in play, filter it down
to legs worth having, partition those into disjoint parlays, turn each parlay
into a real combined market at the exchange, and buy it.

Two things about that last step are easy to get wrong and expensive:

  A parlay is ONE contract.  Buying five legs as five contracts is five
  independent bets that each pay on their own. A combined market pays only if
  every leg resolves YES -- the product -- at correspondingly longer odds.
  They are different trades with the same legs, so the combination is created
  through the collection endpoint rather than assembled from single orders.

  A new combined market is BORN EMPTY.  Nothing quotes it. Its bid and ask
  come back at zero, which is not a cheap price, it is no market at all. A
  market order into that book fills nothing -- the safe outcome, but only if
  you expect it. So this engine rests a LIMIT at the theoretical price instead
  of sending a market order into a book it can see is empty.

Everything reachable here is gated on ``dry_run`` by default. Nothing about
the analysis needs the account, so the whole pass can be inspected before it
is ever allowed to trade.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

from app.domains.botstation.parley import combos as combinator
from app.domains.botstation.parley import filters
from app.domains.botstation.parley.models import (ComboOrder, MarketState,
                                                  TennisScoreState)

logger = logging.getLogger(__name__)

# What we will pay OVER fair value, in cents. This is the whole difference
# between a combo that trades and one that does not: makers quote a combo
# above its theoretical price, because they are taking correlation risk the
# product-of-legs figure ignores. A live quote on a 71c parlay came back at
# 76c -- five cents over -- and a 2c ceiling declined it, which is what a 2c
# ceiling will do to almost every quote.
#
# It was also unreachable. place_combo accepted the argument and nothing ever
# passed one, so the engine ran on this constant no matter what the operator
# set.
DEFAULT_SLIPPAGE_C = 5

# What one parlay may spend, in dollars, unless the launch form says
# otherwise. A budget rather than a contract count because a parlay's price
# swings with its legs: the same "5 contracts" is $4.55 on a 91c combo and
# $2.25 on a 45c one, so a fixed count is a different bet every pass.
DEFAULT_STAKE_USD = 5.0

# How long to wait for a maker to answer an RFQ, and how often to look.
# Combos are High Volatility Markets, where Kalshi allows a 3s confirmation
# window and a 1s execution timer -- so a few seconds is generous, and
# waiting longer only ages the leg prices the combo was built from.
QUOTE_WAIT_S = 6.0
QUOTE_POLL_S = 0.75

# How long a parlay is given to execute before the stake is raised, and by how
# much it may rise in total. A maker who will not fill $12 sometimes fills a
# larger ticket -- the spread they earn is on size, and a request too small to
# be worth answering is simply left alone.
#
# The ceiling is on the WHOLE escalation, not on each step: 30% of $12 is
# $15.60 and that is where it stops, whatever happens next. A budget that can
# creep is not a budget.
DEFAULT_ESCALATION_PCT = 30.0
DEFAULT_FILL_WAIT_S = 60.0


def stake_ladder(stake_usd: float, escalation_pct: float) -> list[float]:
    """The stakes to try, in order. Always starts at the operator's number.

    Two rungs, not a smooth climb: the point is one honest retry at a bigger
    size, not an auction against ourselves. Rounded to the cent, because that
    is the unit the exchange takes and a fraction of one is not a real
    difference.
    """
    base = round(float(stake_usd), 2)
    pct = max(0.0, float(escalation_pct))
    if pct <= 0:
        return [base]
    top = round(base * (1.0 + pct / 100.0), 2)
    return [base] if top <= base else [base, top]

# A combined market cheaper than this is not worth the fees to hold.
MIN_COMBO_PRICE_C = 2
# And one this expensive has almost no upside left.
MAX_COMBO_PRICE_C = 95


@dataclass
class PassResult:
    """Everything one pass did, and everything it declined to do."""

    candidates: list = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    combos: list[ComboOrder] = field(default_factory=list)
    placed: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    dry_run: bool = True

    def summary(self) -> dict:
        return {
            "eligible_legs": len(self.candidates),
            "rejected_legs": len(self.rejected),
            "dry_run": self.dry_run,
            "placed": len(self.placed),
            "skipped": len(self.skipped),
            **combinator.summarise(self.combos),
        }


def theoretical_price_c(combo: ComboOrder) -> int:
    """Fair value of the parlay in cents: the product of its legs.

    The number to rest a limit at when nothing is quoting. It assumes the legs
    are independent, which is precisely what refusing two legs from one event
    buys us -- without that rule this figure would be optimistic in exactly
    the cases where it matters.
    """
    # ComboOrder.cost_c is this same figure; kept as one calculation so the
    # cost an operator reads and the limit actually sent can never diverge.
    return combo.cost_c


# Discovered collections, cached. The set Kalshi publishes changes slowly and
# each one costs a request to describe, so re-reading it every pass would be
# ~100 calls for an answer that is the same all afternoon.
_COLLECTIONS: tuple[float, list[dict]] | None = None
_COLLECTION_TTL_S = 900


def open_collections(cred, *, force: bool = False) -> list[dict]:
    global _COLLECTIONS

    import time

    if not force and _COLLECTIONS and time.time() - _COLLECTIONS[0] < _COLLECTION_TTL_S:
        return _COLLECTIONS[1]
    from app.domains.botstation import venue as kalshi

    try:
        found = kalshi.open_collections(cred)
    except Exception as exc:                            # noqa: BLE001
        logger.info("collection discovery failed: %s", type(exc).__name__)
        return _COLLECTIONS[1] if _COLLECTIONS else []
    _COLLECTIONS = (time.time(), found)
    return found


def legs_in_collection(chosen: dict, candidates: list) -> list:
    """The legs this collection can actually host.

    A collection that lists no events hosts everything -- Kalshi leaves the
    field empty on the broad cross-category ones rather than enumerating a few
    thousand tickers.
    """
    events = (chosen or {}).get("events")
    if events is None:
        return list(candidates)
    return [c for c in candidates if (c.event_ticker or c.ticker) in events]


def choose_collection(collections: list[dict], candidates: list) -> dict | None:
    """The collection that can host the most of these legs.

    Chosen, never configured. A combined market can only be built from events
    its collection lists, so a parlay assembled from the best legs on the
    board usually fits NO collection -- the legs have to be picked inside one.

    Kalshi publishes a handful of cross-sport collections carrying thousands
    of events and a long tail of single-game ones carrying three. Ranking by
    how many of THIS pass's legs each can host lands on the broad one when the
    legs are spread across sports, and on a single-game one when they are not,
    without either being named anywhere.
    """
    best, best_n = None, 0
    for collection in collections:
        events = collection.get("events") or set()
        n = sum(1 for c in candidates
                if (c.event_ticker or c.ticker) in events)
        if n > best_n:
            best, best_n = collection, n
    if best is None or best_n < max(2, int(best.get("size_min") or 2)):
        return None
    return best


def build_pass(markets: list[MarketState],
               scores: dict[str, TennisScoreState] | None = None,
               held_positions: list[dict] | None = None,
               *, min_legs: int = combinator.MIN_LEGS,
               max_legs: int = combinator.MAX_LEGS,
               max_combos: int | None = None,
               min_lead: int = filters.MIN_SET_LEAD,
               tennis_min: float = filters.TENNIS_MIN_PROBABILITY,
               other_min: float = filters.DEFAULT_MIN_PROBABILITY,
               soccer_min: float = filters.SOCCER_MIN_PROBABILITY,
               max_leg: float = filters.MAX_LEG_PROBABILITY,
               max_hours: int = filters.MAX_HOURS_TO_EXPIRY,
               max_spread_c: int = filters.MAX_SPREAD_C) -> PassResult:
    """Everything up to, but not including, touching the account.

    Separated from placement so the whole decision can be tested and shown to
    an operator without an account, a network, or any risk of a trade.
    """
    tracker = filters.PositionTracker.from_positions(held_positions or [])
    candidates, rejected = filters.eligible_legs(
        markets, scores=scores, tracker=tracker, min_lead=min_lead,
        tennis_min=tennis_min, other_min=other_min, soccer_min=soccer_min,
        max_leg=max_leg, max_hours=max_hours, max_spread_c=max_spread_c)
    # Built as a unit. The real size depends on the limit price, which is
    # only known once the combo exists, so place_combo does the sizing.
    built = combinator.build_combos(
        candidates, min_legs=min_legs, max_legs=max_legs,
        max_combos=max_combos)
    return PassResult(candidates=candidates, rejected=rejected,
                      combos=combinator.rank(built))


# The smallest size the exchange accepts: contracts_fp takes 0.01-contract
# increments, so anything below this rounds to nothing.
MIN_CONTRACTS = 0.01


def contracts_for(stake_usd: float, limit_c: int) -> float:
    """How many contracts a dollar budget buys at this price.

    FRACTIONAL, to the exchange's 0.01-contract increment. Whole contracts
    were leaving most of the budget unspent -- $5 at 89c bought 5 and left
    55c behind -- and a budget that silently rounds down to a different bet
    every pass is the thing dollar sizing was meant to remove. The fills that
    work on this account are all fractional for the same reason.

    Rounded DOWN. The stake is a ceiling on what one parlay may cost, so
    rounding up to reach it would spend more than the operator authorised.

    Zero is a real answer. When the parlay costs more than the whole stake
    there is no honest size to send, and the caller must decline rather than
    buy anyway.
    """
    stake_c = float(stake_usd) * 100.0
    if limit_c <= 0:
        return 0.0
    # floor to 2dp without importing math for one call
    size = int(stake_c / limit_c * 100) / 100.0
    return size if size >= MIN_CONTRACTS else 0.0


def place_combo(cred, combo: ComboOrder, collection: str, *,
                dry_run: bool = True,
                stake_usd: float = DEFAULT_STAKE_USD,
                slippage_c: int = DEFAULT_SLIPPAGE_C,
                escalation_pct: float = DEFAULT_ESCALATION_PCT,
                fill_wait_s: float = DEFAULT_FILL_WAIT_S,
                idempotency_key: str | None = None) -> dict:
    """Create the combined market for a parlay and rest a buy against it.

    Returns what happened, including when nothing did. "No fill" is an
    ordinary outcome here rather than an error: an empty book is the normal
    state of a market that was created seconds ago.
    """
    from app.domains.botstation import venue as kalshi

    legs = [{"event_ticker": leg.event_ticker or leg.ticker,
             "market_ticker": leg.ticker, "side": "yes"} for leg in combo.legs]
    fair_c = theoretical_price_c(combo)
    limit_c = min(MAX_COMBO_PRICE_C, fair_c + slippage_c)
    count = contracts_for(stake_usd, limit_c)

    # Sized BEFORE the combined market is created. Creating an instrument on
    # the exchange is a side effect, and doing it for a parlay we then decline
    # to buy leaves a market nobody asked for behind.
    if count < MIN_CONTRACTS:
        return {"placed": False, "collection": collection,
                "tickers": combo.tickers, "theoretical_c": fair_c,
                "limit_c": limit_c, "stake_usd": stake_usd, "contracts": 0,
                "detail": f"${stake_usd:.2f} does not cover the "
                          f"{MIN_CONTRACTS} contract minimum at {limit_c}c"}
    # The combo carries its own size so the pass summary an operator reads
    # reports what was actually sent, not the placeholder it was built with.
    combo.contracts = count

    if dry_run:
        return {"placed": False, "dry_run": True, "collection": collection,
                "tickers": combo.tickers, "theoretical_c": fair_c,
                "limit_c": limit_c, "contracts": count, "stake_usd": stake_usd,
                "detail": f"dry run — would buy {count:g} x {limit_c}c "
                          f"(${count * limit_c / 100:.2f})"}

    market = kalshi.combined_market(cred, collection, legs)
    ticker = market.get("ticker")
    if not ticker:
        return {"placed": False, "tickers": combo.tickers,
                "detail": "the exchange did not return a combined market"}

    # What the book actually looks like, rather than what the quote fields
    # imply. A newly created combo has no book at all, and its ask reads 0.
    book = {}
    try:
        book = kalshi.orderbook(cred, ticker)
    except Exception:                                   # noqa: BLE001
        logger.info("no order book for %s yet", ticker)
    has_asks = bool(book.get("no_dollars") or book.get("no"))

    if limit_c < MIN_COMBO_PRICE_C:
        return {"placed": False, "combo_ticker": ticker,
                "tickers": combo.tickers, "theoretical_c": fair_c,
                "detail": f"fair value {fair_c}c is below the "
                          f"{MIN_COMBO_PRICE_C}c floor — not worth the fees"}

    base = {"combo_ticker": ticker, "tickers": combo.tickers,
            "theoretical_c": fair_c, "limit_c": limit_c,
            "contracts": count, "stake_usd": stake_usd,
            "book_had_asks": has_asks}

    # ASK FOR A PRICE FIRST. Nothing quotes a freshly created combined
    # market, so a limit into it rests against an empty book until it
    # expires -- which is what every parley order has done. An RFQ is the
    # mechanism for a market with no book, and it is what the combo buys on
    # this account that actually executed went through.
    #
    # Then, if nobody answers, ONE retry at a larger stake. A maker who will
    # not fill $12 sometimes fills $15.60: the spread they earn is on size,
    # and a request too small to be worth answering is left alone rather than
    # refused. The wait between the two is what "not executed for 60 seconds"
    # means -- an unanswered RFQ is withdrawn before the next is raised, so
    # only ever one stands at a time.
    ladder = stake_ladder(stake_usd, escalation_pct)
    for rung, stake in enumerate(ladder):
        sized = contracts_for(stake, limit_c)
        if sized < MIN_CONTRACTS:
            continue
        quote = _take_quote(cred, ticker, stake, limit_c,
                            {**base, "contracts": sized, "stake_usd": stake})
        if quote is not None:
            if rung:
                logger.info("filled on the raised stake: $%.2f (from $%.2f)",
                            stake, ladder[0])
            return quote
        if rung + 1 < len(ladder):
            # Whatever is left of the 60s, not 60s on top of the time the
            # quote wait already spent.
            remaining = max(0.0, fill_wait_s - QUOTE_WAIT_S)
            logger.info("no fill at $%.2f; waiting %.0fs then trying $%.2f",
                        stake, remaining, ladder[rung + 1])
            time.sleep(remaining)

    # Nothing took it at any size. Rest the limit at the largest size tried:
    # an order nobody takes costs nothing, and the book may fill in later.
    stake_usd = ladder[-1]
    count = max(count, contracts_for(stake_usd, limit_c))
    combo.contracts = count
    base = {**base, "contracts": count, "stake_usd": stake_usd}
    order = kalshi.place_order(
        cred, ticker=ticker, count=count, side="yes", action="buy",
        order_type="limit", price_c=limit_c,
        client_order_id=idempotency_key or str(uuid.uuid4()))

    return {**base, "placed": True,
            "cost_usd": round(count * limit_c / 100, 2),
            "order_id": order.get("order_id") or order.get("id"),
            "detail": ("no quote; resting a limit into an empty book"
                       if not has_asks else "no quote; resting a limit")}


def _take_quote(cred, ticker: str, stake_usd: float, limit_c: int,
                base: dict) -> dict | None:
    """Ask makers for a price and take it if it beats the limit.

    Returns the outcome when a quote was accepted, else None so the caller
    falls back to resting an order. Never raises: a broken RFQ must not cost
    us the ordinary path.

    The RFQ is sized in DOLLARS. That is both what the endpoint takes and
    what the working fills on this account look like -- the exchange derives
    the fractional contract count from the amount, which is why they are
    numbers like 34.11 rather than a round lot.
    """
    from app.domains.botstation import venue as kalshi

    rfq_id = None
    try:
        rfq_id = kalshi.request_quote(cred, ticker, stake_usd)
        if not rfq_id:
            return None
        deadline = time.monotonic() + QUOTE_WAIT_S
        best = None
        while time.monotonic() < deadline:
            time.sleep(QUOTE_POLL_S)
            for q in kalshi.quotes_for(cred, rfq_id):
                if (q.get("status") or "open") != "open":
                    continue
                cost_c = kalshi.buy_yes_cost_c(q)
                if cost_c is None:
                    continue
                if best is None or cost_c < best[0]:
                    best = (cost_c, q)
            if best is not None:
                break

        if best is None:
            logger.info("no maker quoted %s within %gs", ticker, QUOTE_WAIT_S)
            # WITHDRAWN, not abandoned. An RFQ we walk away from stays open on
            # the account, and a pass that leaks one every ten minutes leaves
            # hundreds standing -- each one an outstanding request to spend the
            # stake, against an account that has to be able to afford them.
            kalshi.cancel_quote_request(cred, rfq_id)
            return None

        cost_c, q = best
        # The same ceiling the limit order would have used. A quote is only
        # worth taking if it is at least as good; otherwise resting is
        # strictly better. This is also what stops an RFQ from becoming a way
        # to pay more than the engine authorised.
        if cost_c > limit_c:
            logger.info("best quote on %s is %dc, above the %dc limit",
                        ticker, cost_c, limit_c)
            kalshi.cancel_quote_request(cred, rfq_id)
            return None

        logger.info("accepting a quote on %s: %dc (limit %dc), $%.2f",
                    ticker, cost_c, limit_c, stake_usd)
        kalshi.accept_quote(cred, rfq_id, q.get("id"), kalshi.BUY_YES_ACCEPTS)

        # What the fill ACTUALLY was, read back from the exchange. The size
        # was never ours to decide -- an RFQ is sized in dollars and the
        # count follows from the price it clears at -- so the request is the
        # wrong number to report and the wrong number to book.
        filled_n, filled_cost, filled_fees = None, None, None
        # Retried, because the position does not appear the instant the quote
        # is accepted -- the first read comes back empty and the ledger then
        # records the size we ASKED for, which is the number this read-back
        # exists to replace.
        for _ in range(4):
            try:
                held = kalshi.position_for(cred, ticker) or {}
                filled_n = float(held.get("position_fp") or 0) or None
                filled_cost = float(held.get("total_traded_dollars") or 0) or None
                filled_fees = float(held.get("fees_paid_dollars") or 0) or None
            except Exception:                           # noqa: BLE001
                logger.info("filled, but the position could not be read back")
                break
            if filled_n:
                break
            time.sleep(1.0)

        paid_c = (round(filled_cost / filled_n * 100, 2)
                  if filled_n and filled_cost else cost_c)
        return {**base, "placed": True, "via": "rfq",
                "quote_id": q.get("id"), "rfq_id": rfq_id,
                "quoted_c": cost_c,
                "filled_c": paid_c,
                "contracts": filled_n if filled_n else base.get("contracts"),
                "cost_usd": round(filled_cost or stake_usd, 2),
                "fees_usd": filled_fees,
                "detail": f"accepted a quote at {cost_c}c "
                          f"(limit was {limit_c}c); filled "
                          f"{filled_n or '?'} at {paid_c}c"}
    except Exception as exc:                            # noqa: BLE001
        logger.warning("RFQ on %s failed (%s: %s); falling back to a limit",
                       ticker, type(exc).__name__, exc)
        if rfq_id:
            kalshi.cancel_quote_request(cred, rfq_id)
        return None


def run_pass(cred, markets: list[MarketState],
             scores: dict[str, TennisScoreState] | None = None,
             *, collection: str | None = None, dry_run: bool = True,
             stake_usd: float = DEFAULT_STAKE_USD,
             slippage_c: int = DEFAULT_SLIPPAGE_C,
             escalation_pct: float = DEFAULT_ESCALATION_PCT,
             fill_wait_s: float = DEFAULT_FILL_WAIT_S,
             max_per_event: int = filters.DEFAULT_MAX_PER_EVENT,
             ignore_tickers: set[str] | None = None,
             max_combos: int | None = 1,
             min_legs: int = combinator.MIN_LEGS,
             max_legs: int = combinator.MAX_LEGS,
             min_lead: int = filters.MIN_SET_LEAD,
             tennis_min: float = filters.TENNIS_MIN_PROBABILITY,
             other_min: float = filters.DEFAULT_MIN_PROBABILITY,
             soccer_min: float = filters.SOCCER_MIN_PROBABILITY,
             max_leg: float = filters.MAX_LEG_PROBABILITY,
             max_hours: int = filters.MAX_HOURS_TO_EXPIRY,
             max_spread_c: int = filters.MAX_SPREAD_C) -> PassResult:
    """One full pass: decide, then place.

    Positions are read from the exchange rather than from a local file, so a
    fill that happened while this process was not running still excludes its
    event. Trusting a local ledger for that is how the same match ends up in
    two parlays after a restart.
    """
    from app.domains.botstation import venue as kalshi

    held: list[dict] = []
    try:
        held = kalshi.positions(cred)
    except Exception:                                   # noqa: BLE001
        # Refuse rather than proceed blind: without knowing what is held, the
        # deduplication guarantee is gone, and doubling up on an event is the
        # specific harm this engine is built to avoid.
        logger.warning("parley: positions unavailable; not trading this pass")
        return PassResult(rejected=[{"ticker": "*",
                                     "reason": "positions unavailable — "
                                               "cannot guarantee no overlap"}],
                          dry_run=dry_run)

    # Positions this pass is not answerable for. The daily long-shot ticket
    # and the regular parlays keep separate books on purpose: the long shot
    # deliberately re-uses matches the regular engine has already backed, and
    # counting them against each other would let one starve the other. Each
    # pass therefore ignores the other's combos rather than pretending they
    # are not there.
    skip = {t for t in (ignore_tickers or set()) if t}
    if skip:
        held = [r for r in held if str(r.get("ticker") or "") not in skip]
    tracker = filters.PositionTracker.from_positions(held, max_per_event)

    # A held COMBO is one ticker in that list and says nothing about what is
    # inside it, so the tracker above sees a parlay it cannot read. Expanded
    # here, every leg of every open parlay counts as taken -- which is the
    # rule this engine exists to keep: one event, one position. Without it a
    # side already sitting in an open parlay is a free candidate for the next
    # one, and Real Madrid ends up in three of them.
    #
    # If ANY combo cannot be read, the pass stops. A partially expanded
    # tracker is worse than none: it looks authoritative and silently permits
    # exactly the overlap being guarded against.
    try:
        for row in held:
            try:
                if abs(float(row.get("position_fp") or 0)) <= 0:
                    continue
            except (TypeError, ValueError):
                continue
            legs = kalshi.combo_legs(cred, str(row.get("ticker") or ""))
            if legs:
                tracker.add_legs(legs)
    except Exception:                                   # noqa: BLE001
        logger.warning("parley: a held combo could not be read; "
                       "not trading this pass")
        return PassResult(rejected=[{"ticker": "*",
                                     "reason": "a held combo's legs could "
                                               "not be read — cannot "
                                               "guarantee no overlap"}],
                          dry_run=dry_run)

    candidates, rejected = filters.eligible_legs(
        markets, scores=scores, tracker=tracker, min_lead=min_lead,
        tennis_min=tennis_min, other_min=other_min, soccer_min=soccer_min,
        max_leg=max_leg, max_hours=max_hours, max_spread_c=max_spread_c)

    # Which collection can host these legs. Legs are then narrowed to that
    # collection's events BEFORE the combinator runs, because a combo built
    # from legs no collection carries is a combo that cannot be placed --
    # and finding that out after building it wastes the pass.
    chosen = None
    if collection:
        chosen = {"collection_ticker": collection, "events": None,
                  "size_min": min_legs, "size_max": max_legs}
    else:
        chosen = choose_collection(open_collections(cred), candidates)

    if chosen is None:
        result = PassResult(candidates=candidates, rejected=rejected,
                            dry_run=dry_run)
        result.skipped = [{"detail": "no open collection can host these legs"}]
        return result

    events = chosen.get("events")
    if events is not None:
        hosted = [c for c in candidates
                  if (c.event_ticker or c.ticker) in events]
        rejected += [{"ticker": c.ticker,
                      "reason": f"not in collection "
                                f"{chosen['collection_ticker']}"}
                     for c in candidates if c not in hosted]
        candidates = hosted

    # The collection's own size limits bound the combo, not just ours.
    lo = max(min_legs, int(chosen.get("size_min") or min_legs))
    hi = min(max_legs, int(chosen.get("size_max") or max_legs) or max_legs)
    built = combinator.build_combos(candidates, min_legs=lo, max_legs=hi,
                                    max_combos=max_combos)
    result = PassResult(candidates=candidates, rejected=rejected,
                        combos=combinator.rank(built), dry_run=dry_run)
    collection = chosen["collection_ticker"]
    logger.info("collection %s hosts %d of the eligible legs",
                collection, len(candidates))

    for combo in result.combos:
        try:
            outcome = place_combo(cred, combo, collection, dry_run=dry_run,
                                  stake_usd=stake_usd,
                                  slippage_c=slippage_c,
                                  escalation_pct=escalation_pct,
                                  fill_wait_s=fill_wait_s)
        except Exception as exc:                        # noqa: BLE001
            result.skipped.append({"tickers": combo.tickers,
                                   "detail": f"{type(exc).__name__}: {exc}"})
            continue
        (result.placed if outcome.get("placed") else result.skipped).append(outcome)

    return result
