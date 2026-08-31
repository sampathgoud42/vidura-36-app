#!/usr/bin/env python3
"""
prediction_baseball_v1.py — live baseball (MLB/NPB/KBO) scalp model.
====================================================================
Sabermetric live win-probability engine + market-vs-model edge detector for
the Kalshi baseball bot (bot_kalshi_sports_v2.py).  Goal: find entries where a
live position can be exited/hedged for a >= BASEBALL_SCALP_PCT (default 10%)
net profit within ~1-2 innings.

Model
-----
1.  Win probability from the current game state (normal approximation of the
    remaining run-differential distribution):
        z  = effective_lead / sqrt(var_per_half_inning * remaining_halves)
        WP = Phi(z)
    where effective_lead = (home_runs - away_runs)
        + RE24 base/out expected-runs adjustment for the team at bat
        + a home-field edge that decays as the game progresses.
2.  Implied probability check: each side's live YES bid (cents) IS the
    market's probability.  edge_c = model_WP*100 - live_bid.
3.  The 10% scalp setup: BUY the side with edge_c >= BASEBALL_MIN_EDGE_C at
    its live bid, exit trigger = resting TP sell at entry * (1+SCALP_PCT%).
    The natural catalyst is simply the market catching up to the base-out /
    inning state (scoreless half-innings move a leader's price ~3-6c each).
4.  Risk: stop-loss BASEBALL_STOP_LOSS_C cents below entry (a crooked-number
    inning against us), enforced by the bot's guardian.

All config comes from environment variables — the bot loads them from
``prediction-trade/kalshi/sports/kaslhi_sports.env`` before importing this
module (keys documented there, section "Baseball bot v2").

Run standalone for a demo evaluation:
    python prediction_baseball_v1.py
"""
from __future__ import annotations

import math
import os
from typing import Optional

# ── confidence labels (same vocabulary as the tennis predictor) ──────────────
CONF_ULTRA = "ultra high"
CONF_HIGH = "high"
CONF_MED = "medium"
CONF_LOW = "low"

# ── config (kaslhi_sports.env — loaded by the bot before this import) ────────
SCALP_PCT = float(os.getenv("BASEBALL_SCALP_PCT", "10"))     # target net profit %
BID_LO = int(os.getenv("BASEBALL_BID_LO", "30"))             # entry band (cents)
BID_HI = int(os.getenv("BASEBALL_BID_HI", "84"))
MIN_EDGE_C = float(os.getenv("BASEBALL_MIN_EDGE_C", "6"))    # model - market (cents)
ULTRA_EDGE_C = float(os.getenv("BASEBALL_ULTRA_EDGE_C", "14"))
MIN_INNING = int(os.getenv("BASEBALL_MIN_INNING", "3"))      # no entries before this
STOP_LOSS_C = int(os.getenv("BASEBALL_STOP_LOSS_C", "18"))   # stop = entry - this
MAX_TP_C = int(os.getenv("SPORT_MAX_TP_C", "98"))            # TP must stay <= this
# home-field advantage in runs over a FULL remaining game (decays linearly)
HOME_EDGE_RUNS = float(os.getenv("BASEBALL_HOME_EDGE_RUNS", "0.12"))
# variance of the run DIFFERENTIAL added per half-inning.  0.60/half-inning →
# full-game run-diff sigma = sqrt(18*0.60) ≈ 3.3 runs (matches MLB empirics).
HALF_INN_VAR = float(os.getenv("BASEBALL_HALF_INN_VAR", "0.60"))
# market-overreaction situation: original favorite (orig bid >= this) …
OVERREACT_FAV_MIN_C = int(os.getenv("BASEBALL_OVERREACT_FAV_MIN_C", "55"))
# … whose live bid dropped at least this many cents below the original
OVERREACT_DROP_C = int(os.getenv("BASEBALL_OVERREACT_DROP_C", "15"))
# ── sports4cast gate (user rule 07/12) ────────────────────────────────────────
# A BUY only executes when the team has >= this win %% in baseball_data.csv
# (scraped daily at 8:15 AM CST from sports4cast.com by baseball4cast_scraper).
FOURCAST_MIN_PCT = float(os.getenv("BASEBALL_4CAST_MIN_PCT", "50"))
# Team not found in the data (NPB/LMB — the feed is MLB-only, or a stale CSV):
# FALSE (default) = fail open (buy allowed, noted in the reason);
# TRUE = block the buy unless the team is present with >= FOURCAST_MIN_PCT.
FOURCAST_REQUIRE = os.getenv("BASEBALL_4CAST_REQUIRE", "FALSE").strip().upper() == "TRUE"
try:
    from baseball4cast_scraper import team_pct as _4cast_team_pct
