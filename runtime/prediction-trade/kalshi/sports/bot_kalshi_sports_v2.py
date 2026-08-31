#!/usr/bin/env python3
"""
bot_kalshi_sports_v2.py — BASEBALL-only live scalp bot (MLB/NPB/KBO).
=====================================================================
v2 of the Kalshi sports bot: same KalshiClient/credential flow, same
``kaslhi_sports.env`` config, but trades ONLY baseball and runs the dedicated
sabermetric scalp model in
``prediction-trade/sports/baseball/prediction_baseball_v1.py``:

  1. Discover LIVE baseball games with usd_volume >= MIN_VOLUME_USD (config)
     and a bid inside [SPORT_BID_LO, SPORT_BID_HI]c — one watcher per game.
  2. Per poll, build the live game state from Kalshi's own milestone
     live-data + play-by-play game_stats (baseball is a pbp-supported sport;
     a SofaScore scraper can be wired into _external_baseball_state later).
  3. predict_scalp(): live win-probability (inning/score/base-out RE24 normal
     model) vs the market's implied bid — a BUY needs >= BASEBALL_MIN_EDGE_C
     cents of model edge inside the BASEBALL_BID_LO-HI entry band.
  4. On BUY: buy YES at bid+bump, confirm the fill, and immediately rest the
     scalp exit — a TP sell at +BASEBALL_SCALP_PCT% (default 10%) over entry.
  5. A guardian maintains the TP sell, a stop-loss at entry-BASEBALL_STOP_LOSS_C
     and the hard price-band exits (ceiling/floor) on every baseball position.

Run:
    python bot_kalshi_sports_v2.py [customer]      # customer default "suma"
"""
from __future__ import annotations

import asyncio
import csv
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
sys.path.insert(0, str(_KALSHI_ROOT / "btc" / "btc15"))        # → `import bot_kalshi_btc15`
sys.path.insert(0, str(_PT_ROOT / "sports"))                    # → `import baseball`

# bot_kalshi_btc15 does `from btc import BtcVidyaMonitor`; that package lives at
# <repo-root>/indicators — alias it (same shim as bot_kalshi_sports_v1).
if "btc" not in sys.modules:
    _REPO_ROOT = _PT_ROOT.parent                                # .../38trades-py-claude
    sys.path.insert(0, str(_REPO_ROOT))
    import indicators as _btc_pkg                                # noqa: E402
    sys.modules["btc"] = _btc_pkg

# ── config + credentials: identical bootstrap to bot_kalshi_sports_v1 ─────────
# 1. Non-secret config (MIN_VOLUME_USD, SPORT_*/BASEBALL_* knobs), tracked in git.
for _name in ("kaslhi_sports.env", "kalshi_sports.env"):
    _p = _HERE / _name
    if _p.exists():
        load_dotenv(_p)
        break

# 2. Per-customer folder in the MAIN checkout (user rule 07/08) — sole source of
#    Kalshi credentials and destination for logs/ + trade_history/.
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
    print(f"[BASEBALL-BOT] WARNING: no .env found in {CUSTOMER_DIR} — "
          f"KALSHI_API_KEY_ID/KALSHI_PRIVATE_KEY/BASE_URI are unset, auth will fail.")

_pk = os.getenv("KALSHI_PRIVATE_KEY", "").strip()
if _pk and not Path(_pk).is_absolute() and (CUSTOMER_DIR / _pk).exists():
    os.environ["KALSHI_PRIVATE_KEY"] = str(CUSTOMER_DIR / _pk)
elif not _pk:
    _pems = sorted(CUSTOMER_DIR.glob("*.pem"))
    if _pems:
        os.environ["KALSHI_PRIVATE_KEY"] = str(_pems[0])

# 3. Import the shared clients WITHOUT letting bot_kalshi_btc15's bare
#    load_dotenv() touch the project root .env (same trick as v1).
_real_load_dotenv = dotenv.load_dotenv
dotenv.load_dotenv = lambda *a, **kw: False
try:
    import kalshi_sports as ks                    # noqa: E402  (KalshiClient + discovery)
    import bot_kalshi_btc15 as v1                 # noqa: E402  (order/position helpers)
finally:
    dotenv.load_dotenv = _real_load_dotenv

# Baseball scalp model — import AFTER kaslhi_sports.env is loaded (it reads its
# BASEBALL_* config from the environment at import time).
from baseball.prediction_baseball_v1 import (  # noqa: E402
    predict_scalp, format_analysis, scalp_tp_cents,
    CONF_ULTRA, SCALP_PCT, STOP_LOSS_C as BB_STOP_LOSS_C)
from baseball import baseball4cast_scraper as b4c  # noqa: E402  (4cast gate data)

KalshiClient = ks.KalshiClient

SPORT = "baseball"                                # v2 trades ONLY baseball
_SPORTS_SET = {SPORT}                             # guardian sell scope
MIN_VOLUME_USD = float(os.getenv("MIN_VOLUME_USD", "25000"))   # same key as config
TOP_N = int(os.getenv("TOP_N_PER_SPORT", "100"))

# ── order execution knobs (SPORT_* shared with v1; BASEBALL_* override) ───────
SPORT_CONTRACTS = int(os.getenv("BASEBALL_CONTRACTS", os.getenv("SPORT_CONTRACTS", "1")))
SPORT_ULTRA_MULT = float(os.getenv("SPORT_ULTRA_FAV_CONTRACTS_MULT", "1.5"))
SPORT_FILL_TIMEOUT_S = int(os.getenv("SPORT_FILL_TIMEOUT_S", str(15 * 60)))
SPORT_FILL_POLL_S = int(os.getenv("SPORT_FILL_POLL_S", "60"))
SPORT_PLACE_ORDERS = os.getenv("SPORT_PLACE_ORDERS", "TRUE").strip().upper() != "FALSE"
SPORT_MAX_TP_C = int(os.getenv("SPORT_MAX_TP_C", "98"))
BASEBALL_POLL_S = int(os.getenv("BASEBALL_POLL_S", "30"))       # in-play re-poll
SPORT_NOTSTARTED_POLL_S = int(os.getenv("SPORT_NOTSTARTED_POLL_S", "1800"))
SPORT_INSUFFICIENT_PAUSE_S = int(os.getenv("SPORT_INSUFFICIENT_PAUSE_S", "1800"))
SPORT_LIST_REFRESH_S = int(os.getenv("SPORT_LIST_REFRESH_S", "300"))
SPORT_MAIN_REFRESH_S = int(os.getenv("SPORT_MAIN_REFRESH_S", "3600"))
SPORT_PENDING_REFRESH_S = int(os.getenv("SPORT_PENDING_REFRESH_S", "1800"))
SPORT_MAX_CONCURRENCY = int(os.getenv("SPORT_MAX_CONCURRENCY", "12"))
SPORT_DECIDED_BID = int(os.getenv("SPORT_DECIDED_BID", "90"))
# baseball games run ~3h; extras/delays happen — default wider than tennis's 4h
SPORT_MAX_LIVE_HOURS = float(os.getenv("BASEBALL_MAX_LIVE_HOURS", "6"))
SPORT_BID_LO = int(os.getenv("SPORT_BID_LO", "25"))             # discovery band
SPORT_BID_HI = int(os.getenv("SPORT_BID_HI", "85"))
SPORT_POST_ORDER_DELAY_S = int(os.getenv("SPORT_POST_ORDER_DELAY_S", "10"))
SPORT_PRICE_BUMP_C = int(os.getenv("SPORT_PRICE_BUMP_C", "5"))  # BUY bump only
SPORT_REBUY = os.getenv("SPORT_REBUY", "TRUE").strip().upper() != "FALSE"
SPORT_LOG_EVERY_S = int(os.getenv("SPORT_LOG_EVERY_S", "120"))
SPORT_POS_LOG_S = int(os.getenv("SPORT_POS_LOG_S", "1800"))
SPORT_TP_GUARD_S = int(os.getenv("SPORT_TP_GUARD_S", "120"))
SPORT_GUARD_RECONFIRM_S = int(os.getenv("SPORT_GUARD_RECONFIRM_S", "30"))
# The scalp exit IS the strategy, so the TP sell is always placed — BASEBALL_SELL
# (not SPORT_SELL, which the tennis bot keeps FALSE) gates it here.
BASEBALL_SELL = os.getenv("BASEBALL_SELL", "TRUE").strip().upper() != "FALSE"
# Stop-loss (guardian): exit once the live bid sits BB_STOP_LOSS_C under entry for
# SPORT_STOP_CONFIRM cycles; a fall past SPORT_STOP_DEEP_C exits immediately.
SPORT_STOP_CONFIRM = int(os.getenv("SPORT_STOP_CONFIRM", "2"))
SPORT_STOP_MIN_BID_C = int(os.getenv("SPORT_STOP_MIN_BID_C", "4"))
SPORT_STOP_DEEP_C = int(os.getenv("SPORT_STOP_DEEP_C", "35"))
SPORT_STOP_SLIP_C = int(os.getenv("SPORT_STOP_SLIP_C", "3"))
# Absolute price-band exits (any baseball position, independent of entry)
SPORT_TP_CEILING_C = int(os.getenv("SPORT_TP_CEILING_C", "97"))
SPORT_SL_FLOOR_C = int(os.getenv("SPORT_SL_FLOOR_C", "9"))
# Never-sell-naked (user rule 07/12): every sell is preceded by this many
# position+resting-order confirmations, this many seconds apart.
SPORT_SELL_CONFIRMS = int(os.getenv("SPORT_SELL_CONFIRMS", "3"))
SPORT_SELL_CONFIRM_DELAY_S = float(os.getenv("SPORT_SELL_CONFIRM_DELAY_S", "5"))
# Score-flip exit (user rule 07/12): while HOLDING, if the bought team LOSES a
# lead and falls BEHIND (e.g. led 2-0, now trails 2-3) → cancel the resting TP
# and fire an exit sell for that market immediately.
BASEBALL_SCORE_FLIP_EXIT = os.getenv("BASEBALL_SCORE_FLIP_EXIT",
                                     "TRUE").strip().upper() != "FALSE"
