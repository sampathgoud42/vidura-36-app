#!/usr/bin/env python3
"""
kalshi_sports.py — async Kalshi **sports** market discovery + filtering.
=======================================================================
Modular, strongly-typed, async helpers over the *current* Kalshi Trade API v2
(``https://.../trade-api/v2``).  Only read-only ``GET`` endpoints are used:

    GET /series   ?category=Sports     → the sports taxonomy
    GET /markets  ?series_ticker=…&status=open
    GET /markets/{ticker}              → one market
    GET /events/{event_ticker}?with_nested_markets=true

API notes (cross-checked live, since the legacy v1 *order* endpoint is
deprecated — but these read endpoints are current):
  • A series carries the **sport** in ``tags`` (e.g. ["Soccer"]) and the
    **league / tournament** in ``title`` (e.g. "English Premier League").
    Sports series have ``category == "Sports"``.
  • A market's tradeable state is ``status == "active"``; prices are dollar
    strings (``yes_bid_dollars`` …); size/volume are fixed-point strings
    (``volume_fp`` = contracts).  Kalshi reports **contract** volume, so USD
    volume is *estimated* as ``volume_fp * last_price_dollars``.
  • Kalshi has **no explicit live/scheduled flag**; it is derived from
    ``occurrence_datetime`` / ``expected_expiration_time`` (see _match_status).
  • Kalshi does **not** expose live scoreboards (innings/sets/goals).
    get_the_market_scores_kalshi() therefore returns the market's implied
    probabilities + a per-sport score *skeleton*, populated only if you wire a
    real scores provider into ``_external_scores``.

Auth/HTTP reuse the v1 ``KalshiClient`` (RSA-PSS signed requests).

Every filter is async and chainable: pass ``markets=<prev result>`` to filter an
existing list (no I/O), or omit it to fetch live data first.

    sport = await filter_by_sport("Tennis")
    epl   = await filter_by_league("English Premier League")
    liq   = await filter_by_min_volume(5000, markets=sport)
    picks = await filter_by_sport_league_min_volume("Soccer", "English Premier League", 1000)
    live  = await filter_live_matches(picks)
    stats = await get_the_market_scores_kalshi(live[0]["ticker"])
"""
from __future__ import annotations

import asyncio
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, TypedDict

# ── Reuse the v1 KalshiClient (auth + signed GETs) ────────────────────────────
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import bot_kalshi_btc15 as v1            # noqa: E402  (auth/client infra)

KalshiClient = v1.KalshiClient


# ── Types ─────────────────────────────────────────────────────────────────────
class SportsMarket(TypedDict, total=False):
    ticker: str
    event_ticker: str
    series_ticker: str
    sport: str            # series tag, e.g. "Soccer"
    league: str           # series title, e.g. "English Premier League"
    title: str            # market question
    status: str           # raw Kalshi status (active/closed/settled/…)
    match_status: str     # derived: "live" | "scheduled" | "settled"
    yes_bid: Optional[int]   # cents
    yes_ask: Optional[int]
    no_bid: Optional[int]
    no_ask: Optional[int]
    last_price: Optional[int]
    volume: float            # contracts (lifetime)
    volume_24h: float        # contracts (24h)
    usd_volume: float        # estimated USD = volume * last_price$
    occurrence_datetime: Optional[str]
    close_time: Optional[str]
    yes_sub_title: str
    no_sub_title: str


# ── small helpers ─────────────────────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _f(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _cents(dollar_str: Any) -> Optional[int]:
    """'0.1900' → 19 (cents).  None when missing."""
    if dollar_str is None:
        return None
    try:
        return int(round(float(dollar_str) * 100))
    except (TypeError, ValueError):
        return None


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def _series_of(ticker: str) -> str:
    """Series ticker = the segment before the first '-' (KXEPL-…-X → KXEPL)."""
    return (ticker or "").split("-", 1)[0]


