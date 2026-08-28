#!/usr/bin/env python3
"""
tennis_live_score.py — live tennis scores from ESPN's free scoreboard API.
==========================================================================
Used by the Kalshi sports bot to look up the live score of a tennis match
(by player name) before placing an order.

WHY NOT the PyPI ``tennis`` library?
    The PyPI ``tennis`` package (bear102/tennis) is an OFFLINE scoring
    *simulator* — you advance state by calling win_point()/serve_fault()
    manually; it does not fetch live data.  It also shares this folder's name,
    so ``import tennis`` here would import this folder, not the library.  So we
    pull live data straight from ESPN's public (key-less) endpoint:

        GET https://site.api.espn.com/apis/site/v2/sports/tennis/{league}/scoreboard

    Tennis is modeled by ESPN as tournaments → groupings → competitions
    (matches) → competitors (players) with per-set ``linescores``.

Coverage: ESPN's atp/wta scoreboards cover ATP/WTA main-tour singles (and some
doubles).  Lower ITF/Challenger events aren't on ESPN — the Kalshi sports bot
reads those live scores from Kalshi's own milestone live-data instead.

CLI:
    python tennis/tennis_live_score.py                 # all live matches
    python tennis/tennis_live_score.py Hanfmann        # one player's match
"""
from __future__ import annotations

import asyncio
import csv
import os
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Optional, TypedDict

import aiohttp

ESPN_URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/{league}/scoreboard"
ESPN_RANK_URL = "https://site.api.espn.com/apis/site/v2/sports/tennis/{league}/rankings"
DEFAULT_LEAGUES = ("atp", "wta")
_HEADERS = {"User-Agent": "Mozilla/5.0"}


class PlayerScore(TypedDict, total=False):
    name: str
    sets_won: int
    games: list[int]            # games per set, e.g. [7, 6, 3]
    tiebreaks: list[Optional[int]]  # tiebreak points per set (None if no TB)
    current_game: Optional[str]  # live game points ("0/15/30/40/AD") if available
    serving: bool
    winner: bool
    rank: Optional[int]         # ATP/WTA ranking (if known)


class MatchScore(TypedDict, total=False):
    tournament: str
    league: str
    surface: str                # court surface: Grass/Clay/Hard/Indoor (if known)
    round: str
    status: str                 # "pre" | "in" | "post"
    status_detail: str          # "Final", "Set 2", "1st Set", …
    completed: bool
    live: bool
    players: list[PlayerScore]
    server: Optional[str]
    leader: Optional[str]
    summary: str                # "Basilashvili d. Dedura 7-6 6-3" / live "7-6 3-2*"


# ── name helpers ──────────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    """Lowercase + strip accents for tolerant name comparison."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _name_matches(query: str, full_name: str) -> bool:
    """True if ``query`` (a Kalshi participant name or surname) matches ESPN's
    ``full_name`` — full substring either way, or a shared surname token."""
    q, n = _norm(query), _norm(full_name)
    if not q or not n:
        return False
    if q in n or n in q:
        return True
    q_tokens, n_tokens = set(q.split()), set(n.split())
    # surname overlap (ignore 1-letter initials)
    return any(t in n_tokens for t in q_tokens if len(t) > 2)


# ── parsing ───────────────────────────────────────────────────────────────────
def _f_int(v: Any) -> Optional[int]:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _player_name(comp: dict) -> str:
    ath = comp.get("athlete") or {}
    if isinstance(ath, dict) and ath.get("displayName"):
        return ath["displayName"]
    # doubles: build from roster athletes (roster items may be dicts or strings)
    names: list[str] = []
    for a in (comp.get("roster") or []):
        if isinstance(a, dict):
            inner = a.get("athlete") if isinstance(a.get("athlete"), dict) else a
            nm = inner.get("displayName") or inner.get("shortName") or ""
            if nm:
                names.append(nm)
        elif isinstance(a, str) and a:
            names.append(a)
    if names:
        return " / ".join(names)
    return (ath.get("shortName") if isinstance(ath, dict) else None) or "Unknown"