# ticker -> (team_runs, opp_runs) of the best lead observed (or at entry)
_SEEN_LEAD: dict = {}
# Kalshi milestone statuses that mean NOT active → drop from the watchlist.
_KALSHI_DROP_STATUSES = {"interrupted", "suspended", "cancelled", "canceled",
                         "postponed", "abandoned", "delayed", "walkover", "wov"}

# ── portfolio profit-target / loss-limit halt (same keys as v1) ───────────────
TARGET_PORTFOLIO_PCT = float(os.getenv("TARGET_PORTFOLIO_PCT", "0"))
HALT_MACHINE_SHUTDOWN = v1.HALT_MACHINE_SHUTDOWN
SPORT_PV_CHECK_S = int(os.getenv("SPORT_PV_CHECK_S", "1800"))
SPORT_LOSS_LIMIT_USD = float(os.getenv("SPORT_LOSS_LIMIT_USD", "0"))
SPORT_LOSS_LIMIT_PCT = float(os.getenv("SPORT_LOSS_LIMIT_PCT", "90"))
SPORT_LOSS_CHECK_S = int(os.getenv("SPORT_LOSS_CHECK_S", "300"))
SPORT_DRAIN_POLL_S = int(os.getenv("SPORT_DRAIN_POLL_S", "60"))
SPORT_DRAIN_TIMEOUT_S = int(os.getenv("SPORT_DRAIN_TIMEOUT_S", "3600"))
_TARGET_REACHED = asyncio.Event()
_STOP = asyncio.Event()
_PAUSE_UNTIL = 0.0

# Structured trade history (one row per trade; the row is UPDATED in place on close).
SPORT_TRADE_CSV = os.getenv("BASEBALL_TRADE_CSV",
                            str(CUSTOMER_DIR / "trade_history" / "trade_history_baseball.csv"))
_TRADE_CSV_COLS = ["ts_epoch", "ts", "ticker", "team", "side", "situation",
                   "confidence", "reason", "inning", "half", "model_wp",
                   "signal_bid", "buy_price", "fill_price", "contracts",
                   "tp_price", "stop_price", "pv_entry", "status",
                   "ts_close", "pv_close", "realized_pnl", "pv_delta_pct"]

_FILLED_ORDERS: dict = {}   # ticker -> {contracts, side, buy_at, tp, stop, open_ts, ...}
_GAME_LABEL: dict = {}      # event ticker -> "League: Away at Home" (for logs)
_STOP_STRIKES: dict = {}    # ticker -> consecutive stop-loss breach cycles
_BAND_STRIKES: dict = {}    # ticker -> consecutive floor breach cycles
_LAST_LOG: dict = {}        # ticker -> last game-state log epoch


# ══════════════════════════════════════════════════════════════════════════════
#  Live baseball game state — Kalshi milestone live-data + pbp game_stats
# ══════════════════════════════════════════════════════════════════════════════
def _event_of(ticker: str) -> str:
    """Event ticker shared by both sides of a game (strip the side suffix)."""
    return ticker.rsplit("-", 1)[0] if ticker.count("-") >= 2 else ticker


def _name_match(a: str, b: str) -> bool:
    """Loose team-name match: containment either way, or shared last word
    ("Yankees" vs "New York Yankees")."""
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    return a.split()[-1] == b.split()[-1]


async def _team_markets(client: KalshiClient, ticker: str) -> dict:
    """
    {team_name: (market_ticker, "yes")} for the event of ``ticker`` — one entry
    per team that has its OWN market.  NEVER BUY NO (user rule 07/12): on a
    single binary market only the YES side's team is routable; the other team
    is simply not tradeable (no NO buys, ever).
    """
    event = _event_of(ticker)
    out: dict[str, tuple] = {}
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


def _pick(d: dict, *keys):
    """First non-None value among ``keys`` in dict ``d``."""
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def _half_from_text(txt) -> "str | None":
    """"top"/"bottom" from text or Kalshi's numeric inning_half (1=top, 2=bottom)."""
    if isinstance(txt, (int, float)):
        return {1: "top", 2: "bottom"}.get(int(txt))
    t = (txt or "").strip().lower()
    if t in ("1", "2"):
        return {"1": "top", "2": "bottom"}[t]
    if "top" in t:
        return "top"
    if "bottom" in t or "bot " in t:
        return "bottom"
    return None


def _bases_from_kalshi(v):
    """Kalshi live_data ``bases`` is a bool array ([1B, 2B, 3B, …]) — convert to
    the predictor's token set; pass through strings/lists of tokens unchanged."""
    if isinstance(v, (list, tuple)) and v and all(isinstance(b, bool) for b in v):
        return {tok for tok, occ in zip(("1B", "2B", "3B"), v) if occ}
    return v


def _parse_pbp(pbp: dict | None) -> dict:
    """Best-effort {home_runs, away_runs, inning, half, last_play} from Kalshi
    pbp periods (period == inning for baseball; scores are latest non-null)."""
    out: dict = {}
    if not pbp:
        return out
    periods = pbp.get("periods") or []
    if not periods:
        return out
    home = away = None
    last_play = None
    started = 0
    for p in periods:
        has_data = (p.get("home_score") is not None or p.get("away_score") is not None
                    or (p.get("events") or []))
        if has_data:
            started += 1
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
    if home is not None:
        out["home_runs"] = int(home)
    if away is not None:
        out["away_runs"] = int(away)
    if started:
        out["inning"] = started
        cur = periods[started - 1]
        # away batted (score set) but home's slot still null → likely the top half
        if cur.get("away_score") is not None and cur.get("home_score") is None:
            out["half"] = "top"
    if last_play:
        out["last_play"] = last_play
        out.setdefault("half", _half_from_text(last_play))
    return out


async def _external_baseball_state(title: str) -> "dict | None":
    """Hook for a SofaScore (or other) live-score scraper — return a dict with
    any of {home_runs, away_runs, inning, half, outs, bases} to merge over the
    Kalshi read.  Not wired yet; Kalshi milestone/pbp is the primary source."""
    return None


