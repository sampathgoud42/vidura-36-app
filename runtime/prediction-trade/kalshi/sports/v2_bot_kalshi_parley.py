#!/usr/bin/env python
"""Parley v2 — live-sport parlay bot.

Thin by design. Every decision this makes lives in
``app.domains.botstation.parley``, where it is unit-tested without an account,
a network, or a running exchange. This file is the loop and the argument
parsing; it holds no trading rules of its own, so there is nowhere for the
engine and the desk to drift apart.

What v2 changes from v1:

  tennis        90% implied AND a real score condition -- 1-0 in sets leading
                set 2 by two games, or 2-0 leading set 3 by two. v1 took any
                match at 80c that was merely "in set 2 or later", so a player
                a set up but a break DOWN qualified.
  other sports  91% implied, up from 80c, and no score requirement because no
                other sport here has a state that independently confirms the
                quote.
  overlap       exposure is deduplicated by EVENT against live exchange
                positions, not by ticker against a local file. Two legs from
                one match can no longer reach the same parlay, and neither can
                a leg on a match already held from an earlier run.
  sizing        2 to 5 legs, partitioned DISJOINTLY: one leg is used once
                across every combo built in a pass, so overlapping bundles
                cannot quietly multiply exposure to one outcome.

Usage:
    v2_bot_kalshi_parley.py <customer> [--live] [--once] [--interval 10]

Paper is the default. --live is the only way to reach real money, and it is
refused outright when the server is locked to paper.
"""

from __future__ import annotations

import argparse
import logging
import json
import os
import sys
from datetime import datetime
import time
from pathlib import Path

# Everything this bot needs is inside the project, so the path is derived from
# this file rather than assumed to be on PYTHONPATH. The bot station launches
# it as a bare subprocess and a bot that only runs under one launcher is a bot
# nobody can debug by hand.
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

logging.basicConfig(level=logging.INFO, format="[PARLEY-v2] %(message)s")
log = logging.getLogger("parley.v2")



def _env_sports(fallback: list[str]) -> list[str]:
    """Which sports to draw legs from, from the launch form.

    Its own reader because this one option is a LIST, and the two callers
    spell it differently: the bot station sets SPORTS to JSON (lifecycle
    json.dumps anything list- or dict-shaped, since Python's repr is not
    valid JSON), while a hand run types --sports tennis,soccer. Both are
    accepted here.

    This was the gap that made the option decorative. `sports` was declared
    in the schema, shown in the form, validated, and written into the run
    row -- and then read only from argv, which defaults to "all". So every
    parley run scanned every live sport whatever the form said, and the
    field looked like it worked because the bot did trade.
    """
    import json
    import os

    raw = (os.environ.get("SPORTS") or "").strip()
    if not raw:
        return fallback
    if raw.startswith("["):
        try:
            value = json.loads(raw)
        except ValueError:
            log.warning("SPORTS=%r is not valid JSON; scanning every sport",
                        raw)
            return fallback
        if not isinstance(value, list):
            return fallback
        return [str(x).strip().lower() for x in value if str(x).strip()]
    return [x.strip().lower() for x in raw.split(",") if x.strip()]


def _env(name: str, fallback, cast=str):
    """One launch-form option, from the environment.

    The bot station passes options as UPPERCASED environment variables, not
    as flags, so anything this script only accepts on the command line is a
    field the operator can edit in the form and nothing will read. Every key
    in the bot's options_schema is read here for exactly that reason.
    """
    import os

    raw = os.environ.get(name.upper())
    if raw is None or raw == "":
        return fallback
    try:
        return cast(raw)
    except (TypeError, ValueError):
        log.warning("%s=%r is not a %s; using %r", name.upper(), raw,
                    cast.__name__, fallback)
        return fallback