except ImportError:                                    # package-style import
    try:
        from baseball.baseball4cast_scraper import team_pct as _4cast_team_pct
    except Exception:                                  # pragma: no cover
        _4cast_team_pct = None
except Exception:                                      # pragma: no cover
    _4cast_team_pct = None

# ── RE24 run-expectancy matrix (league-average, expected runs rest-of-inning) ─
# keyed by (frozenset of occupied bases, outs).  Base tokens: "1B","2B","3B".
_RE24 = {
    (frozenset(), 0): 0.48, (frozenset(), 1): 0.25, (frozenset(), 2): 0.10,
    (frozenset({"1B"}), 0): 0.85, (frozenset({"1B"}), 1): 0.51, (frozenset({"1B"}), 2): 0.22,
    (frozenset({"2B"}), 0): 1.06, (frozenset({"2B"}), 1): 0.64, (frozenset({"2B"}), 2): 0.31,
    (frozenset({"3B"}), 0): 1.30, (frozenset({"3B"}), 1): 0.95, (frozenset({"3B"}), 2): 0.35,
    (frozenset({"1B", "2B"}), 0): 1.44, (frozenset({"1B", "2B"}), 1): 0.88,
    (frozenset({"1B", "2B"}), 2): 0.43,
    (frozenset({"1B", "3B"}), 0): 1.75, (frozenset({"1B", "3B"}), 1): 1.10,
    (frozenset({"1B", "3B"}), 2): 0.48,
    (frozenset({"2B", "3B"}), 0): 1.96, (frozenset({"2B", "3B"}), 1): 1.39,
    (frozenset({"2B", "3B"}), 2): 0.56,
    (frozenset({"1B", "2B", "3B"}), 0): 2.29, (frozenset({"1B", "2B", "3B"}), 1): 1.54,
    (frozenset({"1B", "2B", "3B"}), 2): 0.75,
}
_RE_EMPTY0 = _RE24[(frozenset(), 0)]                     # fresh-half baseline


def _norm_bases(bases) -> frozenset:
    """Normalize a bases input ("1B,3B", ["1B","3B"], {"1B"}, None) → frozenset."""
    if not bases:
        return frozenset()
    if isinstance(bases, str):
        bases = bases.replace(";", ",").split(",")
    out = set()
    for b in bases:
        t = str(b).strip().upper().replace("ST", "B").replace("ND", "B").replace("RD", "B")
        t = {"1": "1B", "2": "2B", "3": "3B", "FIRST": "1B", "SECOND": "2B",
             "THIRD": "3B"}.get(t, t)
        if t in ("1B", "2B", "3B"):
            out.add(t)
    return frozenset(out)


def run_expectancy(bases, outs: Optional[int]) -> float:
    """RE24 expected runs for the rest of this half-inning (0.0 if state unknown)."""
    if outs is None:
        return 0.0
    o = max(0, min(2, int(outs)))
    return _RE24.get((_norm_bases(bases), o), _RE_EMPTY0)