async def _baseball_state(client: KalshiClient, ticker: str) -> "dict | None":
    """
    Live game state for the game of ``ticker`` from Kalshi's own endpoints:
        /milestones?related_event_ticker={event}   → id, status, title, details
        /live_data/milestone/{id}                   → structured details (if any)
        /live_data/milestone/{id}/game_stats        → play-by-play (pbp)
    Returns {home, away, home_runs, away_runs, inning, half, outs, bases,
             status, title, start_date, last_play} — or None if no milestone.
    outs/bases are best-effort (None when Kalshi doesn't expose them); the
    predictor degrades gracefully without them.
    """
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
    mid = m0.get("id")
    det = m0.get("details") or {}
    title = m0.get("title", "")
    st: dict = {"title": title, "status": str(det.get("status") or "").lower(),
                "start_date": m0.get("start_date"),
                "home": None, "away": None, "home_runs": None, "away_runs": None,
                "inning": None, "half": None, "outs": None, "bases": None}

    # league label for logs
    league = det.get("league") or det.get("tournament_name")
    if league:
        _GAME_LABEL[event] = f"{league}: {title}" if title else str(league)

    # structured live-data details (field names vary by sport — probe common ones)
    ld_det: dict = {}
    if mid:
        try:
            ld = await client.req("GET", f"/live_data/milestone/{mid}")
            ld_det = ((ld or {}).get("live_data") or {}).get("details") or {}
        except Exception:
            ld_det = {}
    # confirmed live probe 07/12: a baseball_game milestone's live_data details
    # carry {home_points, away_points, inning, inning_half (1=top/2=bottom),
    # outs, balls, strikes, bases ([bool,…]), last_play, status, winner}.
    for src in (ld_det, det):
        if st["home_runs"] is None:
            hs = _pick(src, "home_points", "home_score", "home_runs",
                       "competitor1_overall_score")
            if hs is not None:
                st["home_runs"] = int(hs)
        if st["away_runs"] is None:
            as_ = _pick(src, "away_points", "away_score", "away_runs",
                        "competitor2_overall_score")
            if as_ is not None:
                st["away_runs"] = int(as_)
        if st["inning"] is None:
            inn = _pick(src, "inning", "current_inning", "period", "current_period")
            if inn is not None:
                try:
                    st["inning"] = int(inn)
                except (TypeError, ValueError):
                    pass
        if st["half"] is None:
            st["half"] = _half_from_text(_pick(src, "inning_half", "half",
                                               "period_half"))
        if st["outs"] is None:
            o = _pick(src, "outs", "current_outs")
            if o is not None:
                try:
                    st["outs"] = max(0, min(2, int(o)))
                except (TypeError, ValueError):
                    pass
        if st["bases"] is None:
            st["bases"] = _bases_from_kalshi(_pick(src, "bases", "runners",
                                                   "base_runners"))
        if src.get("last_play"):
            st.setdefault("last_play", src.get("last_play"))
        if src.get("winner"):                       # game decided → treat as settled
            st["status"] = "finished"
        elif not st["status"] and src.get("status"):
            st["status"] = str(src.get("status")).lower()

    # play-by-play fallback/refinement
    if mid and (st["home_runs"] is None or st["inning"] is None or st["half"] is None):
        try:
            gs = await client.req("GET", f"/live_data/milestone/{mid}/game_stats")
            pbp = gs.get("pbp") if isinstance(gs, dict) else None
        except Exception:
            pbp = None
        for k, v in _parse_pbp(pbp).items():
            if st.get(k) is None:
                st[k] = v

    # optional external scraper (SofaScore) overlay
    try:
        ext = await _external_baseball_state(title)
    except Exception:
        ext = None
    if ext:
        for k, v in ext.items():
            if v is not None:
                st[k] = v

    # team names: resolve HOME/AWAY from the milestone title matched against the
    # event's market participant names.  Kalshi baseball titles are AWAY-first
    # for BOTH separators — "Milwaukee vs Pittsburgh" is Away vs Home (confirmed
    # live 07/12: home_points tracked the second-listed team) — matching the US
    # "Away at Home" convention.
    participants = list(await _team_markets(client, ticker))
    t = title or ""
    pair = None
    for sep in (" at ", " @ ", " vs. ", " vs "):
        if sep in t:
            a, b = t.split(sep, 1)                            # a=away, b=home
            pair = (b, a)                                     # (home, away)
            break
    if pair:
        for nm in participants:
            if _name_match(nm, pair[0]):
                st["home"] = nm
            elif _name_match(nm, pair[1]):
                st["away"] = nm
    if (st["home"] is None or st["away"] is None) and len(participants) == 2:
        # Fall back to competitor ids if the title didn't resolve — otherwise
        # leave unresolved (the predictor will WAIT rather than guess sides).
        rest = [n for n in participants if n not in (st["home"], st["away"])]
        if st["home"] is not None and len(rest) == 1:
            st["away"] = rest[0]
        elif st["away"] is not None and len(rest) == 1:
            st["home"] = rest[0]
    return st


async def score_flip_check(client: KalshiClient, ticker: str) -> tuple:
    """
    Score-flip exit trigger (user rule 07/12) for a HELD market ``ticker``:
    the bought team previously LED the game (observed live, or leading at
    entry — seeded into ``_SEEN_LEAD``) and is NOW BEHIND on runs
    (e.g. 2-0 → 2-3).  Returns (fire: bool, why: str).  A lead observed on any
    call updates ``_SEEN_LEAD``; ties never fire; a team that was never seen
    leading never fires (that risk is the stop-loss's job).
    Shared by the v2 guardian and the main bot's baseball adapter exit_check.
    """
    try:
        tm = await _team_markets(client, ticker)
    except Exception:
        return False, ""
    held = next((nm for nm, (mkt, _s) in tm.items() if mkt == ticker), None)
    if not held:
        return False, ""
    st = await _baseball_state(client, ticker)
    if not st or st.get("home_runs") is None or st.get("away_runs") is None:
        return False, ""
    if _name_match(held, st.get("home") or ""):
        team, opp = int(st["home_runs"]), int(st["away_runs"])
    elif _name_match(held, st.get("away") or ""):
        team, opp = int(st["away_runs"]), int(st["home_runs"])
    else:
        return False, ""
    if team > opp:                                     # leading → remember it
        _SEEN_LEAD[ticker] = (team, opp)
        return False, ""
    if team < opp and ticker in _SEEN_LEAD:            # led before, behind now
        was = _SEEN_LEAD[ticker]
        led = (f"led {was[0]}-{was[1]}" if isinstance(was, tuple) else "led")
        return True, (f"score flip: {held} {led}, now trails {team}-{opp} "
                      f"({_fmt_state(st)})")
    return False, ""


def _fmt_state(st: dict) -> str:
    h = str(st.get("half") or "?").capitalize()
    return f"{h} {st.get('inning', '?')}"


async def _match_meta(c, ticker: str) -> tuple:
    """(age_hours, kalshi_status, start_ts) from the game's milestone."""
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
        league = det.get("league") or det.get("tournament_name")
        if league:
            _GAME_LABEL[event] = f"{league}: {m0.get('title', '')}"
        age = start_ts = None
        sd = m0.get("start_date")
        if sd:
            start = datetime.fromisoformat(str(sd).replace("Z", "+00:00"))
            start_ts = start.timestamp()
            age = (datetime.now(timezone.utc) - start).total_seconds() / 3600.0
        return age, status, start_ts
    except Exception:
        return None, "", None


# ══════════════════════════════════════════════════════════════════════════════
#  Discovery — live baseball games, volume floor from config, bid in band
# ══════════════════════════════════════════════════════════════════════════════
async def _live_games_in_band(c) -> list:
    """
    Live baseball games with usd_volume >= MIN_VOLUME_USD (STRICT) whose YES or
    NO bid is inside [SPORT_BID_LO, SPORT_BID_HI]c, volume-sorted, capped at
    TOP_N, then filtered by milestone status / staleness.
    """
    all_live = await ks.filter_by_sport_min_volume_live(SPORT, 0, top_n=10 ** 9, client=c)

    # FULL-GAME winner markets only (series KXMLBGAME / KXNPBGAME / KXLMBGAME …).
    # Baseball has heavy derivative series — KXMLBF5/F7/F3 "first N innings"
    # winners (which even carry a 3rd "Tie" side), KXMLBEXTRAS, totals — that a
    # 9-inning win-probability model must never trade; drop them at discovery.
    pre = len(all_live)
    all_live = [g for g in all_live
                if ks._series_of(g["ticker"]).upper().endswith("GAME")]
    if pre - len(all_live):
        print(f"  [{SPORT}] excluded {pre - len(all_live)} derivative market(s) "
              f"(F5/F3/extras/totals — full-game *GAME series only)")

    def in_band(m) -> bool:
        for b in (m.get("yes_bid"), m.get("no_bid")):
            if b is not None and SPORT_BID_LO <= b <= SPORT_BID_HI:
                return True
        return False

    kept, low_vol = [], 0
    for m in all_live:
        if not in_band(m):
            continue
        if float(m.get("usd_volume", 0.0)) < MIN_VOLUME_USD:
            low_vol += 1
            continue
        kept.append(m)
    if low_vol:
        print(f"  [{SPORT}] excluded {low_vol} game(s) below MIN_VOLUME_USD=${MIN_VOLUME_USD:,.0f}")
    kept.sort(key=lambda m: m.get("usd_volume", 0.0), reverse=True)
    kept = kept[:TOP_N]

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
        m["start_ts"] = start_ts
        fresh.append(m)
    return fresh