def _match_status(m: dict) -> str:
    """
    Derive "live" | "scheduled" | "settled" from Kalshi fields (no native flag).

    NOTE: ``occurrence_datetime`` is NOT reliable as a "start" time — for some
    series (e.g. ITF tennis) it equals ``expected_expiration_time`` (the settle
    time), so an in-play match looks like it "hasn't started".  We therefore key
    off trading/expiration times instead:

      settled    — status closed/settled/finalized, or now ≥ expected expiration.
      scheduled  — unopened/initialized, or trading hasn't opened yet
                   (now < open_time).
      live       — active and not yet at expected expiration (in-play, or a
                   today match about to settle).
    """
    st = (m.get("status") or "").lower()
    if st in ("settled", "finalized", "determined", "closed", "canceled",
              "cancelled"):
        return "settled"
    if st in ("unopened", "initialized"):
        return "scheduled"
    now = _now()
    # Settle by the EXPECTED expiration (≈ match end), NOT the far-future
    # close_time/expiration_time (those are the series' final settlement window).
    exp = _parse_dt(m.get("expected_expiration_time")) or _parse_dt(m.get("close_time"))
    if exp is not None and now >= exp:
        return "settled"
    op = _parse_dt(m.get("open_time"))
    if op is not None and now < op:
        return "scheduled"
    if st == "active":
        return "live"
    return "scheduled"


def _enrich(m: dict, smap: dict[str, dict]) -> SportsMarket:
    """Flatten a raw Kalshi market into a typed SportsMarket (+ sport/league)."""
    series_t = _series_of(m.get("ticker", ""))
    meta = smap.get(series_t, {})
    vol = _f(m.get("volume_fp"))
    last = _f(m.get("last_price_dollars"))
    return SportsMarket(
        ticker=m.get("ticker", ""),
        event_ticker=m.get("event_ticker", ""),
        series_ticker=series_t,
        sport=meta.get("sport", "Other"),
        league=meta.get("league", ""),
        title=m.get("title", ""),
        status=m.get("status", ""),
        match_status=_match_status(m),
        yes_bid=_cents(m.get("yes_bid_dollars")),
        yes_ask=_cents(m.get("yes_ask_dollars")),
        no_bid=_cents(m.get("no_bid_dollars")),
        no_ask=_cents(m.get("no_ask_dollars")),
        last_price=_cents(m.get("last_price_dollars")),
        volume=vol,
        volume_24h=_f(m.get("volume_24h_fp")),
        usd_volume=round(vol * last, 2),
        occurrence_datetime=m.get("occurrence_datetime"),
        close_time=m.get("close_time"),
        yes_sub_title=m.get("yes_sub_title", ""),
        no_sub_title=m.get("no_sub_title", ""),
    )


# ── sports taxonomy (cached) ──────────────────────────────────────────────────
_SERIES_CACHE: dict[str, dict] = {}
_SERIES_CACHE_TS: float = 0.0


async def _sports_series(client: KalshiClient, *, ttl: float = 600.0) -> dict[str, dict]:
    """
    Map ``series_ticker -> {"sport", "league", "tags"}`` for every
    ``category == "Sports"`` series.  Cached for ``ttl`` seconds.
    """
    global _SERIES_CACHE, _SERIES_CACHE_TS
    if _SERIES_CACHE and (time.time() - _SERIES_CACHE_TS) < ttl:
        return _SERIES_CACHE
    d = await client.req("GET", "/series", params={"category": "Sports"})
    out: dict[str, dict] = {}
    for s in d.get("series", []):
        if s.get("category") != "Sports":
            continue
        tags = s.get("tags") or []
        out[s.get("ticker", "")] = {
            "sport": tags[0] if tags else "Other",
            "league": s.get("title") or "",
            "tags": tags,
        }
    _SERIES_CACHE, _SERIES_CACHE_TS = out, time.time()
    return out


async def list_sports(*, client: Optional[KalshiClient] = None) -> list[str]:
    """Return every distinct sport (series tag) currently on Kalshi, sorted."""
    own = client is None
    c = client or KalshiClient()
    try:
        smap = await _sports_series(c)
        return sorted({meta["sport"] for meta in smap.values()})
    finally:
        if own:
            await c.close()