def _phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def win_probability(home_runs: int, away_runs: int, inning: int,
                    half: Optional[str], *, outs: Optional[int] = None,
                    bases=None) -> float:
    """
    HOME team's live win probability from the current base-out state.

    Args:
        home_runs/away_runs: current score.
        inning:  current inning number (1-based; >9 = extras).
        half:    "top" | "bottom" | None (unknown → mid-inning assumption).
        outs:    outs in the current half (None = unknown).
        bases:   occupied bases for the team at bat ("1B,3B", list/set, or None).
    Returns:
        float in [0.015, 0.985] — clamped so a scalp always has a hedge price.
    """
    inning = max(1, int(inning or 1))
    h = (half or "").strip().lower()
    completed_halves = 2 * (inning - 1) + (1 if h in ("bottom", "bot", "b") else 0)
    # fraction of the CURRENT half still to be played
    frac_cur = (3 - outs) / 3.0 if outs is not None else 0.5
    total_halves = max(18, 2 * inning)                    # extras extend the game
    remaining = max(0.5, total_halves - completed_halves - 1 + frac_cur)

    diff = float(home_runs - away_runs)
    # team at bat gets credit for its base-out state (runs already "in motion")
    re_adj = max(0.0, run_expectancy(bases, outs) - _RE_EMPTY0 * frac_cur)
    if h in ("bottom", "bot", "b"):
        diff += re_adj
    elif h in ("top", "t"):
        diff -= re_adj
    # home-field edge decays with the fraction of the game remaining
    diff += HOME_EDGE_RUNS * (remaining / 18.0)

    sigma = math.sqrt(HALF_INN_VAR * remaining)
    wp = _phi(diff / max(sigma, 0.20))
    return min(0.985, max(0.015, wp))


def scalp_tp_cents(entry_c: int, pct: float = SCALP_PCT) -> int:
    """TP sell price locking a >= ``pct``% net gain over ``entry_c`` (cents)."""
    return min(99, max(entry_c + 1, math.ceil(entry_c * (1 + pct / 100.0))))


def _fmt_inning(g: dict) -> str:
    h = str(g.get("half") or "?").capitalize()
    return f"{h} {g.get('inning', '?')}"


def _analysis(g: dict, team: str, is_home: bool, wp: float, bid: int,
              tp: int, stop: int, edge: float) -> dict:
    """The 4-part structured breakdown (implied check / setup / leverage / risk)."""
    opp = g.get("away") if is_home else g.get("home")
    lead = ((g.get("home_runs") or 0) - (g.get("away_runs") or 0)) * (1 if is_home else -1)
    state = (f"{_fmt_inning(g)}, "
             + (f"{g['outs']} out, " if g.get("outs") is not None else "")
             + (f"bases {','.join(sorted(_norm_bases(g.get('bases')))) or 'empty'}, "
                if g.get("outs") is not None else "")
             + f"{'leads' if lead > 0 else 'trails' if lead < 0 else 'tied'} "
             + (f"by {abs(lead)}" if lead else ""))
    return {
        "implied_check": (f"market implies {bid}% for {team}; model (inning/score/"
                          f"base-out normal approx) says {wp * 100:.1f}% — the book is "
                          f"{'under' if edge > 0 else 'over'}pricing them by {abs(edge):.1f}c"),
        "scalp_setup": (f"BUY {team} YES @ {bid}c now; exit trigger = resting sell "
                        f"@ {tp}c (+{SCALP_PCT:.0f}% net) — typically reached after "
                        f"1-2 scoreless half-innings {'holding' if lead >= 0 else 'or a tying rally'}"),
        "leverage": (f"{team} {state.strip(', ')}; each clean half-inning from here "
                     f"moves the leader's price ~3-6c toward settlement, and the "
                     f"{'home bottom-half advantage' if is_home else 'road lead'} "
                     f"compounds it late"),
        "risk": (f"worst case: a crooked-number inning by {opp} flips the state — "
                 f"stop-loss exits at {stop}c (entry-{STOP_LOSS_C}c); beyond that the "
                 f"guardian's hard floor caps a blowout"),
    }


