#!/usr/bin/env python3
"""
predict_v3.py — Tennis Match Prediction Model v3 → Kalshi buy signal + exit.
============================================================================
COPY OF predict_v1.py (the frozen 07/06 weekend-stable snapshot — see its
header for the full provenance) PLUS the favorite-comeback EXIT rule
(user request 07/08, Ahn vs Bernales):

  We held the NON-favorite (Bernales, bought after her surge) and at ~1:10 PM
  the pre-match favorite (Ahn) started coming back — Bernales slid from ~75%
  to 53.8% while Ahn climbed — but nothing exited: the reversal-flip needs the
  favorite to have a full DOUBLE-BREAK, and the 30c stop-loss was still far
  below.  The trade rode down to -$50.25 at settlement.

  v3 adds ``favorite_comeback_exit()``: while HOLDING the non-favorite, exit
  the trade EVEN AT A LOSS as soon as the favorite's comeback is confirmed by
  any of:
    1. the favorite now holds their own double-break in the current set;
    2. the favorite's live bid has caught/passed the held player's bid
       (the market no longer rates our player the likely winner);
    3. we are under water (held bid >= EXIT_FAV_DROP_C below entry) AND the
       favorite's bid is within EXIT_FAV_PARITY_C of the held player's —
       near-parity while losing = the comeback is real, get out.

  The bot (bot_kalshi_sports_v1.py, FAVEXIT guardian pass) calls this every
  guardian cycle for each held tennis position and sells aggressively when it
  fires — no favorite re-buy, just capital protection.

Everything below the exit-rule block is byte-for-byte predict_v1.py.

Given a live tennis match, pick the player to BACK TO WIN THE MATCH (the only
tradeable Kalshi market) and a confidence — "ultra high" | "high" | "medium" |
"low" — and, when that player's live bid is in the value band, a buy tip.

Match data shape (the "scraper shape", side A = home / B = away):
    scenario        "elite" | "parity"        (elite if either rank <= 10)
    favorite        "A" | "B" | None          (pre-match: better rank / odds)
    fav_prob        favorite implied % (cents) | None
    completed_sets  int
    sets            (a_sets, b_sets)
    set1_winner/margin, set2_winner/margin
    games           (current-set games a, b)
    serving         "A" | "B" | None
    points          (a_pts, b_pts) each 0/15/30/40/A
    break_point     bool
    double_break    "A" | "B" | None          (set leader by >= double break)
    stay_in_set     "A" | "B" | None          (server down, serving to stay)

The bot feeds this from the Kalshi milestone data it already fetches (fast,
works across many matches).  The browser-based scraper
(tennis/web/tennis_live_match_scraper.py) is wired via ``scrape_match_data`` /
``predict_for_player`` for on-demand use — it launches a browser per call, so
it is NOT used inside the bot's per-poll loop.

SITUATIONS  (model v2.0)
  A set 1 in progress · B set 1 done · C post-break consolidation ·
  D serving-to-stay · E double-break dead zone · F set-3 decider ·
  Fallback micro-state engine (tennis_all_combinations.csv).
"""
from __future__ import annotations

import asyncio
import csv
import os
import re
import sys
from pathlib import Path
from typing import Optional

try:
    from .tennis_live_score import rank_for, one_liner
except ImportError:                    # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from tennis_live_score import rank_for, one_liner

# confidence levels
CONF_ULTRA = "ultra high"
CONF_HIGH = "high"
CONF_MED = "medium"
CONF_LOW = "low"

# Band raised 40→68 on the 06/28 settlement study (273 trades, TRUE settle outcomes):
# the old 40-82 band lost -$137 under the live TP+40% exit because a CHEAP bid in
# these efficient ITF markets is a genuine coin flip, not value — and TP+40% caps
# winners tiny while a loser costs the full stake, so you need ~80%+ win to profit.
# That win rate only exists at bid >= ~68c (68-85 band: 80% win, +$9; E flips
# -$27→+$27, B -$29→~breakeven).  Buy only CONFIRMED strong favorites.
BID_LO = int(os.getenv("PREDICT_BID_LO", "68"))   # was 40: 40-67c bids are coin-flips that lose under TP+40%
BID_HI = int(os.getenv("PREDICT_BID_HI", "84"))   # was 82: 75-84c fills win ~85%; the +5 buy bump fills ~87c
HEAVY_FAV_CENTS = int(os.getenv("PREDICT_HEAVY_FAV", "72"))   # >= heavy favorite
ULTRA_BUY_MAX = int(os.getenv("PREDICT_ULTRA_MAX", "85"))     # ultra high: buy if bid < this (restored from 72)
ULTRA_BUY_MIN = int(os.getenv("PREDICT_ULTRA_MIN", "35"))     # ultra high: and bid >= this (a "winning" favorite priced
                                                              # below this is a data anomaly — don't buy into it)
SET1_MAX_BID = int(os.getenv("PREDICT_SET1_MAX", "85"))       # set 1 (non-ultra) bid cap; was 50 (now inverted vs the
                                                              # 68 floor) — set to band-hi so set-1 uses the same band
SET2_MAX_BID = int(os.getenv("PREDICT_SET2_MAX_BID", "56"))   # set 2 (3rd set not started): a BUY signal only executes
                                                              # below this — else WAIT and keep polling for the dip
SET3_CLOSE_C = int(os.getenv("PREDICT_SET3_CLOSE", "10"))     # set 3: "original odds close" if |diff| <= this
# Strong original favorite (set-2 management): needs BOTH a rank and an odds edge.
FAV_RANK_DIFF = int(os.getenv("PREDICT_FAV_RANK_DIFF", "50"))   # rank edge (e.g. 220 vs 106)
FAV_ODDS_DIFF = int(os.getenv("PREDICT_FAV_ODDS_DIFF", "25"))   # original-odds edge (e.g. 82 vs 36)
SET2_MIN_GAMES = int(os.getenv("PREDICT_SET2_MIN_GAMES", "4"))  # set 2: wait until the 5th game (>= games)
FAV_DROP_C = int(os.getenv("PREDICT_FAV_DROP", "25"))           # "sharp" live-price drop vs original (cents)
# Favorite-rebound rule (user correction 07/02, e.g. Semanova/Bouzkova): when the
# rank favorite is behind/losing or has lost set 1, NEVER back the opponent — wait
# for the favorite's own live price to fall into this value zone, then buy the
# favorite. See _favorite_rebound().
FAV_REBOUND_LO = int(os.getenv("PREDICT_FAV_REBOUND_LO", "50"))
FAV_REBOUND_HI = int(os.getenv("PREDICT_FAV_REBOUND_HI", "60"))
POLL_INTERVAL_S = float(os.getenv("PREDICT_POLL_S", "5"))