# ── core fetch ────────────────────────────────────────────────────────────────
async def fetch_sports_markets(
    *,
    sport: Optional[str] = None,
    league: Optional[str] = None,
    status: str = "open",
    client: Optional[KalshiClient] = None,
    max_series: int = 150,
    concurrency: int = 10,
) -> list[SportsMarket]:
    """
    Fetch enriched sports markets, optionally narrowed by ``sport`` (tag) and/or
    ``league`` (series-title substring).  Markets for the matching series are
    fetched concurrently (``concurrency`` at a time) and capped to ``max_series``
    series to avoid hammering the API when no narrowing is given.

    Args:
        sport:   sport tag, e.g. "Tennis" (case-insensitive). None = all.
        league:  league/tournament substring, e.g. "ATP". None = all.
        status:  Kalshi market status filter ("open", "settled", …).
        client:  reuse an existing KalshiClient (else one is created/closed).
    Returns:
        list[SportsMarket]
    """
    own = client is None
    c = client or KalshiClient()
    try:
        smap = await _sports_series(c)
        sel = [
            st for st, meta in smap.items()
            if (not sport or meta["sport"].lower() == sport.lower())
            and (not league or league.lower() in meta["league"].lower())
        ]
        if len(sel) > max_series:
            sel = sel[:max_series]

        sem = asyncio.Semaphore(concurrency)

        async def _one(st: str) -> list[dict]:
            async with sem:
                try:
                    d = await c.req("GET", "/markets", params={
                        "series_ticker": st, "status": status, "limit": 1000})
                    return d.get("markets", [])
                except Exception:
                    return []

        chunks = await asyncio.gather(*(_one(st) for st in sel))
        return [_enrich(m, smap) for sub in chunks for m in sub]
    finally:
        if own:
            await c.close()


# ── 1) live / scheduled ───────────────────────────────────────────────────────
async def live_or_scheduled(
    status: str,
    markets: Optional[list[SportsMarket]] = None,
    *,
    client: Optional[KalshiClient] = None,
) -> list[SportsMarket]:
    """
    Filter markets whose derived match state equals ``status``.

    Args:
        status:  "live" or "scheduled".
        markets: list to filter; if None, sports markets are fetched first.
    Returns:
        list[SportsMarket] with ``match_status == status``.

    >>> live = await live_or_scheduled("live", markets=await fetch_sports_markets(sport="Soccer"))
    """
    s = status.strip().lower()
    if markets is None:
        markets = await fetch_sports_markets(client=client)
    return [m for m in markets if m.get("match_status") == s]


# ── 2) by sport ───────────────────────────────────────────────────────────────
async def filter_by_sport(
    sport_name: str,
    markets: Optional[list[SportsMarket]] = None,
    *,
    client: Optional[KalshiClient] = None,
) -> list[SportsMarket]:
    """
    Filter markets to a single sport category (series tag).

    Args:
        sport_name: e.g. "Soccer", "Tennis" (case-insensitive).
        markets:    list to filter; if None, that sport is fetched live.
    Returns:
        list[SportsMarket] for the sport.

    >>> tennis = await filter_by_sport("Tennis")
    """
    if markets is None:
        markets = await fetch_sports_markets(sport=sport_name, client=client)
    q = sport_name.strip().lower()
    return [m for m in markets if m.get("sport", "").lower() == q]


# ── 3) by league ──────────────────────────────────────────────────────────────
async def filter_by_league(
    league_name: str,
    markets: Optional[list[SportsMarket]] = None,
    *,
    client: Optional[KalshiClient] = None,
) -> list[SportsMarket]:
    """
    Filter markets by league/tournament (series-title substring match).

    Args:
        league_name: e.g. "English Premier League", "ATP" (case-insensitive).
        markets:     list to filter; if None, the league is fetched live.
    Returns:
        list[SportsMarket] whose league contains ``league_name``.

    >>> epl = await filter_by_league("English Premier League")
    """
    if markets is None:
        markets = await fetch_sports_markets(league=league_name, client=client)
    q = league_name.strip().lower()
    return [m for m in markets if q in m.get("league", "").lower()]


