"""The shapes the parlay engine works in.

Pydantic rather than dataclasses because these cross a trust boundary: every
one of them is built from a Kalshi response, and Kalshi sends numbers as
decimal strings, omits fields that do not apply, and uses different names for
the same idea in different endpoints. Validation at the edge means the rest of
the engine can assume a float is a float instead of every function re-checking.

Prices are held in CENTS as integers. Kalshi quotes ``yes_bid_dollars`` as a
decimal string and the engine reasons in probability, so there are three
representations of one number floating around; picking integer cents for the
internal one means combo arithmetic never accumulates float error and an exact
comparison against a threshold is meaningful.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def cents(value) -> int | None:
    """A Kalshi dollar string to integer cents.

    Returns None rather than 0 for a missing quote. The difference matters:
    a market with no bid is not a market bid at zero, and treating it as such
    would make an unquoted leg look like the worst possible price instead of
    an unknown one.
    """
    if value is None or value == "":
        return None
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return None


class MarketState(BaseModel):
    """One tradeable side of one event, as the exchange currently quotes it."""

    ticker: str
    event_ticker: str = ""
    title: str = ""
    # The competitor or outcome this market pays on: the player's name for
    # tennis, the team for a ball sport.
    outcome: str = ""
    sport: str = "unknown"

    yes_bid_c: int | None = None
    yes_ask_c: int | None = None
    # The other side of the same market. Kalshi quotes it explicitly and it
    # mirrors the yes side -- no_bid = 100 - yes_ask -- but it is READ rather
    # than derived, because the mirror is an identity of the order book and
    # not a promise in the API contract.
    no_bid_c: int | None = None
    no_ask_c: int | None = None
    # Which side of this market a leg would take. "Chelsea to win" and
    # "Chelsea NOT to win" are one market and two bets, and on a three-way
    # soccer market the second is often the only one worth having: a 6c
    # outsider is a 93c leg read from the other side.
    #
    # It lives on the market rather than on the candidate because every
    # filter downstream asks the same questions -- what does it pay, how wide
    # is it, is it inside the band -- and those answers differ by side. One
    # field here means none of them has to learn about sides.
    side: Literal["yes", "no"] = "yes"
    volume: int = 0
    # Volume in DOLLARS, which is what "biggest market" means to an operator.
    # Contracts alone rank a penny market above a dollar one for the same
    # turnover, and the daily ticket ranks on this.
    volume_usd: float = 0.0
    open_interest: int = 0

    # Is the underlying event actually in play? A market can be quoted at 96c
    # before the match starts, which is a price about the future rather than
    # about a lead somebody currently holds.
    live: bool = False
    completed: bool = False

    # When this market CLOSES -- the moment the leg resolves and its capital
    # comes back. A parlay leg on something that closes in three weeks holds
    # the whole combo for three weeks, however good the price looks today.
    #
    # Read from close_ts, not expected_expiration_ts. On a stage race those
    # disagree by a fortnight: the Vuelta stage market reports an expected
    # expiration of TODAY (when the stage finishes) and a close of 12
    # September (when the race does). It is the close that frees the capital,
    # so it is the close this horizon is measured against.
    closes_at: str | None = None

    @field_validator("ticker", "event_ticker", "outcome", "title", mode="before")
    @classmethod
    def _strip(cls, v):
        return (v or "").strip() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _default_event(self):
        # Kalshi market tickers are EVENT-OUTCOME. Deriving the event when it
        # was not supplied is what makes the "two legs from one match" check
        # possible at all -- that check is by EVENT, not by ticker.
        if not self.event_ticker and self.ticker.count("-") >= 2:
            object.__setattr__(self, "event_ticker",
                               self.ticker.rsplit("-", 1)[0])
        return self

    @property
    def bid_c(self) -> int | None:
        """The bid on the side this leg would take.

        Falls back to the mirror when the exchange omitted the no side, which
        is the identity every order book satisfies: buying NO at 1 - yes_ask
        is the same trade as selling YES at the ask.
        """
        if self.side == "no":
            if self.no_bid_c is not None:
                return self.no_bid_c
            return None if self.yes_ask_c is None else 100 - self.yes_ask_c
        return self.yes_bid_c

    @property
    def ask_c(self) -> int | None:
        """The ask on the side this leg would take."""
        if self.side == "no":
            if self.no_ask_c is not None:
                return self.no_ask_c
            return None if self.yes_bid_c is None else 100 - self.yes_bid_c
        return self.yes_ask_c

    @property
    def implied_probability(self) -> float | None:
        """What the quote says the chance is, 0..1.

        Taken from the BID, on whichever side the leg is. The ask is what you
        would pay and is always the higher of the two, so testing the ask
        against a floor would admit legs the market is not actually that
        confident about. The bid is the conservative side of the spread and
        the one a threshold should bite on.
        """
        bid = self.bid_c
        if bid is None:
            return None
        return bid / 100.0

    @property
    def spread_c(self) -> int | None:
        """Ask minus bid, in cents. None when either side is unquoted.

        A wide spread is the market saying it does not know. Buying into one
        means paying the ask and being able to sell only at the bid, so the
        position starts underwater by the width of the spread -- and on a
        parlay leg that cost is multiplied by every other leg.
        """
        bid, ask = self.bid_c, self.ask_c
        if bid is None or ask is None:
            return None
        return ask - bid

    @property
    def is_tradeable(self) -> bool:
        """Quoted on both sides and not already over."""
        return (self.live and not self.completed
                and self.bid_c is not None and self.ask_c is not None)

    def as_no(self) -> MarketState | None:
        """The same market read from the other side, or None if it cannot be.

        A separate object rather than a flag on the leg: two sides of one
        market are two different bets with two different prices, and the
        combinator ranks them against each other exactly as it ranks any
        other pair. The event they belong to is unchanged, so the rule that
        one match contributes one leg still decides which of the two survives.
        """
        if self.side == "no":
            return None
        flipped = self.model_copy(update={"side": "no"})
        if flipped.bid_c is None or flipped.ask_c is None:
            return None
        # Kalshi's no_sub_title is often the yes title verbatim, which would
        # print a leg that reads like its own opposite.
        label = self.outcome or self.ticker
        return flipped.model_copy(update={"outcome": f"NOT {label}"})

    @classmethod
    def from_kalshi(cls, raw: dict, *, sport: str = "unknown",
                    live: bool = False, completed: bool = False) -> MarketState:
        return cls(
            ticker=raw.get("ticker") or "",
            event_ticker=raw.get("event_ticker") or "",
            title=raw.get("title") or "",
            outcome=raw.get("yes_sub_title") or raw.get("title") or "",
            sport=sport,
            yes_bid_c=cents(raw.get("yes_bid_dollars")),
            yes_ask_c=cents(raw.get("yes_ask_dollars")),
            no_bid_c=cents(raw.get("no_bid_dollars")),
            no_ask_c=cents(raw.get("no_ask_dollars")),
            volume=int(raw.get("volume") or 0),
            open_interest=int(raw.get("open_interest") or 0),
            live=live, completed=completed,
            # close first, and only then the expected-expiration fields as a
            # fallback for endpoints that omit it.
            closes_at=(raw.get("close_ts") or raw.get("close_time")
                       or raw.get("expected_expiration_ts")
                       or raw.get("expected_expiration_time")),
        )


class TennisScoreState(BaseModel):
    """A live tennis match, in the shape Kalshi's milestone feed reports it.

    ``games`` is one entry per set PLAYED SO FAR, including the one in
    progress, which is what makes "which set are we in" answerable without a
    separate field: it is ``len(games) - 1``.
    """

    player: str
    opponent: str = ""
    sets_won: int = 0
    opponent_sets_won: int = 0
    games: list[int] = Field(default_factory=list)
    opponent_games: list[int] = Field(default_factory=list)
    serving: bool = False
    live: bool = True
    completed: bool = False

    @property
    def current_set_index(self) -> int:
        """0-based index of the set in progress, or -1 if none has started."""
        return max(len(self.games), len(self.opponent_games)) - 1

    def games_in(self, index: int) -> int:
        return self.games[index] if 0 <= index < len(self.games) else 0

    def opponent_games_in(self, index: int) -> int:
        return (self.opponent_games[index]
                if 0 <= index < len(self.opponent_games) else 0)

    def lead_in(self, index: int) -> int:
        """Games ahead in that set. Negative means behind."""
        return self.games_in(index) - self.opponent_games_in(index)

    @classmethod
    def from_match_score(cls, score: dict, player_name: str) -> TennisScoreState | None:
        """Pull one player's view out of a two-player MatchScore."""
        players = score.get("players") or []
        if len(players) < 2:
            return None
        wanted = (player_name or "").strip().lower()
        me = next((p for p in players
                   if (p.get("name") or "").strip().lower() == wanted), None)
        if me is None:
            return None
        other = next(p for p in players if p is not me)
        return cls(
            player=me.get("name") or "",
            opponent=other.get("name") or "",
            sets_won=int(me.get("sets_won") or 0),
            opponent_sets_won=int(other.get("sets_won") or 0),
            games=[int(g or 0) for g in (me.get("games") or [])],
            opponent_games=[int(g or 0) for g in (other.get("games") or [])],
            serving=bool(me.get("serving")),
            live=bool(score.get("live", True)),
            completed=bool(score.get("completed")),
        )


