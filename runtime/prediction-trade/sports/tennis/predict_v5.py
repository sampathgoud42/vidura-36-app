#!/usr/bin/env python3
"""
predict_v5.py — Tennis Prediction Model v5: the forensics-derived whitelist.
============================================================================
Built 07/16 from a 12-agent forensic study of ALL 554 bot tennis trades
(Jul 1-15) with ground-truth P&L rebuilt from the Kalshi fills/settlements
API (the trade CSVs had recorded +$6,536 of phantom profit; the TRUE result
was -$1,538.70).  Design was a 3-way blind panel (capital-preservation /
expectancy / robustness mandates) scored by an independent judge on a
time-ordered 60/40 train/holdout replay, then adversarially verified by two
skeptic agents (both CONFIRMED; every number below independently reproduced).

WHY THE OLD MODELS LOST (forensic highlights):
  • Rebuy/averaging-down loops (bot re-armed matches and bought up to 22x the
    planned size into collapsing prices): -$1,126 of the -$1,539.
  • No exit structure: 111 positions rode to $0 (71% of gross losses).
  • Entry friction (+5c taker bump + spread + fees): $958 = 62% of net loss.
  • "Ghost double-break": between sets the FINISHED set looked like the
    current set (games[-1]), so 40% of E signals fired on stale 6-2-style
    scores — buying 1-1 deciders at 68-85c.
  • 60-79c entries: -$1,652 (needs ~75% wr, model delivers a flat ~62%).
  • "ultra high" confidence was anti-calibrated (-$5.03/trade vs high -$2.42)
    and 1.5x-sized exactly the trades where the market disagreed most.

V5 ENTRY POLICY (replay-verified: train +$200.91/64 kept, holdout +$60.63/17
kept @ 30.0% ROI, ALL +$261.54 vs baseline -$1,486 per-unique; contract-scaled
attribution ~11% lower, still solidly positive; holdout positive at 50/50 and
70/30 splits and under every +/-2-3c band-edge perturbation):

  GHOST GUARD  set-boundary state (no current-set games entry yet) → WAIT.
  PRICE GATE   enter ONLY at signal bid 50-62c — NO env override (the 06/28
               68c floor was silently reverted to 40c by env once already).
               Below 50c the market calls our pick the underdog; above 62c
               the fee-inclusive breakeven exceeds the model's flat ~62%.
  F1  bid 50-59c AND situation not in {A, E}      (the proven core band)
  F2  situation == fallback                        (50-62c)
  F3  tour == ITF-M AND hour 06-11 CST             (50-62c)  [PROVISIONAL]
  F4  tour == WTA AND confidence == high, never ultra (50-62c) [PROVISIONAL]
  EXCL  situation Bfav never on ITF-W/ITF-M (no odds/rank data there — the
        bot cannot actually know who the favorite is).        [PROVISIONAL]
  SIZE  flat — size_mult is always 1.0 or 0; confidence NEVER upsizes
        (ultra is downgraded to high on output).

  [PROVISIONAL] rules had <=2 holdout occurrences — they ride on train +
  mechanism evidence.  Signals carry v5_rule tags in the reason so live
  results can re-validate each rule after ~30 occurrences.

The EXIT/SIZING side of v5 lives in the bot (sport_adapters/tennis.py +
bot_kalshi_main.py): one entry per match EVER (persistent ledger), maker-first
entries (no +5c bump, 60s fill window), resting 97c TP always, entry-20c
one-strike stop that the spread guard may never defer, 30c hard floor, flat 20
contracts, and API-reconciled daily (-$60) / weekly (-$150) halt brakes.

predict_v3 stays untouched (standalone v1 bot); v4 remains for reference.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from .predict_v3 import (  # noqa: F401  (re-exported for the bots)
        predict_buy as _v3_predict_buy,
        load_combinations, live_statuses, _md_from_kalshi,
        favorite_comeback_exit, favorite_collapse_exit,
        bought_high_collapse_exit, determine_favorite, is_ultra_favorite,
        CONF_ULTRA, CONF_HIGH, CONF_MED, CONF_LOW)
except ImportError:                    # pragma: no cover  (script-style import)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from predict_v3 import (  # noqa: F401
        predict_buy as _v3_predict_buy,
        load_combinations, live_statuses, _md_from_kalshi,
        favorite_comeback_exit, favorite_collapse_exit,
        bought_high_collapse_exit, determine_favorite, is_ultra_favorite,
        CONF_ULTRA, CONF_HIGH, CONF_MED, CONF_LOW)

_CST = ZoneInfo("America/Chicago")

# ── v5 band: HARD-CODED, no env override (audit finding F2: PREDICT_BID_LO=40
# in the env silently re-opened the 40-67c coin-flip band that the 06/28 study
# had closed; verifier must-fix: never tighten lo above 50 / hi below 60).
BID_LO = 50
BID_HI = 62
R1_HI = 59                      # F1 (generic, non-A/E) ceiling
ITF_TOURS = ("ITF-W", "ITF-M")


def tour_of(ticker: str) -> str:
    """Tour tier from a Kalshi ticker (same mapping the forensics used)."""
    t = (ticker or "").upper()
    if "ITFW" in t or ("ITF" in t and "W" in t.split("-")[0]):
        return "ITF-W"
    if "ITF" in t:
        return "ITF-M"
    if "CHALLENGER" in t:
        return "CHALL"
    if "ATP" in t:
        return "ATP"
    if "WTA" in t:
        return "WTA"
    return "OTHER"


def is_ghost_state(match: dict) -> bool:
    """
    Set-boundary "ghost" detector (audit finding F1): between sets, Kalshi's
    round scores still end at the FINISHED set — games[-1] is 6-2-like and
    _md_from_kalshi mistakes it for the current set, so situation E fires
    "double-break" on stale data (40% of historical E signals; the Wang/Mrva
    loss family).  Real in-set state has one MORE games entry than completed
    sets; anything else is unreliable → WAIT.
    """
    players = match.get("players") or []
    if len(players) < 2:
        return False                     # let v3 return its own WAIT
    completed = sum(int(p.get("sets_won", 0) or 0) for p in players)
    if completed <= 0:
        return False                     # set 1: games list may be empty or [g1]
    glen = max(len(players[0].get("games") or []),
               len(players[1].get("games") or []))
    return glen <= completed             # no current-set entry yet → ghost


def entry_gate(*, situation, confidence, bid, tour, hour_cst) -> tuple:
    """
    The verified v5 whitelist (pure function; mirrors the replay-validated
    policy_final).  Returns (size_mult, rule_tag, why) — mult 0 = do not enter.
    """
    if bid is None or not (BID_LO <= bid <= BID_HI):
        return 0.0, "price-gate", (f"bid {bid}c outside the v5 {BID_LO}-{BID_HI}c "
                                   f"entry band (60-79c lost -$1,652; <50c = market "
                                   f"calls our pick the underdog)")
    sit = (situation or "").strip()
    if sit == "Bfav" and tour in ITF_TOURS:
        return 0.0, "bfav-itf-excl", ("favorite-identity signal on ITF — no "
                                      "odds/rank data, favorite unknowable")
    if bid <= R1_HI and sit not in ("A", "E"):
        return 1.0, "F1", f"core band {BID_LO}-{R1_HI}c, non-A/E situation"
    if sit == "fallback":
        return 1.0, "F2", "fallback situation in band [PROVISIONAL]"
    if tour == "ITF-M" and 6 <= (hour_cst if hour_cst is not None else -1) <= 11:
        return 1.0, "F3", "ITF-M morning (06-11 CST) in band [PROVISIONAL]"
    if tour == "WTA" and confidence == CONF_HIGH:
        return 1.0, "F4", "WTA plain-high in band [PROVISIONAL]"
    return 0.0, "no-rule", (f"in band but no whitelist rule matches "
                            f"(sit={sit or '?'}, tour={tour}, conf={confidence})")


def predict_buy(match: dict, live_bids: dict, original_bids: dict, *,
                combos=None, bid_range: tuple = (BID_LO, BID_HI),
                ticker=None, neutral_favorite: bool = False) -> dict:
    """
    v3's engine → the v5 ghost guard + whitelist.  BUY signals carry
    ``v5_rule`` (F1..F4) for live re-validation of the provisional rules,
    ``size_mult`` (always 1.0 — flat sizing), and never ultra confidence.
    """
    # ── ghost guard: set-boundary state is unreliable — never trade on it ────
    if is_ghost_state(match):
        return {"action": "WAIT", "ticker": ticker,
                "reason": "v5 ghost guard: set just ended, no current-set games "
                          "entry yet — state unreliable (F1 audit), waiting"}

    sig = _v3_predict_buy(match, live_bids, original_bids, combos=combos,
                          bid_range=(BID_LO, BID_HI), ticker=ticker,
                          neutral_favorite=neutral_favorite)
    if not sig or sig.get("action") != "BUY":
        return sig

    bid = sig.get("bid")
    hour = datetime.now(_CST).hour
    mult, rule, why = entry_gate(situation=sig.get("situation"),
                                 confidence=sig.get("confidence"),
                                 bid=bid, tour=tour_of(ticker),
                                 hour_cst=hour)
    if mult <= 0:
        return {**sig, "action": "WAIT",
                "reason": f"{sig.get('reason', '')} | v5 [{rule}]: {why}"}

    # flat sizing: never upsize; ultra is anti-calibrated → downgrade on output
    if sig.get("confidence") == CONF_ULTRA:
        sig["confidence"] = CONF_HIGH
        sig["reason"] = (sig.get("reason", "")
                         + " | v5: ultra downgraded to high (anti-calibrated; "
                           "no size-up)")
    sig["size_mult"] = 1.0
    sig["backing_favorite"] = False          # belt+braces: kills the 1.5x path
    sig["v5_rule"] = rule
    sig["reason"] = f"{sig.get('reason', '')} | v5 [{rule}]: {why}"
    return sig