# ── 4) by minimum USD volume ──────────────────────────────────────────────────
async def filter_by_min_volume(
    min_usd: float,
    markets: Optional[list[SportsMarket]] = None,
    *,
    client: Optional[KalshiClient] = None,
) -> list[SportsMarket]:
    """
    Keep markets whose estimated USD volume ≥ ``min_usd``.

    USD volume is estimated as ``contracts (volume_fp) * last_price_dollars``
    (Kalshi reports contract volume, not dollar volume).

    Args:
        min_usd: minimum estimated USD volume (inclusive).
        markets: list to filter; if None, all sports markets are fetched
                 (capped — prefer chaining a narrower list in).
    Returns:
        list[SportsMarket] meeting the volume floor.

    >>> liquid = await filter_by_min_volume(5000, markets=await filter_by_sport("Soccer"))
    """
    if markets is None:
        markets = await fetch_sports_markets(client=client)
    return [m for m in markets if m.get("usd_volume", 0.0) >= float(min_usd)]


# ── 5) composed: sport + league + min volume ──────────────────────────────────
async def filter_by_sport_league_min_volume(
    sport_name: str,
    league_name: str,
    min_usd: float,
    *,
    status: str = "open",
    client: Optional[KalshiClient] = None,
) -> list[SportsMarket]:
    """
    One-shot fetch + filter: markets matching ``sport_name`` AND ``league_name``
    AND estimated USD volume ≥ ``min_usd``.

    Returns:
        list[SportsMarket]

    >>> picks = await filter_by_sport_league_min_volume("Soccer", "English Premier League", 1000)
    """
    own = client is None
    c = client or KalshiClient()
    try:
        markets = await fetch_sports_markets(
            sport=sport_name, league=league_name, status=status, client=c)
        sp, lg, mv = sport_name.lower(), league_name.lower(), float(min_usd)
        return [
            m for m in markets
            if m.get("sport", "").lower() == sp
            and lg in m.get("league", "").lower()
            and m.get("usd_volume", 0.0) >= mv
        ]
    finally:
        if own:
            await c.close()


# ── 6) live main-match markets (ready to trade) ───────────────────────────────
# Sub-market keywords → NOT the headline "match winner" line.
#
# 07/10 BUG FIX: these were matched as bare SUBSTRINGS, so "quarter" also hit
# "Quarterfinal" and silently threw away every quarterfinal match-winner market
# ("Will X win the A vs B: Quarterfinal match?").  On a quarterfinals day that
# rejected 133 of 207 live head-to-head markets and cut the watchlist from ~13
# to 3.  The same flaw would match "over" inside "Overton"/"Hanover", "under"
# inside "Sunderland", etc.  They are now matched on WORD BOUNDARIES, so
# "quarter" no longer matches "Quarterfinal" but still matches "3rd Quarter".
_SUB_KEYWORDS = (
    "spread", "total", "over", "under", "o/u", "handicap", "btts", "both teams",
    "1st half", "2nd half", "first half", "second half", "half", "quarter",
    "period", "win by", "margin", "points", "goals", "set", "sets", "race to",
    "double chance", "draw no bet", "correct score", "exact", "anytime",
    "first to", "alternate", "alt", "odd/even", "to advance", "to qualify",
)
_MAIN_KEYWORDS = ("winner", "moneyline", "to win", "match", "game", "result")


def _kw_re(words) -> "re.Pattern":
    """Match any keyword as a whole word/phrase (not as a substring inside a
    longer word) — 'quarter' matches "3rd Quarter" but not "Quarterfinal"."""
    body = "|".join(re.escape(w.strip()) for w in words)
    return re.compile(rf"(?<!\w)(?:{body})(?!\w)", re.IGNORECASE)