def _is_pending(m: dict) -> bool:
    ts = m.get("start_ts")
    return ts is not None and ts > time.time()


# ══════════════════════════════════════════════════════════════════════════════
#  Trade execution — buy, confirm fill, rest the +SCALP_PCT% exit
# ══════════════════════════════════════════════════════════════════════════════
async def _match_exposure(client, market_ticker: str) -> tuple:
    """(open_contracts, resting_orders) summed over the whole GAME (event)."""
    event = _event_of(market_ticker)
    pos_contracts = 0
    pd = await client.req("GET", "/portfolio/positions", params={"limit": 1000})
    for p in pd.get("market_positions", []):
        if _event_of(p.get("ticker", "")) == event:
            pos_contracts += abs(int(float(p.get("position_fp", "0"))))
    rest = await v1.resting_orders(client)
    rest_n = sum(1 for o in rest if _event_of(o.get("ticker", "")) == event)
    return pos_contracts, rest_n


async def _confirm_open_position(client, ticker: str, *, expect_side=None,
                                 require_no_resting: bool = True,
                                 tag: str = "SELLCHECK") -> tuple:
    """
    NEVER-sell-naked rule (user 07/12): before ANY sell order, confirm an open
    position exists on this EXACT market SPORT_SELL_CONFIRMS times (default 3),
    SPORT_SELL_CONFIRM_DELAY_S (5s) apart, re-fetching BOTH the position and
    the market's resting orders every round.  Any round showing no position,
    a side mismatch, or (when ``require_no_resting``) an existing resting order
    cancels the sell — returns (0, None, None).  Success returns
    (contracts, side, position_dict) from the last read.
    """
    have, side, pos = 0, None, None
    n = max(1, SPORT_SELL_CONFIRMS)
    for i in range(n):
        if i:
            await asyncio.sleep(SPORT_SELL_CONFIRM_DELAY_S)
        try:
            pos = await v1.position_for(client, ticker)
            rest = await v1.resting_orders(client, ticker)
        except Exception as e:
            print(f"  [{tag}] {ticker} sell-confirm {i + 1}/{n} fetch failed: {e} "
                  f"— NO sell placed", file=sys.stderr)
            return 0, None, None
        have = pos["contracts"] if pos else 0
        side = (("yes" if float((pos or {}).get("position_fp", "0")) >= 0 else "no")
                if pos else None)
        if have <= 0:
            print(f"  [{tag}] {ticker} sell-confirm {i + 1}/{n}: NO open position "
                  f"— NO sell placed")
            return 0, None, None
        if expect_side is not None and side != expect_side:
            print(f"  [{tag}] {ticker} sell-confirm {i + 1}/{n}: side {side!r} != "
                  f"expected {expect_side!r} — NO sell placed")
            return 0, None, None
        if require_no_resting and rest:
            print(f"  [{tag}] {ticker} sell-confirm {i + 1}/{n}: {len(rest)} resting "
                  f"order(s) already on this market — NO new sell")
            return 0, None, None
        print(f"  [{tag}] {ticker} sell-confirm {i + 1}/{n}: holding {have} {side} OK")
    return have, side, pos


async def _await_fill(client, ticker, want, timeout_s) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        pos = await v1.position_for(client, ticker)
        have = pos["contracts"] if pos else 0
        print(f"    [FILL] {ticker} contracts {have}/{want}")
        if have >= want:
            return True
        await asyncio.sleep(SPORT_FILL_POLL_S)
    return False


async def _portfolio_value(client) -> float:
    d = await client.req("GET", "/portfolio/balance")
    return (float(d.get("balance", 0)) + float(d.get("portfolio_value", 0))) / 100.0


def _trade_log(row: dict) -> None:
    """Append the BUY row (the close later UPDATES this same row)."""
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
    """Update the row created at BUY (keyed by ticker+ts_epoch) with close/P&L."""
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
        if (r.get("ticker") == ticker and r.get("ts_epoch") == target_key
                and r.get("status") == "OPEN"):
            r.update({k: str(v) if v != "" else "" for k, v in updates.items()})
            r["status"] = "CLOSED"
            found = True
            break
    if not found:
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


async def _pnl_from_fills(client, ticker: str, side: str, since_ts: float = 0.0) -> float:
    """Realized P&L (USD) from fills since ``since_ts`` — priced on the token we
    actually HELD (yes_price for yes positions, no_price for no positions; a
    fill's own 'side' field reflects order matching, not our holding — v1 bug)."""
    try:
        d = await client.req("GET", "/portfolio/fills",
                             params={"ticker": ticker, "limit": 1000})
    except Exception:
        return 0.0
    key = "yes_price_dollars" if side == "yes" else "no_price_dollars"
    pnl = 0.0
    for fx in d.get("fills", []):
        if ticker not in (fx.get("ticker"), fx.get("market_ticker")):
            continue
        if since_ts and float(fx.get("ts") or 0) < since_ts - 5:
            continue
        cnt = float(fx.get("count_fp") or 0)
        px = float(fx.get(key) or 0)
        fee = float(fx.get("fee_cost") or 0)
        pnl += (cnt * px - fee) if fx.get("action") == "sell" else -(cnt * px + fee)
    return round(pnl, 2)


async def _settlement_revenue(client, ticker: str) -> float:
    try:
        d = await client.req("GET", "/portfolio/settlements",
                             params={"ticker": ticker, "limit": 50})
    except Exception:
        return 0.0
    rev = 0.0
    for s in d.get("settlements", []):
        if ticker in (s.get("ticker"), s.get("event_ticker")):
            rev += float(s.get("revenue") or 0) / 100.0
    return round(rev, 2)


async def _realized_pnl(client, ticker: str, side: str, since_ts: float = 0.0) -> float:
    return round(await _pnl_from_fills(client, ticker, side, since_ts)
                 + await _settlement_revenue(client, ticker), 2)