class ComboCandidate(BaseModel):
    """A leg that passed every filter and may go into a combo."""

    market: MarketState
    # Why it qualified, in words. Carried onto the order so a combo placed at
    # 3am can be explained the next morning without re-deriving the state that
    # no longer exists.
    reason: str = ""
    score_state: TennisScoreState | None = None

    @property
    def ticker(self) -> str:
        return self.market.ticker

    @property
    def event_ticker(self) -> str:
        return self.market.event_ticker

    @property
    def probability(self) -> float:
        return self.market.implied_probability or 0.0

    @property
    def side(self) -> str:
        return self.market.side

    @property
    def ask_c(self) -> int:
        return self.market.ask_c or 100


class ComboOrder(BaseModel):
    """A parlay: two to five legs, none of them from the same event."""

    # 24 is the outer bound this desk will construct, not the house
    # style: a regular parlay is capped at 5 by the engine's max_legs,
    # while the daily long-shot ticket deliberately runs much longer.
    # Keeping the model permissive and the POLICY in the caller means a
    # different appetite is a launch option, not a code change.
    legs: list[ComboCandidate] = Field(min_length=2, max_length=24)
    # Whether two legs may come from the SAME event. False everywhere except
    # the daily long-shot ticket, which is explicitly a correlated bet: it
    # wants "set 1 winner" and "match winner" on one match precisely because
    # they move together, and a huge payout is the point rather than a
    # diversified one.
    allow_same_event: bool = False
    # Fractional: the exchange sizes in 0.01-contract increments, and a
    # dollar budget rarely divides into whole ones. Set by place_combo
    # once the limit price is known, so the pass summary reports what
    # was actually sent.
    contracts: float = Field(default=1.0, gt=0)

    @model_validator(mode="after")
    def _legs_are_disjoint(self):
        """No two legs from one match.

        Not a preference. Two markets on the same event are the SAME
        underlying question, so a parlay built from both is not diversified --
        it is one bet at a worse price, and if the favourite loses, every leg
        fails together. This is the invariant the whole combinator exists to
        preserve, so it is enforced on the object rather than trusted to the
        code that builds it.
        """
        # ONE MARKET, ONE LEG -- checked before the same-event escape hatch
        # below, because this one holds even for the deliberately correlated
        # ticket. A combo carrying both sides of a market can never pay: the
        # legs contradict each other, so one of them is guaranteed to fail
        # and the contract is worthless the moment it is created. Carrying
        # the same side twice is merely pointless; carrying both is a bet
        # against yourself.
        markets = [leg.ticker for leg in self.legs]
        if len(set(markets)) != len(markets):
            clash = sorted({t for t in markets if markets.count(t) > 1})
            raise ValueError(
                "a combo cannot hold two legs on the same market "
                "(both sides of one cannot both land): " + ", ".join(clash))

        if self.allow_same_event:
            return self
        events = [leg.event_ticker or leg.ticker for leg in self.legs]
        if len(set(events)) != len(events):
            raise ValueError(
                "a combo cannot hold two legs from the same event: "
                + ", ".join(sorted(events))
            )
        return self

    @property
    def tickers(self) -> list[str]:
        return [leg.ticker for leg in self.legs]

    @property
    def sides(self) -> list[str]:
        """Parallel to ``tickers``. The ticker names the market; only this
        says which way round the bet on it is."""
        return [leg.market.side for leg in self.legs]

    @property
    def combined_probability(self) -> float:
        """Product of the legs. Independence is ASSUMED, and that assumption
        is exactly why legs from one event are refused above."""
        p = 1.0
        for leg in self.legs:
            p *= leg.probability
        return p

    @property
    def cost_c(self) -> int:
        """What one contract of this parlay costs, in cents.

        The PRODUCT of the legs, not their sum. A parlay is a single combined
        contract that pays $1 if every leg lands, so five legs at 99c cost
        about 95c together -- not 500c. Summing them reported five separate
        purchases, which is the trade this engine deliberately does not make,
        and made a thin 5% edge look like a 5x outlay.

        This is the same number the limit rests at, so the cost the operator
        reads and the price actually sent are one calculation.
        """
        return max(1, min(99, int(round(self.combined_probability * 100))))

    def describe(self) -> str:
        return " + ".join(f"{leg.market.outcome or leg.ticker}"
                          f"@{leg.market.bid_c}c" for leg in self.legs)
