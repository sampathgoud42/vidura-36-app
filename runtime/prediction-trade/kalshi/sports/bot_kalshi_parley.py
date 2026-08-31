#!/usr/bin/env python3
"""
bot_kalshi_parley.py — Kalshi PARLEY (multi-leg combo) bot.
===========================================================
Builds ONE combined market out of several *live* sports matches and buys it
with a market order.  A leg only joins the combo when the match is genuinely
in play and the price already says the leg is close to decided:

    leg = a match where ONE participant's YES price is > PARLEY_MIN_PROB_C
          (default 80c = "odds > 80%"), the match is AT LEAST in its second
          set, and THAT >80% participant is the one LEADING that set.

Legs are combined through Kalshi's multivariate event collections (the
exchange's own parlay primitive):

    POST /multivariate_event_collections/{collection_ticker}
         {"selected_markets": [{event_ticker, market_ticker, side:"yes"}, …],
          "with_market_payload": true}
      → {"event_ticker", "market_ticker", "market": {…quotes…}}

The combined market resolves YES only if EVERY leg resolves YES (the
collection's own rule: "will only resolve to YES if every associated market
resolves to YES"), so the combo pays the product of the legs — the classic
parlay payoff.  That market is then bought with a MARKET order.

MARKET ORDER (important): the Kalshi V2 create-order endpoint has NO market
order type — every order carries a price.  A market order is therefore sent
the way the exchange models one: a MARKETABLE **immediate-or-cancel** order
priced at the current ask + PARLEY_SLIPPAGE_C (hard-capped at
PARLEY_MAX_PRICE_C).  It sweeps the resting book instantly and cancels the
remainder instead of resting — never a hidden limit order sitting in the book.

WHICH MATCHES (config, same shape as the sports bot's per-sport knobs):
    PARLEY_SPORTS_LIST=tennis      sports to scan (DEFAULT: tennis only)
    PARLEY_MIN_PROB_C=80           a leg needs a YES price strictly ABOVE this
    PARLEY_MIN_SET=2               match must be at least in this set
    PARLEY_LEAD_SCOPE=current      which set the >80% player must lead:
                                   current | second | off
    PARLEY_MIN_LEGS=2              fewer qualifying legs than this → no parlay
    PARLEY_MAX_LEGS=0              0 = take EVERY qualifying match

LIVE-ONLY: a match reaches the combo only after passing all three liveness
gates the sports bot uses — Kalshi market status (postponed / delayed /
cancelled / suspended / retired / walkover … are dropped), the sport adapter's
own confirmation (tennis: SofaScore live statuses), and the Kalshi milestone
live-scoreboard flag (``live`` true, ``completed`` false).  A match that has
not started, or that has finished, can never become a leg.

RISK — identical mechanism to bot_kalshi_main (per-sport knobs, PARLEY_ prefix):
    PARLEY_BANK=100                session bankroll ($); 0 = unlimited.  A new
                                   parlay must FIT in what is left of the bank
    PARLEY_CONTRACTS=10            contracts per parlay order
    PARLEY_STOP_LOSS_PCT=50        realized session loss >= this % of the bank
                                   → BANK-HALT banner, no new parlays (open
                                   ones stay managed)
    PARLEY_TP_CEILING_C=97         resting take-profit sell
    PARLEY_STOP_LOSS_C=20          entry-relative stop (exit at entry-20c)
    PARLEY_STOP_CONFIRM=1          breach cycles before the stop fires
    PARLEY_SL_FLOOR_C=15           hard floor — never hold below this
    PARLEY_DAY_LOSS_HALT_USD=60    API-reconciled realized-loss brakes
    PARLEY_WEEK_LOSS_HALT_USD=150  (fills + settlements, never internal P&L)

and the same order-safety rules as the other bots: NEVER BUY NO (legs are
always the YES side of the leading participant's market), NEVER SELL NAKED
(every sell triple-confirms an open position first), spread gate before
placing a resting TP, one entry per combination (persistent ledger), and
PARLEY_PAPER=TRUE to run the whole pipeline against the live book with no
real order.

Run:
    python bot_kalshi_parley.py [customer]        # customer default "suma"
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

# The engine module performs the whole config/credential bootstrap (env files,
# customer dir, private key, dotenv guards) and exposes the shared helpers —
# importing it is how this bot inherits EXACTLY the sports bots' plumbing
# (spread gate, sell-confirm, trade CSV, P&L reconciliation, log rotation).
import bot_kalshi_main as eng                                   # noqa: E402
import bot_kalshi_sports_v1 as tv1                              # noqa: E402
from sport_adapters import create_adapter                       # noqa: E402
from sport_adapters.base import SportBook, SportConfig          # noqa: E402

ks = eng.ks
v1 = eng.v1
KalshiClient = eng.KalshiClient
CUSTOMER_DIR = eng.CUSTOMER_DIR


def _env(key: str, default):
    v = os.getenv(f"PARLEY_{key}")
    return default if v is None or str(v).strip() == "" else v


def _i(key: str, default: int) -> int:
    try:
        return int(float(_env(key, default)))
    except (TypeError, ValueError):
        return default


def _b(key: str, default: bool) -> bool:
    return str(_env(key, "TRUE" if default else "FALSE")).strip().upper() == "TRUE"


# ── selection ────────────────────────────────────────────────────────────────
SPORTS_LIST = [s.strip().lower() for s in
               str(_env("SPORTS_LIST", "tennis")).split(",") if s.strip()]
MIN_PROB_C = _i("MIN_PROB_C", 80)          # leg needs a YES price ABOVE this
MIN_SET = _i("MIN_SET", 2)                 # match must be at least in this set
LEAD_SCOPE = str(_env("LEAD_SCOPE", "current")).strip().lower()   # current|second|off
MIN_LEGS = max(2, _i("MIN_LEGS", 2))       # the exchange's own minimum is 2
MAX_LEGS = _i("MAX_LEGS", 0)               # 0 = every qualifying match
MIN_VOLUME_USD = float(_env("MIN_VOLUME_USD", os.getenv("MIN_VOLUME_USD", "5000")))
TOP_N = _i("TOP_N", 100)

# ── execution ────────────────────────────────────────────────────────────────
COLLECTION = str(_env("COLLECTION", "")).strip()   # blank = auto-pick
SLIPPAGE_C = _i("SLIPPAGE_C", 3)           # market order = ask + this, IOC
MAX_PRICE_C = _i("MAX_PRICE_C", 95)        # never pay more than this per contract
MIN_PRICE_C = _i("MIN_PRICE_C", 2)         # a combo cheaper than this is noise
MAX_OPEN = _i("MAX_OPEN", 1)               # concurrent open parlays
COOLDOWN_S = _i("COOLDOWN_S", 900)         # min gap between two parlays
SCAN_S = _i("SCAN_S", 60)                  # rescan cadence
GUARD_S = _i("GUARD_S", 120)               # guardian cadence
FILL_POLL_S = _i("FILL_POLL_S", 5)
FILL_WAIT_S = _i("FILL_WAIT_S", 30)
PLACE_ORDERS = _b("PLACE_ORDERS", True)
# A COMBINED MARKET IS BORN EMPTY. Verified live 08/14: a combo created through
# the collection endpoint comes back status=active with an orderbook of
# {"yes_dollars": [], "no_dollars": []} — bid 0 / ask 0, and it stays empty
# (no automated market maker quotes it).  A market order into an empty book
# fills NOTHING, which is the correct and safe outcome: the bot takes no
# position and releases the combination.  Set PARLEY_LIMIT_FALLBACK=TRUE to
# instead REST a good-till-cancelled buy at the theoretical price (the product
# of the leg probabilities, + PARLEY_SLIPPAGE_C) and wait PARLEY_FILL_WAIT_S
# for someone to take it — a maker entry rather than the market order.
LIMIT_FALLBACK = _b("LIMIT_FALLBACK", False)
PAPER = _b("PAPER", False)
# Creating the combined market is a POST to the exchange (Kalshi caps market
# creations at 5000/week).  Paper mode needs a REAL combined market to price
# against, so it creates one by default; FALSE prices the combo theoretically
# (product of the leg probabilities) and never touches the exchange.
PAPER_CREATE_MARKET = _b("PAPER_CREATE_MARKET", True)

_LEAD_SCOPES = {"current", "second", "off"}
if LEAD_SCOPE not in _LEAD_SCOPES:
    print(f"[PARLEY] PARLEY_LEAD_SCOPE={LEAD_SCOPE!r} invalid "
          f"(want {sorted(_LEAD_SCOPES)}) — falling back to 'current'",
          file=sys.stderr)
    LEAD_SCOPE = "current"

# ── risk: the SAME SportConfig/SportBook the per-sport banks use ─────────────
# SportConfig.load reads PARLEY_BANK / PARLEY_CONTRACTS / PARLEY_STOP_LOSS_PCT
# / … exactly like TENNIS_* and BASEBALL_* — one shared risk implementation.
CFG = SportConfig.load("parley", {
    "bank": 100,
    "contracts": 10,
    "stop_loss_pct": 50,
    "stop_loss_c": 20,          # entry-relative stop
    "stop_confirm": 1,          # one strike, like tennis v5
    "tp_ceiling_c": 97,         # resting profit lock
    "sl_floor_c": 15,           # gapped-through backstop (parlays are cheap)
    "day_loss_halt_usd": 60,
    "week_loss_halt_usd": 150,
    "poll_s": 60,
    "max_live_hours": 6,
})
BOOK = SportBook(CFG)

TRADE_CSV = str(_env("TRADE_CSV",
                     str(CUSTOMER_DIR / "trade_history" /
                         ("paper_parley.csv" if PAPER else "trade_history_parley.csv"))))
LEDGER_PATH = Path(_env("LEDGER", str(CUSTOMER_DIR / "trade_history" /
                                      ("parley_ledger_paper.json" if PAPER
                                       else "parley_ledger.json"))))
LEDGER_KEEP_DAYS = _i("LEDGER_KEEP_DAYS", 3)

_LEDGER: dict = {}                 # combo key -> epoch of the entry
_OPEN: dict = {}                   # combined market ticker -> position info
_STRIKES: dict = {}                # combined ticker -> consecutive stop breaches
_LAST_ENTRY_TS = 0.0
_STOP = asyncio.Event()

_ADAPTERS: dict = {}
for _s in SPORTS_LIST:
    try:
        _ADAPTERS[_s] = create_adapter(_s)
    except Exception as _e:
        print(f"[PARLEY] sport {_s!r} unavailable ({_e}) — skipped", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════════════════
#  Combination ledger — one entry per set of legs, ever (survives restarts)
# ══════════════════════════════════════════════════════════════════════════════
def _combo_key(legs: list) -> str:
    return "|".join(sorted(l["market_ticker"] for l in legs))


def _ledger_load() -> None:
    global _LEDGER
    try:
        with open(LEDGER_PATH, encoding="utf-8") as f:
            _LEDGER = json.load(f) or {}
    except Exception:
        _LEDGER = {}
    cutoff = datetime.now(timezone.utc).timestamp() - LEDGER_KEEP_DAYS * 86400
    _LEDGER = {k: v for k, v in _LEDGER.items()
               if isinstance(v, (int, float)) and v >= cutoff}
    if _LEDGER:
        print(f"[LEDGER] {len(_LEDGER)} parlay combination(s) already traded "
              f"within {LEDGER_KEEP_DAYS}d — permanently ineligible")


def _ledger_add(key: str) -> None:
    """Record BEFORE the order goes out; flush to disk immediately."""
    _LEDGER[key] = datetime.now(timezone.utc).timestamp()
    try:
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = LEDGER_PATH.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_LEDGER, f)
        os.replace(tmp, LEDGER_PATH)
    except Exception as e:
        print(f"  [LEDGER] write failed: {e}", file=sys.stderr)


def _ledger_drop(key: str, why: str) -> None:
    """Release a combination reserved for an order that never traded.

    The ledger is written BEFORE the order (so a crash mid-placement can never
    double-enter).  When the account then CONFIRMS nothing was bought, holding
    the reservation would retire a perfectly good combination forever — this
    hands it back."""
    if _LEDGER.pop(key, None) is None:
        return
    try:
        tmp = LEDGER_PATH.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_LEDGER, f)
        os.replace(tmp, LEDGER_PATH)
        print(f"  [LEDGER] combination released ({why}) — eligible again")
    except Exception as e:
        print(f"  [LEDGER] release write failed: {e}", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════════════════
#  Leg discovery — live matches whose favourite is > MIN_PROB_C and leading
# ══════════════════════════════════════════════════════════════════════════════
async def _event_markets(client, event: str) -> list:
    """Every sibling market of an event: ticker, participant, quotes, status."""
    try:
        d = await client.req("GET", f"/events/{event}",
                             params={"with_nested_markets": "true"})
    except Exception:
        return []
    out = []
    for mk in ((d.get("event") or {}).get("markets") or []):
        out.append({
            "ticker": mk.get("ticker", ""),
            "name": mk.get("yes_sub_title") or mk.get("title", ""),
            "status": str(mk.get("status", "")).lower(),
            "yes_bid": ks._cents(mk.get("yes_bid_dollars")),
            "yes_ask": ks._cents(mk.get("yes_ask_dollars")),
        })
    return out


def _set_index(players: list) -> int:
    """0-based index of the set in progress (= how many sets have games - 1)."""
    return max((len(p.get("games") or []) for p in players), default=0) - 1


def _games_in(player: dict, idx: int) -> int:
    g = player.get("games") or []
    return int(g[idx]) if 0 <= idx < len(g) else 0


async def _qualify_tennis(client, ticker: str) -> "dict | None":
    """
    One live tennis match → a parlay leg, or None.

    Gates, in order: milestone scoreboard exists → match is LIVE and not
    finished → at least in set MIN_SET → exactly one participant priced ABOVE
    MIN_PROB_C → that participant leads the set named by LEAD_SCOPE.
    """
    event = eng._event_of(ticker)
    try:
        sc = await tv1.get_kalshi_tennis_score(client, ticker)
    except Exception as e:
        print(f"    [leg] {event}: score fetch failed ({e}) — skipped")
        return None
    if not sc:
        print(f"    [leg] {event}: no live scoreboard — skipped")
        return None
    if sc.get("completed") or not sc.get("live"):
        print(f"    [leg] {event}: status={sc.get('status')!r} "
              f"(live={sc.get('live')}, completed={sc.get('completed')}) — "
              f"not an in-play match, skipped")
        return None

    players = sc.get("players") or []
    if len(players) < 2:
        return None
    cur_idx = _set_index(players)
    set_num = cur_idx + 1
    if set_num < MIN_SET:
        print(f"    [leg] {event}: only in set {max(set_num, 0)} "
              f"(need >= {MIN_SET}) — skipped")
        return None

    markets = await _event_markets(client, event)
    by_name = {m["name"]: m for m in markets if m["name"]}
    fav, fav_mkt = None, None
    for p in players:
        mk = by_name.get(p.get("name", ""))
        if mk is None or mk["status"] not in ("active", "open"):
            continue
        if mk["yes_bid"] is not None and mk["yes_bid"] > MIN_PROB_C:
            if fav is not None:                 # both sides > threshold: bad book
                print(f"    [leg] {event}: two participants above "
                      f"{MIN_PROB_C}c — inconsistent book, skipped")
                return None
            fav, fav_mkt = p, mk
    if fav is None:
        best = max((m["yes_bid"] or 0) for m in markets) if markets else 0
        print(f"    [leg] {event}: best price {best}c is not > {MIN_PROB_C}c — skipped")
        return None

    other = players[1] if players[0] is fav else players[0]
    if LEAD_SCOPE != "off":
        idx = cur_idx if LEAD_SCOPE == "current" else MIN_SET - 1
        mine, theirs = _games_in(fav, idx), _games_in(other, idx)
        if mine <= theirs:
            print(f"    [leg] {event}: {fav['name']} @ {fav_mkt['yes_bid']}c is NOT "
                  f"leading set {idx + 1} ({mine}-{theirs}) — skipped")
            return None
    sets_label = "/".join(f"{_games_in(fav, i)}-{_games_in(other, i)}"
                          for i in range(cur_idx + 1))
    print(f"    [leg] {event}: {fav['name']} @ {fav_mkt['yes_bid']}c, set {set_num}, "
          f"games {sets_label} — QUALIFIES")
    return {
        "event_ticker": event,
        "market_ticker": fav_mkt["ticker"],
        "side": "yes",
        "sport": "tennis",
        "name": fav["name"],
        "opponent": other.get("name", ""),
        "prob_c": int(fav_mkt["yes_bid"]),
        "set_num": set_num,
        "games": sets_label,
        "tournament": sc.get("tournament", ""),
    }


_QUALIFIERS = {"tennis": _qualify_tennis}


async def _collect_legs(client) -> list:
    """Scan every configured sport for qualifying live matches."""
    legs: list = []
    for sport, adapter in _ADAPTERS.items():
        qualify = _QUALIFIERS.get(sport)
        if qualify is None:
            print(f"  [{sport}] no parlay qualifier (set/lead state is "
                  f"sport-specific) — skipped")
            continue
        try:
            live = await ks.filter_by_sport_min_volume_live(sport, 0, top_n=10 ** 9,
                                                            client=client)
        except Exception as e:
            print(f"  [{sport}] discovery failed: {e}", file=sys.stderr)
            continue
        live = adapter.filter_discovered(live)
        live = [m for m in live
                if float(m.get("usd_volume", 0.0)) >= MIN_VOLUME_USD]
        live.sort(key=lambda m: m.get("usd_volume", 0.0), reverse=True)
        live = live[:TOP_N]

        # liveness gate 1: Kalshi's own market status + staleness
        metas = await asyncio.gather(
            *(adapter.match_meta(client, m["ticker"]) for m in live),
            return_exceptions=True)
        fresh, n_drop, n_pending, n_stale = [], 0, 0, 0
        for m, meta in zip(live, metas):
            age, status, start_ts = (meta if isinstance(meta, tuple) and len(meta) == 3
                                     else (None, "", None))
            if status in eng._KALSHI_DROP_STATUSES:
                print(f"  [{sport}] {m['ticker']} status={status!r} — "
                      f"postponed/delayed/cancelled, dropped")
                n_drop += 1
                continue
            if start_ts is not None and start_ts > time.time():
                n_pending += 1                 # scheduled, not started yet
                continue
            if isinstance(age, (int, float)) and age > CFG.max_live_hours:
                n_stale += 1                   # live too long — suspended in practice
                continue
            m["start_ts"] = start_ts
            adapter.note_match(m)
            fresh.append(m)
        # liveness gate 2: the adapter's own confirmation (tennis: SofaScore)
        n_before = len(fresh)
        try:
            fresh = await adapter.confirm_active(fresh, client)
        except Exception as e:
            print(f"  [{sport}] confirm_active failed: {e} — using unconfirmed list",
                  file=sys.stderr)
        print(f"  [{sport}] {len(live)} discovered → {len(fresh)} in-play to qualify "
              f"(not started {n_pending}, not active {n_drop}, stale {n_stale}, "
              f"unconfirmed {n_before - len(fresh)})")

        # liveness gate 3 + the price/set/lead rules
        seen_events: set = set()
        for m in fresh:
            ev = eng._event_of(m["ticker"])
            if ev in seen_events:
                continue                       # one leg per match, never both sides
            seen_events.add(ev)
            leg = await qualify(client, m["ticker"])
            if leg:
                legs.append(leg)
    legs.sort(key=lambda l: l["prob_c"], reverse=True)
    return legs


# ══════════════════════════════════════════════════════════════════════════════
#  Combined market (the parlay itself)
# ══════════════════════════════════════════════════════════════════════════════
_COLLECTION_CACHE: dict = {}


async def _pick_collection(client, legs: list) -> "tuple[str, str] | None":
    """(collection_ticker, series_ticker) able to host EVERY leg's event."""
    if _COLLECTION_CACHE.get("ts", 0) < time.time() - 900:
        try:
            d = await client.req("GET", "/multivariate_event_collections",
                                 params={"limit": 100, "status": "open"})
        except Exception as e:
            print(f"  [PARLEY] collection list failed: {e}", file=sys.stderr)
            return None
        cols = []
        for col in d.get("multivariate_contracts", []):
            ct = col.get("collection_ticker", "")
            if COLLECTION and ct != COLLECTION:
                continue
            try:
                det = await client.req("GET",
                                       f"/multivariate_event_collections/{ct}")
            except Exception:
                continue
            body = det.get("multivariate_contract", det)
            cols.append({
                "collection_ticker": ct,
                "series_ticker": col.get("series_ticker", ""),
                "events": set(body.get("associated_event_tickers") or []),
                "size_min": int(body.get("size_min") or 2),
                "size_max": int(body.get("size_max") or 0),
            })
        _COLLECTION_CACHE.update(ts=time.time(), cols=cols)
    wanted = {l["event_ticker"] for l in legs}
    for col in _COLLECTION_CACHE.get("cols", []):
        if wanted <= col["events"] and len(wanted) >= col["size_min"]:
            if col["size_max"] and len(wanted) > col["size_max"]:
                continue
            return col["collection_ticker"], col["series_ticker"]
    return None


