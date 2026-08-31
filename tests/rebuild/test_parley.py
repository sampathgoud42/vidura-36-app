"""Parley v2: which legs qualify, and how they are bundled.

The rules under test, as specified:

    tennis        >= 90% implied AND (1-0 in sets leading set 2 by >= 2 games,
                  or 2-0 in sets leading set 3 by >= 2 games)
    other sports  >= 91% implied
    combos        2 to 5 legs, DISJOINT: no ticker and no EVENT twice, and
                  nothing already held

Two of these are easy to get subtly wrong in ways no error would report, so
they get the most attention here:

  The score gate is not the price gate. A tennis market at 96% whose player is
  only one game clear must be refused -- otherwise the score condition is
  decorative and the real rule is just "96%".

  Disjointness is by EVENT, not ticker. Two markets on one match are the same
  question asked twice; a parlay holding both is one bet at worse odds that
  loses every leg together, while looking diversified.
"""

from __future__ import annotations

import pytest

from app.domains.botstation.parley import combos as combinator
from app.domains.botstation.parley import filters
from app.domains.botstation.parley.models import (ComboCandidate, ComboOrder,
                                                  MarketState, TennisScoreState)


def market(ticker: str, event: str, sport: str, bid: int,
           ask: int | None = None, **kw) -> MarketState:
    return MarketState(ticker=ticker, event_ticker=event, sport=sport,
                       yes_bid_c=bid, yes_ask_c=ask if ask is not None else bid + 2,
                       live=kw.pop("live", True), **kw)


def score(sets_won: int, opp_sets: int, games: list[int],
          opp_games: list[int], **kw) -> TennisScoreState:
    return TennisScoreState(player="A", opponent="B", sets_won=sets_won,
                            opponent_sets_won=opp_sets, games=games,
                            opponent_games=opp_games, **kw)


# ---- the tennis state machine ---------------------------------------------

@pytest.mark.parametrize("label,state,expected", [
    ("1-0, two clear in set 2", score(1, 0, [6, 3], [4, 1]), True),
    ("2-0, two clear in set 3", score(2, 0, [6, 6, 3], [4, 2, 1]), True),
    ("1-0, four clear in set 2", score(1, 0, [6, 5], [4, 1]), True),
    # Near misses, each for a different reason.
    ("no set won yet", score(0, 0, [5], [2]), False),
    ("1-0 but only one game clear", score(1, 0, [6, 2], [4, 1]), False),
    ("1-0 but BEHIND in set 2", score(1, 0, [6, 1], [4, 4]), False),
    ("1-1 — level on sets", score(1, 1, [6, 2, 4], [4, 6, 1]), False),
    ("2-1 — opponent has a set", score(2, 1, [6, 6, 2, 3], [4, 2, 6, 1]), False),
    ("2-0 but set 3 has not begun", score(2, 0, [6, 6], [4, 2]), False),
    ("match finished", score(2, 0, [6, 6, 6], [4, 2, 1], completed=True), False),
    ("not in play", score(1, 0, [6, 3], [4, 1], live=False), False),
])
def test_the_tennis_conditions(label, state, expected):
    ok, why = filters.verify_tennis_conditions(state)
    assert ok is expected, f"{label}: expected {expected}, got {ok} ({why})"
    if not ok:
        assert why, "a refusal must say why"


def test_a_one_game_lead_is_refused_however_good_the_price():
    """The score gate is not the price gate.

    A 96% market whose player is one game clear must still be refused. If it
    were not, the score condition would be decorative and the effective rule
    would be "any tennis market above 90%" — which is precisely the v1
    behaviour v2 exists to replace.
    """
    markets = [market("KXATP-M1-A", "KXATP-M1", "tennis", 96)]
    scores = {"KXATP-M1-A": score(1, 0, [6, 2], [4, 1])}   # +1, not +2

    candidates, rejected = filters.eligible_legs(markets, scores=scores)
    assert candidates == []
    assert "2 required" in rejected[0]["reason"]


