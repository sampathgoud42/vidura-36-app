#!/usr/bin/env python3
"""
kalshi_sports_bot.py — orchestrates the kalshi_sports helpers.
=============================================================
Reads ``kaslhi_sports.env`` (SPORTS_LIST, MIN_VOLUME_USD, TOP_N_PER_SPORT) and:

  1. For each sport in SPORTS_LIST → filter_by_sport_min_volume_live(sport,
     MIN_VOLUME_USD) → store up to TOP_N_PER_SPORT live high-volume tickers per
     sport, e.g. tennis=[m1..m5], cricket=[m1..m5], …
  2. In parallel, fetch get_the_market_scores_kalshi() for every stored ticker
     and print the FIRST market's response per sport (for entry-logic design).
  3. get_live_bid_prices(ticker) for the top market of each sport — live YES bid
     per participant, e.g. {"Nadal": 49, "Federer": 51}.

Auth/HTTP reuse the v1 ``KalshiClient`` (via kalshi_sports). Read-only — places
no orders.

Run:
    python kalshi_sports_bot.py
"""
from __future__ import annotations

import asyncio
import csv
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import dotenv
from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
_KALSHI_ROOT = _HERE.parent                                    # prediction-trade/kalshi
_PT_ROOT = _KALSHI_ROOT.parent                                 # prediction-trade
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_KALSHI_ROOT))
sys.path.insert(0, str(_KALSHI_ROOT / "btc" / "btc15"))        # kalshi/btc/btc15 → `import bot_kalshi_btc15`
sys.path.insert(0, str(_PT_ROOT / "sports"))                    # prediction-trade/sports → `import tennis`

# bot_kalshi_btc15 (imported below, directly and via kalshi_sports) does
# `from btc import BtcVidyaMonitor`. That package isn't inside prediction-trade —
# it lives at <repo-root>/indicators (renamed from `btc`; the many `from btc
# import ...` call sites across kalshi/btc/** were never updated to match).
# Alias it into sys.modules so the import resolves without duplicating the file
# into prediction-trade.
if "btc" not in sys.modules:
    _REPO_ROOT = _PT_ROOT.parent                                # .../38trades-py-claude
    sys.path.insert(0, str(_REPO_ROOT))
    import indicators as _btc_pkg                                # noqa: E402
    sys.modules["btc"] = _btc_pkg

# ── This bot is fully independent of the project root .env ────────────────────
# 1. Non-secret config (SPORTS_LIST, MIN_VOLUME_USD, SPORT_* knobs, ...), tracked in git.
for _name in ("kaslhi_sports.env", "kalshi_sports.env"):
    _p = _HERE / _name
    if _p.exists():
        load_dotenv(_p)
        break

# 2. Per-customer folder — <project root>\customers\<name>\ — is the ONLY source
#    of Kalshi credentials (KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY, BASE_URI) and
#    the destination for this run's logs/ and trade_history/ (see SPORT_LOG_DIR
#    and SPORT_TRADE_CSV below). Never committed to git; code/imports stay
#    entirely under this repo regardless of which customer folder is selected.
#    Selected by (in order): 1st CLI arg, SPORTS_CUSTOMER env var, else "suma".
#    User rule 07/08: customer data ALWAYS lives in the MAIN checkout,
#    never a .claude/worktrees copy — even when this bot script runs from
#    a worktree. In this project that means <project>/customers/<name>/,
#    and nothing outside the project is ever read. SPORTS_CUSTOMERS_DIR
#    still overrides (the web app passes the exact folder it
#    authenticated).
def _main_checkout_root(p: Path) -> Path:
    parts = p.parts
    for _i, _part in enumerate(parts[:-1]):
        if _part.lower() == ".claude" and parts[_i + 1].lower() == "worktrees":
            return Path(*parts[:_i])
    return p


_PROJECT_ROOT = _main_checkout_root(_HERE.resolve().parents[2])  # 38trades-py-claude
SPORTS_CUSTOMERS_DIR = Path(os.getenv("SPORTS_CUSTOMERS_DIR",
                                      str(_PROJECT_ROOT / "customers")))
SPORTS_CUSTOMER = sys.argv[1] if len(sys.argv) > 1 else os.getenv("SPORTS_CUSTOMER", "suma")
CUSTOMER_DIR = SPORTS_CUSTOMERS_DIR / SPORTS_CUSTOMER

# credentials: an explicit KALSHI_SPORTS_SECRETS path override wins (e.g. the web
# app passes the exact customer .env it already resolved); otherwise <customer
# folder>/.env, falling back to any other *.env found there. override=True so it
# wins even if something upstream already set these.
_secrets_found = False
_secrets_override = os.getenv("KALSHI_SPORTS_SECRETS", "")
_candidates = ([Path(_secrets_override)] if _secrets_override else
              [CUSTOMER_DIR / ".env"] + sorted(CUSTOMER_DIR.glob("*.env")))
for _p in _candidates:
    if _p.exists():
        load_dotenv(_p, override=True)
        _secrets_found = True
        break
if not _secrets_found:
    print(f"[SPORTSBOT] WARNING: no .env found in {CUSTOMER_DIR} — "
          f"KALSHI_API_KEY_ID/KALSHI_PRIVATE_KEY/BASE_URI are unset, auth will fail.")

# KALSHI_PRIVATE_KEY resolution: absolute path used as-is; a bare filename (the
# common case, e.g. "kalshi_private.pem") resolves relative to CUSTOMER_DIR; if
# unset entirely, fall back to any *.pem found in CUSTOMER_DIR.
_pk = os.getenv("KALSHI_PRIVATE_KEY", "").strip()
if _pk and not Path(_pk).is_absolute() and (CUSTOMER_DIR / _pk).exists():
    os.environ["KALSHI_PRIVATE_KEY"] = str(CUSTOMER_DIR / _pk)
elif not _pk:
    _pems = sorted(CUSTOMER_DIR.glob("*.pem"))
    if _pems:
        os.environ["KALSHI_PRIVATE_KEY"] = str(_pems[0])

# 3. Import bot_kalshi_btc15 WITHOUT letting its own bare load_dotenv() (called at that
#    module's import time) touch the project root .env. Neutralize dotenv.load_dotenv
#    only for the duration of this import; bot_kalshi_btc15.py itself is untouched, so
#    the BTC/perp bots still read root .env normally when run on their own.
_real_load_dotenv = dotenv.load_dotenv
dotenv.load_dotenv = lambda *a, **kw: False
try:
    import kalshi_sports as ks                    # noqa: E402  (uses v1 KalshiClient)
    import bot_kalshi_btc15 as v1                 # noqa: E402  (V2 order/position helpers)
finally:
    dotenv.load_dotenv = _real_load_dotenv

# Live tennis scores (ESPN ATP/WTA; ITF via Kalshi milestone live-data) — optional.
try:
    from tennis.tennis_live_score import (  # noqa: E402
        get_match_score, one_liner, load_rankings_csv, rank_for, _name_matches,
        load_rank_tours, tour_for, _rankings_csv_path)
    _HAS_TENNIS_SCORES = True
except Exception as _e:                       # pragma: no cover
    _HAS_TENNIS_SCORES = False
    print(f"[SPORTSBOT] tennis live-score util unavailable: {_e}")

# Match-winner predictor → buy signal (optional). live_statuses confirms active play.
# MODEL SWITCH (user request 07/08): running tennis/predict_v3.py — the frozen
# weekend-stable v1 snapshot PLUS the favorite-comeback exit rule (Ahn/Bernales
# 07/08: we held the non-favorite while the favorite came back and rode the
# trade to -$50; v3 exits even at a loss — see the FAVEXIT guardian pass).
# To go back, change the module below to tennis.predict_v1 (and drop
# favorite_comeback_exit from the import).
try:
    from tennis.predict_v3 import (  # noqa: E402
        predict_buy, load_combinations, live_statuses,
        _md_from_kalshi, favorite_comeback_exit, favorite_collapse_exit,
        bought_high_collapse_exit,
        determine_favorite, BID_LO, BID_HI, CONF_HIGH, CONF_ULTRA)
    _HAS_PREDICT = True
except Exception as _e:                       # pragma: no cover
    _HAS_PREDICT = False
    print(f"[SPORTSBOT] tennis predictor unavailable: {_e}")

KalshiClient = ks.KalshiClient

SPORTS_LIST = [s.strip() for s in
               os.getenv("SPORTS_LIST", "tennis,cricket,basketball,soccer").split(",")
               if s.strip()]
# lower-cased set used to SCOPE order placement (esp. the blanket TP guardian) to
# only the sports configured here — never sell positions in any other category.
_SPORTS_SET = {s.lower() for s in SPORTS_LIST}
MIN_VOLUME_USD = float(os.getenv("MIN_VOLUME_USD", "25000"))      # 0 = all live matches
TOP_N_PER_SPORT = int(os.getenv("TOP_N_PER_SPORT", "100"))    # include them all

# ── order execution on a BUY prediction ──────────────────────────────────────
SPORT_CONTRACTS = int(os.getenv("SPORT_CONTRACTS", "1"))
# Ultra-high conviction on the FAVORITE → size up (user rule 07/09): an
# ultra-high BUY that backs the determined favorite buys this multiple of the
# base contract count (e.g. 100 → 150 at 1.5x). Any other signal (high/medium
# confidence, or ultra-high on a non-favorite) uses SPORT_CONTRACTS as-is.
SPORT_ULTRA_FAV_MULT = float(os.getenv("SPORT_ULTRA_FAV_CONTRACTS_MULT", "1.5"))
# accept the requested SPORT_TRGATE_PCT spelling as well as SPORT_TARGET_PCT
SPORT_TARGET_PCT = float(os.getenv("SPORT_TARGET_PCT",
                                   os.getenv("SPORT_TRGATE_PCT", "20")))
SPORT_FILL_TIMEOUT_S = int(os.getenv("SPORT_FILL_TIMEOUT_S", str(15 * 60)))   # 15 min
SPORT_FILL_POLL_S = int(os.getenv("SPORT_FILL_POLL_S", "60"))   # poll the fill every 60s
SPORT_CLOSE_TIMEOUT_S = int(os.getenv("SPORT_CLOSE_TIMEOUT_S", str(4 * 3600)))
# Not-yet-started matches are parked and re-checked on this cadence (promoted to
# the active watchlist once their start time passes). Keeps the polled set small.
SPORT_PENDING_REFRESH_S = int(os.getenv("SPORT_PENDING_REFRESH_S", "1800"))   # 30 min — promote pending
# Strict full re-discovery of the active (main) watchlist on this cadence.
SPORT_MAIN_REFRESH_S = int(os.getenv("SPORT_MAIN_REFRESH_S", "3600"))         # 60 min — refresh main list
SPORT_PLACE_ORDERS = os.getenv("SPORT_PLACE_ORDERS", "TRUE").strip().upper() != "FALSE"
SPORT_SELL = os.getenv("SPORT_SELL", "TRUE").strip().upper() != "FALSE"  # FALSE = never place TP sells
SPORT_MAX_TP_C = int(os.getenv("SPORT_MAX_TP_C", "98"))  # never place a sell whose TP > this (e.g. 99c)
# Finals TP (user rule 07/12): a position on a match whose tournament label contains
# "final" ALWAYS gets a take-profit sell at +SPORT_FINAL_TP_PCT% over entry, even
# when SPORT_SELL=FALSE. A finals TP above SPORT_MAX_TP_C is clamped to it (an exit
# must always exist), where a normal TP would simply not be placed.
SPORT_FINAL_TP_PCT = float(os.getenv("SPORT_FINAL_TP_PCT", "20"))
SPORT_POLL_S = int(os.getenv("SPORT_POLL_S", "30"))            # re-evaluate for trades every 30s (in-play)
SPORT_NOTSTARTED_POLL_S = int(os.getenv("SPORT_NOTSTARTED_POLL_S", "1800"))  # not-started: re-check every 30 min
SPORT_INSUFFICIENT_PAUSE_S = int(os.getenv("SPORT_INSUFFICIENT_PAUSE_S", "1800"))  # pause buys 30 min on insufficient balance
SPORT_LIST_REFRESH_S = int(os.getenv("SPORT_LIST_REFRESH_S", "300"))  # refresh live list
SPORT_MAX_CONCURRENCY = int(os.getenv("SPORT_MAX_CONCURRENCY", "12"))  # concurrent eval calls
SPORT_DECIDED_BID = int(os.getenv("SPORT_DECIDED_BID", "90"))  # drop match if leader bid > this
SPORT_MAX_LIVE_HOURS = float(os.getenv("SPORT_MAX_LIVE_HOURS", "4"))  # drop if live > this many h
SPORT_CONFIRM_ACTIVE = os.getenv("SPORT_CONFIRM_ACTIVE", "TRUE").strip().upper() != "FALSE"
# SofaScore statuses that mean the match is NOT actively being played → drop.
_DROP_STATUSES = {"interrupted", "suspended", "canceled", "cancelled", "postponed",
                  "delayed", "retired", "finished", "ended", "walkover"}
# Kalshi milestone details.status values that mean NOT active → drop.
_KALSHI_DROP_STATUSES = {"interrupted", "suspended", "cancelled", "canceled",
                         "retired", "abandoned", "walkover", "wov", "postponed"}

# Startup rankings scrape: run tennis/web/sofascore_rankings.py (cwd=tennis/) once
# at bot startup so tennis_rankings.csv is fresh before the favorite/rank-dependent
# situations (A, B, favorite-rebound) start using it.  Fails open on any error/
# timeout — the bot still starts and falls back to whatever CSV is on disk.
SPORT_SCRAPE_RANKINGS = os.getenv("SPORT_SCRAPE_RANKINGS", "TRUE").strip().upper() != "FALSE"
SPORT_SCRAPE_TIMEOUT_S = int(os.getenv("SPORT_SCRAPE_TIMEOUT_S", "240"))  # ATP+WTA (browser) + ITF (api)
# Skip the startup scrape if the rankings CSV was already refreshed within this
# many hours (rankings barely move day-to-day, and the scrape is slow). Elapsed
# wall-clock hours since the file's local mtime; set 0 to always scrape.
SPORT_RANK_MAX_AGE_H = float(os.getenv("SPORT_RANK_MAX_AGE_H", "48"))