async def _create_combined_market(client, collection: str, legs: list) -> "dict | None":
    """
    POST the combination to Kalshi and get the combined market back.

    This endpoint is create-or-return: the first caller for a given set of legs
    creates the market, later callers get the same one.  ``with_market_payload``
    returns the quotes in the same round-trip, so no second fetch is needed.
    """
    body = {"selected_markets": [{"event_ticker": l["event_ticker"],
                                  "market_ticker": l["market_ticker"],
                                  "side": l["side"]} for l in legs],
            "with_market_payload": True}
    try:
        r = await client.req("POST",
                             f"/multivariate_event_collections/{collection}",
                             body=body)
    except Exception as e:
        print(f"  [PARLEY] combined-market creation failed: {e}", file=sys.stderr)
        return None
    mkt = r.get("market") or {}
    return {
        "ticker": r.get("market_ticker") or mkt.get("ticker", ""),
        "event_ticker": r.get("event_ticker", ""),
        "status": str(mkt.get("status", "")).lower(),
        "yes_bid": ks._cents(mkt.get("yes_bid_dollars")),
        "yes_ask": ks._cents(mkt.get("yes_ask_dollars")),
    }


def _theoretical_c(legs: list) -> int:
    """Product of the leg probabilities, in cents — the fair parlay price."""
    p = 1.0
    for l in legs:
        p *= max(0.01, min(0.99, l["prob_c"] / 100.0))
    return max(1, round(p * 100))