def test_a_tennis_leg_with_no_score_is_refused():
    """90% is the LOWER bar, and it is only lower because the scoreboard
    confirms it. With no score there is nothing confirming anything, so the
    leg cannot have the discount."""
    markets = [market("KXATP-M1-A", "KXATP-M1", "tennis", 95)]
    candidates, rejected = filters.eligible_legs(markets, scores={})
    assert candidates == []
    assert "no live score" in rejected[0]["reason"]


# ---- the odds floors ------------------------------------------------------

@pytest.mark.parametrize("sport,bid,expected", [
    ("tennis", 90, True), ("tennis", 89, False),
    ("nba", 91, True), ("nba", 90, False),
    ("nfl", 95, True), ("mlb", 90, False),
    ("soccer", 91, True),
])
def test_each_sport_has_its_own_floor(sport, bid, expected):
    """Tennis at 90, everything else at 91. One cent under is refused —
    a threshold that bends is not a threshold."""
    ok, why = filters.meets_odds_floor(market("T", "E", sport, bid))
    assert ok is expected, f"{sport} at {bid}c: {why}"


def test_the_floor_is_measured_on_the_bid():
    """A market quoted 85/95 is an 85% market with a wide spread, not a 95%
    one. Testing the ask would admit it on a price nobody is offering."""
    wide = market("T", "E", "nba", 85, ask=95)
    ok, _ = filters.meets_odds_floor(wide)
    assert ok is False


def test_an_unquoted_market_is_not_a_zero():
    """No bid means unknown, not worthless."""
    unquoted = MarketState(ticker="T", event_ticker="E", sport="nba",
                           yes_bid_c=None, yes_ask_c=None, live=True)
    assert unquoted.implied_probability is None
    ok, why = filters.meets_odds_floor(unquoted)
    assert ok is False and "not quoted" in why


# ---- deduplication --------------------------------------------------------

def test_an_event_already_held_is_excluded():
    """Holding one side of a match rules out the whole match, not just that
    ticker. A second leg on it is more of the same bet."""
    tracker = filters.PositionTracker.from_positions(
        [{"ticker": "KXNBA-G1-LAL", "position_fp": "10.00"}])
    candidates, rejected = filters.eligible_legs(
        [market("KXNBA-G1-BOS", "KXNBA-G1", "nba", 95)], tracker=tracker)
    assert candidates == []
    assert "already exposed" in rejected[0]["reason"]


def test_a_flat_position_does_not_exclude_anything():
    """Excluding markets merely TOUCHED would shrink the universe daily until
    nothing qualified."""
    tracker = filters.PositionTracker.from_positions(
        [{"ticker": "KXNBA-G1-LAL", "position_fp": "0.00"}])
    candidates, _ = filters.eligible_legs(
        [market("KXNBA-G1-BOS", "KXNBA-G1", "nba", 95)], tracker=tracker)
    assert len(candidates) == 1


def test_only_the_strongest_leg_from_an_event_survives():
    markets = [market("KXNBA-G1-A", "KXNBA-G1", "nba", 92),
               market("KXNBA-G1-B", "KXNBA-G1", "nba", 95)]
    candidates, rejected = filters.eligible_legs(markets)
    assert [c.ticker for c in candidates] == ["KXNBA-G1-B"]
    assert "already covers" in rejected[0]["reason"]


# ---- combos ---------------------------------------------------------------

def _candidates(n: int, sport: str = "nba", bid: int = 95):
    return [ComboCandidate(market=market(f"KX-{i}-A", f"KX-{i}", sport, bid))
            for i in range(n)]


@pytest.mark.parametrize("n,expected_sizes", [
    (2, [2]), (3, [3]), (5, [5]),
    # The policy is "take as many as allowed, shrinking ONLY to avoid
    # stranding a remainder too small to be a parlay". Six legs therefore
    # split 4+2, not 3+3: five would leave one leg orphaned, four leaves a
    # legal pair. Both are valid partitions; this is the one the module
    # documents, and pinning it here stops the split changing silently.
    (6, [4, 2]),
    (7, [5, 2]),
    (10, [5, 5]),
    (11, [5, 4, 2]),
    (1, []),            # a one-leg parlay is a single bet wearing a costume
    (0, []),
])
def test_legs_are_partitioned_without_stranding_a_remainder(n, expected_sizes):
    built = combinator.build_combos(_candidates(n))
    assert sorted(len(c.legs) for c in built) == sorted(expected_sizes)
    # Whatever the split, nothing may be left in a group too small to trade.
    used = sum(len(c.legs) for c in built)
    leftover = n - used
    assert leftover < combinator.MIN_LEGS, (
        f"{leftover} legs left over — enough for another combo")


