"""Turning qualified legs into parlays.

The problem is a partition, not a choice: given N eligible legs, cut them into
disjoint groups of 2 to 5. Disjoint is the whole point -- a leg that appears
in two combos is one outcome deciding two bets, which doubles the loss when it
goes wrong while the operator believes they are diversified.

So this does NOT enumerate combinations. `itertools.combinations` over 12 legs
is 2,510 overlapping parlays, and picking the "best" ones from that list gives
you the same three favourites in every bundle. Instead each leg is used at
most once across the entire output, which caps the number of combos at
N // min_size and makes "how exposed am I" answerable by counting.

Ordering is strongest-first. Parlay probability is the PRODUCT of its legs, so
the combined number falls fast: five legs at 92% is 66%, and the difference
between a 92% leg and a 90% one compounds across every combo it appears in.
Spending the best legs first means the strongest bundle is the one that gets
placed when only one is wanted.
"""

from __future__ import annotations

import logging

from app.domains.botstation.parley.models import ComboCandidate, ComboOrder

logger = logging.getLogger(__name__)

MIN_LEGS = 2
MAX_LEGS = 5

# What the combinator will build if asked. The daily long-shot ticket uses
# the upper end; nothing else does.
ABSOLUTE_MAX_LEGS = 24


def build_combos(candidates: list[ComboCandidate], *,
                 min_legs: int = MIN_LEGS, max_legs: int = MAX_LEGS,
                 contracts: int = 1,
                 max_combos: int | None = None) -> list[ComboOrder]:
    """Partition candidates into disjoint parlays of ``min_legs``..``max_legs``.

    Legs are spent strongest-first and never reused. What is left over when
    fewer than ``min_legs`` remain is simply not traded -- a one-leg "parlay"
    is a single bet wearing the wrong name, and padding it with a leg that
    failed the filters is how a threshold quietly becomes a suggestion.
    """
    if min_legs < 2:
        raise ValueError("a parlay needs at least 2 legs; 1 is a single bet")
    if max_legs < min_legs:
        raise ValueError(f"max_legs {max_legs} is below min_legs {min_legs}")

    # Strongest first. Ties break on the cheaper ask, because two legs at the
    # same probability are not the same trade if one costs more to enter.
    pool = sorted(candidates,
                  key=lambda c: (-c.probability, c.ask_c, c.ticker))

    combos: list[ComboOrder] = []
    used_events: set[str] = set()
    index = 0

    while index < len(pool):
        remaining = len(pool) - index
        if remaining < min_legs:
            break

        # Take as many as allowed, but never leave a remainder too small to
        # form a combo of its own. Taking 5 from 6 strands the 6th; taking 4
        # leaves 2, which is a whole extra parlay.
        size = min(max_legs, remaining)
        while size > min_legs and 0 < (remaining - size) < min_legs:
            size -= 1

        legs: list[ComboCandidate] = []
        while index < len(pool) and len(legs) < size:
            candidate = pool[index]
            index += 1
            event = candidate.event_ticker or candidate.ticker
            if event in used_events:
                # Should not happen -- eligible_legs already deduplicates by
                # event -- but the guarantee is enforced here too rather than
                # assumed, because this is the invariant that matters most and
                # it is cheap to check twice.
                continue
            legs.append(candidate)
            used_events.add(event)

        if len(legs) < min_legs:
            # Ran out of usable legs part-way. Put nothing out rather than
            # something undersized.
            break

        try:
            combos.append(ComboOrder(legs=legs, contracts=contracts))
        except ValueError as exc:
            # ComboOrder enforces disjointness itself. Reaching here means a
            # real bug upstream, and placing the order anyway would be the
            # wrong way to handle it.
            logger.warning("discarded an invalid combo: %s", exc)

        if max_combos is not None and len(combos) >= max_combos:
            break

    return combos


def rank(combos: list[ComboOrder]) -> list[ComboOrder]:
    """Best first, by combined probability then by cost.

    Probability is the primary key because a parlay that does not land is
    worth nothing regardless of what it cost. Cost breaks ties, since two
    bundles equally likely to win are not equally good if one ties up more
    capital.
    """
    return sorted(combos, key=lambda c: (-c.combined_probability, c.cost_c))


def summarise(combos: list[ComboOrder]) -> dict:
    """A one-glance view of what was built."""
    return {
        "combos": len(combos),
        "legs_used": sum(len(c.legs) for c in combos),
        "sizes": sorted(len(c.legs) for c in combos),
        "best_probability": (round(max(c.combined_probability for c in combos), 4)
                             if combos else None),
        "total_cost_c": sum(c.cost_c * c.contracts for c in combos),
    }
