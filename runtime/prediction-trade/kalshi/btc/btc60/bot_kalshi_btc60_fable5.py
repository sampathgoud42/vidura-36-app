#!/usr/bin/env python3
"""
bot_kalshi_btc60_fable5.py - Kalshi BTC HOURLY bot (Fable 5 build)
===================================================================
Self-contained hourly bot for the KXBTCD series ("BTC price at X PM EDT").
Everything the bot needs lives under kalshi/btc/ (this file, the shared
btc/ signal package, strategy defaults below) EXCEPT the Kalshi API secrets
(KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY, BASE_URI, optional DRY_RUN_MODE),
which are read from the customer folder named by btc.env's customer_folder +
default_customer (e.g. <project>/customers/suma/.env + kalshi_private.pem)
-- see the "SECRETS" block below. Every strategy parameter is defaulted in
this file.

STRATEGY (backtested on kbtc-60.log: 211 hourly events, Jun 20-30 2026,
~43k signal ticks - see analyze notes below):

  "Buy the FAVORITE at 65-80c when the volume Point-of-Control agrees,
   in minutes 10-30 of the hour, maker entry, TP +15% / SL -30%."

  * Side       : spot >= strike -> YES, spot < strike -> NO (the favorite).
  * Confirm    : LiquiditySR POC color must agree - POC below price (Green,
                 volume support under us) for YES; POC above price (Red,
                 volume resistance overhead) for NO.
  * Price      : favorite side's bid in [65, 80]c; rest a maker limit AT the
                 bid (no spread crossing, no taker fee on entry).
  * Timing     : entries only minutes 10-30 of the hour (<HH:30 per spec;
                 minute >= 10 lets the hour establish its range first).
  * Exits      : TP +15% (resting maker sell) or SL -30% (monitored, taker),
                 force-flatten 5 min before close - NEVER hold to settlement.
  * Re-entry   : after each exit the bot may re-enter while still inside the
                 entry window (multiple trades per hour, one position at a
                 time, never a position left on an hourly market).

  Backtest of this exact rule (maker fills, 3c adverse slippage on SL exits,
  taker fee on exits): n=369 trades, win 75.9%, avg +1.15%/trade;
  compounding 10% of PV per trade => +39% over 10 days.  Breakeven win rate
  for TP15/SL30 is 66.7% - the POC + minute>=10 filters are what push the
  favorite's win rate to ~76%; without them the same band is ~71% (= zero
  EV).  Rules tested and REJECTED (all -EV): signal-aligned entries at any
  band 30-85c, underdog entries, hour-open drift continuation, S/R
  proximity, big-cushion favorites at cheap asks, and letting the BTC
  monitor's STRONG signal DICTATE trade direction (win% collapses to
  61-66%, avg -3.6% to -5%/trade - momentum alone is too noisy on this
  market; re-confirms the signal-aligned rejection above).

  STRONG-signal CONFIRMATION (added after a live loss where the bot bought
  YES seconds after a STRONG SELL fired): a candidate only fires when the
  most recent STRONG BUY/SELL within STRONG_CONFIRM_LOOKBACK_TICKS AGREES
  with its side - YES needs a recent STRONG_BUY, NO needs a recent
  STRONG_SELL.  No confirming strong signal -> no trade (it never flips to
  the opposite side; the override tested above does that and is -EV).
  Backtested at 300s/20-tick lookback: n=235 (vs 369 baseline), win 76.2%
  vs 75.9%, avg +2.25%/trade vs +2.22% - a bit more edge per trade at the
  cost of ~36% fewer trades (less compounding throughput; PV10%=1.61 vs
  2.09 baseline over the 10-day sample).  Chosen deliberately over the
  cheaper "just don't oppose a strong signal" gate (n=267, win 75.7%,
  PV10%=1.67) because it's the version the account owner asked for.

  LIVE-PAPER REVIEW (2026-07-07, 46 paper trades over 2026-07-04..07):
  realized win rate 56.5% (vs 66.7% breakeven for TP16/SL20), net -$20.50.
  Split by side, NO ran 68% WR / +$4.95 (matches the backtest) while YES
  ran only 43% WR / -$25.45 - all of the drawdown.  Two changes made from
  this: (1) YES-side candidates now need a bid_lo+5c pricier entry than NO
  (see YES_BID_LO_BONUS) since a pump that flips spot>=strike + fires the
  STRONG_BUY confirm looks more often like a local top than a NO-side dip
  reversal on this sample; (2) flatten()'s first exit attempt now sells AT
  the bid instead of undercutting it by 2c (marketable already; the
  undercut was pure giveaway and partly explains realized SL exits running
  ~10pp worse than the nominal SL).  Both changes tighten/de-risk rather
  than re-fit the core rule - the underlying 75.9% backtest edge is still
  the target; 46 trades isn't enough to conclude the edge is gone.

HARD-CODED RISK PARAMETERS (defaults; the learner may adjust within bounds,
persisted to btc60_fable5_state.json):
"""
from __future__ import annotations

# ══════════════════════════════════════════════════════════════════════════
#  HARD-CODED TRADE PARAMETERS  (learner adjusts within [min,max] bounds)
# ══════════════════════════════════════════════════════════════════════════
TAKE_PROFIT_PCT  = 15.0     # sell when bid >= entry * 1.15   (bounds 12-20)
# Per-trade profit target override (user 07/30). When BTC60_TP_PCT is set the
# user's number WINS over both the persisted state file and the learner —
# otherwise an explicit target would silently drift away within a few trades
# and the input would be a lie. Unset (0) keeps the self-tuning behaviour.
TP_PCT_OVERRIDE  = float(__import__("os").getenv("BTC60_TP_PCT", "0") or 0)
STOP_LOSS_PCT    = 30.0     # dump when bid <= entry * 0.70   (bounds 20-35)
# Per-trade stop-loss override, same contract as BTC60_TP_PCT above: when set
# the user's number WINS over the persisted state file and the learner, so an
# explicit stop cannot silently drift. Unset (0) keeps the self-tuning.
SL_PCT_OVERRIDE  = float(__import__("os").getenv("BTC60_SL_PCT", "0") or 0)
PV_PCT_PER_TRADE = 10.0     # size each trade at 10% of the BTC BANKROLL (5-15)
# Common bot contract (user 08/03): FIXED contracts on every buy; the
# pv-percent sizing above is no longer used for order size (the learner
# still tunes tp/sl/bid_lo). KALSHI_CONTRACTS is what the desk injects.
FIXED_CONTRACTS  = int(__import__("os").getenv("KALSHI_CONTRACTS", "1") or 1)

# The Kalshi account is SHARED with other bots (sports, perp, ...), so this
# bot sizes and learns off its OWN bankroll ledger - never the account
# balance.  The ledger is seeded once with BTC_BANKROLL_SEED, then updated
# only by this bot's realized P&L and persisted in the state file (edit
# "bankroll" there to top up / draw down).  Account cash is only consulted
# as a spend CAP so we never place orders the account can't fund.
BTC_BANKROLL_SEED = float(__import__("os").getenv("BTC_BANKROLL", "100"))
# $ initial BTC-market bankroll. BTC_BANKROLL (set per engine bay from the UI)
# RESEEDS the ledger on start rather than only on first run, so "this bot
# trades $250" means what it says instead of being overridden by whatever the
# state file happens to hold.
BTC_BANKROLL_RESEED = bool(__import__("os").getenv("BTC_BANKROLL"))
# Profit target measured on THIS BOT'S bankroll, not the shared account's
# portfolio value (user 07/30): halt new entries once realized P&L has grown
# the bankroll by this %. 0 = run indefinitely.
BTC_TARGET_PCT = float(__import__("os").getenv("BTC60_TARGET_PCT", "0") or 0)
# Bank stop-loss (user 08/03): the capital-protection mirror of the target.
BANK_SL_PCT    = float(__import__("os").getenv("BTC60_BANK_SL_PCT", "0") or 0)

# ── NO-TRADE windows (user 08/03): quiet hours in HALT_TIMEZONE local time.
# The bot STAYS RUNNING (signals, monitors, TP management) but enters no NEW
# trade while local time is inside any window. Format:
#   NO_TRADE_TIMES="17:00-19:30,05:00-08:00"
# end < start wraps midnight; an empty string disables the windows entirely.
import datetime as _ntdt
import os as _ntos
import sys as _ntsys
from zoneinfo import ZoneInfo as _NTZone