def test_no_leg_is_ever_used_twice_across_combos():
    """The property the whole combinator exists for. Overlapping bundles
    multiply exposure to one outcome while looking diversified."""
    built = combinator.build_combos(_candidates(11))
    tickers = [t for combo in built for t in combo.tickers]
    assert len(tickers) == len(set(tickers))


def test_a_combo_cannot_hold_two_legs_from_one_event():
    """Enforced on the object, not trusted to the code that builds it."""
    same_event = [
        ComboCandidate(market=market("KXNBA-G1-A", "KXNBA-G1", "nba", 95)),
        ComboCandidate(market=market("KXNBA-G1-B", "KXNBA-G1", "nba", 95)),
    ]
    with pytest.raises(ValueError, match="same event"):
        ComboOrder(legs=same_event)


@pytest.mark.parametrize("n_legs", [0, 1, 6])
def test_a_combo_is_between_two_and_five_legs(n_legs):
    with pytest.raises(Exception):
        ComboOrder(legs=_candidates(n_legs))


def test_combined_probability_is_the_product():
    """And it falls fast, which is why the strongest legs are spent first."""
    combo = ComboOrder(legs=_candidates(3, bid=90))
    assert combo.combined_probability == pytest.approx(0.9 ** 3)


def test_combos_are_ranked_strongest_first():
    strong = ComboOrder(legs=[
        ComboCandidate(market=market("A-1", "A", "nba", 97)),
        ComboCandidate(market=market("B-1", "B", "nba", 97))])
    weak = ComboOrder(legs=[
        ComboCandidate(market=market("C-1", "C", "nba", 91)),
        ComboCandidate(market=market("D-1", "D", "nba", 91))])
    assert combinator.rank([weak, strong])[0] is strong


def test_the_theoretical_price_is_the_parlay_fair_value():
    """What a limit rests at when nothing quotes the combined market — which
    is its normal state seconds after creation."""
    from app.domains.botstation.parley import engine

    combo = ComboOrder(legs=_candidates(2, bid=90))
    assert engine.theoretical_price_c(combo) == 81      # 0.90 * 0.90


# ---- the whole pass -------------------------------------------------------

def test_a_full_pass_applies_every_rule_together():
    markets = [
        market("KXNFL-G4-KC", "KXNFL-G4", "nfl", 95),
        market("KXNBA-G1-LAL", "KXNBA-G1", "nba", 93),
        market("KXNBA-G3-GSW", "KXNBA-G3", "nba", 90),      # under the 91 floor
        market("KXMLB-G5-NYY", "KXMLB-G5", "mlb", 92),      # already held
        market("KXATP-M1-ALC", "KXATP-M1", "tennis", 90),   # 90 ok + good score
        market("KXATP-M3-DJO", "KXATP-M3", "tennis", 96),   # great price, bad score
    ]
    scores = {
        "KXATP-M1-ALC": score(1, 0, [6, 3], [4, 1]),
        "KXATP-M3-DJO": score(1, 0, [6, 2], [4, 1]),
    }
    held = [{"ticker": "KXMLB-G5-NYY", "position_fp": "10.00"}]

    from app.domains.botstation.parley import engine

    result = engine.build_pass(markets, scores=scores, held_positions=held)
    eligible = {c.ticker for c in result.candidates}
    assert eligible == {"KXNFL-G4-KC", "KXNBA-G1-LAL", "KXATP-M1-ALC"}

    assert len(result.combos) == 1
    combo = result.combos[0]
    assert 2 <= len(combo.legs) <= 5
    assert len(set(combo.tickers)) == len(combo.tickers)