_SUB_RE = _kw_re(_SUB_KEYWORDS)
_MAIN_RE = _kw_re(_MAIN_KEYWORDS)

# Derivative series that describe a PART of a match (a set, a game) rather than
# the match winner.  These carry "X vs Y" in their titles and so slip past the
# head-to-head text check — reject them by series ticker.  (User rule 07/10:
# never trade set-winner markets.)
_DERIVATIVE_SERIES_TOKENS = (
    "SETWINNER", "GWINNER", "GAMEWINNER", "EXACTMATCH",
    "SETSPREAD", "GSPREAD", "GAMESPREAD", "GTOTAL", "GAMETOTAL",
    "EXACTSETS", "TOTALSETS", "ANYSET",
)


def _is_main_match(m: SportsMarket) -> bool:
    """Heuristic: a headline match-winner market, not a derivative sub-market."""
    series = (m.get("series_ticker") or "").upper()
    if any(t in series for t in _DERIVATIVE_SERIES_TOKENS):
        return False                       # set/game winner, exact score, ...
    txt = f"{m.get('league', '')} {m.get('title', '')}"
    if _SUB_RE.search(txt):
        return False
    return bool(_MAIN_RE.search(txt))


# Head-to-head ("X vs Y") detector — excludes tournament OUTRIGHTS ("win the
# Berlin", "Tournament Winner") which are also mutually-exclusive markets and
# would otherwise pass _is_main_match (their league contains "winner").
_H2H_SERIES_TOKENS = ("MATCH", "GAME")
_H2H_TEXT_TOKENS = (" vs ", " vs. ", " v. ", " v ", " @ ")


def _is_head_to_head(m: SportsMarket) -> bool:
    """True for an X-vs-Y match market; False for tournament/outright winners."""
    series = (m.get("series_ticker") or "").upper()
    if any(t in series for t in _H2H_SERIES_TOKENS):
        return True
    txt = f" {m.get('title', '')} {m.get('league', '')} ".lower()
    return any(t in txt for t in _H2H_TEXT_TOKENS)


class LiveMatch(TypedDict):
    ticker: str
    event_ticker: str
    sport: str
    league: str
    title: str
    yes_sub_title: str
    no_sub_title: str
    yes_bid: Optional[int]
    yes_ask: Optional[int]
    no_bid: Optional[int]
    no_ask: Optional[int]
    last_price: Optional[int]
    usd_volume: float


