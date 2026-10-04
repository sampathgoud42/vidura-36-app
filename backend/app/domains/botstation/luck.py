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
import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_RUNTIME = None

# A preview waiting to be confirmed. Held in memory on purpose: it is a
# proposal, not a record, and an unconfirmed one is worth nothing tomorrow.
_PREVIEWS: dict[str, dict] = {}
PREVIEW_TTL_S = 900

def _game_key(market) -> tuple[str, str]:
    """The game a market belongs to, across all of its series.

    Kalshi lists one fixture's winner, spread, total and props as separate
    events in separate series -- KXNCAAFGAME-26OCT03PSUNW and
    KXNCAAFSPREAD-26OCT03PSUNW -- that share everything after the series:
    the date and the two teams. That suffix is the game. The event-level
    rule in the filters cannot see it, since every prop is its own event.
    """
    event = market.event_ticker or market.ticker
    return ((market.sport or "").lower(),
            event.split("-", 1)[1] if "-" in event else event)


def _one_per_game(candidates) -> list:
    """The strongest leg of each game: the highest NO price inside the band.

    A NO-side ticket reads every prop of a fixture, and those are one bet
    asked several ways -- "Ecuador do not win" already implies "Ecuador do
    not win by two" -- so the exchange refuses the pair as duplicated legs,
    and when it would not, both still lose together. One leg per game keeps
    the ticket spread across games, the way the slips it is modelled on are.
    """
    best: dict[tuple[str, str], Any] = {}
    for c in candidates:
        key = _game_key(c.market)
        held = best.get(key)
        if held is None or ((c.market.implied_probability or 0.0),
                            c.market.volume_usd) > (
                (held.market.implied_probability or 0.0),
                held.market.volume_usd):
            best[key] = c
    return list(best.values())


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


# The sports in play, for the desk's sport picker. Two listing calls -- every
# sports series with its tag, every open event -- for an answer that changes
# over hours, so it is held a few minutes rather than re-read each time the
# panel opens.
_SPORTS: tuple[float, list[dict]] | None = None
SPORTS_TTL_S = 600


