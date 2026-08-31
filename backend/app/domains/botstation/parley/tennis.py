"""Reading a live tennis score from Kalshi.

This is the sports bot's reader, moved rather than rewritten. The logic here
was worked out against the live feed and knows things that are not obvious
from the endpoint documentation:

  * competitors come back as UUIDs, and the only way to learn which player a
    market pays on is to map ``custom_strike.tennis_competitor`` through the
    event's own markets to ``yes_sub_title``
  * ``competitor{n}_overall_score`` is the sets tally, but it is sometimes
    absent mid-match, in which case won rounds have to be counted instead
  * an ``advantage`` marker belongs on the point score, not the game score
  * a match with a ``winner`` is over regardless of what ``status`` says

I had written a second copy of this inside the parley v2 script before
noticing this one existed. Two readers of one feed is exactly the duplication
the rebuild exists to remove -- they drift the first time either is fixed, and
nothing reports the disagreement.

It lives here rather than in the vendored script because the vendored one
cannot currently be imported at all: ``bot_kalshi_sports_v1`` reaches for
``bot_kalshi_btc15``, which was never vendored into this project, so every
sports script fails at import. Putting the reader somewhere importable is
what makes it reusable in the first place.

Client-agnostic on purpose. It takes a ``fetch(method, path, params)``
callable rather than a client, so the async sports client and the rebuild's
sync one can both drive it without either owning it.
"""

from __future__ import annotations

import logging
from typing import Callable, Protocol

logger = logging.getLogger(__name__)

Fetch = Callable[..., dict]


class _Client(Protocol):
    def request(self, method: str, path: str, *,
                params: dict | None = ...) -> dict: ...


def fetcher_for(client: _Client) -> Fetch:
    """Adapt the rebuild's Kalshi client to the fetch signature."""
    def fetch(method: str, path: str, params: dict | None = None) -> dict:
        return client.request(method, path, params=params)
    return fetch


def event_of(ticker: str) -> str:
    """Market tickers are EVENT-OUTCOME; the milestone feed is per event."""
    return ticker.rsplit("-", 1)[0] if ticker.count("-") >= 2 else ticker


def _match_score(detail: dict, names: dict[str, str], title: str) -> dict | None:
    """Build a MatchScore-shaped dict from /live_data/milestone details."""
    c1, c2 = detail.get("competitor1_id"), detail.get("competitor2_id")
    parts = [t.strip() for t in title.split(" vs ")] if " vs " in title else []
    n1 = names.get(c1) or (parts[0] if parts else "Player 1")
    n2 = names.get(c2) or (parts[1] if len(parts) > 1 else "Player 2")

    rounds1 = detail.get("competitor1_round_scores") or []
    rounds2 = detail.get("competitor2_round_scores") or []
    games1 = [int(r.get("score", 0) or 0) for r in rounds1]
    games2 = [int(r.get("score", 0) or 0) for r in rounds2]

    # The sets tally, which is sometimes absent mid-match. Counting won rounds
    # is the fallback; without it a live match reads as 0-0 in sets and every
    # score condition fails for a reason that has nothing to do with the game.
    sets1 = detail.get("competitor1_overall_score")
    sets2 = detail.get("competitor2_overall_score")
    if sets1 is None:
        sets1 = sum(1 for r in rounds1 if r.get("outcome") == "winner")
    if sets2 is None:
        sets2 = sum(1 for r in rounds2 if r.get("outcome") == "winner")

    winner_id = detail.get("winner") or ""
    completed = bool(winner_id)
    # A match with a winner is over whatever status says. Trusting status
    # alone would leave a finished match looking tradeable.
    live = ((detail.get("widget_status") == "live"
             or detail.get("status") in ("started", "live", "inprogress"))
            and not completed)

    server_id = detail.get("server")
    advantage = detail.get("advantage") or ""

    def points(score, competitor_id, index) -> str | None:
        if score is None:
            return None
        text = str(score)
        if advantage and advantage in (competitor_id, f"competitor{index}",
                                       "home" if index == 1 else "away"):
            text += "A"
        return text

    players = [
        {"name": n1, "sets_won": int(sets1 or 0), "games": games1,
         "current_game": points(detail.get("competitor1_current_round_score"),
                                c1, 1) if live else None,
         "serving": server_id == c1, "winner": winner_id == c1},
        {"name": n2, "sets_won": int(sets2 or 0), "games": games2,
         "current_game": points(detail.get("competitor2_current_round_score"),
                                c2, 2) if live else None,
         "serving": server_id == c2, "winner": winner_id == c2},
    ]
    server = n1 if server_id == c1 else n2 if server_id == c2 else None
    leader = (n1 if players[0]["sets_won"] > players[1]["sets_won"]
              else n2 if players[1]["sets_won"] > players[0]["sets_won"]
              else None)
    return {"tournament": title,
            "status": "post" if completed else "in" if live else "pre",
            "completed": completed, "live": live, "players": players,
            "server": server, "leader": leader}


def match_score(fetch: Fetch, ticker: str) -> dict | None:
    """The live score for one market's event, or None.

    Three calls: the milestone id, its live data, and the event's markets to
    resolve competitor UUIDs to the names printed on the contracts. Returns
    None whenever any of that is missing -- and the filters treat None as
    "cannot confirm", never as "condition met".
    """
    event = event_of(ticker)
    try:
        found = fetch("GET", "/milestones",
                      {"related_event_ticker": event, "limit": 5})
    except Exception as exc:                            # noqa: BLE001
        logger.info("milestones for %s: %s", event, type(exc).__name__)
        return None

    milestones = found.get("milestones") or []
    if not milestones or not str(milestones[0].get("type", "")).startswith("tennis"):
        return None
    milestone = milestones[0]

    try:
        live = fetch("GET", f"/live_data/milestone/{milestone['id']}", None)
    except Exception as exc:                            # noqa: BLE001
        logger.info("live data for %s: %s", event, type(exc).__name__)
        return None

    detail = ((live or {}).get("live_data") or {}).get("details") or {}
    if not detail:
        return None

    names: dict[str, str] = {}
    try:
        payload = fetch("GET", f"/events/{event}", {"with_nested_markets": "true"})
        for market in (payload.get("event", {}).get("markets") or []):
            competitor = (market.get("custom_strike") or {}).get("tennis_competitor")
            if competitor:
                names[competitor] = (market.get("yes_sub_title")
                                     or market.get("title") or "")
    except Exception:                                   # noqa: BLE001
        # Without the map the players fall back to the milestone title, which
        # is still enough to match one of them by name most of the time.
        pass

    score = _match_score(detail, names, milestone.get("title", ""))
    if score is not None:
        score["match_start"] = milestone.get("start_date")
    return score


def state_for(fetch: Fetch, ticker: str, outcome: str):
    """The score as the player this market pays on sees it.

    Returns None when the contract names somebody neither competitor
    resolved to. Refusing is the only safe answer there: guessing would put
    the lead on the wrong side of the match, which is the one mistake that
    turns this filter from a safeguard into a liability.
    """
    from app.domains.botstation.parley.models import TennisScoreState

    score = match_score(fetch, ticker)
    if score is None:
        return None
    return TennisScoreState.from_match_score(score, outcome)