async def execute_scalp_trade(client, market_ticker: str, side: str, team: str,
                              sig: dict, *, contracts: int) -> None:
    """
    BUY ``side`` on ``market_ticker`` at the signal bid + bump, confirm the fill,
    then rest the scalp exit: a TP sell at sig['tp_price'] (+SCALP_PCT% net).
    Never stacks — skips if the GAME already has a position or resting order.
    """
    global _PAUSE_UNTIL
    if _TARGET_REACHED.is_set():
        print(f"  [TRADE] {market_ticker}: profit target reached — not opening new buys")
        return
    if time.time() < _PAUSE_UNTIL:
        return
    # NEVER BUY NO (user rule 07/12): only YES-side entries, ever.
    if side != "yes":
        print(f"  [TRADE] {market_ticker}: side={side!r} — NEVER BUY NO "
              f"(user rule 07/12); buy refused")
        return
    try:
        pos_n, rest_n = await _match_exposure(client, market_ticker)
    except Exception as e:
        print(f"  [TRADE] {market_ticker}: position/order check failed ({e}); skip")
        return
    if pos_n > 0 or rest_n > 0:
        print(f"  [TRADE] {market_ticker}: game already has position={pos_n}, "
              f"resting={rest_n} — skip until flat")
        return

    buy_cents = int(sig["bid"])
    buy_px = min(99, buy_cents + SPORT_PRICE_BUMP_C)
    tp = int(sig.get("tp_price") or scalp_tp_cents(buy_cents))
    stop = int(sig.get("stop_price") or max(1, buy_cents - BB_STOP_LOSS_C))
    print(f"  [TRADE] BUY {team} {side.upper()} x{contracts} @ {buy_px}c "
          f"(signal {buy_cents}c +{SPORT_PRICE_BUMP_C}) on {market_ticker} "
          f"(scalp TP {tp}c / stop {stop}c)")
    # accounting fix (07/16 forensics): stamp open_ts BEFORE placement so buy
    # fills land inside _realized_pnl's since_ts window (the old post-fill
    # stamp dropped every buy's cost basis — phantom profit in the CSV).
    open_ts = time.time()
    r = await v1.place_buy(client, market_ticker, side,
                           buy_at_cents=buy_px, contracts=contracts)
    if r is None:
        need = contracts * buy_px / 100.0
        try:
            cash = await v1.portfolio_balance(client)
        except Exception:
            cash = None
        if cash is not None and cash < need:
            _PAUSE_UNTIL = time.time() + SPORT_INSUFFICIENT_PAUSE_S
            print(f"  [TRADE] insufficient balance (cash ${cash:.2f} < need ${need:.2f}) — "
                  f"pausing new buys for {SPORT_INSUFFICIENT_PAUSE_S // 60} min")
        else:
            print(f"  [TRADE] buy order failed for {market_ticker}")
        return

    if v1.DRY_RUN:
        print(f"  [DRY][TRADE] order placed; would confirm {contracts} filled and "
              f"rest the scalp TP @ {tp}c (+{SCALP_PCT:.0f}%).")
        return

    print(f"  [TRADE] order placed — waiting {SPORT_POST_ORDER_DELAY_S}s …")
    await asyncio.sleep(SPORT_POST_ORDER_DELAY_S)

    if not await _await_fill(client, market_ticker, contracts, SPORT_FILL_TIMEOUT_S):
        print(f"  [TRADE] not filled in {SPORT_FILL_TIMEOUT_S}s — cancelling this order")
        try:
            for o in await v1.resting_orders(client, market_ticker):
                await client.req("DELETE", f"/portfolio/events/orders/{o['order_id']}")
        except Exception as e:
            print(f"  [TRADE] cancel failed: {e}")
        return
    print(f"  [TRADE] filled {contracts} contracts on {market_ticker}")

    try:
        fill_price = (round(float(r.get("average_fill_price")) * 100)
                      if r.get("average_fill_price") else "")
    except Exception:
        fill_price = ""
    try:
        pv_entry = round(await _portfolio_value(client), 2)
    except Exception:
        pv_entry = ""
    # (open_ts stamped BEFORE placement — accounting fix, see above)
    _FILLED_ORDERS[market_ticker] = {
        "contracts": contracts, "side": side, "buy_at": buy_px, "tp": tp,
        "stop": stop, "team": team, "situation": sig.get("situation", ""),
        "confidence": sig.get("confidence", ""), "signal_bid": buy_cents,
        "pv_entry": pv_entry, "open_ts": open_ts}
    if sig.get("lead", 0) > 0:            # bought a leading team → seed the
        _SEEN_LEAD[market_ticker] = (      # score-flip exit's "was ahead" state
            tuple(sig["score_tuple"]) if sig.get("score_tuple") else True)
    _trade_log({"ts_epoch": open_ts, "ts": _now_cst(), "ticker": market_ticker,
                "team": team, "side": side, "situation": sig.get("situation", ""),
                "confidence": sig.get("confidence", ""), "reason": sig.get("reason", ""),
                "inning": sig.get("inning", ""), "half": sig.get("half", ""),
                "model_wp": sig.get("model_wp", ""), "signal_bid": buy_cents,
                "buy_price": buy_px, "fill_price": fill_price, "contracts": contracts,
                "tp_price": tp, "stop_price": stop, "pv_entry": pv_entry,
                "status": "OPEN"})

    if not BASEBALL_SELL:
        print(f"  [TRADE] BASEBALL_SELL=FALSE — holding {contracts} (no scalp TP)")
    else:
        if tp > SPORT_MAX_TP_C:
            print(f"  [TRADE] TP {tp}c > {SPORT_MAX_TP_C}c — clamped")
            tp = SPORT_MAX_TP_C
            _FILLED_ORDERS[market_ticker]["tp"] = tp
        # never-sell-naked: triple-confirm the position (5s apart) even right
        # after a confirmed fill, before the TP sell goes out.
        have_c, _s, _p = await _confirm_open_position(client, market_ticker,
                                                      expect_side=side,
                                                      require_no_resting=True,
                                                      tag="TRADE")
        if have_c <= 0:
            print(f"  [TRADE] TP not placed — position not confirmed; "
                  f"guardian will handle it")
        else:
            await v1.place_tp_sell(client, market_ticker, side, have_c, tp)
            print(f"  [TRADE] scalp TP sell @ {tp}c resting (+{SCALP_PCT:.0f}% target); "
                  f"guardian maintains it.")


# ══════════════════════════════════════════════════════════════════════════════
#  Guardian — TP maintenance, stop-loss, hard price-band exits (baseball only)
# ══════════════════════════════════════════════════════════════════════════════
def _tp_for(have: int, info: dict, pos: dict) -> int:
    """TP price for a held position: recorded TP, else +SCALP_PCT% over the
    recorded entry, else over the position's actual cost basis."""
    if info.get("tp"):
        return int(info["tp"])
    buy_at = info.get("buy_at")
    if not buy_at:
        cost = float(pos.get("total_traded_dollars")
                     or pos.get("market_exposure_dollars") or 0)
        buy_at = round(cost / have * 100) if have else 0
    return scalp_tp_cents(int(buy_at)) if buy_at else 0


async def _cancel_game_orders(client, ticker: str) -> None:
    event = _event_of(ticker)
    for o in await v1.resting_orders(client):
        if _event_of(o.get("ticker", "")) == event:
            await client.req("DELETE", f"/portfolio/events/orders/{o['order_id']}")