def _normalize_match(comp: dict, tournament: str, league: str) -> Optional[MatchScore]:
    cs = comp.get("competitors") or []
    if len(cs) < 2:
        return None
    st = (comp.get("status") or {}).get("type", {}) or {}
    state = st.get("state", "")            # pre | in | post
    detail = st.get("detail", "")
    completed = bool(st.get("completed"))
    rnd = (comp.get("round") or {}).get("displayName", "") if isinstance(comp.get("round"), dict) else ""

    games = [[_f_int(x.get("value")) for x in (p.get("linescores") or [])] for p in cs]
    players: list[PlayerScore] = []
    for i, p in enumerate(cs):
        mine: list[int] = []
        tbs: list[Optional[int]] = []
        for x in (p.get("linescores") or []):
            v = _f_int(x.get("value"))
            if v is None:
                continue
            mine.append(v)
            tbs.append(_f_int(x.get("tiebreak")))   # set tiebreak points, if any
        opp = games[1 - i]
        sets_won = sum(
            1 for j, g in enumerate(games[i])
            if g is not None and j < len(opp) and opp[j] is not None and g > opp[j]
        )
        serving = bool(p.get("possession") or p.get("serving"))
        cur = p.get("score") if state == "in" else None  # live game points (best-effort)
        players.append(PlayerScore(
            name=_player_name(p),
            sets_won=sets_won,
            games=mine,
            tiebreaks=tbs,
            current_game=str(cur) if cur not in (None, "") else None,
            serving=serving,
            winner=bool(p.get("winner")),
        ))

    server = next((pl["name"] for pl in players if pl["serving"]), None)
    leader = None
    if players[0]["sets_won"] != players[1]["sets_won"]:
        leader = max(players, key=lambda x: x["sets_won"])["name"]
    elif completed:
        leader = next((pl["name"] for pl in players if pl["winner"]), None)

    # scoreline summary
    score_pairs = " ".join(
        f"{a}-{b}" for a, b in zip(players[0]["games"], players[1]["games"]))
    if completed:
        win = next((pl for pl in players if pl["winner"]), players[0])
        lose = players[1] if win is players[0] else players[0]
        summary = f"{win['name']} d. {lose['name']} {score_pairs}".strip()
    else:
        srv = "*" if server == players[0]["name"] else ""
        summary = f"{players[0]['name']} {srv}vs {players[1]['name']} {score_pairs}".strip()

    return MatchScore(
        tournament=tournament, league=league, round=rnd,
        status=state, status_detail=detail, completed=completed,
        live=(state == "in"),
        players=players, server=server, leader=leader, summary=summary,
    )


def _flatten(scoreboard: dict, league: str) -> list[MatchScore]:
    out: list[MatchScore] = []
    for ev in scoreboard.get("events", []):
        tour = ev.get("name", "")
        # tennis: matches live under groupings[].competitions[]
        comps: list[dict] = []
        for g in (ev.get("groupings") or []):
            comps.extend(g.get("competitions") or [])
        comps.extend(ev.get("competitions") or [])  # fallback (other shapes)
        for comp in comps:
            try:
                m = _normalize_match(comp, tour, league)
            except Exception:
                m = None              # one malformed match must not drop the rest
            if m:
                out.append(m)
    return out


# ── public API ────────────────────────────────────────────────────────────────
async def fetch_all_matches(
    *,
    leagues: tuple[str, ...] = DEFAULT_LEAGUES,
    session: Optional[aiohttp.ClientSession] = None,
    live_only: bool = False,
) -> list[MatchScore]:
    """All tennis matches across ``leagues`` (atp/wta), normalized."""
    own = session is None
    s = session or aiohttp.ClientSession(headers=_HEADERS)

    async def _one(lg: str) -> list[MatchScore]:
        try:
            async with s.get(ESPN_URL.format(league=lg), timeout=15) as r:
                d = await r.json()
            return _flatten(d, lg)
        except Exception:
            return []

    try:
        chunks = await asyncio.gather(*(_one(lg) for lg in leagues))
        matches = [m for sub in chunks for m in sub]
        return [m for m in matches if m["live"]] if live_only else matches
    finally:
        if own:
            await s.close()


async def list_live_matches(
    *, leagues: tuple[str, ...] = DEFAULT_LEAGUES,
    session: Optional[aiohttp.ClientSession] = None,
) -> list[MatchScore]:
    """Only the in-progress matches."""
    return await fetch_all_matches(leagues=leagues, session=session, live_only=True)


async def get_live_score(
    player: str,
    *,
    opponent: Optional[str] = None,
    leagues: tuple[str, ...] = DEFAULT_LEAGUES,
    session: Optional[aiohttp.ClientSession] = None,
    prefer_live: bool = True,
) -> Optional[MatchScore]:
    """
    Live score of the match featuring ``player`` (optionally also ``opponent``).

    Match names are compared tolerantly (accents/case-insensitive, surname or
    full-substring), so pass the Kalshi participant name directly, e.g.
    ``await get_live_score("Yannick Hanfmann")``.

    Returns the MatchScore (prefers an in-progress match when several match the
    name), or None if ESPN has no such match (e.g. ITF/lower Challenger events).
    """
    matches = await fetch_all_matches(leagues=leagues, session=session)

    def _hit(m: MatchScore) -> bool:
        names = [p["name"] for p in m["players"]]
        if not any(_name_matches(player, n) for n in names):
            return False
        if opponent:
            return any(_name_matches(opponent, n) for n in names)
        return True

    cands = [m for m in matches if _hit(m)]
    if not cands:
        return None
    if prefer_live:
        cands.sort(key=lambda m: (m["live"], not m["completed"]), reverse=True)
    return cands[0]