# ══════════════════════════════════════════════════════════════════════════════
#  Orders — market order = marketable IOC (the V2 API has no market type)
# ══════════════════════════════════════════════════════════════════════════════
def _mk_market_order(ticker: str, contracts: int, max_price_c: int) -> dict:
    """Buy-YES order that sweeps the book NOW and cancels any remainder.

    The V2 book is single-sided and quoted from the YES leg: side='bid' buys
    YES and ``price`` is the YES price in dollars (same mapping as
    v1._mk_order).  ``immediate_or_cancel`` is what makes it a market order —
    it takes every resting offer up to ``max_price_c`` and never rests."""
    import uuid
    return {
        "ticker": ticker,
        "side": "bid",                                 # bid = buy YES
        "count": f"{int(contracts):.2f}",              # fixed-point per V2 schema
        "price": f"{max_price_c / 100.0:.4f}",         # worst price we will pay
        "time_in_force": "immediate_or_cancel",        # ← market order
        "self_trade_prevention_type": "taker_at_cross",
        "client_order_id": str(uuid.uuid4()),
    }


async def _place_market_buy(client, ticker: str, contracts: int,
                            max_price_c: int) -> "dict | None":
    order = _mk_market_order(ticker, contracts, max_price_c)
    print(f"  [ORDER] MARKET buy x{contracts} on {ticker} "
          f"(IOC, max {max_price_c}c)")
    if v1.DRY_RUN:
        print("  [DRY][ORDER] not sent (DRY_RUN_MODE=TRUE)")
        return {"order": {"order_id": "DRY", "status": "filled"}}
    try:
        return await client.req("POST", v1.ORDER_CREATE_PATH, body=order)
    except Exception as e:
        print(f"  [ORDER] FAILED: {e}", file=sys.stderr)
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  API-reconciled dollar brakes (fills + settlements, never internal P&L)
# ══════════════════════════════════════════════════════════════════════════════
_BRAKE: dict = {}
_BRAKE_CACHE_S = _i("BRAKE_CACHE_S", 300)