SPORT_TP_GUARD_S = int(os.getenv("SPORT_TP_GUARD_S", "120"))   # TP-guardian interval (2 min)
SPORT_GUARD_RECONFIRM_S = int(os.getenv("SPORT_GUARD_RECONFIRM_S", "30"))  # re-confirm a position before placing TP
SPORT_POS_LOG_S = int(os.getenv("SPORT_POS_LOG_S", "1800"))    # open-positions summary log (30 min)
SPORT_LOG_EVERY_S = int(os.getenv("SPORT_LOG_EVERY_S", "120"))  # per-match players-data log throttle (print every 120s)
_LAST_LOG: dict = {}                                            # ticker -> last log timestamp
# Registry of successfully FILLED buy orders → ensures each has a resting TP sell.
#   {ticker: {"contracts": int, "buy_at": cents}}
_FILLED_ORDERS: dict = {}
# Tournament label per event ticker (e.g. "Wimbledon Men Singles - Round of 128"),
# cached from the milestone at discovery and shown in the per-match log line.
_TOURNAMENT: dict = {}
SPORT_POST_ORDER_DELAY_S = int(os.getenv("SPORT_POST_ORDER_DELAY_S", "10"))  # pause after placing
SPORT_PRICE_BUMP_C = int(os.getenv("SPORT_PRICE_BUMP_C", "5"))  # +cents added to BUY price only (not TP)
# ── Stop loss (checked by the TP-guardian every SPORT_TP_GUARD_S) ──
# Exit a held position once its live YES bid has fallen >= SPORT_STOP_LOSS_C cents
# below the entry cost basis — bounds a losing favorite's loss instead of letting
# it ride to $0 at settlement.  Entries are 68-84c (~80% win) with +14-27c TP upside,
# so a 30c stop keeps reward:risk firmly +EV while staying wide enough to ride a
# normal one-set swing.  0 disables the stop.  The exit crosses SPORT_STOP_SLIP_C
# cents through the bid so it actually fills in these thin markets.
SPORT_STOP_LOSS_C = int(os.getenv("SPORT_STOP_LOSS_C", "30"))
SPORT_STOP_SLIP_C = int(os.getenv("SPORT_STOP_SLIP_C", "3"))
# These ITF books are thin and frequently go EMPTY (null bid). A single low read is
# NOT proof of a collapse — it is often an empty book. So require the bid to sit
# below the trigger for SPORT_STOP_CONFIRM consecutive guardian cycles before
# exiting, and ignore reads below SPORT_STOP_MIN_BID_C as "no quote" (don't let an
# empty book dump a winner at ~0c).
SPORT_STOP_CONFIRM = int(os.getenv("SPORT_STOP_CONFIRM", "2"))
SPORT_STOP_MIN_BID_C = int(os.getenv("SPORT_STOP_MIN_BID_C", "4"))
# Deep stop: a drop this far below entry is an unambiguous collapse (entry 68-84 →
# bid <= 23-39c), not a normal one-set swing, so exit IMMEDIATELY (1 cycle) instead
# of waiting for SPORT_STOP_CONFIRM — caps a fast blowout without the ~4-min lag.
SPORT_STOP_DEEP_C = int(os.getenv("SPORT_STOP_DEEP_C", "45"))
_STOP_STRIKES: dict = {}   # ticker -> consecutive cycles seen below the stop trigger
# Absolute price-band exit (user rule 07/10): exit ANY held position whose live
# bid reaches the take-profit ceiling (near-certain win — lock it, free capital)
# or falls to the stop floor (near-certain loss). Independent of entry price.
# The ceiling exits immediately; the floor needs SPORT_STOP_CONFIRM confirming
# cycles (thin books flicker) and a real quote (>= SPORT_STOP_MIN_BID_C). Set 0
# to disable either side. The trade CSV is updated by the close-detection loop.
SPORT_TP_CEILING_C = int(os.getenv("SPORT_TP_CEILING_C", "97"))   # sell when bid >= this
SPORT_SL_FLOOR_C = int(os.getenv("SPORT_SL_FLOOR_C", "9"))        # sell when bid <= this
_BAND_STRIKES: dict = {}   # ticker -> consecutive cycles seen at/under the stop floor
# Reversal-flip: sell a held non-favorite when the favorite gets their own
# double-break, then buy the favorite if in range.  FALSE = never sell early for
# this reason either — only a TP fill or natural settlement closes a position.
SPORT_REVERSAL_FLIP = os.getenv("SPORT_REVERSAL_FLIP", "TRUE").strip().upper() != "FALSE"
# One-and-done per match (user rule 07/12): SPORT_REBUY=FALSE → at most ONE buy per
# match per session. Both player markets are claimed into ``traded`` at buy time and
# the close handler no longer makes the match re-eligible (also gates the
# reversal-flip favorite buy, which would be a second trade on the same match).
SPORT_REBUY = os.getenv("SPORT_REBUY", "TRUE").strip().upper() != "FALSE"
# v3 favorite-comeback exit (user rule 07/08, Ahn/Bernales): while HOLDING the
# non-favorite, exit EVEN AT A LOSS once the favorite's comeback is confirmed
# by tennis.predict_v3.favorite_comeback_exit — their own double-break, their
# bid catching ours, or losing + near-parity.  The score trigger exits
# immediately; the price triggers need SPORT_FAVX_CONFIRM consecutive guardian
# cycles (thin ITF books flicker).  Sell only — no favorite re-buy.
SPORT_FAV_COMEBACK_EXIT = os.getenv("SPORT_FAV_COMEBACK_EXIT", "TRUE").strip().upper() != "FALSE"
SPORT_FAVX_CONFIRM = int(os.getenv("SPORT_FAVX_CONFIRM", "2"))
_FAVX_STRIKES: dict = {}   # ticker -> consecutive guardian cycles with comeback confirmed
# v3 bought-high collapse exit (user rule 07/10): while HOLDING a side bought
# above 76c whose live odds have fallen below 25c, sell/exit — unless the match
# is already in the last 2 points of the deciding set (see
# tennis.predict_v3.bought_high_collapse_exit). Favorite-independent; needs
# SPORT_FAVX_CONFIRM consecutive cycles like the price-based comeback triggers.
SPORT_HIGH_COLLAPSE_EXIT = os.getenv("SPORT_HIGH_COLLAPSE_EXIT", "TRUE").strip().upper() != "FALSE"
# Structured trade history for backtesting (entry context + PV + realized P&L on close).
# Default: <customer folder>/trade_history/trade_history_sports.csv.
SPORT_TRADE_CSV = os.getenv("SPORT_TRADE_CSV",
                            str(CUSTOMER_DIR / "trade_history" / "trade_history_sports.csv"))
# One row per trade: created at BUY, updated IN PLACE (not a second appended row)
# once the position closes.  ts_epoch is the unique key used to find the row again.
_TRADE_CSV_COLS = ["ts_epoch", "ts", "ticker", "player", "situation", "confidence",
                   "reason", "set_num", "signal_bid", "buy_price", "fill_price",
                   "contracts", "tp_price", "pv_entry", "status",
                   "ts_close", "pv_close", "realized_pnl", "pv_delta_pct"]
# STEP 1 discovery band: keep live matches with a bid in [LO, HI]c (ignores MIN_VOLUME_USD)
SPORT_BID_LO = int(os.getenv("SPORT_BID_LO", "25"))
SPORT_BID_HI = int(os.getenv("SPORT_BID_HI", "85"))

# ── portfolio profit-target halt ─────────────────────────────────────────────
# Capture portfolio value (cash + open positions) at start; every SPORT_PV_CHECK_S
# re-check it.  Once PV has grown by TARGET_PORTFOLIO_PCT (e.g. start $100, pct 100
# → target $200) STOP opening new buys, keep managing/draining the positions bought
# this session, and only after they all close halt the bot (+ shutdown when
# HALT_MACHINE_SHUTDOWN).  0 disables.
TARGET_PORTFOLIO_PCT = float(os.getenv("TARGET_PORTFOLIO_PCT", "0"))
HALT_MACHINE_SHUTDOWN = v1.HALT_MACHINE_SHUTDOWN              # shut PC down on halt
SPORT_PV_CHECK_S = int(os.getenv("SPORT_PV_CHECK_S", "1800"))  # cash check interval (30 min)
# BOT-bank loss limit (user rule 07/10 + 07/11): trade only with the allotted
# "bank" (SPORT_LOSS_LIMIT_USD, the user-entered BOT bank). Every session loss
# is drawn down against the bank; once the bank has dropped SPORT_LOSS_LIMIT_PCT
# (default 90%) — i.e. only 10% of it remains — stop opening new buys, drain the
# open positions and halt. 0 bank disables. Checked on the faster
# SPORT_LOSS_CHECK_S cadence (risk management), not the 30-min profit cadence.
SPORT_LOSS_LIMIT_USD = float(os.getenv("SPORT_LOSS_LIMIT_USD", "0"))
SPORT_LOSS_LIMIT_PCT = float(os.getenv("SPORT_LOSS_LIMIT_PCT", "90"))  # stop at this % of bank lost
SPORT_LOSS_CHECK_S = int(os.getenv("SPORT_LOSS_CHECK_S", "300"))   # loss check interval (5 min)
SPORT_DRAIN_POLL_S = int(os.getenv("SPORT_DRAIN_POLL_S", "60"))      # drain re-check interval
SPORT_DRAIN_TIMEOUT_S = int(os.getenv("SPORT_DRAIN_TIMEOUT_S", "3600"))  # max drain wait (60 min); 0 = forever
_TARGET_REACHED = asyncio.Event()                            # set → stop opening new buys
_STOP = asyncio.Event()                                      # set → halt the bot (after drain)
_PAUSE_UNTIL = 0.0                                           # epoch until which new buys are paused (insufficient balance)

# Sports whose Kalshi milestones expose play-by-play via /live_data game_stats.
_GAME_STATS_SPORTS = ("football", "basketball", "soccer", "hockey", "baseball")


def _pbp_summary(pbp: dict | None) -> dict | None:
    """Condense play-by-play into a current-score snapshot (sport-agnostic).

    Scans periods forward keeping the latest non-null scores/play, so an empty
    trailing period (a not-yet-played inning/quarter) doesn't blank the score.
    """
    if not pbp:
        return None
    periods = pbp.get("periods") or []
    if not periods:
        return None
    home = away = None
    last_play = None
    for p in periods:
        if p.get("home_score") is not None:
            home = p.get("home_score")
        if p.get("away_score") is not None:
            away = p.get("away_score")
        for ev in (p.get("events") or []):
            if ev.get("home_points") is not None:
                home = ev.get("home_points")
            if ev.get("away_points") is not None:
                away = ev.get("away_points")
            if ev.get("description"):
                last_play = ev.get("description")
    return {"home": home, "away": away,
            "periods": len(periods), "last_play": last_play}


async def get_game_stats(ticker: str, sport: str, *,
                         client: "KalshiClient | None" = None) -> dict:
    """
    Fetch Kalshi LIVE play-by-play game stats for a market/event ``ticker``.

    Resolves the chain (Kalshi has no ticker→stats endpoint directly):
        ticker → event_ticker
               → milestone   GET /milestones?related_event_ticker={event}
               → game stats  GET /live_data/milestone/{milestone_id}/game_stats

    ``game_stats`` exposes play-by-play only for *game* sports (Pro/College
    Football, Pro/College/WNBA Basketball, Soccer, Pro Hockey, Pro Baseball).
    For other sports (e.g. Tennis) the milestone exists but ``pbp`` is null —
    this returns ``supported=False`` with the milestone metadata instead.

    Args:
        ticker: market or event ticker, e.g. "KXATPMATCH-26JUN21HANVAL-HAN".
        sport:  sport label from step 2, e.g. "Tennis".
    Returns:
        dict: {ticker, sport, event_ticker, milestone_id, milestone_type, league,
               status, title, supported, score, pbp, note}.

    >>> await get_game_stats("KXATPMATCH-26JUN21HANVAL-HAN", "Tennis")
    """
    own = client is None
    c = client or KalshiClient()
    try:
        # 1) event ticker: strip the YES/NO outcome segment (…-HANVAL-HAN → …-HANVAL)
        event_ticker = ticker.rsplit("-", 1)[0] if ticker.count("-") >= 2 else ticker

        async def _find_milestone(ev: str) -> dict | None:
            d = await c.req("GET", "/milestones",
                            params={"related_event_ticker": ev, "limit": 10})
            ms = d.get("milestones", [])
            return ms[0] if ms else None

        ms = await _find_milestone(event_ticker)
        if ms is None:                                  # fallback: authoritative event_ticker
            try:
                md = await c.req("GET", f"/markets/{ticker}")
                ev2 = (md.get("market", {}) or {}).get("event_ticker", "")
                if ev2 and ev2 != event_ticker:
                    event_ticker = ev2
                    ms = await _find_milestone(ev2)
            except Exception:
                pass

        if ms is None:
            return {"ticker": ticker, "sport": sport, "event_ticker": event_ticker,
                    "milestone_id": None, "milestone_type": None, "league": None,
                    "status": None, "title": None, "supported": False,
                    "score": None, "pbp": None,
                    "note": "no milestone linked to this event"}

        mid = ms.get("id")
        details = ms.get("details") or {}

        # 2) play-by-play game stats (uniform pbp shape; null for non-game sports)
        pbp = None
        try:
            gs = await c.req("GET", f"/live_data/milestone/{mid}/game_stats")
            pbp = gs.get("pbp") if isinstance(gs, dict) else None
        except Exception:
            pbp = None

        return {
            "ticker": ticker,
            "sport": sport,
            "event_ticker": event_ticker,
            "milestone_id": mid,
            "milestone_type": ms.get("type", ""),
            "league": details.get("league"),
            "status": details.get("status"),
            "title": ms.get("title"),
            "supported": pbp is not None,
            "score": _pbp_summary(pbp),
            "pbp": pbp,
            "note": ("live play-by-play available" if pbp else
                     "Kalshi game_stats has no play-by-play for this sport/milestone "
                     "(supported: football/basketball/soccer/hockey/baseball)."),
        }
    finally:
        if own:
            await c.close()


# ── live tennis score via Kalshi milestone live-data (ATP/WTA/ITF, no key) ────
def _tour_from_ticker(ticker: str) -> str:
    s = (ticker or "").upper()
    if "ITF" in s:
        return "ITF"
    if "CHALLENGER" in s:
        return "Challenger"
    if "ATP" in s:
        return "ATP"
    if "WTA" in s:
        return "WTA"
    return "Tennis"


def _kalshi_tennis_matchscore(det: dict, name_map: dict, title: str,
                              tour: str, round_label: str) -> "dict | None":
    """Build a MatchScore-shaped dict from /live_data/milestone tennis details.

    MOVED. The implementation now lives in
    ``app.domains.botstation.parley.tennis``, which is importable on its own
    -- this module is not, because it reaches for ``bot_kalshi_btc15``, which
    was never vendored into this project. Parley v2 needed the same reader,
    and two copies of it would have drifted the first time either was fixed.

    This shim keeps the local signature so the rest of this file is unchanged,
    and adds back the two fields the shared version does not carry because
    only this bot uses them: ``league`` and ``round``.
    """
    import sys as _sys
    from pathlib import Path as _Path

    _root = _Path(__file__).resolve().parents[4]
    if str(_root / "backend") not in _sys.path:
        _sys.path.insert(0, str(_root / "backend"))
    from app.domains.botstation.parley.tennis import _match_score

    score = _match_score(det, name_map, title)
    if score is None:
        return None
    score.update({"league": tour, "round": round_label,
                  "status_detail": round_label, "summary": ""})
    # tiebreaks was always empty here; kept so callers indexing it still work.
    for player in score.get("players", []):
        player.setdefault("tiebreaks", [])
    return score