_NT_DEFAULT = "17:00-19:30,05:00-08:00"
_NT_TZ = _NTZone(_ntos.getenv("HALT_TIMEZONE", "America/Chicago"))


def _nt_parse():
    out = []
    for part in (_ntos.getenv("NO_TRADE_TIMES", _NT_DEFAULT) or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            a, b = part.split("-", 1)
            h1, m1 = a.strip().split(":")
            h2, m2 = b.strip().split(":")
            out.append((_ntdt.time(int(h1), int(m1)), _ntdt.time(int(h2), int(m2))))
        except ValueError:
            print(f"[NO-TRADE] unparsable window {part!r} - ignored",
                  file=_ntsys.stderr)
    return out


NO_TRADE_WINDOWS = _nt_parse()
_nt_announced = [False]


def _in_no_trade_window(t=None):
    """The window containing local time ``t`` (default: now), else None."""
    t = t or _ntdt.datetime.now(_NT_TZ).time()
    for s, e in NO_TRADE_WINDOWS:
        if (s <= t <= e) if s <= e else (t >= s or t <= e):
            return (s, e)
    return None


ENTRY_BID_LO     = 65       # favorite's bid band, cents      (learner: lo 65-72)
ENTRY_BID_HI     = 80
ENTRY_BID_SWEET  = 72       # prefer candidate bid closest to this

# 2026-07-07 paper-trade review (46 trades, 2026-07-04..07, btc60_fable5_
# trade_history_paper.csv): overall win rate 56.5% vs the 66.7% breakeven
# needed for the live TP16/SL20 - net -$20.50 on a $100 bankroll.  Split by
# side: NO (spot<strike favorite) was 68% WR / +$4.95 - in line with the
# backtest.  YES (spot>=strike favorite) was only 43% WR / -$25.45 - ALL of
# the loss.  Hypothesis: an intra-hour BTC pump that pushes spot above
# strike (which is also what fires the required STRONG_BUY confirm) is
# often a local top that mean-reverts before close, so YES continuation
# bets are lower quality than NO continuation bets off the same signal.
# Rather than disabling YES outright on a 46-trade sample, require a
# pricier (higher-conviction) bid for it - NO keeps the normal bid_lo.
YES_BID_LO_BONUS = 5        # cents added to bid_lo for YES-side candidates only
ENTRY_START_MIN  = 10       # no entries in the first 10 min of the hour
ENTRY_CUTOFF_MIN = 30       # no NEW entries at/after HH:30 (per spec)
FLATTEN_BEFORE_CLOSE_MIN = 5   # force-flat deadline (min before close)
# One trade per market by default (user 07/30) — for btc60 an hourly event IS
# the market. Was 6 as a churn circuit-breaker; MAX_TRADES_PER_MARKET is the
# shared name across every BTC engine.
MAX_TRADES_PER_HOUR = int(__import__("os").getenv("MAX_TRADES_PER_MARKET", "1"))
POLL_S           = 10       # order/position/bid poll cadence (seconds)
POC_REFRESH_S    = 150      # recompute LiquiditySR POC every 2.5 min
# Portfolio-floor halt REMOVED (user 07/30). Risk is expressed as this bot's
# own bankroll plus BTC60_TARGET_PCT on it; a floor is redundant because the
# bankroll already caps what can be spent, and it used to stop the bot dead on
# a drawdown that the target logic handles. Set BTC60_MIN_BANKROLL to a
# positive number only if you deliberately want the old behaviour back.
MIN_PORTFOLIO_HALT = float(__import__("os").getenv("BTC60_MIN_BANKROLL", "0") or 0)
SERIES           = "KXBTCD" # Kalshi hourly BTC series

# A candidate only fires when the most recent STRONG BUY/SELL within this
# many monitor TICKS (15s poll interval -> 20 ticks = 5 min) AGREES with
# its side: YES requires a recent STRONG_BUY, NO requires a recent
# STRONG_SELL.  No match -> skip (never flips to the opposite side - a
# full signal-driven override backtests badly; see the module docstring).
STRONG_CONFIRM_LOOKBACK_TICKS = 20   # ~5 min at the BTC monitor's 15s poll

# Exhaustion-avoidance: require the 30-min net move (in the direction that
# favors the candidate side) to sit in [NET30_LO, NET30_HI] USD - not
# negative (moving against the "favorite" despite the spot>=strike label)
# and not already extended past NET30_HI (likely exhausted).  Backtested on
# kbtc-60.log (211 hourly events, Jun 20-30) against the exact deployed
# rule: baseline n=248 win 76.2% avg+2.26%/trade -> add 0<=net30<=60 gives
# n=41 win 82.9% avg+5.34%/trade.  Split-half robustness check (first vs
# second half of June): helps in BOTH halves, though second-half-alone
# stayed at 73.5% (regime-dependent edge, not a guarantee in all markets).
# Hardcoded, not learner-tunable, until it accumulates its own live track
# record the way pv_pct/bid_lo/sl_pct/tp_pct have.
NET30_LOOKBACK_TICKS = 120   # ~30 min at the BTC monitor's 15s poll
NET30_LO = 0
NET30_HI = 60

# Learner bounds + cadence
LEARN_EVERY      = 10       # re-fit after every N completed trades
LEARN_WINDOW     = 60       # fit on the most recent N trades
TP_BOUNDS        = (12.0, 20.0)
SL_BOUNDS        = (20.0, 35.0)
PV_BOUNDS        = (5.0, 15.0)
BID_LO_BOUNDS    = (65, 72)

# Faster reactive brake, independent of the LEARN_EVERY=10 fit above: check
# every FAST_CHECK_EVERY trades, and if FAST_CHECK_LOSS_THRESHOLD or more of
# them lost, tighten immediately rather than waiting for the slower cadence.
# Applied IN-PROCESS (no restart needed - the running bot reads
# learner.pv_pct/bid_lo fresh on every entry decision); bounded by the same
# PV_BOUNDS/BID_LO_BOUNDS as the normal fit, so it can never runs away.
FAST_CHECK_EVERY         = 5
FAST_CHECK_LOSS_THRESHOLD = 2

import asyncio
import base64
import csv
import json
import math
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiohttp
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as _padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from dotenv import load_dotenv

# ── locate the shared btc/ package + this bot's own non-secret config ───────
_HERE = Path(__file__).resolve().parent          # .../kalshi/btc/btc60
_ROOT = _HERE.parent                             # .../kalshi/btc  (has btc/ + btc.env)
sys.path.insert(0, str(_ROOT))

load_dotenv(_ROOT / "btc.env")                    # customer_folder / default_customer only

from btc import BtcVidyaMonitor                  # noqa: E402  Coinbase spot, 15s (local btc/ pkg)
from btc.liquidity_sr import LiquiditySR, run as lsr_run   # noqa: E402  POC (local btc/ pkg)

# ══════════════════════════════════════════════════════════════════════════
#  SECRETS - the ONLY thing not self-contained under kalshi/btc/.
#  btc.env (tracked in git, no secrets) names a customer folder; that
#  folder's .env (KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY, BASE_URI, optional
#  DRY_RUN_MODE) and *.pem are the sole source of Kalshi credentials.
#  Override the customer without touching btc.env via BTC_CUSTOMERS_DIR /
#  BTC_CUSTOMER env vars (e.g. a differently-configured launch).
# ══════════════════════════════════════════════════════════════════════════
def _require_customer() -> str:
    """No silent default: another machine must never pick up a
    stranger's folder name. The API injects BTC_CUSTOMER."""
    name = os.getenv("BTC_CUSTOMER", os.getenv("default_customer", "")).strip()
    if not name:
        sys.exit("BTC_CUSTOMER (or btc.env default_customer) must name "
                 "the customer folder — there is no default on this deployment")
    return name


_CUSTOMER_DIR = (Path(os.getenv("BTC_CUSTOMERS_DIR",
                                os.getenv("customer_folder", "")).strip())
                 / _require_customer())

_secrets_found = False
for _cand in [_CUSTOMER_DIR / ".env"] + sorted(_CUSTOMER_DIR.glob("*.env")):
    if _cand.is_file():
        load_dotenv(_cand, override=True)
        _secrets_found = True
        break
if not _secrets_found:
    sys.exit(f"[SECRETS] no .env found in customer folder {_CUSTOMER_DIR} "
             f"(resolved from btc.env's customer_folder/default_customer) - "
             f"refusing to start without real Kalshi credentials.")

BASE_URI   = os.getenv("BASE_URI", "https://external-api.kalshi.com/trade-api/v2")
API_KEY_ID = os.getenv("KALSHI_API_KEY_ID", "")
DRY_RUN    = os.getenv("DRY_RUN_MODE", "TRUE").upper() == "TRUE"

def _resolve_pem() -> Path:
    raw = os.getenv("KALSHI_PRIVATE_KEY", "kalshi_private.pem")
    p = Path(raw)
    if p.is_absolute():
        if p.is_file():
            return p
        raise FileNotFoundError(f"KALSHI_PRIVATE_KEY '{raw}' not found")
    cand = _CUSTOMER_DIR / p.name
    if cand.is_file():
        return cand.resolve()
    pems = sorted(_CUSTOMER_DIR.glob("*.pem"))
    if pems:
        return pems[0].resolve()
    raise FileNotFoundError(
        f"KALSHI_PRIVATE_KEY '{raw}' not found in customer folder {_CUSTOMER_DIR}")

# ── files (all live next to this script) ─────────────────────────────────────
# Paper runs get their own CSV/state so DRY_RUN never contaminates the live
# learner or the live bankroll ledger.
_SUFFIX    = "_paper" if DRY_RUN else ""
CSV_FILE   = _HERE / f"btc60_fable5_trade_history{_SUFFIX}.csv"
STATE_FILE = _HERE / f"btc60_fable5_state{_SUFFIX}.json"
LOG_FILE   = _HERE / f"btc60_fable5_{datetime.now():%Y%m%d}.log"
LOCK_FILE  = _HERE / f"btc60_fable5{_SUFFIX}.lock"

_CSV_COLS = ["timestamp", "event", "ticker", "side", "strike", "contracts",
             "entry_cents", "exit_cents", "exit_reason", "pnl_dollars",
             "ret_pct", "max_gain_pct", "max_dd_pct", "pv_after",
             "pv_pct_used", "tp_pct", "sl_pct", "spot_at_entry",
             "poc_price", "poc_color", "minute_of_hour", "net30_at_entry"]


class _Tee:
    """Mirror stdout/stderr to the session log file."""
    def __init__(self, *streams):
        self._streams = streams
    def write(self, data):
        for s in self._streams:
            try:
                s.write(data)
            except Exception:
                pass
        self.flush()
    def flush(self):
        for s in self._streams:
            try:
                s.flush()
            except Exception:
                pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ts_ms() -> str:
    return str(int(_utc_now().timestamp() * 1000))


def _log(tag: str, msg: str) -> None:
    print(f"[{tag} {_utc_now():%H:%M:%S}Z] {msg}")


# ══════════════════════════════════════════════════════════════════════════
#  SINGLE-INSTANCE LOCK
#  On 2026-07-02 two copies of this bot ran against the same live account at
#  once (each launched independently, neither aware of the other) - both
#  bought/flattened the SAME markets, both clobbered the same state.json
#  with divergent bankroll numbers, and one instance fabricated a "STOP_LOSS"
#  exit that was actually just it finding a position the OTHER instance had
#  already closed.  This lock makes a second launch refuse to start instead
#  of silently corrupting the ledger again.
# ══════════════════════════════════════════════════════════════════════════
def _pid_alive(pid: int) -> bool:
    """Best-effort liveness check.  Inconclusive -> True (fail closed: refuse
    to start rather than risk running a second live copy)."""
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5).stdout
            return str(pid) in out
        except Exception:
            return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except Exception:
        return True