async def _api_parley_pnl(client, since_ts: float) -> float:
    """Realized P&L (USD) on COMBINED markets only, from fills + settlements."""
    prefixes = tuple(c["series_ticker"] for c in _COLLECTION_CACHE.get("cols", [])
                     if c.get("series_ticker")) or ("KXMVE",)

    def _mine(tk: str) -> bool:
        return str(tk).startswith(prefixes)

    pnl, cursor = 0.0, None
    for _page in range(20):
        params = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        d = await client.req("GET", "/portfolio/fills", params=params)
        fills = d.get("fills", [])
        stop = False
        for fx in fills:
            try:
                ts = float(fx.get("ts"))
            except (TypeError, ValueError):
                ts = None
            if ts is not None and ts < since_ts:
                stop = True
                break
            if not _mine(fx.get("ticker") or fx.get("market_ticker") or ""):
                continue
            cnt = float(fx.get("count_fp") or 0)
            px = float(fx.get("yes_price_dollars") or 0)
            fee = float(fx.get("fee_cost") or 0)
            pnl += (cnt * px - fee) if fx.get("action") == "sell" else -(cnt * px + fee)
        cursor = d.get("cursor")
        if stop or not cursor or not fills:
            break
    cursor = None
    for _page in range(10):
        params = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        d = await client.req("GET", "/portfolio/settlements", params=params)
        rows = d.get("settlements", [])
        stop = False
        for s in rows:
            try:
                ts = datetime.fromisoformat(
                    str(s.get("settled_time")).replace("Z", "+00:00")).timestamp()
            except Exception:
                ts = None
            if ts is not None and ts < since_ts:
                stop = True
                break
            if _mine(s.get("ticker") or ""):
                pnl += float(s.get("revenue") or 0) / 100.0
        cursor = d.get("cursor")
        if stop or not cursor or not rows:
            break
    return round(pnl, 2)