# ── v3: favorite-comeback exit (user rule 07/08, Ahn vs Bernales) ─────────────
# While HOLDING the non-favorite: how far under water (cents below entry) the
# held bid must be before "losing + near-parity" (trigger 3) can fire, and how
# close (cents) the favorite's bid must be to the held player's to count as
# near-parity.  Trigger 2 (favorite bid caught/passed ours) and trigger 1
# (favorite has their own double-break) have no thresholds.
EXIT_FAV_DROP_C = int(os.getenv("PREDICT_EXIT_FAV_DROP", "8"))
EXIT_FAV_PARITY_C = int(os.getenv("PREDICT_EXIT_FAV_PARITY", "5"))

# v3 (user rule 07/10): while HOLDING the FAVORITE, if the favorite is being
# beaten badly and is about to lose both sets — the NON-favorite (opponent) is
# now priced above this many cents during play — sell the favorite position.
EXIT_FAV_COLLAPSE_OPP_C = int(os.getenv("PREDICT_EXIT_FAV_COLLAPSE_OPP", "90"))

# v3 (user rule 07/10): bought-high collapse. If we bought a side ABOVE
# EXIT_HIGH_ENTRY_C and its live odds have since fallen BELOW EXIT_HIGH_COLLAPSE_C,
# sell/exit — UNLESS the match is already in the last 2 points of the deciding
# (final) set, where it's "anybody's game" so we let it settle. Applies to any
# held side (favorite or not). SETS_TO_WIN=2 → best-of-3 (the deciding set is the
# set where both players already hold SETS_TO_WIN-1 sets, e.g. 1-1 → set 3).
EXIT_HIGH_ENTRY_C = int(os.getenv("PREDICT_EXIT_HIGH_ENTRY", "76"))      # bought strictly above
EXIT_HIGH_COLLAPSE_C = int(os.getenv("PREDICT_EXIT_HIGH_COLLAPSE", "25"))  # odds strictly below
SETS_TO_WIN = int(os.getenv("PREDICT_SETS_TO_WIN", "2"))

# v3 (user rule 07/09, Oliveira): in SET 1 (no set completed yet), do NOT back
# a player the market priced as the pre-match UNDERDOG — a first-set lead /
# double-break by an underdog is not a match-winner signal. "Underdog" = their
# original (pre-match) odds are below this many cents (below even money), or
# below the opponent's original odds. Oliveira led set 1 5-2 at original 16c,
# situation E bought her, then she lost the match to ~3c.
SET1_UNDERDOG_MAX_C = int(os.getenv("PREDICT_SET1_UNDERDOG_MAX", "50"))

# ── v3: favorite priority (user rule 07/10) ───────────────────────────────────
# A strict, deterministic ladder:
#   Priority 1 — ORIGINAL odds: only if BOTH known and |diff| > FAV_ODDS_EDGE_C
#                (>21, e.g. 61 vs 39 = 22); otherwise original odds are IGNORED.
#   Priority 2 — RANKINGS (from the rankings CSV; the WTA/ATP-vs-ITF category is
#                the CSV's own 'tour' column, independent of the match ticker):
#     2.1/2.2  a WTA/ATP ranking outranks an ITF (or absent) one — the player
#              with a WTA/ATP rank when the other lacks one is the favorite;
#     2.3      same category (both WTA/ATP, or both ITF) → by rank NUMBER:
#              2.3.1  rank diff > 90                                  → better rank
#              2.3.2  both ranks > 100, one in [100,250], diff > 49   → better rank
#              2.3.3  both ranks in (50,100), diff > 20               → better rank
#   Priority 3 — NEUTRAL (no favorite → None).
FAV_ODDS_EDGE_C = int(os.getenv("PREDICT_FAV_ODDS_EDGE", "21"))    # strict: diff must be > this


def _tour_group(tour) -> "str | None":
    """'main' for a WTA/ATP ranking, 'itf' for ITF, None if no ranking/unknown."""
    if not tour:
        return None
    t = str(tour).strip().upper()
    if t in ("ATP", "WTA"):
        return "main"
    if t == "ITF":
        return "itf"
    return None


def _rank_decides(rA: int, rB: int) -> "str | None":
    """The 2.3 same-category numeric rules. Returns the better-ranked side
    ('A'/'B') when a rule fires, else None."""
    if rA == rB:
        return None
    best = "A" if rA < rB else "B"
    lo, hi = min(rA, rB), max(rA, rB)
    diff = hi - lo
    if diff > 90:                                                  # 2.3.1
        return best
    if lo > 100 and hi > 100 and (100 <= lo <= 250 or 100 <= hi <= 250) and diff > 49:
        return best                                               # 2.3.2
    if 50 < lo < 100 and 50 < hi < 100 and diff > 20:             # 2.3.3
        return best
    return None


def determine_favorite(names: tuple, original_bids: dict, ranks: tuple, *,
                       rank_tours: tuple = (None, None),
                       live_bids: dict | None = None,
                       games: tuple | None = None, points: tuple | None = None):
    """
    Favorite priority (user rule 07/10). ``names`` = (A, B); ``original_bids`` =
    {name: cents}; ``ranks`` = (rank A, rank B); ``rank_tours`` = (tour A,
    tour B) from the rankings CSV (ATP/WTA/ITF/None). Returns "A" | "B" | None
    (None = Neutral / no favorite). ``live_bids``/``games``/``points`` are
    accepted for call-site compatibility but no longer used.
    """
    nA, nB = names
    oA, oB = original_bids.get(nA), original_bids.get(nB)
    rA, rB = _rk(ranks[0]), _rk(ranks[1])
    gA, gB = _tour_group(rank_tours[0]), _tour_group(rank_tours[1])

    # ── Priority 1: original odds, ONLY on a clear (>FAV_ODDS_EDGE_C) edge ──
    if oA is not None and oB is not None and abs(oA - oB) > FAV_ODDS_EDGE_C:
        return "A" if oA > oB else "B"

    # ── Priority 2: rankings ──
    a_main, b_main = gA == "main", gB == "main"
    # 2.1/2.2 — a WTA/ATP ranking beats an ITF-only or unranked opponent
    if a_main and not b_main:
        return "A"
    if b_main and not a_main:
        return "B"
    # 2.3 — same category (both WTA/ATP, or both ITF) → numeric rank rules
    if gA is not None and gA == gB and rA is not None and rB is not None:
        return _rank_decides(rA, rB)

    # ── Priority 3: Neutral ──
    return None