# Kalshi has no surface field, so derive it from the tournament name. Good
# coverage for ATP/WTA + any name carrying an explicit surface word; unknown
# (most ITF) → "" (surface omitted from the label).
_SURFACE_MAP = {
    "Grass": ("wimbledon", "halle", "terra wortmann", "queen", "cinch",
              "hertogenbosch", "libema", "rosmalen", "boss open", "stuttgart open",
              "eastbourne", "devonshire", "mallorca", "bad homburg", "berlin",
              "nottingham", "rothesay", "birmingham", "surbiton", "ilkley",
              "newport", "hall of fame"),
    "Clay": ("roland garros", "french open", "monte", "madrid", "mutua", "rome",
             "italian open", "internazionali", "barcelona", "godo", "hamburg",
             "gstaad", "bastad", "kitzbuhel", "kitzbühel", "umag", "geneva",
             "lyon", "munich", "bmw open", "estoril", "houston", "bucharest",
             "cordoba", "buenos aires", "rio open", "santiago", "sao paulo"),
    "Hard": ("australian open", "us open", "indian wells", "miami open",
             "cincinnati", "national bank", "toronto", "montreal", "dubai",
             "doha", "qatar", "acapulco", "los cabos", "atlanta", "washington",
             "citi open", "winston-salem", "chengdu", "zhuhai", "beijing",
             "china open", "japan open", "shanghai", "auckland", "adelaide",
             "brisbane", "united cup", "hong kong", "dallas", "delray beach"),
    "Indoor": ("paris masters", "rolex paris", "vienna", "erste bank", "basel",
               "swiss indoors", "metz", "moselle", "antwerp", "european open",
               "stockholm", "sofia", "marseille", "open 13", "rotterdam",
               "abn amro", "montpellier", "atp finals", "nitto"),
}


def _court_surface(tour: "str | None", tournament_name: "str | None") -> str:
    """Best-effort court surface from the tournament name ('' if unknown)."""
    n = (tournament_name or "").lower()
    for s in ("indoor", "grass", "clay", "hard"):       # explicit in the name
        if s in n:
            return s.capitalize()
    for surface, kws in _SURFACE_MAP.items():
        if any(k in n for k in kws):
            return surface
    return ""


async def get_kalshi_tennis_score(client: KalshiClient, ticker: str) -> "dict | None":
    """
    Live tennis score from Kalshi's own milestone live-data endpoints:
        GET /milestones?related_event_ticker={event}     → milestone id
        GET /live_data/milestone/{id}                     → set/game/point detail
    Resolves competitor UUIDs to names via the event markets'
    ``custom_strike.tennis_competitor`` → ``yes_sub_title``.  Covers ATP/WTA/ITF
    with no external key.  Returns a MatchScore-shaped dict, or None if there's
    no tennis milestone / live data for the event.
    """
    event = ticker.rsplit("-", 1)[0] if ticker.count("-") >= 2 else ticker
    try:
        d = await client.req("GET", "/milestones",
                             params={"related_event_ticker": event, "limit": 5})
    except Exception:
        return None
    ms = d.get("milestones", [])
    if not ms or not str(ms[0].get("type", "")).startswith("tennis"):
        return None
    m0 = ms[0]
    try:
        ld = await client.req("GET", f"/live_data/milestone/{m0['id']}")
    except Exception:
        return None
    det = ((ld or {}).get("live_data") or {}).get("details") or {}
    if not det:
        return None
    name_map: dict[str, str] = {}
    try:
        ed = await client.req("GET", f"/events/{event}",
                             params={"with_nested_markets": "true"})
        for mk in (ed.get("event", {}).get("markets") or []):
            cid = (mk.get("custom_strike") or {}).get("tennis_competitor")
            if cid:
                name_map[cid] = mk.get("yes_sub_title") or mk.get("title", "")
    except Exception:
        pass
    md = m0.get("details") or {}
    round_label = md.get("round", "")
    score = _kalshi_tennis_matchscore(det, name_map, m0.get("title", ""),
                                      _tour_from_ticker(ticker), round_label)
    if score is not None:
        score["match_start"] = m0.get("start_date")     # for pre-match odds lookup
        score["surface"] = _court_surface(md.get("tour"), md.get("tournament_name"))
    return score


async def get_player_odds(client: KalshiClient, ticker: str,
                          match_start: "str | None" = None) -> "tuple[dict, dict]":
    """
    (live, original) YES-price (cents) per player for the event of ``ticker``:
      • live     — each sibling market's current ``yes_bid_dollars``
      • original — pre-match odds: the hourly candle CLOSE just before the match
                   ``match_start`` (the consolidated price before play began).
                   Falls back to the first candle's open, then the live bid.
    Returns ({name: live_cents}, {name: original_cents}).
    """
    event = ticker.rsplit("-", 1)[0] if ticker.count("-") >= 2 else ticker
    start_ts = None
    if match_start:
        try:
            start_ts = int(datetime.fromisoformat(
                str(match_start).replace("Z", "+00:00")).timestamp())
        except Exception:
            start_ts = None

    live: dict[str, "int | None"] = {}
    original: dict[str, "int | None"] = {}
    try:
        ed = await client.req("GET", f"/events/{event}",
                             params={"with_nested_markets": "true"})
        markets = (ed.get("event", {}) or {}).get("markets") or []
    except Exception:
        return live, original
    now = int(time.time())
    for mk in markets:
        mt = mk.get("ticker", "")
        name = mk.get("yes_sub_title") or mk.get("title", "")
        if not name:
            continue
        live[name] = ks._cents(mk.get("yes_bid_dollars"))
        series = mt.split("-", 1)[0]
        op = None
        try:
            d = await client.req(
                "GET", f"/series/{series}/markets/{mt}/candlesticks",
                params={"start_ts": now - 14 * 86400, "end_ts": now,
                        "period_interval": 60})
            cs = d.get("candlesticks") or []
            if cs:
                before = ([k for k in cs if k.get("end_period_ts", 0) <= start_ts]
                          if start_ts else [])
                cand = before[-1] if before else cs[0]
                pr = cand.get("price") or {}
                op = pr.get("close_dollars") if before else pr.get("open_dollars")
        except Exception:
            pass
        # bug fix 07/06: a market with no candle history (thin/late-created,
        # common for lower-tier players) used to fall back to the LIVE price,
        # making "original" silently track live every poll — this faked a
        # "close pre-match odds" read for F3 and corrupted favorite-vs-odds
        # comparisons (e.g. Schepper, Vinciguerra, Grabher).  None = genuinely
        # unknown; every downstream consumer already guards for None.
        original[name] = ks._cents(op) if op not in (None, "") else None
    return live, original


def _odds_drift_note(original: dict, live: dict) -> str:
    """Flag when the original favorite is now the live underdog (odds flipped)."""
    rows = [(n, original.get(n), live.get(n)) for n in original]
    rows = [(n, o, l) for n, o, l in rows if o is not None and l is not None]
    if len(rows) < 2:
        return ""
    fav = max(rows, key=lambda x: x[1])                 # original favorite
    opp = max((r for r in rows if r[0] != fav[0]), key=lambda x: x[2])
    if fav[2] < opp[2]:                                  # favorite now trailing live
        return f" {fav[0].split()[-1]} is not playing with original odds"
    return ""


async def _player_markets(client: KalshiClient, ticker: str) -> dict:
    """{player_name: market_ticker} for the event of ``ticker`` (one market/player)."""
    event = ticker.rsplit("-", 1)[0] if ticker.count("-") >= 2 else ticker
    out: dict[str, str] = {}
    try:
        ed = await client.req("GET", f"/events/{event}",
                             params={"with_nested_markets": "true"})
        for mk in (ed.get("event", {}) or {}).get("markets") or []:
            nm = mk.get("yes_sub_title") or mk.get("title", "")
            if nm:
                out[nm] = mk.get("ticker", "")
    except Exception:
        pass
    return out


async def _await_sport_fill(client, ticker, want, timeout_s) -> bool:
    """Poll positions until contracts >= want (i.e. == SPORT_CONTRACTS) or timeout."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        pos = await v1.position_for(client, ticker)
        have = pos["contracts"] if pos else 0
        print(f"    [FILL] {ticker} contracts {have}/{want}")
        if have >= want:
            return True
        await asyncio.sleep(SPORT_FILL_POLL_S)
    return False


async def _await_sport_close(client, ticker, timeout_s) -> bool:
    """Poll positions until the position is flat (contracts == 0) or timeout."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        pos = await v1.position_for(client, ticker)
        have = pos["contracts"] if pos else 0
        if have == 0:
            return True
        print(f"    [CLOSE] {ticker} still holding {have} …")
        await asyncio.sleep(15)
    return False


def _event_of(ticker: str) -> str:
    """Event ticker shared by both sides of a match (strip the side suffix)."""
    return ticker.rsplit("-", 1)[0] if ticker.count("-") >= 2 else ticker


def _is_final_round(ticker: str) -> bool:
    """User rule 07/12: any match whose tournament label contains "final"
    (e.g. "ATP Umag Qualification Final" — substring, so Semifinal/Quarterfinal
    match too) ignores the favourite ladder entirely: the favourite is forced
    Neutral in signals and the favorite-based exits are skipped. Tournament not
    yet cached → False (fail open to normal behavior)."""
    return "final" in str(_TOURNAMENT.get(_event_of(ticker), "")).lower()


async def _match_exposure(client, market_ticker: str) -> tuple:
    """
    Exposure across BOTH sides of a match.  The player-A and player-B markets
    share an event ticker, so this sums open contracts and resting orders over
    every market in that event — letting callers refuse a second position on a
    match already held / ordered, regardless of side (A vs B).
    Returns (open_contracts, resting_order_count).
    """
    event = _event_of(market_ticker)
    pos_contracts = 0
    pd = await client.req("GET", "/portfolio/positions", params={"limit": 1000})
    for p in pd.get("market_positions", []):
        if _event_of(p.get("ticker", "")) == event:
            pos_contracts += abs(int(float(p.get("position_fp", "0"))))
    rest = await v1.resting_orders(client)            # all resting orders
    rest_n = sum(1 for o in rest if _event_of(o.get("ticker", "")) == event)
    return pos_contracts, rest_n


async def execute_sport_trade(client, market_ticker: str, player: str,
                              buy_cents: int, *, contracts: int = SPORT_CONTRACTS,
                              situation: str = "", confidence: str = "",
                              reason: str = "", set_num: "int | str" = "") -> None:
    """
    BUY YES on ``market_ticker`` at ``buy_cents`` for ``contracts``, wait up to
    15 min for the fill (confirmed via positions == SPORT_CONTRACTS), then place
    a TP sell at +SPORT_TARGET_PCT% and wait for the position to close.

    Never stacks: if the market already has an open position OR a resting order,
    the order is skipped (only places when positions == 0 AND resting == 0).
    Pauses SPORT_POST_ORDER_DELAY_S after placing.
    """
    global _PAUSE_UNTIL
    # guard: profit target reached → do not open any new buys
    if _TARGET_REACHED.is_set():
        print(f"  [TRADE] {market_ticker}: profit target reached — not opening new buys")
        return
    # guard: paused after an insufficient-balance error → skip until the pause lifts
    if time.time() < _PAUSE_UNTIL:
        return
    # guard: never hold more than one position per MATCH — both player markets
    # (side A and side B) share an event ticker, so check the whole event.
    try:
        pos_n, rest_n = await _match_exposure(client, market_ticker)
    except Exception as e:
        print(f"  [TRADE] {market_ticker}: position/order check failed ({e}); skip")
        return
    if pos_n > 0 or rest_n > 0:
        print(f"  [TRADE] {market_ticker}: match already has position={pos_n}, "
              f"resting={rest_n} (either side) — skip until flat")
        return

    # bump the BUY price by SPORT_PRICE_BUMP_C cents to improve fill; the TP sell is
    # a clean +SPORT_TARGET_PCT% over the signal (no bump on the TP) — finals use
    # +SPORT_FINAL_TP_PCT% instead (user rule 07/12).
    buy_px = min(99, buy_cents + SPORT_PRICE_BUMP_C)
    is_final = _is_final_round(market_ticker)
    tp_pct = SPORT_FINAL_TP_PCT if is_final else SPORT_TARGET_PCT
    tp = min(99, round(buy_cents * (1 + tp_pct / 100.0)))
    print(f"  [TRADE] BUY {player} YES x{contracts} @ {buy_px}c "
          f"(signal {buy_cents}c +{SPORT_PRICE_BUMP_C}) on {market_ticker} (TP {tp}c)")
    r = await v1.place_buy(client, market_ticker, "yes",
                           buy_at_cents=buy_px, contracts=contracts)
    if r is None:
        # distinguish an insufficient-balance failure → pause new buys for 30 min
        need = contracts * buy_px / 100.0
        try:
            cash = await v1.portfolio_balance(client)
        except Exception:
            cash = None
        if cash is not None and cash < need:
            _PAUSE_UNTIL = time.time() + SPORT_INSUFFICIENT_PAUSE_S
            print(f"  [TRADE] insufficient balance (cash ${cash:.2f} < need ${need:.2f}) — "
                  f"pausing new buys for {SPORT_INSUFFICIENT_PAUSE_S // 60} min, then retry")
        else:
            print(f"  [TRADE] buy order failed for {market_ticker}")
        return

    if v1.DRY_RUN:
        print(f"  [DRY][TRADE] order placed; would wait {SPORT_POST_ORDER_DELAY_S}s, "
              f"confirm {contracts} filled, place TP @ {tp}c, then wait for close.")
        return

    # delay after placing the order, before checking the fill
    print(f"  [TRADE] order placed — waiting {SPORT_POST_ORDER_DELAY_S}s …")
    await asyncio.sleep(SPORT_POST_ORDER_DELAY_S)

    # 1) wait for fill, double-confirmed via positions
    if not await _await_sport_fill(client, market_ticker, contracts, SPORT_FILL_TIMEOUT_S):
        print(f"  [TRADE] not filled in {SPORT_FILL_TIMEOUT_S}s — cancelling this order")
        try:                                  # cancel only THIS market's resting order(s)
            for o in await v1.resting_orders(client, market_ticker):
                await client.req("DELETE", f"/portfolio/events/orders/{o['order_id']}")
        except Exception as e:
            print(f"  [TRADE] cancel failed: {e}")
        return
    print(f"  [TRADE] filled {contracts} contracts on {market_ticker}")

    # entry context for backtesting: fill price + portfolio value at entry
    try:
        fill_price = round(float(r.get("average_fill_price")) * 100) if r.get("average_fill_price") else ""
    except Exception:
        fill_price = ""
    try:
        pv_entry = round(await _portfolio_value(client), 2)
    except Exception:
        pv_entry = ""
    # register the filled order so the TP-guardian maintains a resting sell on it
    open_ts = time.time()          # shared key: also written as ts_epoch below, so
                                    # the close can find and update this exact row
    _FILLED_ORDERS[market_ticker] = {"contracts": contracts, "buy_at": buy_px, "tp": tp,
                                     "situation": situation, "confidence": confidence,
                                     "signal_bid": buy_cents, "pv_entry": pv_entry,
                                     "reason": reason, "set_num": set_num,
                                     "open_ts": open_ts}
    _trade_log({"ts_epoch": open_ts, "ts": _now_cst(), "ticker": market_ticker, "player": player,
                "situation": situation, "confidence": confidence, "signal_bid": buy_cents,
                "buy_price": buy_px, "fill_price": fill_price, "contracts": contracts,
                "tp_price": tp, "pv_entry": pv_entry, "reason": reason, "set_num": set_num,
                "status": "OPEN"})

    # 2) place the TP sell at +SPORT_TARGET_PCT% (gated by SPORT_SELL and SPORT_MAX_TP_C).
    # Finals (user rule 07/12): the +SPORT_FINAL_TP_PCT% TP is ALWAYS placed,
    # irrespective of SPORT_SELL; a too-high finals TP is clamped to SPORT_MAX_TP_C.
    if not SPORT_SELL and not is_final:
        print(f"  [TRADE] SPORT_SELL=FALSE — holding {contracts} on {market_ticker} (no TP sell)")
    elif tp > SPORT_MAX_TP_C and not is_final:
        print(f"  [TRADE] TP {tp}c > {SPORT_MAX_TP_C}c — no TP sell placed, holding {market_ticker}")
    else:
        if tp > SPORT_MAX_TP_C:
            print(f"  [TRADE] finals TP {tp}c > {SPORT_MAX_TP_C}c — clamped to {SPORT_MAX_TP_C}c")
            tp = SPORT_MAX_TP_C
            _FILLED_ORDERS[market_ticker]["tp"] = tp
        await v1.place_tp_sell(client, market_ticker, "yes", contracts, tp)
        print(f"  [TRADE] TP sell @ {tp}c placed"
              + (f" (finals +{SPORT_FINAL_TP_PCT:.0f}%)" if is_final else "")
              + "; tp-guardian will keep it resting.")