async def filter_live_matches(
    list_of_markets: list[SportsMarket],
    *,
    client: Optional[KalshiClient] = None,
    refresh_bids: bool = True,
    main_only: bool = True,
    dedupe_by_event: bool = True,
) -> list[LiveMatch]:
    """
    From #5's output, return the **live, head-to-head match-winner** markets with
    their bid/ask prices (ready to place an order on).  When ``main_only``:
      • derivative sub-markets (spreads, totals, "win by 1.5+", BTTS, …) are
        dropped (``_is_main_match``), and
      • tournament OUTRIGHTS ("win the Berlin", "Tournament Winner") are dropped
        (``_is_head_to_head`` — only "X vs Y" matches are kept).
    "live" = active and not yet at expected expiration (see ``_match_status``).

    Args:
        list_of_markets: SportsMarket list (e.g. from
                         filter_by_sport_league_min_volume).
        refresh_bids:    re-fetch each market's live bid/ask before returning
                         (most accurate at order time).
        main_only:       keep only headline head-to-head match-winner markets.
        dedupe_by_event: return ONE row per match (the highest-volume side),
                         instead of both the YES-side and NO-side markets.
    Returns:
        list[LiveMatch] (ticker + all bid/ask prices), sorted by estimated USD
        volume — highest-volume match first.

    >>> ready = await filter_live_matches(picks)   # ready[0] = highest volume
    """
    own = client is None
    c = client or KalshiClient()
    try:
        # 1) live, headline, head-to-head (X vs Y) markets only
        cand = [
            m for m in list_of_markets
            if m.get("match_status") == "live"
            and (not main_only or (_is_main_match(m) and _is_head_to_head(m)))
        ]
        # 2) one row per MATCH: keep the highest-volume side per event, but carry
        #    the WHOLE MATCH's volume (both player markets) on it.  Previously the
        #    row kept only its own side's usd_volume, so a match was judged on ~half
        #    its traded value and real matches fell under MIN_VOLUME_USD (07/10).
        if dedupe_by_event:
            best: dict[str, SportsMarket] = {}
            event_usd: dict[str, float] = {}
            for m in cand:
                ev = m.get("event_ticker") or m.get("ticker", "")
                event_usd[ev] = event_usd.get(ev, 0.0) + float(m.get("usd_volume", 0.0) or 0.0)
                if ev not in best or m.get("usd_volume", 0.0) > best[ev].get("usd_volume", 0.0):
                    best[ev] = m
            for ev, m in best.items():
                m["side_usd_volume"] = m.get("usd_volume", 0.0)   # this side only
                m["usd_volume"] = round(event_usd[ev], 2)          # whole match
            cand = list(best.values())
        # 3) highest-volume match first
        cand.sort(key=lambda x: x.get("usd_volume", 0.0), reverse=True)

        # 4) refresh live bids on the survivors and build rows
        out: list[LiveMatch] = []
        for m in cand:
            yb, ya = m.get("yes_bid"), m.get("yes_ask")
            nb, na = m.get("no_bid"), m.get("no_ask")
            lp = m.get("last_price")
            if refresh_bids:
                try:
                    md = await c.req("GET", f"/markets/{m['ticker']}")
                    fm = md.get("market", {})
                    yb, ya = _cents(fm.get("yes_bid_dollars")), _cents(fm.get("yes_ask_dollars"))
                    nb, na = _cents(fm.get("no_bid_dollars")), _cents(fm.get("no_ask_dollars"))
                    lp = _cents(fm.get("last_price_dollars"))
                except Exception:
                    pass
            out.append(LiveMatch(
                ticker=m.get("ticker", ""),
                event_ticker=m.get("event_ticker", ""),
                sport=m.get("sport", ""),
                league=m.get("league", ""),
                title=m.get("title", ""),
                yes_sub_title=m.get("yes_sub_title", ""),
                no_sub_title=m.get("no_sub_title", ""),
                yes_bid=yb, yes_ask=ya, no_bid=nb, no_ask=na,
                last_price=lp, usd_volume=m.get("usd_volume", 0.0),
            ))
        return out
    finally:
        if own:
            await c.close()


async def filter_by_sport_min_volume_live(
    sport_name: str,
    min_usd: float,
    *,
    top_n: int = 5,
    client: Optional[KalshiClient] = None,
) -> list[LiveMatch]:
    """
    Top ``top_n`` **live** headline match-winner markets for ``sport_name`` whose
    estimated USD volume ≥ ``min_usd``, highest volume first.  Returns fewer than
    ``top_n`` (down to 0) if that's all that qualifies.

    Composes: fetch sport → filter_by_min_volume → filter_live_matches (live +
    main-market + volume-sorted) → take top_n.

    Args:
        sport_name: e.g. "Soccer", "Tennis" (case-insensitive).
        min_usd:    minimum estimated USD volume (inclusive).
        top_n:      max markets to return (default 5).
    Returns:
        list[LiveMatch] (ticker + bid/ask prices), highest volume first.

    >>> top = await filter_by_sport_min_volume_live("Soccer", 1000)   # ≤5 live games
    """
    own = client is None
    c = client or KalshiClient()
    try:
        by_sport = await fetch_sports_markets(sport=sport_name, client=c)
        liquid = await filter_by_min_volume(min_usd, markets=by_sport)
        live = await filter_live_matches(liquid, client=c)   # live + main, vol-sorted
        return live[:max(0, top_n)]
    finally:
        if own:
            await c.close()