# ── v3: ultra-high trigger — strong favorite who is winning (user rule 07/09) ─
# A BUY that backs the favorite is upgraded to ULTRA-HIGH when the favorite has
# a large ORIGINAL-odds edge (>= FAV_ODDS_DIFF, e.g. Nicod 86 vs Azmeh 15) AND
# is currently at least holding/even on the scoreboard (not behind). Ultra-high
# buys skip the normal value band (buy if ULTRA lower<=bid<ULTRA_BUY_MAX) and
# the bot sizes them 1.5x (SPORT_ULTRA_FAV_CONTRACTS_MULT).
def _favorite_is_winning(md: dict, favside: str) -> bool:
    """True when the favorite is NOT behind: up a set, or level on sets and at
    least even on games in the current set."""
    a_sets, b_sets = md.get("sets", (0, 0))
    fav_sets = a_sets if favside == "A" else b_sets
    opp_sets = b_sets if favside == "A" else a_sets
    if fav_sets != opp_sets:
        return fav_sets > opp_sets
    ga, gb = md.get("games", (0, 0))
    fav_g = ga if favside == "A" else gb
    opp_g = gb if favside == "A" else ga
    return fav_g >= opp_g


def is_ultra_favorite(md: dict, side: Optional[str], names: tuple,
                      original_bids: dict) -> bool:
    """Whether backing ``side`` qualifies as an ultra-high strong-favorite buy:
    side is the favorite, the favorite's original-odds edge >= FAV_ODDS_DIFF,
    and the favorite is currently winning/holding."""
    fav = md.get("favorite")
    if fav is None or side is None or side != fav:
        return False
    nfav = names[0] if fav == "A" else names[1]
    nopp = names[1] if fav == "A" else names[0]
    ofav, oopp = original_bids.get(nfav), original_bids.get(nopp)
    if ofav is None or oopp is None or (ofav - oopp) < FAV_ODDS_DIFF:
        return False
    return _favorite_is_winning(md, fav)


def favorite_comeback_exit(md: Optional[dict], held_side: Optional[str],
                           entry_c: Optional[int], held_bid_c: Optional[int],
                           fav_bid_c: Optional[int]) -> tuple:
    """
    v3 exit rule: we bought the NON-favorite; if the pre-match (rank) favorite
    is coming back into the match, EXIT the trade even at a loss.

    Args: the kalshi md dict (for favorite/double_break), which side we hold
    ("A"/"B"), our entry price and both players' live bids in cents.
    Returns (exit: bool, reason: str).  Never fires when we hold the favorite
    (the stop-loss and favorite-protection rules own that case).
    """
    fav = (md or {}).get("favorite")
    if fav is None or held_side is None or held_side == fav:
        return False, "not holding a non-favorite"
    # 1) score reversal: the favorite now holds their own double-break
    if (md or {}).get("double_break") == fav:
        return True, "favorite has their own double-break"
    if held_bid_c is None or fav_bid_c is None:
        return False, "missing live bids"
    # 2) market reversal: the favorite's price caught/passed the held player's
    if fav_bid_c >= held_bid_c:
        return True, (f"favorite bid {fav_bid_c}c caught held player's "
                      f"{held_bid_c}c — market no longer backs our player")
    # 3) losing + near-parity: under water and the favorite is closing in
    if (entry_c and held_bid_c <= entry_c - EXIT_FAV_DROP_C
            and fav_bid_c >= held_bid_c - EXIT_FAV_PARITY_C):
        return True, (f"held bid {held_bid_c}c <= entry {entry_c}c - "
                      f"{EXIT_FAV_DROP_C}c and favorite within "
                      f"{EXIT_FAV_PARITY_C}c ({fav_bid_c}c) — comeback confirmed")
    return False, "favorite not coming back"


def favorite_collapse_exit(md: Optional[dict], held_side: Optional[str],
                           opp_bid_c: Optional[int]) -> tuple:
    """
    v3 exit rule (user 07/10): we HOLD the FAVORITE; if the favorite is being
    beaten badly and about to lose both sets — the NON-favorite (opponent) is
    now priced above EXIT_FAV_COLLAPSE_OPP_C during play — sell the favorite.

    Args: kalshi md (for favorite), which side we hold ("A"/"B"), and the
    opponent's live bid in cents. Returns (exit: bool, reason: str). Only fires
    when we hold the favorite (the comeback rule owns the non-favorite case).
    """
    fav = (md or {}).get("favorite")
    if fav is None or held_side is None or held_side != fav:
        return False, "not holding the favorite"
    if opp_bid_c is None:
        return False, "no opponent bid"
    if opp_bid_c > EXIT_FAV_COLLAPSE_OPP_C:
        return True, (f"non-favorite bid {opp_bid_c}c > {EXIT_FAV_COLLAPSE_OPP_C}c "
                      f"— favorite beaten badly, about to lose — sell")
    return False, "favorite not collapsing"


# ── bought-high collapse exit (user rule 07/10) ───────────────────────────────
# Point strings from the live score: "0","15","30","40", advantage as "40A"/"AD"/"A".
_POINT_RANK = {"0": 0, "15": 1, "30": 2, "40": 3}


def _point_val(s) -> Optional[int]:
    """Rank a tennis point string: 0/15/30/40 → 0/1/2/3, advantage → 4. None if
    unparseable."""
    if s is None:
        return None
    s = str(s).strip().upper()
    if s in ("AD", "A") or s.endswith("A"):      # advantage (e.g. '40A')
        return 4
    return _POINT_RANK.get(s)


def _within_two_points_of_game(self_pts, opp_pts) -> bool:
    """Best case (self wins every remaining point), is self <= 2 points from
    winning the CURRENT game?  advantage or 40-x → 1 point; deuce or 30-≤30 → 2
    points; anything else → more than 2."""
    a, b = _point_val(self_pts), _point_val(opp_pts)
    if a is None or b is None:
        return False
    if a == 4:                       # self has advantage → 1 point
        return True
    if a == 3:                       # self at 40 → 1 pt (opp<40) or 2 pts (deuce)
        return b <= 3
    if a == 2:                       # self at 30 → 2 pts only if opp ≤ 30
        return b <= 2
    return False