# ---- the shared tennis reader ---------------------------------------------
# Shapes taken from the live milestone feed. The reader is shared with the
# sports bot rather than reimplemented; these pin the parsing decisions that
# are not obvious from the endpoint alone.

_DETAIL = {
    "competitor1_id": "c-one", "competitor2_id": "c-two",
    "competitor1_round_scores": [{"score": 6, "outcome": "winner"},
                                 {"score": 3, "outcome": None}],
    "competitor2_round_scores": [{"score": 4, "outcome": "loser"},
                                 {"score": 1, "outcome": None}],
    "competitor1_overall_score": 1, "competitor2_overall_score": 0,
    "widget_status": "live", "server": "c-one",
}
_NAMES = {"c-one": "Alcaraz", "c-two": "Sinner"}


def _fetch_for(detail, names=_NAMES, kind="tennis_match"):
    def fetch(method, path, params=None):
        if path == "/milestones":
            return {"milestones": [{"id": "m1", "type": kind,
                                    "title": "Alcaraz vs Sinner"}]}
        if path.startswith("/live_data/milestone/"):
            return {"live_data": {"details": detail}}
        if path.startswith("/events/"):
            return {"event": {"markets": [
                {"custom_strike": {"tennis_competitor": cid},
                 "yes_sub_title": name} for cid, name in names.items()]}}
        raise AssertionError(f"unexpected call {path}")
    return fetch


def test_the_shared_reader_parses_a_live_match():
    from app.domains.botstation.parley import tennis

    state = tennis.state_for(_fetch_for(_DETAIL), "KXATP-M1-ALC", "Alcaraz")
    assert state is not None
    assert (state.sets_won, state.opponent_sets_won) == (1, 0)
    assert state.games == [6, 3] and state.opponent_games == [4, 1]
    assert state.live is True and state.completed is False
    # And it satisfies the spec's first condition.
    ok, why = filters.verify_tennis_conditions(state)
    assert ok, why


def test_the_reader_takes_the_perspective_of_the_named_player():
    """The same match, read from the other side, is a player a set DOWN."""
    from app.domains.botstation.parley import tennis

    state = tennis.state_for(_fetch_for(_DETAIL), "KXATP-M1-SIN", "Sinner")
    assert (state.sets_won, state.opponent_sets_won) == (0, 1)
    ok, _ = filters.verify_tennis_conditions(state)
    assert ok is False


def test_a_market_naming_neither_competitor_is_refused():
    """Guessing which side a contract pays on would put the lead on the wrong
    player — the one mistake that turns this filter into a liability."""
    from app.domains.botstation.parley import tennis

    assert tennis.state_for(_fetch_for(_DETAIL), "KXATP-M1-X", "Nadal") is None


def test_the_sets_tally_falls_back_to_counting_won_rounds():
    """overall_score goes missing mid-match. Without the fallback a live
    match reads 0-0 in sets and every condition fails for a reason that has
    nothing to do with the game."""
    from app.domains.botstation.parley import tennis

    detail = {k: v for k, v in _DETAIL.items()
              if not k.endswith("overall_score")}
    state = tennis.state_for(_fetch_for(detail), "KXATP-M1-ALC", "Alcaraz")
    assert state.sets_won == 1 and state.opponent_sets_won == 0


def test_a_finished_match_is_over_whatever_status_says():
    """A winner is decisive; trusting widget_status alone would leave a
    finished match looking tradeable."""
    from app.domains.botstation.parley import tennis

    detail = {**_DETAIL, "winner": "c-one", "widget_status": "live"}
    state = tennis.state_for(_fetch_for(detail), "KXATP-M1-ALC", "Alcaraz")
    assert state.completed is True and state.live is False
    ok, why = filters.verify_tennis_conditions(state)
    assert ok is False and "over" in why


def test_a_non_tennis_milestone_returns_nothing():
    from app.domains.botstation.parley import tennis

    fetch = _fetch_for(_DETAIL, kind="basketball_game")
    assert tennis.state_for(fetch, "KXNBA-G1-LAL", "Lakers") is None