# ── 7) per-sport match stats / scores ─────────────────────────────────────────
def _score_template(sport: str) -> dict:
    """Per-sport scoreboard skeleton (keys differ by sport)."""
    s = sport.lower()
    if s in ("tennis", "table tennis", "squash"):
        return {"unit": "set", "sets": [], "current_set_games": None, "server": None}
    if s == "cricket":
        return {"unit": "innings", "innings": [], "runs": None, "wickets": None,
                "overs": None, "target": None}
    if s == "baseball":
        return {"unit": "inning", "inning": None, "half": None,
                "runs": {"home": None, "away": None},
                "hits": {"home": None, "away": None}, "outs": None}
    if s == "basketball":
        return {"unit": "quarter", "period": None, "clock": None,
                "points": {"home": None, "away": None}}
    if s in ("football", "cfb"):
        return {"unit": "quarter", "quarter": None, "clock": None,
                "points": {"home": None, "away": None}, "possession": None}
    if s == "hockey":
        return {"unit": "period", "period": None, "clock": None,
                "goals": {"home": None, "away": None}}
    if s in ("soccer", "rugby"):
        unit = "goal" if s == "soccer" else "point"
        return {"unit": unit, "half": None, "clock": None,
                "score": {"home": None, "away": None}}
    if s in ("mma", "boxing", "ufc"):
        return {"unit": "round", "round": None, "method": None}
    if s == "golf":
        return {"unit": "hole", "round": None, "thru": None,
                "leaderboard": []}
    if s in ("motorsport",):
        return {"unit": "lap", "lap": None, "leader": None, "positions": []}
    if s == "chess":
        return {"unit": "game", "game": None, "result_so_far": None}
    return {"unit": "generic", "score": None}


async def _external_scores(sport: str, participants: list[dict], *,
                           client: Optional[KalshiClient] = None) -> Optional[dict]:
    """
    Hook for a real live-scores provider (ESPN, api-sports.io, sportradar, …).

    Kalshi's API has no scoreboard, so wire your provider here and return a dict
    to merge into the per-sport ``_score_template``.  Returns None by default.
    """
    return None


async def get_the_market_scores_kalshi(
    market_ticker: str,
    *,
    client: Optional[KalshiClient] = None,
) -> dict:
    """
    Return full match stats for ``market_ticker`` to inform a buy decision.

    Because Kalshi exposes **no live scoreboard**, this returns:
      • ``participants``  — every outcome in the event with its live yes/no
        bid/ask and **implied probability** (the market's read on who's winning);
      • ``implied``       — {participant: probability};
      • ``score``         — a per-sport skeleton (innings/sets/goals/…), filled
        only if ``_external_scores`` is wired to a real feed;
      • ``match_status``  — live / scheduled / settled.

    Args:
        market_ticker: any market in the event (its siblings are pulled too).
    Returns:
        dict (see keys above).

    >>> stats = await get_the_market_scores_kalshi("KXEPLGAME-25DEC01ARSCHE-ARS")
    """
    own = client is None
    c = client or KalshiClient()
    try:
        md = await c.req("GET", f"/markets/{market_ticker}")
        m = md.get("market", {})
        smap = await _sports_series(c)
        meta = smap.get(_series_of(market_ticker), {})
        sport = meta.get("sport", "Other")

        # Pull every outcome (sibling market) in the event → the "scoreboard".
        ev_ticker = m.get("event_ticker", "")
        siblings: list[dict] = [m]
        if ev_ticker:
            try:
                ed = await c.req("GET", f"/events/{ev_ticker}",
                                 params={"with_nested_markets": "true"})
                siblings = (ed.get("event", {}) or {}).get("markets", []) or [m]
            except Exception:
                pass

        participants: list[dict] = []
        for sm in siblings:
            name = (sm.get("yes_sub_title")
                    or (sm.get("custom_strike") or {}).get("Participant")
                    or sm.get("title", ""))
            ya = _cents(sm.get("yes_ask_dollars"))
            yb = _cents(sm.get("yes_bid_dollars"))
            lp = _cents(sm.get("last_price_dollars"))
            prob = (lp if lp is not None else ya if ya is not None else 0) / 100.0
            participants.append({
                "name": name,
                "ticker": sm.get("ticker", ""),
                "yes_bid": yb, "yes_ask": ya, "last_price": lp,
                "implied_prob": round(prob, 3),
            })

        score = _score_template(sport)
        ext = await _external_scores(sport, participants, client=c)
        if ext:
            score.update(ext)

        return {
            "ticker": market_ticker,
            "event_ticker": ev_ticker,
            "sport": sport,
            "league": meta.get("league", ""),
            "title": m.get("title", ""),
            "match_status": _match_status(m),
            "participants": participants,
            "implied": {p["name"]: p["implied_prob"] for p in participants if p["name"]},
            "score": score,
            "scores_source": "external" if ext else "none",
            "note": ("Kalshi trade-api has no live scoreboard; `score` is a "
                     "per-sport skeleton, populated only if _external_scores() "
                     "is wired to a real feed. `implied` reflects the market's "
                     "live probabilities."),
        }
    finally:
        if own:
            await c.close()