def _within_two_points_of_set(self_games, opp_games, self_pts, opp_pts) -> bool:
    """self is <= 2 points from winning the current SET: winning the current game
    would win the set (serving/receiving it out) AND self is <= 2 points from the
    game. Tiebreak (6-6) is treated as NOT within-2 (we don't suppress there)."""
    game_wins_set = (self_games >= 5 and (self_games - opp_games) >= 1
                     and not (self_games == 6 and opp_games == 6)
                     and not (self_games == 5 and opp_games == 5))
    return bool(game_wins_set and _within_two_points_of_game(self_pts, opp_pts))


def in_last_two_points_of_deciding_set(players) -> bool:
    """True when the match is in the last 2 points of the DECIDING (final) set:
    both players already hold SETS_TO_WIN-1 sets (e.g. 1-1 → set 3 in best-of-3)
    and one player is <= 2 points from winning the current set — hence the match.
    In this window the bought-high collapse exit stands down ('anybody's game')."""
    try:
        p1, p2 = players[0], players[1]
        s1, s2 = int(p1.get("sets_won") or 0), int(p2.get("sets_won") or 0)
        if s1 != SETS_TO_WIN - 1 or s2 != SETS_TO_WIN - 1:
            return False                          # not the deciding final set
        g1 = int((p1.get("games") or [0])[-1] or 0)
        g2 = int((p2.get("games") or [0])[-1] or 0)
        c1, c2 = p1.get("current_game"), p2.get("current_game")
        return (_within_two_points_of_set(g1, g2, c1, c2)
                or _within_two_points_of_set(g2, g1, c2, c1))
    except Exception:
        return False


def bought_high_collapse_exit(entry_c: Optional[int], held_bid_c: Optional[int],
                              players: Optional[list]) -> tuple:
    """
    v3 exit rule (user 07/10): if we bought this side ABOVE EXIT_HIGH_ENTRY_C (76c)
    and its live odds have since fallen BELOW EXIT_HIGH_COLLAPSE_C (25c), sell/exit
    — UNLESS the match is already in the last 2 points of the deciding set, where
    it's "anybody's game" and we let it settle. Independent of favorite status.
    Returns (exit: bool, reason: str).
    """
    if entry_c is None or held_bid_c is None:
        return False, "missing entry/live bid"
    if entry_c < EXIT_HIGH_ENTRY_C:              # 76c itself qualifies (user example)
        return False, f"entry {entry_c}c below {EXIT_HIGH_ENTRY_C}c"
    if held_bid_c >= EXIT_HIGH_COLLAPSE_C:
        return False, f"bid {held_bid_c}c not below {EXIT_HIGH_COLLAPSE_C}c"
    if in_last_two_points_of_deciding_set(players or []):
        return False, "last 2 points of deciding set — anybody's game, holding"
    return True, (f"bought high @ {entry_c}c but bid collapsed to {held_bid_c}c "
                  f"(< {EXIT_HIGH_COLLAPSE_C}c) before the deciding set's last 2 "
                  f"points — sell")


# ── combinations fallback table ───────────────────────────────────────────────
def load_combinations(path: Optional[str] = None) -> dict:
    """{(serving, "ga:gb", "pa:pb"): "A"|"B"} from tennis_all_combinations.csv."""
    p = Path(path or (Path(__file__).resolve().parent / "tennis_all_combinations.csv"))
    out: dict = {}
    if not p.exists():
        return out
    try:
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                srv = (r.get("Serving") or "").strip()
                lead = (r.get("Leading") or "").strip()
                m = re.match(r"\s*(\d+:\d+)\(([^)]*)\)", r.get("Current Score (A:B)") or "")
                if m and srv and lead:
                    out[(srv, m.group(1), m.group(2).replace(" ", ""))] = lead
    except Exception:
        pass
    return out


# ── helpers ───────────────────────────────────────────────────────────────────
def _firstname(name: str) -> str:
    """Lowercased, stripped first name for tolerant scraper search."""
    return (name or "").strip().split()[0].lower() if name and name.strip() else ""