async def _tp_guardian(client, traded: set) -> None:
    """
    Every SPORT_TP_GUARD_S over ALL open baseball positions:
      • close-detection: session position gone → record P&L in the trade CSV,
        re-arm the game for another entry when SPORT_REBUY=TRUE;
      • hard band exits: bid >= SPORT_TP_CEILING_C (immediate) or bid <=
        SPORT_SL_FLOOR_C (SPORT_STOP_CONFIRM cycles) → exit;
      • stop-loss: bid <= entry - BB_STOP_LOSS_C for SPORT_STOP_CONFIRM cycles
        (immediately past entry - SPORT_STOP_DEEP_C) → exit crossing the bid;
      • TP maintenance: any baseball position without a resting sell gets its
        +SCALP_PCT% TP re-placed (double-confirmed against live positions).
    Only ever sells baseball positions (series taxonomy check) — never another
    category; taxonomy fetch failure = no sells that cycle (fail safe).
    """
    while True:
        await asyncio.sleep(SPORT_TP_GUARD_S)
        try:
            pd = await client.req("GET", "/portfolio/positions", params={"limit": 1000})
            positions = [p for p in pd.get("market_positions", [])
                         if abs(int(float(p.get("position_fp", "0")))) > 0]
            resting = await v1.resting_orders(client)
        except Exception as e:
            print(f"  [GUARD] fetch failed: {e}", file=sys.stderr)
            continue
        resting_tickers = {o.get("ticker") for o in resting}
        open_tickers = {p.get("ticker") for p in positions}

        # ── close detection: update the CSV row, re-arm the game if allowed ──
        for tk in list(_FILLED_ORDERS):
            if tk not in open_tickers:
                info = _FILLED_ORDERS.pop(tk, None) or {}
                _STOP_STRIKES.pop(tk, None)
                _BAND_STRIKES.pop(tk, None)
                _SEEN_LEAD.pop(tk, None)
                ev = _event_of(tk)
                if SPORT_REBUY:
                    for d in [x for x in traded if _event_of(x) == ev]:
                        traded.discard(d)
                try:
                    pnl = await _realized_pnl(client, tk, info.get("side", "yes"),
                                              info.get("open_ts", 0))
                    pv_close = round(await _portfolio_value(client), 2)
                    pve = info.get("pv_entry")
                    pct = (round((pv_close - pve) / pve * 100, 2)
                           if isinstance(pve, (int, float)) and pve else "")
                    _trade_log_close(tk, info.get("open_ts", ""), {
                        "ts_close": _now_cst(), "pv_close": pv_close,
                        "realized_pnl": pnl, "pv_delta_pct": pct})
                except Exception as e:
                    print(f"  [TRADECSV] close record failed: {e}", file=sys.stderr)
                print(f"  [GUARD] {tk} position closed — "
                      + ("game re-eligible" if SPORT_REBUY
                         else "SPORT_REBUY=FALSE, game stays done (max 1 trade)"))

        # sell scope: baseball only (never touch another category)
        try:
            smap = await ks._sports_series(client)
        except Exception as e:
            print(f"  [GUARD] sports taxonomy fetch failed: {e} — no sells this cycle",
                  file=sys.stderr)
            continue

        def _in_scope(tk: str) -> bool:
            return str(smap.get(ks._series_of(tk), {}).get("sport", "")).lower() in _SPORTS_SET

        stopped: set = set()

        # ── hard price-band exits ────────────────────────────────────────────
        if SPORT_TP_CEILING_C > 0 or SPORT_SL_FLOOR_C > 0:
            for p in positions:
                tk = p.get("ticker", "")
                if not _in_scope(tk):
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
                    _BAND_STRIKES.pop(tk, None)
                    continue
                if hit_sl and not hit_tp:
                    strikes = _BAND_STRIKES.get(tk, 0) + 1
                    _BAND_STRIKES[tk] = strikes
                    if strikes < SPORT_STOP_CONFIRM:
                        print(f"  [BANDEXIT] {tk} bid {bid_c}c <= {SPORT_SL_FLOOR_C}c floor "
                              f"— breach {strikes}/{SPORT_STOP_CONFIRM}, watching")
                        continue
                # never-sell-naked: triple-confirm (5s apart) before exiting;
                # resting TPs are replaced, so they don't block confirmation.
                have2, _s2, _p2 = await _confirm_open_position(
                    client, tk, expect_side=side, require_no_resting=False,
                    tag="BANDEXIT")
                if have2 <= 0:
                    continue
                try:
                    await _cancel_game_orders(client, tk)
                except Exception as e:
                    print(f"  [BANDEXIT] {tk} cancel game orders failed: {e}", file=sys.stderr)
                kind = (f"take-profit ceiling {SPORT_TP_CEILING_C}c" if hit_tp
                        else f"stop floor {SPORT_SL_FLOOR_C}c")
                exit_px = max(1, bid_c - SPORT_STOP_SLIP_C)
                print(f"  [BANDEXIT] {tk} bid {bid_c}c hit {kind} — exiting {have2} "
                      f"{side} @ {exit_px}c")
                try:
                    await v1.place_tp_sell(client, tk, side, have2, exit_px)
                    stopped.add(tk)
                    _BAND_STRIKES.pop(tk, None)
                except Exception as e:
                    print(f"  [BANDEXIT] {tk} exit sell failed: {e}", file=sys.stderr)

        # ── stop-loss (entry-relative) ───────────────────────────────────────
        if BB_STOP_LOSS_C > 0:
            for p in positions:
                tk = p.get("ticker", "")
                if tk in stopped or not _in_scope(tk):
                    continue
                have = abs(int(float(p.get("position_fp", "0"))))
                if have <= 0:
                    continue
                info = _FILLED_ORDERS.get(tk, {})
                entry = info.get("buy_at")
                if not entry:
                    cost = float(p.get("total_traded_dollars")
                                 or p.get("market_exposure_dollars") or 0)
                    entry = round(cost / have * 100) if have else 0
                if not entry:
                    continue
                side = "yes" if float(p.get("position_fp", "0")) >= 0 else "no"
                try:
                    bid = await v1._bid_price(client, tk, side)
                except Exception:
                    bid = None
                bid_c = round(bid * 100) if bid is not None else None
                trigger = entry - BB_STOP_LOSS_C
                deep = entry - SPORT_STOP_DEEP_C
                if bid_c is None or bid_c < SPORT_STOP_MIN_BID_C:
                    continue                                   # empty book ≠ collapse
                if bid_c > trigger:
                    _STOP_STRIKES.pop(tk, None)
                    continue
                strikes = _STOP_STRIKES.get(tk, 0) + 1
                _STOP_STRIKES[tk] = strikes
                need = 1 if bid_c <= deep else SPORT_STOP_CONFIRM
                if strikes < need:
                    print(f"  [STOPLOSS] {tk} bid {bid_c}c <= {trigger}c — breach "
                          f"{strikes}/{need}, watching")
                    continue
                # never-sell-naked: triple-confirm (5s apart) before exiting.
                have2, _s2, _p2 = await _confirm_open_position(
                    client, tk, expect_side=side, require_no_resting=False,
                    tag="STOPLOSS")
                if have2 <= 0:
                    continue
                try:
                    await _cancel_game_orders(client, tk)
                except Exception as e:
                    print(f"  [STOPLOSS] {tk} cancel game orders failed: {e}", file=sys.stderr)
                exit_px = max(1, bid_c - SPORT_STOP_SLIP_C)
                print(f"  [STOPLOSS] {tk} bid {bid_c}c <= entry {entry}c - "
                      f"{BB_STOP_LOSS_C}c ({trigger}c) x{strikes} — exiting {have2} "
                      f"{side} @ {exit_px}c")
                try:
                    await v1.place_tp_sell(client, tk, side, have2, exit_px)
                    stopped.add(tk)
                except Exception as e:
                    print(f"  [STOPLOSS] {tk} exit sell failed: {e}", file=sys.stderr)

        # ── SCORE-FLIP exit (user rule 07/12): bought team led, now trails ───
        # e.g. we bought them up 2-0 and it's now 2-3 → cancel the resting TP
        # and fire an exit sell for this market (score is durable — no strikes).
        if BASEBALL_SCORE_FLIP_EXIT:
            for p in positions:
                tk = p.get("ticker", "")
                if tk in stopped or not _in_scope(tk):
                    continue
                have = abs(int(float(p.get("position_fp", "0"))))
                if have <= 0:
                    continue
                side = "yes" if float(p.get("position_fp", "0")) >= 0 else "no"
                try:
                    fire, why = await score_flip_check(client, tk)
                except Exception as e:
                    print(f"  [SCOREFLIP] {tk} check failed: {e}", file=sys.stderr)
                    continue
                if not fire:
                    continue
                try:
                    bid = await v1._bid_price(client, tk, side)
                except Exception:
                    bid = None
                bid_c = round(bid * 100) if bid is not None else None
                if bid_c is None or bid_c < SPORT_STOP_MIN_BID_C:
                    continue                       # no sane quote to exit into
                # never-sell-naked: triple-confirm (5s apart) before exiting.
                have2, _s2, _p2 = await _confirm_open_position(
                    client, tk, expect_side=side, require_no_resting=False,
                    tag="SCOREFLIP")
                if have2 <= 0:
                    continue
                try:
                    await _cancel_game_orders(client, tk)
                except Exception as e:
                    print(f"  [SCOREFLIP] {tk} cancel game orders failed: {e}",
                          file=sys.stderr)
                exit_px = max(1, bid_c - SPORT_STOP_SLIP_C)
                print(f"  [SCOREFLIP] {tk} {why} — exiting {have2} {side} "
                      f"@ {exit_px}c (even at a loss)")
                try:
                    await v1.place_tp_sell(client, tk, side, have2, exit_px)
                    stopped.add(tk)
                    _SEEN_LEAD.pop(tk, None)
                except Exception as e:
                    print(f"  [SCOREFLIP] {tk} exit sell failed: {e}", file=sys.stderr)

        # ── TP maintenance (the scalp exit must always be resting) ──────────
        if not BASEBALL_SELL:
            continue
        candidates = []
        for p in positions:
            tk = p.get("ticker", "")
            if tk in resting_tickers or tk in stopped:
                continue
            if not _in_scope(tk):
                continue
            candidates.append(p)
        if not candidates:
            continue
        for c_ in candidates:
            tk = c_.get("ticker", "")
            # never-sell-naked (user 07/12): triple-confirm the position AND the
            # absence of any resting order (5s apart) before placing the TP.
            have, side, pos_now = await _confirm_open_position(
                client, tk, require_no_resting=True, tag="GUARD")
            if have <= 0:
                continue
            tp = _tp_for(have, _FILLED_ORDERS.get(tk, {}), pos_now)
            if not tp:
                print(f"  [GUARD] {tk} holding {have} {side} but no TP derivable — skip",
                      file=sys.stderr)
                continue
            if tp > SPORT_MAX_TP_C:
                print(f"  [GUARD] {tk} TP {tp}c > {SPORT_MAX_TP_C}c — clamped")
                tp = SPORT_MAX_TP_C
            print(f"  [GUARD] {tk} holding {have} {side} (reconfirmed), no resting "
                  f"sell — placing scalp TP @ {tp}c")
            try:
                await v1.place_tp_sell(client, tk, side, have, tp)
                _FILLED_ORDERS.setdefault(tk, {"contracts": have, "side": side,
                                               "buy_at": None, "tp": tp})
            except Exception as e:
                print(f"  [GUARD] {tk} place TP failed: {e}", file=sys.stderr)