def _acquire_lock() -> None:
    if LOCK_FILE.is_file():
        raw = LOCK_FILE.read_text().strip()
        old_pid = int(raw) if raw.isdigit() else None
        if old_pid and _pid_alive(old_pid):
            sys.exit(
                f"[LOCK] Another instance appears to be running (PID "
                f"{old_pid}, lock={LOCK_FILE}). Refusing to start a second "
                f"copy against the same bankroll/account - this is exactly "
                f"what corrupted the ledger on 2026-07-02. If you're certain "
                f"it isn't running, delete the lock file and retry.")
        print(f"[LOCK] stale lock (PID {old_pid}) - taking over.")
    LOCK_FILE.write_text(str(os.getpid()))


def _release_lock() -> None:
    try:
        if (LOCK_FILE.is_file()
                and LOCK_FILE.read_text().strip() == str(os.getpid())):
            LOCK_FILE.unlink()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════
#  KALSHI CLIENT  (aiohttp + RSA-PSS signing - same auth as the v1 infra)
# ══════════════════════════════════════════════════════════════════════════
class KalshiClient:
    def __init__(self) -> None:
        self._pk = load_pem_private_key(_resolve_pem().read_bytes(), password=None)
        self._session: Optional[aiohttp.ClientSession] = None
        self._mu = asyncio.Lock()

    def _sign(self, ts: str, method: str, path: str) -> str:
        sig = self._pk.sign(
            f"{ts}{method}{path}".encode(),
            _padding.PSS(mgf=_padding.MGF1(hashes.SHA256()),
                         salt_length=_padding.PSS.DIGEST_LENGTH),
            hashes.SHA256())
        return base64.b64encode(sig).decode()

    def _headers(self, method: str, path: str) -> dict[str, str]:
        ts = _ts_ms()
        return {
            "Content-Type":            "application/json",
            "KALSHI-ACCESS-KEY":       API_KEY_ID,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": self._sign(ts, method.upper(),
                                                  f"/trade-api/v2{path}"),
            "Cache-Control": "no-cache",
        }

    async def _sess(self) -> aiohttp.ClientSession:
        async with self._mu:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(limit=30, ttl_dns_cache=300),
                    timeout=aiohttp.ClientTimeout(total=12, connect=4))
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def req(self, method: str, path: str, *, params: dict | None = None,
                  body: dict | None = None, retries: int = 3) -> dict:
        url, last = f"{BASE_URI}{path}", None
        sess = await self._sess()
        for attempt in range(1, retries + 1):
            try:
                async with sess.request(method.upper(), url,
                                        headers=self._headers(method, path),
                                        params=params, json=body) as r:
                    txt = await r.text()
                    if r.status >= 400:
                        raise RuntimeError(f"HTTP {r.status}: {txt}")
                    return json.loads(txt)
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as e:
                last = e
                if attempt < retries:
                    await asyncio.sleep(0.4 * attempt)
        raise RuntimeError(f"{method} {path} failed after {retries} tries: {last}")


# ── V2 order body (single-sided YES book: bid=buy YES, ask=sell YES) ─────────
ORDER_CREATE_PATH = "/portfolio/events/orders"


def _mk_order(ticker: str, action: str, side: str, count: int,
              price_cents: int) -> dict:
    if side == "yes":
        v2_side, yes_cents = ("bid" if action == "buy" else "ask"), price_cents
    else:
        v2_side, yes_cents = ("ask" if action == "buy" else "bid"), 100 - price_cents
    return {
        "ticker": ticker,
        "side": v2_side,
        "count": f"{int(count):.2f}",
        "price": f"{yes_cents / 100.0:.4f}",
        "time_in_force": "good_till_canceled",
        "self_trade_prevention_type": "taker_at_cross",
        "client_order_id": str(uuid.uuid4()),
    }


# ══════════════════════════════════════════════════════════════════════════
#  PORTFOLIO / ORDER HELPERS  (paper-book aware: DRY_RUN simulates fills)
# ══════════════════════════════════════════════════════════════════════════
class PaperBook:
    """In DRY_RUN, tracks the simulated position + orders so the monitoring
    logic exercises the same code paths against live market bids."""
    def __init__(self) -> None:
        self.position: dict | None = None       # {ticker, side, contracts}
        self.resting:  list[dict] = []          # [{ticker, action, side, price, count}]

PAPER = PaperBook()


async def account_cash(c: KalshiClient) -> float:
    """Whole-account available cash - used ONLY as a spend cap (the account
    is shared with other bots; sizing/learning use the BTC bankroll)."""
    if DRY_RUN:
        return 1e9
    d = await c.req("GET", "/portfolio/balance")
    return d.get("balance", 0) / 100.0


async def position_for(c: KalshiClient, ticker: str) -> tuple[int, str | None]:
    """Return (contracts, side) held on ticker; (0, None) when flat."""
    if DRY_RUN:
        p = PAPER.position
        if p and p["ticker"] == ticker:
            return p["contracts"], p["side"]
        return 0, None
    d = await c.req("GET", "/portfolio/positions",
                    params={"ticker": ticker, "_": _ts_ms()})
    for p in d.get("market_positions", []):
        if p.get("ticker") == ticker:
            fp = float(p.get("position_fp", "0"))
            if fp == 0:
                return 0, None
            return abs(int(fp)), ("yes" if fp > 0 else "no")
    return 0, None