def _rk(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _norm_pt(v) -> str:
    s = str(v if v is not None else "0").strip().upper()
    if s in ("A", "AD") or s.endswith("A"):
        return "A"
    return s if s in ("0", "15", "30", "40") else {"1": "15", "2": "30", "3": "40"}.get(s, "0")


_PT_RANK = {"0": 0, "15": 1, "30": 2, "40": 3, "A": 4}


def _is_break_point(serving, pa, pb) -> bool:
    if serving == "A":
        return pb == "A" or (pb == "40" and pa not in ("40", "A"))
    if serving == "B":
        return pa == "A" or (pa == "40" and pb not in ("40", "A"))
    return False


def _other(side: str) -> str:
    return "B" if side == "A" else "A"


# ── build match_data from a Kalshi MatchScore ─────────────────────────────────
def _md_from_kalshi(match: dict) -> Optional[dict]:
    players = match.get("players") or []
    if len(players) < 2:
        return None
    A, B = players[0], players[1]
    ag = list(A.get("games") or [])
    bg = list(B.get("games") or [])
    a_sets, b_sets = A.get("sets_won", 0), B.get("sets_won", 0)
    completed = a_sets + b_sets
    cur_a = ag[-1] if ag else 0
    cur_b = bg[-1] if bg else 0
    ra, rb = _rk(A.get("rank")), _rk(B.get("rank"))
    elite = (ra is not None and ra <= 10) or (rb is not None and rb <= 10)
    fav = None
    if ra is not None and rb is not None:            # both ranked → better rank wins
        if ra != rb:
            fav = "A" if ra < rb else "B"
    elif ra is not None:                              # only A ranked → A is favorite (NA = non-favorite)
        fav = "A"
    elif rb is not None:                              # only B ranked → B is favorite
        fav = "B"
    # both unranked (ra is None and rb is None) → fav stays None, skip
    serving = "A" if A.get("serving") else ("B" if B.get("serving") else None)
    pa, pb = _norm_pt(A.get("current_game")), _norm_pt(B.get("current_game"))

    s1w = s1m = s2w = s2m = None
    if completed >= 1 and ag and bg:
        s1w, s1m = ("A" if ag[0] > bg[0] else "B"), abs(ag[0] - bg[0])
    if completed >= 2 and len(ag) >= 2 and len(bg) >= 2:
        s2w, s2m = ("A" if ag[1] > bg[1] else "B"), abs(ag[1] - bg[1])

    margin = abs(cur_a - cur_b)
    dbreak = None
    if margin >= 3:                                  # ~double break within a set
        dbreak = "A" if cur_a > cur_b else "B"
    stay = None
    if serving == "A" and (cur_a, cur_b) in ((4, 5), (5, 6)):
        stay = "A"
    elif serving == "B" and (cur_b, cur_a) in ((4, 5), (5, 6)):
        stay = "B"

    return {
        "scenario": "elite" if elite else "parity",
        "favorite": fav, "fav_prob": None,
        "completed_sets": completed, "sets": (a_sets, b_sets),
        "set1_winner": s1w, "set1_margin": s1m,
        "set2_winner": s2w, "set2_margin": s2m,
        "games": (cur_a, cur_b), "serving": serving, "points": (pa, pb),
        "break_point": _is_break_point(serving, pa, pb),
        "double_break": dbreak, "stay_in_set": stay,
    }


# ── v2.0 situation engine ─────────────────────────────────────────────────────
def predict_v2(md: dict) -> tuple:
    """Return (side, confidence, situation, reason); side None = wait/fallback."""
    scen = md["scenario"]
    fav = md.get("favorite")
    favp = md.get("fav_prob")
    cs = md["completed_sets"]
    ga, gb = md["games"]
    pa, pb = md["points"]
    serving = md.get("serving")

    # ── E — double-break dead zone: back the set leader (match momentum) ──
    if md.get("double_break"):
        return md["double_break"], CONF_HIGH, "E", "double-break — back set leader"

    # ── D — serving to stay; only if the server has dropped >= 3 straight points
    #        (0-40, triple break point) back the receiver — not at just 0-15 ──
    if md.get("stay_in_set"):
        srv = md["stay_in_set"]
        recv = _other(srv)
        sp = pa if srv == "A" else pb
        rp = pb if srv == "A" else pa
        if sp == "0" and _PT_RANK.get(rp, 0) >= 3:
            return recv, CONF_HIGH, "D", "server dropped 3+ straight points staying in set"

    # ── set-structure situations ──
    if cs == 0:
        # SITUATION A — set 1 in progress
        if (ga + gb) < 4 and not md.get("break_point"):
            return None, None, "A", "wait (<4 games, no break yet)"
        if fav is None:
            return None, None, "A", "no pre-match favorite"
        fav_g = ga if fav == "A" else gb
        opp_g = gb if fav == "A" else ga
        if fav_g >= opp_g:                       # favorite holding / leading
            return fav, (CONF_HIGH if scen == "elite" else CONF_MED), "A", "favorite holding"
        if scen == "elite":                      # favorite broken, elite → back anyway
            return fav, CONF_MED, "A", "elite favorite broken — back recovery"
        return _other(fav), CONF_MED, "A", "parity: favorite broken, back underdog"

    if cs == 1:
        # SITUATION B — set 1 completed
        s1w, s1m = md.get("set1_winner"), md.get("set1_margin")
        if s1w is None:
            return None, None, "B", "wait"
        if fav is None:
            return s1w, CONF_LOW, "B", "set1 winner (no favorite)"
        if s1w == fav:
            # 06/28 settlement study: backing the set-1-winning favorite has NO edge —
            # in-band (68-84c) it ran 49 trades, 73% win, -$17 under TP+40%; held to
            # settlement -$16/70%.  A set-1 winner is efficiently priced, so 73% isn't
            # enough once TP caps the upside but a loss costs full freight.  WAIT.
            return fav, CONF_LOW, "B", "favorite won set1 — efficiently priced, no edge (wait)"
        if s1m >= 4:                             # dominant upset
            if scen == "elite":
                return fav, CONF_MED, "B", "elite fav lost set1 dominantly — bounce-back"
            # tagged "Bsweep" so this 2-0 sweep play stays separable in the trade log
            return s1w, CONF_HIGH, "Bsweep", "parity: set1 winner closes 2-0"
        if favp is not None and favp >= HEAVY_FAV_CENTS and s1m <= 2:   # tight upset trap
            return _other(fav), CONF_MED, "B", "heavy fav lost tight set1 — back underdog"
        return s1w, CONF_LOW, "B", "set1 winner (other margin)"

    if cs == 2:
        # SITUATION F — set 3 decider (split 1-1)
        a_sets, b_sets = md["sets"]
        if a_sets == 1 and b_sets == 1:
            if scen == "elite" and fav:
                return fav, CONF_HIGH, "F", "elite decider — back favorite"
            # Parity set-3 deciders without the F3 odds signal are a coin flip:
            # backtest 06/23-25 the "dominant set2 winner" MED bucket went 17 trades,
            # 41% win, +$0.04/trade (net ~$0) while F3 (odds close-decider) ran 70%
            # win / +$22.59.  Downgrade both to LOW (→ WAIT) so only F (elite) and the
            # F3 return-pressure play trade the decider.
            s2w, s2m = md.get("set2_winner"), md.get("set2_margin")
            if s2w and s2m and s2m >= 4:
                return s2w, CONF_LOW, "F", "parity decider: dominant set2 winner — wait (coin flip)"
            if serving:
                return serving, CONF_LOW, "F", "parity decider: back set3 opener server"

    return None, None, "fallback", "defer to micro-state"


# ── fallback micro-state engine ───────────────────────────────────────────────
def _combo_fallback(md: dict, combos: Optional[dict]) -> tuple:
    ga, gb = md["games"]
    pa, pb = md["points"]
    serving = md.get("serving")

    # asymmetric scoreboard at 5 games.  Log analysis (06/22-23): backing the
    # 5-game RECEIVER collapsed ~70% of the time (premature — server usually holds
    # to 5-5), so it is downgraded to LOW (→ WAIT).  The 5-game SERVER (serving for
    # the set) is a real edge but at ULTRA it ignored the band and bought ~85c and
    # still lost ~57%; downgraded to HIGH so it respects the band / set-1 cap.
    if max(ga, gb) == 5 and ga != gb:
        five = "A" if ga > gb else "B"
        if serving == five:
            return five, CONF_HIGH, "fallback", "5-game server serving for set"
        return five, CONF_LOW, "fallback", "5-game receiver (needs a break) — wait"

    # symmetric games → up on points; tie → server
    if ga == gb:
        ra, rb = _PT_RANK.get(pa, 0), _PT_RANK.get(pb, 0)
        if ra > rb:
            return "A", CONF_LOW, "fallback", "symmetric: A ahead on points"
        if rb > ra:
            return "B", CONF_LOW, "fallback", "symmetric: B ahead on points"
        if serving:
            return serving, CONF_LOW, "fallback", "symmetric tie: edge to server"

    # combinations.csv lookup
    if combos:
        key = (serving, f"{min(ga, 5)}:{min(gb, 5)}", f"{pa}:{pb}")
        lead = combos.get(key)
        if lead:
            return lead, CONF_LOW, "fallback", "combinations.csv leader"
    return None, None, "fallback", "undetermined"


# ── set-3 close-decider (odds + return pressure) ──────────────────────────────
def _set3_decider(md: dict, names: tuple, live_bids: dict, original_bids: dict) -> tuple:
    """
    Deciding set (1-1) play: when the pre-match (original) odds were CLOSE and the
    slight original favorite is at least even on LIVE odds AND has won a point on
    the opponent's serve (return pressure) in set 3, back that player HIGH.
    e.g. Kunitsyn* vs Chen 1-1: 5-7,6-4,0-0 (15:15) live{49;50} orig{50;53}
         → Chen (orig 53, live 50≥49, returning & has a point) → BUY high.
    Returns (side, conf, situation, reason); side None when it does not apply.
    """
    nA, nB = names
    oA, oB, lA, lB = (original_bids.get(nA), original_bids.get(nB),
                      live_bids.get(nA), live_bids.get(nB))
    if None in (oA, oB, lA, lB):
        return None, None, "F3", "set-3: missing odds"
    if abs(oA - oB) > SET3_CLOSE_C:
        return None, None, "F3", "set-3: original odds not close"
    favside = "A" if oA >= oB else "B"                 # slight original favorite
    fav_live = lA if favside == "A" else lB
    opp_live = lB if favside == "A" else lA
    fav_pts = md["points"][0] if favside == "A" else md["points"][1]
    serving = md.get("serving")
    returning = serving is not None and serving != favside   # favorite is returning
    if fav_live >= opp_live and returning and _PT_RANK.get(fav_pts, 0) >= 1:
        return favside, CONF_HIGH, "F3", "set-3 close decider: favorite even+ with a return point"
    return None, None, "F3", "set-3 decider: conditions not met"


# ── strong original favorite + set-2 management ───────────────────────────────
def _strong_original_favorite(match: dict, names: tuple, original_bids: dict) -> tuple:
    """The clear original favorite, requiring BOTH a rank edge >= FAV_RANK_DIFF and
    an original-odds edge >= FAV_ODDS_DIFF.  Returns (side, name) or (None, None)."""
    players = match.get("players") or []
    if len(players) < 2:
        return None, None
    rA, rB = _rk(players[0].get("rank")), _rk(players[1].get("rank"))
    nA, nB = names
    oA, oB = original_bids.get(nA), original_bids.get(nB)
    if None in (rA, rB, oA, oB):
        return None, None
    if rA < rB and (rB - rA) >= FAV_RANK_DIFF and (oA - oB) >= FAV_ODDS_DIFF:
        return "A", nA
    if rB < rA and (rA - rB) >= FAV_RANK_DIFF and (oB - oA) >= FAV_ODDS_DIFF:
        return "B", nB
    return None, None


def _set2_favorite(match: dict, md: dict, names: tuple,
                   live_bids: dict, original_bids: dict) -> tuple:
    """
    Set-2 management when a STRONG original favorite (rank+odds) WON set 1.
    Returns (applies, (side, conf, situation, reason)); applies False → not this case.
      1) wait until set 2 reaches the 5th game (>= SET2_MIN_GAMES games played)
      2) if the favorite's live price dropped sharply (>= FAV_DROP_C) AND the
         favorite is serving → BUY the favorite (value) regardless of set-2 score
      3) else if set 2 still favours the favorite (>= on games) → BUY (band/confidence)
         else → wait
    """
    favside, favname = _strong_original_favorite(match, names, original_bids)
    if favside is None or md.get("set1_winner") != favside:
        return False, (None, None, None, None)
    ga, gb = md["games"]                                  # current (set-2) games
    if (ga + gb) < SET2_MIN_GAMES:                        # (1) too early
        return True, (None, None, "B2", "set-2 too early — wait for 5th game")
    fav_live, fav_orig = live_bids.get(favname), original_bids.get(favname)
    if (fav_orig is not None and fav_live is not None
            and (fav_orig - fav_live) >= FAV_DROP_C and md.get("serving") == favside):
        return True, (favside, CONF_HIGH, "B2",          # (2) sharp drop + serving → value buy
                      "favorite price dropped sharply + serving — value buy")
    fav_g = ga if favside == "A" else gb
    opp_g = gb if favside == "A" else ga
    if fav_g >= opp_g:                                    # (3) set 2 still favouring favorite
        return True, (favside, CONF_HIGH, "B", "favorite won set1, holding set2")
    return True, (None, None, "B2", "favorite faltering in set 2, no price drop — wait")


def _favorite_rebound(md: dict, names: tuple, live_bids: dict) -> tuple:
    """
    When the pre-match (rank) favorite is behind/losing set 1, or has lost set 1,
    NEVER back the opponent — wait for the favorite's own live price to fall into
    [FAV_REBOUND_LO, FAV_REBOUND_HI] (a real discount), then buy the favorite.
    e.g. Semanova vs Bouzkova: Bouzkova (favorite) lost set 1 — the model backed
    Semanova (the set1 winner) at 68c and lost; it should instead have waited for
    Bouzkova's own price to recover into 50-60c and bought Bouzkova.
    Returns (applies, (side, conf, situation, reason)); applies False → favorite is
    fine (winning/won set 1, or unknown) → fall through to the normal engine.
    """
    fav = md.get("favorite")
    if fav is None:
        return False, (None, None, None, None)
    if md.get("double_break"):        # situation E is the strongest signal in the
        return False, (None, None, None, None)   # model — always let it fire first
    cs = md["completed_sets"]
    if cs == 0:
        ga, gb = md["games"]
        fav_g = ga if fav == "A" else gb
        opp_g = gb if fav == "A" else ga
        serving = md.get("serving")
        bp_against_fav = bool(md.get("break_point")) and serving is not None and serving != fav
        behind = (ga + gb) >= 4 and fav_g < opp_g
        if not (behind or bp_against_fav):
            return False, (None, None, None, None)        # favorite fine — not this case
    elif cs == 1:
        s1w = md.get("set1_winner")
        if s1w is None or s1w == fav:
            return False, (None, None, None, None)        # favorite won (or unknown) set1
    else:
        return False, (None, None, None, None)            # set-3 decider handles itself

    # Bfav BUY disabled here too (user request 07/07) — same reason as the current
    # model: corrected-P&L shows 40% win / -$153 total, -EV under TP+30%.  Only the
    # protective half survives: favorite behind/lost set1 → force WAIT, never back
    # the opponent.  (This snapshot's other weekend rules remain unchanged.)
    fav_name = names[0] if fav == "A" else names[1]
    fav_bid = live_bids.get(fav_name)
    if fav_bid is None:
        return True, (None, None, "Bfav", "favorite behind/lost set1 — no live bid, wait")
    return True, (None, None, "Bfav",
                  f"favorite behind/lost set1 (bid {fav_bid}c) — wait, never buy the opponent "
                  f"(rebound BUY disabled 07/07)")


# ── public: predict + buy gate ────────────────────────────────────────────────
def predict_buy(match: dict, live_bids: dict, original_bids: dict, *,
                combos: Optional[dict] = None,
                bid_range: tuple = (BID_LO, BID_HI),
                ticker: Optional[str] = None,
                neutral_favorite: bool = False) -> dict:
    """
    Predict the match winner via the v2.0 engine and gate on bid band.
    Returns {action: BUY|SKIP|WAIT, player, side, bid, confidence, situation,
             reason, score, tip}.

    ``neutral_favorite=True`` (finals rule, user 07/12) forces the favourite to
    None/Neutral: every favorite-keyed rule (set-2 favorite, rebound, ultra-high
    upgrade, backing_favorite sizing) is bypassed and only the neutral situation
    engine + combo fallback decide.
    """
    players = match.get("players") or []
    if len(players) < 2:
        return {"action": "WAIT", "ticker": ticker, "reason": "no players"}
    names = (players[0].get("name", ""), players[1].get("name", ""))
    md = _md_from_kalshi(match)
    if md is None:
        return {"action": "WAIT", "ticker": ticker, "reason": "no match data"}
    # v3 favorite priority (07/10): original-odds edge >21c, else WTA/ATP-vs-ITF
    # ranking category + rank-difference rules, else Neutral — overrides
    # _md_from_kalshi's rank-only pick. rank_tour comes from the rankings CSV.
    md["favorite"] = determine_favorite(
        names, original_bids,
        (players[0].get("rank"), players[1].get("rank")),
        rank_tours=(players[0].get("rank_tour"), players[1].get("rank_tour")))
    if neutral_favorite:                         # finals rule → always Neutral
        md["favorite"] = None
    if md.get("favorite"):                       # favorite's pre-match implied %
        fn = names[0] if md["favorite"] == "A" else names[1]
        md["fav_prob"] = original_bids.get(fn)

    # priority overrides: set-3 close-decider, and set-2 strong-favorite management
    side = conf = situation = reason = None
    if md["completed_sets"] == 2:
        side, conf, situation, reason = _set3_decider(md, names, live_bids, original_bids)
    elif md["completed_sets"] == 1:
        applies, dec = _set2_favorite(match, md, names, live_bids, original_bids)
        if applies:                              # strong fav won set 1 → this rule governs
            side, conf, situation, reason = dec
            if side is None:                     # its decision is WAIT (too early / faltering)
                return {"action": "WAIT", "ticker": ticker, "situation": situation,
                        "reason": reason, "score": one_liner(match)}
        if side is None:                         # favorite didn't win set1 (or rule N/A)
            applies, dec = _favorite_rebound(md, names, live_bids)
            if applies:
                side, conf, situation, reason = dec
                if side is None:
                    return {"action": "WAIT", "ticker": ticker, "situation": situation,
                            "reason": reason, "score": one_liner(match)}
    elif md["completed_sets"] == 0:
        applies, dec = _favorite_rebound(md, names, live_bids)
        if applies:
            side, conf, situation, reason = dec
            if side is None:
                return {"action": "WAIT", "ticker": ticker, "situation": situation,
                        "reason": reason, "score": one_liner(match)}
    if side is None:                             # else fall to the v2.0 situation engine
        side, conf, situation, reason = predict_v2(md)
    if side is None:
        if "wait" in (reason or "").lower():     # genuine wait (too early)
            return {"action": "WAIT", "ticker": ticker, "situation": situation,
                    "reason": reason, "score": one_liner(match)}
        side, conf, situation, reason = _combo_fallback(md, combos)   # undecided → micro-state

    if side is None:
        return {"action": "WAIT", "ticker": ticker, "situation": situation,
                "reason": reason, "score": one_liner(match)}

    # v3 (user rule 07/09, Oliveira): in SET 1, never back a pre-match UNDERDOG.
    # A first-set lead/double-break by someone the market priced as the underdog
    # is a low-confidence match-winner signal — wait for a completed set.
    if md["completed_sets"] == 0:
        led_o = original_bids.get(names[0] if side == "A" else names[1])
        opp_o = original_bids.get(names[1] if side == "A" else names[0])
        underdog = (led_o is not None
                    and (led_o < SET1_UNDERDOG_MAX_C
                         or (opp_o is not None and led_o < opp_o)))
        if underdog:
            return {"action": "WAIT", "ticker": ticker, "situation": situation,
                    "player": names[0] if side == "A" else names[1], "side": side,
                    "confidence": conf,
                    "reason": reason + f" | set-1 pre-match underdog "
                                       f"(orig {led_o}c) — skip low-confidence buy",
                    "score": one_liner(match), "favorite": md.get("favorite")}

    # v3 (user rule 07/09): a strong original favorite who is winning is our
    # highest-conviction read — upgrade to ULTRA-HIGH so the buy gate skips the
    # value band and the bot sizes it 1.5x.
    if is_ultra_favorite(md, side, names, original_bids):
        conf = CONF_ULTRA
        reason = f"{reason} | strong favorite winning — ultra-high"

    name = names[0] if side == "A" else names[1]
    bid = live_bids.get(name)
    lo, hi = bid_range
    cs = md["completed_sets"]
    out = {"ticker": ticker, "situation": situation, "player": name, "side": side,
           "bid": bid, "confidence": conf, "reason": reason, "score": one_liner(match),
           # expose the determined favorite so the bot can size up an ultra-high
           # BUY that backs the favorite (user rule 07/09)
           "favorite": md.get("favorite"),
           "backing_favorite": bool(md.get("favorite")) and side == md.get("favorite")}
    if bid is None:
        return {**out, "action": "SKIP", "reason": reason + " | no live bid"}

    tip = f"{name.split()[-1]} >> buy at {bid}c ({conf})"

    # ── confidence-based buy gate ─────────────────────────────────────────────
    #   ultra high → ignore band; buy if bid < ULTRA_BUY_MAX (85c)
    #   high       → current flow (buy if bid in band)
    #   medium     → set 1: WAIT for set 2 & re-predict; set 2/3: current flow
    #   low        → WAIT (skip until a medium+ prediction)
    if conf == CONF_LOW:
        return {**out, "action": "WAIT",
                "reason": reason + " | low confidence — wait for medium+"}

    # ── set-2 price gate: a BUY signal during set 2 (3rd set not started) only
    #    executes below SET2_MAX_BID; otherwise WAIT — the watcher keeps polling,
    #    so the order goes in only if/when the price dips into range ──
    if cs == 1 and bid >= SET2_MAX_BID:
        return {**out, "action": "WAIT",
                "reason": reason + f" | set-2: waiting for bid < {SET2_MAX_BID}c (now {bid}c)"}

    if conf == CONF_ULTRA:
        if ULTRA_BUY_MIN <= bid < ULTRA_BUY_MAX:
            return {**out, "action": "BUY", "tip": tip}
        return {**out, "action": "SKIP",
                "reason": reason + f" | ultra high but bid {bid}c outside "
                                   f"{ULTRA_BUY_MIN}-{ULTRA_BUY_MAX - 1}c"}

    if conf == CONF_MED and cs == 0:
        return {**out, "action": "WAIT",
                "reason": reason + " | medium in set 1 — wait for set 2 to re-predict"}

    # high, or medium in set 2/3 → band flow; in set 1 (non-ultra) cap bid < SET1_MAX_BID
    eff_hi = min(hi, SET1_MAX_BID - 1) if cs == 0 else hi
    if lo <= bid <= eff_hi:
        return {**out, "action": "BUY", "tip": tip}
    return {**out, "action": "SKIP", "reason": reason + f" | bid {bid}c outside {lo}-{eff_hi}c"}


# ── scraper-backed path (on-demand; launches a browser) ───────────────────────
async def scrape_match_data(player1: str, player2: Optional[str] = None) -> dict:
    """
    Live match data for ``player1`` (and optional ``player2``) via the SofaScore
    Playwright scraper, searched by first name (lowercased/stripped).  Heavy
    (launches a browser) — use on demand, not inside the bot's poll loop.
    """
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "web"))
        from tennis_live_match_scraper import scrape_live_match  # type: ignore
    except Exception as e:                       # pragma: no cover
        return {"status": "scraper unavailable", "error": str(e)}
    return await scrape_live_match(_firstname(player1),
                                   _firstname(player2) if player2 else None)