async def get_live_bid_prices(
    market_ticker: str,
    *,
    client: Optional[KalshiClient] = None,
) -> dict[str, Optional[int]]:
    """
    Live YES bid price (cents) per participant for the event containing
    ``market_ticker`` — what you'd pay to back each side right now.

    • Head-to-head binary market (1 outcome market): returns both sides, e.g.
      ``{"Nadal": 49, "Federer": 51}`` (yes_sub_title → yes_bid, no_sub_title → no_bid).
    • Multi-outcome event (one market per participant): ``{participant: yes_bid}``.

    Args:
        market_ticker: any market in the event.
    Returns:
        dict[participant_name, yes_bid_cents]  (value None if no bid).

    >>> await get_live_bid_prices("KXATPMATCH-...-NADAL")   # {"Nadal": 49, "Federer": 51}
    """
    own = client is None
    c = client or KalshiClient()
    try:
        md = await c.req("GET", f"/markets/{market_ticker}")
        m = md.get("market", {})
        ev = m.get("event_ticker", "")
        siblings: list[dict] = [m]
        if ev:
            try:
                ed = await c.req("GET", f"/events/{ev}",
                                 params={"with_nested_markets": "true"})
                siblings = (ed.get("event", {}) or {}).get("markets", []) or [m]
            except Exception:
                pass

        out: dict[str, Optional[int]] = {}
        if len(siblings) == 1:
            sm = siblings[0]
            yn = (sm.get("yes_sub_title")
                  or (sm.get("custom_strike") or {}).get("Participant") or sm.get("title", ""))
            nn = sm.get("no_sub_title")
            if yn:
                out[yn] = _cents(sm.get("yes_bid_dollars"))
            if nn:
                out[nn] = _cents(sm.get("no_bid_dollars"))
        else:
            for sm in siblings:
                yn = (sm.get("yes_sub_title")
                      or (sm.get("custom_strike") or {}).get("Participant") or sm.get("title", ""))
                if yn:
                    out[yn] = _cents(sm.get("yes_bid_dollars"))
        return out
    finally:
        if own:
            await c.close()


# ── demo ──────────────────────────────────────────────────────────────────────
async def _demo() -> None:
    print("Sports on Kalshi:", await list_sports())
    picks = await filter_by_sport_league_min_volume("Tennis", "ATP", 0)
    print(f"\nATP markets (vol≥0): {len(picks)}")
    for p in picks[:5]:
        print(f"  {p['ticker']}  {p['match_status']:9s} {p['title'][:48]}  "
              f"yes_bid={p['yes_bid']}  usd_vol={p['usd_volume']}")
    live = await filter_live_matches(picks, refresh_bids=False)
    print(f"\nlive main matches: {len(live)}")
    if live:
        import json
        print(json.dumps(await get_the_market_scores_kalshi(live[0]["ticker"]),
                         indent=2, default=str)[:900])


if __name__ == "__main__":
    asyncio.run(_demo())