async def event_position(c: KalshiClient, event: str
                         ) -> tuple[str, int, str, int | None] | None:
    """Any open position on ANY market of this hourly event:
    (ticker, contracts, side, avg_entry_cents or None); None when flat.
    avg entry is derived from the API's market exposure so an adopted
    position can be monitored with correct TP/SL anchors."""
    if DRY_RUN:
        p = PAPER.position
        if p and p["ticker"].startswith(f"{event}-"):
            return p["ticker"], p["contracts"], p["side"], None
        return None
    d = await c.req("GET", "/portfolio/positions",
                    params={"event_ticker": event, "_": _ts_ms()})
    for p in d.get("market_positions", []):
        tk = p.get("ticker") or ""
        try:
            fp = float(p.get("position_fp", "0"))
        except Exception:
            fp = 0.0
        # ticker prefix double-checked in case the API ignores the filter
        if not tk.startswith(f"{event}-") or fp == 0:
            continue
        side = "yes" if fp > 0 else "no"
        n = abs(int(fp))
        avg = None
        try:
            exp = float(p.get("market_exposure_dollars", "0"))
            if n > 0 and exp > 0:
                avg = max(1, min(99, int(round(100 * exp / n))))
        except Exception:
            pass
        return tk, n, side, avg
    return None


async def resting_orders(c: KalshiClient, ticker: str | None = None) -> list[dict]:
    if DRY_RUN:
        return [o for o in PAPER.resting if ticker is None or o["ticker"] == ticker]
    d = await c.req("GET", "/portfolio/orders", params={"status": "resting"})
    orders = d.get("orders", [])
    return [o for o in orders if ticker is None or o.get("ticker") == ticker]


async def cancel_all(c: KalshiClient) -> None:
    """Cancel this bot's resting orders - ONLY on SERIES markets, so other
    bots sharing the account (sports, perp) are never touched.

    Uses the V2 cancel path (DELETE /portfolio/events/orders/{id}) -
    the legacy V1 path (DELETE /portfolio/orders/{id}) returns HTTP 410
    deprecated_v1_order_endpoint and was being silently swallowed by
    return_exceptions=True below, meaning cancel_all() never actually
    cancelled anything (discovered 2026-07-04 while investigating a
    resting order that survived a "successful" cancel)."""
    if DRY_RUN:
        PAPER.resting.clear()
        return
    orders = [o for o in await resting_orders(c)
              if (o.get("ticker") or "").startswith(SERIES)]
    if not orders:
        return
    _log("CANCEL", f"cancelling {len(orders)} resting {SERIES} order(s)")
    results = await asyncio.gather(
        *(c.req("DELETE", f"/portfolio/events/orders/{o['order_id']}")
          for o in orders),
        return_exceptions=True)
    failed = [r for r in results if isinstance(r, Exception)]
    if failed:
        _log("CANCEL", f"{len(failed)}/{len(orders)} cancel(s) FAILED: "
                       f"{failed[0]!r}")


# ── never sell what we do not hold ───────────────────────────────────────────
# Kalshi's V2 book is single-sided and quoted from the YES leg, so "sell YES"
# is an ASK. An ASK with no YES inventory does not fail - it OPENS A SHORT,
# which on this venue reads as a NO position. See the same guard in
# btc15/v4_bot_kalshi_btc15.py for the live incident that produced it.
#
# Callers here already read the position before exiting, but that read happens
# several awaits before the POST, and a resting TP can fill inside the gap.
# The invariant belongs at the wire.
SELL_GUARD_RETRIES = int(os.getenv("KALSHI_SELL_GUARD_RETRIES", "3"))
SELL_GUARD_DELAY_S = float(os.getenv("KALSHI_SELL_GUARD_DELAY_S", "1.5"))


async def sellable_contracts(c: KalshiClient, ticker: str, side: str,
                             want: int, tag: str = "SELL") -> int:
    """Contracts safe to sell right now: min(want, held), else 0. Never raises.

    Zero is retried briefly - a just-filled buy is not instantly visible in
    /portfolio/positions, and without the retry the opening TP would race the
    fill and silently stop being placed.
    """
    want = max(0, int(want))
    if want == 0:
        return 0
    for attempt in range(1, max(1, SELL_GUARD_RETRIES) + 1):
        try:
            held, held_side = await position_for(c, ticker)
        except Exception as e:                                  # noqa: BLE001
            _log(tag, f"position fetch failed ({e}) — NOTHING SOLD (fail safe)")
            return 0
        if held > 0:
            if held_side is not None and held_side != side:
                _log(tag, f"holding {held} {held_side.upper()} but asked to sell "
                          f"{side.upper()} — NOTHING SOLD (a sell on the other leg "
                          f"opens a new position)")
                return 0
            if held < want:
                _log(tag, f"asked to sell {want} but only {held} held — clamped")
            return min(want, held)
        if attempt < max(1, SELL_GUARD_RETRIES):
            await asyncio.sleep(SELL_GUARD_DELAY_S)
    _log(tag, f"{ticker}: NO open position — NOTHING SOLD "
              f"(selling flat would open a short)")
    return 0