async def _portfolio_value(client) -> float:
    """Total portfolio value in USD = cash balance + open-position value.  Kalshi's
    /portfolio/balance returns both ``balance`` and ``portfolio_value`` (cents)."""
    d = await client.req("GET", "/portfolio/balance")
    return (float(d.get("balance", 0)) + float(d.get("portfolio_value", 0))) / 100.0


def _trade_log(row: dict) -> None:
    """Append one row to the sports trade-history CSV (backtest dataset) — used
    only for the initial BUY; the position's close UPDATES this same row (see
    _trade_log_close), it does not append a second row."""
    try:
        path = Path(SPORT_TRADE_CSV)
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_TRADE_CSV_COLS, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow({c: row.get(c, "") for c in _TRADE_CSV_COLS})
    except Exception as e:
        print(f"  [TRADECSV] write failed: {e}", file=sys.stderr)


def _trade_log_close(ticker: str, ts_epoch, updates: dict) -> None:
    """
    Update the SAME row created at BUY (matched by ticker + ts_epoch, the exact
    key recorded at open) with the close/P&L fields, instead of appending a new
    row.  Rewrites the CSV atomically (temp file + os.replace) so a crash
    mid-write can't corrupt the file.  Falls back to appending a fresh row if
    the original OPEN row can't be found (e.g. log predates this schema).
    """
    path = Path(SPORT_TRADE_CSV)
    if not path.exists():
        return
    try:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception as e:
        print(f"  [TRADECSV] close read failed: {e}", file=sys.stderr)
        return
    target_key = str(ts_epoch)
    found = False
    for r in rows:
        if r.get("ticker") == ticker and r.get("ts_epoch") == target_key and r.get("status") == "OPEN":
            r.update({k: str(v) if v != "" else "" for k, v in updates.items()})
            r["status"] = "CLOSED"
            found = True
            break
    if not found:                          # OPEN row missing (older log) — append instead
        row = {"ticker": ticker, "ts_epoch": target_key, "status": "CLOSED"}
        row.update(updates)
        rows.append({c: row.get(c, "") for c in _TRADE_CSV_COLS})
    tmp = path.with_suffix(".tmp")
    try:
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_TRADE_CSV_COLS, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in _TRADE_CSV_COLS})
        os.replace(tmp, path)
    except Exception as e:
        print(f"  [TRADECSV] close write failed: {e}", file=sys.stderr)


async def _pnl_from_fills(client, ticker: str, since_ts: float = 0.0) -> float:
    """Best-effort realized P&L (USD) for a ticker from fills SINCE ``since_ts``
    (this trade's open epoch) — net cash flow (sell cash in − buy cash out − fees).
    Filtering by since_ts avoids summing prior trades on a re-entered ticker.
    Caveat: a position held to a winning settlement (not sold) has no sell fill, so
    it shows as a buy-only loss; TP-sell and settlement-loss exits are correct.

    bug fix 07/06: previously picked yes_price_dollars vs no_price_dollars based on
    the FILL's own reported ``side`` field — but that reflects order-matching
    mechanics (which side of the book we matched against), not which token our
    position holds.  A stop-loss/TP sell closing a held YES position can come back
    with side='no' (e.g. the Delaney trade: side='no', no_price_dollars=0.96, but
    we were selling YES @ yes_price_dollars=0.04 — the old code used 0.96, turning
    a ~-$20 loss into a fake +$47.87 "win").  This bot (execute_sport_trade) only
    ever calls place_buy(..., "yes", ...) — it NEVER holds a NO position — so
    yes_price_dollars is always the correct price for both entry and exit fills."""
    try:
        d = await client.req("GET", "/portfolio/fills", params={"ticker": ticker, "limit": 1000})
    except Exception:
        return 0.0
    pnl = 0.0
    for fx in d.get("fills", []):
        if ticker not in (fx.get("ticker"), fx.get("market_ticker")):
            continue
        if since_ts and float(fx.get("ts") or 0) < since_ts - 5:   # only this trade's fills
            continue
        cnt = float(fx.get("count_fp") or 0)
        px = float(fx.get("yes_price_dollars") or 0)
        fee = float(fx.get("fee_cost") or 0)
        pnl += (cnt * px - fee) if fx.get("action") == "sell" else -(cnt * px + fee)
    return round(pnl, 2)


async def _settlement_revenue(client, ticker: str) -> float:
    """Settlement payout (USD) for a ticker — the revenue credited for contracts
    held to resolution.  Needed because a position held to a winning settlement has
    no sell fill, so fills alone would score it as a loss."""
    try:
        d = await client.req("GET", "/portfolio/settlements", params={"ticker": ticker, "limit": 50})
    except Exception:
        return 0.0
    rev = 0.0
    for s in d.get("settlements", []):
        if ticker in (s.get("ticker"), s.get("event_ticker")):
            rev += float(s.get("revenue") or 0) / 100.0
    return round(rev, 2)


async def _realized_pnl(client, ticker: str, since_ts: float = 0.0) -> float:
    """True realized P&L (USD) = fills (sells − buys) + settlement payout."""
    return round(await _pnl_from_fills(client, ticker, since_ts)
                 + await _settlement_revenue(client, ticker), 2)


async def _pv_target_guard(client, starting_pv: float, target_pv,
                           loss_floor_pv=None) -> None:
    """
    Portfolio halt in two phases — profit target AND/OR BOT-bank loss limit:

    1. Poll portfolio value on a timer; set ``_TARGET_REACHED`` (which stops the
       bot from opening any NEW buys) when EITHER
         • PV has grown to the profit target (start × (1+TARGET_PORTFOLIO_PCT/100)),
         • or PV has fallen to ``loss_floor_pv`` = start − SPORT_LOSS_LIMIT_USD
           (the session has lost the whole allotted bank).
       When a loss limit is armed the timer runs on the faster SPORT_LOSS_CHECK_S
       cadence (risk management); otherwise the 30-min profit cadence.
    2. Keep the TP-guardian running and wait for every position bought this
       session (``_FILLED_ORDERS``) to close.  Only then halt the bot and, when
       HALT_MACHINE_SHUTDOWN, shut the machine down.
    """
    if not target_pv and loss_floor_pv is None:
        return
    check_s = SPORT_LOSS_CHECK_S if loss_floor_pv is not None else SPORT_PV_CHECK_S

    # ── phase 1: poll portfolio value until target reached OR loss limit hit ──
    while not _TARGET_REACHED.is_set():
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=check_s)
            return                                # stopped elsewhere → exit guard
        except asyncio.TimeoutError:
            pass                                  # tick
        try:
            pv = await _portfolio_value(client)
        except Exception as e:
            print(f"  [TARGET-PV] check failed: {e}", file=sys.stderr)
            continue
        gain = (pv / starting_pv - 1.0) * 100.0 if starting_pv else 0.0
        floor_txt = f" / loss floor ${loss_floor_pv:.2f}" if loss_floor_pv is not None else ""
        tgt_txt = f" / target ${target_pv:.2f}" if target_pv else ""
        print(f"  [TARGET-PV] PV ${pv:.2f} ({gain:+.1f}%){tgt_txt}{floor_txt}  ({_now_cst()})")
        if target_pv and pv >= target_pv:
            print(f"  [TARGET-PV] profit target reached (PV ${pv:.2f} >= ${target_pv:.2f}) — "
                  f"stopping new buys; draining {len(_FILLED_ORDERS)} open position(s).")
            _TARGET_REACHED.set()
        elif loss_floor_pv is not None and pv <= loss_floor_pv:
            lost = starting_pv - pv
            remaining = max(0.0, SPORT_LOSS_LIMIT_USD - lost)
            print(f"  [LOSS-LIMIT] BOT bank down {SPORT_LOSS_LIMIT_PCT:.0f}% "
                  f"(lost ${lost:.2f} of ${SPORT_LOSS_LIMIT_USD:.2f}, ${remaining:.2f} left; "
                  f"PV ${pv:.2f} <= floor ${loss_floor_pv:.2f}) — stopping new buys; "
                  f"draining {len(_FILLED_ORDERS)} open position(s), then halting.")
            _TARGET_REACHED.set()

    # ── phase 2: wait for all session positions to close, then halt ──────────
    waited = 0
    while _FILLED_ORDERS:
        print(f"  [DRAIN] waiting for {len(_FILLED_ORDERS)} session position(s) to close: "
              f"{sorted(_FILLED_ORDERS)}  ({_now_cst()})")
        await asyncio.sleep(SPORT_DRAIN_POLL_S)
        waited += SPORT_DRAIN_POLL_S
        if SPORT_DRAIN_TIMEOUT_S and waited >= SPORT_DRAIN_TIMEOUT_S:
            print(f"  [DRAIN] timeout after {waited}s — {len(_FILLED_ORDERS)} position(s) "
                  f"still open; halting anyway.")
            break

    print(f"  [SPORTS TARGET-PV HALT] all session positions closed — halting"
          f"{' + machine shutdown' if HALT_MACHINE_SHUTDOWN else ''}.")
    if HALT_MACHINE_SHUTDOWN:
        print("  [SPORTS TARGET-PV HALT] initiating machine shutdown in 30s …")
        os.system("shutdown /s /f /t 30")
    _STOP.set()


def _tp_for(have: int, info: dict, pos: dict, pct: "float | None" = None) -> int:
    """TP price (cents) for a held position: prefer the recorded TP, else recompute
    from the recorded buy price, else derive from the position's actual cost basis.
    +SPORT_TARGET_PCT% over the entry (capped at 99); no bump on the TP.
    ``pct`` overrides the fallback percent (finals rule: SPORT_FINAL_TP_PCT)."""
    if info.get("tp"):
        return int(info["tp"])
    buy_at = info.get("buy_at")
    if not buy_at:                                    # unknown order (e.g. prior run): use cost basis
        cost = float(pos.get("total_traded_dollars")
                     or pos.get("market_exposure_dollars") or 0)
        buy_at = round(cost / have * 100) if have else 0
    if not buy_at:
        return 0
    return min(99, round(buy_at * (1 + (SPORT_TARGET_PCT if pct is None else pct) / 100.0)))


_PENDING_FLIP: dict = {}   # ticker (being sold) -> {"favorite": name, "event": event_ticker}