async def _positions_logger(client) -> None:
    """Every SPORT_POS_LOG_S log open positions with cost basis + planned TP."""
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
            return
        except asyncio.TimeoutError:
            pass


async def _pv_target_guard(client, starting_pv: float, target_pv,
                           loss_floor_pv=None) -> None:
    """Profit-target / BOT-bank loss-limit halt (same two-phase flow as v1)."""
    if not target_pv and loss_floor_pv is None:
        return
    check_s = SPORT_LOSS_CHECK_S if loss_floor_pv is not None else SPORT_PV_CHECK_S
    while not _TARGET_REACHED.is_set():
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=check_s)
            return
        except asyncio.TimeoutError:
            pass
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
            print(f"  [TARGET-PV] profit target reached (PV ${pv:.2f} >= ${target_pv:.2f}) "
                  f"— stopping new buys; draining {len(_FILLED_ORDERS)} open position(s).")
            _TARGET_REACHED.set()
        elif loss_floor_pv is not None and pv <= loss_floor_pv:
            lost = starting_pv - pv
            print(f"  [LOSS-LIMIT] BOT bank down (lost ${lost:.2f}; PV ${pv:.2f} <= "
                  f"floor ${loss_floor_pv:.2f}) — stopping new buys, draining, halting.")
            _TARGET_REACHED.set()

    waited = 0
    while _FILLED_ORDERS:
        print(f"  [DRAIN] waiting for {len(_FILLED_ORDERS)} session position(s) to "
              f"close: {sorted(_FILLED_ORDERS)}  ({_now_cst()})")
        await asyncio.sleep(SPORT_DRAIN_POLL_S)
        waited += SPORT_DRAIN_POLL_S
        if SPORT_DRAIN_TIMEOUT_S and waited >= SPORT_DRAIN_TIMEOUT_S:
            print(f"  [DRAIN] timeout after {waited}s — halting anyway.")
            break
    print(f"  [BASEBALL TARGET-PV HALT] halting"
          f"{' + machine shutdown' if HALT_MACHINE_SHUTDOWN else ''}.")
    if HALT_MACHINE_SHUTDOWN:
        print("  [BASEBALL TARGET-PV HALT] initiating machine shutdown in 30s …")
        os.system("shutdown /s /f /t 30")
    _STOP.set()


# ══════════════════════════════════════════════════════════════════════════════
#  Evaluation + watchers
# ══════════════════════════════════════════════════════════════════════════════
async def _original_odds(client, ticker: str, match_start) -> dict:
    """Pre-game YES cents per team: hourly candle CLOSE just before start (None
    when a market has no candle history — never faked from the live price)."""
    event = _event_of(ticker)
    start_ts = None
    if match_start:
        try:
            start_ts = int(datetime.fromisoformat(
                str(match_start).replace("Z", "+00:00")).timestamp())
        except Exception:
            start_ts = None
    original: dict = {}
    try:
        ed = await client.req("GET", f"/events/{event}",
                              params={"with_nested_markets": "true"})
        markets = (ed.get("event", {}) or {}).get("markets") or []
    except Exception:
        return original
    now = int(time.time())
    for mk in markets:
        mt = mk.get("ticker", "")
        name = mk.get("yes_sub_title") or mk.get("title", "")
        if not name:
            continue
        op = None
        try:
            d = await client.req(
                "GET", f"/series/{mt.split('-', 1)[0]}/markets/{mt}/candlesticks",
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
        original[name] = ks._cents(op) if op not in (None, "") else None
    return original


async def _eval_one_game(c, tk) -> "dict | None":
    """Evaluate one game: Kalshi state + live/original odds → predict_scalp.
    Returns the signal dict ({not_started: True} before first pitch)."""
    try:
        st = await _baseball_state(c, tk)
    except Exception as e:
        print(f"  {tk}: state error: {e}")
        return None
    if st is None:
        return None
    if st.get("home_runs") is None and st.get("inning") is None:
        return {"action": "WAIT", "not_started": True, "ticker": tk}
    try:
        live = await ks.get_live_bid_prices(tk, client=c)
    except Exception:
        live = {}
    try:
        orig = await _original_odds(c, tk, st.get("start_date"))
    except Exception:
        orig = {}
    sig = predict_scalp(st, live, orig, ticker=tk)
    sig["inning"], sig["half"] = st.get("inning", ""), st.get("half", "")

    label = _GAME_LABEL.get(_event_of(tk))
    prefix = f"[{label}] " if label else ""
    fmt = lambda dct: "; ".join(f"{n.split()[-1]}:{dct.get(n)}" for n in dct)
    line = (f"{prefix}{sig.get('score', '')} >>> live:{{{fmt(live)}}} "
            f"Original:{{{fmt(orig)}}} | model_wp(best)={sig.get('model_wp', '?')} "
            f"edge={sig.get('edge_c', '?')}c")
    now = time.time()
    if sig.get("action") == "BUY":
        print(f"  {line}")
        print(f"  [SIGNAL] {sig['tip']}  ({sig['situation']}/{sig['confidence']}) "
              f"{sig['reason']}")
        print(format_analysis(sig))
        _LAST_LOG[tk] = now
    elif (now - _LAST_LOG.get(tk, 0)) >= SPORT_LOG_EVERY_S:
        print(f"  {line}")
        if sig.get("action") == "SKIP":
            print(f"  [SIGNAL] SKIP: {sig.get('reason', '')}")
        _LAST_LOG[tk] = now

    _bids = [b for b in live.values() if isinstance(b, (int, float))]
    sig["leader_bid"] = max(_bids) if _bids else None
    return sig


async def _watch_ticker(c, tk, traded, dropped, sem, main_list) -> None:
    """One watcher per game: poll every BASEBALL_POLL_S; on BUY place + manage
    the scalp, then stop (one trade per game per run)."""
    misses = 0
    while tk not in traded:
        if _TARGET_REACHED.is_set():
            return
        _pause = _PAUSE_UNTIL - time.time()
        if _pause > 0:
            await asyncio.sleep(min(_pause + 1, SPORT_NOTSTARTED_POLL_S))
            continue
        if not any(m["ticker"] == tk for m in main_list):
            return                                     # dropped from the watchlist
        sig = None
        try:
            async with sem:
                sig = await _eval_one_game(c, tk)
        except Exception as e:
            print(f"  [{tk}] watch error: {e}", file=sys.stderr)

        if sig and sig.get("not_started"):
            misses = 0
            await asyncio.sleep(SPORT_NOTSTARTED_POLL_S)
            continue
        if sig is None:
            misses += 1
            if misses >= 3:
                return
        else:
            misses = 0
            lb = sig.get("leader_bid")
            decided = lb is not None and lb > SPORT_DECIDED_BID
            if sig.get("action") == "BUY" and SPORT_PLACE_ORDERS and not decided:
                tm = await _team_markets(c, tk)
                mkt_side = tm.get(sig["team"])
                if not mkt_side:
                    print(f"  [{tk}] no market for {sig['team']!r}; skip")
                else:
                    mkt, side = mkt_side
                    n_contracts = SPORT_CONTRACTS
                    if sig.get("confidence") == CONF_ULTRA:
                        n_contracts = max(1, round(SPORT_CONTRACTS * SPORT_ULTRA_MULT))
                        print(f"  [SIZEUP] ultra-high edge on {sig['team']} — "
                              f"buying {n_contracts} (= {SPORT_CONTRACTS} x{SPORT_ULTRA_MULT})")
                    traded.add(tk)
                    if not SPORT_REBUY:                # one trade per game — claim both sides
                        for _mtk, _s in tm.values():
                            if _mtk:
                                traded.add(_mtk)
                    try:
                        await execute_scalp_trade(c, mkt, side, sig["team"], sig,
                                                  contracts=n_contracts)
                    except Exception as e:
                        print(f"  [{tk}] trade error: {e}", file=sys.stderr)
                    return
            elif sig.get("action") == "BUY" and decided:
                print(f"  [{tk}] leader at {lb}c (> {SPORT_DECIDED_BID}c) — game "
                      f"decided, not scalping")
        await asyncio.sleep(BASEBALL_POLL_S)


async def _main_refresh(c, main_list: list, pending_list: list) -> None:
    """Every SPORT_MAIN_REFRESH_S: full re-discovery of live baseball games."""
    while not _STOP.is_set():
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=SPORT_MAIN_REFRESH_S)
            return
        except asyncio.TimeoutError:
            pass
        if _TARGET_REACHED.is_set():
            continue
        try:
            fresh = await _live_games_in_band(c)
        except Exception as e:
            print(f"  [main-refresh] {e}", file=sys.stderr)
            continue
        main_list[:] = [m for m in fresh if not _is_pending(m)]
        pending_list[:] = [m for m in fresh if _is_pending(m)]
        print(f"  [main-refresh] live={len(main_list)} pending={len(pending_list)}"
              f"  ({_now_cst()})")