async def _brake_check(client) -> "str | None":
    """None = clear to trade; else the reason new parlays are halted."""
    if PAPER:
        return None
    if CFG.day_loss_halt_usd <= 0 and CFG.week_loss_halt_usd <= 0:
        return None
    now = time.time()
    if _BRAKE.get("halt_until", 0) > now:
        return _BRAKE.get("why", "halted")
    if now - _BRAKE.get("ts", 0) < _BRAKE_CACHE_S:
        return None
    try:
        cst = v1._cst_now()
        day_start = cst.replace(hour=0, minute=0, second=0,
                                microsecond=0).timestamp()
        day = await _api_parley_pnl(client, day_start)
        week = await _api_parley_pnl(client, now - 7 * 86400)
    except Exception as e:
        print(f"  [BRAKE] API check failed: {e} — no new parlays this cycle "
              f"(fail safe)", file=sys.stderr)
        return "brake check failed (fail safe)"
    _BRAKE.update(ts=now, day=day, week=week)
    if CFG.week_loss_halt_usd > 0 and week <= -CFG.week_loss_halt_usd:
        _BRAKE["halt_until"] = now + 7 * 86400
        _BRAKE["why"] = (f"WEEK loss brake: realized ${week:+.2f} <= "
                         f"-${CFG.week_loss_halt_usd:.0f} — HALTED pending review")
        print(f"\n{'#' * 74}\n#  [BRAKE] PARLEY {_BRAKE['why']}\n{'#' * 74}\n")
        return _BRAKE["why"]
    if CFG.day_loss_halt_usd > 0 and day <= -CFG.day_loss_halt_usd:
        nxt = cst.replace(hour=9, minute=0, second=0,
                          microsecond=0) + timedelta(days=1)
        _BRAKE["halt_until"] = nxt.timestamp()
        _BRAKE["why"] = (f"DAY loss brake: realized ${day:+.2f} <= "
                         f"-${CFG.day_loss_halt_usd:.0f} — no new parlays until "
                         f"{nxt:%m-%d 09:00} CST")
        print(f"\n{'#' * 74}\n#  [BRAKE] PARLEY {_BRAKE['why']}\n{'#' * 74}\n")
        return _BRAKE["why"]
    print(f"  [BRAKE] parley realized: day ${day:+.2f} / week ${week:+.2f} "
          f"(limits -${CFG.day_loss_halt_usd:.0f}/-${CFG.week_loss_halt_usd:.0f}) "
          f"— clear")
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  Entry
# ══════════════════════════════════════════════════════════════════════════════
def _legs_summary(legs: list) -> str:
    return " + ".join(f"{l['name']} ({l['prob_c']}c, set {l['set_num']} "
                      f"{l['games']})" for l in legs)


