"""Which live legs are allowed into a parlay, and which are refused.

Two different bars, deliberately:

    tennis        >= 90% implied AND a specific match state
    everything    >= 91% implied
    else

Tennis gets the lower price bar because it is the one sport where the score
itself tells you the favourite is nearly home. A player who has taken the
first set and leads the second by two games has to be broken AND then lose a
tiebreak-or-better run to lose the match; the price and the scoreboard are
saying the same thing twice. No other sport here has a state that
independently confirms the quote, so those pay a point more in price for the
privilege of being taken on the quote alone.

The filters all REFUSE rather than adjust. A leg one cent under the bar is not
nudged in, and a match one game short of the lead is not admitted because it
is close. That is the same rule the order path follows everywhere else in this
system, and for the same reason: a threshold that bends is not a threshold.
"""

from __future__ import annotations

import collections

import logging

from app.domains.botstation.parley.models import (ComboCandidate, MarketState,
                                                  TennisScoreState)

logger = logging.getLogger(__name__)

# Implied-probability floors, as fractions of 1. One bar for everything, with
# soccer set lower on its own: a soccer market at 82c is a side genuinely
# ahead, while the same price in a two-player sport usually means the match is
# still live in a way the odds have not settled on.
DEFAULT_MIN_PROBABILITY = 0.85
SOCCER_MIN_PROBABILITY = 0.80
SOCCER_SPORTS = {"soccer", "football (soccer)"}

# Tennis keeps its own name for the floor even though it now shares the common
# one, because the SCORE condition still applies to it and nothing else. The
# price bar and the state bar are separate rules that happen to move together.
TENNIS_MIN_PROBABILITY = DEFAULT_MIN_PROBABILITY

# And a ceiling. Above this the outcome is effectively decided: a 99c leg adds
# almost nothing to a parlay's probability while still costing 99c of the
# combined price, so five of them buy a 5% return for five ways to be wrong.
# A ceiling is the knob a floor cannot substitute for -- raising the floor
# admits MORE near-certainties, not fewer.
MAX_LEG_PROBABILITY = 0.98

# How far ahead the favourite must be in the set now being played.
MIN_SET_LEAD = 2

# How many OPEN parlays may ride on the same match at once. One means a match
# is spent the moment it enters a parlay; higher lets a strong side back a few
# tickets without concentrating the book on it. Every parlay sharing a match
# wins or loses together, so this is a direct dial on correlated risk -- which
# is why it is a number an operator sets rather than a constant.
DEFAULT_MAX_PER_EVENT = 2

TENNIS_SPORTS = {"tennis", "atp", "wta", "itf"}

# A tennis leg bid ABOVE this is taken on the price alone.
#
# The bar is a floor to beat, not a level to reach: at 93 the first acceptable
# bid is 94, the same reading as the ">59 cents" the launch form uses.
#
# The reasoning is that tennis is the one sport whose filters can refuse a leg
# the market has already decided. A 96c favourite is refused for having no
# live score -- three HTTP calls that only happen for legs above the 90% bar
# -- or for a 4c spread that says nothing at all about a set-and-a-break
# lead. Above this price the quote IS the evidence, so the price bar, the
# spread and the score requirement are all waived.
#
# NOT waived: the expiry horizon, and nothing structural. A 96c leg on a
# tournament outright closing in three weeks would hold the whole parlay's
# capital for three weeks, which is the one thing a long horizon costs and
# the price cannot argue with. Nor may a locked leg double up on an event
# the book already holds -- that guarantee is what makes a parlay's legs
# independent, and no price buys an exemption from it.
TENNIS_LOCK_C = 93

# How far ahead a leg may close. A parlay pays nothing until its LAST leg
# resolves, so one leg three weeks out holds the whole combo -- and the other
# legs' capital -- for three weeks.
#
# 72 rather than 24, measured rather than chosen: Kalshi's close_ts sits well
# after the event, so a game played TODAY closes in ~55h and the earliest
# close across a full scan of live legs was 49.8h. A 24h horizon admitted
# nothing whatsoever. 72h is the smallest value that takes today's and
# tomorrow's fixtures while still excluding a Vuelta stage market that closes
# on 12 September.
MAX_HOURS_TO_EXPIRY = 72

# The widest bid/ask we will cross. A wide market is one that does not know:
# we pay the ask and could only sell at the bid, so a leg starts underwater by
# the spread, and on a parlay that cost compounds across every leg.
MAX_SPREAD_C = 3