async def live_statuses() -> list:
    """All live tennis match statuses in one browser session (see scraper).
    Returns [] on failure so callers can fail open."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent / "web"))
        from tennis_live_match_scraper import get_live_statuses  # type: ignore
    except Exception:
        return []
    try:
        return await get_live_statuses()
    except Exception:
        return []


def _md_from_scraper(d: dict) -> dict:
    """Convert the scraper's match dict (A=home/B=away) into the v2 md shape."""
    scen = "elite" if "Elite" in str(d.get("scenario_type") or "") else "parity"
    cg = (str(d.get("current_games") or "0:0").split(":") + ["0", "0"])[:2]
    cp = (str(d.get("current_points") or "0:0").split(":") + ["0", "0"])[:2]
    ga, gb = _rk(cg[0]) or 0, _rk(cg[1]) or 0
    pa, pb = _norm_pt(cp[0]), _norm_pt(cp[1])
    cs = max(0, (d.get("current_set") or 1) - 1)
    s1w, s1m = d.get("set_1_winner"), d.get("set_1_margin")
    serving = d.get("serving")
    margin = abs(ga - gb)
    dbreak = (("A" if ga > gb else "B")
              if (d.get("double_break_detected") == "YES" or margin >= 3) else None)
    sets = (1, 1) if cs >= 2 else ((1, 0) if (cs == 1 and s1w == "A")
                                   else (0, 1) if cs == 1 else (0, 0))
    return {
        "scenario": scen, "favorite": d.get("pre_match_favorite"), "fav_prob": None,
        "completed_sets": cs, "sets": sets,
        "set1_winner": s1w, "set1_margin": s1m, "set2_winner": None, "set2_margin": None,
        "games": (ga, gb), "serving": serving, "points": (pa, pb),
        "break_point": d.get("break_point") == "YES", "double_break": dbreak,
        "stay_in_set": (serving if d.get("stay_in_set_pressure") == "YES" else None),
    }