def predict_scalp(game: dict, live_bids: dict, original_bids: Optional[dict] = None,
                  *, ticker: Optional[str] = None) -> dict:
    """
    Evaluate one live baseball game for a >= SCALP_PCT% scalp entry.

    Args:
        game: {home, away, home_runs, away_runs, inning, half, outs, bases,
               status, last_play} — from the bot's Kalshi milestone/pbp fetch
               (outs/bases may be None; the model degrades gracefully).
        live_bids:     {team_name: live YES bid cents} (both sides).
        original_bids: {team_name: pre-game YES cents} (optional — enables the
                       market-overreaction situation).
    Returns:
        {action: BUY|SKIP|WAIT, team, side ("home"/"away"), bid, confidence,
         situation, reason, model_wp, implied, edge_c, tp_price, stop_price,
         tp_pct, score, tip, analysis{implied_check, scalp_setup, leverage, risk}}
    """
    home, away = game.get("home"), game.get("away")
    hr, ar = game.get("home_runs"), game.get("away_runs")
    inning = game.get("inning")
    score = (f"{away} {ar if ar is not None else '?'} - "
             f"{hr if hr is not None else '?'} {home} ({_fmt_inning(game)})")
    base = {"action": "WAIT", "ticker": ticker, "score": score}
    if not home or not away:
        return {**base, "reason": "no team names resolved"}
    if hr is None or ar is None or not inning:
        return {**base, "reason": "no live score/inning yet"}
    if int(inning) < MIN_INNING:
        return {**base, "reason": f"inning {inning} < BASEBALL_MIN_INNING={MIN_INNING} "
                                  f"— lines too early/efficient, waiting"}

    wp_home = win_probability(hr, ar, inning, game.get("half"),
                              outs=game.get("outs"), bases=game.get("bases"))
    sides = []                                          # (edge_c, team, is_home, wp, bid)
    for team, is_home, wp in ((home, True, wp_home), (away, False, 1.0 - wp_home)):
        bid = live_bids.get(team)
        if bid is None:
            continue
        sides.append((wp * 100 - bid, team, is_home, wp, int(bid)))
    if not sides:
        return {**base, "action": "SKIP", "reason": "no live bids on either side"}
    edge, team, is_home, wp, bid = max(sides, key=lambda s: s[0])

    out = {**base, "team": team, "side": "home" if is_home else "away", "bid": bid,
           "model_wp": round(wp, 3), "implied": bid, "edge_c": round(edge, 1),
           "tp_pct": SCALP_PCT}
    if edge < MIN_EDGE_C:
        return {**out, "reason": f"best edge {edge:+.1f}c ({team}) < min {MIN_EDGE_C:.0f}c "
                                 f"— market fairly priced, waiting"}
    if not (BID_LO <= bid <= BID_HI):
        return {**out, "reason": f"{team} bid {bid}c outside entry band "
                                 f"{BID_LO}-{BID_HI}c — waiting for a workable price"}
    tp = scalp_tp_cents(bid)
    if tp > MAX_TP_C:
        return {**out, "reason": f"TP {tp}c > {MAX_TP_C}c — no +{SCALP_PCT:.0f}% "
                                 f"headroom left at {bid}c"}

    # ── situation labels ──────────────────────────────────────────────────────
    lead = (hr - ar) if is_home else (ar - hr)
    orig = (original_bids or {}).get(team)
    if (orig is not None and orig >= OVERREACT_FAV_MIN_C
            and bid <= orig - OVERREACT_DROP_C and lead >= -2):
        situation = "OVERREACTION"
        why = (f"pre-game favorite ({orig}c) marked down to {bid}c on a "
               f"{'small deficit' if lead < 0 else 'tie/lead'} — model still "
               f"{wp * 100:.0f}%")
    elif lead > 0 and int(inning) >= 7:
        situation = "LATE-LEAD"
        why = f"leads by {lead} in the {_fmt_inning(game)} and is underpriced"
    elif lead > 0:
        situation = "MID-LEAD"
        why = f"leads by {lead}, market lagging the base-out state"
    elif lead == 0:
        situation = "TIE-EDGE"
        why = ("tied — model edge from base-out state"
               + (" + home bottom-half advantage" if is_home else ""))
    else:
        situation = "TRAIL-VALUE"
        why = f"trails by {abs(lead)} but base-out/inning math says {wp * 100:.0f}%"

    # ── confidence ────────────────────────────────────────────────────────────
    if edge >= ULTRA_EDGE_C and int(inning) >= 6:
        conf = CONF_ULTRA
    elif edge >= MIN_EDGE_C + 3 or int(inning) >= 7:
        conf = CONF_HIGH
    else:
        conf = CONF_MED
    if conf == CONF_MED and int(inning) < 5:
        return {**out, "situation": situation, "confidence": conf,
                "reason": f"{why} | medium confidence before the 5th — waiting"}

    # ── sports4cast gate (user rule 07/12): only buy a team the scraped data
    # gives >= FOURCAST_MIN_PCT to win.  Team absent from the feed (NPB/LMB,
    # or a stale/missing CSV) → fail open unless BASEBALL_4CAST_REQUIRE=TRUE.
    fc_note = ""
    if _4cast_team_pct is not None:
        try:
            fc = _4cast_team_pct(team)
        except Exception:
            fc = None
        if fc is not None and fc < FOURCAST_MIN_PCT:
            return {**out, "situation": situation, "confidence": conf,
                    "reason": (f"{why} | 4cast gate: {team} only {fc:.1f}% "
                               f"(< {FOURCAST_MIN_PCT:.0f}%) in baseball_data.csv "
                               f"— buy blocked")}
        if fc is None and FOURCAST_REQUIRE:
            return {**out, "situation": situation, "confidence": conf,
                    "reason": (f"{why} | 4cast gate: {team} not found in "
                               f"baseball_data.csv (BASEBALL_4CAST_REQUIRE=TRUE) "
                               f"— buy blocked")}
        fc_note = (f"; 4cast {fc:.1f}%" if fc is not None
                   else "; 4cast n/a (fail open)")

    stop = max(1, bid - STOP_LOSS_C)
    reason = (f"{why} | model {wp * 100:.1f}% vs implied {bid}c (edge {edge:+.1f}c)"
              f"{fc_note}; TP {tp}c (+{SCALP_PCT:.0f}%), stop {stop}c")
    team_runs, opp_runs = (hr, ar) if is_home else (ar, hr)
    return {**out, "action": "BUY", "situation": situation, "confidence": conf,
            "reason": reason, "tp_price": tp, "stop_price": stop,
            # entry score context for the score-flip exit (user rule 07/12):
            # lead > 0 seeds "team was ahead" so a later 2-0 -> 2-3 flip exits
            "lead": lead, "score_tuple": (team_runs, opp_runs),
            "tip": f"{team} >> buy at {bid}c, sell at {tp}c ({conf})",
            "analysis": _analysis(game, team, is_home, wp, bid, tp, stop, edge)}