def sports_in_play(cred) -> list[dict]:
    """Every sport with an open event now, busiest first.

    Named as the scanner names them -- Kalshi's sport tag on each series,
    lowercased -- so a sport picked on the desk is one `_load_markets`
    filters on, with nothing to translate between the two.
    """
    global _SPORTS
    if _SPORTS and time.time() - _SPORTS[0] < SPORTS_TTL_S:
        return _SPORTS[1]
    from app.services.kalshi_client import DEFAULT_BASE, KalshiClient

    runtime = _runtime()
    client = KalshiClient(cred.token, private_key_pem=cred.private_key_pem,
                          base_uri=cred.base_url or DEFAULT_BASE)
    try:
        tags = runtime._sport_tags(client)
        active = runtime._active_sports_series(client)
    finally:
        client.close()
    counts: dict[str, int] = {}
    for series in active:
        if series in tags:
            counts[tags[series][0]] = counts.get(tags[series][0], 0) + 1
    found = [{"sport": sport, "series": n} for sport, n in
             sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    # An empty answer is a failed read (both listings swallow their errors),
    # not a day without sport: kept out of the cache so the next open retries.
    if found:
        _SPORTS = (time.time(), found)
    return found


# ---- tennis ---------------------------------------------------------------
#
# A tennis leg on this ticket is the match FAVOURITE's, and only when it is
#   above TENNIS_ANY_C, or
#   above TENNIS_LEADING_C while ahead on the scoreboard.
# That replaces every tennis gate the regular engine has (the price lock, a
# set won with a lead in the next). The gates that are not about tennis --
# the leg price band, the spread, the horizon, the volume floor, Kalshi's
# own combination rules -- apply to it like any other leg.
TENNIS_ANY_C = 85
TENNIS_LEADING_C = 75

# Who the favourite is comes from the ATP/WTA/ITF rankings first -- the
# sports bot's own rule set (predict_v3.determine_favorite) -- and the price
# only when the rankings cannot say. They are scraped again when older than
# this, while the board is being read.
RANKINGS_MAX_AGE_S = 5 * 24 * 3600
RANKINGS_SCRAPE_TIMEOUT_S = 300
_RANKINGS_LOCK = threading.Lock()


def _tennis_lib():
    """The runtime's tennis package: the rankings CSV and the favourite rules
    the sports bot already plays by -- shared, not copied."""
    from app.core.config import get_settings

    root = get_settings().source_repo / "prediction-trade" / "sports"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from tennis import predict_v3, tennis_live_score
    return tennis_live_score, predict_v3


def _rankings_age_s() -> float:
    try:
        live_score, _ = _tennis_lib()
        return time.time() - live_score._rankings_csv_path().stat().st_mtime
    except Exception:                                   # noqa: BLE001
        return float("inf")


def _rankings_at() -> str | None:
    """When the rankings CSV was written, for the sheet to say."""
    try:
        live_score, _ = _tennis_lib()
        stamp = live_score._rankings_csv_path().stat().st_mtime
    except Exception:                                   # noqa: BLE001
        return None
    return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()


def refresh_rankings_if_stale(max_age_s: float = RANKINGS_MAX_AGE_S) -> str:
    """Scrape the ATP/WTA/ITF rankings again when the CSV is older than
    ``max_age_s``: the runtime's own scraper, run as a script with this
    Python (ATP/WTA from ESPN's JSON, ITF from the ITF's -- no browser).
    One scrape at a time: a second caller waits for it."""
    if _rankings_age_s() < max_age_s:
        return "fresh"
    if not _RANKINGS_LOCK.acquire(blocking=False):
        with _RANKINGS_LOCK:
            return "refreshed by another scan"
    try:
        if _rankings_age_s() < max_age_s:
            return "fresh"
        live_score, _ = _tennis_lib()
        tennis_dir = os.path.dirname(os.path.abspath(live_score.__file__))
        started = time.time()
        try:
            proc = subprocess.run(
                [sys.executable, os.path.join("web", "sofascore_rankings.py")],
                cwd=tennis_dir, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=RANKINGS_SCRAPE_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            logger.warning("luck: rankings scrape timed out after %ss",
                           RANKINGS_SCRAPE_TIMEOUT_S)
            return "timed out"
        except OSError as exc:
            logger.warning("luck: rankings scrape could not start: %s", exc)
            return "failed"
        tail = " | ".join((proc.stdout or "").strip().splitlines()[-3:])
        logger.info("luck: rankings scrape exited %s in %.0fs: %s",
                    proc.returncode, time.time() - started, tail)
        return "refreshed" if proc.returncode == 0 else "failed"
    finally:
        _RANKINGS_LOCK.release()


def _ranked(live_score, name: str, ranks: dict, tours: dict) -> tuple[int | None, str | None]:
    """A player's rank and tour: the exact name, else the ONE ranked player
    with the same surname and first initial.

    Not the shared rank_for, which takes any word of three letters or more
    the two names have in common: "Sarah Van Emst" came back as Botic Van De
    Zandschulp, ATP 41 -- enough to make someone the favourite by ranking
    who is not.
    """
    key = live_score._norm(name)
    if key not in ranks:
        parts = key.replace("-", " ").split()
        if len(parts) < 2:
            return None, None
        hits = [k for k in ranks
                if len(k.split()) >= 2 and k.replace("-", " ").split()[-1] == parts[-1]
                and k[:1] == parts[0][:1]]
        if len(hits) != 1:
            return None, None
        key = hits[0]
    return ranks.get(key), tours.get(key)


def _tennis_favourites(markets) -> dict[str, str]:
    """Each match's favourite: ticker -> how it was decided, "ranking" or
    "price". Match-winner markets only, two players to an event."""
    from app.domains.botstation.parley import filters

    pairs: dict[str, list] = {}
    for m in markets:
        if filters.is_tennis(m.sport) and m.headline and m.side == "yes":
            pairs.setdefault(m.event_ticker or m.ticker, []).append(m)
    if not pairs:
        return {}
    try:
        live_score, predict = _tennis_lib()
        ranks = live_score.load_rankings_csv()
        tours = live_score.load_rank_tours()
    except Exception as exc:                            # noqa: BLE001
        logger.warning("luck: tennis rankings unavailable (%s); favourites "
                       "go by price", type(exc).__name__)
        live_score = predict = None
        ranks, tours = {}, {}
    favourites: dict[str, str] = {}
    for pair in pairs.values():
        if len(pair) != 2:
            continue
        a, b = pair
        side = None
        if predict is not None:
            names = (a.outcome or "", b.outcome or "")
            (rank_a, tour_a), (rank_b, tour_b) = (
                _ranked(live_score, n, ranks, tours) for n in names)
            # No original odds: the scan sees only live prices, and handing
            # those in would let the score, not the players, pick the
            # favourite. The rankings decide; the price only when they cannot.
            side = predict.determine_favorite(
                names, {}, (rank_a, rank_b), rank_tours=(tour_a, tour_b))
        if side in ("A", "B"):
            favourites[(a if side == "A" else b).ticker] = "ranking"
        elif (a.bid_c or 0) != (b.bid_c or 0):
            favourites[max(pair, key=lambda m: m.bid_c or 0).ticker] = "price"
    return favourites


def _leading(score) -> bool:
    """Ahead on the scoreboard: more sets, or level on sets and more games
    in the set being played. A finished match or one not in play is not led."""
    if score.completed or not score.live:
        return False
    if score.sets_won != score.opponent_sets_won:
        return score.sets_won > score.opponent_sets_won
    current = score.current_set_index
    return current >= 0 and score.lead_in(current) > 0


def _tennis_rule(favourites: dict[str, str]):
    """The favourite's match-winner leg above TENNIS_ANY_C, or above
    TENNIS_LEADING_C while leading. For filters.eligible_legs."""
    def rule(market, score) -> tuple[bool, str]:
        if not market.headline or market.side != "yes":
            return False, "tennis: only a match winner's YES side is taken"
        how = favourites.get(market.ticker)
        if how is None:
            return False, "tennis: not the favourite"
        bid = market.bid_c or 0
        if bid > TENNIS_ANY_C:
            return True, f"tennis favourite by {how} at {bid}c"
        if bid <= TENNIS_LEADING_C:
            return False, (f"tennis favourite at {bid}c, not above "
                           f"{TENNIS_LEADING_C}c")
        if score is None:
            return False, (f"tennis favourite at {bid}c with no live score "
                           "to show a lead")
        if not _leading(score):
            return False, f"tennis favourite at {bid}c is not ahead"
        return True, f"tennis favourite by {how}, leading, at {bid}c"
    return rule


def preview(cred, *, min_legs: int = 5, max_legs: int = 24,
            min_leg_c: int = 60, max_leg_c: int = 98,
            min_volume_usd: float = 0.0,
            max_spread_c: int | None = None,
            max_hours: int | None = None,
            sports: list[str] | None = None, no_side_only: bool = False,
            owner: str = "") -> dict:
    """Choose the legs, have the exchange accept them, describe them. Buys
    nothing.

    ``owner`` is the operator the preview is for: only they can place it.

    Returns a token the caller passes back to `place`. The one thing created
    on the exchange is the combined market for the legs shown (see
    `_confirm`): Kalshi has no other way left to say whether it accepts a
    combination, and a ticket it would refuse must never reach the sheet.
    No order, no position, nothing spent -- a preview nobody confirms leaves
    an empty combined market behind and nothing else.

    ``max_spread_c`` and ``max_hours`` are the two gates the regular parlay
    engine sets for itself and this ticket has no reason to share. A long
    shot is bought to be held to settlement, so a wide market costs it less
    than it costs a parlay meant to be worth its price the whole way -- and
    the 72h horizon exists to stop ONE leg holding a parlay's capital for
    weeks, which is a different concern when the whole ticket is $5.

    None means the engine's own default, so there is one place either number
    is written down.

    ``no_side_only`` builds the ticket from NO sides alone: every market --
    headline winners and every game prop, spreads, totals, both teams to
    score -- read as "this does not happen", and nothing backed outright.
    It changes the SIDES and nothing else: the leg price band, the volume
    floor, the spread gate and the horizon apply exactly as set. Legs are
    taken one per game -- a fixture's props are one bet asked several ways --
    and ranked on price, highest first.

    ``sports`` narrows the scan to those sports, as `sports_in_play` names
    them. Empty or omitted is every sport.

    A tennis leg is a match favourite's -- by the ATP/WTA/ITF rankings, else
    by price -- above TENNIS_ANY_C, or above TENNIS_LEADING_C while leading;
    on a NO-side ticket too, as YES, the only side Kalshi takes tennis on.
    """
    from app.domains.botstation.parley import engine, filters
    from app.domains.botstation.parley.models import ComboOrder

    spread_c = (filters.MAX_SPREAD_C if max_spread_c is None
                else max(0, int(max_spread_c)))
    hours = (filters.MAX_HOURS_TO_EXPIRY if max_hours is None
             else max(1, int(max_hours)))

    # Only these sports' series are read at all, which also makes a narrow
    # ticket a quicker scan. Empty is every sport, one that opened since the
    # desk listed them included.
    wanted = sorted({s.strip().lower() for s in (sports or []) if s and s.strip()})
    # Tennis favourites go by the rankings, scraped again -- alongside the
    # board scan rather than before it -- when they are over five days old.
    tennis_in = not wanted or "tennis" in wanted
    scrape = None
    if tennis_in and _rankings_age_s() >= RANKINGS_MAX_AGE_S:
        scrape = threading.Thread(target=refresh_rankings_if_stale,
                                  name="luck-rankings", daemon=True)
        scrape.start()
    runtime = _runtime()
    markets, scores = runtime._load_markets(
        cred, wanted, include_sub_events=True,
        tennis_score_floor=TENNIS_LEADING_C / 100.0)
    if scrape is not None:
        scrape.join(timeout=RANKINGS_SCRAPE_TIMEOUT_S)
    favourites = _tennis_favourites(markets) if tennis_in else {}
    offered = markets
    if no_side_only:
        # Every market from its NO side and from nothing else. A market that
        # cannot be bought on that side -- no quote there -- is not offered.
        # Tennis is the exception: Kalshi takes its matches on the YES side
        # only, and a favourite's YES is the same bet as NOT the other player.
        offered = [no for no in (m.as_no() for m in markets
                                 if not filters.is_tennis(m.sport))
                   if no is not None]
        offered += [m for m in markets if filters.is_tennis(m.sport)]

    frac = max(1, int(min_leg_c)) / 100.0
    # The CEILING was never offered, so it silently used the engine's 98%.
    # It matters more here than on a regular parlay: a long shot is built from
    # many legs, and one already-decided leg at 99c adds cost without adding
    # any real chance -- it just shortens the payout.
    ceiling = min(99, max(int(min_leg_c) + 1, int(max_leg_c))) / 100.0
    candidates, _rejected = filters.eligible_legs(
        offered, scores=scores, tracker=filters.PositionTracker(),
        tennis_min=frac, other_min=frac, soccer_min=frac,
        max_leg=ceiling, max_spread_c=spread_c, max_hours=hours,
        # The sides are already decided on a NO-side ticket. Offering soccer
        # from both would put a YES leg back on it.
        soccer_no_side=not no_side_only,
        # Tennis by this ticket's own rule -- the favourite, above 85c, or
        # above 75c while leading -- in place of every tennis gate the
        # regular engine has: the price lock, the need for a score, the
        # set-won-and-a-lead conditions. The band, spread and horizon above
        # still apply to it.
        tennis_rule=_tennis_rule(favourites),
        tennis_needs_score=False,
        tennis_lock_c=None)

    # Counted at every stage, by sport. Nothing here filters ON sport -- the
    # scan takes whatever Kalshi has open -- so "why is there never a cricket
    # leg" can only be answered by showing where cricket was lost, and the
    # honest answer is usually a gate the operator set or a collection that
    # does not carry the match. Without this the sheet shows twenty soccer
    # legs and no reason, and the bot looks like it has a sport list.
    eligible_by_sport = _by_sport(candidates)

    floor = max(0.0, float(min_volume_usd))
    if floor:
        candidates = [c for c in candidates if c.market.volume_usd >= floor]
    volume_by_sport = _by_sport(candidates)

    collection, candidates = runtime._daily_collection(cred, candidates)
    if not collection:
        return {"ok": False,
                "detail": "no open collection can host these legs"}
    hosted_by_sport = _by_sport(candidates)

    if no_side_only:
        # After the collection, not before: a game whose best prop the
        # collection cannot host may still have a leg it can.
        candidates = _one_per_game(candidates)
        candidates.sort(key=lambda c: ((c.market.implied_probability or 0.0),
                                       c.market.volume_usd), reverse=True)
    else:
        candidates.sort(key=lambda c: (c.market.volume_usd, c.market.volume),
                        reverse=True)
    # Then each event's own limit -- one of its markets, on nearly every
    # event -- with the ranking above deciding which of an event's legs stays.
    candidates = engine.within_event_limits(
        engine.collection_terms(cred, collection), candidates)
    picked = candidates[:max(2, int(max_legs))]
    if len(picked) < int(min_legs):
        return {"ok": False, "scanned": len(markets),
                "detail": f"only {len(picked)} legs clear the bar, "
                          f"{min_legs} required",
                "funnel": _funnel(markets, eligible_by_sport,
                                  volume_by_sport, hosted_by_sport,
                                  _by_sport(picked))}

    picked, combo_ticker, refused = _confirm(cred, runtime, collection,
                                             picked, int(min_legs))
    if refused:
        return {"ok": False, "scanned": len(markets), "detail": refused,
                "funnel": _funnel(markets, eligible_by_sport,
                                  volume_by_sport, hosted_by_sport,
                                  _by_sport(picked))}

    combo = ComboOrder(legs=picked, allow_same_event=True)
    token = uuid.uuid4().hex
    _sweep()
    _PREVIEWS[token] = {
        "expires": time.time() + PREVIEW_TTL_S,
        "tickers": [c.ticker for c in picked],
        "collection": collection,
        # The gates these legs were chosen under, carried to `place`. Its
        # re-check runs the same filters again, and on the engine's defaults
        # it would throw out every leg a widened spread had just admitted --
        # the operator would see a ticket built and then refused for legs
        # they were shown and approved.
        "max_spread_c": spread_c,
        "max_hours": hours,
        # The side of every leg, as shown. The re-check at placing reads the
        # board afresh, and a fresh read is YES-side: without this a NO leg
        # would be re-checked, and bought, as the opposite bet.
        "sides": {c.ticker: c.market.side for c in picked},
        "max_leg": ceiling,
        "combo_ticker": combo_ticker,
        # Placing re-reads only these sports: every leg is from one of them.
        "sports": wanted,
        "owner": owner,
    }
    return {
        "ok": True,
        "token": token,
        "scanned": len(markets),
        "eligible": len(candidates),
        "collection": collection,
        "probability": round(combo.combined_probability, 6),
        "fair_c": engine.theoretical_price_c(combo),
        # Echoed so the sheet can say what this ticket was filtered on
        # rather than the operator having to remember what they typed.
        "max_spread_c": spread_c,
        "max_hours": hours,
        "no_side_only": no_side_only,
        "sports": wanted,
        "tennis_rankings_at": _rankings_at() if tennis_in else None,
        # Kalshi accepted these exact legs as one combination. Legs can be
        # dropped on the sheet and the rest still stand: a side rule, an
        # event limit or a duplicate pair cannot be broken by taking a leg
        # away.
        "confirmed": True,
        "combo_ticker": combo_ticker,
        # The QUOTE, not just the price. price_c is the bid, and a bid on its
        # own cannot be judged: 89 is a different leg at 89/91 than it is at
        # 89/97, and the second is what a spread gate exists to keep out. The
        # sheet is where a leg is accepted or dropped by hand, so both sides
        # and the width belong on it.
        "legs": [{"ticker": c.ticker,
                  "outcome": c.market.outcome or c.ticker,
                  "market": c.market.title or c.ticker,
                  "event": c.market.event_ticker or "",
                  "sport": c.market.sport,
                  # The side's own quote. A soccer leg taken from the NO side
                  # is priced there too, and showing it the yes prices would
                  # put a 7c number beside a leg bought at 93c.
                  "side": c.market.side,
                  "price_c": c.market.bid_c,
                  "bid_c": c.market.bid_c,
                  "ask_c": c.market.ask_c,
                  "spread_c": c.market.spread_c,
                  "volume_usd": round(c.market.volume_usd, 2)}
                 for c in picked],
        "expires_in_s": PREVIEW_TTL_S,
        "funnel": _funnel(markets, eligible_by_sport, volume_by_sport,
                          hosted_by_sport, _by_sport(picked)),
    }


def _by_sport(items) -> dict[str, int]:
    """How many of these legs each sport contributed."""
    out: dict[str, int] = {}
    for item in items:
        sport = (getattr(item, "market", item).sport or "other").lower()
        out[sport] = out.get(sport, 0) + 1
    return out


def _funnel(markets, eligible: dict, volume: dict, hosted: dict,
            picked: dict) -> list[dict]:
    """One row per sport on the board, from live markets down to legs kept.

    Ordered by what is LIVE rather than by what survived, so a sport that
    contributed nothing still appears -- that row is the whole point. The
    columns narrow left to right, and whichever pair a sport falls between
    names the gate that stopped it.
    """
    live: dict[str, int] = {}
    for m in markets:
        sport = (m.sport or "other").lower()
        live[sport] = live.get(sport, 0) + 1
    return [{"sport": sport, "live": n,
             "eligible": eligible.get(sport, 0),
             "on_volume": volume.get(sport, 0),
             "hosted": hosted.get(sport, 0),
             "picked": picked.get(sport, 0)}
            for sport, n in sorted(live.items(), key=lambda kv: -kv[1])]


def _confirm(cred, runtime, collection: str, picked: list,
             min_legs: int) -> tuple[list, str, str]:
    """Have the exchange accept this exact combination before it is shown.

    Kalshi publishes some of its rules -- the events a collection hosts, the
    ones that take YES only, how many of an event's markets may go in -- and
    those are applied while the legs are chosen. Not all of them: two legs
    that say the same thing ("wins" and "wins by over 0.5") are refused as
    duplicates, and only the exchange knows that rule whole. Its lookup
    endpoint is gone, so the way to ask is to resolve the combination:
    create-or-return, no order, nothing spent, and placing the same legs
    later returns the same combined market.

    Legs it names as duplicates are dropped, the thinner first, and it is
    asked again -- the rule `place` has always used. Returns the legs it
    accepted, the combined market's ticker and no reason; or the reason not.
    """
    from app.domains.botstation import venue as kalshi
    from app.domains.botstation.parley import engine
    from app.services.kalshi_client import KalshiApiError

    legs = list(picked)
    for _ in range(12):
        try:
            market = kalshi.combined_market(cred, collection,
                                            engine.selected_markets(legs))
        except Exception as exc:                        # noqa: BLE001
            cause = exc.__cause__
            # A refusal is the exchange's answer. Anything else -- no answer,
            # a rate limit, a rejected key -- is no answer at all, and its
            # body is not repeated: a 401's can carry the key id.
            if not (isinstance(cause, KalshiApiError)
                    and 400 <= cause.status_code < 500
                    and cause.status_code not in (401, 403, 429)):
                return legs, "", ("Kalshi could not be asked whether it "
                                  "accepts this combination -- try again")
            named = runtime._redundant_legs(str(exc))
            clash = [c for c in legs if c.ticker in named]
            if not named or len(clash) < 2 or len(legs) <= min_legs:
                return legs, "", ("Kalshi would not accept this combination "
                                  f"({_refusal_code(cause.body)})")
            drop = min(clash, key=lambda c: c.market.volume_usd)
            legs = [c for c in legs if c.ticker != drop.ticker]
            logger.info("luck preview: dropped %s as redundant (%d legs left)",
                        drop.ticker, len(legs))
            continue
        ticker = market.get("ticker") or ""
        if not ticker:
            return legs, "", ("Kalshi did not return a combined market for "
                              "these legs")
        return legs, ticker, ""
    return legs, "", "could not assemble a combination the exchange accepts"


def _refusal_code(body: str) -> str:
    """The exchange's error code, e.g. invalid_parameters -- not its text."""
    try:
        err = (json.loads(body) or {}).get("error") or {}
        return str(err.get("code") or "refused")
    except (ValueError, AttributeError):
        return "refused"


def place(cred, token: str, *, tenant_slug: str = "",
          tickers: list[str] | None = None,
          min_usd: float = 5.0, max_usd: float = 7.5,
          min_legs: int = 5, owner: str = "") -> dict:
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
    # Another operator's preview reads exactly like an expired one: a token is
    # not a way to buy what someone else was shown, nor to learn it exists.
    if held is None or held.get("owner", "") != owner:
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
    markets, scores = runtime._load_markets(
        cred, held.get("sports") or [], include_sub_events=True)
    # Each leg on the side it was shown on. The board reads YES-side, and a
    # leg previewed as "Ecuador do not win" must be re-checked -- and bought
    # -- as that, never as its opposite.
    sides = held.get("sides") or {}
    shown = []
    for market in markets:
        if market.ticker not in wanted:
            continue
        if sides.get(market.ticker) == "no":
            market = market.as_no()
            if market is None:                          # no longer quoted there
                continue
        shown.append(market)
    # The price bar is deliberately wide here: these legs already passed it
    # once. What is being re-checked is that they are still LIVE and still
    # quoted, not whether they would be chosen again.
    candidates, _ = filters.eligible_legs(
        shown, scores=scores,
        tracker=filters.PositionTracker(),
        tennis_min=0.01, other_min=0.01, soccer_min=0.01,
        # On the preview's own gates, not the engine's. A leg admitted by a
        # widened spread would otherwise be thrown out here, and the ticket
        # refused for legs the operator was shown and kept. Tennis likewise:
        # the re-check must not apply a rule the selection did not.
        max_spread_c=int(held.get("max_spread_c", filters.MAX_SPREAD_C)),
        max_hours=int(held.get("max_hours", filters.MAX_HOURS_TO_EXPIRY)),
        max_leg=float(held.get("max_leg", filters.MAX_LEG_PROBABILITY)),
        # The sides were fixed when the legs were shown; offering soccer from
        # both again could swap a leg for its opposite.
        soccer_no_side=False,
        # A tennis leg was judged by this ticket's own rule when it was shown;
        # the regular engine's tennis gates must not refuse it now.
        tennis_rule=lambda market, score: (True, "previewed"),
        tennis_needs_score=False, tennis_lock_c=None)

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


def start(fn, *args, job_owner: str = "", **kwargs) -> str:
    """Run one luck-bot call in the background. Returns its id.

    ``job_owner`` is the operator who started it; `job` answers only them."""
    import threading

    _sweep_jobs()
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {"status": "running", "started": time.time(),
                     "result": None, "error": None, "done_at": None,
                     "owner": job_owner}
    thread = threading.Thread(target=_run_job,
                              args=(job_id, fn, *args), kwargs=kwargs,
                              daemon=True)
    thread.start()
    return job_id


def job(job_id: str, owner: str = "") -> dict | None:
    """A job's progress, for the operator who started it. Anyone else gets
    None -- the same answer as a job that does not exist."""
    held = _JOBS.get(job_id)
    if held is None or held.get("owner", "") != owner:
        return None
    out = {"status": held["status"],
           "elapsed_s": round(time.time() - held["started"], 1)}
    if held["status"] == "done":
        out["result"] = held["result"]
    elif held["status"] == "failed":
        out["error"] = held["error"]
    return out