async def predict_for_player(player1: str, player2: Optional[str] = None, *,
                             combos: Optional[dict] = None) -> dict:
    """
    Standalone prediction for a live match via the scraper (search by first name).
    Returns {action, side, confidence, situation, reason, raw}. Heavy (browser).
    """
    d = await scrape_match_data(player1, player2)
    if d.get("status") != "In-Progress":
        return {"action": "WAIT", "reason": d.get("status", "no match"), "raw": d}
    md = _md_from_scraper(d)
    side, conf, sit, reason = predict_v2(md)
    if side is None and "wait" not in (reason or "").lower():
        side, conf, sit, reason = _combo_fallback(md, combos or load_combinations())
    return {"action": ("PREDICT" if side else "WAIT"), "side": side,
            "confidence": conf, "situation": sit, "reason": reason, "raw": d}


# ── async poller over live Kalshi matches ─────────────────────────────────────
def _load_bot():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "kalshi"))
    import bot_kalshi_sports_v1 as bot           # type: ignore[import-not-found]
    return bot


async def _demo() -> None:
    bot = _load_bot()
    import kalshi_sports as ks                   # type: ignore[import-not-found]
    from tennis_live_score import load_rankings_csv
    combos = load_combinations()
    rankings = load_rankings_csv()
    c = bot.KalshiClient()
    try:
        live = await ks.filter_by_sport_min_volume_live("tennis", 0, top_n=12, client=c)
        print(f"v2.0 predictions ({len(live)} live, band {BID_LO}-{BID_HI}c):\n")
        for tm in live:
            sc = await bot.get_kalshi_tennis_score(c, tm["ticker"])
            if not sc:
                continue
            for p in sc.get("players", []):
                rk = rank_for(p.get("name", ""), rankings)
                p["rank"] = rk if rk is not None else "NA"
            lv, og = await bot.get_player_odds(c, tm["ticker"], sc.get("match_start"))
            sig = predict_buy(sc, lv, og, combos=combos, ticker=tm["ticker"])
            print(f"  [{sig['action']:4}] {sig.get('score','')}")
            print(f"          -> {sig.get('tip') or sig.get('reason')}  "
                  f"(conf={sig.get('confidence')}, sit={sig.get('situation')})")
    finally:
        await c.close()


def main() -> None:
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    asyncio.run(_demo())


if __name__ == "__main__":
    main()
