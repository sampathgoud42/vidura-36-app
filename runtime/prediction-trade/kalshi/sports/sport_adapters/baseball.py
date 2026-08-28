#!/usr/bin/env python3
"""
sport_adapters/baseball.py — baseball plugin for bot_kalshi_main.py.
====================================================================
Thin adapter over ``bot_kalshi_sports_v2`` (Kalshi milestone live_data game
state) and the sabermetric scalp model in
``prediction-trade/sports/baseball/prediction_baseball_v1.py``.

Behavior preserved from v2:
  • full-game *GAME series only (KXMLBF5/F7/F3 first-N-innings derivatives —
    which even carry a "Tie" side — and KXMLBEXTRAS are never traded);
  • BUY needs >= BASEBALL_MIN_EDGE_C model edge in the BASEBALL_BID_LO-HI band;
  • the scalp exit is the strategy: TP sell at +BASEBALL_SCALP_PCT% (10%);
  • ultra-high edge (>= BASEBALL_ULTRA_EDGE_C, inning >= 6) sizes ultra_mult x.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # kalshi/sports
import bot_kalshi_sports_v2 as bv2                              # noqa: E402
from baseball import baseball4cast_scraper as b4c               # noqa: E402
from baseball.prediction_baseball_v1 import FOURCAST_MIN_PCT    # noqa: E402

from .base import SportAdapter                                  # noqa: E402


class BaseballAdapter(SportAdapter):
    name = "baseball"
    DEFAULTS = {
        "stop_loss_c": bv2.BB_STOP_LOSS_C,          # BASEBALL_STOP_LOSS_C (18c)
        "max_live_hours": bv2.SPORT_MAX_LIVE_HOURS,  # BASEBALL_MAX_LIVE_HOURS (6h)
        "poll_s": bv2.BASEBALL_POLL_S,
    }

    async def startup(self, client) -> None:
        """sports4cast gate data (user rule 07/12): scrape baseball_data.csv
        now if stale, then re-scrape every day at 8:15 AM CST."""
        await b4c.ensure_fresh()
        asyncio.create_task(b4c.daily_scrape_task())

    def describe(self) -> str:
        return (super().describe() + f" TP=+{bv2.SCALP_PCT:.0f}% scalp "
                f"4cast-gate>={FOURCAST_MIN_PCT:.0f}%")

    # ── discovery ────────────────────────────────────────────────────────────
    def filter_discovered(self, matches: list) -> list:
        """Full-game winner series only (…GAME) — no F5/F3/extras derivatives."""
        keep = [g for g in matches
                if bv2.ks._series_of(g["ticker"]).upper().endswith("GAME")]
        if len(matches) - len(keep):
            print(f"  [baseball] excluded {len(matches) - len(keep)} derivative "
                  f"market(s) (F5/F3/extras/totals — full-game *GAME series only)")
        return keep

    async def match_meta(self, client, ticker) -> tuple:
        return await bv2._match_meta(client, ticker)   # also caches _GAME_LABEL

    def label(self, ticker: str) -> str:
        return str(bv2._GAME_LABEL.get(bv2._event_of(ticker), ""))

    # ── evaluation ───────────────────────────────────────────────────────────
    async def evaluate(self, client, ticker) -> "dict | None":
        sig = await bv2._eval_one_game(client, ticker)
        if sig and sig.get("team") and not sig.get("player"):
            sig["player"] = sig["team"]                # engine-normalized name key
        return sig

    def context(self, sig: dict) -> str:
        if sig.get("inning"):
            return f"{sig.get('half') or '?'} {sig.get('inning')}"
        return ""

    # ── execution policy ─────────────────────────────────────────────────────
    async def market_for(self, client, ticker, name: str) -> "tuple | None":
        tm = await bv2._team_markets(client, ticker)
        return tm.get(name)                            # (market_ticker, side)

    async def claim_tickers(self, client, ticker) -> list:
        tm = await bv2._team_markets(client, ticker)
        return [mt for mt, _s in tm.values() if mt] or [ticker]

    def size_contracts(self, sig: dict) -> int:
        if sig.get("confidence") == bv2.CONF_ULTRA:    # ultra-high model edge
            return max(1, round(self.cfg.contracts * self.cfg.ultra_mult))
        return self.cfg.contracts

    def tp_for_entry(self, ticker: str, entry_c: int,
                     sig: "dict | None" = None) -> "int | None":
        """Scalp policy: the signal's tp_price (+BASEBALL_SCALP_PCT% over the
        signal bid), else recompute over ``entry_c``; always clamped."""
        if not bv2.BASEBALL_SELL or not entry_c:
            return None
        tp = (int(sig["tp_price"]) if sig and sig.get("tp_price")
              else bv2.scalp_tp_cents(int(entry_c)))
        return min(tp, bv2.SPORT_MAX_TP_C)

    # ── score-flip exit (user rule 07/12) ─────────────────────────────────────
    def on_position_opened(self, ticker: str, sig: dict) -> None:
        """Bought a LEADING team → seed the score-flip exit's 'was ahead' state
        so a later 2-0 → 2-3 flip exits even if no guardian read saw the lead."""
        if (sig or {}).get("lead", 0) > 0:
            bv2._SEEN_LEAD[ticker] = (tuple(sig["score_tuple"])
                                      if sig.get("score_tuple") else True)

    async def exit_check(self, client, ticker, entry_c, held_bid_c, side,
                         position) -> tuple:
        """While holding: bought team led the game and is NOW BEHIND
        (e.g. 2-0 → 2-3) → cancel the resting TP and fire the exit sell.
        Score is durable, so it fires immediately (no strike debounce); the
        engine's spread gate re-runs this check at the stable bid before
        selling, and the sell itself is triple-confirmed."""
        if not bv2.BASEBALL_SCORE_FLIP_EXIT:
            return False, "", False
        fire, why = await bv2.score_flip_check(client, ticker)
        return fire, why, True
