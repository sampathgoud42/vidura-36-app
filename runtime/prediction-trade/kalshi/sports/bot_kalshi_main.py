#!/usr/bin/env python3
"""
bot_kalshi_main.py — multi-sport Kalshi bot (tennis + baseball, pluggable).
===========================================================================
The merge of bot_kalshi_sports_v1 (tennis) and bot_kalshi_sports_v2 (baseball)
into ONE generic engine + per-sport plugins:

    engine (this file)                     sport_adapters/<sport>.py
    ─────────────────────────────────      ──────────────────────────────────
    discovery (volume/band/staleness)      market filters (e.g. no F5/F3)
    watcher tasks + supervisor             live scoring + prediction model
    order execution + fill confirm         market/side mapping, sizing, TP policy
    guardian (TP upkeep, stop-loss,        sport-specific exits (tennis
      band exits, close detection)           favorite-comeback/collapse, …)
    per-sport BANK risk + banner halt
    portfolio target/loss halt, CSV, logs

ACTIVE sports come from MAIN_SPORTS_LIST in ``kaslhi_sports.env`` (fallback
SPORTS_LIST); each must have an adapter registered in sport_adapters/.
PIPELINE sports live in MAIN_SPORTS_LIST_TBD: their adapters + stub models
(basketball, cricket, hockey, soccer, golf) are loaded and structure-validated
at startup but never discovered or traded — implementing the model and moving
the sport into MAIN_SPORTS_LIST activates it.  Adding a brand-new sport = one
adapter file + one registry line + env knobs — the engine does not change
(see sport_adapters/__init__.py and sport_adapters/generic.py).

On launch the bot FIRST adopts every position already open in the account
(prior runs, the v1/v2 bots, manual buys) whose sport is configured: it reports
entry basis / live bid / unrealized P&L per position and the guardian monitors
them for profit (TP policy + band ceiling) and stop-loss (per-sport stop +
floor) from its first cycle — before the slow startup steps (rankings scrape,
discovery) even begin.  Their closes are CSV-logged and drawn against the
sport's bank.

PAPER TRADING (user 07/17): MAIN_PAPER=TRUE runs the identical pipeline —
discovery, tennis v5 + baseball models, spread gate, one-entry ledger (its own
_paper file), per-sport banks — but simulates every order against the live
book instead of placing it: resting-limit entry fills (taker fee 7%·p·(1-p) on
crossed fills, maker fills free), the sport's real exit policy (resting TP,
entry-relative stop with its strike count, floor, adapter exits, settlement at
100/0).  Results land in paper_trades_main.csv; the real account is only ever
READ for quotes.  Adoption, the real guardian, and the API brakes are skipped.

Spread gate (user rule 07/12): before EVERY order — buy, TP sell, stop-loss/
band/sport exit — a bid/ask spread wider than SPORT_SPREAD_MAX_C (3c) means
the book is unstable: the bot waits (up to SPORT_SPREAD_TIMEOUT_S) for the
spread to come back inside the max with two consecutive identical quotes,
then RE-VALIDATES the signal (buys re-run the full evaluation; exits re-check
their trigger at the fresh bid) and only acts if it still holds.  Buys that
fail revalidation are abandoned (the watcher keeps polling); exits/TPs defer
to the next guardian cycle.

Hard order-safety rules (user 07/12): NEVER BUY NO — only YES-side entries,
ever (backing the other participant means buying YES on THEIR market); and
NEVER SELL NAKED — every sell order (TP, stop-loss, band/sport exits) is
preceded by SPORT_SELL_CONFIRMS (3) consecutive confirmations, 5s apart, that
an open position exists on that exact market (positions AND resting orders
re-fetched each round); any round that disagrees cancels the sell.

Per-sport risk (new in main; upper- or lower-case env keys both work):
    <SPORT>_BANK=100           session bankroll ($) for that sport (0 = unlimited)
    <SPORT>_CONTRACTS=20       contracts per order for that sport
    <SPORT>_STOP_LOSS_PCT=30   once the sport's realized session loss exceeds
                               this % of its bank, THAT sport's betting stops
                               with a banner (open positions stay managed;
                               other sports keep trading)

Run:
    python bot_kalshi_main.py [customer]        # customer default "suma"
"""
from __future__ import annotations

import asyncio
import csv
import os
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import dotenv
from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent
_KALSHI_ROOT = _HERE.parent                                    # prediction-trade/kalshi
_PT_ROOT = _KALSHI_ROOT.parent                                 # prediction-trade
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_KALSHI_ROOT))
sys.path.insert(0, str(_KALSHI_ROOT / "btc" / "btc15"))        # → `import bot_kalshi_btc15`
sys.path.insert(0, str(_PT_ROOT / "sports"))                    # → `import tennis`, `import baseball`

# bot_kalshi_btc15 does `from btc import BtcVidyaMonitor`; that package lives at
# <repo-root>/indicators — alias it (same shim as the v1/v2 bots).
if "btc" not in sys.modules:
    _REPO_ROOT = _PT_ROOT.parent                                # .../38trades-py-claude
    sys.path.insert(0, str(_REPO_ROOT))
    import indicators as _btc_pkg                                # noqa: E402
    sys.modules["btc"] = _btc_pkg

# ── config + credentials: identical bootstrap to the v1/v2 bots ───────────────
for _name in ("kaslhi_sports.env", "kalshi_sports.env"):
    _p = _HERE / _name
    if _p.exists():
        load_dotenv(_p)
        break


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
    print(f"[MAIN-BOT] WARNING: no .env found in {CUSTOMER_DIR} — "
          f"KALSHI_API_KEY_ID/KALSHI_PRIVATE_KEY/BASE_URI are unset, auth will fail.")

_pk = os.getenv("KALSHI_PRIVATE_KEY", "").strip()
if _pk and not Path(_pk).is_absolute() and (CUSTOMER_DIR / _pk).exists():
    os.environ["KALSHI_PRIVATE_KEY"] = str(CUSTOMER_DIR / _pk)
elif not _pk:
    _pems = sorted(CUSTOMER_DIR.glob("*.pem"))
    if _pems:
        os.environ["KALSHI_PRIVATE_KEY"] = str(_pems[0])

# Import the shared clients WITHOUT letting bot_kalshi_btc15's bare
# load_dotenv() touch the project root .env (same trick as v1/v2).
_real_load_dotenv = dotenv.load_dotenv
dotenv.load_dotenv = lambda *a, **kw: False
try:
    import kalshi_sports as ks                    # noqa: E402
    import bot_kalshi_btc15 as v1                 # noqa: E402
finally:
    dotenv.load_dotenv = _real_load_dotenv

# Sport plugins — created AFTER config/credentials are loaded (their modules,
# and the v1/v2 bots they delegate to, read env at import time).
from sport_adapters import create_adapter, SportAdapter, SportBook, available  # noqa: E402

KalshiClient = ks.KalshiClient

# ── engine config (generic; per-sport knobs live in each SportConfig) ─────────
# MAIN_SPORTS_LIST      → ACTIVE sports: discovered, watched, traded.
# MAIN_SPORTS_LIST_TBD  → PIPELINE sports: adapter + stub model are loaded and
#   structure-VALIDATED at startup (so a broken plugin surfaces immediately),
#   but they are never discovered/traded until moved into MAIN_SPORTS_LIST.
SPORTS_LIST = [s.strip().lower() for s in
               os.getenv("MAIN_SPORTS_LIST", os.getenv("SPORTS_LIST", "tennis")).split(",")
               if s.strip()]
SPORTS_TBD = [s.strip().lower() for s in
              os.getenv("MAIN_SPORTS_LIST_TBD", "").split(",")
              if s.strip() and s.strip().lower() not in SPORTS_LIST]
MIN_VOLUME_USD = float(os.getenv("MIN_VOLUME_USD", "25000"))
TOP_N_PER_SPORT = int(os.getenv("TOP_N_PER_SPORT", "100"))
SPORT_BID_LO = int(os.getenv("SPORT_BID_LO", "25"))            # discovery band
SPORT_BID_HI = int(os.getenv("SPORT_BID_HI", "85"))
SPORT_PLACE_ORDERS = os.getenv("SPORT_PLACE_ORDERS", "TRUE").strip().upper() != "FALSE"
SPORT_REBUY = os.getenv("SPORT_REBUY", "TRUE").strip().upper() != "FALSE"
SPORT_FILL_TIMEOUT_S = int(os.getenv("SPORT_FILL_TIMEOUT_S", str(15 * 60)))
SPORT_FILL_POLL_S = int(os.getenv("SPORT_FILL_POLL_S", "60"))
SPORT_POST_ORDER_DELAY_S = int(os.getenv("SPORT_POST_ORDER_DELAY_S", "10"))
SPORT_PRICE_BUMP_C = int(os.getenv("SPORT_PRICE_BUMP_C", "5"))
SPORT_MAX_TP_C = int(os.getenv("SPORT_MAX_TP_C", "98"))
SPORT_DECIDED_BID = int(os.getenv("SPORT_DECIDED_BID", "90"))
SPORT_NOTSTARTED_POLL_S = int(os.getenv("SPORT_NOTSTARTED_POLL_S", "1800"))
SPORT_INSUFFICIENT_PAUSE_S = int(os.getenv("SPORT_INSUFFICIENT_PAUSE_S", "1800"))
SPORT_LIST_REFRESH_S = int(os.getenv("SPORT_LIST_REFRESH_S", "300"))
SPORT_MAIN_REFRESH_S = int(os.getenv("SPORT_MAIN_REFRESH_S", "3600"))
SPORT_PENDING_REFRESH_S = int(os.getenv("SPORT_PENDING_REFRESH_S", "1800"))
SPORT_MAX_CONCURRENCY = int(os.getenv("SPORT_MAX_CONCURRENCY", "12"))
SPORT_TP_GUARD_S = int(os.getenv("SPORT_TP_GUARD_S", "120"))
SPORT_GUARD_RECONFIRM_S = int(os.getenv("SPORT_GUARD_RECONFIRM_S", "30"))
SPORT_POS_LOG_S = int(os.getenv("SPORT_POS_LOG_S", "1800"))
SPORT_STOP_CONFIRM = int(os.getenv("SPORT_STOP_CONFIRM", "2"))
SPORT_STOP_MIN_BID_C = int(os.getenv("SPORT_STOP_MIN_BID_C", "4"))
SPORT_STOP_DEEP_C = int(os.getenv("SPORT_STOP_DEEP_C", "45"))
SPORT_STOP_SLIP_C = int(os.getenv("SPORT_STOP_SLIP_C", "3"))
SPORT_TP_CEILING_C = int(os.getenv("SPORT_TP_CEILING_C", "97"))
SPORT_SL_FLOOR_C = int(os.getenv("SPORT_SL_FLOOR_C", "9"))
SPORT_FAVX_CONFIRM = int(os.getenv("SPORT_FAVX_CONFIRM", "2"))
# ── spread gate (user rule 07/12) ─────────────────────────────────────────────
# Before EVERY order (buy, TP sell, stop-loss/band/sport exits): if the bid/ask
# spread is wider than SPORT_SPREAD_MAX_C cents the book is unstable — WAIT for
# it to stabilize (spread back inside the max AND two consecutive identical
# quotes), then RE-VALIDATE the signal/exit condition and only act if it still
# holds.  A book that never stabilizes within SPORT_SPREAD_TIMEOUT_S aborts a
# buy / defers an exit or TP to the next guardian cycle.
SPORT_SPREAD_MAX_C = int(os.getenv("SPORT_SPREAD_MAX_C", "3"))
SPORT_SPREAD_WAIT_S = int(os.getenv("SPORT_SPREAD_WAIT_S", "10"))
SPORT_SPREAD_TIMEOUT_S = int(os.getenv("SPORT_SPREAD_TIMEOUT_S", "120"))
# ── never-sell-naked rule (user rule 07/12) ───────────────────────────────────
# NEVER place a sell order without an open position on that EXACT market:
# every sell is preceded by SPORT_SELL_CONFIRMS consecutive confirmations
# (positions AND resting orders re-fetched each round) spaced
# SPORT_SELL_CONFIRM_DELAY_S apart.  Any round that shows no position (or an
# unexpected side / a conflicting resting order) cancels the sell entirely.
SPORT_SELL_CONFIRMS = int(os.getenv("SPORT_SELL_CONFIRMS", "3"))
SPORT_SELL_CONFIRM_DELAY_S = float(os.getenv("SPORT_SELL_CONFIRM_DELAY_S", "5"))
_KALSHI_DROP_STATUSES = {"interrupted", "suspended", "cancelled", "canceled",
                         "postponed", "abandoned", "delayed", "retired",
                         "walkover", "wov"}