def within_expiry_horizon(market, *, hours: int = MAX_HOURS_TO_EXPIRY,
                          now=None) -> tuple[bool, str]:
    """Does this close soon enough to be worth tying capital up for.

    Measured on close_ts. A stage-race market can report an expected
    expiration of today and a CLOSE two weeks out; the close is when the leg
    resolves and the money comes back, so the close is what a parlay horizon
    has to be measured against.
    """
    from datetime import datetime, timezone

    raw = market.closes_at
    if not raw:
        # Unknown, so refused. An unreadable close time is the one case where
        # guessing "soon" risks locking a combo up indefinitely.
        return False, "no close time on this market"
    try:
        expires = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return False, f"close time {raw!r} could not be read"
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    ahead = (expires - (now or datetime.now(timezone.utc))).total_seconds() / 3600
    if ahead > hours:
        return False, (f"closes in {ahead:.1f}h, beyond the {hours}h horizon")
    return True, f"closes in {ahead:.1f}h"


def within_spread(market, *, max_c: int = MAX_SPREAD_C) -> tuple[bool, str]:
    """Is the market tight enough to cross."""
    spread = market.spread_c
    if spread is None:
        return False, "not quoted on both sides"
    if spread > max_c:
        return False, (f"{market.yes_bid_c}/{market.yes_ask_c} is {spread}c "
                       f"wide; {max_c}c is the limit")
    return True, f"{spread}c spread"


def is_tennis(sport: str) -> bool:
    return (sport or "").strip().lower() in TENNIS_SPORTS


def is_soccer(sport: str) -> bool:
    return (sport or "").strip().lower() in SOCCER_SPORTS


def minimum_probability(sport: str) -> float:
    return (SOCCER_MIN_PROBABILITY if is_soccer(sport)
            else DEFAULT_MIN_PROBABILITY)


def meets_odds_floor(market: MarketState, minimum: float | None = None,
                     ceiling: float = MAX_LEG_PROBABILITY) -> tuple[bool, str]:
    """Is the quote confident enough. Returns (ok, why not).

    Measured on the BID. The ask is what you would pay and always sits above
    the bid, so testing the ask would let a leg in on a price nobody is
    actually offering -- a wide market quoted 85/95 would pass an ask test at
    91 while the real consensus is 85.
    """
    floor = minimum if minimum is not None else minimum_probability(market.sport)
    if not market.live:
        return False, "the event is not in play"
    if market.completed:
        return False, "the event has finished"
    probability = market.implied_probability
    if probability is None:
        return False, "no bid — the market is not quoted"
    if market.yes_ask_c is None:
        return False, "no ask — the market cannot be bought"
    if probability < floor:
        return False, (f"implied {probability:.0%} is below the "
                       f"{floor:.0%} floor for {market.sport}")
    if probability > ceiling:
        return False, (f"implied {probability:.0%} is above the "
                       f"{ceiling:.0%} ceiling — the outcome is already "
                       f"decided and the leg adds cost, not probability")
    return True, ""


def verify_tennis_conditions(
        score: TennisScoreState,
        min_lead: int = MIN_SET_LEAD) -> tuple[bool, str]:
    """Is this player far enough ahead to be parlay material.

    Exactly two states qualify, and both are "a set up with nothing conceded,
    and clear in the next one":

        1-0 in sets   and leading set 2 by >= min_lead games
        2-0 in sets   and leading set 3 by >= min_lead games

    Anything else is refused with the reason. Notably NOT qualifying:

      * level on sets, however big the lead in the current set -- a break up
        in the first set is not a won match
      * 2-1 in sets: a lead, but against an opponent who has already taken a
        set, which is not the 2-0 this is priced for
      * a set up but only one game ahead -- one break back levels it
      * a set up and BEHIND in the next one, which is the shape of a comeback
        in progress and the most expensive way to be wrong here
      * a match already decided, where there is nothing left to win

    ``sets_won`` is the count of sets ALREADY TAKEN, and the set in progress
    is ``len(games) - 1``. Those two have to agree: a player with one set won
    should be playing the second, and if the feed says otherwise the state is
    not something to trade on.
    """
    if score.completed:
        return False, "the match is over"
    if not score.live:
        return False, "the match is not in play"

    sets_won = score.sets_won
    if sets_won not in (1, 2):
        if sets_won == 0:
            return False, "no set won yet — a lead inside set 1 is not a lead"
        return False, f"{sets_won} sets won is outside the two states this bets on"

    # The opponent must have taken NOTHING. The two states this trades are
    # "1 set completed" and "2 sets completed" -- 1-0 and 2-0 -- so 1-1 and
    # 2-1 are both out, and they are out for different reasons worth keeping
    # apart: 1-1 is level, while 2-1 is a lead but against someone who has
    # already shown they can take a set off this player. Deliberately NOT
    # generalised to "ahead on sets": widening a rule that decides which
    # trades fire is a trading change, and this one would admit the middle of
    # a five-setter at the same price as a straight-sets rout.
    #
    # Tested before the set index, because at 1-1 the match is legitimately in
    # set 3 and reporting that as an inconsistent scoreboard would call an
    # ordinary match a data fault.
    if score.opponent_sets_won > 0:
        return False, (f"{sets_won}-{score.opponent_sets_won} in sets — this "
                       f"bets on 1-0 and 2-0 only; the opponent has a set")

    # Which set should be in progress: the number COMPLETED by either player,
    # not the number this one has won. Using sets_won alone made every match
    # where the opponent had taken a set look inconsistent.
    expected_index = sets_won + score.opponent_sets_won
    current = score.current_set_index
    if current != expected_index:
        return False, (f"{sets_won}-{score.opponent_sets_won} in sets puts the "
                       f"match in set {expected_index + 1}, but the feed is on "
                       f"set {current + 1}; the scoreboard is inconsistent")

    lead = score.lead_in(current)
    if lead < min_lead:
        return False, (f"leading set {current + 1} by {lead:+d} game(s); "
                       f"{min_lead} required")

    return True, (f"{sets_won}-{score.opponent_sets_won} in sets, "
                  f"{score.games_in(current)}-{score.opponent_games_in(current)} "
                  f"in set {current + 1}")