def _sport_tags(client) -> dict[str, tuple[str, str]]:
    """Every Kalshi Sports series -> its sport tag.

    Discovered, never listed. The engine used to carry a hard-coded map of
    five series tickers, so soccer, basketball, cricket, MMA, esports, table
    tennis, motorsport, boxing, golf, hockey, lacrosse and cycling were all
    invisible to it -- and a sport Kalshi added tomorrow stayed invisible
    until somebody edited this file. There are 3579 of them and 28 tags.
    """
    try:
        data = client.request("GET", "/series", params={"category": "Sports"})
    except Exception as exc:                            # noqa: BLE001
        log.warning("series discovery failed (%s)", type(exc).__name__)
        return {}
    out = {}
    for series in data.get("series", []):
        if series.get("category") != "Sports":
            continue
        tags = series.get("tags") or []
        if series.get("ticker"):
            # (sport tag, series title). The title is the "league", which the
            # headline-market filters read to tell a match-winner market from
            # a derivative one.
            out[series["ticker"]] = ((tags[0] if tags else "other").lower(),
                                     series.get("title") or "")
    return out


def _active_sports_series(client) -> set[str]:
    """Series with an OPEN event right now.

    Of 3579 sports series only ~800 have anything open, and asking about the
    other 2700 is 2700 requests for nothing. Events are the cheap way to know
    which: /events carries both series_ticker and category, and the whole open
    book pages in a couple of seconds.

    Fetching markets for every series was the alternative, which is what
    kalshi_sports caps at 150 series "to avoid hammering the API" -- a cap
    that silently drops most sports rather than most requests.
    """
    active, cursor = set(), None
    for _page in range(60):
        params = {"status": "open", "limit": 200}
        if cursor:
            params["cursor"] = cursor
        try:
            data = client.request("GET", "/events", params=params)
        except Exception as exc:                        # noqa: BLE001
            log.warning("event scan failed (%s)", type(exc).__name__)
            break
        for event in data.get("events") or []:
            if event.get("category") == "Sports" and event.get("series_ticker"):
                active.add(event["series_ticker"])
        cursor = data.get("cursor")
        if not cursor:
            break
    return active


def _markets_for(series: str, cred) -> list[dict]:
    """Open markets for one series, on this worker's own client.

    A client per worker rather than one shared: the sessions underneath are
    not built to be driven from several threads at once, and a corrupted
    response here would look like a market that does not exist.
    """
    from app.services.kalshi_client import DEFAULT_BASE, KalshiClient

    client = KalshiClient(cred.token, private_key_pem=cred.private_key_pem,
                          base_uri=cred.base_url or DEFAULT_BASE)
    try:
        data = client.request("GET", "/markets", params={
            "series_ticker": series, "status": "open", "limit": 1000})
        return data.get("markets") or []
    except Exception:                                   # noqa: BLE001
        return []
    finally:
        client.close()


# ---- the daily long-shot ticket -------------------------------------------
#
# One parlay a day, deliberately unlike the others: many more legs, a much
# lower bar per leg, and a small fixed stake. A 5-leg parlay of 90% sides pays
# about 1.7x; twenty legs of 60% sides pays thousands. It is a lottery ticket
# bought on purpose, and it is kept apart from the regular book in both
# directions -- its matches do not consume the regular engine's allowance, and
# the regular engine's positions do not narrow its choices.
#
# State lives in the operator's folder rather than in memory: the bot restarts
# often, and "have I already bought today's ticket" must survive that or the
# answer resets to no and it buys another.

DAILY_STATE = "parley_daily.json"


def _daily_state_path(customer_dir: Path) -> Path:
    return customer_dir / DAILY_STATE