# ── portfolio profit-target / loss-limit halt (same keys as v1/v2) ────────────
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

# ── PAPER TRADING mode (user 07/17) ───────────────────────────────────────────
# MAIN_PAPER=TRUE: the full pipeline runs — discovery, models (tennis v5 +
# baseball), spread gate, one-entry ledger, per-sport banks — but NO real order
# ever goes out and the REAL account is never read for positions.  Entries are
# simulated as resting limit orders against the live book (fill when the ask
# crosses our limit, or the bid trades through it; expire unfilled after the
# sport's fill window — never chase), exits replay the sport's real policy
# (resting TP fill when bid >= tp, entry-relative stop with the sport's strike
# count, hard floor, adapter exits like baseball's score-flip, settlement at
# 100/0), and Kalshi's taker fee (7% * p * (1-p)) is charged on taker fills.
# Results land in paper_trades_main.csv; the match ledger uses a separate
# _paper file so paper runs never block future REAL entries.
MAIN_PAPER = os.getenv("MAIN_PAPER", "FALSE").strip().upper() == "TRUE"
MAIN_PAPER_POLL_S = int(os.getenv("MAIN_PAPER_POLL_S", "15"))
_PAPER_ORDERS: dict = {}     # ticker -> resting simulated entry order
_PAPER_POS: dict = {}        # ticker -> open simulated position
_PAPER_STRIKES: dict = {}    # ticker -> consecutive stop/floor breach polls

# ── sport plugins + per-sport banks ───────────────────────────────────────────
ADAPTERS: dict = {}                               # ACTIVE: discovered + traded
BOOKS: dict[str, SportBook] = {}
for _s in SPORTS_LIST:
    try:
        _a = create_adapter(_s)
        ADAPTERS[_s] = _a
        BOOKS[_s] = SportBook(_a.cfg)
    except Exception as _e:
        print(f"[MAIN-BOT] sport {_s!r} unavailable ({_e}) — skipped. "
              f"Registered adapters: {', '.join(available())}", file=sys.stderr)
_SPORTS_SET = set(ADAPTERS)                       # guardian sell scope (ACTIVE only)

# PIPELINE (TBD) sports: instantiate to VALIDATE the plugin structure (adapter
# imports, model module resolves, config parses) but never trade them.
TBD_ADAPTERS: dict = {}
for _s in SPORTS_TBD:
    try:
        TBD_ADAPTERS[_s] = create_adapter(_s)
    except Exception as _e:
        print(f"[MAIN-BOT] TBD sport {_s!r} failed structure validation: {_e}",
              file=sys.stderr)
_TBD_SET = set(TBD_ADAPTERS)

# ── trade history (one CSV, all sports; row UPDATED in place on close) ────────
SPORT_TRADE_CSV = os.getenv("MAIN_TRADE_CSV",
                            str(CUSTOMER_DIR / "trade_history" / "trade_history_main.csv"))
PAPER_TRADE_CSV = os.getenv("MAIN_PAPER_CSV",
                            str(CUSTOMER_DIR / "trade_history" / "paper_trades_main.csv"))
_TRADE_CSV_COLS = ["ts_epoch", "ts", "sport", "ticker", "name", "side",
                   "situation", "confidence", "reason", "context", "model_wp",
                   "signal_bid", "buy_price", "fill_price", "contracts",
                   "tp_price", "stop_price", "pv_entry", "status",
                   "ts_close", "pv_close", "realized_pnl", "pv_delta_pct"]

_FILLED_ORDERS: dict = {}    # ticker -> {sport, side, contracts, buy_at, tp, ...}
_STOP_STRIKES: dict = {}     # ticker -> stop-loss breach cycles
_BAND_STRIKES: dict = {}     # ticker -> floor breach cycles
_EXIT_STRIKES: dict = {}     # ticker -> adapter exit-rule breach cycles


def _event_of(ticker: str) -> str:
    return ticker.rsplit("-", 1)[0] if ticker.count("-") >= 2 else ticker


def _is_pending(m: dict) -> bool:
    ts = m.get("start_ts")
    return ts is not None and ts > time.time()


# ══════════════════════════════════════════════════════════════════════════════
#  Discovery (generic; adapter hooks for sport-specific filters/meta)
# ══════════════════════════════════════════════════════════════════════════════
async def _live_matches_in_band(c, adapter) -> list:
    """Live matches for the adapter's sport: usd_volume >= MIN_VOLUME_USD
    (STRICT), a bid inside [SPORT_BID_LO, SPORT_BID_HI]c, volume-sorted, capped
    at TOP_N_PER_SPORT, then milestone-status/staleness filtered and
    adapter-confirmed."""
    sport = adapter.name
    all_live = await ks.filter_by_sport_min_volume_live(sport, 0, top_n=10 ** 9, client=c)
    all_live = adapter.filter_discovered(all_live)

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
        print(f"  [{sport}] excluded {low_vol} match(es) below "
              f"MIN_VOLUME_USD=${MIN_VOLUME_USD:,.0f}")
    kept.sort(key=lambda m: m.get("usd_volume", 0.0), reverse=True)
    kept = kept[:TOP_N_PER_SPORT]

    metas = await asyncio.gather(*(adapter.match_meta(c, m["ticker"]) for m in kept),
                                 return_exceptions=True)
    fresh = []
    for m, meta in zip(kept, metas):
        age, status, start_ts = (meta if isinstance(meta, tuple) and len(meta) == 3
                                 else (None, "", None))
        if status in _KALSHI_DROP_STATUSES:
            print(f"  [status] {m['ticker']} kalshi status={status!r} — not active, removed")
            continue
        if isinstance(age, (int, float)) and age > adapter.cfg.max_live_hours:
            print(f"  [stale] {m['ticker']} live {age:.1f}h > "
                  f"{adapter.cfg.max_live_hours:.0f}h — removed")
            continue
        m["age_hours"] = age
        m["start_ts"] = start_ts
        adapter.note_match(m)
        fresh.append(m)
    return await adapter.confirm_active(fresh, c)


# ══════════════════════════════════════════════════════════════════════════════
#  Portfolio / P&L helpers
# ══════════════════════════════════════════════════════════════════════════════
async def _match_exposure(client, market_ticker: str) -> tuple:
    """(open_contracts, resting_orders) summed over the whole MATCH (event)."""
    event = _event_of(market_ticker)
    pos_contracts = 0
    pd = await client.req("GET", "/portfolio/positions", params={"limit": 1000})
    for p in pd.get("market_positions", []):
        if _event_of(p.get("ticker", "")) == event:
            pos_contracts += abs(int(float(p.get("position_fp", "0"))))
    rest = await v1.resting_orders(client)
    rest_n = sum(1 for o in rest if _event_of(o.get("ticker", "")) == event)
    return pos_contracts, rest_n


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