class PositionTracker:
    """What this operator is already exposed to.

    A parlay leg on an event we already hold is not a second bet, it is more
    of the first one -- the same outcome deciding both -- and the point of a
    parlay is that its legs are independent. So exposure is tracked by EVENT
    as well as by ticker: holding the favourite in a match rules out that
    whole match, not merely that one ticker.

    Fed from three places, because a position becomes real in stages: the
    exchange knows about fills, the local ledger knows about combos we have
    sent, and the combinator has to know about legs it has already used in
    THIS pass before any of that lands.
    """

    def __init__(self) -> None:
        # COUNTS, not membership. The rule is no longer "never twice" but
        # "at most N open parlays may ride on the same match", so the tracker
        # has to know how many rather than whether.
        self._tickers: collections.Counter[str] = collections.Counter()
        self._events: collections.Counter[str] = collections.Counter()
        self.max_per_event = DEFAULT_MAX_PER_EVENT

    @classmethod
    def from_positions(cls, positions: list[dict],
                       max_per_event: int = DEFAULT_MAX_PER_EVENT
                       ) -> PositionTracker:
        """Build from Kalshi's /portfolio/positions.

        Only rows with contracts actually held count. A flat row is history,
        and excluding markets we have merely TOUCHED would shrink the
        universe every day until nothing qualified.
        """
        tracker = cls()
        tracker.max_per_event = max(1, int(max_per_event))
        for row in positions or []:
            try:
                held = abs(float(row.get("position_fp") or 0))
            except (TypeError, ValueError):
                held = 0.0
            if held > 0:
                tracker.add(str(row.get("ticker") or ""))
        return tracker

    def add(self, ticker: str, event_ticker: str = "") -> None:
        ticker = (ticker or "").strip()
        if not ticker:
            return
        self._tickers[ticker] += 1
        event = (event_ticker or "").strip()
        if not event and ticker.count("-") >= 2:
            event = ticker.rsplit("-", 1)[0]
        if event:
            self._events[event] += 1

    def add_combo(self, tickers: list[str]) -> None:
        for ticker in tickers:
            self.add(ticker)

    def add_legs(self, legs: list[dict]) -> None:
        """Mark every leg of a held combo as taken.

        The event ticker comes from the exchange rather than from splitting
        the market ticker: the split is a good guess and this is not a place
        to guess, because a leg wrongly parsed is a leg that can be sold
        twice in two different parlays.
        """
        for leg in legs or []:
            self.add(str(leg.get("market_ticker") or ""),
                     str(leg.get("event_ticker") or ""))

    def count_for(self, market: MarketState) -> int:
        """How many open parlays already ride on this match.

        The EVENT is what counts, not the ticker. Two legs on the same match
        -- Real Madrid to win and Malaga to win -- are the same question
        asked twice, and both fail together, so they cannot be treated as
        separate exposures however different their tickers look.
        """
        return max(self._tickers.get(market.ticker, 0),
                   self._events.get(market.event_ticker or "", 0))

    def holds(self, market: MarketState) -> bool:
        """True when this match has reached its allowance."""
        return self.count_for(market) >= self.max_per_event

    def blocks(self, market: MarketState) -> str:
        """Why this market is excluded, or "" if it is not."""
        n = self.count_for(market)
        if n >= self.max_per_event:
            return (f"{market.event_ticker or market.ticker} is already in "
                    f"{n} open parlays, the limit is {self.max_per_event}")
        return ""

    def __len__(self) -> int:
        return len(self._tickers)