async def place_order(c: KalshiClient, ticker: str, action: str, side: str,
                      count: int, price_cents: int, tag: str) -> bool:
    _log(tag, f"{'[DRY] ' if DRY_RUN else ''}{action.upper()} {side.upper()} "
              f"x{count} @ {price_cents}c on {ticker}")
    if DRY_RUN:
        PAPER.resting.append({"ticker": ticker, "action": action, "side": side,
                              "price": price_cents, "count": count})
        return True
    if action == "sell":
        count = await sellable_contracts(c, ticker, side, count, tag)
        if count <= 0:
            return False
    body = _mk_order(ticker, action, side, count, price_cents)
    try:
        await c.req("POST", ORDER_CREATE_PATH, body=body)
        return True
    except Exception as e:
        _log(tag, f"order FAILED: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════
#  MARKET DATA
# ══════════════════════════════════════════════════════════════════════════
def _cents(m: dict, key: str) -> int | None:
    raw = m.get(key)
    if raw is not None:
        try:
            return int(round(float(raw)))
        except Exception:
            pass
    raw = m.get(f"{key}_dollars")
    if raw is not None:
        try:
            return int(round(float(raw) * 100))
        except Exception:
            pass
    return None


def _strike(m: dict) -> float | None:
    raw = m.get("floor_strike") or m.get("strike_price") or m.get("cap_strike")
    try:
        return float(raw) if raw is not None else None
    except Exception:
        return None


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


async def open_markets(c: KalshiClient) -> list[dict]:
    d = await c.req("GET", "/markets", params={
        "series_ticker": SERIES, "status": "open", "limit": 1000})
    return d.get("markets", [])


async def market_bid(c: KalshiClient, ticker: str, side: str) -> int | None:
    """Best bid (cents) for side on one market."""
    try:
        d = await c.req("GET", f"/markets/{ticker}", params={"_": _ts_ms()})
        return _cents(d.get("market", {}), f"{side}_bid")
    except Exception as e:
        _log("BID", f"read failed: {e}")
        return None


async def current_hour_event(c: KalshiClient, after: datetime | None
                             ) -> tuple[str, datetime]:
    """Soonest-closing open KXBTCD event with close_time > now (and > after).
    Only events closing within 65 min qualify (= the CURRENT hour's market;
    Kalshi also lists tomorrow's same-hour event, which must be ignored).
    Blocks until one exists."""
    while True:
        try:
            now = _utc_now()
            closes: dict[str, datetime] = {}
            for m in await open_markets(c):
                ev, ct = m.get("event_ticker"), _parse_dt(m.get("close_time"))
                if not ev or ct is None or ct <= now:
                    continue
                if ct > now + timedelta(minutes=65):
                    continue
                if after is not None and ct <= after:
                    continue
                if ev not in closes or ct < closes[ev]:
                    closes[ev] = ct
            if closes:
                ev = min(closes, key=lambda k: closes[k])
                return ev, closes[ev]
        except Exception as e:
            _log("MARKET", f"event poll error: {e}")
        await asyncio.sleep(5)


# ══════════════════════════════════════════════════════════════════════════
#  SIGNALS - favorite side + POC agreement
# ══════════════════════════════════════════════════════════════════════════
class PocCache:
    """LiquiditySR POC, recomputed at most every POC_REFRESH_S."""
    def __init__(self) -> None:
        self._eng = LiquiditySR()
        self.price: float | None = None
        self.color: str | None = None            # Green / Red / Blue
        self._last = 0.0

    async def refresh(self) -> None:
        now = asyncio.get_event_loop().time()
        if now - self._last < POC_REFRESH_S and self.color is not None:
            return
        try:
            res = await lsr_run(engine=self._eng, verbose=False)
            poc = res.get("poc")
            if poc:
                self.price, self.color = poc["price"], poc["color"]
                _log("POC", f"{self.price:,.0f} ({self.color})")
            self._last = now
        except Exception as e:
            _log("POC", f"refresh failed: {e}")


def poc_agrees(side: str, poc_color: str | None) -> bool:
    return (side == "yes" and poc_color == "Green") or \
           (side == "no" and poc_color == "Red")


def _recent_strong_dir(btc: "BtcVidyaMonitor", lookback: int) -> str | None:
    """Most recent 'strong_buy'/'strong_sell' within the last `lookback`
    monitor ticks (15s each), or None.  Local to this file (rather than
    BtcVidyaMonitor.hasRecentStrongAgainst, which the module is shared with
    other bots) so it can implement REQUIRE-agreement instead of just
    not-opposed - see the module docstring for the backtest comparing the
    two."""
    history = list(btc.strength_history)[-lookback:]
    for sig in reversed(history):
        if sig in ("strong_buy", "strong_sell"):
            return sig
    return None


def strong_confirms(side: str, btc: "BtcVidyaMonitor",
                    lookback: int = STRONG_CONFIRM_LOOKBACK_TICKS) -> bool:
    """True iff the most recent STRONG BTC signal within `lookback` ticks
    agrees with `side` (YES <- STRONG_BUY, NO <- STRONG_SELL)."""
    rs = _recent_strong_dir(btc, lookback)
    return (side == "yes" and rs == "strong_buy") or \
           (side == "no" and rs == "strong_sell")


def _net30_in_favor(side: str, btc: "BtcVidyaMonitor") -> float | None:
    """Net USD move over the last ~30 min (btc.hourly_buf, ~15s ticks),
    signed so POSITIVE means the move favors `side`.  None when hourly_buf
    has fewer than NET30_LOOKBACK_TICKS+1 entries (monitor warmup, e.g.
    right after a restart) - callers must treat None as "no filter data
    yet" and ALLOW the trade, not block it (see pick_candidate)."""
    hist = list(btc.hourly_buf)
    if len(hist) < NET30_LOOKBACK_TICKS + 1:
        return None
    then, now = hist[-(NET30_LOOKBACK_TICKS + 1)], hist[-1]
    if then <= 0:
        return None
    raw = now - then
    return raw if side == "yes" else -raw


async def pick_candidate(c: KalshiClient, event: str, spot: float,
                         poc: PocCache, bid_lo: int,
                         btc: "BtcVidyaMonitor"
                         ) -> tuple[str, str, float, int, float | None] | None:
    """Among the event's strikes, return (ticker, side, strike, bid, net30)
    for the favorite whose bid is in [bid_lo, ENTRY_BID_HI] and whose side
    the POC confirms; prefer the bid closest to ENTRY_BID_SWEET.  Requires
    a recent STRONG BTC signal that AGREES with the side (YES needs
    STRONG_BUY, NO needs STRONG_SELL) - no confirming strong signal, no
    trade.  See the module docstring for why this requires agreement
    rather than letting the signal pick the direction outright (that
    backtests badly).  Also requires the 30-min net move to sit in
    [NET30_LO, NET30_HI] in the side's favor (exhaustion avoidance) unless
    there isn't yet enough price history to judge (warmup allows)."""
    best = None
    blocked_by_strong = False
    blocked_by_exhaustion = False
    for m in await open_markets(c):
        if m.get("event_ticker") != event:
            continue
        stk = _strike(m)
        if stk is None:
            continue
        side = "yes" if spot >= stk else "no"
        bid = _cents(m, f"{side}_bid")
        side_bid_lo = bid_lo + (YES_BID_LO_BONUS if side == "yes" else 0)
        if bid is None or not (side_bid_lo <= bid <= ENTRY_BID_HI):
            continue
        if not poc_agrees(side, poc.color):
            continue
        if not strong_confirms(side, btc):
            blocked_by_strong = True
            continue
        net30 = _net30_in_favor(side, btc)
        if net30 is not None and not (NET30_LO <= net30 <= NET30_HI):
            blocked_by_exhaustion = True
            continue
        dist = abs(bid - ENTRY_BID_SWEET)
        if best is None or dist < best[0]:
            best = (dist, m["ticker"], side, stk, bid, net30)
    if best is None:
        if blocked_by_strong:
            _log("GATE", "candidate(s) skipped - no recent STRONG BTC signal "
                         "confirms the side")
        if blocked_by_exhaustion:
            _log("GATE", f"candidate(s) skipped - 30m net move outside "
                         f"[{NET30_LO},{NET30_HI}] favor-band (exhaustion "
                         f"avoidance)")
    return (best[1], best[2], best[3], best[4], best[5]) if best else None


# ══════════════════════════════════════════════════════════════════════════
#  LEARNER - bounded self-tuning from the trade history CSV
# ══════════════════════════════════════════════════════════════════════════
class Learner:
    """
    Persists {pv_pct, tp_pct, sl_pct, bid_lo, n_trades} to STATE_FILE and
    re-fits every LEARN_EVERY trades on the last LEARN_WINDOW rows:

      pv_pct : Kelly-lite on recent win rate around the 70% design point -
               pv = 10 * (1 + 2.5*(wr - 0.70)), clamped 5-15.
      bid_lo : gets pickier (+1, max 72) after a losing window, relaxes
               (-1, min 65) after a window earning > +2%/trade.
      sl_pct : p90 of winners' max drawdown + 5pts (clamped 20-35) - the
               stop sits just past where winning trades bottom out.
      tp_pct : if fewer than 40% of exits reach TP, step down 1 (min 12);
               if more than 75% reach it, step up 1 (max 20).

    Every change is logged with its reason.  Deletion of the state file
    resets to the hard-coded defaults at the top of this file.
    """
    def __init__(self) -> None:
        self.pv_pct = PV_PCT_PER_TRADE
        self.tp_pct = TAKE_PROFIT_PCT
        self.sl_pct = STOP_LOSS_PCT
        self.bid_lo = ENTRY_BID_LO
        self.n_trades = 0
        # BTC-market bankroll ledger: the ONLY capital base this bot sizes
        # and learns from.  Seeded once, then moved only by this bot's
        # realized P&L - other bots on the shared account never touch it.
        self.bankroll = BTC_BANKROLL_SEED
        self._load()

    def _load(self) -> None:
        # Fresh session on EVERY start (user 08/03): the bankroll begins at
        # the seed, and tp/sl/pv/bid_lo begin at their defaults (or the
        # operator's pins below) rather than resuming the previous session's
        # learned values. The old state is logged for the record only —
        # within a session the learner still tunes and persists as before.
        try:
            if STATE_FILE.is_file():
                d = json.loads(STATE_FILE.read_text())
                _log("LEARN", f"previous session: bankroll="
                              f"${float(d.get('bankroll', 0) or 0):.2f} "
                              f"tp={float(d.get('tp_pct', 0) or 0):.1f}% "
                              f"sl={float(d.get('sl_pct', 0) or 0):.1f}% "
                              f"- fresh session resets to seed/defaults")
        except Exception as e:
            _log("LEARN", f"state read failed ({e}) - using defaults")
        if TP_PCT_OVERRIDE > 0:
            # applied AFTER the state load so the stored tp_pct cannot win
            self.tp_pct = TP_PCT_OVERRIDE
            _log("LEARN", f"tp_pct pinned to {self.tp_pct:.1f}% by BTC60_TP_PCT "
                          f"- the learner will not adjust it")
        if SL_PCT_OVERRIDE > 0:
            # same placement and reason as the tp pin: after the state load,
            # so a stored sl_pct cannot override what the operator typed
            self.sl_pct = SL_PCT_OVERRIDE
            _log("LEARN", f"sl_pct pinned to {self.sl_pct:.1f}% by BTC60_SL_PCT "
                          f"- the learner will not adjust it")
        _log("LEARN", f"session starts: bankroll=${self.bankroll:.2f} "
                      f"pv={self.pv_pct:.1f}% tp={self.tp_pct:.1f}% "
                      f"sl={self.sl_pct:.1f}% bid_lo={self.bid_lo}")
        # profit target is measured on THIS bot's bankroll, never the shared
        # account's portfolio value
        self.start_bankroll = self.bankroll
        self.halted = False

    def target_reached(self) -> bool:
        """True once realized P&L has grown this bot's own bankroll by
        BTC60_TARGET_PCT. No target set (0) = never halts."""
        if BTC_TARGET_PCT <= 0 or not self.start_bankroll:
            return False
        goal = self.start_bankroll * (1 + BTC_TARGET_PCT / 100.0)
        if self.bankroll < goal:
            return False
        if not self.halted:
            self.halted = True
            _log("TARGET", f"bankroll ${self.bankroll:.2f} >= ${goal:.2f} "
                           f"(+{BTC_TARGET_PCT:.0f}% on ${self.start_bankroll:.2f}) "
                           f"- no new entries")
        return True

    def _save(self) -> None:
        try:
            STATE_FILE.write_text(json.dumps({
                "pv_pct": self.pv_pct, "tp_pct": self.tp_pct,
                "sl_pct": self.sl_pct, "bid_lo": self.bid_lo,
                "n_trades": self.n_trades,
                "bankroll": round(self.bankroll, 2),
                "updated": _utc_now().isoformat()}, indent=2))
        except Exception as e:
            _log("LEARN", f"state save failed: {e}")

    def settle(self, pnl: float) -> None:
        """Apply one trade's realized P&L to the BTC bankroll."""
        self.bankroll += pnl
        self._save()

    @staticmethod
    def _clamp(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, v))

    def on_trade_logged(self) -> None:
        self.n_trades += 1
        if self.n_trades % FAST_CHECK_EVERY == 0:
            self._fast_check()
        if self.n_trades % LEARN_EVERY == 0:
            self._fit()          # broader 60-trade fit has the final say
        self._save()

    def _fast_check(self) -> None:
        """
        Reactive brake: every FAST_CHECK_EVERY trades, look at just the
        last FAST_CHECK_EVERY rows (not the full LEARN_WINDOW).  If
        FAST_CHECK_LOSS_THRESHOLD or more were losses, tighten right now -
        bid_lo up a notch and pv_pct cut 15% - instead of waiting for the
        next LEARN_EVERY-trade _fit().  Never loosens; only _fit() (with
        its longer, more statistically meaningful window) is allowed to
        widen entries or raise size back up.
        """
        try:
            with CSV_FILE.open("r", newline="") as f:
                rows = list(csv.DictReader(f))[-FAST_CHECK_EVERY:]
        except Exception:
            return
        if len(rows) < FAST_CHECK_EVERY:
            return
        losses = sum(1 for r in rows if float(r.get("ret_pct") or 0) <= 0)
        if losses < FAST_CHECK_LOSS_THRESHOLD:
            return

        old_pv, old_bid = self.pv_pct, self.bid_lo
        self.pv_pct = self._clamp(self.pv_pct * 0.85, *PV_BOUNDS)
        if self.bid_lo < BID_LO_BOUNDS[1]:
            self.bid_lo += 1
        _log("FASTCHECK",
             f"{losses}/{FAST_CHECK_EVERY} losses in the last "
             f"{FAST_CHECK_EVERY} trades - tightening now (not waiting for "
             f"the next {LEARN_EVERY}-trade fit): "
             f"pv_pct {old_pv:.1f}->{self.pv_pct:.1f}%  "
             f"bid_lo {old_bid}->{self.bid_lo}")

    def _fit(self) -> None:
        try:
            with CSV_FILE.open("r", newline="") as f:
                rows = list(csv.DictReader(f))[-LEARN_WINDOW:]
        except Exception:
            return
        if len(rows) < LEARN_EVERY:
            return
        rets = [float(r["ret_pct"]) for r in rows if r.get("ret_pct")]
        if not rets:
            return
        wr = sum(1 for r in rets if r > 0) / len(rets)
        avg = sum(rets) / len(rets)

        new_pv = self._clamp(PV_PCT_PER_TRADE * (1 + 2.5 * (wr - 0.70)),
                             *PV_BOUNDS)
        if abs(new_pv - self.pv_pct) >= 0.5:
            _log("LEARN", f"pv_pct {self.pv_pct:.1f} -> {new_pv:.1f} "
                          f"(win rate {wr:.0%} over last {len(rets)})")
            self.pv_pct = new_pv

        if avg < 0 and self.bid_lo < BID_LO_BOUNDS[1]:
            self.bid_lo += 1
            _log("LEARN", f"bid_lo -> {self.bid_lo} (avg {avg:+.2f}%/trade "
                          f"negative - being pickier)")
        elif avg > 2.0 and self.bid_lo > BID_LO_BOUNDS[0]:
            self.bid_lo -= 1
            _log("LEARN", f"bid_lo -> {self.bid_lo} (avg {avg:+.2f}%/trade - "
                          f"widening entries)")

        win_dds = sorted(float(r["max_dd_pct"]) for r in rows
                         if r.get("max_dd_pct") and float(r.get("ret_pct") or 0) > 0)
        if SL_PCT_OVERRIDE > 0:
            pass                      # user pinned the stop; do not drift it
        elif len(win_dds) >= 10:
            p90 = win_dds[int(0.9 * (len(win_dds) - 1))]
            new_sl = self._clamp(p90 + 5.0, *SL_BOUNDS)
            if abs(new_sl - self.sl_pct) >= 1.0:
                _log("LEARN", f"sl_pct {self.sl_pct:.1f} -> {new_sl:.1f} "
                              f"(p90 winner drawdown {p90:.1f}%)")
                self.sl_pct = new_sl

        tp_hits = sum(1 for r in rows if r.get("exit_reason") == "TAKE_PROFIT")
        frac = tp_hits / len(rows)
        if TP_PCT_OVERRIDE > 0:
            pass                      # user pinned the target; do not drift it
        elif frac < 0.40 and self.tp_pct > TP_BOUNDS[0]:
            self.tp_pct -= 1.0
            _log("LEARN", f"tp_pct -> {self.tp_pct:.1f} (only {frac:.0%} of "
                          f"exits reached TP)")
        elif frac > 0.75 and self.tp_pct < TP_BOUNDS[1]:
            self.tp_pct += 1.0
            _log("LEARN", f"tp_pct -> {self.tp_pct:.1f} ({frac:.0%} of exits "
                          f"reached TP - asking for more)")