async def _confirm_open_position(client, ticker: str, *, expect_side=None,
                                 require_no_resting: bool = True,
                                 tag: str = "SELLCHECK") -> tuple:
    """
    NEVER-sell-naked rule (user 07/12): before ANY sell order, confirm an open
    position exists on this EXACT market SPORT_SELL_CONFIRMS times (default 3),
    SPORT_SELL_CONFIRM_DELAY_S (5s) apart, re-fetching BOTH the position and
    the market's resting orders on every round.  The sell is cancelled (returns
    (0, None, None)) the moment any round shows:
      • no open position (or a fetch error — fail safe),
      • a side different from ``expect_side`` (when given),
      • any resting order already on the ticker (when ``require_no_resting`` —
        used for TP placement so a sell is never duplicated; exits that REPLACE
        a resting TP pass False and cancel it themselves after confirmation).
    Returns (contracts, side, position_dict) from the LAST confirming read.
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
        print(f"  [{tag}] {ticker} sell-confirm {i + 1}/{n}: holding {have} {side}"
              + ("" if require_no_resting else f", resting={len(rest)}") + " OK")
    return have, side, pos


# ── spread gate helpers ───────────────────────────────────────────────────────
async def _quote(client, ticker: str, side: str) -> tuple:
    """(bid_c, ask_c) for ``side`` of ``ticker`` — (None, None) on error."""
    try:
        md = await client.req("GET", f"/markets/{ticker}")
        mkt = md.get("market", {}) or {}
        return (ks._cents(mkt.get(f"{side}_bid_dollars")),
                ks._cents(mkt.get(f"{side}_ask_dollars")))
    except Exception:
        return None, None


def _spread_ok(bid_c, ask_c) -> bool:
    return (bid_c is not None and ask_c is not None
            and (ask_c - bid_c) <= SPORT_SPREAD_MAX_C)


async def _await_stable_quote(client, ticker: str, side: str,
                              tag: str = "SPREAD") -> tuple:
    """
    Wait for a STABLE book on ``ticker``/``side``: spread <= SPORT_SPREAD_MAX_C
    AND two consecutive polls (SPORT_SPREAD_WAIT_S apart) with an identical
    bid/ask.  Returns (latest_bid_c, stable: bool); gives up after
    SPORT_SPREAD_TIMEOUT_S.  If the book is already tight on the first read it
    returns immediately.
    """
    bid, ask = await _quote(client, ticker, side)
    if _spread_ok(bid, ask):
        return bid, True
    print(f"  [{tag}] {ticker} {side} spread "
          f"{bid if bid is not None else '?'}/{ask if ask is not None else '?'}c "
          f"> {SPORT_SPREAD_MAX_C}c — waiting for a stable book "
          f"(up to {SPORT_SPREAD_TIMEOUT_S}s)")
    t0 = time.time()
    prev = None
    while time.time() - t0 < SPORT_SPREAD_TIMEOUT_S:
        await asyncio.sleep(SPORT_SPREAD_WAIT_S)
        bid, ask = await _quote(client, ticker, side)
        if _spread_ok(bid, ask) and prev == (bid, ask):
            print(f"  [{tag}] {ticker} book stable at {bid}/{ask}c "
                  f"after {time.time() - t0:.0f}s")
            return bid, True
        prev = (bid, ask) if _spread_ok(bid, ask) else None
    print(f"  [{tag}] {ticker} book still unstable after {SPORT_SPREAD_TIMEOUT_S}s "
          f"(last {bid}/{ask}c)")
    return bid, False


async def _pnl_from_fills(client, ticker: str, side: str, since_ts: float = 0.0) -> float:
    """Realized P&L (USD) from fills since ``since_ts``, priced on the token we
    HELD (yes_price for yes positions, no_price for no) — a fill's own 'side'
    field reflects order matching, not our holding."""
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


# ══════════════════════════════════════════════════════════════════════════════
#  Trade CSV
# ══════════════════════════════════════════════════════════════════════════════
def _trade_log(row: dict, csv_path: "str | None" = None) -> None:
    try:
        path = Path(csv_path or SPORT_TRADE_CSV)
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=_TRADE_CSV_COLS, extrasaction="ignore")
            if new:
                w.writeheader()
            w.writerow({c: row.get(c, "") for c in _TRADE_CSV_COLS})
    except Exception as e:
        print(f"  [TRADECSV] write failed: {e}", file=sys.stderr)


def _trade_log_close(ticker: str, ts_epoch, updates: dict,
                     csv_path: "str | None" = None) -> None:
    path = Path(csv_path or SPORT_TRADE_CSV)
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


# ══════════════════════════════════════════════════════════════════════════════
#  ONE-ENTRY-PER-MATCH ledger (v5, user 07/16) — persistent across restarts
# ══════════════════════════════════════════════════════════════════════════════
# The tennis forensics found hidden rebuy/averaging-down loops (bot restarts +
# re-arms re-bought collapsing matches at up to 22x planned size) caused
# -$1,126 of the -$1,539 true loss.  This ledger records every EVENT ticker at
# order time — BEFORE placement — in a file that survives restarts; a match in
# the ledger can never be entered again, by any sport, ever.
# Paper mode keeps its OWN ledger file so paper runs never block real entries.
_LEDGER_PATH = Path(os.getenv("MAIN_MATCH_LEDGER",
                              str(CUSTOMER_DIR / "trade_history" /
                                  ("match_ledger_paper.json" if MAIN_PAPER
                                   else "match_ledger.json"))))
_LEDGER_KEEP_DAYS = int(os.getenv("MAIN_LEDGER_KEEP_DAYS", "5"))
_MATCH_LEDGER: dict = {}


def _ledger_load() -> None:
    global _MATCH_LEDGER
    try:
        import json
        with open(_LEDGER_PATH, encoding="utf-8") as f:
            _MATCH_LEDGER = json.load(f) or {}
    except Exception:
        _MATCH_LEDGER = {}
    # prune entries older than _LEDGER_KEEP_DAYS (tickers are date-scoped)
    cutoff = (datetime.now(timezone.utc).timestamp() - _LEDGER_KEEP_DAYS * 86400)
    _MATCH_LEDGER = {k: v for k, v in _MATCH_LEDGER.items()
                     if isinstance(v, (int, float)) and v >= cutoff}
    if _MATCH_LEDGER:
        print(f"[LEDGER] {len(_MATCH_LEDGER)} match(es) already traded within "
              f"{_LEDGER_KEEP_DAYS}d — permanently ineligible (one entry per match)")


def _ledger_add(event: str) -> None:
    """Record BEFORE order placement; flush to disk immediately."""
    _MATCH_LEDGER[event] = datetime.now(timezone.utc).timestamp()
    try:
        import json
        _LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _LEDGER_PATH.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_MATCH_LEDGER, f)
        os.replace(tmp, _LEDGER_PATH)
    except Exception as e:
        print(f"  [LEDGER] write failed: {e}", file=sys.stderr)


_ledger_load()


# ══════════════════════════════════════════════════════════════════════════════
#  API-reconciled dollar brakes (v5, user 07/16)
# ══════════════════════════════════════════════════════════════════════════════
# The old bank-halt never tripped because internal P&L recorded $0-settled
# losers as 0.00.  These brakes compute a sport's realized day/week P&L from
# the FILLS + SETTLEMENTS API (the same source the forensics used) and halt
# new entries for that sport on breach: day → until 09:00 CST next day;
# week → 7 days (human review).  Cached _BRAKE_CACHE_S per sport.
_BRAKE_CACHE_S = int(os.getenv("MAIN_BRAKE_CACHE_S", "300"))
_BRAKE_STATE: dict = {}      # sport -> {"ts", "day", "week", "halt_until", "why"}


async def _api_sport_pnl(client, sport: str, since_ts: float) -> float:
    """Realized P&L (USD) for ``sport`` from fills+settlements since ``since_ts``:
    sells - buys - fees + settlement revenue, filtered by series taxonomy."""
    smap = await ks._sports_series(client)

    def _is_sport(tk: str) -> bool:
        return str(smap.get(ks._series_of(tk), {}).get("sport", "")).lower() == sport

    pnl, cursor = 0.0, None
    for _page in range(20):                       # fills, newest first
        params = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        d = await client.req("GET", "/portfolio/fills", params=params)
        fills = d.get("fills", [])
        stop = False
        for fx in fills:
            ts = fx.get("ts")
            try:
                ts = float(ts)
            except (TypeError, ValueError):
                ts = None
            if ts is not None and ts < since_ts:
                stop = True
                break
            tk = fx.get("ticker") or fx.get("market_ticker") or ""
            if not _is_sport(tk):
                continue
            cnt = float(fx.get("count_fp") or 0)
            px = float(fx.get("yes_price_dollars") or 0)
            fee = float(fx.get("fee_cost") or 0)
            pnl += (cnt * px - fee) if fx.get("action") == "sell" else -(cnt * px + fee)
        cursor = d.get("cursor")
        if stop or not cursor or not fills:
            break
    cursor = None
    for _page in range(10):                       # settlements, newest first
        params = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        d = await client.req("GET", "/portfolio/settlements", params=params)
        rows = d.get("settlements", [])
        stop = False
        for s in rows:
            st = s.get("settled_time")
            try:
                ts = datetime.fromisoformat(str(st).replace("Z", "+00:00")).timestamp()
            except Exception:
                ts = None
            if ts is not None and ts < since_ts:
                stop = True
                break
            tk = s.get("ticker") or ""
            if _is_sport(tk):
                pnl += float(s.get("revenue") or 0) / 100.0
        cursor = d.get("cursor")
        if stop or not cursor or not rows:
            break
    return round(pnl, 2)


async def _brake_check(client, adapter) -> "str | None":
    """None = clear to trade; else a reason string (sport halted)."""
    if MAIN_PAPER:
        return None          # paper mode: real-account fills are irrelevant
    cfg = adapter.cfg
    if cfg.day_loss_halt_usd <= 0 and cfg.week_loss_halt_usd <= 0:
        return None
    st = _BRAKE_STATE.setdefault(adapter.name, {})
    now = time.time()
    if st.get("halt_until", 0) > now:
        return st.get("why", "halted")
    if now - st.get("ts", 0) < _BRAKE_CACHE_S:
        return None
    try:
        cst = v1._cst_now()
        day_start = cst.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        day = await _api_sport_pnl(client, adapter.name, day_start)
        week = await _api_sport_pnl(client, adapter.name, now - 7 * 86400)
    except Exception as e:
        print(f"  [BRAKE] {adapter.name} API check failed: {e} — "
              f"NO new entries this cycle (fail safe)", file=sys.stderr)
        return "brake check failed (fail safe)"
    st.update(ts=now, day=day, week=week)
    if cfg.week_loss_halt_usd > 0 and week <= -cfg.week_loss_halt_usd:
        st["halt_until"] = now + 7 * 86400
        st["why"] = (f"WEEK loss brake: realized ${week:+.2f} <= "
                     f"-${cfg.week_loss_halt_usd:.0f} — HALTED pending review")
        print(f"\n{'#' * 74}\n#  [BRAKE] {adapter.name.upper()} {st['why']}\n{'#' * 74}\n")
        return st["why"]
    if cfg.day_loss_halt_usd > 0 and day <= -cfg.day_loss_halt_usd:
        nxt = (cst.replace(hour=9, minute=0, second=0, microsecond=0)
               + timedelta(days=1))
        st["halt_until"] = nxt.timestamp()
        st["why"] = (f"DAY loss brake: realized ${day:+.2f} <= "
                     f"-${cfg.day_loss_halt_usd:.0f} — no new entries until "
                     f"{nxt:%m-%d 09:00} CST")
        print(f"\n{'#' * 74}\n#  [BRAKE] {adapter.name.upper()} {st['why']}\n{'#' * 74}\n")
        return st["why"]
    print(f"  [BRAKE] {adapter.name} realized: day ${day:+.2f} / week ${week:+.2f} "
          f"(limits -${cfg.day_loss_halt_usd:.0f}/-${cfg.week_loss_halt_usd:.0f}) — clear")
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  Execution
# ══════════════════════════════════════════════════════════════════════════════
async def execute_trade(client, adapter, book: SportBook, market_ticker: str,
                        side: str, name: str, sig: dict, *, contracts: int,
                        revalidate=None) -> bool:
    """BUY ``side`` at signal bid + bump; confirm the fill; place the adapter's
    TP (or hold when the adapter's policy returns None).  Gated by: global
    target, insufficient-balance pause, one-position-per-match, the SPORT's
    bank (exposure cap + drawdown halt), and the SPREAD gate (user rule 07/12):
    a bid/ask spread > SPORT_SPREAD_MAX_C waits for a stable book, then re-runs
    ``revalidate`` (async → fresh signal) and only buys if it is still a BUY
    for the same participant.

    Returns True when an order was actually placed (the watcher stops for this
    match), False when the buy was aborted pre-order (the watcher un-claims the
    match and keeps polling)."""
    global _PAUSE_UNTIL
    if _TARGET_REACHED.is_set():
        print(f"  [TRADE] {market_ticker}: profit target reached — not opening new buys")
        return False
    if time.time() < _PAUSE_UNTIL:
        return False
    # NEVER BUY NO (user rule 07/12): only YES-side entries, ever.  Backing the
    # other participant means buying YES on THEIR market, never NO on this one.
    if side != "yes":
        print(f"  [TRADE] {market_ticker}: side={side!r} — NEVER BUY NO "
              f"(user rule 07/12); buy refused")
        return False

    # ── spread gate: unstable book → wait, then REVALIDATE the buy signal ────
    bid0, ask0 = await _quote(client, market_ticker, side)
    if bid0 is not None and ask0 is not None and not _spread_ok(bid0, ask0):
        _bid_now, stable = await _await_stable_quote(client, market_ticker, side,
                                                     tag="SPREAD-BUY")
        if not stable:
            print(f"  [SPREAD-BUY] {market_ticker}: book never stabilized — "
                  f"buy abandoned (watcher keeps polling)")
            return False
        if revalidate is not None:
            try:
                sig2 = await revalidate()
            except Exception as e:
                print(f"  [SPREAD-BUY] {market_ticker}: revalidation errored ({e}) "
                      f"— buy abandoned")
                return False
            name2 = (sig2 or {}).get("player") or (sig2 or {}).get("team")
            if (not sig2 or sig2.get("action") != "BUY" or name2 != name
                    or sig2.get("bid") is None):
                print(f"  [SPREAD-BUY] {market_ticker}: after stabilization the "
                      f"signal is no longer BUY {name} "
                      f"(now {(sig2 or {}).get('action')}/{name2}) — buy abandoned")
                return False
            sig = sig2                            # act on the FRESH signal/price
            print(f"  [SPREAD-BUY] {market_ticker}: signal re-validated "
                  f"(BUY {name} @ {sig['bid']}c) — proceeding")

    # ── ONE ENTRY PER MATCH, EVER (v5, user 07/16): persistent ledger ────────
    event = _event_of(market_ticker)
    if event in _MATCH_LEDGER:
        print(f"  [LEDGER] {market_ticker}: match {event} already traded "
              f"(one entry per match, EVER) — permanently ineligible")
        return True                                  # terminal — stop watching

    # ── API-reconciled dollar brake (v5): day/week realized-loss halt ────────
    brake = await _brake_check(client, adapter)
    if brake:
        print(f"  [BRAKE] {market_ticker}: {adapter.name} halted — {brake}")
        return False

    buy_cents = int(sig["bid"])
    buy_px = min(99, buy_cents + adapter.cfg.price_bump_c)   # 0 = maker at the bid
    cost_usd = contracts * buy_px / 100.0
    ok, why = book.can_buy(cost_usd)                 # per-sport bank gate
    if not ok:
        print(f"  [BANK] {market_ticker}: {why} — skip")
        return False
    try:
        pos_n, rest_n = await _match_exposure(client, market_ticker)
    except Exception as e:
        print(f"  [TRADE] {market_ticker}: position/order check failed ({e}); skip")
        return False
    if pos_n > 0 or rest_n > 0:
        print(f"  [TRADE] {market_ticker}: match already has position={pos_n}, "
              f"resting={rest_n} — skip until flat")
        return True                                  # already in this match — stop watching

    tp = adapter.tp_for_entry(market_ticker, buy_cents, sig)
    stop = (max(1, buy_px - adapter.cfg.stop_loss_c)
            if adapter.cfg.stop_loss_c > 0 else "")
    print(f"  [TRADE] BUY [{adapter.name}] {name} {side.upper()} x{contracts} @ {buy_px}c "
          f"(signal {buy_cents}c +{adapter.cfg.price_bump_c}) on {market_ticker} "
          f"(TP {tp if tp else 'none'}" + (f" / stop {stop}c" if stop else "") + ")")
    # accounting fix (07/16 forensics): stamp open_ts BEFORE placement so the
    # buy fills are inside the since_ts window — the old post-fill stamp made
    # _realized_pnl drop every buy's cost basis ($8,050 of phantom profit).
    open_ts = time.time()
    _ledger_add(event)                   # one-entry ledger: written BEFORE the order

    # ── PAPER mode: simulate a resting limit entry instead of a real order ───
    if MAIN_PAPER:
        _PAPER_ORDERS[market_ticker] = {
            "sport": adapter.name, "side": side, "name": name,
            "limit": buy_px, "contracts": contracts, "placed_ts": open_ts,
            "timeout_s": adapter.cfg.fill_timeout_s, "tp": tp,
            "stop_c": adapter.cfg.stop_loss_c, "floor_c": adapter.cfg.sl_floor_c,
            "stop_confirm": max(1, adapter.cfg.stop_confirm),
            "signal_bid": buy_cents,
            "situation": sig.get("situation", ""),
            "confidence": sig.get("confidence", ""),
            "reason": sig.get("reason", ""), "context": adapter.context(sig),
            "model_wp": sig.get("model_wp", "")}
        try:
            adapter.on_position_opened(market_ticker, sig)   # e.g. score-flip seed
        except Exception:
            pass
        print(f"  [PAPER] resting BUY [{adapter.name}] {name} x{contracts} @ "
              f"{buy_px}c (window {adapter.cfg.fill_timeout_s}s, TP "
              f"{tp if tp else 'none'}, stop "
              f"{adapter.cfg.stop_loss_c or '-'}c) — simulated, no real order")
        return True

    r = await v1.place_buy(client, market_ticker, side,
                           buy_at_cents=buy_px, contracts=contracts)
    if r is None:
        need = cost_usd
        try:
            cash = await v1.portfolio_balance(client)
        except Exception:
            cash = None
        if cash is not None and cash < need:
            _PAUSE_UNTIL = time.time() + SPORT_INSUFFICIENT_PAUSE_S
            print(f"  [TRADE] insufficient balance (cash ${cash:.2f} < need ${need:.2f}) "
                  f"— pausing new buys for {SPORT_INSUFFICIENT_PAUSE_S // 60} min")
        else:
            print(f"  [TRADE] buy order failed for {market_ticker}")
        return False

    if v1.DRY_RUN:
        print(f"  [DRY][TRADE] order placed; would confirm {contracts} filled"
              + (f" and place TP @ {tp}c." if tp else " (no TP by policy)."))
        return True

    print(f"  [TRADE] order placed — waiting {SPORT_POST_ORDER_DELAY_S}s …")
    await asyncio.sleep(SPORT_POST_ORDER_DELAY_S)

    fill_window = adapter.cfg.fill_timeout_s        # tennis v5: 60s maker window
    if not await _await_fill(client, market_ticker, contracts, fill_window):
        print(f"  [TRADE] not filled in {fill_window}s — cancelling this order "
              f"(a missed entry costs nothing; never chase)")
        try:
            for o in await v1.resting_orders(client, market_ticker):
                await client.req("DELETE", f"/portfolio/events/orders/{o['order_id']}")
        except Exception as e:
            print(f"  [TRADE] cancel failed: {e}")
        return True
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
    # (open_ts was stamped BEFORE placement — accounting fix, see above)
    _FILLED_ORDERS[market_ticker] = {
        "sport": adapter.name, "side": side, "contracts": contracts,
        "buy_at": buy_px, "tp": tp, "name": name,
        "situation": sig.get("situation", ""), "confidence": sig.get("confidence", ""),
        "signal_bid": buy_cents, "pv_entry": pv_entry, "open_ts": open_ts}
    book.register_open(market_ticker, cost_usd)
    try:                          # adapter state seeding (e.g. score-flip exit)
        adapter.on_position_opened(market_ticker, sig)
    except Exception as e:
        print(f"  [TRADE] {market_ticker} on_position_opened hook failed: {e}",
              file=sys.stderr)
    _trade_log({"ts_epoch": open_ts, "ts": _now_cst(), "sport": adapter.name,
                "ticker": market_ticker, "name": name, "side": side,
                "situation": sig.get("situation", ""),
                "confidence": sig.get("confidence", ""),
                "reason": sig.get("reason", ""), "context": adapter.context(sig),
                "model_wp": sig.get("model_wp", ""), "signal_bid": buy_cents,
                "buy_price": buy_px, "fill_price": fill_price,
                "contracts": contracts, "tp_price": tp or "", "stop_price": stop,
                "pv_entry": pv_entry, "status": "OPEN"})

    if tp is None:
        print(f"  [TRADE] no TP by {adapter.name} policy — holding {contracts} "
              f"(guardian still enforces stops/bands)")
    else:
        # spread gate on the SELL too: an unstable book defers the TP to the
        # guardian (which re-checks the spread every cycle before placing).
        b_q, a_q = await _quote(client, market_ticker, side)
        if b_q is not None and a_q is not None and not _spread_ok(b_q, a_q):
            print(f"  [TRADE] spread {b_q}/{a_q}c > {SPORT_SPREAD_MAX_C}c — "
                  f"TP deferred; guardian places it once the book is stable")
        else:
            # never-sell-naked: even right after a confirmed fill, triple-confirm
            # the position (5s apart) before the TP sell goes out.
            have_c, _s, _p = await _confirm_open_position(client, market_ticker,
                                                          expect_side=side,
                                                          require_no_resting=True,
                                                          tag="TRADE")
            if have_c <= 0:
                print(f"  [TRADE] TP not placed — position not confirmed; "
                      f"guardian will handle it")
            else:
                await v1.place_tp_sell(client, market_ticker, side, have_c, tp)
                print(f"  [TRADE] TP sell @ {tp}c resting; guardian maintains it.")
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  PAPER guardian — simulated fills, exits, settlement, fees (user 07/17)
# ══════════════════════════════════════════════════════════════════════════════
def _paper_fee(price_c: int, contracts: int) -> float:
    """Kalshi taker fee: 0.07 * p * (1-p) per contract (maker fills pay 0)."""
    p = max(0.01, min(0.99, price_c / 100.0))
    return round(0.07 * p * (1 - p) * contracts, 2)


def _paper_close(tk: str, pos: dict, exit_px: int, kind: str, taker: bool) -> None:
    """Book a simulated exit: fees, P&L, CSV close, bank update, log."""
    fee = _paper_fee(exit_px, pos["contracts"]) if taker else 0.0
    proceeds = exit_px * pos["contracts"] / 100.0 - fee
    pnl = round(proceeds - pos["cost_usd"], 2)
    _PAPER_POS.pop(tk, None)
    _PAPER_STRIKES.pop(tk, None)
    _trade_log_close(tk, pos["open_ts"],
                     {"ts_close": _now_cst(), "realized_pnl": pnl,
                      "pv_close": "", "pv_delta_pct": ""},
                     csv_path=PAPER_TRADE_CSV)
    book = BOOKS.get(pos["sport"])
    if book:
        book.register_close(tk, pnl)
        bank_line = " | " + book.status_line()
    else:
        bank_line = ""
    print(f"  [PAPER-CLOSE] {tk} {kind.upper()} @ {exit_px}c x{pos['contracts']} "
          f"→ P&L ${pnl:+.2f} (entry {pos['fill_px']}c, fees "
          f"${pos['entry_fee'] + fee:.2f}){bank_line}")


async def _paper_guardian(client) -> None:
    """
    Every MAIN_PAPER_POLL_S: simulate the whole order lifecycle against the
    LIVE book (read-only):
      entries — resting limit fills when the ask crosses our limit (taker fee)
                or the bid trades through it (maker, no fee); expire unfilled
                after the sport's fill window (never chase);
      exits   — resting TP fills when bid >= tp (maker); entry-relative stop
                and hard floor with the sport's strike count (taker, crossing
                3c); adapter exit rules (baseball score-flip) immediately;
                settlement closes at 100/0 when the market finalizes.
    """
    while not _STOP.is_set():
        await asyncio.sleep(MAIN_PAPER_POLL_S)
        try:
            await _paper_tick(client)
        except Exception as e:
            print(f"  [PAPER] tick failed: {e}", file=sys.stderr)


async def _paper_tick(client) -> None:
        # ── 1) entry fills ────────────────────────────────────────────────────
        for tk, o in list(_PAPER_ORDERS.items()):
            try:
                md = await client.req("GET", f"/markets/{tk}")
                mkt = md.get("market", {}) or {}
            except Exception:
                continue
            side = o["side"]
            bid_c = ks._cents(mkt.get(f"{side}_bid_dollars"))
            ask_c = ks._cents(mkt.get(f"{side}_ask_dollars"))
            fill_px = taker = None
            if ask_c is not None and ask_c <= o["limit"]:
                fill_px, taker = ask_c, True          # ask crossed us → take it
            elif bid_c is not None and bid_c < o["limit"]:
                fill_px, taker = o["limit"], False    # traded through → maker fill
            if fill_px is None:
                if time.time() - o["placed_ts"] > o["timeout_s"]:
                    _PAPER_ORDERS.pop(tk, None)
                    print(f"  [PAPER] {tk} entry expired unfilled after "
                          f"{o['timeout_s']}s — cancelled (never chase)")
                continue
            _PAPER_ORDERS.pop(tk, None)
            fee = _paper_fee(fill_px, o["contracts"]) if taker else 0.0
            cost = round(fill_px * o["contracts"] / 100.0 + fee, 2)
            pos = {**o, "fill_px": fill_px, "entry_fee": fee, "cost_usd": cost,
                   "open_ts": time.time()}
            _PAPER_POS[tk] = pos
            book = BOOKS.get(o["sport"])
            if book:
                book.register_open(tk, cost)
            _trade_log({"ts_epoch": pos["open_ts"], "ts": _now_cst(),
                        "sport": o["sport"], "ticker": tk, "name": o["name"],
                        "side": side, "situation": o["situation"],
                        "confidence": o["confidence"], "reason": o["reason"],
                        "context": o["context"], "model_wp": o["model_wp"],
                        "signal_bid": o["signal_bid"], "buy_price": o["limit"],
                        "fill_price": fill_px, "contracts": o["contracts"],
                        "tp_price": o["tp"] or "", "stop_price":
                            (o["limit"] - o["stop_c"]) if o["stop_c"] else "",
                        "status": "OPEN"}, csv_path=PAPER_TRADE_CSV)
            print(f"  [PAPER-FILL] {tk} {o['name']} x{o['contracts']} @ {fill_px}c "
                  f"({'taker' if taker else 'maker'}, fee ${fee:.2f}) — "
                  f"TP {o['tp'] or 'none'}c, stop "
                  f"{(o['limit'] - o['stop_c']) if o['stop_c'] else '-'}c")

        # ── 2) exits on open paper positions ─────────────────────────────────
        for tk, p in list(_PAPER_POS.items()):
            try:
                md = await client.req("GET", f"/markets/{tk}")
                mkt = md.get("market", {}) or {}
            except Exception:
                continue
            side = p["side"]
            status = str(mkt.get("status") or "").lower()
            result = str(mkt.get("result") or "").lower()
            if result in ("yes", "no") or status in ("settled", "finalized",
                                                     "determined"):
                win = result == side
                _paper_close(tk, p, 100 if win else 0, "settle", taker=False)
                continue
            bid_c = ks._cents(mkt.get(f"{side}_bid_dollars"))
            if bid_c is None:
                continue
            # resting TP: fills the moment the bid reaches it (maker, no fee)
            if p.get("tp") and bid_c >= int(p["tp"]):
                _paper_close(tk, p, int(p["tp"]), "tp", taker=False)
                continue
            # adapter exit rules (e.g. baseball score-flip) — immediate
            adapter = ADAPTERS.get(p["sport"])
            if adapter is not None:
                try:
                    fire, why, _imm = await adapter.exit_check(
                        client, tk, p["fill_px"], bid_c, side, {})
                except Exception:
                    fire = False
                if fire:
                    print(f"  [PAPER] {tk} adapter exit: {why}")
                    _paper_close(tk, p, max(1, bid_c - SPORT_STOP_SLIP_C),
                                 "sportexit", taker=True)
                    continue
            # entry-relative stop + hard floor (sport's strike count)
            hit_stop = p["stop_c"] and bid_c <= p["fill_px"] - p["stop_c"]
            hit_floor = (p["floor_c"]
                         and SPORT_STOP_MIN_BID_C <= bid_c <= p["floor_c"])
            if hit_stop or hit_floor:
                n = _PAPER_STRIKES.get(tk, 0) + 1
                _PAPER_STRIKES[tk] = n
                if n >= p["stop_confirm"]:
                    _paper_close(tk, p, max(1, bid_c - SPORT_STOP_SLIP_C),
                                 "stop" if hit_stop else "floor", taker=True)
                continue
            _PAPER_STRIKES.pop(tk, None)


async def _paper_logger() -> None:
    """Every SPORT_POS_LOG_S: paper book snapshot (orders, positions, banks)."""
    while not _STOP.is_set():
        parts = [f"{tk}{{x{p['contracts']} @ {p['fill_px']}c, tp:{p.get('tp')}}}"
                 for tk, p in _PAPER_POS.items()]
        print(f"  [PAPER-BOOK] resting={len(_PAPER_ORDERS)} "
              f"open={{{', '.join(parts)}}} | "
              + " | ".join(b.status_line() for b in BOOKS.values())
              + f"  ({_now_cst()})")
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=SPORT_POS_LOG_S)
            return
        except asyncio.TimeoutError:
            pass


# ══════════════════════════════════════════════════════════════════════════════
#  Startup adoption — monitor positions that already exist when the bot launches
# ══════════════════════════════════════════════════════════════════════════════
async def _adopt_existing_positions(client, traded: set) -> None:
    """
    Launch-time inventory of positions ALREADY open in the account (prior runs,
    the v1/v2 bots, or manual buys).  Every position whose series resolves to a
    CONFIGURED sport is ADOPTED:
      • registered in _FILLED_ORDERS with its cost basis as the entry, so the
        guardian monitors it from its first cycle — profit side (the sport's TP
        policy re-placed if no sell is resting, plus the band ceiling) and loss
        side (per-sport stop-loss + hard floor);
      • its match is claimed in ``traded`` (no second buy on it this session);
      • an ADOPTED row goes to the trade CSV, and on close its realized P&L is
        recorded there AND drawn against the sport's bank (a big loss on an
        adopted position can therefore bank-halt that sport — intended).
    Positions of sports NOT in MAIN_SPORTS_LIST are listed but never touched.
    """
    try:
        pd = await client.req("GET", "/portfolio/positions", params={"limit": 1000})
        positions = [p for p in pd.get("market_positions", [])
                     if abs(int(float(p.get("position_fp", "0")))) > 0]
        resting = await v1.resting_orders(client)
        smap = await ks._sports_series(client)
    except Exception as e:
        print(f"  [ADOPT] startup position scan failed: {e} — the guardian will "
              f"still pick open positions up on its normal cycle", file=sys.stderr)
        return
    if not positions:
        print("  [ADOPT] no existing positions — nothing to monitor from prior runs.")
        return
    resting_tickers = {o.get("ticker") for o in resting}
    print(f"\n=== ADOPT: {len(positions)} existing position(s) found at launch ===")
    adopted = 0
    for p in positions:
        tk = p.get("ticker", "")
        sp = str(smap.get(ks._series_of(tk), {}).get("sport", "")).lower()
        adapter = ADAPTERS.get(sp)
        have = abs(int(float(p.get("position_fp", "0"))))
        side = "yes" if float(p.get("position_fp", "0")) >= 0 else "no"
        if adapter is None:
            where = ("in the TBD pipeline (activate via MAIN_SPORTS_LIST to manage it)"
                     if sp in _TBD_SET else f"not in {sorted(_SPORTS_SET)}")
            print(f"  [ADOPT] {tk} ({have} {side}) sport={sp or 'unknown'} {where} "
                  f"— out of scope, left alone")
            continue
        entry = _basis_entry({}, p, have)                 # cost basis (cents)
        try:
            bid = await v1._bid_price(client, tk, side)
        except Exception:
            bid = None
        bid_c = round(bid * 100) if bid is not None else None
        unreal = ((bid_c - entry) * have / 100.0
                  if (bid_c is not None and entry) else None)
        if tk in resting_tickers:
            tp_txt = "sell already resting"
        else:
            tp_plan = adapter.tp_for_entry(tk, entry) if entry else None
            tp_txt = (f"TP {min(int(tp_plan), SPORT_MAX_TP_C)}c (guardian places)"
                      if tp_plan else "hold (policy; band ceiling "
                                      f"{adapter.cfg.tp_ceiling_c}c still locks wins)")
        stop_txt = (f"stop {max(1, entry - adapter.cfg.stop_loss_c)}c"
                    if (adapter.cfg.stop_loss_c > 0 and entry)
                    else f"stop: floor {adapter.cfg.sl_floor_c}c only")
        open_ts = time.time()
        _FILLED_ORDERS[tk] = {"sport": sp, "side": side, "contracts": have,
                              "buy_at": entry or None, "tp": None, "name": "",
                              "open_ts": open_ts, "adopted": True,
                              "basis_cost": round(have * (entry or 0) / 100.0, 2),
                              "pv_entry": ""}
        traded.add(tk)                                    # no re-buy on this market
        _ledger_add(_event_of(tk))                        # one entry per match, EVER
        _trade_log({"ts_epoch": open_ts, "ts": _now_cst(), "sport": sp,
                    "ticker": tk, "name": "", "side": side, "situation": "ADOPTED",
                    "confidence": "", "reason": "existing position adopted at startup "
                                                "(entry = cost basis)",
                    "signal_bid": bid_c or "", "buy_price": entry or "",
                    "contracts": have, "status": "OPEN"})
        print(f"  [ADOPT] [{sp}] {tk}: {have} {side} @ basis {entry}c | "
              f"bid {bid_c if bid_c is not None else '?'}c | unrealized "
              + (f"${unreal:+.2f}" if unreal is not None else "n/a")
              + f" | {tp_txt} | {stop_txt}")
        adopted += 1
    print(f"  [ADOPT] monitoring {adopted} existing position(s) for profit/stop-loss "
          f"(guardian cycle every {SPORT_TP_GUARD_S}s).\n")


# ══════════════════════════════════════════════════════════════════════════════
#  Guardian — close detection, band exits, stop-loss, adapter exits, TP upkeep
# ══════════════════════════════════════════════════════════════════════════════
async def _cancel_match_orders(client, ticker: str) -> None:
    event = _event_of(ticker)
    for o in await v1.resting_orders(client):
        if _event_of(o.get("ticker", "")) == event:
            await client.req("DELETE", f"/portfolio/events/orders/{o['order_id']}")


def _basis_entry(info: dict, pos: dict, have: int) -> int:
    entry = info.get("buy_at")
    if not entry and have:
        cost = float(pos.get("total_traded_dollars")
                     or pos.get("market_exposure_dollars") or 0)
        entry = round(cost / have * 100)
    return int(entry or 0)


async def _exit_position(client, ticker, side, tag, why, bid_c, recheck=None,
                         risk_off: bool = False) -> bool:
    """Cancel the match's resting orders and exit crossing the bid.

    Spread gate (user rule 07/12): a bid/ask spread wider than
    SPORT_SPREAD_MAX_C means the book is unstable — wait up to
    SPORT_SPREAD_TIMEOUT_S for it to stabilize, then RE-VALIDATE the exit
    condition (``recheck``, sync or async, called with the fresh bid) and only
    sell if it still holds.  A book that never stabilizes defers the exit to
    the next guardian cycle.

    ``risk_off=True`` (v5, user 07/16): STOP-LOSS/floor exits skip the spread
    wait ENTIRELY — the 07/16 forensics found the spread guard deadlocked
    losing positions to $0 (IGNHAI/BOEPOH: 'book unstable' deferrals every
    cycle while the match died).  The guard may defer TP placement, never a
    risk-off exit.  The never-sell-naked triple confirm still applies."""
    bid0, ask0 = await _quote(client, ticker, side)
    if (not risk_off and bid0 is not None and ask0 is not None
            and not _spread_ok(bid0, ask0)):
        bid_new, stable = await _await_stable_quote(client, ticker, side, tag=tag)
        if not stable:
            print(f"  [{tag}] {ticker}: book never stabilized — exit deferred "
                  f"to next guardian cycle")
            return False
        if bid_new is None or bid_new < SPORT_STOP_MIN_BID_C:
            return False                        # no sane quote to exit into
        if recheck is not None:
            res = recheck(bid_new)
            if asyncio.iscoroutine(res):
                res = await res
            if not res:
                print(f"  [{tag}] {ticker}: condition no longer holds at stable "
                      f"bid {bid_new}c — exit cancelled")
                return False
            print(f"  [{tag}] {ticker}: re-validated at stable bid {bid_new}c — exiting")
        bid_c = bid_new
    # never-sell-naked (user 07/12): triple-confirm the open position (5s apart,
    # positions + resting orders each round) before selling.  Exits REPLACE any
    # resting TP, so a resting order is not a blocker here — it is cancelled
    # after confirmation, just before the sell goes out.
    have, side_c, _pos = await _confirm_open_position(client, ticker,
                                                      expect_side=side,
                                                      require_no_resting=False,
                                                      tag=tag)
    if have <= 0:
        return False
    try:
        await _cancel_match_orders(client, ticker)
    except Exception as e:
        print(f"  [{tag}] {ticker} cancel match orders failed: {e}", file=sys.stderr)
    exit_px = max(1, bid_c - SPORT_STOP_SLIP_C)
    print(f"  [{tag}] {ticker} {why} — exiting {have} {side} @ {exit_px}c")
    try:
        await v1.place_tp_sell(client, ticker, side, have, exit_px)
        return True
    except Exception as e:
        print(f"  [{tag}] {ticker} exit sell failed: {e}", file=sys.stderr)
        return False


async def _tp_guardian(client, traded: set) -> None:
    """Every SPORT_TP_GUARD_S over ALL open in-scope positions (see module doc:
    close detection → band exits → per-sport stop-loss → adapter exit rules →
    TP maintenance).  Sells only positions whose series resolves to a configured
    sport; taxonomy fetch failure = no sells that cycle (fail safe)."""
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

        # ── close detection: CSV close + per-sport bank P&L + re-arm ─────────
        for tk in list(_FILLED_ORDERS):
            if tk not in open_tickers:
                info = _FILLED_ORDERS.pop(tk, None) or {}
                for d_ in (_STOP_STRIKES, _BAND_STRIKES, _EXIT_STRIKES):
                    d_.pop(tk, None)
                ev = _event_of(tk)
                if SPORT_REBUY:
                    for d in [x for x in traded if _event_of(x) == ev]:
                        traded.discard(d)
                pnl = None
                try:
                    pnl = await _realized_pnl(client, tk, info.get("side", "yes"),
                                              info.get("open_ts", 0))
                    if info.get("adopted") and isinstance(pnl, (int, float)):
                        # adopted at startup: fills since adoption only contain
                        # the EXIT cash-in — subtract the entry cost basis
                        pnl = round(pnl - info.get("basis_cost", 0.0), 2)
                    pv_close = round(await _portfolio_value(client), 2)
                    pve = info.get("pv_entry")
                    pct = (round((pv_close - pve) / pve * 100, 2)
                           if isinstance(pve, (int, float)) and pve else "")
                    _trade_log_close(tk, info.get("open_ts", ""), {
                        "ts_close": _now_cst(), "pv_close": pv_close,
                        "realized_pnl": pnl, "pv_delta_pct": pct})
                except Exception as e:
                    print(f"  [TRADECSV] close record failed: {e}", file=sys.stderr)
                book = BOOKS.get(info.get("sport", ""))
                if book:
                    book.register_close(tk, pnl)      # may trigger the bank-halt banner
                    print(f"  [BANK] {book.status_line()}")
                print(f"  [GUARD] {tk} position closed (P&L "
                      f"{'$%.2f' % pnl if isinstance(pnl, float) else 'n/a'}) — "
                      + ("match re-eligible" if SPORT_REBUY
                         else "SPORT_REBUY=FALSE, match stays done"))

        # sell scope: configured sports only
        try:
            smap = await ks._sports_series(client)
        except Exception as e:
            print(f"  [GUARD] sports taxonomy fetch failed: {e} — no sells this cycle",
                  file=sys.stderr)
            continue

        def _sport_of(tk: str) -> str:
            return str(smap.get(ks._series_of(tk), {}).get("sport", "")).lower()

        stopped: set = set()

        # ── hard price-band exits (ceiling immediate; floor debounced) ───────
        # Ceiling (profit-lock) and floor (loss cut) are PER-SPORT: each
        # adapter's cfg.tp_ceiling_c / cfg.sl_floor_c (falling back to the
        # global SPORT_TP_CEILING_C / SPORT_SL_FLOOR_C).  For tennis under v4
        # (user 07/13) these are the ONLY exits: 97c ceiling, 7c floor.
        for p in positions:
            tk = p.get("ticker", "")
            adapter = ADAPTERS.get(_sport_of(tk))
            if adapter is None:
                continue
            ceiling_c, floor_c = adapter.cfg.tp_ceiling_c, adapter.cfg.sl_floor_c
            if ceiling_c <= 0 and floor_c <= 0:
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
            hit_tp = ceiling_c > 0 and bid_c >= ceiling_c
            hit_sl = floor_c > 0 and SPORT_STOP_MIN_BID_C <= bid_c <= floor_c
            if not (hit_tp or hit_sl):
                _BAND_STRIKES.pop(tk, None)
                continue
            if hit_sl and not hit_tp:
                need = max(1, adapter.cfg.stop_confirm)      # v5 tennis: 1 strike
                strikes = _BAND_STRIKES.get(tk, 0) + 1
                _BAND_STRIKES[tk] = strikes
                if strikes < need:
                    print(f"  [BANDEXIT] {tk} bid {bid_c}c <= {floor_c}c "
                          f"floor — breach {strikes}/{need}, watching")
                    continue
            kind = (f"bid {bid_c}c hit take-profit ceiling {ceiling_c}c"
                    if hit_tp else f"bid {bid_c}c hit stop floor {floor_c}c")

            def _band_recheck(b, _c=ceiling_c, _f=floor_c) -> bool:   # still out?
                if _c > 0 and b >= _c:
                    return True
                return _f > 0 and SPORT_STOP_MIN_BID_C <= b <= _f

            if await _exit_position(client, tk, side, "BANDEXIT", kind, bid_c,
                                    recheck=_band_recheck,
                                    risk_off=(hit_sl and not hit_tp)):
                stopped.add(tk)
                _BAND_STRIKES.pop(tk, None)

        # ── per-sport stop-loss (entry-relative, adapter-configured) ─────────
        for p in positions:
            tk = p.get("ticker", "")
            if tk in stopped:
                continue
            sp = _sport_of(tk)
            adapter = ADAPTERS.get(sp)
            if adapter is None or adapter.cfg.stop_loss_c <= 0:
                continue
            have = abs(int(float(p.get("position_fp", "0"))))
            if have <= 0:
                continue
            entry = _basis_entry(_FILLED_ORDERS.get(tk, {}), p, have)
            if not entry:
                continue
            side = "yes" if float(p.get("position_fp", "0")) >= 0 else "no"
            try:
                bid = await v1._bid_price(client, tk, side)
            except Exception:
                bid = None
            bid_c = round(bid * 100) if bid is not None else None
            trigger = entry - adapter.cfg.stop_loss_c
            deep = entry - SPORT_STOP_DEEP_C
            if bid_c is None or bid_c < SPORT_STOP_MIN_BID_C:
                continue                               # empty book ≠ collapse
            if bid_c > trigger:
                _STOP_STRIKES.pop(tk, None)
                continue
            strikes = _STOP_STRIKES.get(tk, 0) + 1
            _STOP_STRIKES[tk] = strikes
            need = 1 if bid_c <= deep else max(1, adapter.cfg.stop_confirm)
            if strikes < need:
                print(f"  [STOPLOSS] {tk} bid {bid_c}c <= {trigger}c — breach "
                      f"{strikes}/{need}, watching")
                continue
            if await _exit_position(client, tk, side, "STOPLOSS",
                                    f"bid {bid_c}c <= entry {entry}c - "
                                    f"{adapter.cfg.stop_loss_c}c ({trigger}c) x{strikes}",
                                    bid_c,
                                    recheck=lambda b, t=trigger: b <= t,
                                    risk_off=True):
                stopped.add(tk)

        # ── adapter-specific exit rules (tennis favorite exits, …) ───────────
        for p in positions:
            tk = p.get("ticker", "")
            if tk in stopped:
                continue
            sp = _sport_of(tk)
            adapter = ADAPTERS.get(sp)
            if adapter is None or type(adapter).exit_check is SportAdapter.exit_check:
                continue                               # base no-op → skip the fetches
            have = abs(int(float(p.get("position_fp", "0"))))
            if have <= 0:
                continue
            side = "yes" if float(p.get("position_fp", "0")) >= 0 else "no"
            entry = _basis_entry(_FILLED_ORDERS.get(tk, {}), p, have)
            try:
                bid = await v1._bid_price(client, tk, side)
            except Exception:
                bid = None
            bid_c = round(bid * 100) if bid is not None else None
            try:
                fire, why, immediate = await adapter.exit_check(
                    client, tk, entry or None, bid_c, side, p)
            except Exception as e:
                print(f"  [SPORTEXIT] {tk} exit_check failed: {e}", file=sys.stderr)
                continue
            if not fire:
                _EXIT_STRIKES.pop(tk, None)
                continue
            strikes = _EXIT_STRIKES.get(tk, 0) + 1
            _EXIT_STRIKES[tk] = strikes
            need = 1 if immediate else SPORT_FAVX_CONFIRM
            if strikes < need:
                print(f"  [SPORTEXIT] {tk} {why} — breach {strikes}/{need}, watching")
                continue
            if bid_c is None or bid_c < SPORT_STOP_MIN_BID_C:
                continue                               # no sane quote to exit into

            async def _sportexit_recheck(b, _ad=adapter, _tk=tk, _entry=entry,
                                         _side=side, _p=p) -> bool:
                f2, _w2, _i2 = await _ad.exit_check(client, _tk, _entry or None,
                                                    b, _side, _p)
                return f2

            if await _exit_position(client, tk, side, "SPORTEXIT",
                                    f"{why} (entry {entry}c, even at a loss)", bid_c,
                                    recheck=_sportexit_recheck, risk_off=True):
                stopped.add(tk)
                _EXIT_STRIKES.pop(tk, None)

        # ── TP maintenance (adapter policy; None = intentionally no TP) ──────
        candidates = []
        for p in positions:
            tk = p.get("ticker", "")
            if tk in resting_tickers or tk in stopped:
                continue
            if _sport_of(tk) not in _SPORTS_SET:
                continue
            candidates.append(p)
        if not candidates:
            continue
        for c_ in candidates:
            tk = c_.get("ticker", "")
            adapter = ADAPTERS.get(_sport_of(tk))
            if adapter is None:
                continue
            side_hint = "yes" if float(c_.get("position_fp", "0")) >= 0 else "no"
            b_q, a_q = await _quote(client, tk, side_hint)   # spread gate first
            if b_q is not None and a_q is not None and not _spread_ok(b_q, a_q):
                print(f"  [GUARD] {tk} spread {b_q}/{a_q}c > {SPORT_SPREAD_MAX_C}c "
                      f"— TP deferred to next cycle (book unstable)")
                continue
            # never-sell-naked (user 07/12): triple-confirm the position AND the
            # absence of any resting order (5s apart) before placing the TP.
            have, side, pos_now = await _confirm_open_position(
                client, tk, require_no_resting=True, tag="GUARD")
            if have <= 0:
                continue
            info = _FILLED_ORDERS.get(tk, {})
            tp = (int(info["tp"]) if info.get("tp") else
                  adapter.tp_for_entry(tk, _basis_entry(info, pos_now, have)))
            if tp is None:
                continue                               # policy: hold (e.g. SPORT_SELL=FALSE)
            tp = min(int(tp), SPORT_MAX_TP_C)
            print(f"  [GUARD] {tk} holding {have} {side} (triple-confirmed), no "
                  f"resting sell — placing TP @ {tp}c ({adapter.name} policy)")
            try:
                await v1.place_tp_sell(client, tk, side, have, tp)
                _FILLED_ORDERS.setdefault(tk, {"sport": adapter.name, "side": side,
                                               "contracts": have, "buy_at": None,
                                               "tp": tp})
            except Exception as e:
                print(f"  [GUARD] {tk} place TP failed: {e}", file=sys.stderr)


async def _positions_logger(client) -> None:
    """Every SPORT_POS_LOG_S: open positions + each sport's bank status."""
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
                buy_at = _basis_entry(_FILLED_ORDERS.get(tk, {}), p, have)
                tp = _FILLED_ORDERS.get(tk, {}).get("tp")
                parts.append(f"{tk}{{contracts:{have}, buy_at:{buy_at}, "
                             f"plan_to_sell:{tp if tp else 'hold'}}}")
            print(f"  [POSITIONS] orders{{{', '.join(parts)}}}  ({_now_cst()})")
            print(f"  [BANKS] " + " | ".join(b.status_line() for b in BOOKS.values()))
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=SPORT_POS_LOG_S)
            return
        except asyncio.TimeoutError:
            pass