async def _tp_guardian(client, traded: set, shared: dict) -> None:
    """
    Safety net for ALL open positions (not just this session's _FILLED_ORDERS):
    every SPORT_TP_GUARD_S, for each market with an open position confirm a RESTING
    SELL order exists; if not, place a TP sell at +SPORT_TARGET_PCT% +bump.  Never
    creates a duplicate (skips any market that already has a resting order).  Two
    API reads per cycle (positions + resting orders), regardless of how many.

    NOTE: SPORT_SELL only gates the TP-placement pass (profit-taking).  The
    stop-loss and reversal-flip passes are loss/risk protection, not profit-taking,
    and always run regardless of SPORT_SELL — otherwise disabling TP sells would
    silently disable the stop-loss too.  Finals (user rule 07/12) bypass the
    SPORT_SELL gate entirely: they always get a +SPORT_FINAL_TP_PCT% TP.

    When a tracked position CLOSES, the match is removed from ``traded`` so the
    supervisor re-spawns its watcher and can take another entry if it again meets
    the buy conditions — the market is never permanently removed.
    """
    while True:
        await asyncio.sleep(SPORT_TP_GUARD_S)
        try:
            pd = await client.req("GET", "/portfolio/positions", params={"limit": 1000})
            positions = [p for p in pd.get("market_positions", [])
                         if abs(int(float(p.get("position_fp", "0")))) > 0]
            resting = await v1.resting_orders(client)         # all resting orders
        except Exception as e:
            print(f"  [GUARD] fetch failed: {e}", file=sys.stderr)
            continue
        resting_tickers = {o.get("ticker") for o in resting}
        open_tickers = {p.get("ticker") for p in positions}
        for tk in list(_FILLED_ORDERS):                       # a position just closed
            if tk not in open_tickers:
                info = _FILLED_ORDERS.pop(tk, None) or {}
                _STOP_STRIKES.pop(tk, None)                    # clear stop-loss breach counter
                _BAND_STRIKES.pop(tk, None)                    # clear price-band breach counter
                _FAVX_STRIKES.pop(tk, None)                    # clear favorite-comeback counter
                ev = _event_of(tk)
                if SPORT_REBUY:
                    for d in [x for x in traded if _event_of(x) == ev]:
                        traded.discard(d)                     # re-eligible for another entry
                try:                                          # update the SAME row's P&L on close
                    pnl = await _realized_pnl(client, tk, info.get("open_ts", 0))
                    pv_close = round(await _portfolio_value(client), 2)
                    pve = info.get("pv_entry")
                    pct = round((pv_close - pve) / pve * 100, 2) if isinstance(pve, (int, float)) and pve else ""
                    _trade_log_close(tk, info.get("open_ts", ""), {
                        "ts_close": _now_cst(), "pv_close": pv_close,
                        "realized_pnl": pnl, "pv_delta_pct": pct})
                except Exception as e:
                    print(f"  [TRADECSV] close record failed: {e}", file=sys.stderr)
                print(f"  [GUARD] {tk} position closed — "
                      + ("match re-eligible for another entry" if SPORT_REBUY
                         else "SPORT_REBUY=FALSE, match stays done (max 1 trade)"))
                flip = _PENDING_FLIP.pop(tk, None)   # reversal-flip sell just confirmed closed
                if flip and SPORT_PLACE_ORDERS and SPORT_REBUY:
                    try:
                        pm = await _player_markets(client, flip["event"])
                        fav_mkt = pm.get(flip["favorite"])
                        fav_bid = None
                        if fav_mkt:
                            fav_bid = await v1._bid_price(client, fav_mkt, "yes")
                        fav_bid_c = round(fav_bid * 100) if fav_bid is not None else None
                        if fav_mkt and fav_bid_c is not None and BID_LO <= fav_bid_c <= BID_HI:
                            print(f"  [REVERSAL] flip-sell confirmed closed — buying favorite "
                                  f"{flip['favorite']} @ {fav_bid_c}c")
                            await execute_sport_trade(client, fav_mkt, flip["favorite"], fav_bid_c,
                                                      situation="Eflip", confidence=CONF_HIGH,
                                                      reason="reversal-flip: favorite got their own "
                                                              "double-break after we held the "
                                                              "non-favorite — sold, buying favorite")
                        else:
                            print(f"  [REVERSAL] flip-sell closed but favorite "
                                  f"{flip['favorite']} bid {fav_bid_c}c not in {BID_LO}-{BID_HI}c "
                                  f"— no buy")
                    except Exception as e:
                        print(f"  [REVERSAL] flip-buy failed: {e}", file=sys.stderr)
        # SCOPE: resolve each position's sport via its series and only ever place
        # sells for sports in SPORTS_LIST.  Never sell any other category (other
        # sports, BTC, etc.).  If the taxonomy can't be fetched, place NO sells this
        # cycle (fail safe) rather than risk selling an out-of-scope position.  This
        # runs regardless of SPORT_SELL — stop-loss/reversal-flip need it too.
        try:
            smap = await ks._sports_series(client)
        except Exception as e:
            print(f"  [GUARD] sports taxonomy fetch failed: {e} — no sells this cycle",
                  file=sys.stderr)
            continue
        # ── STOP-LOSS pass ────────────────────────────────────────────────────
        # Runs over ALL in-scope held positions (incl. those with a resting TP —
        # that is exactly when the downside must be watched).  Trigger when the live
        # bid sits >= SPORT_STOP_LOSS_C below entry for SPORT_STOP_CONFIRM consecutive
        # cycles (these thin books go empty/null often, so one low read is not a
        # collapse — reads below SPORT_STOP_MIN_BID_C are treated as "no quote").
        # On trigger: cancel ALL resting orders for the whole MATCH (both player
        # sides share the event), then exit aggressively (cross SPORT_STOP_SLIP_C
        # through the bid).  If it can't fill it is re-priced to the bid next cycle.
        stopped: set = set()

        # ── PRICE-BAND EXIT pass (user rule 07/10) ─────────────────────────────
        # Hard ceiling/floor on ANY in-scope open position's live bid, regardless
        # of entry price: take profit at >= SPORT_TP_CEILING_C (near-certain win —
        # lock it and free the capital) or cut at <= SPORT_SL_FLOOR_C (near-certain
        # loss). The ceiling exits immediately; the floor needs SPORT_STOP_CONFIRM
        # cycles (thin books flicker) and a real quote (>= SPORT_STOP_MIN_BID_C).
        # The trade CSV row is updated on close by the close-detection loop above.
        if SPORT_TP_CEILING_C > 0 or SPORT_SL_FLOOR_C > 0:
            for p in positions:
                tk = p.get("ticker", "")
                sp = str(smap.get(ks._series_of(tk), {}).get("sport", "")).lower()
                if sp not in _SPORTS_SET:
                    continue
                have = abs(int(float(p.get("position_fp", "0"))))
                if have <= 0:
                    continue
                side = "yes" if float(p.get("position_fp", "0")) >= 0 else "no"
                try:
                    bid = await v1._bid_price(client, tk, side)
                except Exception:
                    bid = None
                bid_c = round(bid * 100) if bid is not None else None
                if bid_c is None:
                    continue
                hit_tp = SPORT_TP_CEILING_C > 0 and bid_c >= SPORT_TP_CEILING_C
                hit_sl = (SPORT_SL_FLOOR_C > 0
                          and SPORT_STOP_MIN_BID_C <= bid_c <= SPORT_SL_FLOOR_C)
                if not (hit_tp or hit_sl):
                    _BAND_STRIKES.pop(tk, None)          # back inside the band → reset
                    continue
                if hit_sl and not hit_tp:                # floor: confirm across cycles
                    strikes = _BAND_STRIKES.get(tk, 0) + 1
                    _BAND_STRIKES[tk] = strikes
                    if strikes < SPORT_STOP_CONFIRM:
                        print(f"  [BANDEXIT] {tk} bid {bid_c}c <= {SPORT_SL_FLOOR_C}c floor "
                              f"— breach {strikes}/{SPORT_STOP_CONFIRM}, watching")
                        continue
                try:                                     # reconfirm we still hold it
                    pos_now = await v1.position_for(client, tk)
                except Exception as e:
                    print(f"  [BANDEXIT] {tk} reconfirm failed: {e} — skip", file=sys.stderr)
                    continue
                have2 = pos_now["contracts"] if pos_now else 0
                if have2 <= 0:
                    continue
                event = _event_of(tk)
                try:                                     # cancel all resting orders for the match
                    for o in await v1.resting_orders(client):
                        if _event_of(o.get("ticker", "")) == event:
                            await client.req("DELETE", f"/portfolio/events/orders/{o['order_id']}")
                except Exception as e:
                    print(f"  [BANDEXIT] {tk} cancel match orders failed: {e}", file=sys.stderr)
                kind = (f"take-profit ceiling {SPORT_TP_CEILING_C}c" if hit_tp
                        else f"stop floor {SPORT_SL_FLOOR_C}c")
                exit_px = max(1, bid_c - SPORT_STOP_SLIP_C)   # cross the bid to ensure a fill
                print(f"  [BANDEXIT] {tk} bid {bid_c}c hit {kind} — exiting {have2} "
                      f"{side} @ {exit_px}c")
                try:
                    await v1.place_tp_sell(client, tk, side, have2, exit_px)
                    stopped.add(tk)
                    _BAND_STRIKES.pop(tk, None)
                except Exception as e:
                    print(f"  [BANDEXIT] {tk} exit sell failed: {e}", file=sys.stderr)

        if SPORT_STOP_LOSS_C > 0:
            for p in positions:
                tk = p.get("ticker", "")
                if tk in stopped:
                    continue
                sp = str(smap.get(ks._series_of(tk), {}).get("sport", "")).lower()
                if sp not in _SPORTS_SET:
                    continue
                have = abs(int(float(p.get("position_fp", "0"))))
                if have <= 0:
                    continue
                info = _FILLED_ORDERS.get(tk, {})
                entry = info.get("buy_at")
                if not entry:                                  # prior-run position: use cost basis
                    cost = float(p.get("total_traded_dollars")
                                 or p.get("market_exposure_dollars") or 0)
                    entry = round(cost / have * 100) if have else 0
                if not entry:
                    continue
                side = "yes" if float(p.get("position_fp", "0")) >= 0 else "no"
                try:
                    bid = await v1._bid_price(client, tk, side)        # dollars, or None
                except Exception:
                    bid = None
                bid_c = round(bid * 100) if bid is not None else None
                trigger = entry - SPORT_STOP_LOSS_C
                deep = entry - SPORT_STOP_DEEP_C
                if bid_c is None or bid_c < SPORT_STOP_MIN_BID_C:   # empty/no-quote → ignore, keep strikes
                    continue
                if bid_c > trigger:                            # recovered/above stop → reset strikes
                    _STOP_STRIKES.pop(tk, None)
                    continue
                strikes = _STOP_STRIKES.get(tk, 0) + 1         # breach confirmed this cycle
                _STOP_STRIKES[tk] = strikes
                need = 1 if bid_c <= deep else SPORT_STOP_CONFIRM   # blowout → exit now; else confirm
                if strikes < need:
                    print(f"  [STOPLOSS] {tk} bid {bid_c}c <= {trigger}c — breach "
                          f"{strikes}/{need}, watching (no exit yet)")
                    continue
                try:                                           # reconfirm we still hold it
                    pos_now = await v1.position_for(client, tk)
                except Exception as e:
                    print(f"  [STOPLOSS] {tk} reconfirm failed: {e} — skip", file=sys.stderr)
                    continue
                have2 = pos_now["contracts"] if pos_now else 0
                if have2 <= 0:
                    continue
                # cancel ALL resting orders for the whole MATCH (event) before exiting
                event = _event_of(tk)
                try:
                    for o in await v1.resting_orders(client):
                        if _event_of(o.get("ticker", "")) == event:
                            await client.req("DELETE", f"/portfolio/events/orders/{o['order_id']}")
                except Exception as e:
                    print(f"  [STOPLOSS] {tk} cancel match orders failed: {e}", file=sys.stderr)
                exit_px = max(1, bid_c - SPORT_STOP_SLIP_C)    # cross the bid to ensure a fill
                print(f"  [STOPLOSS] {tk} bid {bid_c}c <= entry {entry}c - {SPORT_STOP_LOSS_C}c "
                      f"({trigger}c) x{strikes} — exiting {have2} {side} @ {exit_px}c")
                try:
                    await v1.place_tp_sell(client, tk, side, have2, exit_px)
                    stopped.add(tk)
                except Exception as e:
                    print(f"  [STOPLOSS] {tk} exit sell failed: {e}", file=sys.stderr)

        # ── REVERSAL-FLIP pass ─────────────────────────────────────────────────
        # User rule 07/05: if we bought the LEADER of a double-break (situation E)
        # and that leader was the non-favorite, and the match now shows the rank
        # FAVORITE with their OWN double-break, the original read has reversed —
        # sell the held (non-favorite) position immediately (cancel all resting
        # orders for the match first) and, once that sell is confirmed closed (see
        # the close-detection loop above), buy the favorite if their live bid is in
        # the general buy band (BID_LO-BID_HI).  Never the symmetric case (holding
        # the favorite, underdog gets a double break) — that would fight the other
        # favorite-protection rules.  Disabled entirely (07/06) when
        # SPORT_REVERSAL_FLIP=FALSE — user wants nothing to sell early except a TP
        # fill or natural settlement.
        for p in (positions if SPORT_REVERSAL_FLIP else []):
            tk = p.get("ticker", "")
            if tk in stopped or tk in _PENDING_FLIP:
                continue
            info = _FILLED_ORDERS.get(tk, {})
            if info.get("situation") != "E":
                continue
            sp = str(smap.get(ks._series_of(tk), {}).get("sport", "")).lower()
            if sp not in _SPORTS_SET:
                continue
            have = abs(int(float(p.get("position_fp", "0"))))
            if have <= 0:
                continue
            try:
                sc = await get_kalshi_tennis_score(client, tk)
            except Exception as e:
                print(f"  [REVERSAL] {tk} score fetch failed: {e}", file=sys.stderr)
                continue
            if not sc:
                continue
            for pl in sc.get("players", []):
                rk = rank_for(pl.get("name", ""), shared.get("rankings") or {})
                pl["rank"] = rk if rk is not None else None
                pl["rank_tour"] = tour_for(pl.get("name", ""), shared.get("rank_tours") or {})
            md = _md_from_kalshi(sc)
            if md is None:
                continue
            fav = md.get("favorite")
            if fav is None or md.get("double_break") != fav:
                continue                     # no reversal to the favorite — nothing to do
            pm = await _player_markets(client, tk)
            names_by_ticker = {mt: nm for nm, mt in pm.items()}
            held_name = names_by_ticker.get(tk)
            players = sc.get("players") or []
            if len(players) < 2:
                continue
            fav_name = players[0]["name"] if fav == "A" else players[1]["name"]
            if held_name == fav_name:
                continue                     # we already hold the favorite — nothing to flip
            try:
                pos_now = await v1.position_for(client, tk)
            except Exception as e:
                print(f"  [REVERSAL] {tk} reconfirm failed: {e} — skip", file=sys.stderr)
                continue
            have2 = pos_now["contracts"] if pos_now else 0
            if have2 <= 0:
                continue
            side = "yes" if float(pos_now.get("position_fp", "0")) >= 0 else "no"
            try:
                bid = await v1._bid_price(client, tk, side)
            except Exception:
                bid = None
            bid_c = round(bid * 100) if bid is not None else None
            if bid_c is None:
                continue
            event = _event_of(tk)
            try:                              # cancel ALL resting orders for the whole match
                for o in await v1.resting_orders(client):
                    if _event_of(o.get("ticker", "")) == event:
                        await client.req("DELETE", f"/portfolio/events/orders/{o['order_id']}")
            except Exception as e:
                print(f"  [REVERSAL] {tk} cancel match orders failed: {e}", file=sys.stderr)
            exit_px = max(1, bid_c - SPORT_STOP_SLIP_C)
            print(f"  [REVERSAL] {tk} favorite {fav_name} now has the double-break — "
                  f"selling held non-favorite {held_name} @ {exit_px}c, will buy "
                  f"{fav_name} once closed")
            try:
                await v1.place_tp_sell(client, tk, side, have2, exit_px)
                stopped.add(tk)
                _PENDING_FLIP[tk] = {"favorite": fav_name, "event": event}
            except Exception as e:
                print(f"  [REVERSAL] {tk} flip-sell failed: {e}", file=sys.stderr)

        # ── FAVORITE-EXIT pass (v3) ──────────────────────────────────────────
        # Three sell-only exit rules over held positions, softer/earlier than the
        # 30c stop-loss (each needs SPORT_FAVX_CONFIRM confirming cycles unless
        # noted): (1) bought-high collapse — bought ≥76c, live odds <25c, outside
        # the deciding set's last 2 points (user 07/10, favorite-independent);
        # (2) favorite-comeback — holding the NON-favorite when the pre-match
        # favorite's comeback is confirmed (07/08; double-break trigger is
        # immediate); (3) favorite-collapse — holding the favorite when it's being
        # beaten badly (07/10).  Sell only — no re-buy.
        for p in (positions if ((SPORT_FAV_COMEBACK_EXIT or SPORT_HIGH_COLLAPSE_EXIT)
                                and _HAS_PREDICT) else []):
            tk = p.get("ticker", "")
            if tk in stopped or tk in _PENDING_FLIP:
                continue
            sp = str(smap.get(ks._series_of(tk), {}).get("sport", "")).lower()
            if sp != "tennis":             # tennis-specific rule (favorite/md shape)
                continue
            have = abs(int(float(p.get("position_fp", "0"))))
            if have <= 0:
                continue
            info = _FILLED_ORDERS.get(tk, {})
            entry = info.get("buy_at")
            if not entry:                  # prior-run position: use cost basis
                cost = float(p.get("total_traded_dollars")
                             or p.get("market_exposure_dollars") or 0)
                entry = round(cost / have * 100) if have else 0
            try:
                sc = await get_kalshi_tennis_score(client, tk)
            except Exception as e:
                print(f"  [FAVEXIT] {tk} score fetch failed: {e}", file=sys.stderr)
                continue
            if not sc:
                continue
            for pl in sc.get("players", []):
                rk = rank_for(pl.get("name", ""), shared.get("rankings") or {})
                pl["rank"] = rk if rk is not None else None
                pl["rank_tour"] = tour_for(pl.get("name", ""), shared.get("rank_tours") or {})
            md = _md_from_kalshi(sc)
            players = sc.get("players") or []
            if md is None or len(players) < 2:
                continue
            # who we hold and their live bid — needed by every exit rule below
            pm = await _player_markets(client, tk)
            held_name = {mt: nm for nm, mt in pm.items()}.get(tk)
            side = "yes" if float(p.get("position_fp", "0")) >= 0 else "no"
            try:
                held_bid = await v1._bid_price(client, tk, side)
            except Exception:
                held_bid = None
            held_bid_c = round(held_bid * 100) if held_bid is not None else None

            async def _bid_c_of(name):
                mkt = pm.get(name)
                if not mkt:
                    return None
                try:
                    b = await v1._bid_price(client, mkt, "yes")
                except Exception:
                    b = None
                return round(b * 100) if b is not None else None

            do_exit, why = False, ""
            # ── bought-high collapse (user 07/10): entry ≥76c and live odds <25c,
            # unless we're in the deciding set's last 2 points. Favorite-independent,
            # so it runs before (and regardless of) the favorite determination.
            if SPORT_HIGH_COLLAPSE_EXIT:
                do_exit, why = bought_high_collapse_exit(entry or None, held_bid_c, players)

            # ── favorite-based exits: collapse if we hold the favorite, comeback if
            # we hold the non-favorite. Needs a favorite (v3 priority ladder) and is
            # skipped once the bought-high rule has already fired.
            # Finals rule (user 07/12): "final" in the tournament label → no favorite
            # logic at all, so these exits are skipped too.
            if _event_of(tk) not in _TOURNAMENT:      # cache miss → fetch so the rule can see the round
                await _match_meta(client, tk)
            if not do_exit and SPORT_FAV_COMEBACK_EXIT and not _is_final_round(tk):
                try:
                    _live_odds, og_odds = await get_player_odds(client, tk, sc.get("match_start"))
                except Exception:
                    og_odds = {}
                md["favorite"] = determine_favorite(
                    (players[0].get("name", ""), players[1].get("name", "")),
                    og_odds, (players[0].get("rank"), players[1].get("rank")),
                    rank_tours=(players[0].get("rank_tour"), players[1].get("rank_tour")))
                fav = md.get("favorite")
                held_side = (None if held_name is None
                             else "A" if held_name == players[0].get("name")
                             else "B" if held_name == players[1].get("name") else None)
                if fav is not None and held_side is not None:
                    fav_name = players[0]["name"] if fav == "A" else players[1]["name"]
                    opp_name = players[1]["name"] if fav == "A" else players[0]["name"]
                    if held_name == fav_name:
                        # we HOLD the FAVORITE → collapse exit when the opponent's
                        # live price shows the favorite is being beaten badly (07/10)
                        opp_bid_c = await _bid_c_of(opp_name)
                        do_exit, why = favorite_collapse_exit(md, held_side, opp_bid_c)
                    else:
                        # we HOLD the NON-favorite → favorite-comeback exit (07/08)
                        fav_bid_c = await _bid_c_of(fav_name)
                        do_exit, why = favorite_comeback_exit(md, held_side, entry or None,
                                                              held_bid_c, fav_bid_c)
            if not do_exit:
                _FAVX_STRIKES.pop(tk, None)          # nothing firing → reset
                continue
            strikes = _FAVX_STRIKES.get(tk, 0) + 1
            _FAVX_STRIKES[tk] = strikes
            need = 1 if "double-break" in why else SPORT_FAVX_CONFIRM
            if strikes < need:
                print(f"  [FAVEXIT] {tk} {why} — breach {strikes}/{need}, watching")
                continue
            if held_bid_c is None or held_bid_c < SPORT_STOP_MIN_BID_C:
                continue                   # no sane quote to exit into this cycle
            try:                           # reconfirm we still hold it
                pos_now = await v1.position_for(client, tk)
            except Exception as e:
                print(f"  [FAVEXIT] {tk} reconfirm failed: {e} — skip", file=sys.stderr)
                continue
            have2 = pos_now["contracts"] if pos_now else 0
            if have2 <= 0:
                continue
            event = _event_of(tk)
            try:                           # cancel ALL resting orders for the match
                for o in await v1.resting_orders(client):
                    if _event_of(o.get("ticker", "")) == event:
                        await client.req("DELETE", f"/portfolio/events/orders/{o['order_id']}")
            except Exception as e:
                print(f"  [FAVEXIT] {tk} cancel match orders failed: {e}", file=sys.stderr)
            exit_px = max(1, held_bid_c - SPORT_STOP_SLIP_C)
            print(f"  [FAVEXIT] {tk} holding {held_name or side}, {why} — "
                  f"exiting {have2} {side} @ {exit_px}c (entry {entry}c, even at a loss)")
            try:
                await v1.place_tp_sell(client, tk, side, have2, exit_px)
                stopped.add(tk)
                _FAVX_STRIKES.pop(tk, None)
            except Exception as e:
                print(f"  [FAVEXIT] {tk} exit sell failed: {e}", file=sys.stderr)

        # collect positions that appear to need a TP (open, in-scope sport, no resting
        # sell). SPORT_SELL=FALSE disables this pass EXCEPT for finals (user rule
        # 07/12): a position on a "final" match always gets its +SPORT_FINAL_TP_PCT% TP.
        candidates = []
        for p in positions:
            tk = p.get("ticker", "")
            if tk in resting_tickers or tk in stopped:         # has a TP, or just stopped out
                continue
            sp = str(smap.get(ks._series_of(tk), {}).get("sport", "")).lower()
            if sp not in _SPORTS_SET:
                print(f"  [GUARD] {tk} sport={sp or 'unknown'} not in {sorted(_SPORTS_SET)} "
                      f"— skip (out-of-scope, no sell placed)")
                continue
            if _event_of(tk) not in _TOURNAMENT:   # finals rule needs the round label
                await _match_meta(client, tk)
            if not SPORT_SELL and not _is_final_round(tk):
                continue                           # selling disabled → only finals get a TP
            candidates.append(p)
        if not candidates:
            continue

        # double-confirm before placing any TP: wait, then re-fetch resting orders
        # and AUTHORITATIVELY re-check each candidate's position per ticker.  STRICT
        # rule: only place a sell when an active position still exists for that exact
        # ticker AND no resting order is pending for it — otherwise never place.
        await asyncio.sleep(SPORT_GUARD_RECONFIRM_S)
        try:
            rest2 = {o.get("ticker") for o in await v1.resting_orders(client)}
        except Exception as e:
            print(f"  [GUARD] reconfirm fetch failed: {e}", file=sys.stderr)
            continue
        for c in candidates:
            tk = c.get("ticker", "")
            try:
                pos_now = await v1.position_for(client, tk)    # authoritative, per-ticker
            except Exception as e:
                print(f"  [GUARD] {tk} reconfirm failed: {e} — skip", file=sys.stderr)
                continue
            have = pos_now["contracts"] if pos_now else 0
            if have <= 0:                                      # NO active position → never sell
                print(f"  [GUARD] {tk} no active position on reconfirm — skip (no sell placed)")
                continue
            if tk in rest2:                                    # resting order pending → no duplicate
                continue
            side = "yes" if float(pos_now.get("position_fp", "0")) >= 0 else "no"
            is_final = _is_final_round(tk)
            tp = _tp_for(have, _FILLED_ORDERS.get(tk, {}), pos_now,
                         pct=SPORT_FINAL_TP_PCT if is_final else None)
            if not tp:
                print(f"  [GUARD] {tk} holding {have} {side} but no TP price derivable — skip",
                      file=sys.stderr)
                continue
            if tp > SPORT_MAX_TP_C:                            # TP too high (e.g. 99c)
                if is_final:                                   # finals must have an exit → clamp
                    print(f"  [GUARD] {tk} finals TP {tp}c > {SPORT_MAX_TP_C}c — "
                          f"clamped to {SPORT_MAX_TP_C}c")
                    tp = SPORT_MAX_TP_C
                else:                                          # normal → hold, no sell
                    print(f"  [GUARD] {tk} TP {tp}c > {SPORT_MAX_TP_C}c — not placing sell (holding)")
                    continue
            print(f"  [GUARD] {tk} holding {have} {side} (reconfirmed), no resting sell — "
                  f"placing TP @ {tp}c" + (f" (finals +{SPORT_FINAL_TP_PCT:.0f}%)" if is_final else ""))
            try:
                await v1.place_tp_sell(client, tk, side, have, tp)
                _FILLED_ORDERS.setdefault(tk, {"contracts": have, "buy_at": tp, "tp": tp})
            except Exception as e:
                print(f"  [GUARD] {tk} place TP failed: {e}", file=sys.stderr)