# ══════════════════════════════════════════════════════════════════════════
#  TRADE LOGGING
# ══════════════════════════════════════════════════════════════════════════
def init_csv() -> None:
    if not CSV_FILE.exists():
        with CSV_FILE.open("w", newline="") as f:
            csv.writer(f).writerow(_CSV_COLS)


def log_trade(**kw) -> None:
    with CSV_FILE.open("a", newline="") as f:
        csv.writer(f).writerow([kw.get(c, "") for c in _CSV_COLS])


# ══════════════════════════════════════════════════════════════════════════
#  TRADE LIFECYCLE
# ══════════════════════════════════════════════════════════════════════════
async def flatten(c: KalshiClient, ticker: str) -> int | None:
    """
    Cancel everything and sell any position on ticker, escalating with a
    FRESHLY-fetched bid at each attempt (rather than one static undercut
    followed by a single 15s wait) so a fast-moving market gets less time
    to run away from a stale price before we react.

    Returns the exit price (cents) actually used, or None if there was
    nothing to flatten - already closed elsewhere (the TP sell filled a
    moment earlier, or this is a stale/duplicate read).  Callers must NOT
    fabricate a price when this returns None; see manage_and_log(), which
    treats it as "no phantom trade to log" instead of a real exit.

    2026-07-07: the first attempt used to undercut the bid by 2c even
    though selling AT the current bid is already marketable (crosses the
    book, fills as taker) - that 2c was pure giveaway.  Paper trades showed
    realized STOP_LOSS exits averaging -31%/trade against a nominal -20%
    SL; a chunk of that gap was this unnecessary undercut stacking with the
    ordinary book-moves-while-we-poll slippage.  Selling right at the bid
    on the first attempt keeps the same escalation for subsequent retries.
    """
    await cancel_all(c)
    contracts, side = await position_for(c, ticker)
    if contracts <= 0:
        return None

    px = None
    for i, undercut in enumerate((0, 2, 4)):
        bid = await market_bid(c, ticker, side)
        px = max(1, (bid if bid is not None else 3) - undercut)
        tag = "selling" if i == 0 else f"re-pricing (attempt {i + 1})"
        _log("FLAT", f"{tag} {contracts} {side.upper()} @ {px}c")
        await place_order(c, ticker, "sell", side, contracts, px, "FLAT")
        if DRY_RUN:
            PAPER.resting.clear()
            PAPER.position = None
            return px
        await asyncio.sleep(5)
        contracts, side = await position_for(c, ticker)
        if contracts <= 0:
            return px
        await cancel_all(c)

    _log("FLAT", f"still holding {contracts} after 3 re-prices - "
                 f"final fire-sale @ 2c")
    await place_order(c, ticker, "sell", side, contracts, 2, "FLAT")
    await asyncio.sleep(5)
    contracts, side = await position_for(c, ticker)
    if contracts > 0:
        _log("FLAT", f"WARNING: still holding {contracts} {side.upper()} on "
                     f"{ticker} after fire-sale - needs manual attention")
    return 2