async def _enter(client, legs: list) -> bool:
    """Create the combined market, market-buy it, log it, rest the TP."""
    global _LAST_ENTRY_TS
    key = _combo_key(legs)
    if key in _LEDGER:
        print(f"  [LEDGER] this exact combination was already traded — skipped")
        return False

    picked = await _pick_collection(client, legs)
    if picked is None:
        print(f"  [PARLEY] no open collection hosts all {len(legs)} leg(s) — "
              f"cannot build this parlay")
        return False
    collection, _series = picked

    theo = _theoretical_c(legs)
    combo = None
    if not PAPER or PAPER_CREATE_MARKET:
        combo = await _create_combined_market(client, collection, legs)
    if combo is None or not combo.get("ticker"):
        if not PAPER:
            return False
        combo = {"ticker": f"PAPER-PARLEY-{int(time.time())}", "status": "active",
                 "yes_bid": max(1, theo - 2), "yes_ask": theo}
        print(f"  [PAPER] no combined market created — pricing the combo "
              f"theoretically at {theo}c")

    tk = combo["ticker"]
    ask = combo.get("yes_ask")
    empty_book = ask is None or ask <= 0
    if empty_book:
        ask = theo
        print(f"  [PARLEY] combined market {tk} has NO resting offer "
              f"(a freshly created combo starts with an empty book) — "
              + (f"resting a limit buy at the theoretical {theo}c "
                 f"(PARLEY_LIMIT_FALLBACK=TRUE)" if LIMIT_FALLBACK else
                 f"a market order would fill 0; set PARLEY_LIMIT_FALLBACK=TRUE "
                 f"to rest a maker buy instead"))
    limit_c = min(MAX_PRICE_C, ask + SLIPPAGE_C)
    if limit_c < MIN_PRICE_C:
        print(f"  [PARLEY] combo price {limit_c}c below PARLEY_MIN_PRICE_C="
              f"{MIN_PRICE_C}c — skipped")
        return False
    if ask > MAX_PRICE_C:
        print(f"  [PARLEY] combo ask {ask}c above PARLEY_MAX_PRICE_C="
              f"{MAX_PRICE_C}c — too expensive, skipped")
        return False

    contracts = max(1, CFG.contracts)
    cost_usd = contracts * limit_c / 100.0
    ok, why = BOOK.can_buy(cost_usd)                 # per-bot bank gate
    if not ok:
        print(f"  [BANK] {why} — skip")
        return False
    brake = await _brake_check(client)
    if brake:
        print(f"  [BRAKE] parley halted — {brake}")
        return False

    tp = CFG.tp_ceiling_c or None
    stop = max(1, limit_c - CFG.stop_loss_c) if CFG.stop_loss_c > 0 else ""
    print(f"\n  [PARLEY] {len(legs)}-leg combo on {tk}")
    print(f"           legs: {_legs_summary(legs)}")
    print(f"           theoretical {theo}c | book ask {combo.get('yes_ask')}c | "
          f"market-order cap {limit_c}c x{contracts} = ${cost_usd:.2f}")
    print(f"           TP {tp or 'none'}c | stop {stop or 'none'}c | "
          f"floor {CFG.sl_floor_c}c")

    if not PLACE_ORDERS:
        # signal-only: nothing was traded, so the combination must NOT be
        # burned in the ledger — it has to stay eligible for a real run
        print("  [PARLEY] PARLEY_PLACE_ORDERS=FALSE — signal only, no order")
        return False

    open_ts = time.time()
    _ledger_add(key)                     # written BEFORE the order, like the engine
    _LAST_ENTRY_TS = open_ts             # also throttles combined-market creation

    fill_px, filled = limit_c, contracts
    if PAPER:
        print(f"  [PAPER] market buy simulated at {limit_c}c x{contracts} — "
              f"no real order")
    else:
        if empty_book and LIMIT_FALLBACK:
            # maker entry: rest the buy and let the fill window decide
            r = await v1.place_buy(client, tk, "yes", buy_at_cents=limit_c,
                                   contracts=contracts)
            print(f"  [ORDER] RESTING buy x{contracts} @ {limit_c}c on {tk} "
                  f"(GTC, {FILL_WAIT_S}s window)")
        else:
            r = await _place_market_buy(client, tk, contracts, limit_c)
        if r is None:
            _ledger_drop(key, "order was rejected — nothing traded")
            return False
        if v1.DRY_RUN:
            print("  [DRY][PARLEY] order placed; skipping fill confirmation")
            return True
        filled, poll_ok = 0, False
        t0 = time.time()
        while time.time() - t0 < FILL_WAIT_S:
            await asyncio.sleep(FILL_POLL_S)
            try:
                pos = await v1.position_for(client, tk)
                poll_ok = True
            except Exception as e:
                pos = None
                print(f"    [FILL] {tk} position read failed: {e}")
            filled = pos["contracts"] if pos else 0
            print(f"    [FILL] {tk} contracts {filled}/{contracts}")
            if filled >= contracts:
                break
        if filled <= 0:
            if empty_book and LIMIT_FALLBACK:
                # a GTC maker order DOES rest — cancel it, never leave a bid
                # hanging on a match the bot has stopped tracking
                print(f"  [PARLEY] resting buy unfilled after {FILL_WAIT_S}s — "
                      f"cancelling (a missed entry costs nothing)")
                try:
                    for o in await v1.resting_orders(client, tk):
                        await client.req("DELETE",
                                         f"/portfolio/events/orders/{o['order_id']}")
                except Exception as e:
                    print(f"  [PARLEY] cancel failed: {e}", file=sys.stderr)
            else:
                # IOC with no liquidity: nothing rests, nothing to cancel.
                print(f"  [PARLEY] market order filled 0 contracts (no liquidity "
                      f"on the combined market) — no position taken")
            # Release the combination ONLY when the account confirmed zero
            # contracts. A failed position read might be hiding a real fill, so
            # that case keeps the ledger entry (never risk a double entry).
            if poll_ok:
                _ledger_drop(key, "market order filled nothing")
            else:
                print(f"  [LEDGER] position never confirmed — combination kept "
                      f"ineligible (a hidden fill must never be doubled)")
            return False
        if filled < contracts:
            print(f"  [PARLEY] partial fill {filled}/{contracts} — the IOC "
                  f"remainder was cancelled by the exchange")
        try:
            pos = await v1.position_for(client, tk)
            cost = float((pos or {}).get("total_traded_dollars")
                         or (pos or {}).get("market_exposure_dollars") or 0)
            fill_px = round(cost / filled * 100) if filled else limit_c
        except Exception:
            fill_px = limit_c

    try:
        pv_entry = round(await eng._portfolio_value(client), 2)
    except Exception:
        pv_entry = ""
    cost_usd = filled * fill_px / 100.0
    _OPEN[tk] = {"side": "yes", "contracts": filled, "buy_at": fill_px,
                 "tp": tp, "open_ts": open_ts, "pv_entry": pv_entry,
                 "legs": legs, "cost_usd": cost_usd}
    BOOK.register_open(tk, cost_usd)
    eng._trade_log({
        "ts_epoch": open_ts, "ts": eng._now_cst(), "sport": "parley",
        "ticker": tk, "name": f"{len(legs)}-leg parlay", "side": "yes",
        "situation": f"{len(legs)} live legs >{MIN_PROB_C}c, set >= {MIN_SET}",
        "confidence": "high", "reason": _legs_summary(legs),
        "context": " | ".join(l["market_ticker"] for l in legs),
        "model_wp": round(theo / 100.0, 4), "signal_bid": combo.get("yes_ask") or "",
        "buy_price": limit_c, "fill_price": fill_px, "contracts": filled,
        "tp_price": tp or "", "stop_price": stop, "pv_entry": pv_entry,
        "status": "OPEN"}, csv_path=TRADE_CSV)
    print(f"  [PARLEY] OPEN {filled} x {tk} @ {fill_px}c (${cost_usd:.2f}) | "
          f"{BOOK.status_line()}")

    if tp and not PAPER:
        b_q, a_q = await eng._quote(client, tk, "yes")
        if b_q is not None and a_q is not None and not eng._spread_ok(b_q, a_q):
            print(f"  [PARLEY] spread {b_q}/{a_q}c > {eng.SPORT_SPREAD_MAX_C}c — "
                  f"TP deferred; the guardian places it once the book is stable")
        else:
            have, _s, _p = await eng._confirm_open_position(
                client, tk, expect_side="yes", require_no_resting=True,
                tag="PARLEY")
            if have > 0:
                await v1.place_tp_sell(client, tk, "yes", have, tp)
                print(f"  [PARLEY] TP sell @ {tp}c resting")
    return True


