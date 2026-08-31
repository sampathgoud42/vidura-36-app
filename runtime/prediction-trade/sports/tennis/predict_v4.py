#!/usr/bin/env python3
"""
predict_v4.py — Tennis Prediction Model v4 = v3 + trade-history risk rules.
===========================================================================
Thin post-processing wrapper over predict_v3 (which stays byte-identical and
keeps powering the standalone v1 bot).  v4 is what bot_kalshi_main.py runs —
the tennis adapter rebinds v1's model symbols to this module in the MAIN
process only.

WHY (07/13 analysis of 169 unique closed tennis trades, +$2,539 net):
  • Situation E (double-break → back the set leader) produced 10 of 16 losses
    and -$539.79 of loss money at only $10.38/trade expectancy (less than half
    of A/F/F3).  The losers were set leaders who were NOT the pre-match
    favorite, run down by the favorite (Wang -$249, Mrva -$79, …).
  • Situation A losses were rare but catastrophic BECAUSE of the ultra-high
    1.5x size-up firing at mid-band prices where the market disagreed with the
    model: Hardt -$254.61 @62c x150, Balshaw -$83 @72c x112.
  • The 50-69c entry band was the leak: 58 trades at ~68-76% win rate and
    ~$4-14/trade vs 92% at 40-49c and $17-30/trade at 70-89c.

V4 RULES (each env-tunable, applied ONLY to v3 BUY signals):
  1. ULTRA needs price agreement — an ultra-high BUY below
     PREDICT4_ULTRA_MIN_BID (70c) is downgraded to plain high: no 1.5x size-up
     and no band bypass (the band gate is re-applied; out of band → WAIT).
  2. E on a NON-favorite is half-sized — the signal carries
     size_mult=PREDICT4_E_NONFAV_MULT (0.5; set 0 to skip these entirely).
     E backing the favorite (or with no favorite) is untouched.
  3. Mid-band favorite-only — inside PREDICT4_SOFT_LO..PREDICT4_SOFT_HI
     (50-69c) a BUY that backs against a determined favorite is a coin flip:
     WAIT (PREDICT4_MIDBAND_FAV_ONLY=FALSE disables).

Everything else (situations, exits, favorite ladder, finals rule) is v3's.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from .predict_v3 import (  # noqa: F401  (re-exported for the bots)
        predict_buy as _v3_predict_buy,
        load_combinations, live_statuses, _md_from_kalshi,
        favorite_comeback_exit, favorite_collapse_exit,
        bought_high_collapse_exit, determine_favorite, is_ultra_favorite,
        BID_LO, BID_HI, CONF_ULTRA, CONF_HIGH, CONF_MED, CONF_LOW)
except ImportError:                    # pragma: no cover  (script-style import)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from predict_v3 import (  # noqa: F401
        predict_buy as _v3_predict_buy,
        load_combinations, live_statuses, _md_from_kalshi,
        favorite_comeback_exit, favorite_collapse_exit,
        bought_high_collapse_exit, determine_favorite, is_ultra_favorite,
        BID_LO, BID_HI, CONF_ULTRA, CONF_HIGH, CONF_MED, CONF_LOW)

# ── v4 config (kaslhi_sports.env) ─────────────────────────────────────────────
# rule 1: ultra-high (1.5x size + band bypass) only when the market agrees —
# live bid must be at least this. Below → plain high, normal band gate.
ULTRA_MIN_BID = int(os.getenv("PREDICT4_ULTRA_MIN_BID", "70"))
# rule 2: sizing multiplier for E (double-break) signals backing a NON-favorite
# (0.5 = half size; 0 = never trade E against the determined favorite).
E_NONFAV_MULT = float(os.getenv("PREDICT4_E_NONFAV_MULT", "0.5"))
# rule 3: inside this band, only back the determined favorite (or Neutral).
MIDBAND_FAV_ONLY = os.getenv("PREDICT4_MIDBAND_FAV_ONLY",
                             "TRUE").strip().upper() != "FALSE"
SOFT_LO = int(os.getenv("PREDICT4_SOFT_LO", "50"))
SOFT_HI = int(os.getenv("PREDICT4_SOFT_HI", "69"))


def predict_buy(match: dict, live_bids: dict, original_bids: dict, *,
                combos=None, bid_range: tuple = (BID_LO, BID_HI),
                ticker=None, neutral_favorite: bool = False) -> dict:
    """v3's predict_buy, then the v4 risk rules on any BUY (see module doc).
    Adds ``size_mult`` (default 1.0) to BUY signals — the bot multiplies its
    contract count by it (rule 2's half-sizing)."""
    sig = _v3_predict_buy(match, live_bids, original_bids, combos=combos,
                          bid_range=bid_range, ticker=ticker,
                          neutral_favorite=neutral_favorite)
    if not sig or sig.get("action") != "BUY":
        return sig
    bid = sig.get("bid")
    fav = sig.get("favorite")                       # "A" | "B" | None
    side = sig.get("side")
    against_favorite = fav is not None and side is not None and side != fav
    sig.setdefault("size_mult", 1.0)
    if bid is None:
        return sig
    lo, hi = bid_range

    # ── rule 1: ultra needs price agreement (>= ULTRA_MIN_BID) ──────────────
    if sig.get("confidence") == CONF_ULTRA and bid < ULTRA_MIN_BID:
        sig["confidence"] = CONF_HIGH               # no 1.5x, no band bypass
        sig["reason"] = (sig.get("reason", "") +
                         f" | v4: ultra at {bid}c < {ULTRA_MIN_BID}c — market "
                         f"disagrees, downgraded to high (no size-up)")
        if not (lo <= bid <= hi):                   # re-apply the high band gate
            return {**sig, "action": "WAIT",
                    "reason": sig["reason"] + f" | bid outside {lo}-{hi}c band"}

    # ── rule 3: mid-band (50-69c) only backs the favorite ───────────────────
    if MIDBAND_FAV_ONLY and against_favorite and SOFT_LO <= bid <= SOFT_HI:
        return {**sig, "action": "WAIT",
                "reason": (sig.get("reason", "") +
                           f" | v4: {bid}c is the {SOFT_LO}-{SOFT_HI}c coin-flip "
                           f"band and the pick is NOT the favorite — wait")}

    # ── rule 2: E (double-break) against the favorite is half-sized ─────────
    if sig.get("situation") == "E" and against_favorite:
        if E_NONFAV_MULT <= 0:
            return {**sig, "action": "WAIT",
                    "reason": (sig.get("reason", "") +
                               " | v4: E backing a non-favorite disabled "
                               "(PREDICT4_E_NONFAV_MULT=0)")}
        sig["size_mult"] = E_NONFAV_MULT
        sig["reason"] = (sig.get("reason", "") +
                         f" | v4: E vs the favorite — size x{E_NONFAV_MULT:g}")
    return sig