def eligible_legs(markets: list[MarketState],
                  scores: dict[str, TennisScoreState] | None = None,
                  tracker: PositionTracker | None = None,
                  *, min_lead: int = MIN_SET_LEAD,
                  tennis_min: float = TENNIS_MIN_PROBABILITY,
                  other_min: float = DEFAULT_MIN_PROBABILITY,
                  soccer_min: float = SOCCER_MIN_PROBABILITY,
                  max_leg: float = MAX_LEG_PROBABILITY,
                  max_hours: int = MAX_HOURS_TO_EXPIRY,
                  max_spread_c: int = MAX_SPREAD_C,
                  tennis_needs_score: bool = True,
                  tennis_lock_c: int | None = TENNIS_LOCK_C,
                  now=None
                  ) -> tuple[list[ComboCandidate], list[dict]]:
    """Every market that may become a leg, and why the rest were refused.

    Returns (candidates, rejections). The rejections are returned rather than
    logged away because "nothing qualified tonight" and "everything was one
    cent short" look identical from the outside, and the operator needs to be
    able to tell.

    ``tennis_needs_score`` is the one sport-specific rule in here, and it is
    optional because it does not mean the same thing to every caller. A
    regular parlay buys a 90c tennis leg as a near-certainty, so the price
    alone is not enough and the live score has to agree. The long-shot ticket
    buys a 65c leg AS a gamble at a bar it set itself -- there the rule
    silently removes tennis from the board, since scores are only ever read
    for legs that already clear the 90% bar.

    ``tennis_lock_c`` is the price above which a tennis leg is taken on the
    quote alone -- see the constant. None turns it off, which is what the
    long-shot ticket wants: it is buying cheap legs on purpose and a waiver
    that also waives its price CEILING would let 99c legs into a combo whose
    whole point is the payout.
    """
    scores = scores or {}
    tracker = tracker or PositionTracker()
    candidates: list[ComboCandidate] = []
    rejected: list[dict] = []

    # Highest probability first, so that when two markets from one event both
    # qualify the stronger one is the leg that is kept.
    ordered = sorted(markets,
                     key=lambda m: (m.implied_probability or 0.0), reverse=True)
    seen_events: set[str] = set()

    for market in ordered:
        blocked = tracker.blocks(market)
        if blocked:
            rejected.append({"ticker": market.ticker, "reason": blocked})
            continue

        event = market.event_ticker or market.ticker
        if event in seen_events:
            rejected.append({"ticker": market.ticker,
                             "reason": f"another leg already covers {event}"})
            continue

        # A tennis leg the market has already decided. Everything below that
        # judges the QUOTE -- the price bar, the spread, the score that has
        # to agree with the price -- is skipped, because at this bid the
        # quote is the evidence they were standing in for. The two checks
        # above are not skipped and neither is the horizon below: those are
        # about the book's shape, not the leg's odds.
        locked = (tennis_lock_c is not None
                  and is_tennis(market.sport)
                  and (market.yes_bid_c or 0) > int(tennis_lock_c))

        if not locked:
            floor = (soccer_min if is_soccer(market.sport)
                     else tennis_min if is_tennis(market.sport) else other_min)
            ok, why = meets_odds_floor(market, floor, ceiling=max_leg)
            if not ok:
                rejected.append({"ticker": market.ticker, "reason": why})
                continue

        ok, why = within_expiry_horizon(market, hours=max_hours, now=now)
        if not ok:
            rejected.append({"ticker": market.ticker, "reason": why})
            continue

        if locked:
            seen_events.add(event)
            candidates.append(ComboCandidate(
                market=market,
                reason=f"tennis bid {market.yes_bid_c}c, above the "
                       f"{tennis_lock_c}c lock — priced in"))
            continue

        ok, why = within_spread(market, max_c=max_spread_c)
        if not ok:
            rejected.append({"ticker": market.ticker, "reason": why})
            continue

        reason = f"implied {market.implied_probability:.0%}"
        score_state = None
        if is_tennis(market.sport):
            score_state = scores.get(market.ticker)
            if score_state is None:
                if tennis_needs_score:
                    rejected.append({
                        "ticker": market.ticker,
                        "reason": "tennis leg with no live score — the price "
                                  "alone is not enough at the 90% bar"})
                    continue
            else:
                ok, why = verify_tennis_conditions(score_state,
                                                   min_lead=min_lead)
                # A score that CONTRADICTS the price still refuses the leg,
                # whoever is asking. The option is about needing a score, not
                # about ignoring one we have.
                if not ok:
                    rejected.append({"ticker": market.ticker, "reason": why})
                    continue
                reason = f"implied {market.implied_probability:.0%}; {why}"

        seen_events.add(event)
        candidates.append(ComboCandidate(market=market, reason=reason,
                                         score_state=score_state))

    return candidates, rejected