async def await_entry_fill(c: KalshiClient, ticker: str, side: str,
                           limit_cents: int, contracts: int,
                           cutoff: datetime) -> bool:
    """Wait for the maker buy to fill.  Cancels + returns False at cutoff."""
    while _utc_now() < cutoff:
        if DRY_RUN:
            # simulated maker fill: market bid trades at/below our limit
            bid = await market_bid(c, ticker, side)
            if bid is not None and bid <= limit_cents:
                PAPER.resting.clear()
                PAPER.position = {"ticker": ticker, "side": side,
                                  "contracts": contracts}
                _log("FILL", f"[DRY] filled {contracts} @ {limit_cents}c")
                return True
        else:
            held, _ = await position_for(c, ticker)
            pending = await resting_orders(c, ticker)
            if held >= contracts:
                _log("FILL", f"filled {held} @ {limit_cents}c")
                return True
            if held > 0 and not pending:
                _log("FILL", f"partial fill {held}/{contracts} - proceeding")
                return True
            if not pending and held == 0:
                # No resting order AND no position can also be a race: an
                # instant (taker) fill whose position hasn't shown up in the
                # API yet.  This exact race once double-bought a position -
                # re-check before declaring the order dead.
                await asyncio.sleep(3)
                held, _ = await position_for(c, ticker)
                if held > 0:
                    _log("FILL", f"filled {held} @ {limit_cents}c "
                                 f"(position lagged the fill)")
                    return True
                _log("FILL", "order gone without fill (cancelled?)")
                return False
        await asyncio.sleep(POLL_S)
    _log("FILL", "entry window over - cancelling unfilled buy")
    await cancel_all(c)
    # a last-moment partial fill still leaves a position; caller re-checks
    held, _ = await position_for(c, ticker)
    return held > 0


async def monitor_position(c: KalshiClient, ticker: str, side: str,
                           entry_cents: int, contracts: int,
                           tp_cents: int, sl_cents: int,
                           deadline: datetime
                           ) -> tuple[str, int, float, float]:
    """
    Watch the position until TP fills, SL triggers, or the flatten deadline.
    Returns (reason, exit_cents, max_gain_pct, max_dd_pct).
    """
    max_bid = min_bid = entry_cents
    while True:
        if _utc_now() >= deadline:
            px = await flatten(c, ticker)
            if px is None:
                return ("ALREADY_FLAT", 0,
                        100 * (max_bid - entry_cents) / entry_cents,
                        100 * (entry_cents - min_bid) / entry_cents)
            return ("DEADLINE_FLATTEN", px,
                    100 * (max_bid - entry_cents) / entry_cents,
                    100 * (entry_cents - min_bid) / entry_cents)

        bid = await market_bid(c, ticker, side)
        if bid is not None and bid > 0:
            max_bid, min_bid = max(max_bid, bid), min(min_bid, bid)

            if DRY_RUN and bid >= tp_cents:
                PAPER.resting.clear()
                PAPER.position = None
                return ("TAKE_PROFIT", tp_cents,
                        100 * (max_bid - entry_cents) / entry_cents,
                        100 * (entry_cents - min_bid) / entry_cents)

            if bid <= sl_cents:
                _log("MON", f"SL: bid {bid}c <= {sl_cents}c - dumping")
                px = await flatten(c, ticker)
                if px is None:
                    return ("ALREADY_FLAT", 0,
                            100 * (max_bid - entry_cents) / entry_cents,
                            100 * (entry_cents - min_bid) / entry_cents)
                return ("STOP_LOSS", px,
                        100 * (max_bid - entry_cents) / entry_cents,
                        100 * (entry_cents - min_bid) / entry_cents)

        if not DRY_RUN:
            held, _ = await position_for(c, ticker)
            if held == 0:
                return ("TAKE_PROFIT", tp_cents,
                        100 * (max_bid - entry_cents) / entry_cents,
                        100 * (entry_cents - min_bid) / entry_cents)

        await asyncio.sleep(POLL_S)


async def manage_and_log(c: KalshiClient, learner: "Learner", *, event: str,
                         ticker: str, side: str, strike: float,
                         entry_cents: int, real: int, spot: float | None,
                         poc: PocCache, minute: float,
                         flatten_deadline: datetime,
                         net30: float | None = None) -> str:
    """Shared tail of every trade: place the TP sell, monitor to
    TP/SL/deadline, settle the bankroll, and log the row.  Used by both the
    normal post-fill path and the open-position adoption guard so the two
    can never drift apart.  Returns the exit reason."""
    tp_cents = min(97, math.ceil(entry_cents * (1 + learner.tp_pct / 100)))
    sl_cents = max(2, math.floor(entry_cents * (1 - learner.sl_pct / 100)))
    _log("TRADE", f"holding {real} @ {entry_cents}c | TP {tp_cents}c "
                  f"SL {sl_cents}c | flat by {flatten_deadline:%H:%MZ}")
    await place_order(c, ticker, "sell", side, real, tp_cents, "TP")

    reason, exit_cents, max_gain, max_dd = await monitor_position(
        c, ticker, side, entry_cents, real, tp_cents, sl_cents,
        flatten_deadline)

    if reason == "ALREADY_FLAT":
        # flatten() found nothing to sell - the position was already closed
        # by the time we tried to exit it (a TP fill we hadn't noticed yet,
        # or a stale read).  Nothing real happened at THIS moment, so do
        # not settle the bankroll or log a fabricated trade for it.
        _log("EXIT", f"{ticker} was already flat by the time we tried to "
                     f"exit - not logging a phantom trade")
        return reason

    fee = 0.07 * (exit_cents / 100) * (1 - exit_cents / 100) * real \
        if reason != "TAKE_PROFIT" else 0.0   # TP sell rests = maker
    pnl = (exit_cents - entry_cents) / 100 * real - fee
    learner.settle(pnl)                # BTC bankroll ledger only
    ret_pct = 100 * (exit_cents - entry_cents) / entry_cents
    _log("EXIT", f"{reason} @ {exit_cents}c | pnl ${pnl:+.2f} "
                 f"({ret_pct:+.1f}%) | BTC bankroll ${learner.bankroll:.2f}")

    log_trade(timestamp=f"{_utc_now():%Y-%m-%d %H:%M:%S}",
              event=event, ticker=ticker, side=side, strike=strike,
              contracts=real, entry_cents=entry_cents,
              exit_cents=round(exit_cents, 2), exit_reason=reason,
              pnl_dollars=round(pnl, 2), ret_pct=round(ret_pct, 2),
              max_gain_pct=round(max_gain, 2),
              max_dd_pct=round(max_dd, 2),
              pv_after=round(learner.bankroll, 2),
              pv_pct_used=learner.pv_pct, tp_pct=learner.tp_pct,
              sl_pct=learner.sl_pct,
              spot_at_entry=round(spot, 2) if spot else "",
              poc_price=poc.price, poc_color=poc.color,
              minute_of_hour=round(minute, 1),
              net30_at_entry=round(net30, 1) if net30 is not None else "")
    learner.on_trade_logged()
    return reason