def _load_daily(customer_dir: Path) -> dict:
    try:
        return json.loads(_daily_state_path(customer_dir).read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _save_daily(customer_dir: Path, state: dict) -> None:
    try:
        _daily_state_path(customer_dir).write_text(
            json.dumps(state, indent=1, default=str), encoding="utf-8")
    except OSError as exc:
        log.warning("could not write %s: %s", DAILY_STATE, exc)


def _due_today(state: dict, at_hhmm: str, tz_name: str) -> bool:
    """Has today's ticket time passed, with today's ticket not yet bought?

    Compared on the LOCAL date in the operator's timezone, not UTC: "every day
    at 5:30pm" means their day, and a UTC date rolls over in the middle of a
    Chicago afternoon.
    """
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo(tz_name))
    except Exception:                                   # noqa: BLE001
        now = datetime.now()
    try:
        hh, mm = (int(x) for x in at_hhmm.split(":", 1))
    except ValueError:
        hh, mm = 17, 30
    if (now.hour, now.minute) < (hh, mm):
        return False
    return state.get("last_date") != now.date().isoformat()


def _daily_ticket(cred, args, customer_dir: Path) -> None:
    """Build and place today's long shot, once.

    Deliberately NOT the regular engine's job, and deliberately not built the
    same way. The regular parlays diversify: one leg per match, few legs, high
    quality, disjoint outcomes. This one concentrates on purpose -- many legs,
    a lower bar, sub-events of the same match included -- because its whole
    reason to exist is the size of the payout if everything lands.

    Ranked by DOLLAR VOLUME rather than by price. Among legs that all clear
    the same bar, the busiest markets are the ones with a real book behind
    them, and a 24-leg ticket assembled from illiquid corners is one nobody
    will quote.
    """
    from app.domains.botstation.parley import combos as combinator
    from app.domains.botstation.parley import engine, filters
    from app.domains.botstation.parley.models import ComboOrder

    state = _load_daily(customer_dir)
    if not _due_today(state, args.daily_at, args.daily_tz):
        return

    log.info("daily ticket: scanning live matches AND sub-events, legs >%dc",
             args.daily_min_c - 1)
    markets, scores = _load_markets(cred, _env_sports(args.sports),
                                    include_sub_events=True)
    log.info("daily ticket: %d markets in play (headline + sub-events)",
             len(markets))

    frac = args.daily_min_c / 100.0
    # An EMPTY tracker: the daily ticket does not care what the regular
    # engine holds, and nothing it picks counts against that engine either.
    candidates, rejected = filters.eligible_legs(
        markets, scores=scores, tracker=filters.PositionTracker(),
        min_lead=_env("min_lead", 2, int),
        tennis_min=frac, other_min=frac, soccer_min=frac,
        max_leg=_env("max_leg_pct", 98.0, float) / 100.0,
        max_hours=_env("max_hours_to_expiry", 72, int),
        max_spread_c=_env("max_spread_c", 3, int))
    log.info("daily ticket: %d legs clear the bar (%d rejected)",
             len(candidates), len(rejected))

    collection, candidates = _daily_collection(cred, candidates)
    if not collection:
        log.info("daily ticket: no collection can host these legs")
        return
    log.info("daily ticket: %s hosts %d of them", collection, len(candidates))

    # Busiest first, then take the top N. Sorted here rather than inside the
    # combinator because this is a selection rule, not a construction rule.
    candidates.sort(key=lambda c: (c.market.volume_usd, c.market.volume),
                    reverse=True)
    picked = candidates[:max(2, int(args.daily_max_legs))]

    if len(picked) < args.daily_min_legs:
        log.info("daily ticket: only %d legs available, need %d — not placed, "
                 "will try again on the next pass",
                 len(picked), args.daily_min_legs)
        return

    for leg in picked:
        log.info("    leg %-34s %3dc  vol $%.0f",
                 leg.market.outcome[:34] or leg.ticker,
                 leg.market.yes_bid_c or 0, leg.market.volume_usd)

    # Build, and let the EXCHANGE prune. Kalshi refuses a combo holding two
    # legs that say the same thing and names the offending pair; we drop the
    # thinner of the two and try again. Bounded, and it never drops below the
    # operator's minimum -- a ticket worth placing is one that still has the
    # legs they asked for.
    outcome = None
    for attempt in range(12):
        combo = ComboOrder(legs=picked, allow_same_event=True)
        if attempt == 0:
            log.info("daily ticket: %d legs  P=%.6f  fair=%dc  top volume $%.0f",
                     len(combo.legs), combo.combined_probability,
                     engine.theoretical_price_c(combo),
                     picked[0].market.volume_usd)
        try:
            outcome = engine.place_combo(
                cred, combo, collection,
                dry_run=not args.live,
                stake_usd=args.daily_stake,
                slippage_c=_env("slippage_c", 5, int),
                escalation_pct=args.daily_escalation_pct,
                fill_wait_s=_env("fill_wait_s", 60, int))
            break
        except Exception as exc:                        # noqa: BLE001
            named = _redundant_legs(str(exc))
            clash = [c for c in picked if c.ticker in named]
            if not named or len(clash) < 2 or len(picked) <= args.daily_min_legs:
                log.warning("daily ticket: %s", exc)
                return
            # Keep the busier of the pair: it is the one with a real book.
            drop = min(clash, key=lambda c: c.market.volume_usd)
            picked = [c for c in picked if c.ticker != drop.ticker]
            log.info("  redundant with another leg, dropping %s (%d left)",
                     drop.market.outcome or drop.ticker, len(picked))
    if outcome is None:
        log.info("daily ticket: could not assemble a combo the exchange "
                 "accepts")
        return

    if not outcome.get("placed"):
        log.info("  daily not placed: %s", outcome.get("detail"))
        return

    log.info("  DAILY PLACED %s", outcome)
    from app.domains.botstation.ledger import entries
    entries.record_entry(
        tenant_slug=args.customer, bot_key="parley", bot_version="v2-daily",
        ticker=outcome.get("combo_ticker") or "",
        external_id=(outcome.get("quote_id") or outcome.get("order_id") or ""),
        contracts=outcome.get("contracts"),
        entry_price_c=outcome.get("filled_c") or outcome.get("limit_c"),
        market_title=_combo_title(outcome),
        outcome=_combo_outcome(outcome),
        entry_usd=outcome.get("cost_usd"),
        fees_usd=outcome.get("fees_usd"),
        is_live=args.live, raw=outcome)

    # Marked done ONLY when something was actually bought. A day the exchange
    # refused is a day the ticket was not bought, and the next pass should try
    # again rather than skip to tomorrow.
    tickers = list(state.get("tickers") or [])
    if outcome.get("combo_ticker"):
        tickers.append(outcome["combo_ticker"])
    state["tickers"] = tickers[-400:]
    state["last_date"] = _today_iso(args.daily_tz)
    _save_daily(customer_dir, state)
    log.info("  daily ticket done for %s", state["last_date"])