async def _positions_logger(client) -> None:
    """
    Every SPORT_POS_LOG_S (30 min) log all open positions in the form:
      orders{TICKER{contracts:N, buy_at:X, plan_to_sell:Y}, ...}
    buy_at = actual cost basis (cents); plan_to_sell = the intended TP price.
    """
    while not _STOP.is_set():
        try:
            pd = await client.req("GET", "/portfolio/positions", params={"limit": 1000})
            positions = [p for p in pd.get("market_positions", [])
                         if abs(int(float(p.get("position_fp", "0")))) > 0]
        except Exception as e:
            print(f"  [POSITIONS] fetch failed: {e}", file=sys.stderr)
            positions = None
        if positions is not None:
            parts = []
            for p in positions:
                tk = p.get("ticker", "")
                have = abs(int(float(p.get("position_fp", "0"))))
                cost = float(p.get("total_traded_dollars")
                             or p.get("market_exposure_dollars") or 0)
                buy_at = round(cost / have * 100) if have else 0
                plan = _tp_for(have, _FILLED_ORDERS.get(tk, {}), p)
                parts.append(f"{tk}{{contracts:{have}, buy_at:{buy_at}, plan_to_sell:{plan}}}")
            print(f"  [POSITIONS] orders{{{', '.join(parts)}}}  ({_now_cst()})")
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=SPORT_POS_LOG_S)
            return                                            # stopped elsewhere
        except asyncio.TimeoutError:
            pass


def _has_progress(sc) -> bool:
    """True once the match has actually started — any set won, game, or point played.
    Pure 0-0 with 0:0 points means games not started yet."""
    for p in (sc.get("players") or []):
        if p.get("sets_won") or any(int(g or 0) for g in (p.get("games") or [])):
            return True
        cg = str(p.get("current_game") or "0").strip().upper()
        if cg not in ("0", ""):
            return True
    return False


async def _eval_one_tennis(c, tk, rankings, combos, who=None, rank_tours=None) -> "dict | None":
    """Evaluate one tennis market: print live score/odds + signal; return the
    predict_buy signal (or None if no live score / not a tennis match).  Matches
    that have not started yet (0-0, no points) return a {not_started: True} marker
    and are NOT logged — the watcher then polls them only every 30 min."""
    sc = None
    try:
        sc = await get_kalshi_tennis_score(c, tk)        # Kalshi milestone source
        if sc is None and who:                            # ESPN fallback (ATP/WTA)
            sc = await get_match_score(who, tk)
    except Exception as e:
        print(f"  {tk}: score error: {e}")
        return None
    if not sc:
        return None
    if not _has_progress(sc):                             # not started → no odds call, no log
        return {"action": "WAIT", "not_started": True, "ticker": tk}
    rank_tours = rank_tours or {}
    for p in sc.get("players", []):
        rk = rank_for(p.get("name", ""), rankings)
        p["rank"] = rk if rk is not None else "NA"
        p["rank_tour"] = tour_for(p.get("name", ""), rank_tours)
    try:
        live, orig = await get_player_odds(c, tk, sc.get("match_start"))
    except Exception:
        live, orig = {}, {}
    order = [p["name"] for p in sc["players"]] or list(live)
    fmt = lambda dct: "; ".join(f"{n.split()[-1]}:{dct.get(n)}" for n in order if n in dct)
    tour = _TOURNAMENT.get(_event_of(tk))           # e.g. "Wimbledon Men Singles - Round of 128"
    prefix = f"[{tour}] " if tour else ""
    cs = sum(int(p.get("sets_won", 0) or 0) for p in sc.get("players", []))
    set3 = "[SET3] " if cs == 2 else ""             # decider subset — tag for visibility
    # favorite priority (v3, 07/10): original-odds edge >21c, else WTA/ATP-vs-ITF
    # ranking category + rank-difference rules, else Neutral (no favorite).
    # Finals rule (user 07/12): tournament label containing "final" → always Neutral.
    neutral_final = _is_final_round(tk)
    fav_side = None
    if _HAS_PREDICT and len(order) >= 2 and not neutral_final:
        try:
            players = sc.get("players", [])
            fav_side = determine_favorite(
                (order[0], order[1]), orig,
                (players[0].get("rank"), players[1].get("rank")),
                rank_tours=(players[0].get("rank_tour"), players[1].get("rank_tour")))
        except Exception:
            fav_side = None
    fav_name = order[0 if fav_side == "A" else 1] if fav_side else None
    favours = (f" >> Favours :: {fav_name.split()[-1]}" if fav_name
               else " >> Favours :: Neutral" + (" (final)" if neutral_final else ""))
    line = (f"{set3}{prefix}{one_liner(sc)} >>> live:{{{fmt(live)}}} "
            f"Original:{{{fmt(orig)}}}{_odds_drift_note(orig, live)}{favours}")

    sig = None
    if _HAS_PREDICT:
        try:
            sig = predict_buy(sc, live, orig, combos=combos, ticker=tk,
                              neutral_favorite=neutral_final)
        except Exception as e:
            sig = {"action": "WAIT", "reason": f"predict error: {e}"}

    # Logging: BUY always surfaces immediately; players data prints at most every
    # SPORT_LOG_EVERY_S per match; WAIT never prints a [SIGNAL] line.
    action = sig.get("action") if sig else "WAIT"
    now = time.time()
    if action == "BUY":
        print(f"  {line}")
        print(f"  [SIGNAL] {sig['tip']}  ({sig['situation']}/{sig['confidence']}) {sig['reason']}")
        _LAST_LOG[tk] = now
    elif (now - _LAST_LOG.get(tk, 0)) >= SPORT_LOG_EVERY_S:
        print(f"  {line}")
        if action == "SKIP":
            print(f"  [SIGNAL] SKIP: {sig.get('reason', '')}")
        _LAST_LOG[tk] = now

    if sig is None:
        return None
    # leading side's live bid (the market favorite) — used to drop decided matches
    _bids = [b for b in live.values() if isinstance(b, (int, float))]
    sig["leader_bid"] = max(_bids) if _bids else None
    sig["set3"] = (cs == 2)              # 3rd-set decider → keep polling at 10s, never drop
    return sig