# ══════════════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════
async def run_bot() -> None:
    _acquire_lock()
    log_fh = LOG_FILE.open("a", encoding="utf-8")
    sys.stdout = _Tee(sys.__stdout__, log_fh)
    sys.stderr = _Tee(sys.__stderr__, log_fh)

    learner = Learner()
    init_csv()
    _log("CFG", f"series={SERIES} DRY_RUN={DRY_RUN} "
                f"btc_bankroll=${learner.bankroll:.2f} tp={learner.tp_pct}% "
                f"sl={learner.sl_pct}% pv={learner.pv_pct}% "
                f"bid_band={learner.bid_lo}-{ENTRY_BID_HI}c "
                f"entry_window=min {ENTRY_START_MIN}-{ENTRY_CUTOFF_MIN}")

    c = KalshiClient()
    btc = BtcVidyaMonitor()
    btc.start()
    poc = PocCache()

    last_close: datetime | None = None
    try:
        while True:
            event, close_time = await current_hour_event(c, last_close)
            hour_open = close_time - timedelta(hours=1)
            entry_open  = hour_open + timedelta(minutes=ENTRY_START_MIN)
            entry_cutoff = hour_open + timedelta(minutes=ENTRY_CUTOFF_MIN)
            flatten_deadline = close_time - timedelta(minutes=FLATTEN_BEFORE_CLOSE_MIN)
            _log("HOUR", f"event {event} closes {close_time:%H:%MZ} | entries "
                         f"{entry_open:%H:%M}-{entry_cutoff:%H:%MZ}")

            if _utc_now() >= entry_cutoff:
                _log("HOUR", "entry window already over - waiting for next hour")
                last_close = close_time
                continue

            trades_this_hour = 0
            while _utc_now() < entry_cutoff and trades_this_hour < MAX_TRADES_PER_HOUR:
                now = _utc_now()
                if now < entry_open:
                    await asyncio.sleep(min(POLL_S,
                        max(1, (entry_open - now).total_seconds())))
                    continue

                bank = learner.bankroll
                # profit target on THIS bot's bankroll (not the shared account)
                if learner.target_reached():
                    return
                # bank stop-loss (user 08/03): protect the capital
                if (BANK_SL_PCT > 0 and learner.start_bankroll
                        and bank <= learner.start_bankroll * (1 - BANK_SL_PCT / 100.0)):
                    _log("BANK-SL", f"SL HIT on Bank: ${bank:.2f} <= "
                                    f"-{BANK_SL_PCT:.0f}% on "
                                    f"${learner.start_bankroll:.2f} - stopping")
                    return
                if MIN_PORTFOLIO_HALT > 0 and bank < MIN_PORTFOLIO_HALT:
                    _log("HALT", f"BTC bankroll ${bank:.2f} < "
                                 f"${MIN_PORTFOLIO_HALT} - stopping "
                                 f"(no new trades)")
                    return

                # NEVER stack positions: if this hour's event already has an
                # open position (e.g. a fill the API reported late, or a
                # leftover from a partial flatten), place NOTHING new -
                # adopt it and manage it to TP/SL instead.
                existing = await event_position(c, event)
                if existing:
                    a_tk, a_real, a_side, a_avg = existing
                    entry_cents = (a_avg
                                   or await market_bid(c, a_tk, a_side) or 50)
                    _log("GUARD", f"open position {a_real} {a_side.upper()} "
                                  f"on {a_tk} (avg~{entry_cents}c) - no new "
                                  f"orders this hour; managing it to TP/SL")
                    await cancel_all(c)   # clear stale buys/TPs, re-anchor
                    try:
                        a_strike = float(a_tk.rsplit("-T", 1)[-1])
                    except Exception:
                        a_strike = 0.0
                    minute = (_utc_now() - hour_open).total_seconds() / 60
                    reason = await manage_and_log(
                        c, learner, event=event, ticker=a_tk, side=a_side,
                        strike=a_strike, entry_cents=entry_cents, real=a_real,
                        spot=btc.last_price, poc=poc, minute=minute,
                        flatten_deadline=flatten_deadline)
                    if reason != "ALREADY_FLAT":
                        trades_this_hour += 1
                    if reason == "DEADLINE_FLATTEN":
                        break   # hour is over for us
                    continue

                await poc.refresh()
                spot = btc.last_price
                if spot is None or poc.color is None:
                    await asyncio.sleep(POLL_S)
                    continue

                # ── NO-TRADE window (user 08/03): stay alive, enter
                # nothing. Announced once per window, not every poll.
                if _in_no_trade_window() is not None:
                    if not _nt_announced[0]:
                        _w = _in_no_trade_window()
                        _log("NO-TRADE", f"local time inside "
                                         f"{_w[0]:%H:%M}-{_w[1]:%H:%M} - no "
                                         f"new entries until it ends")
                        _nt_announced[0] = True
                    await asyncio.sleep(POLL_S)
                    continue
                _nt_announced[0] = False

                cand = await pick_candidate(c, event, spot, poc, learner.bid_lo, btc)
                if cand is None:
                    await asyncio.sleep(POLL_S)
                    continue
                ticker, side, strike, bid, net30 = cand
                minute = (_utc_now() - hour_open).total_seconds() / 60

                # common bot contract (user 08/03): fixed size, %-of-bankroll
                # sizing removed — contracts means contracts
                contracts = max(1, FIXED_CONTRACTS)
                cost = contracts * bid / 100
                # spend cap: never order more than the SHARED account can fund
                cash = await account_cash(c)
                if cost > cash:
                    contracts = int(cash // (bid / 100))
                    if contracts < 1:
                        _log("ENTRY", f"account cash ${cash:.2f} can't fund "
                                      f"even 1 contract @ {bid}c - waiting")
                        await asyncio.sleep(POLL_S)
                        continue
                    cost = contracts * bid / 100
                    _log("ENTRY", f"capped to {contracts} contracts by "
                                  f"account cash ${cash:.2f}")
                net30_s = f"{net30:+.0f}" if net30 is not None else "warmup"
                _log("ENTRY", f"{ticker} {side.upper()} strike={strike:,.0f} "
                              f"bid={bid}c spot=${spot:,.0f} poc={poc.color} "
                              f"net30={net30_s} min={minute:.0f} | "
                              f"{contracts} contracts "
                              f"(~${cost:.2f} = {learner.pv_pct:.0f}% of "
                              f"${bank:.2f} BTC bankroll)")

                if not await place_order(c, ticker, "buy", side, contracts, bid,
                                         "BUY"):
                    await asyncio.sleep(POLL_S)
                    continue

                if not await await_entry_fill(c, ticker, side, bid, contracts,
                                              entry_cutoff):
                    continue

                held, _side = await position_for(c, ticker)
                real = held if held > 0 else contracts
                reason = await manage_and_log(
                    c, learner, event=event, ticker=ticker, side=side,
                    strike=strike, entry_cents=bid, real=real, spot=spot,
                    poc=poc, minute=minute,
                    flatten_deadline=flatten_deadline, net30=net30)
                if reason != "ALREADY_FLAT":
                    trades_this_hour += 1

                if reason == "DEADLINE_FLATTEN":
                    break   # hour is over for us

            # ── end of entry window: make sure nothing is left behind ────────
            await cancel_all(c)
            # safety sweep: if a position exists on any market of this event,
            # keep monitoring it to TP/SL/deadline via the normal path above;
            # here we only guarantee flatness at the deadline.
            leftover = None
            if not DRY_RUN:
                try:
                    d = await c.req("GET", "/portfolio/positions",
                                    params={"event_ticker": event, "_": _ts_ms()})
                    for p in d.get("market_positions", []):
                        tk = p.get("ticker") or ""
                        # belt-and-braces: only THIS event's markets, in case
                        # the API ignores the event_ticker filter
                        if (tk.startswith(f"{event}-")
                                and abs(float(p.get("position_fp", "0"))) > 0):
                            leftover = tk
                            break
                except Exception:
                    pass
            elif PAPER.position:
                leftover = PAPER.position["ticker"]
            if leftover:
                wait_s = (flatten_deadline - _utc_now()).total_seconds()
                _log("SWEEP", f"unexpected position on {leftover} - flattening "
                              f"{'now' if wait_s <= 0 else f'at deadline'}")
                if wait_s > 0:
                    await asyncio.sleep(wait_s)
                await flatten(c, leftover)

            last_close = close_time
            _log("HOUR", f"done with {event} ({trades_this_hour} trade(s)) - "
                         f"next hour")
            await asyncio.sleep(5)
    finally:
        try:
            await cancel_all(c)
        except Exception:
            pass
        try:
            await btc.stop()
        except Exception:
            pass
        try:
            await c.close()
        except Exception:
            pass
        try:
            log_fh.close()
        except Exception:
            pass
        _release_lock()


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