def format_analysis(sig: dict) -> str:
    """Multi-line log block for a BUY signal's structured analysis."""
    a = sig.get("analysis") or {}
    if not a:
        return ""
    return ("    [1] Implied check : " + a.get("implied_check", "") + "\n"
            "    [2] Scalp setup   : " + a.get("scalp_setup", "") + "\n"
            "    [3] Leverage      : " + a.get("leverage", "") + "\n"
            "    [4] Risk/stop     : " + a.get("risk", ""))


# ── demo ──────────────────────────────────────────────────────────────────────
def main() -> None:
    game = {"home": "New York Yankees", "away": "Boston Red Sox",
            "home_runs": 4, "away_runs": 2, "inning": 7, "half": "top",
            "outs": 1, "bases": "1B", "status": "live"}
    live = {"New York Yankees": 71, "Boston Red Sox": 26}
    orig = {"New York Yankees": 58, "Boston Red Sox": 42}
    sig = predict_scalp(game, live, orig, ticker="DEMO")
    print(f"score: {sig.get('score')}")
    print(f"action={sig.get('action')} team={sig.get('team')} bid={sig.get('bid')} "
          f"conf={sig.get('confidence')} situation={sig.get('situation')}")
    print(f"reason: {sig.get('reason')}")
    if sig.get("action") == "BUY":
        print(format_analysis(sig))


if __name__ == "__main__":
    main()