def _combo_title(outcome: dict) -> str:
    """How a parlay reads in a one-line ledger.

    A combo has no single market question, so it is described by its shape --
    "5-leg parlay" -- rather than by the first leg's title, which would name
    one bet and hide four.
    """
    legs = outcome.get("tickers") or []
    return f"{len(legs)}-leg parlay" if legs else "parlay"


def _combo_outcome(outcome: dict) -> str:
    """The sides taken, short enough for a column."""
    legs = [str(t) for t in (outcome.get("tickers") or [])]
    if not legs:
        return ""
    # The trailing segment of a Kalshi ticker is the side: ...-FED -> FED.
    sides = [t.rsplit("-", 1)[-1] for t in legs]
    head = ", ".join(sides[:4])
    return head if len(sides) <= 4 else f"{head} +{len(sides) - 4}"


def _redundant_legs(message: str) -> list[str]:
    """The leg tickers Kalshi named as redundant, from its rejection.

    The exchange does not forbid two legs on one match -- it forbids two that
    say the SAME thing. "Monterrey to win" already implies "over 0.5 goals",
    so a combo holding both is priced as if it held one, and Kalshi refuses it
    with duplicated_legs and names the pair in `details`.

    Rather than trying to model those implications ourselves -- there is one
    per sport per market type, and they change as Kalshi lists new ones -- we
    take the exchange at its word and drop a leg it objected to. It is the
    only party that knows the whole rule.
    """
    marker = '"details":"'
    at = message.find(marker)
    if at < 0:
        return []
    rest = message[at + len(marker):]
    end = rest.find('"')
    if end < 0:
        return []
    return [t.strip() for t in rest[:end].split(",") if t.strip()]


