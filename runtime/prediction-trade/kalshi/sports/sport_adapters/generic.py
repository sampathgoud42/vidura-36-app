#!/usr/bin/env python3
"""
sport_adapters/generic.py — shared adapter base for pipeline (TBD) game sports.
===============================================================================
Team/participant sports that are wired into the engine but whose prediction
model is still a STUB (basketball, cricket, hockey, soccer, golf, …) subclass
``GenericGameAdapter``: it provides a best-effort Kalshi game state (milestone
live_data probe), generic market/side mapping and a generic TP policy, and
calls the sport's model module for the actual signal.  A new sport's adapter
is therefore ~15 lines:

    class HockeyAdapter(GenericGameAdapter):
        name = "hockey"
        MODEL_MODULE = "hockey.prediction_hockey_v1"

Once the model stops being a stub (returns real BUY signals), the sport can
move from MAIN_SPORTS_LIST_TBD to MAIN_SPORTS_LIST with no engine changes —
and the adapter can override any hook (state fetch, TP, exits) as the model
matures, exactly like tennis.py / baseball.py do.
"""
from __future__ import annotations

import importlib
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_SPORTS_DIR = Path(__file__).resolve().parents[3] / "sports"   # prediction-trade/sports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # kalshi/sports
sys.path.insert(0, str(_SPORTS_DIR))
import kalshi_sports as ks                                      # noqa: E402

from .base import SportAdapter, sport_env                       # noqa: E402

_LAST_LOG: dict = {}
_LOG_EVERY_S = int(os.getenv("SPORT_LOG_EVERY_S", "120"))


def _event_of(ticker: str) -> str:
    return ticker.rsplit("-", 1)[0] if ticker.count("-") >= 2 else ticker


def _pick(d: dict, *keys):
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _name_match(a: str, b: str) -> bool:
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    return a.split()[-1] == b.split()[-1]