# ── player rankings (ESPN ATP/WTA top-150, free) ──────────────────────────────
_RANK_CACHE: dict[str, int] = {}
_RANK_CACHE_TS: float = 0.0


async def get_player_rankings(
    *,
    leagues: tuple[str, ...] = ("atp", "wta"),
    session: Optional[aiohttp.ClientSession] = None,
    ttl: float = 3600.0,
) -> dict[str, int]:
    """``{normalized_name: rank}`` for the ATP/WTA top-150 (ESPN). Cached ttl s."""
    global _RANK_CACHE, _RANK_CACHE_TS
    if _RANK_CACHE and (time.time() - _RANK_CACHE_TS) < ttl:
        return _RANK_CACHE
    own = session is None
    s = session or aiohttp.ClientSession(headers=_HEADERS)
    out: dict[str, int] = {}
    try:
        for lg in leagues:
            try:
                async with s.get(ESPN_RANK_URL.format(league=lg), timeout=15) as r:
                    d = await r.json()
            except Exception:
                continue
            for grp in d.get("rankings", []):
                for e in grp.get("ranks", []):
                    ath = e.get("athlete") or {}
                    name = ath.get("displayName") if isinstance(ath, dict) else None
                    rk = e.get("current")
                    if name and isinstance(rk, int) and rk > 0:
                        out.setdefault(_norm(name), rk)
        if out:
            _RANK_CACHE, _RANK_CACHE_TS = out, time.time()
        return out
    finally:
        if own:
            await s.close()


def rank_for(name: str, rankings: dict) -> Optional[int]:
    """Tolerant lookup of a player's rank in a name→rank map (None if absent)."""
    if not name or not rankings:
        return None
    n = _norm(name)
    if n in rankings:
        return rankings[n]
    for k, v in rankings.items():
        if _name_matches(name, k):
            return v
    return None


def _rankings_csv_path(path: Optional[str] = None) -> Path:
    return Path(path or os.getenv("TENNIS_RANKINGS_CSV")
                or (Path(__file__).resolve().parent / "web" / "tennis_rankings.csv"))


def load_rankings_csv(path: Optional[str] = None) -> dict[str, int]:
    """
    ``{normalized_name: rank}`` from the SofaScore scraper CSV
    (``tennis/web/tennis_rankings.csv``).  Returns ``{}`` if the file is missing
    — callers should then show "NA".  Override with ``path`` or env
    ``TENNIS_RANKINGS_CSV``.
    """
    p = _rankings_csv_path(path)
    out: dict[str, int] = {}
    if not p.exists():
        return out
    try:
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = (row.get("player") or "").strip()
                if not name:
                    continue
                try:
                    rk = int(str(row.get("rank")).strip())
                except (TypeError, ValueError):
                    continue
                out.setdefault(_norm(name), rk)
    except Exception:
        pass
    return out


def load_rank_tours(path: Optional[str] = None) -> dict[str, str]:
    """
    ``{normalized_name: tour}`` from the SAME rankings CSV, where ``tour`` is the
    CSV's own category column (ATP / WTA / ITF) — used to prioritise a
    WTA/ATP ranking over an ITF one when picking the favorite (07/10 rule).
    The category comes purely from the CSV row, independent of the match's
    tournament/ticker.  ``{}`` if the file is missing.
    """
    p = _rankings_csv_path(path)
    out: dict[str, str] = {}
    if not p.exists():
        return out
    try:
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = (row.get("player") or "").strip()
                tour = (row.get("tour") or "").strip().upper()
                if name and tour:
                    out.setdefault(_norm(name), tour)
    except Exception:
        pass
    return out


def tour_for(name: str, tours: dict) -> Optional[str]:
    """Tolerant lookup of a player's ranking tour (ATP/WTA/ITF), or None."""
    if not name or not tours:
        return None
    n = _norm(name)
    if n in tours:
        return tours[n]
    for k, v in tours.items():
        if _name_matches(name, k):
            return v
    return None