async def _watch_ticker(c, tk, shared, combos, traded, dropped, sem,
                        main_by_sport, who=None) -> None:
    """
    One independent watcher per match: poll every SPORT_POLL_S; on a BUY signal
    (player priced in band) place + manage the order, then stop.  Exits after a
    few empty polls (non-tennis / match ended), or drops the match for good once
    the leading side's bid is > SPORT_DECIDED_BID (match decided — no value).
    The bounded ``sem`` limits CONCURRENT eval API calls only — the long trade
    management runs outside it so other watchers keep polling.

    Players-data logging and prediction run ONLY while the match is in the active
    (main) watchlist — if a refresh drops it out, the watcher exits (the
    supervisor re-spawns one if it returns to the list).
    """
    misses = 0
    while tk not in traded:
        if _TARGET_REACHED.is_set():           # profit target hit → stop polling for buys
            return
        _pause = _PAUSE_UNTIL - time.time()    # insufficient-balance pause → idle, don't poll
        if _pause > 0:
            await asyncio.sleep(min(_pause + 1, SPORT_NOTSTARTED_POLL_S))
            continue
        if not any(mt["ticker"] == tk          # only evaluate/predict for main_watchlist
                   for ms in main_by_sport.values() for mt in ms):
            return
        sig = None
        try:
            async with sem:
                sig = await _eval_one_tennis(c, tk, shared["rankings"], combos, who=who,
                                             rank_tours=shared.get("rank_tours"))
        except Exception as e:
            print(f"  [{tk}] watch error: {e}", file=sys.stderr)

        if sig and sig.get("not_started"):   # games not started → check only every 30 min
            misses = 0
            await asyncio.sleep(SPORT_NOTSTARTED_POLL_S)
            continue
        if sig is None:
            misses += 1
            if misses >= 3:                  # no tennis data → stop watching this one
                return
        else:
            misses = 0
            lb = sig.get("leader_bid")
            # Heavily favored (leader bid > SPORT_DECIDED_BID): do NOT drop — keep
            # watching for a price drop as the match goes to set 2/3 (B2 opportunity),
            # just don't buy yet.
            decided = lb is not None and lb > SPORT_DECIDED_BID
            if sig.get("action") == "BUY" and SPORT_PLACE_ORDERS and not decided:
                pm = await _player_markets(c, tk)
                mkt = pm.get(sig["player"])
                if not mkt:
                    print(f"  [{tk}] no market ticker for {sig['player']!r}; skip")
                else:
                    # ultra-high conviction backing the favorite → 1.5x size
                    n_contracts = SPORT_CONTRACTS
                    if (sig.get("confidence") == CONF_ULTRA
                            and sig.get("backing_favorite")):
                        n_contracts = max(1, round(SPORT_CONTRACTS * SPORT_ULTRA_FAV_MULT))
                        print(f"  [SIZEUP] ultra-high on the favorite {sig['player']} — "
                              f"buying {n_contracts} (= {SPORT_CONTRACTS} x{SPORT_ULTRA_FAV_MULT})")
                    traded.add(tk)            # claim before the (long) trade flow
                    if not SPORT_REBUY:       # one trade per match — claim BOTH sides
                        for _mtk in pm.values():
                            if _mtk:
                                traded.add(_mtk)
                    try:
                        await execute_sport_trade(c, mkt, sig["player"], sig["bid"],
                                                  contracts=n_contracts,
                                                  situation=sig.get("situation", ""),
                                                  confidence=sig.get("confidence", ""),
                                                  reason=sig.get("reason", ""),
                                                  set_num=sig.get("set_num", ""))
                    except Exception as e:
                        print(f"  [{tk}] trade error: {e}", file=sys.stderr)
                    return                     # one trade per match per run
            elif sig.get("action") == "BUY" and decided:
                print(f"  [{tk}] leader at {lb}c (> {SPORT_DECIDED_BID}c) — watching for "
                      f"price drop, not buying yet")
        await asyncio.sleep(SPORT_POLL_S)


async def _match_meta(c, ticker: str) -> tuple:
    """
    (age_hours, kalshi_status, start_ts) from the match's milestone in ONE call:
      age_hours    — hours since start_date (None if unknown/not started)
      kalshi_status— milestone details.status lowercased ("live", "not_started",
                     "interrupted", "cancelled", "wov", …) or ""
      start_ts     — match start time as a UTC epoch (None if unknown)
    Machine is CST; age is a duration and epoch comparisons are timezone-safe.
    """
    event = _event_of(ticker)
    try:
        d = await c.req("GET", "/milestones",
                        params={"related_event_ticker": event, "limit": 1})
        ms = d.get("milestones", [])
        if not ms:
            return None, "", None
        m0 = ms[0]
        det = m0.get("details") or {}
        status = str(det.get("status") or "").lower()
        tour = det.get("tournament_name")
        if tour:                                     # cache the tournament label for the log
            rnd = det.get("round")
            _TOURNAMENT[event] = f"{tour} - {rnd}" if rnd else str(tour)
        age = start_ts = None
        sd = m0.get("start_date")
        if sd:
            start = datetime.fromisoformat(str(sd).replace("Z", "+00:00"))
            start_ts = start.timestamp()
            age = (datetime.now(timezone.utc) - start).total_seconds() / 3600.0
        return age, status, start_ts
    except Exception:
        return None, "", None


async def _live_matches_in_band(c, sport: str) -> list:
    """
    Live matches for ``sport`` with estimated USD volume >= MIN_VOLUME_USD (STRICT:
    lower-volume matches are excluded from the watchlist and never traded) whose YES
    or NO bid is within [SPORT_BID_LO, SPORT_BID_HI]c, sorted by volume (highest
    first), capped at TOP_N_PER_SPORT, then with matches live > SPORT_MAX_LIVE_HOURS
    removed (stale / likely finished).
    """
    all_live = await ks.filter_by_sport_min_volume_live(
        sport, 0, top_n=10 ** 9, client=c)        # 0 floor + no cap → every live match

    def in_band(m) -> bool:
        for b in (m.get("yes_bid"), m.get("no_bid")):
            if b is not None and SPORT_BID_LO <= b <= SPORT_BID_HI:
                return True
        return False

    kept, low_vol = [], 0
    for m in all_live:
        if not in_band(m):
            continue
        if float(m.get("usd_volume", 0.0)) < MIN_VOLUME_USD:   # STRICT volume floor
            low_vol += 1
            continue
        kept.append(m)
    if low_vol:
        print(f"  [{sport}] excluded {low_vol} match(es) below MIN_VOLUME_USD=${MIN_VOLUME_USD:,.0f}")
    kept.sort(key=lambda m: m.get("usd_volume", 0.0), reverse=True)
    kept = kept[:TOP_N_PER_SPORT]

    # checkpoint: drop matches that are not actively being played (Kalshi status)
    # or that have been live > SPORT_MAX_LIVE_HOURS — both from one milestone call.
    metas = await asyncio.gather(*(_match_meta(c, m["ticker"]) for m in kept),
                                 return_exceptions=True)
    fresh = []
    for m, meta in zip(kept, metas):
        age, status, start_ts = (meta if isinstance(meta, tuple) and len(meta) == 3
                                 else (None, "", None))
        if status in _KALSHI_DROP_STATUSES:
            print(f"  [status] {m['ticker']} kalshi status={status!r} — not active, removed")
            continue
        if isinstance(age, (int, float)) and age > SPORT_MAX_LIVE_HOURS:
            print(f"  [stale] {m['ticker']} live {age:.1f}h > {SPORT_MAX_LIVE_HOURS:.0f}h — removed")
            continue
        m["age_hours"] = age
        m["start_ts"] = start_ts       # future start → parked as pending
        fresh.append(m)

    # secondary checkpoint: confirm via SofaScore status (optional; fails open).
    # One browser session fetches all live statuses; drop interrupted/suspended/etc.
    if sport.lower() == "tennis" and SPORT_CONFIRM_ACTIVE and _HAS_PREDICT and fresh:
        try:
            statuses = await live_statuses()
        except Exception:
            statuses = []
        if statuses:                              # fail open if the scraper returned nothing
            active = []
            for m in fresh:
                st = _status_for_match(m, statuses)
                if st in _DROP_STATUSES:
                    print(f"  [status] {m['ticker']} status={st!r} — not active, removed")
                    continue
                active.append(m)
            fresh = active
    return fresh


def _status_for_match(m, statuses) -> "str | None":
    """SofaScore status type for a match, matched by player name (None if absent)."""
    who = m.get("yes_sub_title") or m.get("title", "")
    if not who:
        return None
    for ev in statuses:
        if _name_matches(who, ev.get("home", "")) or _name_matches(who, ev.get("away", "")):
            return ev.get("status")
    return None


def _is_pending(m: dict) -> bool:
    """Match not started yet — its start time is still in the future."""
    ts = m.get("start_ts")
    return ts is not None and ts > time.time()


def _split_started(by_sport: dict) -> tuple:
    """
    Split each sport's STEP-1 list by start time vs now:
      main_by_sport    — start time has passed (live) → used by subsequent steps
      pending_by_sport — not started yet → parked for the promoter
    """
    main, pend = {}, {}
    for sport, ms in by_sport.items():
        main[sport] = [m for m in ms if not _is_pending(m)]
        pend[sport] = [m for m in ms if _is_pending(m)]
    return main, pend


async def _main_refresh(c, main_by_sport: dict, pending_by_sport: dict,
                        shared: dict) -> None:
    """
    STRICTLY every SPORT_MAIN_REFRESH_S (60 min): re-discover live matches and
    rebuild the lists — started → ``main_by_sport`` (active watchlist), not yet
    started → ``pending_by_sport``.  NOTE: orders already placed this session are
    tracked in ``_FILLED_ORDERS`` and kept monitored by the TP-guardian / drain
    regardless of whether their match stays in (or drops out of) the main list.
    """
    while not _STOP.is_set():
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=SPORT_MAIN_REFRESH_S)
            return                                       # stopped elsewhere
        except asyncio.TimeoutError:
            pass
        if _TARGET_REACHED.is_set():
            continue                                     # no new discovery after target
        for sport in SPORTS_LIST:
            try:
                fresh = await _live_matches_in_band(c, sport)
            except Exception as e:
                print(f"  [main-refresh {sport}] {e}", file=sys.stderr)
                continue
            main_by_sport[sport] = [m for m in fresh if not _is_pending(m)]
            pending_by_sport[sport] = [m for m in fresh if _is_pending(m)]
            print(f"  [main-refresh {sport}] live={len(main_by_sport[sport])} "
                  f"pending={len(pending_by_sport[sport])}  ({v1._cst_now():%H:%M:%S} CST)")
        try:
            shared["rankings"] = load_rankings_csv()
            shared["rank_tours"] = load_rank_tours()
        except Exception:
            pass


async def _promotion_volume_ok(client, ticker: str) -> bool:
    """Re-check a single ticker's CURRENT usd_volume against MIN_VOLUME_USD right
    before promotion — a match's volume when first discovered (pre-start, often
    near-zero) is not a reliable predictor of its volume once play begins, so
    trusting the stale discovery-time value could promote a still-thin market.
    Fails open (returns True) on a fetch error so a transient API hiccup doesn't
    strand a match in pending forever."""
    try:
        md = await client.req("GET", f"/markets/{ticker}")
        m = md.get("market", {}) or {}
        usd_volume = ks._f(m.get("volume_fp")) * ks._f(m.get("last_price_dollars"))
    except Exception as e:
        print(f"  [promote] {ticker} volume re-check failed: {e} — promoting anyway (fail open)",
              file=sys.stderr)
        return True
    return usd_volume >= MIN_VOLUME_USD


async def _pending_promoter(client, main_by_sport: dict, pending_by_sport: dict) -> None:
    """
    Every SPORT_PENDING_REFRESH_S (30 min): move pending matches whose start time
    has now passed into ``main_by_sport`` (active watchlist) — but first RE-CHECK
    each one's current usd_volume against MIN_VOLUME_USD (one API call per
    promotion candidate).  A match discovered hours earlier, pre-start, may have
    had near-zero volume then; that stale reading is not trustworthy evidence
    it still clears the floor once play begins, so matches that no longer clear
    it are dropped (not promoted) instead of silently entering the watchlist.
    Full re-discovery of the main list is done by _main_refresh.
    """
    while not _STOP.is_set():
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=SPORT_PENDING_REFRESH_S)
            return
        except asyncio.TimeoutError:
            pass
        if _TARGET_REACHED.is_set():
            continue
        for sport in SPORTS_LIST:
            pend = pending_by_sport.get(sport, [])
            candidates = [m for m in pend if not _is_pending(m)]
            if not candidates:
                continue
            ok_flags = await asyncio.gather(
                *(_promotion_volume_ok(client, m["ticker"]) for m in candidates))
            started = [m for m, ok in zip(candidates, ok_flags) if ok]
            dropped = [m for m, ok in zip(candidates, ok_flags) if not ok]
            have = {m["ticker"] for m in main_by_sport.setdefault(sport, [])}
            for m in started:
                if m["ticker"] not in have:
                    main_by_sport[sport].append(m)
            handled = {m["ticker"] for m in candidates}
            pending_by_sport[sport] = [m for m in pend if m["ticker"] not in handled]
            if started:
                print(f"  [promote {sport}] {len(started)} match(es) now live → active "
                      f"watchlist  ({v1._cst_now():%H:%M:%S} CST)")
            for m in dropped:
                print(f"  [promote {sport}] {m['ticker']} below MIN_VOLUME_USD="
                      f"${MIN_VOLUME_USD:,.0f} at start — dropped, not promoted")