# ══════════════════════════════════════════════════════════════════════════════
#  Guardian — TP upkeep, entry-relative stop, hard floor, close detection
# ══════════════════════════════════════════════════════════════════════════════
async def _adopt_open_parlays(client) -> None:
    """Adopt combined-market positions left by an earlier run, so they are
    protected by the stop/TP from this bot's first guardian cycle."""
    if PAPER:
        return
    try:
        d = await client.req("GET", "/portfolio/positions", params={"limit": 1000})
    except Exception as e:
        print(f"[PARLEY] adoption skipped — positions fetch failed: {e}",
              file=sys.stderr)
        return
    prefixes = ("KXMVE",)
    for p in d.get("market_positions", []):
        tk = p.get("ticker", "")
        have = abs(int(float(p.get("position_fp", "0"))))
        if have <= 0 or not tk.startswith(prefixes) or tk in _OPEN:
            continue
        cost = float(p.get("total_traded_dollars")
                     or p.get("market_exposure_dollars") or 0)
        entry = round(cost / have * 100) if have else 0
        _OPEN[tk] = {"side": "yes", "contracts": have, "buy_at": entry,
                     "tp": CFG.tp_ceiling_c or None, "open_ts": 0.0,
                     "pv_entry": "", "legs": [], "cost_usd": cost,
                     "adopted": True, "basis_cost": cost}
        BOOK.register_open(tk, cost)
        print(f"[ADOPT] {tk}: {have} contracts, basis {entry}c "
              f"(${cost:.2f}) — now guarded")


async def _guardian(client) -> None:
    """Every GUARD_S, over the parlays THIS bot owns (never anyone else's
    positions — the sports bots manage their own tickers)."""
    while not _STOP.is_set():
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=GUARD_S)
            break
        except asyncio.TimeoutError:
            pass
        if not _OPEN:
            continue
        try:
            d = await client.req("GET", "/portfolio/positions", params={"limit": 1000})
            positions = {p.get("ticker"): p for p in d.get("market_positions", [])
                         if abs(int(float(p.get("position_fp", "0")))) > 0}
            resting = {o.get("ticker") for o in await v1.resting_orders(client)}
        except Exception as e:
            print(f"  [GUARD] fetch failed: {e}", file=sys.stderr)
            continue

        # ── close detection: CSV close + bank P&L ────────────────────────────
        for tk in list(_OPEN):
            if PAPER or tk in positions:
                continue
            info = _OPEN.pop(tk)
            _STRIKES.pop(tk, None)
            pnl = None
            try:
                pnl = await eng._realized_pnl(client, tk, info.get("side", "yes"),
                                              info.get("open_ts", 0))
                if info.get("adopted") and isinstance(pnl, (int, float)):
                    pnl = round(pnl - info.get("basis_cost", 0.0), 2)
                pv_close = round(await eng._portfolio_value(client), 2)
                pve = info.get("pv_entry")
                pct = (round((pv_close - pve) / pve * 100, 2)
                       if isinstance(pve, (int, float)) and pve else "")
                eng._trade_log_close(tk, info.get("open_ts", ""),
                                     {"ts_close": eng._now_cst(),
                                      "pv_close": pv_close, "realized_pnl": pnl,
                                      "pv_delta_pct": pct}, csv_path=TRADE_CSV)
            except Exception as e:
                print(f"  [TRADECSV] close record failed: {e}", file=sys.stderr)
            BOOK.register_close(tk, pnl)
            print(f"  [GUARD] {tk} parlay closed (P&L "
                  f"{'$%.2f' % pnl if isinstance(pnl, float) else 'n/a'}) — "
                  f"{BOOK.status_line()}")

        # ── band exits / stop-loss / TP upkeep ───────────────────────────────
        for tk, info in list(_OPEN.items()):
            if PAPER:
                continue
            p = positions.get(tk)
            if not p:
                continue
            have = abs(int(float(p.get("position_fp", "0"))))
            side = info.get("side", "yes")
            entry = eng._basis_entry(info, p, have)
            bid, ask = await eng._quote(client, tk, side)
            if bid is None:
                continue
            ceiling = CFG.tp_ceiling_c
            floor = CFG.sl_floor_c
            stop_at = entry - CFG.stop_loss_c if (entry and CFG.stop_loss_c > 0) else None

            if ceiling > 0 and bid >= ceiling:
                await eng._exit_position(client, tk, side, "PARLEY-TP",
                                         f"bid {bid}c >= ceiling {ceiling}c", bid,
                                         risk_off=True)
                continue
            breach = ((floor > 0 and bid <= floor)
                      or (stop_at is not None and bid <= stop_at))
            if breach:
                n = _STRIKES.get(tk, 0) + 1
                _STRIKES[tk] = n
                need = max(1, CFG.stop_confirm)
                why = (f"bid {bid}c <= "
                       + (f"floor {floor}c" if floor > 0 and bid <= floor
                          else f"stop {stop_at}c (entry {entry}c-{CFG.stop_loss_c})"))
                if n < need:
                    print(f"  [PARLEY-STOP] {tk} breach {n}/{need} — {why}")
                    continue
                # risk_off: the spread guard may defer a TP, never a loss cut
                if await eng._exit_position(client, tk, side, "PARLEY-STOP", why,
                                            bid, risk_off=True):
                    _STRIKES.pop(tk, None)
                continue
            _STRIKES.pop(tk, None)

            tp = info.get("tp")
            if tp and tk not in resting and have > 0:
                if ask is not None and not eng._spread_ok(bid, ask):
                    continue                   # unstable book — retry next cycle
                confirmed, _s, _p = await eng._confirm_open_position(
                    client, tk, expect_side=side, require_no_resting=True,
                    tag="PARLEY-TP")
                if confirmed > 0:
                    await v1.place_tp_sell(client, tk, side, confirmed, tp)
                    print(f"  [PARLEY-TP] {tk} TP sell @ {tp}c re-placed "
                          f"x{confirmed}")