async def _pv_target_guard(client, starting_pv: float, target_pv,
                           loss_floor_pv=None) -> None:
    """GLOBAL profit-target / loss-limit halt (per-sport banks are separate)."""
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
            print(f"  [LOSS-LIMIT] PV ${pv:.2f} <= floor ${loss_floor_pv:.2f} — "
                  f"stopping new buys, draining, halting.")
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
    print(f"  [MAIN TARGET-PV HALT] halting"
          f"{' + machine shutdown' if HALT_MACHINE_SHUTDOWN else ''}.")
    if HALT_MACHINE_SHUTDOWN:
        print("  [MAIN TARGET-PV HALT] initiating machine shutdown in 30s …")
        os.system("shutdown /s /f /t 30")
    _STOP.set()


# ══════════════════════════════════════════════════════════════════════════════
#  Watchers + refresh loops
# ══════════════════════════════════════════════════════════════════════════════
async def _watch_ticker(c, adapter, tk, traded, dropped, sem, main_by_sport) -> None:
    """One watcher per match: poll every adapter.cfg.poll_s; on BUY size, gate
    on the sport's bank and execute; then stop (one trade per match per run)."""
    book = BOOKS[adapter.name]
    misses = 0
    while tk not in traded:
        if _TARGET_REACHED.is_set() or book.halted:
            return
        _pause = _PAUSE_UNTIL - time.time()
        if _pause > 0:
            await asyncio.sleep(min(_pause + 1, SPORT_NOTSTARTED_POLL_S))
            continue
        if not any(m["ticker"] == tk for m in main_by_sport.get(adapter.name, [])):
            return                                     # dropped from the watchlist
        sig = None
        try:
            async with sem:
                sig = await adapter.evaluate(c, tk)
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
            name = sig.get("player") or sig.get("team")
            if sig.get("action") == "BUY" and SPORT_PLACE_ORDERS and not decided and name:
                mkt_side = await adapter.market_for(c, tk, name)
                if not mkt_side:
                    print(f"  [{tk}] no market ticker for {name!r}; skip")
                else:
                    mkt, side = mkt_side
                    n_contracts = adapter.size_contracts(sig)
                    if n_contracts != adapter.cfg.contracts:
                        print(f"  [SIZEUP] {adapter.name} {name} — buying {n_contracts} "
                              f"(= {adapter.cfg.contracts} x{adapter.cfg.ultra_mult})")
                    claimed = {tk}
                    traded.add(tk)
                    if not SPORT_REBUY:                # one trade per match: claim all sides
                        for _mtk in await adapter.claim_tickers(c, tk):
                            traded.add(_mtk)
                            claimed.add(_mtk)
                    placed = True                      # on error keep the claim (no hot retry)
                    try:
                        placed = await execute_trade(
                            c, adapter, book, mkt, side, name, sig,
                            contracts=n_contracts,
                            # spread gate revalidation: re-run this match's full
                            # evaluation once the book is stable
                            revalidate=lambda: adapter.evaluate(c, tk))
                    except Exception as e:
                        print(f"  [{tk}] trade error: {e}", file=sys.stderr)
                    if placed:
                        return                         # one trade per match per run
                    for _t in claimed:                 # aborted pre-order (spread/bank/
                        traded.discard(_t)             # pause) → un-claim, keep watching
            elif sig.get("action") == "BUY" and decided:
                print(f"  [{tk}] leader at {lb}c (> {SPORT_DECIDED_BID}c) — decided, "
                      f"not buying")
        await asyncio.sleep(adapter.cfg.poll_s)