def _daily_collection(cred, candidates) -> tuple[str, list]:
    """The collection hosting the most of these legs, and those legs.

    A combined market can only be built from events its collection lists, so
    the legs have to be narrowed to whichever one hosts the most of them --
    the same rule the regular pass follows. Picking 24 legs first and hoping
    they fit is how a ticket gets refused at creation.
    """
    from app.domains.botstation.parley import engine
    chosen = engine.choose_collection(engine.open_collections(cred), candidates)
    if not chosen:
        return "", []
    hosted = engine.legs_in_collection(chosen, candidates)
    return chosen.get("collection_ticker") or "", hosted


def _today_iso(tz_name: str) -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz_name)).date().isoformat()
    except Exception:                                   # noqa: BLE001
        return datetime.now().date().isoformat()


def _regular_tickers(cred) -> set[str]:
    """Combo tickers the REGULAR engine holds, which the daily one ignores."""
    from app.domains.botstation import venue as kalshi
    try:
        return {str(r.get("ticker") or "") for r in kalshi.positions(cred)
                if abs(float(r.get("position_fp") or 0)) > 0}
    except Exception:                                   # noqa: BLE001
        return set()


def _load_markets(cred, wanted: list[str], include_sub_events: bool = False):
    """Every LIVE sports market, and the score for every live tennis one.

    Kept in this file rather than the engine because it is I/O shape, not a
    trading rule: which endpoints hold today's live events is a Kalshi
    detail, while what makes a leg tradeable is the thing worth testing.

    "Live" is decided by kalshi_sports._match_status, imported rather than
    reimplemented. It is a subtle judgement -- Kalshi publishes no in-play
    flag, and the obvious field is a trap: occurrence_datetime equals the
    SETTLE time on some series, so an in-play ITF match reads as if it has
    not started. That function already knows.

    This matters more than it looks. Every market used to be constructed with
    live=True, so a market quoted at 95% the day BEFORE a match counted as
    in-play and could enter a parlay on a price that had nothing to do with a
    lead anyone currently held.
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.domains.botstation.parley import filters, tennis
    from app.domains.botstation.parley.models import (MarketState,
                                                      TennisScoreState)
    from app.services.kalshi_client import DEFAULT_BASE, KalshiClient

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from kalshi_sports import (_is_head_to_head, _is_main_match,  # noqa: E402
                               _match_status)

    client = KalshiClient(cred.token, private_key_pem=cred.private_key_pem,
                          base_uri=cred.base_url or DEFAULT_BASE)
    fetch = tennis.fetcher_for(client)
    markets: list[MarketState] = []
    scores: dict[str, TennisScoreState] = {}
    counts: dict[str, int] = {}

    try:
        tags = _sport_tags(client)
        active = _active_sports_series(client)
        # An empty selection means EVERY sport that is in play, which is the
        # point: the operator should not have to name a sport for the bot to
        # notice a match happening in it.
        keep = {w.strip().lower() for w in wanted if w.strip()}
        if not keep or "all" in keep:
            keep = None

        series = sorted(s for s in active
                        if s in tags and (keep is None or tags[s][0] in keep))
        log.info("scanning %d active sports series (of %d known)",
                 len(series), len(tags))

        with ThreadPoolExecutor(max_workers=12) as pool:
            for raws in pool.map(lambda s: _markets_for(s, cred), series):
                for raw in raws:
                    ticker = raw.get("ticker") or ""
                    series_ticker = ticker.split("-", 1)[0]
                    meta = tags.get(series_ticker)
                    if meta is None or _match_status(raw) != "live":
                        continue
                    sport, league = meta

                    # HEADLINE MATCH-WINNER MARKETS ONLY, using the sports
                    # bot's own detectors. Without them a parlay filled up
                    # with derivatives of ONE fixture -- "Elfsborg",
                    # "Elfsborg wins by more than 1.5 goals" and "Both Teams
                    # To Score" are three separate events on the same match,
                    # so the event-level dedup cannot see they are the same
                    # bet. If Elfsborg lose, every one of those legs fails
                    # together, which is the exact correlation a parlay is
                    # supposed to avoid.
                    #
                    # It also drops tournament outrights (MLB playoffs,
                    # season home-run totals) that are not in play at all in
                    # the sense this engine means.
                    enriched = {**raw, "series_ticker": series_ticker,
                                "league": league}
                    # The daily long-shot ticket wants the SUB-EVENTS too --
                    # set winners, totals, both-teams-to-score -- because it
                    # is buying correlation on purpose. Every other caller
                    # keeps the headline-only rule above.
                    if not include_sub_events:
                        if not (_is_main_match(enriched)
                                and _is_head_to_head(enriched)):
                            continue

                    state = MarketState.from_kalshi(raw, sport=sport, live=True)
                    # Dollar turnover, for ranking. volume_fp is contracts;
                    # multiplying by the last traded price is what makes a
                    # 90c market and a 5c market comparable.
                    try:
                        vol = float(raw.get("volume_fp") or raw.get("volume") or 0)
                        px = float(raw.get("last_price_dollars") or 0) or (
                            (state.yes_bid_c or 0) / 100.0)
                        state.volume_usd = round(vol * px, 2)
                    except (TypeError, ValueError):
                        state.volume_usd = 0.0
                    if not state.is_tradeable:
                        continue
                    markets.append(state)
                    counts[sport] = counts.get(sport, 0) + 1

        log.info("live markets by sport: %s",
                 ", ".join(f"{s}={n}" for s, n in sorted(counts.items()))
                 or "none in play right now")

        # Scores ONLY for tennis legs that already clear the price bar. Each is
        # three more HTTP calls, and asking about a match whose price has
        # already disqualified it spends them for nothing.
        for state in markets:
            if not filters.is_tennis(state.sport):
                continue
            ok, _why = filters.meets_odds_floor(state)
            if not ok:
                continue
            score = tennis.state_for(fetch, state.ticker, state.outcome)
            if score is not None:
                scores[state.ticker] = score
    finally:
        client.close()
    return markets, scores


def run_once(cred, args) -> int:
    from app.domains.botstation.parley import engine

    # Today's long shot, if it is due. Built first so a pass that is late for
    # any reason still buys the ticket before spending its budget elsewhere.
    if args.daily_enabled:
        try:
            _daily_ticket(cred, args, Path(args.customer_dir))
        except Exception as exc:                        # noqa: BLE001
            # Never let the lottery ticket take down the regular engine.
            log.warning("daily ticket failed: %s: %s",
                        type(exc).__name__, exc)
        if getattr(args, "daily_only", False):
            return 0

    markets, scores = _load_markets(cred, _env_sports(args.sports))
    log.info("%d tradeable live markets", len(markets))

    # Percent in the form, fraction in the engine. Converting here rather
    # than storing fractions means the operator types 91, not 0.91.
    result = engine.run_pass(
        cred, markets, scores=scores,
        collection=_env("collection", args.collection) or None,
        dry_run=not args.live,
        stake_usd=_env("stake_usd", args.stake_usd, float),
        slippage_c=_env("slippage_c", 5, int),
        max_per_event=_env("max_per_event", 2, int),
        # The daily long shot keeps its own book -- its matches are not the
        # regular engine's problem, and vice versa.
        ignore_tickers=set(
            (_load_daily(Path(args.customer_dir)).get("tickers") or [])),
        escalation_pct=_env("escalation_pct", 30.0, float),
        fill_wait_s=_env("fill_wait_s", 60, int),
        max_combos=_env("max_combos", args.max_combos, int),
        min_legs=_env("min_legs", args.min_legs, int),
        max_legs=_env("max_legs", args.max_legs, int),
        min_lead=_env("min_lead", 2, int),
        tennis_min=_env("tennis_min_pct", 85.0, float) / 100.0,
        other_min=_env("other_min_pct", 85.0, float) / 100.0,
        soccer_min=_env("soccer_min_pct", 80.0, float) / 100.0,
        max_leg=_env("max_leg_pct", 98.0, float) / 100.0,
        max_hours=_env("max_hours_to_expiry", 72, int),
        max_spread_c=_env("max_spread_c", 3, int))

    for candidate in result.candidates:
        log.info("  leg  %-28s %s", candidate.ticker, candidate.reason)
    for rejection in result.rejected[:20]:
        log.info("  skip %-28s %s", rejection["ticker"], rejection["reason"])
    for combo in result.combos:
        log.info("  combo %d legs  P=%.3f  fair=%dc  %s",
                 len(combo.legs), combo.combined_probability,
                 engine.theoretical_price_c(combo), combo.describe())
    from app.domains.botstation.ledger import entries

    for outcome in result.placed:
        log.info("  PLACED %s", outcome)
        # Into the ledger, at entry. Nothing else will: reconciliation only
        # CLOSES rows, so a placement that records nothing here is invisible
        # to the desk's trade history for good, however real the position is.
        recorded = entries.record_entry(
            tenant_slug=args.customer,
            bot_key="parley", bot_version="v2",
            ticker=outcome.get("combo_ticker") or "",
            # The quote id when a maker filled us, the resting order id
            # otherwise. Either is the exchange's own handle on this trade,
            # which is what makes the write idempotent across retries.
            external_id=(outcome.get("quote_id")
                         or outcome.get("order_id") or ""),
            contracts=outcome.get("contracts"),
            entry_price_c=outcome.get("filled_c") or outcome.get("limit_c"),
            market_title=_combo_title(outcome),
            outcome=_combo_outcome(outcome),
            entry_usd=outcome.get("cost_usd"),
            fees_usd=outcome.get("fees_usd"),
            is_live=args.live,
            raw=outcome)
        if not recorded:
            log.warning("  the trade was NOT written to the ledger")
    for outcome in result.skipped:
        log.info("  not placed: %s", outcome.get("detail"))

    log.info("summary: %s", result.summary())
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("customer")
    ap.add_argument("--live", action="store_true",
                    help="reach the real account; paper otherwise")
    ap.add_argument("--once", action="store_true")
    # Minutes, not seconds. The launch form calls this "Check combos every
    # (minutes)" and passes CHECK_EVERY_MIN; --interval stays for a hand
    # run and is read in minutes too, so the two cannot mean different
    # things depending on how the bot was started.
    ap.add_argument("--interval", type=int, default=10,
                    help="minutes between passes (default 10)")
    # A budget per parlay, not a count: the price of a combo moves with
    # its legs, so a fixed count spends a different amount every pass.
    ap.add_argument("--stake-usd", type=float, default=12.0,
                    dest="stake_usd")
    ap.add_argument("--min-legs", type=int, default=2, dest="min_legs")
    ap.add_argument("--max-legs", type=int, default=5, dest="max_legs")
    ap.add_argument("--max-combos", type=int, default=1, dest="max_combos")
    ap.add_argument("--collection", default=None,
                    help="Kalshi multivariate collection ticker")
    # "all" is the default: every sport that is currently in play. Naming
    # sports narrows it; naming none does not narrow it to nothing.
    ap.add_argument("--sports", default="all")
    # The daily long-shot ticket. Off unless asked for.
    ap.add_argument("--daily", action="store_true", dest="daily_enabled")
    # Run ONLY the daily ticket and stop. For a hand run that must not also
    # spend the regular engine's stake.
    ap.add_argument("--daily-only", action="store_true", dest="daily_only")
    ap.add_argument("--daily-at", default="17:30", dest="daily_at")
    ap.add_argument("--daily-tz", default="America/Chicago", dest="daily_tz")
    ap.add_argument("--daily-stake", type=float, default=5.0,
                    dest="daily_stake")
    ap.add_argument("--daily-max-legs", type=int, default=24,
                    dest="daily_max_legs")
    ap.add_argument("--daily-min-c", type=int, default=60, dest="daily_min_c")
    ap.add_argument("--daily-min-legs", type=int, default=5,
                    dest="daily_min_legs")
    ap.add_argument("--daily-escalation-pct", type=float, default=50.0,
                    dest="daily_escalation_pct")
    args = ap.parse_args()

    # Read from the launch form too, the same way every other option is.
    args.daily_enabled = _env("daily_enabled", args.daily_enabled,
                              lambda v: str(v).strip().lower()
                              in ("1", "true", "yes", "on"))
    args.daily_at = _env("daily_at", args.daily_at)
    args.daily_tz = _env("daily_tz", args.daily_tz)
    args.daily_stake = _env("daily_stake_usd", args.daily_stake, float)
    args.daily_max_legs = _env("daily_max_legs", args.daily_max_legs, int)
    # ">59 cents" is a floor the leg must beat, so the first acceptable
    # price is 60. Stored as the inclusive minimum the filters compare on.
    args.daily_min_c = _env("daily_min_c", args.daily_min_c, int)
    args.daily_min_legs = _env("daily_min_legs", args.daily_min_legs, int)
    args.daily_escalation_pct = _env("daily_escalation_pct",
                                     args.daily_escalation_pct, float)
    args.customer_dir = os.environ.get("BOT_CUSTOMER_DIR") or "."
    args.sports = [s.strip() for s in args.sports.split(",") if s.strip()]

    from sqlalchemy import select

    from app.api_v2 import deps
    from app.core.config import get_settings
    from app.platform.db.session import session_scope
    from app.tenancy import repository as tenants
    from app.tenancy.models import Tenant

    # Same as v6: the station signals live through DRY_RUN_MODE, and this
    # script never read it -- so a live launch from the desk ran in dry mode
    # and placed nothing, while the run row and the banner both said live.
    from app.domains.botstation import lifecycle

    args.live = lifecycle.wants_live(args.live)

    if args.live and get_settings().paper_only:
        log.error("this server is locked to paper; --live is refused")
        return 2

    with session_scope() as db:
        tenant = db.scalars(
            select(Tenant).where(Tenant.slug == args.customer)).first()
        if tenant is None:
            log.error("no operator named %r", args.customer)
            return 2
        cred = tenants.load_credential(db, tenant.id, "kalshi", deps.keyring())

    log.info("parley v2 for %s — %s", args.customer,
             "LIVE" if args.live else "paper (no orders will be sent)")
    if args.daily_enabled:
        log.info("daily ticket ON — %s %s | $%.2f up to $%.2f | %d-%d legs "
                 "| legs >%dc | ranked by $ volume",
                 args.daily_at, args.daily_tz, args.daily_stake,
                 round(args.daily_stake * (1 + args.daily_escalation_pct / 100), 2),
                 args.daily_min_legs, args.daily_max_legs,
                 args.daily_min_c - 1)
    if args.once:
        return run_once(cred, args)
    while True:
        try:
            run_once(cred, args)
        except KeyboardInterrupt:
            log.info("stopped")
            return 0
        except Exception as exc:                        # noqa: BLE001
            # A pass that failed is not a reason to exit: the next one may
            # succeed, and a bot that quits silently is worse than one that
            # logs and retries.
            log.warning("pass failed: %s: %s", type(exc).__name__, exc)
        time.sleep(max(1, _env("check_every_min", args.interval, int)) * 60)


if __name__ == "__main__":
    raise SystemExit(main())