class GenericGameAdapter(SportAdapter):
    """Adapter base for pipeline sports (stub models).  See module docstring."""
    MODEL_MODULE = ""                       # e.g. "hockey.prediction_hockey_v1"
    MODEL_FUNC = "predict_buy"

    def __init__(self, cfg) -> None:
        super().__init__(cfg)
        self._labels: dict = {}
        self._model = importlib.import_module(self.MODEL_MODULE)
        self._predict = getattr(self._model, self.MODEL_FUNC)

    def describe(self) -> str:
        stub = " model=STUB (never buys)" if getattr(self._model, "IS_STUB", False) else ""
        return super().describe() + stub

    # ── discovery meta ────────────────────────────────────────────────────────
    async def match_meta(self, client, ticker) -> tuple:
        event = _event_of(ticker)
        try:
            d = await client.req("GET", "/milestones",
                                 params={"related_event_ticker": event, "limit": 1})
            ms = d.get("milestones", [])
            if not ms:
                return None, "", None
            m0 = ms[0]
            det = m0.get("details") or {}
            status = str(det.get("status") or "").lower()
            league = det.get("league") or det.get("tournament_name")
            if league:
                self._labels[event] = f"{league}: {m0.get('title', '')}"
            age = start_ts = None
            sd = m0.get("start_date")
            if sd:
                start = datetime.fromisoformat(str(sd).replace("Z", "+00:00"))
                start_ts = start.timestamp()
                age = (datetime.now(timezone.utc) - start).total_seconds() / 3600.0
            return age, status, start_ts
        except Exception:
            return None, "", None

    def label(self, ticker: str) -> str:
        return str(self._labels.get(_event_of(ticker), ""))

    # ── generic game state (best-effort Kalshi milestone live_data probe) ─────
    async def _game_state(self, client, ticker) -> "dict | None":
        """{home, away, home_score, away_score, period, clock, status, title,
        start_date, raw} — whatever Kalshi's milestone live_data exposes for
        this sport.  ``raw`` carries the untouched details dict so a maturing
        model can parse sport-specific fields without an adapter change."""
        event = _event_of(ticker)
        try:
            d = await client.req("GET", "/milestones",
                                 params={"related_event_ticker": event, "limit": 5})
        except Exception:
            return None
        ms = d.get("milestones", [])
        if not ms:
            return None
        m0 = ms[0]
        det = m0.get("details") or {}
        title = m0.get("title", "")
        ld_det: dict = {}
        if m0.get("id"):
            try:
                ld = await client.req("GET", f"/live_data/milestone/{m0['id']}")
                ld_det = ((ld or {}).get("live_data") or {}).get("details") or {}
            except Exception:
                ld_det = {}
        st: dict = {"title": title, "start_date": m0.get("start_date"),
                    "status": str((ld_det.get("status") or det.get("status") or "")).lower(),
                    "home": None, "away": None, "home_score": None,
                    "away_score": None, "period": None, "clock": None,
                    "raw": ld_det or det}
        for src in (ld_det, det):
            if st["home_score"] is None:
                hs = _pick(src, "home_points", "home_score", "competitor1_overall_score")
                if hs is not None:
                    st["home_score"] = hs
            if st["away_score"] is None:
                as_ = _pick(src, "away_points", "away_score", "competitor2_overall_score")
                if as_ is not None:
                    st["away_score"] = as_
            if st["period"] is None:
                st["period"] = _pick(src, "period", "current_period", "inning",
                                     "quarter", "half", "round")
            if st["clock"] is None:
                st["clock"] = _pick(src, "clock", "game_clock", "time", "overs")
        # participants + home/away resolution (Kalshi titles are Away-first)
        participants = list(await self._team_markets(client, ticker))
        pair = None
        for sep in (" at ", " @ ", " vs. ", " vs "):
            if sep in title:
                a, b = title.split(sep, 1)                 # a=away, b=home
                pair = (b, a)
                break
        if pair:
            for nm in participants:
                if _name_match(nm, pair[0]):
                    st["home"] = nm
                elif _name_match(nm, pair[1]):
                    st["away"] = nm
        st["participants"] = participants
        return st

    # ── evaluation ────────────────────────────────────────────────────────────
    async def evaluate(self, client, ticker) -> "dict | None":
        st = await self._game_state(client, ticker)
        if st is None:
            return None
        try:
            live = await ks.get_live_bid_prices(ticker, client=client)
        except Exception:
            live = {}
        sig = self._predict(st, live, {}, ticker=ticker)
        if sig is None:
            return None
        if sig.get("team") and not sig.get("player"):
            sig["player"] = sig["team"]
        now = time.time()
        if sig.get("action") == "BUY" or (now - _LAST_LOG.get(ticker, 0)) >= _LOG_EVERY_S:
            label = self.label(ticker)
            prefix = f"[{label}] " if label else ""
            fmt = "; ".join(f"{n.split()[-1]}:{b}" for n, b in live.items())
            print(f"  {prefix}{sig.get('score', st.get('title', ticker))} "
                  f">>> live:{{{fmt}}} [{sig.get('action')}] {sig.get('reason', '')}")
            _LAST_LOG[ticker] = now
        _bids = [b for b in live.values() if isinstance(b, (int, float))]
        sig["leader_bid"] = max(_bids) if _bids else None
        return sig

    # ── execution policy (generic) ────────────────────────────────────────────
    async def _team_markets(self, client, ticker) -> dict:
        """{name: (market_ticker, "yes")} — one entry per participant that has
        its OWN market.  NEVER BUY NO (user rule 07/12): on a single binary
        market only the YES side's participant is routable; the other side is
        simply not tradeable (no NO buys, ever)."""
        event = _event_of(ticker)
        out: dict = {}
        try:
            ed = await client.req("GET", f"/events/{event}",
                                  params={"with_nested_markets": "true"})
            markets = (ed.get("event", {}) or {}).get("markets") or []
        except Exception:
            return out
        for m in markets:
            nm = m.get("yes_sub_title") or m.get("title", "")
            if nm:
                out[nm] = (m.get("ticker", ""), "yes")
        return out

    async def market_for(self, client, ticker, name: str) -> "tuple | None":
        return (await self._team_markets(client, ticker)).get(name)

    async def claim_tickers(self, client, ticker) -> list:
        tm = await self._team_markets(client, ticker)
        return [mt for mt, _s in tm.values() if mt] or [ticker]

    def tp_for_entry(self, ticker: str, entry_c: int,
                     sig: "dict | None" = None) -> "int | None":
        """Signal's tp_price when the model sets one; else a flat
        +<SPORT>_TARGET_PCT% (default SPORT_TARGET_PCT/20%) over entry."""
        if not entry_c:
            return None
        if sig and sig.get("tp_price"):
            tp = int(sig["tp_price"])
        else:
            pct = float(sport_env(self.name, "TARGET_PCT",
                                  os.getenv("SPORT_TARGET_PCT", "20")))
            tp = round(entry_c * (1 + pct / 100.0))
        return min(99, tp)