async def _main_refresh(c, main_by_sport: dict, pending_by_sport: dict) -> None:
    while not _STOP.is_set():
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=SPORT_MAIN_REFRESH_S)
            return
        except asyncio.TimeoutError:
            pass
        if _TARGET_REACHED.is_set():
            continue
        for sport, adapter in ADAPTERS.items():
            if BOOKS[sport].halted:
                main_by_sport[sport] = []
                pending_by_sport[sport] = []
                continue
            try:
                fresh = await _live_matches_in_band(c, adapter)
            except Exception as e:
                print(f"  [main-refresh {sport}] {e}", file=sys.stderr)
                continue
            main_by_sport[sport] = [m for m in fresh if not _is_pending(m)]
            pending_by_sport[sport] = [m for m in fresh if _is_pending(m)]
            adapter.on_refresh()
            print(f"  [main-refresh {sport}] live={len(main_by_sport[sport])} "
                  f"pending={len(pending_by_sport[sport])}  ({_now_cst()})")


async def _pending_promoter(client, main_by_sport: dict, pending_by_sport: dict) -> None:
    while not _STOP.is_set():
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=SPORT_PENDING_REFRESH_S)
            return
        except asyncio.TimeoutError:
            pass
        if _TARGET_REACHED.is_set():
            continue
        for sport in ADAPTERS:
            pend = pending_by_sport.get(sport, [])
            candidates = [m for m in pend if not _is_pending(m)]
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
            have = {m["ticker"] for m in main_by_sport.setdefault(sport, [])}
            for m, ok in zip(candidates, ok_flags):
                if ok and m["ticker"] not in have:
                    main_by_sport[sport].append(m)
                elif not ok:
                    print(f"  [promote {sport}] {m['ticker']} below MIN_VOLUME_USD="
                          f"${MIN_VOLUME_USD:,.0f} at start — dropped")
            handled = {m["ticker"] for m in candidates}
            pending_by_sport[sport] = [m for m in pend if m["ticker"] not in handled]
            if any(ok_flags):
                print(f"  [promote {sport}] {sum(ok_flags)} match(es) now live → "
                      f"watchlist  ({_now_cst()})")


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════
async def run() -> None:
    _setup_logging()
    print(f"[MAIN-BOT] {'*** PAPER MODE *** ' if MAIN_PAPER else ''}"
          f"active={sorted(ADAPTERS)}  pipeline(TBD)={sorted(TBD_ADAPTERS)}  "
          f"min_vol=${MIN_VOLUME_USD:,.0f}  top_n={TOP_N_PER_SPORT}  "
          f"place_orders={SPORT_PLACE_ORDERS}  rebuy={SPORT_REBUY}  DRY_RUN={v1.DRY_RUN}")
    for sport, adapter in ADAPTERS.items():
        print(f"[MAIN-BOT]   {sport:<10s}: {adapter.describe()}")
    for sport, adapter in TBD_ADAPTERS.items():
        print(f"[MAIN-BOT]   {sport:<10s}: TBD (structure OK, not trading) — "
              f"{adapter.describe()}")
    if TBD_ADAPTERS:
        print(f"[MAIN-BOT]   to activate a TBD sport: implement its prediction "
              f"model, then move it from MAIN_SPORTS_LIST_TBD to MAIN_SPORTS_LIST.")
    if not ADAPTERS:
        print("[MAIN-BOT] no usable sport adapters — nothing to do.")
        return
    c = KalshiClient()
    try:
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

        # ── monitor EXISTING positions from minute one ────────────────────────
        # Adopt prior-run/manual positions and start the guardian + loggers
        # BEFORE the slow startup steps (rankings scrape, discovery), so
        # profit-taking and stop-loss protection are live immediately.
        traded: set = set()
        dropped: set = set()
        if MAIN_PAPER:
            print("\n" + "#" * 74)
            print("#  PAPER TRADING MODE — no real orders, real account untouched.       #")
            print("#  Simulated fills/exits vs the live book; results in                 #")
            print(f"#  {Path(PAPER_TRADE_CSV).name:<66s}  #")
            print("#" * 74 + "\n")
            asyncio.create_task(_paper_guardian(c))
            asyncio.create_task(_paper_logger())
        else:
            await _adopt_existing_positions(c, traded)
            asyncio.create_task(_tp_guardian(c, traded))
            asyncio.create_task(_positions_logger(c))
            asyncio.create_task(_pv_target_guard(c, starting_pv, target_pv,
                                                 loss_floor_pv))

        # ── DATA PREFLIGHT + per-sport startup ────────────────────────────────
        # user 07/13: before trading, guarantee each active sport's data is
        # scraped FOR TODAY (by last-updated timestamp) — baseball_data.csv and
        # tennis_rankings.csv. Each adapter's startup() checks its CSV's date
        # and scrapes if it is missing or not from today's CST date.
        print(f"\n=== DATA PREFLIGHT: ensuring today's data is scraped "
              f"({_now_cst()}) ===")
        for sport, adapter in ADAPTERS.items():
            try:
                await adapter.startup(c)
            except Exception as e:
                print(f"  [{sport}] startup/data-preflight failed: {e}", file=sys.stderr)

        # ── STEP 1: discovery per sport ───────────────────────────────────────
        main_by_sport: dict = {}
        pending_by_sport: dict = {}
        for sport, adapter in ADAPTERS.items():
            try:
                matches = await _live_matches_in_band(c, adapter)
            except Exception as e:
                print(f"  [{sport}] fetch error: {e}")
                matches = []
            main_by_sport[sport] = [m for m in matches if not _is_pending(m)]
            pending_by_sport[sport] = [m for m in matches if _is_pending(m)]

        print(f"\n=== STEP 1: live matches per sport, vol >= ${MIN_VOLUME_USD:,.0f}, "
              f"bid {SPORT_BID_LO}-{SPORT_BID_HI}c ===")
        for sport in ADAPTERS:
            live_n, pend_n = len(main_by_sport[sport]), len(pending_by_sport[sport])
            print(f"  {sport}: live={live_n} pending={pend_n}  "
                  f"{[(m['ticker'], round(m.get('usd_volume', 0))) for m in main_by_sport[sport]]}")

        # ── STEP 2: parallel watchers (guardian/loggers already running) ──────
        print(f"\n=== PARALLEL POLLING across {sorted(ADAPTERS)} "
              f"(concurrency {SPORT_MAX_CONCURRENCY}; Ctrl-C to stop) ===")
        asyncio.create_task(_main_refresh(c, main_by_sport, pending_by_sport))
        asyncio.create_task(_pending_promoter(c, main_by_sport, pending_by_sport))
        sem = asyncio.Semaphore(SPORT_MAX_CONCURRENCY)
        watchers: dict = {}
        while not _STOP.is_set():
            for tk, t in list(watchers.items()):
                if t.done():
                    watchers.pop(tk)
            if not _TARGET_REACHED.is_set():
                for sport, adapter in ADAPTERS.items():
                    if BOOKS[sport].halted:
                        continue                        # bank-halted → no new watchers
                    for m in main_by_sport.get(sport, []):
                        tk = m["ticker"]
                        if tk not in watchers and tk not in traded and tk not in dropped:
                            watchers[tk] = asyncio.create_task(_watch_ticker(
                                c, adapter, tk, traded, dropped, sem, main_by_sport))
                print(f"  [watch] {sum(1 for t in watchers.values() if not t.done())} "
                      f"active watcher(s); traded={len(traded)}; "
                      + "; ".join(b.status_line() for b in BOOKS.values())
                      + f"  ({_now_cst()})")
            else:
                print(f"  [DRAIN] target reached — no new buys; "
                      f"{len(_FILLED_ORDERS)} session position(s) open  ({_now_cst()})")
            try:
                await asyncio.wait_for(_STOP.wait(), timeout=SPORT_LIST_REFRESH_S)
            except asyncio.TimeoutError:
                pass
            if _STOP.is_set():
                break
        print("[MAIN-BOT] halt signalled — cancelling watchers.")
        for t in watchers.values():
            t.cancel()
    finally:
        await c.close()


# ── logging (rotating tee, main-prefixed) ─────────────────────────────────────
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
    """kalshi_main_YYYYMMDD.log in SPORT_LOG_DIR (customer logs folder)."""
    _PREFIX = "kalshi_main_"

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
        print(f"[MAIN-BOT] could not open log: {e}", file=sys.stderr)
        return
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.stdout = _Tee(sys.__stdout__, rot)
    sys.stderr = _Tee(sys.__stderr__, rot)
    print(f"[MAIN-BOT] logging to {rot.path.name}  (archive on day change)  ({_now_cst()})")


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
