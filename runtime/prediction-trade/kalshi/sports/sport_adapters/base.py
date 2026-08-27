#!/usr/bin/env python3
"""
sport_adapters/base.py — the sport-plugin contract for bot_kalshi_main.py.
==========================================================================
The main bot is a generic engine (discovery → watchers → execution → guardian
→ per-sport bank risk).  Everything SPORT-SPECIFIC lives in one adapter class
per sport:

    class MySportAdapter(SportAdapter):
        name = "mysport"                       # Kalshi series tag, lowercased
        DEFAULTS = {"stop_loss_c": 20}         # per-sport config defaults
        async def evaluate(...): ...           # state + predictor → signal dict

then register it in sport_adapters/__init__.py and add "mysport" to
MAIN_SPORTS_LIST in kaslhi_sports.env.  Nothing in the engine changes.

Per-sport config convention (kaslhi_sports.env; upper- or lower-case accepted):
    <SPORT>_BANK           session bankroll in USD for this sport (0 = unlimited)
    <SPORT>_CONTRACTS      contracts per order (falls back to SPORT_CONTRACTS)
    <SPORT>_STOP_LOSS_PCT  halt THIS sport once its realized session loss
                           exceeds this %% of the bank (banner message; other
                           sports keep trading; open positions stay managed)
    <SPORT>_STOP_LOSS_C    per-position stop (cents under entry; 0 = disabled)
    <SPORT>_POLL_S         in-play re-poll cadence
    <SPORT>_MAX_LIVE_HOURS drop a match/game live longer than this
Prediction-model knobs stay with each model (PREDICT_* for tennis,
BASEBALL_* for baseball, …) — the adapter's module reads them itself.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def sport_env(sport: str, key: str, default=None):
    """Per-sport env lookup: TENNIS_BANK / tennis_bank / tennis_BANK all accepted."""
    for k in (f"{sport.upper()}_{key.upper()}", f"{sport.lower()}_{key.lower()}",
              f"{sport.lower()}_{key.upper()}"):
        v = os.getenv(k)
        if v is not None and str(v).strip() != "":
            return v
    return default


def _fenv(sport, key, default) -> float:
    try:
        return float(sport_env(sport, key, default))
    except (TypeError, ValueError):
        return float(default)


@dataclass
class SportConfig:
    """Resolved per-sport configuration (env + adapter DEFAULTS)."""
    name: str
    bank: float             # <SPORT>_BANK ($; 0 = unlimited)
    contracts: int          # <SPORT>_CONTRACTS
    stop_loss_pct: float    # <SPORT>_STOP_LOSS_PCT (bank drawdown halt; 0 = off)
    stop_loss_c: int        # <SPORT>_STOP_LOSS_C (per-position entry stop; 0 = off)
    poll_s: int             # <SPORT>_POLL_S
    max_live_hours: float   # <SPORT>_MAX_LIVE_HOURS
    ultra_mult: float       # ultra-high-confidence sizing multiplier
    tp_ceiling_c: int       # <SPORT>_TP_CEILING_C (hard profit-lock ceiling; 0 = off)
    sl_floor_c: int         # <SPORT>_SL_FLOOR_C (hard loss floor; 0 = off)
    price_bump_c: int       # <SPORT>_PRICE_BUMP_C (+cents crossed on BUY; 0 = maker)
    fill_timeout_s: int     # <SPORT>_FILL_TIMEOUT_S (cancel unfilled buy after this)
    stop_confirm: int       # <SPORT>_STOP_CONFIRM (breach cycles before an exit fires)
    day_loss_halt_usd: float   # <SPORT>_DAY_LOSS_HALT_USD (API-reconciled; 0 = off)
    week_loss_halt_usd: float  # <SPORT>_WEEK_LOSS_HALT_USD (API-reconciled; 0 = off)

    @classmethod
    def load(cls, name: str, defaults: Optional[dict] = None) -> "SportConfig":
        d = defaults or {}
        return cls(
            name=name,
            bank=_fenv(name, "BANK", d.get("bank", 0)),
            contracts=int(_fenv(name, "CONTRACTS",
                                d.get("contracts", os.getenv("SPORT_CONTRACTS", "1")))),
            stop_loss_pct=_fenv(name, "STOP_LOSS_PCT", d.get("stop_loss_pct", 0)),
            stop_loss_c=int(_fenv(name, "STOP_LOSS_C", d.get("stop_loss_c", 0))),
            poll_s=int(_fenv(name, "POLL_S",
                             d.get("poll_s", os.getenv("SPORT_POLL_S", "30")))),
            max_live_hours=_fenv(name, "MAX_LIVE_HOURS", d.get("max_live_hours", 4)),
            ultra_mult=float(os.getenv("SPORT_ULTRA_FAV_CONTRACTS_MULT", "1.5")),
            # hard price-band exits: per-sport <SPORT>_TP_CEILING_C / _SL_FLOOR_C,
            # falling back to the global SPORT_TP_CEILING_C / SPORT_SL_FLOOR_C.
            tp_ceiling_c=int(_fenv(name, "TP_CEILING_C",
                                   d.get("tp_ceiling_c",
                                         os.getenv("SPORT_TP_CEILING_C", "97")))),
            sl_floor_c=int(_fenv(name, "SL_FLOOR_C",
                                 d.get("sl_floor_c",
                                       os.getenv("SPORT_SL_FLOOR_C", "9")))),
            # execution style (tennis v5: maker-first — bump 0, short fill window)
            price_bump_c=int(_fenv(name, "PRICE_BUMP_C",
                                   d.get("price_bump_c",
                                         os.getenv("SPORT_PRICE_BUMP_C", "5")))),
            fill_timeout_s=int(_fenv(name, "FILL_TIMEOUT_S",
                                     d.get("fill_timeout_s",
                                           os.getenv("SPORT_FILL_TIMEOUT_S",
                                                     str(15 * 60))))),
            stop_confirm=int(_fenv(name, "STOP_CONFIRM",
                                   d.get("stop_confirm",
                                         os.getenv("SPORT_STOP_CONFIRM", "2")))),
            # hard dollar brakes computed from the FILLS/SETTLEMENTS API — never
            # from internal P&L (which recorded $0-settled losers as 0.00)
            day_loss_halt_usd=_fenv(name, "DAY_LOSS_HALT_USD",
                                    d.get("day_loss_halt_usd", 0)),
            week_loss_halt_usd=_fenv(name, "WEEK_LOSS_HALT_USD",
                                     d.get("week_loss_halt_usd", 0)),
        )


class SportBook:
    """
    Per-sport session bankroll + risk gate.

    Tracks realized P&L of this sport's CLOSED trades and the cost of its OPEN
    positions.  Two protections:
      • exposure cap — a new buy must fit inside what is left of the bank
        (bank + realized losses − open cost); bank 0 disables the cap;
      • drawdown halt — once realized loss >= bank * stop_loss_pct/100 the
        sport is HALTED (banner printed once): no new buys for this sport this
        session, while its open positions keep being managed by the guardian.
    """

    def __init__(self, cfg: SportConfig) -> None:
        self.cfg = cfg
        self.realized_pnl = 0.0
        self.open_cost: dict[str, float] = {}       # ticker -> entry cost USD
        self.halted = False

    @property
    def drawdown_usd(self) -> float:
        return max(0.0, -self.realized_pnl)

    def remaining_bank(self) -> Optional[float]:
        """USD still available to buy with (None = unlimited, no bank set)."""
        if self.cfg.bank <= 0:
            return None
        return (self.cfg.bank + min(0.0, self.realized_pnl)
                - sum(self.open_cost.values()))

    def can_buy(self, cost_usd: float) -> tuple[bool, str]:
        if self.halted:
            return False, (f"{self.cfg.name} is BANK-HALTED "
                           f"(lost >= {self.cfg.stop_loss_pct:.0f}% of "
                           f"${self.cfg.bank:.2f} bank) — no new buys")
        rem = self.remaining_bank()
        if rem is not None and cost_usd > rem:
            return False, (f"{self.cfg.name} bank cap: need ${cost_usd:.2f} but only "
                           f"${max(rem, 0):.2f} left of ${self.cfg.bank:.2f} "
                           f"(open ${sum(self.open_cost.values()):.2f}, "
                           f"realized ${self.realized_pnl:+.2f})")
        return True, ""

    def register_open(self, ticker: str, cost_usd: float) -> None:
        self.open_cost[ticker] = cost_usd

    def register_close(self, ticker: str, pnl_usd) -> None:
        self.open_cost.pop(ticker, None)
        if isinstance(pnl_usd, (int, float)):
            self.realized_pnl += pnl_usd
        self._check_drawdown()

    def status_line(self) -> str:
        rem = self.remaining_bank()
        return (f"{self.cfg.name}: realized ${self.realized_pnl:+.2f}"
                + (f", bank left ${rem:.2f}/${self.cfg.bank:.2f}" if rem is not None
                   else ", bank unlimited")
                + (", HALTED" if self.halted else ""))

    def _check_drawdown(self) -> None:
        if self.halted or self.cfg.bank <= 0 or self.cfg.stop_loss_pct <= 0:
            return
        limit = self.cfg.bank * self.cfg.stop_loss_pct / 100.0
        if self.drawdown_usd >= limit:
            self.halted = True
            self._banner()

    def _banner(self) -> None:
        n = self.cfg.name.upper()
        pct = (self.realized_pnl / self.cfg.bank * 100.0) if self.cfg.bank else 0.0
        lines = [
            f"[BANK-HALT]  {n} BETTING STOPPED",
            f"bank ${self.cfg.bank:.2f} | session realized P&L "
            f"${self.realized_pnl:+.2f} ({pct:+.1f}% of bank)",
            f"drawdown limit {n}_STOP_LOSS_PCT={self.cfg.stop_loss_pct:.0f}% reached",
            f"no NEW {self.cfg.name} buys this session — open {self.cfg.name} "
            f"positions remain managed; other sports continue",
        ]
        w = max(len(s) for s in lines) + 6
        print("\n" + "#" * w)
        for s in lines:
            print(f"#  {s.ljust(w - 6)}  #")
        print("#" * w + "\n")


class SportAdapter:
    """
    One live sport plugged into bot_kalshi_main.  Override what the sport needs;
    every hook has a safe default.  The engine guarantees hooks are only called
    for tickers it discovered under this adapter's ``name`` (Kalshi series tag).
    """
    name = "sport"
    DEFAULTS: dict = {}                              # SportConfig.load defaults

    def __init__(self, cfg: SportConfig) -> None:
        self.cfg = cfg

    # ── lifecycle ────────────────────────────────────────────────────────────
    async def startup(self, client) -> None:
        """One-time prep at bot start (e.g. tennis rankings scrape)."""

    def on_refresh(self) -> None:
        """Called on each main watchlist refresh (e.g. reload rankings CSV)."""

    def describe(self) -> str:
        """One config summary line for the startup log."""
        return (f"bank=${self.cfg.bank:.0f} contracts={self.cfg.contracts} "
                f"bank-stop={self.cfg.stop_loss_pct:.0f}% "
                f"pos-stop={self.cfg.stop_loss_c}c poll={self.cfg.poll_s}s")

    # ── discovery ────────────────────────────────────────────────────────────
    def filter_discovered(self, matches: list) -> list:
        """Sport-specific market filter (e.g. baseball drops F5/F3 derivatives)."""
        return matches

    async def confirm_active(self, matches: list, client) -> list:
        """Secondary is-it-really-live check (e.g. tennis SofaScore statuses)."""
        return matches

    async def match_meta(self, client, ticker) -> tuple:
        """(age_hours, kalshi_status, start_ts) for staleness/pending checks."""
        return None, "", None

    def note_match(self, m: dict) -> None:
        """Observe a discovered LiveMatch row (e.g. cache names for scoring)."""

    def label(self, ticker: str) -> str:
        """Human label for logs (tournament / league)."""
        return ""

    # ── evaluation ───────────────────────────────────────────────────────────
    async def evaluate(self, client, ticker) -> "dict | None":
        """Poll one match: fetch state + odds, run the predictor.  Returns the
        signal dict {action: BUY|SKIP|WAIT, player|team, bid, confidence,
        situation, reason, [tp_price, stop_price, not_started, leader_bid]}."""
        raise NotImplementedError

    def context(self, sig: dict) -> str:
        """Short state context for the trade CSV (set #, inning, …)."""
        return ""

    # ── execution policy ─────────────────────────────────────────────────────
    async def market_for(self, client, ticker, name: str) -> "tuple | None":
        """(market_ticker, side) to buy for participant ``name``."""
        return None

    async def claim_tickers(self, client, ticker) -> list:
        """All market tickers of this match to claim for one-trade-per-match."""
        return [ticker]

    def size_contracts(self, sig: dict) -> int:
        """Contracts for this signal (default: flat cfg.contracts)."""
        return self.cfg.contracts

    def tp_for_entry(self, ticker: str, entry_c: int,
                     sig: "dict | None" = None) -> "int | None":
        """TP sell price for an entry at ``entry_c`` — None = place no TP
        (hold to settlement); also used by the guardian to re-place lost TPs."""
        return None

    def on_position_opened(self, ticker: str, sig: dict) -> None:
        """Called after a buy FILLS, with the signal that triggered it — for
        seeding per-position state (e.g. baseball's score-flip 'was leading')."""

    # ── risk (sport-specific early exits, beyond the generic stop-loss) ──────
    async def exit_check(self, client, ticker, entry_c, held_bid_c, side,
                         position) -> tuple:
        """(fire, why, immediate) — e.g. tennis favorite-comeback exit.
        ``immediate`` skips the confirm-strike debounce."""
        return False, "", False
