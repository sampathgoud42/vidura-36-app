#!/usr/bin/env python3
"""
predict_v6.py — v1 engine + FAVOURITE-ONLY buy policy.
=======================================================
Born 2026-08-05 from the operator's post-mortem: the bot bought a clear
NON-favourite (the Carpico match) and took the full-stake loss that the
favourite-only literature predicts. v6 is the frozen profitable-weekend v1
engine, byte-for-byte, with exactly ONE new rule applied to its output:

    NEVER buy the non-favourite.
    A BUY survives only when the picked player is
      (a) the pre-match favourite (rank/odds), or
      (b) a NEUTRAL match — no pre-match favourite at all, or the two
          players' original odds within PREDICT_V6_NEUTRAL_DIFF cents
          (default 11c, e.g. 55/45 or closer — near-even matches where
          "favourite" is noise), or
      (c) a CONFIRMED live flip — the original underdog has overtaken the
          favourite on LIVE bids AND held that lead while
          PREDICT_V6_FLIP_POINTS more points were played (default 2).
          The first poll that sees the flip starts a per-ticker counter;
          each observed score change counts one point.  Flip back before
          confirmation → counter resets.  No knee-jerk re-labelling of the
          favourite off a single point.
    Anything else is downgraded to WAIT: the watcher keeps polling, and if
    the engine's pick later flips to the favourite the trade can still
    happen — but an unconfirmed underdog is never bought.

Everything else — situations A-F, the micro-state fallback, the bid band,
the confidence gates — is v1 unchanged (including its documented weekend-era
quirks; the gate neutralises the known "parity branch backs the underdog"
path by construction).

Env knobs: everything v1 reads, plus
    PREDICT_V6_NEUTRAL_DIFF   original-odds gap (cents) treated as neutral
                              (default 11)
    PREDICT_V6_FLIP_POINTS    points the ex-underdog must hold the live lead
                              before being accepted as favourite (default 2)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

try:                                       # package import (tennis.predict_v6)
    from . import predict_v1 as _v1
except ImportError:                        # pragma: no cover — script/dev use
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import predict_v1 as _v1

# Re-export EVERYTHING v1 exposes (the sports adapter copies a fixed list of
# attributes — including the underscored _md_from_kalshi — off the selected
# model module; v6 must look exactly like v1 apart from predict_buy).
for _name in dir(_v1):
    if _name.startswith("__"):
        continue
    globals().setdefault(_name, getattr(_v1, _name))
_md_from_kalshi = _v1._md_from_kalshi      # explicit: adapter asks for it

V6_NEUTRAL_DIFF_C = int(os.getenv("PREDICT_V6_NEUTRAL_DIFF", "11"))
V6_FLIP_POINTS = int(os.getenv("PREDICT_V6_FLIP_POINTS", "2"))

# Live-flip hysteresis: ticker -> {"pick", "sig", "pts"}.  Lives for the bot
# process; a handful of watched tickers, so no pruning needed.
_flip_state: dict = {}


def _score_sig(match: dict) -> tuple:
    """Snapshot of the live score — any point played changes this."""
    sig = []
    for p in (match.get("players") or [])[:2]:
        sig.append((p.get("sets_won"), tuple(p.get("games") or []),
                    p.get("current_game")))
    return tuple(sig)


def _flip_confirmed(key, pick: str, match: dict,
                    live_bids: dict, fav_name: str) -> tuple:
    """(confirmed, pts_seen) — has the ex-underdog held the live lead for
    V6_FLIP_POINTS observed points?  Not live-leading resets the counter."""
    lb_pick, lb_fav = live_bids.get(pick), live_bids.get(fav_name)
    if lb_pick is None or lb_fav is None or lb_pick <= lb_fav:
        _flip_state.pop(key, None)         # not (or no longer) live favourite
        return False, None
    sig = _score_sig(match)
    st = _flip_state.get(key)
    if st is None or st["pick"] != pick:
        _flip_state[key] = {"pick": pick, "sig": sig, "pts": 0}
        return False, 0                    # flip just observed — start waiting
    if sig != st["sig"]:
        st["sig"] = sig
        st["pts"] += 1
    return st["pts"] >= V6_FLIP_POINTS, st["pts"]


def _blocked_by_favourite_policy(match: dict, live_bids: dict,
                                 original_bids: dict, out: dict,
                                 ticker) -> Optional[str]:
    """Reason suffix when the BUY must be blocked, else None."""
    md = _v1._md_from_kalshi(match)
    if md is None:
        return None                        # v1 already vetted the data
    fav = md.get("favorite")
    if not fav:
        return None                        # no pre-match favourite -> neutral
    players = match.get("players") or []
    if len(players) < 2:
        return None
    names = (players[0].get("name", ""), players[1].get("name", ""))
    fav_name = names[0] if fav == "A" else names[1]
    pick = out.get("player")
    if not pick or pick == fav_name:
        return None                        # backing the favourite
    ob_fav = original_bids.get(fav_name)
    ob_pick = original_bids.get(pick)
    if (ob_fav is not None and ob_pick is not None
            and abs(ob_fav - ob_pick) <= V6_NEUTRAL_DIFF_C):
        return None                        # coin-flip odds -> neutral match
    key = ticker or names
    confirmed, pts = _flip_confirmed(key, pick, match, live_bids, fav_name)
    if confirmed:
        return None                        # underdog became favourite + held 2 pts
    if pts is not None:
        return (f"{pick} just took the live lead over {fav_name} — waiting "
                f"{pts}/{V6_FLIP_POINTS} points before accepting the flip")
    return (f"{pick} is not the favourite ({fav_name}) — favourite-only "
            f"policy, no underdog buys")


def predict_buy(match: dict, live_bids: dict, original_bids: dict, *,
                combos: Optional[dict] = None,
                bid_range: tuple = (_v1.BID_LO, _v1.BID_HI),
                ticker: Optional[str] = None) -> dict:
    """v1's decision, then the favourite-only gate on any BUY."""
    out = _v1.predict_buy(match, live_bids, original_bids,
                          combos=combos, bid_range=bid_range, ticker=ticker)
    if out.get("action") != "BUY":
        return out
    why = _blocked_by_favourite_policy(match, live_bids, original_bids,
                                       out, ticker)
    if why is None:
        return out
    blocked = {**out, "action": "WAIT"}
    blocked.pop("tip", None)
    blocked["reason"] = (out.get("reason") or "") + " | v6: " + why
    return blocked