async def _pending_promoter(client, main_list: list, pending_list: list) -> None:
    """Every SPORT_PENDING_REFRESH_S: promote started games (volume re-checked)."""
    while not _STOP.is_set():
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=SPORT_PENDING_REFRESH_S)
            return
        except asyncio.TimeoutError:
            pass
        if _TARGET_REACHED.is_set():
            continue
        candidates = [m for m in pending_list if not _is_pending(m)]
        if not candidates:
            continue

        async def _vol_ok(ticker: str) -> bool:
            try:
                md = await client.req("GET", f"/markets/{ticker}")
                m = md.get("market", {}) or {}
                usd = ks._f(m.get("volume_fp")) * ks._f(m.get("last_price_dollars"))
            except Exception as e:
                print(f"  [promote] {ticker} volume re-check failed: {e} — "
                      f"promoting anyway (fail open)", file=sys.stderr)
                return True
            return usd >= MIN_VOLUME_USD

        ok_flags = await asyncio.gather(*(_vol_ok(m["ticker"]) for m in candidates))
        have = {m["ticker"] for m in main_list}
        for m, ok in zip(candidates, ok_flags):
            if ok and m["ticker"] not in have:
                main_list.append(m)
            elif not ok:
                print(f"  [promote] {m['ticker']} below MIN_VOLUME_USD="
                      f"${MIN_VOLUME_USD:,.0f} at start — dropped")
        handled = {m["ticker"] for m in candidates}
        pending_list[:] = [m for m in pending_list if m["ticker"] not in handled]
        if any(ok_flags):
            print(f"  [promote] {sum(ok_flags)} game(s) now live → watchlist  ({_now_cst()})")


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════
async def run() -> None:
    _setup_logging()
    print(f"[BASEBALL-BOT v2] sport={SPORT}  min_vol=${MIN_VOLUME_USD:,.0f}  "
          f"top_n={TOP_N}  contracts={SPORT_CONTRACTS}  scalp=+{SCALP_PCT:.0f}%  "
          f"stop=-{BB_STOP_LOSS_C}c  place_orders={SPORT_PLACE_ORDERS}  "
          f"poll={BASEBALL_POLL_S}s  rebuy={SPORT_REBUY}  DRY_RUN={v1.DRY_RUN}")
    c = KalshiClient()
    try:
        # sports4cast gate data (user rule 07/12): scrape baseball_data.csv now
        # if stale, then re-scrape every day at 8:15 AM CST while the bot runs.
        await b4c.ensure_fresh()
        asyncio.create_task(b4c.daily_scrape_task())

        try:
            starting_pv = await _portfolio_value(c)
        except Exception as e:
            print(f"[TARGET-PV] start value error: {e}")
            starting_pv = 0.0
        target_pv = (starting_pv * (1 + TARGET_PORTFOLIO_PCT / 100.0)
                     if (TARGET_PORTFOLIO_PCT > 0 and starting_pv > 0) else None)
        _bank_stop_usd = SPORT_LOSS_LIMIT_USD * (SPORT_LOSS_LIMIT_PCT / 100.0)
        loss_floor_pv = (starting_pv - _bank_stop_usd
                         if (SPORT_LOSS_LIMIT_USD > 0 and starting_pv > 0) else None)
        print(f"[TARGET-PV] start PV ${starting_pv:.2f}" + (
            f"  target ${target_pv:.2f} (+{TARGET_PORTFOLIO_PCT:.0f}%)"
            if target_pv else "  (TARGET_PORTFOLIO_PCT disabled)"))

        # ── STEP 1: live baseball games, volume floor from config, bid in band ─
        try:
            games = await _live_games_in_band(c)
        except Exception as e:
            print(f"  [{SPORT}] fetch error: {e}")
            games = []
        print(f"\n=== STEP 1: live {SPORT} games, vol >= ${MIN_VOLUME_USD:,.0f}, "
              f"bid {SPORT_BID_LO}-{SPORT_BID_HI}c ===")
        print(f"  {SPORT}: {len(games)}  "
              f"{[(m['ticker'], round(m.get('usd_volume', 0))) for m in games]}")

        main_list = [m for m in games if not _is_pending(m)]
        pending_list = [m for m in games if _is_pending(m)]
        print(f"=== STEP 1b: {len(main_list)} started → watchlist; "
              f"{len(pending_list)} pending ===")

        # ── STEP 2: first game's live state + bids (sanity print) ────────────
        if main_list:
            tk0 = main_list[0]["ticker"]
            try:
                st0 = await _baseball_state(c, tk0)
                bids0 = await ks.get_live_bid_prices(tk0, client=c)
                print(f"\n=== STEP 2: state of top game {tk0} ===\n  state={st0}\n"
                      f"  bids={bids0}")
            except Exception as e:
                print(f"  [STEP2] {tk0}: {e}")

        # ── STEP 3: parallel watchers + guardians ─────────────────────────────
        traded: set = set()
        dropped: set = set()
        print(f"\n=== PARALLEL POLLING every {BASEBALL_POLL_S}s "
              f"(concurrency {SPORT_MAX_CONCURRENCY}; Ctrl-C to stop) ===")
        asyncio.create_task(_tp_guardian(c, traded))
        asyncio.create_task(_positions_logger(c))
        asyncio.create_task(_pv_target_guard(c, starting_pv, target_pv, loss_floor_pv))
        asyncio.create_task(_main_refresh(c, main_list, pending_list))
        asyncio.create_task(_pending_promoter(c, main_list, pending_list))
        sem = asyncio.Semaphore(SPORT_MAX_CONCURRENCY)
        watchers: dict = {}
        while not _STOP.is_set():
            for tk, t in list(watchers.items()):
                if t.done():
                    watchers.pop(tk)
            if not _TARGET_REACHED.is_set():
                for m in main_list:
                    tk = m["ticker"]
                    if tk not in watchers and tk not in traded and tk not in dropped:
                        watchers[tk] = asyncio.create_task(
                            _watch_ticker(c, tk, traded, dropped, sem, main_list))
                print(f"  [watch] {sum(1 for t in watchers.values() if not t.done())} "
                      f"active watcher(s); traded={len(traded)}  ({_now_cst()})")
            else:
                print(f"  [DRAIN] target reached — no new buys; "
                      f"{len(_FILLED_ORDERS)} session position(s) open  ({_now_cst()})")
            try:
                await asyncio.wait_for(_STOP.wait(), timeout=SPORT_LIST_REFRESH_S)
            except asyncio.TimeoutError:
                pass
            if _STOP.is_set():
                break
        print("[BASEBALL-BOT] halt signalled — cancelling watchers.")
        for t in watchers.values():
            t.cancel()
    finally:
        await c.close()


# ── logging (same rotating tee as v1, baseball-prefixed) ──────────────────────
class _Tee:
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


class _RotatingLog:
    """kalshi_baseball_YYYYMMDD.log in SPORT_LOG_DIR (customer logs folder);
    prior-date files auto-archived, rolls at midnight."""
    _PREFIX = "kalshi_baseball_"

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
    if isinstance(sys.stdout, _Tee):
        return
    try:
        rot = _RotatingLog()
    except Exception as e:
        print(f"[BASEBALL-BOT] could not open log: {e}", file=sys.stderr)
        return
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.stdout = _Tee(sys.__stdout__, rot)
    sys.stderr = _Tee(sys.__stderr__, rot)
    print(f"[BASEBALL-BOT] logging to {rot.path.name}  (archive on day change)  ({_now_cst()})")


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