async def _scrape_tennis_rankings(force: bool = False) -> None:
    """
    Run tennis/web/sofascore_rankings.py (cwd=tennis/) once at bot startup so
    tennis_rankings.csv is fresh before rank-dependent situations (A, B, the
    favorite-rebound rule) start using it.  Subprocess, bounded by
    SPORT_SCRAPE_TIMEOUT_S; fails open on any error/timeout/missing Playwright —
    the bot still starts and _eval_one_tennis falls back to whatever CSV is on disk.

    ``force=True`` bypasses the SPORT_RANK_MAX_AGE_H freshness skip (the main bot
    passes it when the CSV is not from today — user 07/13).
    """
    tennis_dir = _PT_ROOT / "sports" / "tennis"
    script = tennis_dir / "web" / "sofascore_rankings.py"
    if not script.exists():
        print(f"  [rank] scraper not found at {script} — skipping, using existing CSV",
              file=sys.stderr)
        return
    # Skip if the CSV is already fresh (updated within SPORT_RANK_MAX_AGE_H hours
    # of now, local time) — rankings barely change day-to-day and the scrape is slow.
    if not force and SPORT_RANK_MAX_AGE_H > 0:
        try:
            csv_path = _rankings_csv_path()
            if csv_path.exists():
                age_h = (time.time() - csv_path.stat().st_mtime) / 3600.0
                if age_h < SPORT_RANK_MAX_AGE_H:
                    updated = time.strftime("%Y-%m-%d %H:%M", time.localtime(csv_path.stat().st_mtime))
                    print(f"  [rank] tennis_rankings.csv fresh (updated {updated}, "
                          f"{age_h:.1f}h ago < {SPORT_RANK_MAX_AGE_H:.0f}h) — skipping scrape")
                    return
        except Exception as e:
            print(f"  [rank] freshness check failed ({e}) — scraping anyway", file=sys.stderr)
    print("  [rank] scraping tennis rankings (tennis/web/sofascore_rankings.py) …")
    t0 = time.time()
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "web/sofascore_rankings.py",
            cwd=str(tennis_dir),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=SPORT_SCRAPE_TIMEOUT_S)
        dt = time.time() - t0
        tail = (out or b"").decode("utf-8", errors="replace").strip().splitlines()[-5:]
        if proc.returncode == 0:
            print(f"  [rank] scrape OK in {dt:.0f}s: " + " | ".join(tail))
        else:
            print(f"  [rank] scrape exited {proc.returncode} in {dt:.0f}s: "
                  + " | ".join(tail), file=sys.stderr)
    except asyncio.TimeoutError:
        print(f"  [rank] scrape timed out after {SPORT_SCRAPE_TIMEOUT_S}s — "
              f"killing it, continuing with existing CSV", file=sys.stderr)
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
    except Exception as e:
        print(f"  [rank] scrape failed: {e} — continuing with existing CSV", file=sys.stderr)


async def run() -> None:
    _setup_logging()
    print(f"[SPORTSBOT] sports={SPORTS_LIST}  min_vol=${MIN_VOLUME_USD:,.0f}  "
          f"top_n={TOP_N_PER_SPORT}  contracts={SPORT_CONTRACTS}  "
          f"TP+{SPORT_TARGET_PCT:.0f}%  place_orders={SPORT_PLACE_ORDERS}  "
          f"poll={SPORT_POLL_S}s  rebuy={SPORT_REBUY}  DRY_RUN={v1.DRY_RUN}")
    c = KalshiClient()
    try:
        # ── portfolio profit-target baseline (checked every 30 min) ──────────
        try:
            starting_pv = await _portfolio_value(c)
        except Exception as e:
            print(f"[TARGET-PV] start value error: {e}")
            starting_pv = 0.0
        target_pv = (starting_pv * (1 + TARGET_PORTFOLIO_PCT / 100.0)
                     if (TARGET_PORTFOLIO_PCT > 0 and starting_pv > 0) else None)
        # BOT-bank loss floor: halt once the bank has dropped SPORT_LOSS_LIMIT_PCT
        # (i.e. PV is down that % of the bank from start; only 10% of it remains)
        _bank_stop_usd = SPORT_LOSS_LIMIT_USD * (SPORT_LOSS_LIMIT_PCT / 100.0)
        loss_floor_pv = (starting_pv - _bank_stop_usd
                         if (SPORT_LOSS_LIMIT_USD > 0 and starting_pv > 0) else None)
        print(f"[TARGET-PV] start PV ${starting_pv:.2f} (cash+positions)" + (
            f"  target ${target_pv:.2f} (+{TARGET_PORTFOLIO_PCT:.0f}%)"
            if target_pv else "  (TARGET_PORTFOLIO_PCT disabled)"))
        if loss_floor_pv is not None:
            print(f"[LOSS-LIMIT] BOT bank ${SPORT_LOSS_LIMIT_USD:.2f} → halt at "
                  f"{SPORT_LOSS_LIMIT_PCT:.0f}% drawn down (PV <= ${loss_floor_pv:.2f}, "
                  f"lose ${_bank_stop_usd:.2f}); check every {SPORT_LOSS_CHECK_S // 60}m")

        # ── 1) ALL live matches per sport with bid in band, sorted by volume ──
        by_sport: dict[str, list[ks.LiveMatch]] = {}
        for sport in SPORTS_LIST:
            try:
                matches = await _live_matches_in_band(c, sport)
            except Exception as e:
                print(f"  [{sport}] fetch error: {e}")
                matches = []
            by_sport[sport] = matches

        print(f"\n=== STEP 1: live matches per sport, vol >= ${MIN_VOLUME_USD:,.0f}, "
              f"bid {SPORT_BID_LO}-{SPORT_BID_HI}c, sorted by volume ===")
        for sport, matches in by_sport.items():
            print(f"  {sport}: {len(matches)}  "
                  f"{[(m['ticker'], round(m.get('usd_volume', 0))) for m in matches]}")

        # ── 1b) split by start time (CST): started → active watchlist used by all
        #         subsequent steps; not-started → pending (30-min promoter) ──────
        main_by_sport, pending_by_sport = _split_started(by_sport)
        n_main = sum(len(v) for v in main_by_sport.values())
        n_pend = sum(len(v) for v in pending_by_sport.values())
        print(f"\n=== STEP 1b: {n_main} started → active watchlist (refreshed every "
              f"{SPORT_MAIN_REFRESH_S // 60}m); {n_pend} not started → pending "
              f"(promoted every {SPORT_PENDING_REFRESH_S // 60}m) ===")
        for sport in SPORTS_LIST:
            pend = pending_by_sport.get(sport, [])
            if pend:
                print(f"  {sport} pending: {[m['ticker'] for m in pend]}")
        by_sport = main_by_sport      # subsequent steps use only the started matches

        # ── 2) scores for every ticker in parallel; print first per sport ───
        async def _scores(sport: str) -> tuple[str, list[dict]]:
            ms = by_sport.get(sport, [])
            scs = await asyncio.gather(
                *(ks.get_the_market_scores_kalshi(m["ticker"], client=c) for m in ms),
                return_exceptions=True,
            )
            return sport, [s for s in scs if not isinstance(s, Exception)]

        score_pairs = await asyncio.gather(*(_scores(s) for s in SPORTS_LIST))
        scores_by_sport: dict[str, list[dict]] = dict(score_pairs)

        print("\n=== STEP 2: first market score response per sport ===")
        for sport in SPORTS_LIST:
            scs = scores_by_sport.get(sport, [])
            print(f"\n--- {sport} (first of {len(scs)}) ---")
            if scs:
                print(json.dumps(scs[0], indent=2, default=str))
            else:
                print("  (no qualifying live markets)")

        # ── 2b) live game stats (play-by-play) for the top market per sport ──
        #         params come from step 1/2: {"ticker": ..., "sport": ...}
        print("\n=== STEP 2b: live game stats (pbp) per sport ===")
        for sport in SPORTS_LIST:
            ms = by_sport.get(sport, [])
            if not ms:
                print(f"  {sport}: (no qualifying live markets)")
                continue
            tk = ms[0]["ticker"]
            try:
                gs = await get_game_stats(tk, sport, client=c)
            except Exception as e:
                gs = {"error": str(e)}
            print(f"  {sport} {tk}: type={gs.get('milestone_type')} "
                  f"status={gs.get('status')} supported={gs.get('supported')} "
                  f"score={gs.get('score')}")

        # ── 2c) prediction inputs (parallel polling/trading happens in step 4) ─
        traded: set = set()
        dropped: set = set()                  # matches abandoned (leader bid > decided)
        combos = load_combinations() if _HAS_PREDICT else {}
        if _HAS_TENNIS_SCORES and SPORT_SCRAPE_RANKINGS and "tennis" in _SPORTS_SET:
            await _scrape_tennis_rankings()    # fresh rankings before rank-dependent situations
        shared = {"rankings": load_rankings_csv() if _HAS_TENNIS_SCORES else {},
                  "rank_tours": load_rank_tours() if _HAS_TENNIS_SCORES else {}}
        if _HAS_TENNIS_SCORES and not shared["rankings"]:
            print("\n  [rank] tennis_rankings.csv missing/empty — run "
                  "tennis/web/sofascore_rankings.py; ranks will show NA", file=sys.stderr)

        # ── 3) live YES bid prices per participant (top market per sport) ───
        print("\n=== STEP 3: live YES bid prices (top market per sport) ===")
        for sport in SPORTS_LIST:
            ms = by_sport.get(sport, [])
            if not ms:
                print(f"  {sport}: (no qualifying live markets)")
                continue
            tk = ms[0]["ticker"]
            try:
                bids = await ks.get_live_bid_prices(tk, client=c)
            except Exception as e:
                bids = {"error": str(e)}
            print(f"  {sport} {tk}: {bids}")

        # ── 4) PARALLEL polling: one watcher task per live match (all sports) ─
        if not _HAS_TENNIS_SCORES:
            print("[SPORTSBOT] tennis scoring unavailable — nothing to poll.")
            return
        print(f"\n=== PARALLEL POLLING every {SPORT_POLL_S}s across {SPORTS_LIST} "
              f"(concurrency {SPORT_MAX_CONCURRENCY}; Ctrl-C to stop) ===")
        # Placed orders are monitored by the TP-guardian via _FILLED_ORDERS,
        # independent of the main/pending lists — so a position keeps its TP sell
        # maintained even after its match drops out of the refreshed main list.
        asyncio.create_task(_tp_guardian(c, traded, shared))  # TP/stop-loss/reversal-flip; re-enable on close
        asyncio.create_task(_positions_logger(c))  # log open positions every 30 min
        asyncio.create_task(_pv_target_guard(c, starting_pv, target_pv, loss_floor_pv))  # profit-target / loss-limit halt
        asyncio.create_task(_main_refresh(c, by_sport, pending_by_sport, shared))  # 60-min main refresh
        asyncio.create_task(_pending_promoter(c, by_sport, pending_by_sport))      # 30-min promotion (re-checks volume)
        sem = asyncio.Semaphore(SPORT_MAX_CONCURRENCY)
        watchers: dict = {}
        while not _STOP.is_set():
            for tk, t in list(watchers.items()):            # drop finished watchers FIRST
                if t.done():                                # (so re-eligible matches re-spawn now)
                    watchers.pop(tk)
            if not _TARGET_REACHED.is_set():
                # spawn a watcher for every live ticker not already watched/traded
                for sport in SPORTS_LIST:
                    for m in by_sport.get(sport, []):
                        tk = m["ticker"]
                        if tk not in watchers and tk not in traded and tk not in dropped:
                            watchers[tk] = asyncio.create_task(_watch_ticker(
                                c, tk, shared, combos, traded, dropped, sem, by_sport,
                                who=m.get("yes_sub_title") or m.get("title")))
                print(f"  [watch] {sum(1 for t in watchers.values() if not t.done())} active "
                      f"watcher(s); traded={len(traded)}  ({v1._cst_now():%H:%M:%S} CST)")
            else:
                # target reached: no new buys — just let positions drain
                print(f"  [DRAIN] target reached — no new buys; "
                      f"{len(_FILLED_ORDERS)} session position(s) still open "
                      f"({v1._cst_now():%H:%M:%S} CST)")
            # wake to pick up promoted / re-eligible matches.
            try:
                await asyncio.wait_for(_STOP.wait(), timeout=SPORT_LIST_REFRESH_S)
            except asyncio.TimeoutError:
                pass
            if _STOP.is_set():
                break
        # halt requested (target reached + positions drained) — stop watcher tasks
        print("[SPORTSBOT] halt signalled — cancelling watchers.")
        for t in watchers.values():
            t.cancel()
    finally:
        await c.close()


class _Tee:
    """Write to several streams at once (console + log file)."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
                st.flush()
            except Exception:
                pass

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass


class _RotatingSportsLog:
    """
    File-like log that writes to ``kalshi_sports_YYYYMMDD.log`` in SPORT_LOG_DIR
    (default ``<customer folder>/logs``).  On startup any prior-date logs are
    moved to ``./archive``; on each write, if the calendar date has rolled over
    the current file is closed, archived, and a fresh dated file is opened.
    """
    _PREFIX = "kalshi_sports_"

    def __init__(self) -> None:
        self._dir = Path(os.getenv("SPORT_LOG_DIR", str(CUSTOMER_DIR / "logs")))
        self._dir.mkdir(parents=True, exist_ok=True)
        self._arch = self._dir / "archive"
        self._arch.mkdir(parents=True, exist_ok=True)
        self._archive_stale()
        self._date = datetime.now().strftime("%Y%m%d")
        self.path = self._dir / f"{self._PREFIX}{self._date}.log"
        self._fh = self.path.open("a", buffering=1, encoding="utf-8", errors="replace")

    def _archive_stale(self) -> None:
        today = datetime.now().strftime("%Y%m%d")
        for f in sorted(self._dir.glob(f"{self._PREFIX}*.log")):
            if f.stem[len(self._PREFIX):] != today:
                try:
                    shutil.move(str(f), str(self._arch / f.name))
                    sys.__stdout__.write(f"[LOG] archived stale log -> {f.name}\n")
                except Exception:
                    pass

    def _roll(self) -> None:
        today = datetime.now().strftime("%Y%m%d")
        if today == self._date:
            return
        try:
            self._fh.flush()
            self._fh.close()
            if self.path.exists():
                shutil.move(str(self.path), str(self._arch / self.path.name))
        except Exception:
            pass
        self._date = today
        self.path = self._dir / f"{self._PREFIX}{today}.log"
        self._fh = self.path.open("a", buffering=1, encoding="utf-8", errors="replace")
        self._fh.write(f"[LOG] date rolled - new log file: {self.path.name}\n")

    def write(self, data: str) -> None:
        self._roll()
        self._fh.write(data)

    def flush(self) -> None:
        try:
            self._fh.flush()
        except Exception:
            pass

    def isatty(self) -> bool:
        return False


def _setup_logging() -> None:
    """Tee stdout+stderr to kalshi_sports_YYYYMMDD.log (archived on day change)
    and the console. Idempotent."""
    if isinstance(sys.stdout, _Tee):
        return
    try:
        rot = _RotatingSportsLog()
    except Exception as e:
        print(f"[SPORTSBOT] could not open log: {e}", file=sys.stderr)
        return
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.stdout = _Tee(sys.__stdout__, rot)
    sys.stderr = _Tee(sys.__stderr__, rot)
    print(f"[SPORTSBOT] logging to {rot.path.name}  (archive on day change)  ({_now_cst()})")


def _now_cst() -> str:
    try:
        return v1._cst_now().strftime("%Y-%m-%d %H:%M:%S CST")
    except Exception:
        return ""


def main() -> None:
    _setup_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