# ══════════════════════════════════════════════════════════════════════════════
#  Main loop
# ══════════════════════════════════════════════════════════════════════════════
async def run() -> None:
    _setup_logging()
    print(f"[PARLEY-BOT] {'*** PAPER MODE *** ' if PAPER else ''}"
          f"sports={SPORTS_LIST} legs>{MIN_PROB_C}c set>={MIN_SET} "
          f"lead={LEAD_SCOPE} legs={MIN_LEGS}..{MAX_LEGS or 'all'}")
    print(f"[PARLEY-BOT] bank=${CFG.bank:.0f} contracts={CFG.contracts} "
          f"bank-stop={CFG.stop_loss_pct:.0f}% TP={CFG.tp_ceiling_c}c "
          f"stop=entry-{CFG.stop_loss_c}c x{CFG.stop_confirm} "
          f"floor={CFG.sl_floor_c}c brakes=[day ${CFG.day_loss_halt_usd:.0f}, "
          f"week ${CFG.week_loss_halt_usd:.0f}]")
    print(f"[PARLEY-BOT] order=MARKET (marketable IOC, ask+{SLIPPAGE_C}c, "
          f"cap {MAX_PRICE_C}c)  place_orders={PLACE_ORDERS}  "
          f"DRY_RUN={v1.DRY_RUN}  trades → {Path(TRADE_CSV).name}")
    if not _ADAPTERS:
        print("[PARLEY-BOT] no usable sport adapters — nothing to do.")
        return
    _ledger_load()

    c = KalshiClient()
    try:
        await _adopt_open_parlays(c)
        asyncio.create_task(_guardian(c))
        for sport, adapter in _ADAPTERS.items():
            try:
                await adapter.startup(c)
            except Exception as e:
                print(f"  [{sport}] startup failed: {e}", file=sys.stderr)

        while not _STOP.is_set():
            print(f"\n=== SCAN {eng._now_cst()} | open parlays {len(_OPEN)}"
                  f"/{MAX_OPEN} | {BOOK.status_line()} ===")
            if BOOK.halted:
                print("  [BANK] parley betting halted for this session")
            elif len(_OPEN) >= MAX_OPEN:
                print(f"  [PARLEY] {len(_OPEN)} parlay(s) already open "
                      f"(PARLEY_MAX_OPEN={MAX_OPEN}) — not building another")
            elif time.time() - _LAST_ENTRY_TS < COOLDOWN_S:
                left = COOLDOWN_S - (time.time() - _LAST_ENTRY_TS)
                print(f"  [PARLEY] cooldown — {left / 60:.1f} min until the "
                      f"next parlay may be built")
            else:
                try:
                    legs = await _collect_legs(c)
                except Exception as e:
                    print(f"  [PARLEY] leg collection failed: {e}", file=sys.stderr)
                    legs = []
                if len(legs) < MIN_LEGS:
                    print(f"  [PARLEY] {len(legs)} qualifying leg(s) — need "
                          f"{MIN_LEGS} to build a parlay")
                else:
                    if MAX_LEGS > 0:
                        legs = legs[:MAX_LEGS]
                    print(f"  [PARLEY] {len(legs)} qualifying leg(s): "
                          f"{_legs_summary(legs)}")
                    try:
                        await _enter(c, legs)
                    except Exception as e:
                        print(f"  [PARLEY] entry failed: {e}", file=sys.stderr)
            try:
                await asyncio.wait_for(_STOP.wait(), timeout=SCAN_S)
            except asyncio.TimeoutError:
                pass
        print("[PARLEY-BOT] halt signalled.")
    finally:
        await c.close()


class _ParleyLog(eng._RotatingLog):
    """kalshi_parley_YYYYMMDD.log in the customer's logs folder."""
    _PREFIX = "kalshi_parley_"


def _setup_logging() -> None:
    if isinstance(sys.stdout, eng._Tee):
        return
    try:
        rot = _ParleyLog()
    except Exception as e:
        print(f"[PARLEY-BOT] could not open log: {e}", file=sys.stderr)
        return
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.stdout = eng._Tee(sys.__stdout__, rot)
    sys.stderr = eng._Tee(sys.__stderr__, rot)
    print(f"[PARLEY-BOT] logging to {rot.path.name}  (archive on day change)")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n[PARLEY-BOT] interrupted — stopping.")


if __name__ == "__main__":
    main()