# ── one-line score formatter ──────────────────────────────────────────────────
def _surname(name: str) -> str:
    name = (name or "").strip()
    if "/" in name:                                    # doubles
        return "/".join(p.strip().split()[-1] for p in name.split("/") if p.strip())
    return name.split()[-1] if name else name


def _tour_code(m: MatchScore) -> str:
    lg = (m.get("league") or "").lower()
    if "itf" in lg:
        return "ITF"
    if "challenger" in lg:
        return "CH"
    if "atp" in lg:
        return "ATP"
    if "wta" in lg:
        return "WTA"
    return (m.get("league") or "TENNIS").upper()[:6]


def one_liner(m: Optional[MatchScore]) -> str:
    """
    Compact one-line score, e.g.:
        ATP - Federer vs Nadal* 1-1: 6-7, 7-6 (7-4), 4-3 (40:40)

    The server's name is marked with ``*`` (live matches only).  Per-set games
    show the tiebreak in parens when present; the in-progress set appends the
    current game points.  Returns "" for None.
    """
    if not m or len(m.get("players", [])) < 2:
        return ""
    p1, p2 = m["players"][0], m["players"][1]

    def _disp(p: PlayerScore) -> str:
        out = _surname(p.get("name", ""))
        if p.get("rank"):
            out += f"({p['rank']})"
        if p.get("serving") and m.get("live"):
            out += "*"
        return out

    g1, g2 = p1.get("games", []), p2.get("games", [])
    tb1, tb2 = p1.get("tiebreaks") or [], p2.get("tiebreaks") or []
    n = max(len(g1), len(g2))
    sets_str: list[str] = []
    for i in range(n):
        a = g1[i] if i < len(g1) else 0
        b = g2[i] if i < len(g2) else 0
        seg = f"{a}-{b}"
        t1 = tb1[i] if i < len(tb1) else None
        t2 = tb2[i] if i < len(tb2) else None
        if t1 is not None or t2 is not None:
            seg += f" ({t1 or 0}-{t2 or 0})"
        if m.get("live") and i == n - 1 and (p1.get("current_game") or p2.get("current_game")):
            seg += f" ({p1.get('current_game') or '0'}:{p2.get('current_game') or '0'})"
        sets_str.append(seg)
    tour = _tour_code(m)
    surface = (m.get("surface") or "").strip()
    prefix = f"{tour} {surface}-" if surface else f"{tour} -"
    head = (f"{prefix} {_disp(p1)} vs {_disp(p2)} "
            f"{p1.get('sets_won', 0)}-{p2.get('sets_won', 0)}")
    return f"{head}: {', '.join(sets_str)}" if sets_str else head


# ── dispatcher: pick the right source by Kalshi series ────────────────────────
async def get_match_score(
    player: str,
    series_or_ticker: str = "",
    *,
    opponent: Optional[str] = None,
    session: Optional[aiohttp.ClientSession] = None,
) -> Optional[MatchScore]:
    """
    Live score for a Kalshi tennis market from ESPN (ATP/WTA).

    ITF/Challenger events aren't on ESPN — the Kalshi sports bot reads those
    from Kalshi's own milestone live-data, so this serves as the ATP/WTA
    fallback.  ``series_or_ticker`` is accepted for call-site compatibility.

    >>> await get_match_score("Naomi Osaka", "KXWTAMATCH-26JUN20OSAFRE-OSA")
    """
    return await get_live_score(player, opponent=opponent, session=session)


# ── CLI demo ──────────────────────────────────────────────────────────────────
async def _demo(player: Optional[str]) -> None:
    if player:
        m = await get_live_score(player)
        if not m:
            print(f"No ESPN match found for {player!r} "
                  "(may be an ITF/Challenger event ESPN doesn't cover).")
            return
        tag = "LIVE" if m["live"] else m["status_detail"]
        print(f"[{tag}] {m['tournament']} — {m['summary']}")
        for p in m["players"]:
            srv = " (serving)" if p["serving"] else ""
            print(f"   {p['name']:<28} sets={p['sets_won']} games={p['games']}"
                  f"{(' pts=' + p['current_game']) if p['current_game'] else ''}{srv}")
        return
    live = await list_live_matches()
    print(f"=== {len(live)} LIVE tennis matches ===")
    for m in live:
        print(f"  [{m['league'].upper()}] {m['summary']}  ({m['tournament']})")
    if not live:
        all_m = await fetch_all_matches()
        print(f"(none in progress; {len(all_m)} matches on the board today)")


def main() -> None:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    arg = " ".join(sys.argv[1:]).strip() or None
    asyncio.run(_demo(arg))


if __name__ == "__main__":
    main()
