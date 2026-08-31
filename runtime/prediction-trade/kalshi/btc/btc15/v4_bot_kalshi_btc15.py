#!/usr/bin/env python3
"""
Kalshi BTC-15 Minute Async Trading Bot  (Opus 4.6 Build)
=========================================================
Fully asynchronous, profit-oriented algo for the KXBTC15M series.

Install:
    pip install aiohttp cryptography python-dotenv numpy pandas

Run:
    python bot_async.py
"""

from __future__ import annotations

import asyncio
import base64
import csv
import json
import math
import os
import shutil
import sys
import uuid
from collections import Counter, deque
from datetime import datetime, time as _time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import AsyncIterator, Literal, Optional

import aiohttp
import numpy as np
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as _padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from dotenv import load_dotenv

# Ensure project root is on sys.path so `import btc` works whether this bot
# is launched via the root dispatcher (cwd=root) or standalone (cwd=kalshi/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from btc import BtcVidyaMonitor   # shared BTC meta-monitor (CUSUM + 4-vote)

# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  CONFIGURATION                                                           ║
# ╚════════════════════════════════════════════════════════════════════════════╝
load_dotenv()

BASE_URI              = os.getenv("BASE_URI", "https://external-api.kalshi.com/trade-api/v2")
API_KEY_ID            = os.getenv("KALSHI_API_KEY_ID", "")
PRIVATE_KEY_PATH      = os.getenv("KALSHI_PRIVATE_KEY", "kalshi_private.pem")

CONTRACTS             = int(os.getenv("KALSHI_CONTRACTS", "50"))
PROFIT_PCT            = float(os.getenv("KALSHI_PROFIT_PCT", "50"))
STOP_PCT              = float(os.getenv("KALSHI_STOP_PCT", "60"))
DRY_RUN               = os.getenv("DRY_RUN_MODE", "TRUE").upper() == "TRUE"
TIME_SEC_TO_ORDER     = int(os.getenv("TIME_SEC_TO_ORDER", "450"))
# One trade per market by default (user 07/30). Re-entering the same 15-minute
# market doubles exposure to a single BTC move that has already gone against
# the first entry, which is the opposite of diversification.
MAX_TRADES_PER_MARKET = int(os.getenv("MAX_TRADES_PER_MARKET", "1"))
RUNNER_CONTRACTS      = int(os.getenv("RUNNER_CONTRACTS", "0"))

# Account-PV floor. DISABLED by default (user 07/30): the Kalshi account is
# shared with the sports/btc60/perp bots, so a floor on its joint value let one
# bot's drawdown halt the others. Risk lives in this bot's own bankroll now.
# Set a positive number only to deliberately restore the old behaviour.
DO_NOT_BUY_IF_PORTFOLIO_BELOW = int(os.getenv("DO_NOT_BUY_IF_PORTFOLIO_BELOW", "0") or 0)

# ── This bot's OWN bankroll (user 07/30) ─────────────────────────────────────
# Same contract as btc60 and the sports banks: BTC_BANKROLL is the capital
# THIS bot trades, BTC15_TARGET_PCT is the profit target measured on it, and
# the ledger moves only on this bot's realized P&L — never the shared account
# balance. The ledger is persisted so a restart resumes where it left off; an
# explicit BTC_BANKROLL reseeds it so the number the operator typed is the one
# traded.
BTC15_BANKROLL   = float(os.getenv("BTC_BANKROLL", "0") or 0)
BTC15_TARGET_PCT = float(os.getenv("BTC15_TARGET_PCT", "0") or 0)
# Bank stop-loss (user 08/03): stop once realized P&L has SHRUNK the bankroll
# by this percent — the capital-protection mirror of the target above.
BTC15_BANK_SL_PCT = float(os.getenv("BTC15_BANK_SL_PCT", "0") or 0)

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


# Profit-ratchet for the MIN-PV floor above.  On every WINNING trade the floor
# ratchets UP (never down) to:  max(floor, pv_after - PORTFOLIO_FLOOR_BUFFER),
# locking in realised gains.  PORTFOLIO_FLOOR_BUFFER is the fixed $ risk budget
# kept below the latest portfolio; if 0/unset it defaults at runtime to
# (starting_portfolio - starting_floor) on the first balance read.
PORTFOLIO_FLOOR_BUFFER = float(os.getenv("PORTFOLIO_FLOOR_BUFFER", "0") or 0)

# Daily profit cap — once today's portfolio value has grown by this percentage
# above the day's starting value, stop placing new orders for the day.
# 0 (default) disables the gate.  The day-start baseline is persisted in
# kalshi_day_start_<YYYYMMDD>.txt (CST date) next to the CSV so the bot
# resumes the same baseline if restarted mid-day.
# Example: start the day at $100, TARGET_PORTFOLIO_PCT=50 → halt new orders
# once portfolio ≥ $150.
TARGET_PORTFOLIO_PCT = float(os.getenv("TARGET_PORTFOLIO_PCT", "0"))

# When False: place the buy and let the market settle naturally — no TP sell,
# no stop-loss monitor.  Bot moves straight to the next market after the fill.
DO_YOU_HAVE_STOP_SELL = os.getenv("DO_YOU_HAVE_STOP_SELL", "TRUE").upper() == "TRUE"

# Only used when DO_YOU_HAVE_STOP_SELL=False.
# Contracts to buy = ceil((CONTRACTS_PV_PCT/100 * portfolio_value) / 0.56)
# e.g. PCT=25, PV=$10 → ceil(0.25*10/0.56) = ceil(4.46) = 5 contracts
CONTRACTS_PV_PCT = float(os.getenv("CONTRACTS_PV_PCT", "25"))

# ── Lotto trade (fun / high-risk) ────────────────────────────────────────────
# Only active when DO_YOU_HAVE_STOP_SELL=FALSE and LOTTO_TRADE=TRUE.
# If market age < 320s and the live bid for the chosen direction drops
# below 14¢, place immediately at 15¢ with LOTTO_CONTRACTS contracts.
# Normal band-guard and pre-order checks continue as usual after placement.
LOTTO_TRADE     = os.getenv("LOTTO_TRADE",     "FALSE").upper() == "TRUE"
LOTTO_CONTRACTS = int(os.getenv("LOTTO_CONTRACTS", "10"))

# Entry price band — only place orders when current bid is inside this range.
# Below MIN: too cheap → market expects this side to lose, low TP gain potential.
# Above MAX: too expensive → minimal upside (TP cap 91¢) vs full downside.
MIN_ENTRY_CENTS       = int(os.getenv("MIN_ENTRY_CENTS", "42"))
MAX_ENTRY_CENTS       = int(os.getenv("MAX_ENTRY_CENTS", "80"))

SENTIMENT_SIZE      = int(os.getenv("SENTIMENT_SIZE", "100"))        # recent directional events to sample
SELL_PCT_THRESHOLD  = float(os.getenv("SELL_PCT_THRESHOLD", "0.55"))      # > 55 % sells → bearish

SENTIMENT_SIZE1      = int(os.getenv("SENTIMENT_SIZE1", "33"))        # recent directional events to sample
SELL_PCT_THRESHOLD1  = float(os.getenv("SELL_PCT_THRESHOLD1", "0.65"))      # > 65 % sells → bearish

MAX_LOSS_RATE        = float(os.getenv("MAX_LOSS_RATE", "33"))        # halt bot if loss_rate exceeds this %


# Default for latestBtcVidyaSignal() when the monitor has < 5 non-hold
# signals in its history (cold start / extremely flat market).
# Valid values: "hold" (block trades), "buy", or "sell".
#   "hold" → safest; bot waits for BTC monitor to warm up before any trade
#   "buy"  → optimistic; allow trades when BTC has no clear signal yet
#   "sell" → pessimistic; lean toward flipping direction when no BTC data
_btc_cold_raw = os.getenv("BTC_COLD_START_DEFAULT", "hold").strip().lower()
BTC_COLD_START_DEFAULT: SignalT = (
    _btc_cold_raw if _btc_cold_raw in ("buy", "sell", "hold") else "hold"
)   # type: ignore[assignment]


SERIES          = "KXBTC15M"
# Platform identity — written as the first column of each CSV row, and used
# to filter rows when computing this platform's win rate.
PLATFORM_NAME   = "kalshi"
# CSV path may be overridden by the root dispatcher (bot.py at project root)
# so both platforms write to a single shared trade_history.csv.
CSV_FILE        = os.getenv("BOT_CSV_PATH", "trade_history.csv")
BUY_CENTS       = 95          # aggressive buy  → $0.95
FIRE_SALE_CENTS = 5           # emergency exit   → $0.05

# ── Trading-hours halt windows ────────────────────────────────────────────────
# Bot will cancel orders, fire-sale any open position, and (optionally) shut
# down the machine when the current local time falls inside any configured
# halt window.  Multiple windows are supported via numbered env vars:
#
#   HALT_START_TIME1=06:15   HALT_END_TIME1=09:45
#   HALT_START_TIME2=22:15   HALT_END_TIME2=02:45   ← wraps midnight
#   …                                                  (1..9 are scanned)
#
# The legacy unsuffixed pair (HALT_START_TIME / HALT_END_TIME) is still
# honoured and combined with any numbered pairs.  If nothing is configured
# the bot falls back to a single window of 06:15–10:45.
HALT_TIMEZONE         = os.getenv("HALT_TIMEZONE",        "America/Chicago")
HALT_MACHINE_SHUTDOWN = os.getenv("HALT_MACHINE_SHUTDOWN", "FALSE").upper() == "TRUE"


def _parse_hhmm(s: str) -> _time:
    """Parse a 'HH:MM' string into a datetime.time, raising on bad input."""
    parts = s.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Expected HH:MM, got {s!r}")
    return _time(int(parts[0]), int(parts[1]))


def _collect_halt_windows() -> list[tuple[_time, _time]]:
    """
    Read every HALT_*_TIME[N] pair from the env and return the list of
    (start, end) tuples.  Order: legacy unsuffixed pair first (if set),
    then numbered pairs in order 1..9.  Numbered slots with only one half
    defined are skipped with a warning.  Each window can wrap midnight
    (end < start) — _in_halt_window() handles that case.
    """
    out: list[tuple[_time, _time]] = []

    # Unsuffixed legacy pair — included only when fully defined.
    s0 = os.getenv("HALT_START_TIME")
    e0 = os.getenv("HALT_END_TIME")
    if s0 and e0:
        try:
            out.append((_parse_hhmm(s0), _parse_hhmm(e0)))
        except Exception as ex:
            print(f"[HALT] Ignoring bad HALT_START_TIME/HALT_END_TIME: {ex}")

    # Numbered pairs 1..9.
    for n in range(1, 10):
        s = os.getenv(f"HALT_START_TIME{n}")
        e = os.getenv(f"HALT_END_TIME{n}")
        if not s and not e:
            continue
        if not (s and e):
            print(f"[HALT] HALT_START_TIME{n} / HALT_END_TIME{n} must be set "
                  f"as a pair — skipping.")
            continue
        try:
            out.append((_parse_hhmm(s), _parse_hhmm(e)))
        except Exception as ex:
            print(f"[HALT] Ignoring bad HALT_*_TIME{n}: {ex}")

    if not out:
        out.append((_time(6, 15), _time(7, 45)))
    return out


HALT_WINDOWS: list[tuple[_time, _time]] = _collect_halt_windows()


def _in_halt_window(now_t: _time) -> tuple[_time, _time] | None:
    """
    If ``now_t`` is inside any configured halt window, return that window
    as (start, end); otherwise return None.  Midnight-wrapping windows
    (end < start) match on either side of midnight.
    """
    for s, e in HALT_WINDOWS:
        if s <= e:
            if s <= now_t <= e:
                return (s, e)
        else:
            # Window crosses midnight, e.g. 22:15 → 02:45.
            if now_t >= s or now_t <= e:
                return (s, e)
    return None

SignalT    = Literal["buy", "sell", "strong_sell", "hold"]
DirectionT = Literal["yes", "no"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

_CST = ZoneInfo("America/Chicago")

def _cst_now() -> datetime:
    """Current time in Central (CST/CDT) — used for all log timestamps."""
    return datetime.now(_CST)


def _ts_ms() -> str:
    return str(int(_utc_now().timestamp() * 1000))


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  STEP 1 — ASYNC KALSHI CLIENT  (aiohttp + RSA-PSS signing)              ║
# ╚════════════════════════════════════════════════════════════════════════════╝
class KalshiClient:
    """
    Persistent-session async HTTP client with RSA-PSS request signing.
    Connection pooling via a single TCPConnector keeps latency low for
    the 500 ms polling loops.
    """

    def __init__(self) -> None:
        raw = Path(PRIVATE_KEY_PATH).read_bytes()
        self._pk = load_pem_private_key(raw, password=None)
        self._session: Optional[aiohttp.ClientSession] = None
        self._mu = asyncio.Lock()

    # ── signing ───────────────────────────────────────────────────────────────
    def _sign(self, ts: str, method: str, path: str) -> str:
        sig = self._pk.sign(
            f"{ts}{method}{path}".encode(),
            _padding.PSS(
                mgf=_padding.MGF1(hashes.SHA256()),
                salt_length=_padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(sig).decode()

    def _auth_headers(self, method: str, path: str) -> dict[str, str]:
        ts = _ts_ms()
        return {
            "Content-Type":            "application/json",
            "KALSHI-ACCESS-KEY":       API_KEY_ID,
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "KALSHI-ACCESS-SIGNATURE": self._sign(ts, method.upper(), f"/trade-api/v2{path}"),
            "Cache-Control":           "no-cache",
            "Pragma":                  "no-cache",
        }

    # ── session lifecycle ─────────────────────────────────────────────────────
    async def _sess(self) -> aiohttp.ClientSession:
        async with self._mu:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(
                        limit=30,
                        ttl_dns_cache=300,
                        enable_cleanup_closed=True,
                    ),
                    timeout=aiohttp.ClientTimeout(total=12, connect=4),
                )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ── core request with auto-retry ──────────────────────────────────────────
    async def req(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        body: dict | None = None,
        retries: int = 3,
    ) -> dict:
        url  = f"{BASE_URI}{path}"
        sess = await self._sess()
        last: Exception | None = None

        for attempt in range(1, retries + 1):
            hdrs = self._auth_headers(method, path)
            try:
                async with sess.request(
                    method.upper(), url, headers=hdrs, params=params, json=body,
                ) as r:
                    txt = await r.text()
                    if r.status >= 400:
                        raise RuntimeError(f"HTTP {r.status}: {txt}")
                    return json.loads(txt)
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as e:
                last = e
                if attempt < retries:
                    await asyncio.sleep(0.4 * attempt)

        raise RuntimeError(f"Failed after {retries} tries: {last}") from last


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  CSV TRADE LOG  (step 8)                                                 ║
# ╚════════════════════════════════════════════════════════════════════════════╝
_CSV_COLS = [
    "platform",
    "timestamp", "ticker", "BTC_TO_BEAT", "BTC_SPOT_PRICE_AT_BUY", "BTC_SPOT_PRICE_AT_SELL",
    "mode", "direction", "actual_direction_previous", "contracts",
    "entry_price", "exit_price", "pnl", "result", "portfolio_value", "returns",
    "MAX_LOSS_PCT", "MAX_PROFIT_PCT", "ENTRY_SIGNAL",
    # paper-vs-live, recorded per row. Without it the ledger could not tell
    # real money from a dry run: the 'mode' column above is the ENTRY STYLE
    # (BUY/FLIP-BUY), and both modes write to the same CSV.
    "dry_run",
]


def init_csv() -> None:
    p = Path(CSV_FILE)
    if not p.exists():
        with p.open("w", newline="") as f:
            csv.writer(f).writerow(_CSV_COLS)


class Bankroll:
    """This bot's own capital ledger — the btc60 / sports-bank contract.

    Seeded from BTC_BANKROLL, moved ONLY by this bot's realized P&L, and
    persisted next to the trade CSV so a restart resumes the same ledger.
    The shared Kalshi account balance is never the score.
    """

    def __init__(self) -> None:
        self.enabled = BTC15_BANKROLL > 0
        self.start = BTC15_BANKROLL
        self.balance = BTC15_BANKROLL
        self._halted = False
        self._load()

    @property
    def _path(self) -> Path:
        return Path(CSV_FILE).parent / "btc15_bankroll.json"

    def _load(self) -> None:
        if not self.enabled:
            return
        # Fresh session on EVERY start (user 08/03): the ledger — and the
        # target/SL measured on it — always begins at the typed seed. The
        # previous session's closing balance is logged for the record and
        # then replaced; the state file's job is now only the in-session
        # persistence that settle() and the TRUEPNL corrections need.
        try:
            if self._path.is_file():
                d = json.loads(self._path.read_text())
                prev = float(d.get("balance", 0) or 0)
                if prev and abs(prev - self.start) > 0.005:
                    print(f"  [BANK] previous session ended at ${prev:.2f} — "
                          f"fresh session resets to ${self.start:.2f}")
        except Exception as e:                       # never block a start
            print(f"  [BANK] state read failed ({e}) — seeding ${self.start:.2f}")
        self.balance = self.start
        self._save()
        print(f"  [BANK] bankroll ${self.balance:.2f} "
              f"(seed ${self.start:.2f}"
              + (f", target +{BTC15_TARGET_PCT:.0f}%" if BTC15_TARGET_PCT > 0 else "")
              + ")")

    def _save(self) -> None:
        if not self.enabled:
            return
        try:
            self._path.write_text(json.dumps(
                {"start": self.start, "balance": round(self.balance, 2)}, indent=2))
        except Exception as e:
            print(f"  [BANK] state save failed: {e}")

    def settle(self, pnl: float) -> None:
        """Apply one trade's realized P&L."""
        if not self.enabled or pnl is None:
            return
        self.balance += float(pnl)
        self._save()
        print(f"  [BANK] {float(pnl):+.2f} → bankroll ${self.balance:.2f}")

    def sl_reached(self) -> bool:
        """True once realized P&L has SHRUNK this bot's bankroll by
        BTC15_BANK_SL_PCT. No bankroll or no SL = never halts."""
        if not self.enabled or BTC15_BANK_SL_PCT <= 0 or self.start <= 0:
            return False
        floor = self.start * (1 - BTC15_BANK_SL_PCT / 100.0)
        if self.balance > floor:
            return False
        print(f"  [BANK-SL] bankroll ${self.balance:.2f} <= ${floor:.2f} "
              f"(-{BTC15_BANK_SL_PCT:.0f}% on ${self.start:.2f}) — SL HIT on Bank")
        return True

    def target_reached(self) -> bool:
        """True once realized P&L has grown THIS bot's bankroll by
        BTC15_TARGET_PCT. No bankroll or no target = never halts."""
        if not self.enabled or BTC15_TARGET_PCT <= 0 or self.start <= 0:
            return False
        goal = self.start * (1 + BTC15_TARGET_PCT / 100.0)
        if self.balance < goal:
            return False
        if not self._halted:
            self._halted = True
            print(f"  [BANK-TARGET] bankroll ${self.balance:.2f} >= ${goal:.2f} "
                  f"(+{BTC15_TARGET_PCT:.0f}% on ${self.start:.2f}) — no new orders")
        return True


BANKROLL = Bankroll()


def log_trade(
    ticker: str, mode: str, direction: str, contracts: int,
    entry: float, exit_: float, pnl: float, result: str, pv: float,
    btc_to_beat: float | None = None,
    btc_spot_at_buy: float | None = None,
    btc_spot_at_sell: float | None = None,
    max_loss_pct: float | None = None,
    max_profit_pct: float | None = None,
    actual_direction_previous: str | None = None,
    signal_source: str | None = None,
) -> None:
    """
    Append one row to the trade history CSV.

    MAX_LOSS_PCT:    populated on TAKE_PROFIT exits — worst unrealised
                     drawdown seen before the trade ultimately won.
                     Use to tune KALSHI_STOP_PCT: if winners never went
                     below 10 %, your stop at 75 % is too loose.

    MAX_PROFIT_PCT:  populated on STOP_LOSS / SELL_SIGNAL exits — best
                     unrealised gain seen before the trade reversed.
                     Use to tune KALSHI_PROFIT_PCT: if losers spent time
                     above 15 % gain before reversing, your TP is too far.
    """
    def _fmt(v: float | None) -> str:
        return f"{round(v, 2)}" if v is not None else ""

    # ── Compute returns vs previous row's portfolio_value ─────────────────────
    returns_str = ""
    try:
        p = Path(CSV_FILE)
        if p.exists():
            with p.open("r", newline="") as rf:
                rows = list(csv.DictReader(rf))
            if rows:
                prev_pv_raw = rows[-1].get("portfolio_value", "")
                if prev_pv_raw:
                    prev_pv = float(prev_pv_raw)
                    if prev_pv > 0:
                        ret_pct = (pv - prev_pv) / prev_pv * 100
                        returns_str = f"{ret_pct:+.2f}%"
    except Exception:
        pass

    ts = _cst_now().strftime("%Y-%m-%d %H:%M")
    with open(CSV_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            PLATFORM_NAME,
            ts, ticker,
            _fmt(btc_to_beat), _fmt(btc_spot_at_buy), _fmt(btc_spot_at_sell),
            mode, direction, actual_direction_previous or "", contracts,
            round(entry, 4), round(exit_, 4), round(pnl, 4), result, round(pv, 2),
            returns_str,
            _fmt(max_loss_pct), _fmt(max_profit_pct), signal_source or "",
            "TRUE" if DRY_RUN else "FALSE",
        ])
    # Single funnel for realized P&L, so this bot's own bankroll ledger moves
    # exactly once per recorded trade.
    BANKROLL.settle(pnl)


def compute_prediction_win_rate() -> dict:
    """
    Read trade_history.csv and compute prediction win/loss rates.

    For each consecutive pair of rows (i, i+1):
      - row[i]["direction"]                   → what the bot predicted
      - row[i+1]["actual_direction_previous"]  → what actually happened next

    WIN  — BOTH conditions hold:
      1. direction[i] == actual_direction_previous[i+1]  (prediction correct)
      2. portfolio_value[i] < portfolio_value[i+1]       (portfolio grew)

    LOSS — BOTH conditions hold (mirror of win):
      1. direction[i] != actual_direction_previous[i+1]  (prediction wrong)
      2. portfolio_value[i] >= portfolio_value[i+1]      (portfolio dropped)

    All other pairs (right direction but PV dropped, wrong direction but PV
    grew) are counted in the total but classified as neither win nor loss.

    Rows with missing/unparseable values in any required field are skipped.
    Returns {
        "success": int, "loss": int, "failure": int,
        "total": int, "rate": float, "loss_rate": float
    }.
    """
    p = Path(CSV_FILE)
    if not p.exists():
        return {"success": 0, "loss": 0, "failure": 0, "total": 0,
                "rate": 0.0, "loss_rate": 0.0}

    try:
        with p.open("r", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return {"success": 0, "loss": 0, "failure": 0, "total": 0,
                "rate": 0.0, "loss_rate": 0.0}

    # When the CSV has a "platform" column (unified bot.py mode), restrict
    # win-rate computation to this platform's own rows.  Legacy rows from
    # before the column existed have no "platform" field and are skipped
    # (DictReader returns None for missing keys).
    if rows and "platform" in rows[0]:
        rows = [r for r in rows
                if (r.get("platform") or "").strip().lower() == PLATFORM_NAME]

    success = loss = failure = 0
    pv_grew_count = 0    # overall: portfolio grew regardless of direction
    pv_total      = 0    # total pairs where both portfolio_values are parseable

    for i in range(len(rows) - 1):
        predicted  = (rows[i].get("direction") or "").strip().lower()
        actual     = (rows[i + 1].get("actual_direction_previous") or "").strip().lower()

        # Parse portfolio values (required for all metrics)
        try:
            pv_curr = float(rows[i].get("portfolio_value") or "")
            pv_next = float(rows[i + 1].get("portfolio_value") or "")
        except (ValueError, TypeError):
            continue   # skip rows where portfolio_value is missing or non-numeric

        portfolio_grew    = (pv_curr < pv_next)
        portfolio_dropped = (pv_curr >= pv_next)

        # Overall portfolio growth — irrespective of direction
        pv_total += 1
        if portfolio_grew:
            pv_grew_count += 1

        # Direction-based metrics require both direction fields
        if not predicted or not actual:
            continue

        direction_match = (predicted == actual)

        if direction_match and portfolio_grew:
            success += 1
        elif not direction_match and portfolio_dropped:
            loss += 1
        else:
            failure += 1   # mixed: right dir but PV dropped, or wrong dir but PV grew

    total            = success + loss + failure
    rate             = (success       / total    * 100) if total    > 0 else 0.0
    loss_rate        = (loss          / total    * 100) if total    > 0 else 0.0
    overall_win_rate = (pv_grew_count / pv_total * 100) if pv_total > 0 else 0.0

    # PV_RETURNS: (last portfolio_value - first portfolio_value) / first * 100
    pv_returns_str = ""
    try:
        pv_vals = [float(r["portfolio_value"]) for r in rows
                   if r.get("portfolio_value", "").strip()]
        if len(pv_vals) >= 2 and pv_vals[0] > 0:
            pv_ret = (pv_vals[-1] - pv_vals[0]) / pv_vals[0] * 100
            pv_returns_str = f"{pv_ret:+.2f}%"
    except Exception:
        pass

    return {"success": success, "loss": loss, "failure": failure,
            "total": total, "rate": rate, "loss_rate": loss_rate,
            "overall_win_rate": overall_win_rate,
            "pv_grew": pv_grew_count, "pv_total": pv_total,
            "pv_returns": pv_returns_str}


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  PORTFOLIO HELPERS                                                       ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def portfolio_balance(c: KalshiClient) -> float:
    d = await c.req("GET", "/portfolio/balance")
    return d.get("balance", 0) / 100.0


def _day_start_state_path() -> Path:
    """
    Path to today's day-start portfolio cache file.  Keyed by CST date and
    placed alongside the trade-history CSV so it survives bot restarts during
    the trading day but rolls over automatically at midnight CST.
    """
    date_str = _cst_now().strftime("%Y%m%d")
    csv_dir  = Path(CSV_FILE).resolve().parent
    return csv_dir / f"{PLATFORM_NAME}_day_start_{date_str}.txt"


def get_day_start_portfolio(current_pv: float) -> float:
    """
    Return today's day-start portfolio baseline.

    The first call of the day persists ``current_pv`` as the baseline; all
    subsequent calls (including after a bot restart) read it back from disk.
    Used to evaluate the ``TARGET_PORTFOLIO_PCT`` daily profit cap.
    """
    p = _day_start_state_path()
    if p.exists():
        try:
            return float(p.read_text().strip())
        except Exception as e:
            print(f"  [TARGET-PV] Could not read {p.name}: {e} — re-seeding.")
    try:
        p.write_text(f"{current_pv:.4f}")
        print(f"  [TARGET-PV] Seeded day-start baseline ${current_pv:.2f} → {p.name}")
    except Exception as e:
        print(f"  [TARGET-PV] Could not persist day-start baseline: {e}")
    return current_pv


async def _halt_and_shutdown(
    c: "KalshiClient",
    ticker: str | None,
    reason_tag: str,
    reason_msg: str,
) -> None:
    """
    Shared shutdown path for "stop trading for the day" halts:
      - MAX_LOSS_RATE (PV Returns < profit-ratcheted floor)
      - DO_NOT_BUY_IF_PORTFOLIO_BELOW (balance too low)
      - TARGET_PORTFOLIO_PCT (daily profit target reached)
      - TRADING-HOURS halt window

    Cancels any resting orders, fire-sells any open position on ``ticker``
    (direction inferred from ``position_fp`` sign so callers don't need to
    track an in-scope ``direction`` variable — that local may not be
    defined yet on the first trade slot, which previously risked an
    UnboundLocalError on the MAX_LOSS_RATE path).  Finally, when
    ``HALT_MACHINE_SHUTDOWN=TRUE``, schedules a Windows machine shutdown
    in 30 s.  The caller must ``return`` from the run loop after invoking
    this helper.
    """
    print(f"  [{reason_tag}] {reason_msg}")
    try:
        await cancel_all(c)
    except Exception as e:
        print(f"  [{reason_tag}] cancel_all failed: {e}")
    if ticker:
        try:
            _pos = await position_for(c, ticker)
            if _pos and _pos["contracts"] > 0:
                # Derive YES/NO from the signed position_fp so we don't
                # depend on the caller's local `direction` variable.
                _fp  = float(_pos.get("position_fp", "0"))
                _dir: DirectionT = "yes" if _fp >= 0 else "no"
                print(f"  [{reason_tag}] Open position: {_pos['contracts']} "
                      f"{_dir.upper()} contracts on {ticker} — fire-selling …")
                await _fire_sale(c, ticker, _dir, _pos["contracts"])
                await asyncio.sleep(2)
        except Exception as e:
            print(f"  [{reason_tag}] position close failed: {e}")
    if HALT_MACHINE_SHUTDOWN:
        print(f"  [{reason_tag}] Initiating machine shutdown in 30 seconds …")
        os.system("shutdown /s /f /t 30" if os.name == "nt"
                  else "shutdown -h +1")
    print(f"  [{reason_tag}] Bot halting now.")


async def position_for(c: KalshiClient, ticker: str) -> dict | None:
    d = await c.req("GET", "/portfolio/positions", params={
        "ticker": ticker, "_": _ts_ms(),
    })
    for p in d.get("market_positions", []):
        if p.get("ticker") == ticker:
            p["contracts"] = abs(int(float(p.get("position_fp", "0"))))
            p["exposure"]  = float(p.get("market_exposure_dollars", "0"))
            return p
    return None


async def resting_orders(c: KalshiClient, ticker: str | None = None) -> list[dict]:
    d = await c.req("GET", "/portfolio/orders", params={"status": "resting"})
    orders = d.get("orders", [])
    if ticker:
        return [o for o in orders if o.get("ticker") == ticker]
    return orders


async def cancel_all(c: KalshiClient) -> int:
    """Cancel every resting order in parallel.  Returns count cancelled."""
    orders = await resting_orders(c)
    if not orders:
        return 0
    print(f"  [CANCEL] Cancelling {len(orders)} resting order(s) …")
    results = await asyncio.gather(
        *(c.req("DELETE", f"/portfolio/events/orders/{o['order_id']}") for o in orders),
        return_exceptions=True,
    )
    failed = sum(1 for r in results if isinstance(r, Exception))
    if failed:
        print(f"  [CANCEL] {failed}/{len(orders)} cancel(s) failed")
    return len(orders) - failed


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  STEP 2 — ACTIVE BTC-15 MARKET DETECTION                                ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def _find_fresh_market(c: KalshiClient) -> dict | None:
    d   = await c.req("GET", "/markets", params={
        "series_ticker": SERIES, "status": "open", "limit": 5,
    })
    now = _utc_now()
    for m in d.get("markets", []):
        ot = m.get("open_time", "")
        if not ot:
            continue
        opened = datetime.fromisoformat(ot.replace("Z", "+00:00"))
        if (now - opened).total_seconds() <= TIME_SEC_TO_ORDER:
            return m
    return None


async def wait_for_market(c: KalshiClient, skip: str | None = None) -> dict:
    print("[MARKET] Scanning for next BTC-15 market …")
    stale: set[str] = set()
    while True:
        try:
            m = await _find_fresh_market(c)
            if m and m["ticker"] != skip and m["ticker"] not in stale:
                ot     = m.get("open_time", "")
                opened = datetime.fromisoformat(ot.replace("Z", "+00:00"))
                age    = (_utc_now() - opened).total_seconds()
                if age > TIME_SEC_TO_ORDER:
                    stale.add(m["ticker"])
                    print(f"[MARKET] Stale {m['ticker']} ({age:.0f}s) — skipping")
                    await asyncio.sleep(5)
                    continue
                print(f"[MARKET] ✓ Found {m['ticker']}  (age {age:.0f}s)")
                return m
        except Exception as e:
            print(f"[MARKET] poll error: {e}")
        await asyncio.sleep(2)


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  STEP 3 — DIRECTION FROM PREVIOUS 6 OUTCOMES  (deque)                   ║
# ║  Max-occurrence of 6; on tie → max-occurrence of recent 3.               ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def _fetch_settled(c: KalshiClient, n: int = 10) -> list[str]:
    d = await c.req("GET", "/markets", params={
        "series_ticker": SERIES, "status": "settled", "limit": n,
    })
    return [m["result"] for m in d.get("markets", []) if m.get("result") in ("yes", "no")]


def _majority(seq: list[str]) -> str | None:
    ct = Counter(seq).most_common()
    if not ct:
        return None
    if len(ct) == 1 or ct[0][1] > ct[1][1]:
        return ct[0][0]
    return None


def resolve_direction(outcomes: list[str]) -> DirectionT:
    """
    deque(maxlen=6) of settled outcomes.
    Returns max-occurrence; tie → use most recent 3 to break.
    """
    buf: deque[str] = deque(outcomes[:6], maxlen=6)
    if not buf:
        return "yes"

    winner = _majority(list(buf))
    if winner:
        return winner   # type: ignore[return-value]

    # Tie → recent 3
    recent = list(buf)[:3]
    w3 = _majority(recent)
    if w3:
        return w3       # type: ignore[return-value]

    # Ultimate fallback
    return Counter(buf).most_common(1)[0][0]   # type: ignore[return-value]


async def determine_direction(c: KalshiClient) -> tuple[DirectionT, str | None]:
    outcomes  = await _fetch_settled(c, 10)
    direction = resolve_direction(outcomes)
    actual_prev = outcomes[0] if outcomes else None
    print(f"  [DIR] Settled (recent→old): {outcomes[:6]}")
    print(f"  [DIR] Direction → {direction.upper()}  |  Last settled → {(actual_prev or '?').upper()}")
    return direction, actual_prev


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  STEP 4 — ASYNC PRICE POLLER + BUY / SELL / HOLD SIGNAL                 ║
# ║                                                                          ║
# ║  Polls every 500 ms into deque(maxlen=20).                               ║
# ║  Signal logic:                                                           ║
# ║    • EMA(3) vs EMA(10) crossover  —  primary trend detector              ║
# ║    • OLS slope over full window   —  confirmation                        ║
# ║    • Progressive-decline guard    —  "sell" ONLY when the tail end       ║
# ║      is monotonically non-increasing AND drop > 1.5 %                    ║
# ║                                                                          ║
# ║  The concurrent create_task + sleep pattern guarantees the poll           ║
# ║  interval never drifts by the HTTP round-trip time.                      ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def _bid_price(c: KalshiClient, ticker: str, side: str) -> float | None:
    """
    Extract the latest bid for `side` from the /markets/{ticker} response.

    Tries multiple field names in priority order because the Kalshi API
    sometimes omits `{side}_bid_dollars` while other price fields are present.
    This is the root cause of the n=13 frozen-deque problem: the field goes
    null after ~15 ticks, so the deque stops growing and compute_signal
    sees stale data forever.

    Fallback chain:
      1. {side}_bid_dollars         (dollars, preferred)
      2. {side}_bid / 100           (cents → dollars)
      3. {side}_ask_dollars - 0.01  (ask minus 1¢ spread)
      4. {side}_ask / 100 - 0.01   (ask in cents, minus 1¢)
      5. last_price_dollars         (last trade, any side)
      6. last_price / 100           (last trade in cents)
    """
    try:
        d   = await c.req("GET", f"/markets/{ticker}", params={"_": _ts_ms()})
        mkt = d.get("market", {})

        # 1. Primary: {side}_bid_dollars
        raw = mkt.get(f"{side}_bid_dollars")
        if raw is not None and float(raw) >= 0:
            return round(float(raw), 4)

        # 2. Cents variant: {side}_bid  (integer 0–99)
        raw = mkt.get(f"{side}_bid")
        if raw is not None and float(raw) >= 0:
            return round(float(raw) / 100.0, 4)

        # 3. Ask-side fallback: {side}_ask_dollars minus 1¢ spread
        raw = mkt.get(f"{side}_ask_dollars")
        if raw is not None and float(raw) > 0.01:
            return round(float(raw) - 0.01, 4)

        # 4. Ask cents variant
        raw = mkt.get(f"{side}_ask")
        if raw is not None and float(raw) > 1:
            return round((float(raw) - 1) / 100.0, 4)

        # 5. Last traded price (any side)
        raw = mkt.get("last_price_dollars")
        if raw is not None and float(raw) >= 0:
            return round(float(raw), 4)

        # 6. Last price in cents
        raw = mkt.get("last_price")
        if raw is not None and float(raw) >= 0:
            return round(float(raw) / 100.0, 4)

        return None

    except Exception:
        return None


def _ema(arr: np.ndarray, span: int) -> float:
    k = 2.0 / (span + 1)
    v = float(arr[0])
    for x in arr[1:]:
        v = float(x) * k + v * (1 - k)
    return v


def compute_signal(buf: deque[float]) -> SignalT:
    """
    Volatility-aware signal engine tuned for Kalshi BTC-15 binary contracts.

    ═══════════════════════════════════════════════════════════════════════
    EVALUATION ORDER  (first match wins):

      0. STRONG_SELL — CRASH FLOOR (gate 1 of 7)
         Latest bid < 0.25  AND  recent high (last 8) ≥ 0.38
         → Price collapsed.  Bypass all other gates.

      1. BUY  (3 quality gates)
         B1. EMA(3) > EMA(10)
         B2. slope > 0
         B3. upticks > downticks in last 9 ticks

      2. SELL  (3 quality gates — mirror of BUY)
         X1. EMA(3) < EMA(10)
         X2. slope < 0
         X3. downticks > upticks in last 9 ticks

      3. STRONG_SELL  (6 confirmed-decline gates — S1..S6 of 7)
         S1. EMA gap > 0.5 × σ
         S2. |slope| > 1.0 × σ  and slope < 0
         S3. 7 of last 8 ticks non-increasing
         S4. Peak-to-current drop > max(12 %, 2.5 × σ / peak)
         S5. Second-half slope < first-half slope (accelerating)
         S6. Latest < EMA(10)

      4. HOLD — default
    ═══════════════════════════════════════════════════════════════════════
    """
    data = np.array(buf, dtype=np.float64)
    n    = len(data)

    if n < 16:
        return "hold"

    latest   = float(data[-1])
    win_high = float(data.max())
    win_low  = float(data.min())

    # ══════════════════════════════════════════════════════════════════════════
    # CRASH FLOOR — first of the 7 strong-sell gates (standalone path)
    # ══════════════════════════════════════════════════════════════════════════
    recent_8_high = float(data[-8:].max())
    if (latest < 0.26 and recent_8_high >= 0.38) or (latest < 0.36 and recent_8_high >= 0.50) or (latest < 0.32 and recent_8_high >= 0.45):
        return "strong_sell"

    # ── Core indicators ───────────────────────────────────────────────────────
    ema_fast = _ema(data, 3)
    ema_slow = _ema(data, min(10, n))
    slope    = float(np.polyfit(np.arange(n), data, 1)[0])

    sigma = float(np.std(data))
    if sigma < 1e-6:
        sigma = 0.005

    # Pre-compute tick directions for last 9 (shared by BUY B3 and SELL X3)
    tail9     = data[-min(9, n):]
    upticks   = sum(1 for i in range(len(tail9) - 1) if tail9[i + 1] > tail9[i])
    downticks = sum(1 for i in range(len(tail9) - 1) if tail9[i + 1] < tail9[i])

    # ══════════════════════════════════════════════════════════════════════════
    # BUY — 3 quality gates
    # ══════════════════════════════════════════════════════════════════════════
    buy_ok = True
    if ema_fast <= ema_slow:                        # B1
        buy_ok = False
    if buy_ok and slope <= 0:                       # B2
        buy_ok = False
    if buy_ok and upticks <= downticks:             # B3
        buy_ok = False
    if buy_ok:
        return "buy"

    # ══════════════════════════════════════════════════════════════════════════
    # SELL — 3 quality gates  (mirror of BUY, lightweight)
    # ══════════════════════════════════════════════════════════════════════════
    sell_ok = True
    if ema_fast >= ema_slow:                        # X1: short EMA below long EMA
        sell_ok = False
    if sell_ok and slope >= 0:                      # X2: overall slope negative
        sell_ok = False
    if sell_ok and downticks <= upticks:            # X3: net downward pressure
        sell_ok = False

    # ══════════════════════════════════════════════════════════════════════════
    # STRONG SELL — 6 gates (S1..S6), forming gates 2..7 of the 7-gate set
    # ══════════════════════════════════════════════════════════════════════════
    # Evaluate strong_sell only if at least the 3-gate sell passed.
    strong_ok = sell_ok

    # S1: EMA gap > 0.5 × σ
    ema_gap = ema_slow - ema_fast
    if strong_ok and ema_gap < 0.5 * sigma:
        strong_ok = False

    # S2: |slope| > 1.0 × σ
    if strong_ok and abs(slope) < 1.0 * sigma:
        strong_ok = False

    # S3: 7 of last 8 ticks non-increasing
    if strong_ok:
        tail8 = data[-8:]
        drops = sum(1 for i in range(len(tail8) - 1) if tail8[i] >= tail8[i + 1])
        if drops < len(tail8) - 2:
            strong_ok = False

    # S4: Peak-to-current drop > max(12 %, 2.5 × σ / peak)
    if strong_ok:
        pct_drop   = (win_high - latest) / (win_high + 1e-9)
        vol_thresh = max(0.12, 2.5 * sigma / (win_high + 1e-9))
        if pct_drop < vol_thresh:
            strong_ok = False

    # S5: Decline accelerating (second-half slope < first-half slope)
    if strong_ok:
        mid         = n // 2
        first_half  = data[:mid]
        second_half = data[mid:]
        slope_1h    = float(np.polyfit(np.arange(len(first_half)),  first_half,  1)[0])
        slope_2h    = float(np.polyfit(np.arange(len(second_half)), second_half, 1)[0])
        if slope_2h >= slope_1h:
            strong_ok = False

    # S6: Latest below slow EMA
    if strong_ok and latest >= ema_slow:
        strong_ok = False

    if strong_ok:
        return "strong_sell"

    if sell_ok:
        return "sell"

    return "hold"


async def poll_for_signal(
    c: KalshiClient,
    ticker: str,
    direction: DirectionT,
    *,
    btc: Optional["BtcVidyaMonitor"] = None,
    isItFlip: bool     = False,
    interval_s: float = 1,
    window: int        = 20,
    max_ticks: int     = 400,
) -> SignalT:
    """
    Sentiment-based scanner (initial scan, step 5a) — gated by BTC bias.

    Collects the LAST `SENTIMENT_SIZE` buy/sell signals from compute_signal
    (hold ticks are ignored).  Once the rolling buffer is full, evaluates
    BOTH the Kalshi sentiment ratio AND the BTC VIDYA signal (past 9 ticks):

        SELL  →  sell_ratio > SELL_PCT_THRESHOLD  AND  btc == "sell"
        BUY   →  btc == "buy"   (regardless of sentiment)
        otherwise keep accumulating

    Stricter symmetry than before: SELL requires both Kalshi sentiment
    AND BTC to agree.  BUY requires BTC bullish — a "hold" or "sell"
    on BTC blocks entry even if Kalshi sentiment looks bullish.
    """
    if isItFlip:
        SENTIMENT_SIZE      = 40
        SELL_PCT_THRESHOLD  = 0.55
        
    else: 
        SENTIMENT_SIZE      = 50        # recent directional events to sample
        SELL_PCT_THRESHOLD  = 0.54      # > 62 % sells → bearish

    buf: deque[float] = deque(maxlen=window)
    sentiment: deque[str] = deque(maxlen=SENTIMENT_SIZE)
    price_buf: deque[float] = deque(maxlen=SENTIMENT_SIZE)
    none_streak = 0
    btc_sig    = btc.latestBtcVidyaSignal() if btc else "hold"
  
    for tick in range(1, max_ticks + 1):
        fetch = asyncio.create_task(_bid_price(c, ticker, direction))
        timer = asyncio.create_task(asyncio.sleep(interval_s))

        price = await fetch
        await timer

        if price is None:
            none_streak += 1
            if none_streak in (5, 15, 30) or none_streak % 50 == 0:
                print(f"    [POLL {tick:03d}] ⚠ {none_streak} consecutive None "
                      f"returns — n stuck at {len(buf)}")
            continue

        none_streak = 0
        buf.append(price)
        price_buf.append(price)
        sig = compute_signal(buf)
        ts  = _cst_now().strftime("%H:%M:%S.%f")[:-3]

        # ── STRONG_SELL short-circuit: 7-gate confirmed crash, exit now ───────
        if sig == "strong_sell":
            print(f"    [POLL {tick:03d}] {ts}  {direction} bid={price:.4f}  "
                  f"n={len(buf)}  → STRONG_SELL — return SELL immediately")
            return "sell"

        # Track directional events; ignore "hold"
        if sig == "sell":
            sentiment.append("sell")
        elif sig == "buy":
            sentiment.append("buy")

        sells = sum(1 for s in sentiment if s == "sell")
        buys  = len(sentiment) - sells

        # Periodic progress log
        if tick % 5 == 0 or sig != "hold":
            pct = (sells / len(sentiment) * 100) if sentiment else 0.0
            print(f"    [POLL {tick:03d}] {ts}  {direction} bid={price:.4f}  "
                  f"n={len(buf)}  sig={sig.upper()}  "
                  f"S/B={sells}/{buys} ({pct:.0f}%) "
                  f"[{len(sentiment)}/{SENTIMENT_SIZE}]")
        btc_sig    = btc.latestBtcVidyaSignal() if btc else "hold"

        # ── Early-exit when SELL threshold is mathematically unreachable ──────
        # If even turning every remaining sentiment slot into a "sell" cannot
        # push sell_ratio to SELL_PCT_THRESHOLD, then SELL can never fire on
        # this scan.  Skip the wasted polling and return BUY so STEP 5a routes
        # to STEP 5d (entry band guard).  Floor at 30 events so we don't act
        # on a sparse early-tick sample.
        EARLY_EXIT_MIN_EVENTS = 30
        if EARLY_EXIT_MIN_EVENTS <= len(sentiment) < SENTIMENT_SIZE:
            _max_sells = sells + (SENTIMENT_SIZE - len(sentiment))
            _max_ratio = _max_sells / SENTIMENT_SIZE
            if _max_ratio < SELL_PCT_THRESHOLD:
                print(f"    [POLL {tick:03d}] ⚡ EARLY-EXIT — even with all "
                      f"remaining {SENTIMENT_SIZE - len(sentiment)} slots as "
                      f"sells, max sell_ratio={_max_ratio:.0%} < threshold "
                      f"{SELL_PCT_THRESHOLD:.0%}  "
                      f"(S/B={sells}/{buys} [{len(sentiment)}/{SENTIMENT_SIZE}]). "
                      f"SELL impossible — return BUY.")
                return "buy"

            # ── Symmetric: SELL threshold already mathematically guaranteed ───
            # If sells already exceed SELL_PCT_THRESHOLD when divided by the
            # FULL SENTIMENT_SIZE (not the current fill), then no amount of
            # future buys can pull the final ratio back below threshold.
            # Skip the rest of the scan and return SELL so STEP 5a runs its
            # sell-retry / flip-confirm path.
            _min_ratio_at_full = sells / SENTIMENT_SIZE
            if _min_ratio_at_full > SELL_PCT_THRESHOLD:
                print(f"    [POLL {tick:03d}] ⚡ EARLY-EXIT — sells already "
                      f"locked in: {sells}/{SENTIMENT_SIZE} = "
                      f"{_min_ratio_at_full:.0%} > threshold "
                      f"{SELL_PCT_THRESHOLD:.0%}  "
                      f"(S/B={sells}/{buys} [{len(sentiment)}/{SENTIMENT_SIZE}]). "
                      f"SELL guaranteed — return SELL.")
                return "sell"

        # Decide once we have SENTIMENT_SIZE directional events
        if len(sentiment) >= SENTIMENT_SIZE:
            sell_ratio = sells / len(sentiment)
            buy_ratio = buys / len(sentiment)
            btc_sig    = btc.latestBtcVidyaSignal() if btc else "hold"

            # ── is_drop_real: oldest-10 max vs newest-10 min in price_buf ─────
            if len(price_buf) >= 20:
                _pb      = list(price_buf)
                _max_old = max(_pb[:15])
                _min_new = min(_pb[-15:])
                is_drop_real = (_max_old - _min_new) >= 0.10
            else:
                is_drop_real = False

            # ── CONFIRM (buy on current direction) — BTC + Kalshi + no real drop
            # Requires: BTC agrees, sell ratio below threshold, AND price has
            # not genuinely dropped (is_drop_real gate).  All three must pass.
            if (direction == "yes" and btc_sig == "buy"
                    and sell_ratio <= SELL_PCT_THRESHOLD
                    and not is_drop_real):
                print(f"    [POLL {tick:03d}] 📈 BTC favours YES — return BUY  "
                      f"(BTC={btc_sig.upper()}  sell={sell_ratio:.0%} <= {SELL_PCT_THRESHOLD:.0%}  drop={is_drop_real})")
                return "buy"
            if (direction == "no" and btc_sig == "sell"
                    and sell_ratio <= SELL_PCT_THRESHOLD
                    and not is_drop_real):
                print(f"    [POLL {tick:03d}] 📈 BTC favours NO  — return BUY  "
                      f"(BTC={btc_sig.upper()}  sell={sell_ratio:.0%} <= {SELL_PCT_THRESHOLD:.0%}  drop={is_drop_real})")
                return "buy"

            # ── FLIP (buy opposite direction) — BTC against + Kalshi bearish ──
            # Stricter: needs BOTH BTC contradicting our side AND Kalshi
            # sentiment bearish on the current side's bids.
            if ((direction == "yes" and btc_sig == "sell")
                    or ((sell_ratio > SELL_PCT_THRESHOLD) and is_drop_real)):
                print(f"    [POLL {tick:03d}] 📉 BTC against YES + Kalshi bearish — "
                      f"FLIP to NO  ({sell_ratio:.0%} sells, BTC={btc_sig.upper()})")
                return "sell"
            if ((direction == "no" and btc_sig == "buy")
                    or ((sell_ratio > SELL_PCT_THRESHOLD) and is_drop_real)):
                print(f"    [POLL {tick:03d}] 📉 BTC against NO + Kalshi bearish — "
                      f"FLIP to YES ({sell_ratio:.0%} sells, BTC={btc_sig.upper()})")
                return "sell"

            if ((direction == "yes" and btc_sig == "sell")
                    or ((sell_ratio > SELL_PCT_THRESHOLD) and is_drop_real)):
                print(f"    [POLL {tick:03d}] 📉 BTC against YES + Kalshi bearish — "
                      f"FLIP to NO  ({sell_ratio:.0%} sells, BTC={btc_sig.upper()})")
                return "sell"
            if (((direction == "no" and btc_sig == "sell")
                    and (buy_ratio > 0.72))
                    and not is_drop_real):
                print(f"    [POLL {tick:03d}] 📈 BTC favours NO  — return BUY  "
                      f"(BTC={btc_sig.upper()}  buy={buy_ratio:.0%} > 72%  drop={is_drop_real})")
                return "buy"
            if (((direction == "yes" and btc_sig == "buy")
                    and (buy_ratio > 0.72))
                    and not is_drop_real):
                print(f"    [POLL {tick:03d}] 📈 BTC favours YES  — return BUY  "
                      f"(BTC={btc_sig.upper()}  buy={buy_ratio:.0%} > 72%  drop={is_drop_real})")
                return "buy"          

            # ── Otherwise: keep polling ───────────────────────────────────────
            if tick % 10 == 0:
                print(f"    [POLL {tick:03d}] ⏸ awaiting confirmation — "
                      f"dir={direction}  Kalshi sells={sell_ratio:.0%}  "
                      f"BTC={btc_sig.upper()} and DROP is real= {is_drop_real}") 

    return "hold"

# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  ORDER BUILDERS / HELPERS                                                ║
# ╚════════════════════════════════════════════════════════════════════════════╝
# Kalshi V2 create-order endpoint (the legacy POST /portfolio/orders was
# deprecated → HTTP 410 "deprecated_v1_order_endpoint").
ORDER_CREATE_PATH = os.getenv("KALSHI_ORDER_PATH", "/portfolio/events/orders")


def _mk_order(
    ticker: str, action: str, side: str, count: int, price_cents: int,
) -> dict:
    """
    Build a Kalshi **V2** create-order body (POST ``ORDER_CREATE_PATH``).

    The V2 book is single-sided and quoted from the YES leg: ``side='bid'``
    buys YES, ``side='ask'`` sells YES, and ``price`` is ALWAYS the YES price
    in dollars.  We map the bot's (action, yes/no side, price-in-cents) onto it:

        buy  YES @ p  ->  bid, price = p/100
        sell YES @ p  ->  ask, price = p/100
        buy  NO  @ p  ->  ask, price = (100-p)/100   (= sell YES at 1-p)
        sell NO  @ p  ->  bid, price = (100-p)/100   (= buy YES at 1-p)
    """
    if side == "yes":
        v2_side = "bid" if action == "buy" else "ask"
        yes_cents = price_cents
    else:                                   # NO leg → complementary YES price
        v2_side = "ask" if action == "buy" else "bid"
        yes_cents = 100 - price_cents
    return {
        "ticker": ticker,
        "side": v2_side,                    # bid = buy YES, ask = sell YES
        "count": f"{int(count):.2f}",       # fixed-point string per V2 schema
        "price": f"{yes_cents / 100.0:.4f}",  # YES price in dollars
        # A RESTING order by default, an immediate one when asked.
        #
        # A good-till-canceled limit rests, and a resting order has to reserve
        # its cash on the shard the market settles on -- which is why Kalshi
        # publishes a "total resting order value" at all. With automatic
        # rebalancing off, that shard holds cents, the reservation cannot be
        # made, and the order comes back insufficient_balance while the
        # account is plainly funded elsewhere.
        #
        # Kalshi's own web app does not rest: it sends order_type "market"
        # with immediate_or_cancel, which matches against what is already
        # there and reserves nothing. That is the difference between an order
        # that fills on this account and one that does not.
        #
        # Env-driven so the change is a launch option rather than a rewrite,
        # and so the older btc engines keep the behaviour they were tuned on.
        "time_in_force": os.getenv("KALSHI_TIF", "good_till_canceled"),
        "self_trade_prevention_type": "taker_at_cross",
        "client_order_id": str(uuid.uuid4()),
    }


def flip(d: DirectionT) -> DirectionT:
    return "no" if d == "yes" else "yes"


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  STEP 5 — PLACE BUY ORDER @ 99¢  (or flipped direction on sell signal)  ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def place_buy(
    c: KalshiClient, ticker: str, side: DirectionT,
    buy_at_cents: int = BUY_CENTS,
    contracts: int = CONTRACTS,
) -> dict | None:
    order = _mk_order(ticker, "buy", side, contracts, buy_at_cents)
    tag   = "[DRY] " if DRY_RUN else ""
    print(f"  {tag}[BUY] {side.upper()} ×{contracts} @ {buy_at_cents}¢")

    if DRY_RUN:
        return {"order": {
            "order_id": f"DRY-{uuid.uuid4().hex[:8]}",
            "ticker": ticker, "side": side, "count": contracts,
            f"{side}_price": buy_at_cents, "status": "filled",
            "taker_fill_cost_dollars": str(round(buy_at_cents / 100 * contracts, 2)),
            "taker_fees_dollars": "0.0",
        }}

    try:
        r = await c.req("POST", ORDER_CREATE_PATH, body=order)
        print(f"  [BUY] resp: {json.dumps(r, indent=2)}")
        return r
    except Exception as e:
        print(f"  [BUY] FAILED: {e}")
        return None


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  STEP 6 — WAIT FOR FILL  →  CALC TP / SL  →  PLACE TP SELL             ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def await_fill(c: KalshiClient, ticker: str, timeout: int = 120) -> bool:
    print(f"  [FILL] Waiting up to {timeout}s …")
    t0 = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - t0) < timeout:
        pending = await resting_orders(c, ticker)
        if not pending:
            print("  [FILL] Filled ✓")
            return True
        print(f"  [FILL] {len(pending)} resting …")
        await asyncio.sleep(4)
    print("  [FILL] Timeout.")
    return False


def _tp_sl(avg_cents: float, buy_contracts: int) -> tuple[int, float]:
    """
    TP cents = entry_avg * (1 + PROFIT_PCT%).
        Hard ceiling: if calculated TP would exceed 90¢, cap it at 91¢
        regardless of what PROFIT_PCT is set to in .env.  This avoids
        placing sell orders at prices the market will never reach.
    SL total $ = (avg_cents/100 * buy_contracts) * (1 - STOP_PCT%).
        ``buy_contracts`` MUST be the actual contracts bought for this
        trade (`_buy_contracts` from the main runner) — NOT the module-level
        ``CONTRACTS`` constant.  When DO_YOU_HAVE_STOP_SELL=FALSE the bot
        sizes contracts dynamically via CONTRACTS_PV_PCT and the sizing
        differs from KALSHI_CONTRACTS, so using the module constant
        produced an SL floor based on the wrong notional.
    """
    tp_raw  = round(avg_cents * (1 + PROFIT_PCT / 100))
    tp      = 91 if tp_raw > 90 else tp_raw
    total   = (avg_cents / 100) * buy_contracts
    sl      = total * (1 - STOP_PCT / 100)
    return int(tp), round(sl, 4)



# ── never sell what we do not hold ───────────────────────────────────────────
# Kalshi's V2 book is single-sided and quoted from the YES leg, so "sell YES"
# is an ASK. An ASK with no YES inventory does not fail - it OPENS A SHORT,
# which on this venue reads as a NO position. That is not a rejected order, it
# is a brand new trade in the opposite direction.
#
# It happened live on 08/27 (Britt Du Pree): the 97c take-profit filled at
# 1:43pm and flattened the position; a second exit fired at 1:46pm, sold 25
# YES the account no longer had, and opened 25 NO at ~80c. Buying out of it at
# 2:12pm cost $23.22 and turned a +$10.00 winner into -$8.02.
#
# Call sites already re-read the position before exiting, but a check that
# happens seconds and several awaits before the POST is a time-of-check /
# time-of-use gap, and a resting take-profit can fill inside it. So the
# invariant lives HERE, at the last statement before the order goes out, where
# nothing can get between it and the wire:
#
#   * the position is re-fetched immediately before sending;
#   * the side must match - selling YES while holding NO opens a short too;
#   * the count is CLAMPED to what is actually held, never the remembered
#     number, so a partial fill or partial exit cannot overshoot;
#   * a fetch error sells NOTHING (fail safe - an unknown position is not an
#     empty one);
#   * a freshly-filled buy may not be visible in /portfolio/positions yet, so
#     zero is retried briefly before it is believed. Without that, placing the
#     opening take-profit would race the fill and silently stop happening.
class _SkipSell(Exception):
    """Raised in place of an order when the guard says there is nothing to sell.

    The inline sell sites in run() each sit inside their own
    `try/except Exception` block, so this rides that handler out rather than
    forcing a restructure of deeply nested control flow. The guard has already
    logged the reason by the time it is raised.
    """


SELL_GUARD_RETRIES = int(os.getenv("KALSHI_SELL_GUARD_RETRIES", "3"))
SELL_GUARD_DELAY_S = float(os.getenv("KALSHI_SELL_GUARD_DELAY_S", "1.5"))


async def sellable_contracts(c: "KalshiClient", ticker: str, side: str,
                             want: int, *, tag: str = "SELL") -> int:
    """Contracts it is safe to sell RIGHT NOW: min(want, held), else 0.

    Never raises - a guard that can throw would just move the failure. Every
    refusal is logged with the reason, because a sell that silently does not
    happen is its own kind of bug.
    """
    want = max(0, int(want))
    if want == 0:
        return 0
    for attempt in range(1, max(1, SELL_GUARD_RETRIES) + 1):
        try:
            pos = await position_for(c, ticker)
        except Exception as e:                                  # noqa: BLE001
            print(f"  [{tag}] {ticker}: position fetch failed ({e}) — "
                  f"NOTHING SOLD (fail safe)", file=sys.stderr)
            return 0
        held = int((pos or {}).get("contracts", 0) or 0)
        if held > 0:
            held_side = "yes" if float(pos.get("position_fp", "0")) >= 0 else "no"
            if held_side != side:
                print(f"  [{tag}] {ticker}: holding {held} {held_side.upper()} but "
                      f"asked to sell {side.upper()} — NOTHING SOLD (a sell on the "
                      f"other leg opens a new position)", file=sys.stderr)
                return 0
            if held < want:
                print(f"  [{tag}] {ticker}: asked to sell {want} but only {held} "
                      f"held — clamped to {held}")
            return min(want, held)
        if attempt < max(1, SELL_GUARD_RETRIES):
            await asyncio.sleep(SELL_GUARD_DELAY_S)
    print(f"  [{tag}] {ticker}: NO open position — NOTHING SOLD "
          f"(selling flat would open a short)", file=sys.stderr)
    return 0


async def place_tp_sell(
    c: KalshiClient, ticker: str, side: DirectionT,
    contracts: int, tp_cents: int,
) -> None:
    tag   = "[DRY] " if DRY_RUN else ""
    print(f"  {tag}[TP] Sell {side.upper()} ×{contracts} @ {tp_cents}¢")
    if DRY_RUN:
        return
    contracts = await sellable_contracts(c, ticker, side, contracts, tag="TP")
    if contracts <= 0:
        return
    order = _mk_order(ticker, "sell", side, contracts, tp_cents)
    try:
        await c.req("POST", ORDER_CREATE_PATH, body=order)
    except Exception as e:
        print(f"  [TP] Sell failed: {e}")


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  STEP 7 — MONITOR TRADE                                                 ║
# ║                                                                          ║
# ║  Async price stream @ 1 000 ms → deque(maxlen=30) → sell / hold.        ║
# ║  Exits on: TP sell filled | SL hit | sell signal from stream.            ║
# ║  On SL / sell-signal: cancel all pending, fire-sale at 5¢.              ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def _monitor_gen(
    c: KalshiClient, ticker: str, side: str,
    interval_s: float = 1.0, window: int = 30,
) -> AsyncIterator[tuple[float | None, SignalT]]:
    """
    Async generator: yields (price, signal) every interval_s seconds.
    Same concurrent-fetch pattern as the 500 ms poller, wider deque.
    """
    buf: deque[float] = deque(maxlen=window)
    while True:
        fetch = asyncio.create_task(_bid_price(c, ticker, side))
        timer = asyncio.create_task(asyncio.sleep(interval_s))
        price = await fetch
        await timer
        if price is not None:
            buf.append(price)
            yield price, compute_signal(buf)
        else:
            yield None, "hold"


async def _fire_sale(
    c: KalshiClient, ticker: str, side: DirectionT, contracts: int,
) -> None:
    tag   = "[DRY] " if DRY_RUN else ""
    print(f"  {tag}[EXIT] Fire-sale {contracts} × {side} @ {FIRE_SALE_CENTS}¢")
    if DRY_RUN:
        return
    contracts = await sellable_contracts(c, ticker, side, contracts, tag="EXIT")
    if contracts <= 0:
        return
    order = _mk_order(ticker, "sell", side, contracts, FIRE_SALE_CENTS)
    try:
        await c.req("POST", ORDER_CREATE_PATH, body=order)
    except Exception as e:
        print(f"  [EXIT] Sell failed: {e}")


async def monitor_trade(
    c: KalshiClient,
    ticker: str,
    direction: DirectionT,
    entry_total: float,
    entry_avg_cents: float,
    tp_cents: int,
    sl_total: float,
    buy_contracts: int,
    btc: Optional["BtcVidyaMonitor"] = None,
) -> tuple[str, float | None, float | None]:
    """
    Returns: (exit_reason, min_bid_seen, max_bid_seen)

    exit_reason   : "TAKE_PROFIT" | "STOP_LOSS" | "SELL_SIGNAL" | "NO_POSITION"
    min_bid_seen  : lowest bid (dollars) observed during the trade
    max_bid_seen  : highest bid (dollars) observed during the trade

    The min/max bids are used by the main loop to compute MAX_LOSS_PCT
    (drawdown on winning trades) and MAX_PROFIT_PCT (peak unrealised
    gain on losing trades) for the CSV log.
    """
    tp_total = (tp_cents / 100) * buy_contracts
    print(f"  [MON] Entry ${entry_total:.2f}  |  TP ${tp_total:.2f} ({tp_cents}¢)  |  "
          f"SL ${sl_total:.2f}")

    # ── Bid extremes tracking (for MAX_LOSS_PCT / MAX_PROFIT_PCT) ─────────────
    min_bid: float | None = None
    max_bid: float | None = None

    # Wait for position to appear (up to 60 s)
    pos: dict | None = None
    for _ in range(12):
        pos = await position_for(c, ticker)
        if pos and pos["contracts"] > 0:
            print(f"  [MON] Position: {pos['contracts']} contracts")
            break
        await asyncio.sleep(5)
    else:
        print("  [MON] Position never appeared — aborting.")
        await cancel_all(c)
        return "NO_POSITION", min_bid, max_bid

    # Main loop  (1 000 ms / deque-20)
    gen  = _monitor_gen(c, ticker, direction, interval_s=1.0, window=20)
    tick = 0

    # ── Sentiment tracking for EXIT TRIGGER 3 ─────────────────────────────────
    MONITOR_SELL_SIGNAL = 0          # cumulative count of sell / strong_sell ticks
    MONITOR_BUY_SIGNAL  = 0          # cumulative count of buy ticks
    MONITOR_MIN_EVENTS  = 100        # min non-hold events before evaluating ratio
    MONITOR_SELL_RATIO  = 0.57       # exit if sells ≥ 60 % of directional signals
    MONITOR_LOSS_PCT  = 0.15       # exit if sells ≥ 60 % of directional signals

    async for price, signal in gen:
        tick += 1
        if price is None:
            continue

        # ── Track bid extremes for MAX_LOSS_PCT / MAX_PROFIT_PCT ──────────────
        if min_bid is None or price < min_bid:
            min_bid = price
        if max_bid is None or price > max_bid:
            max_bid = price

        # Refresh position periodically (every 3 ticks = ~3 s)
        if tick % 3 == 0:
            pos = await position_for(c, ticker)

        # Position gone → probably TP filled
        if pos is None or pos["contracts"] == 0:
            pending = await resting_orders(c, ticker)
            if not pending:
                print("  [MON] ✓ Position closed — TP filled.")
                return "TAKE_PROFIT", min_bid, max_bid
            await cancel_all(c)
            return "TAKE_PROFIT", min_bid, max_bid

        contracts  = pos["contracts"]
        live_value = price * contracts
        ts         = _cst_now().strftime("%H:%M:%S")

        # ── Accumulate sentiment counters (hold signals ignored) ──────────────
        if signal in ("sell", "strong_sell"):
            MONITOR_SELL_SIGNAL += 1
        elif signal == "buy":
            MONITOR_BUY_SIGNAL += 1
        total_events = MONITOR_SELL_SIGNAL + MONITOR_BUY_SIGNAL
        #eg 0.22
        total_loss = round(1-round(float(live_value/entry_total),2),2)
        total_loss_compare = int(round(total_loss*100,2))
        if tick % 5 == 0 or signal == "strong_sell":
            sell_pct = (MONITOR_SELL_SIGNAL / total_events * 100) if total_events else 0.0
            print(f"  [MON {tick:04d}] {ts}  bid={price:.4f}  "
                  f"val=${live_value:.2f}  SL=${sl_total:.2f}  "
                  f"TP=${tp_total:.2f}  sig={signal.upper()}  "
                  f"S/B={MONITOR_SELL_SIGNAL}/{MONITOR_BUY_SIGNAL} ({sell_pct:.0f}%)")
        sell_pct_to_compare = (MONITOR_SELL_SIGNAL / total_events * 100) if total_events else 0.0
        # Periodically check whether TP sell already filled
        if tick % 6 == 0:
            pending = await resting_orders(c, ticker)
            if not pending:
                chk = await position_for(c, ticker)
                if chk is None or chk["contracts"] == 0:
                    print("  [MON] ✓ TP filled (confirmed).")
                    return "TAKE_PROFIT", min_bid, max_bid

        # ── EXIT TRIGGER 1: STOP LOSS  ────────────────────────────────────────
        if live_value <= sl_total:
            print(f"  [MON] ⛔ STOP LOSS  val=${live_value:.2f} ≤ SL=${sl_total:.2f}")
            await cancel_all(c)
            await asyncio.sleep(1)
            await _fire_sale(c, ticker, direction, contracts)
            return "STOP_LOSS", min_bid, max_bid

        # ── EXIT TRIGGER 2: STRONG_SELL signal  ───────────────────────────────
        # Weak "sell" signals are ignored — we hold until TP fills or SL hits.
        # Only the 7-gate confirmed STRONG_SELL triggers an early exit.
        if signal == "strong_sell" and total_loss > MONITOR_LOSS_PCT:
            print(f"  [MON] 📉📉 STRONG_SELL signal — executing fire sale")
            await cancel_all(c)
            await asyncio.sleep(1)
            await _fire_sale(c, ticker, direction, contracts)
            return "SELL_SIGNAL", min_bid, max_bid

        # ── EXIT TRIGGER 3: Bearish sentiment ratio + BTC contradiction ───────
        # After at least MONITOR_MIN_EVENTS non-hold events, fire only when:
        #   sell_ratio >= MONITOR_SELL_RATIO   (Kalshi sentiment bearish)
        #   AND total_loss > MONITOR_LOSS_PCT  (position already underwater)
        #   AND BTC bias contradicts our held direction:
        #         direction "yes"  → BTC == "sell"  (BTC down hurts YES)
        #         direction "no"   → BTC == "buy"   (BTC up hurts NO)
        if total_events >= MONITOR_MIN_EVENTS:
            sell_ratio       = MONITOR_SELL_SIGNAL / total_events
            btc_sig          = btc.latestBtcVidyaSignal() if btc else "hold"
            btc_contradicts  = (
                (direction == "yes" and btc_sig == "sell") or
                (direction == "no"  and btc_sig == "buy")
            )
            if (sell_ratio >= MONITOR_SELL_RATIO
                    and total_loss > MONITOR_LOSS_PCT
                    and btc_contradicts):
                print(f"  [MON] 📊 BEARISH SENTIMENT + BTC against {direction.upper()} — "
                      f"loss={total_loss:.0%}  "
                      f"{MONITOR_SELL_SIGNAL}/{total_events} sells "
                      f"({sell_ratio:.1%} ≥ {MONITOR_SELL_RATIO:.0%}) "
                      f"+ BTC={btc_sig.upper()} — fire sale")
                await cancel_all(c)
                await asyncio.sleep(1)
                await _fire_sale(c, ticker, direction, contracts)
                return "SELL_SIGNAL", min_bid, max_bid

        # ── EXIT TRIGGER 4: Entered at wrong time, exit soon ─────────────────
        monitor_sell_ratio_compare = int(round(MONITOR_SELL_RATIO * 100)) + 15
        if (signal == "sell"
                and sell_pct_to_compare > monitor_sell_ratio_compare
                and total_events > 100):
            print(f"  [MON] 📉 SELL signal + sentiment {sell_pct_to_compare:.0f}% "
                  f"> {monitor_sell_ratio_compare}% threshold — fire sale")
            await cancel_all(c)
            await asyncio.sleep(1)
            await _fire_sale(c, ticker, direction, contracts)
            return "SELL_SIGNAL", min_bid, max_bid


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  STDOUT / STDERR TEE  (mirror all print() to a dated log file)          ║
# ╚════════════════════════════════════════════════════════════════════════════╝
class _Tee:
    """Writes to every stream in the list — used to tee stdout/stderr to file."""
    def __init__(self, *streams):
        self._streams = streams

    def write(self, data: str) -> None:
        for s in self._streams:
            s.write(data)

    def flush(self) -> None:
        for s in self._streams:
            s.flush()

    def isatty(self) -> bool:
        return False


class _RotatingLogFile:
    """
    File-like object that writes to kalshi_btc_15_YYYYMMDD.log.

    Behaviour:
    - On startup: any existing kalshi_btc_15_*.log files from previous dates
      are moved to ./archive/ automatically.
    - On each write: if the calendar date has rolled over since the file was
      opened, the current file is closed, moved to ./archive/, and a new
      dated file is opened transparently.
    """
    # Defaults preserve legacy standalone behaviour.  When the root dispatcher
    # (bot.py) launches this bot, it sets BOT_LOG_PREFIX=bot_ and BOT_LOG_DIR
    # to the project root so both platforms share a single bot_YYYYMMDD.log.
    _PREFIX_DEFAULT = "kalshi_btc_15_"

    def __init__(self) -> None:
        self._log_dir     = Path(os.getenv("BOT_LOG_DIR", "."))
        self._PREFIX      = os.getenv("BOT_LOG_PREFIX", self._PREFIX_DEFAULT)
        self._ARCHIVE_DIR = self._log_dir / "archive"
        self._ARCHIVE_DIR.mkdir(exist_ok=True, parents=True)
        self._archive_stale_logs()
        self._date = datetime.now().strftime("%Y%m%d")
        self._path = self._log_dir / f"{self._PREFIX}{self._date}.log"
        self._fh   = self._path.open("a", buffering=1, encoding="utf-8")

    # ------------------------------------------------------------------
    def _archive_stale_logs(self) -> None:
        """Move any log files whose date != today into ./archive/."""
        today = datetime.now().strftime("%Y%m%d")
        for f in sorted(self._log_dir.glob(f"{self._PREFIX}*.log")):
            date_part = f.stem[len(self._PREFIX):]   # e.g. "20260517"
            if date_part != today:
                dest = self._ARCHIVE_DIR / f.name
                shutil.move(str(f), str(dest))
                # Can't use print() here (stdout not yet redirected)
                sys.__stdout__.write(f"[LOG] Archived stale log → {dest}\n")

    def _rotate_if_needed(self) -> None:
        """If the date has changed, close the old file, archive it, open new."""
        today = datetime.now().strftime("%Y%m%d")
        if today == self._date:
            return
        # Flush & close current file
        self._fh.flush()
        self._fh.close()
        # Archive the just-closed file
        if self._path.exists():
            dest = self._ARCHIVE_DIR / self._path.name
            shutil.move(str(self._path), str(dest))
        # Open fresh file for the new date
        self._date = today
        self._path = self._log_dir / f"{self._PREFIX}{today}.log"
        self._fh   = self._path.open("a", buffering=1, encoding="utf-8")
        self._fh.write(f"[LOG] Date rolled — new log file: {self._path.name}\n")
        self._fh.flush()

    # ------------------------------------------------------------------  (file-like interface)
    def write(self, data: str) -> None:
        self._rotate_if_needed()
        self._fh.write(data)

    def flush(self) -> None:
        self._fh.flush()

    def isatty(self) -> bool:
        return False

    def close(self) -> None:
        self._fh.flush()
        self._fh.close()

    @property
    def name(self) -> str:
        return str(self._path)


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  MAIN BOT LOOP  (Steps 1 – 10 orchestrated)                             ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def run() -> None:
    # MIN-PV floor is ratcheted up at runtime on winning trades (see STEP 8).
    global DO_NOT_BUY_IF_PORTFOLIO_BELOW
    _floor_buffer: float | None = (PORTFOLIO_FLOOR_BUFFER
                                   if PORTFOLIO_FLOOR_BUFFER > 0 else None)

    # ── Tee all output to a rotating dated log file ──────────────────────────
    _log_fh    = _RotatingLogFile()          # archives stale logs at startup
    sys.stdout = _Tee(sys.__stdout__, _log_fh)
    sys.stderr = _Tee(sys.__stderr__, _log_fh)
    print(f"[LOG] Session started — logging to {_log_fh.name}")
    _wins_str = ", ".join(
        f"{s.strftime('%H:%M')}-{e.strftime('%H:%M')}"
        for s, e in HALT_WINDOWS
    )
    print(f"[HALT] Halt windows ({HALT_TIMEZONE}): {_wins_str}  "
          f"(machine_shutdown={HALT_MACHINE_SHUTDOWN})")

    init_csv()
    c = KalshiClient()

    # ── BTC spot-price VIDYA monitor (background task, 30 s polling) ──────────
    btc = BtcVidyaMonitor()
    btc.start()

    current_ticker: str | None = None

    try:
        # ══════════════════════════════════════════════════════════════════════
        # STEP 10 — Outer loop: wait for new market → repeat
        # ══════════════════════════════════════════════════════════════════════
        while True:
            LOSS_RATE      = 0
            market         = await wait_for_market(c, skip=current_ticker)
            ticker         = market["ticker"]
            current_ticker = ticker
            market_opened  = _utc_now()
            _btc_beat_raw  = market.get("strike_price") or market.get("floor_strike") or market.get("cap_strike")
            btc_to_beat    = float(_btc_beat_raw) if _btc_beat_raw else None

            print(f"\n{'═' * 64}")
            print(f"  MARKET : {ticker}")
            print(f"  TRADES : 0/{MAX_TRADES_PER_MARKET}")
            print(f"{'═' * 64}")

            # ══════════════════════════════════════════════════════════════════
            # STEP 9 — Inner loop: up to MAX_TRADES_PER_MARKET
            # ══════════════════════════════════════════════════════════════════
            for trade_no in range(1, MAX_TRADES_PER_MARKET + 1):

                age = (_utc_now() - market_opened).total_seconds()
                if age > TIME_SEC_TO_ORDER:
                    print(f"  Window expired ({age:.0f}s). Next market.")
                    break

                print(f"\n  ── Trade {trade_no}/{MAX_TRADES_PER_MARKET} "
                      f"on {ticker} ──")

                _wr = compute_prediction_win_rate()
                LOSS_RATE = _wr['loss_rate']
                GAIN_RATE = _wr['pv_returns']
                if _wr["pv_total"] > 0:
                    _pv_ret_part = (f" PV Returns: {_wr['pv_returns']}"
                                   if _wr.get("pv_returns") else "")
                    print(f"  [WIN RATE] Prediction "
                          f"(TOTAL:{_wr['total']}; SUCCESS:{_wr['success']}; FAIL:{_wr['loss']}; MIXED:{_wr['failure']}) || "
                          f"SUCESS rate: {_wr['rate']:.1f}% <> LOSS rate: {_wr['loss_rate']:.1f}% || "
                          f"PV + rate: {_wr['overall_win_rate']:.1f}% "
                          f"({_wr['pv_grew']}/{_wr['pv_total']}) || "
                          f"{_pv_ret_part}")
                else:
                    print("  [WIN RATE] No historical trades to evaluate yet.")
                _gain_pct = float(GAIN_RATE.strip().rstrip('%')) if GAIN_RATE else 0.0

                # ── Profit-ratchet: relax the halt floor as banked gains grow.
                #    The more cumulative PV Returns we have, the larger a
                #    drawdown we tolerate before halting (avoids being stopped
                #    out on normal volatility after a strong run).  Tiers are
                #    evaluated highest-first so the threshold is deterministic.
                #    Use a LOCAL floor — never reassign the module-level
                #    MAX_LOSS_RATE (that turns it into a function local and
                #    raises UnboundLocalError on the first read).
                if _gain_pct > 100:
                    _halt_floor = MAX_LOSS_RATE - 75 - 100 - 100   # → -242
                elif _gain_pct > 75:
                    _halt_floor = MAX_LOSS_RATE - 75 - 100         # → -142
                elif _gain_pct > 50:
                    _halt_floor = MAX_LOSS_RATE - 75               # → -42
                else:
                    _halt_floor = -MAX_LOSS_RATE                   # → -33
                if _gain_pct < _halt_floor:
                    await _halt_and_shutdown(
                        c, ticker,
                        reason_tag="LOSS-RATE HALT",
                        reason_msg=(f"PV Returns={GAIN_RATE} < floor "
                                    f"{_halt_floor}% — halting for the day."),
                    )
                    return
                pv = await portfolio_balance(c)
                print(f"  Portfolio: ${pv:.2f}")
                # Establish the profit-ratchet buffer once, from the starting
                # portfolio: buffer = starting_pv - starting_floor (≥ 0).
                # ── BANK-TARGET: stop opening new trades once realized P&L has
                #    grown THIS bot's own bankroll by BTC15_TARGET_PCT. Replaces
                #    the account-PV target below, which scored this bot against
                #    a balance the sports/btc60/perp bots also move.
                if BANKROLL.target_reached():
                    await _halt_and_shutdown(
                        c, ticker,
                        reason_tag="BANK-TARGET HALT",
                        reason_msg=(f"TP reached on bank: ${BANKROLL.balance:.2f} "
                                    f"= +{BTC15_TARGET_PCT:.0f}% on "
                                    f"${BANKROLL.start:.2f} — stopping."),
                    )
                    return
                if BANKROLL.sl_reached():
                    await _halt_and_shutdown(
                        c, ticker,
                        reason_tag="BANK-SL HALT",
                        reason_msg=(f"SL HIT on Bank: ${BANKROLL.balance:.2f} "
                                    f"<= -{BTC15_BANK_SL_PCT:.0f}% on "
                                    f"${BANKROLL.start:.2f} — stopping."),
                    )
                    return
                if DO_NOT_BUY_IF_PORTFOLIO_BELOW > 0 and _floor_buffer is None:
                    _floor_buffer = max(0.0, pv - DO_NOT_BUY_IF_PORTFOLIO_BELOW)
                    print(f"  [MIN-PV] profit-ratchet buffer = ${_floor_buffer:.2f} "
                          f"(floor rises to pv−buffer on each win)")
                if DO_NOT_BUY_IF_PORTFOLIO_BELOW > 0 and pv < DO_NOT_BUY_IF_PORTFOLIO_BELOW:
                    await _halt_and_shutdown(
                        c, ticker,
                        reason_tag="MIN-PV HALT",
                        reason_msg=(f"Portfolio ${pv:.2f} < "
                                    f"DO_NOT_BUY_IF_PORTFOLIO_BELOW "
                                    f"${DO_NOT_BUY_IF_PORTFOLIO_BELOW} — "
                                    f"halting bot."),
                    )
                    return

                # ── TARGET-PV HALT: stop placing new orders once today's PV
                #    growth ≥ TARGET_PORTFOLIO_PCT.  Day-start baseline is
                #    persisted per-date so a mid-day bot restart resumes the
                #    same target.  Set TARGET_PORTFOLIO_PCT=0 to disable.
                if TARGET_PORTFOLIO_PCT > 0:
                    day_start_pv  = get_day_start_portfolio(pv)
                    target_pv     = day_start_pv * (1 + TARGET_PORTFOLIO_PCT / 100.0)
                    gain_today    = ((pv - day_start_pv) / day_start_pv * 100.0
                                     if day_start_pv > 0 else 0.0)
                    print(f"  [TARGET-PV] Day-start=${day_start_pv:.2f}  "
                          f"Target=${target_pv:.2f} (+{TARGET_PORTFOLIO_PCT:.0f}%)  "
                          f"Today={gain_today:+.2f}%")
                    if pv >= target_pv:
                        await _halt_and_shutdown(
                            c, ticker,
                            reason_tag="TARGET-PV HALT",
                            reason_msg=(f"HIT — ${pv:.2f} ≥ target "
                                        f"${target_pv:.2f}. "
                                        f"No new orders today."),
                        )
                        return

                # ── STEP 9a: best-of-three direction vote ──────────────────────
                # Direction is the majority vote across three independent
                # voters.  Voter 1 (settled markets) always votes; voters 2
                # and 3 may abstain.  On a tie (e.g. v1=YES, v2=abstain,
                # v3=NO), V1 (settled markets) breaks the tie.
                #
                #   V1  Settled-market momentum  — last 6 settled KXBTC15M
                #       outcomes, majority vote with a recent-3 tiebreak.
                #       (Always returns "yes" or "no".)
                #       Also yields `actual_direction_previous` for CSV.
                #
                #   V2  Live BTC vs market strike with ±$15 dead band:
                #       live > strike + 15 → YES
                #       live < strike - 15 → NO
                #       within band        → abstain
                #
                #   V3  BTC strong signal — btc.btcSignalWithStrength():
                #       "buy"  / "strong_buy"  → YES (buy YES contracts)
                #       "sell" / "strong_sell" → NO  (buy NO  contracts)
                #       "hold"                 → abstain
                # ---------------------------------------------------------------
                votes_yes = votes_no = 0

                # V1 — settled-market majority vote
                v1_dir, actual_direction_previous = await determine_direction(c)
                if v1_dir == "yes":
                    votes_yes += 1
                else:
                    votes_no  += 1

                # V2 — live BTC vs strike (±$15 dead band)
                _live_btc = btc.last_price if btc else None
                V2_BUFFER = 5.0
                v2_dir: str = "abstain"
                v2_note: str
                if _live_btc is not None and btc_to_beat is not None:
                    if _live_btc > btc_to_beat + V2_BUFFER:
                        v2_dir     = "yes"
                        votes_yes += 1
                        v2_note    = (f"live ${_live_btc:,.2f} > "
                                      f"${btc_to_beat + V2_BUFFER:,.2f}")
                    elif _live_btc < btc_to_beat - V2_BUFFER:
                        v2_dir     = "no"
                        votes_no  += 1
                        v2_note    = (f"live ${_live_btc:,.2f} < "
                                      f"${btc_to_beat - V2_BUFFER:,.2f}")
                    else:
                        v2_note = (f"live ${_live_btc:,.2f} within "
                                   f"strike ${btc_to_beat:,.2f} "
                                   f"±${V2_BUFFER:.0f}")
                else:
                    v2_note = (f"missing data — live_btc={_live_btc}, "
                               f"strike={btc_to_beat}")

                # V3 — BTC strong signal
                strong_sig = btc.btcSignalWithStrength() if btc else "hold"
                if strong_sig in ("buy", "strong_buy"):
                    v3_dir = "yes"
                    votes_yes += 1
                elif strong_sig in ("sell", "strong_sell"):
                    v3_dir = "no"
                    votes_no  += 1
                else:
                    v3_dir = "abstain"   # "hold"

                # Tally → direction (V1 breaks ties since it always votes)
                if votes_yes > votes_no:
                    direction = "yes"
                elif votes_no > votes_yes:
                    direction = "no"
                else:
                    direction = v1_dir   # tie-break

                kalshi_direction = direction   # kept for downstream prints
                btc_sig          = btc.latestBtcVidyaSignal() if btc else "hold"

                print(f"  [DIR] Best-of-3 vote → {direction.upper()}  "
                      f"(YES={votes_yes}  NO={votes_no})")
                print(f"  [DIR]  V1 settled-markets : {v1_dir.upper()}")
                print(f"  [DIR]  V2 live-vs-strike  : {v2_dir.upper():<7s} "
                      f"({v2_note})")
                print(f"  [DIR]  V3 strong-signal   : {v3_dir.upper():<7s} "
                      f"(btcSignalWithStrength={strong_sig.upper()})")

                # ── STEP 4: 500 ms price signal ──────────────────────────────
                print(f"  KALSHI >> {kalshi_direction.upper()} ||  BTC >> {btc_sig.upper()} …")
                print(f"  Scanning {direction.upper()} momentum …")
                signal = await poll_for_signal(
                    c, ticker, direction,
                    btc=btc,
                    interval_s=1, window=20, max_ticks=300,
                )
                print(f"  Signal → {signal.upper()}")

                mode: str

                if signal == "hold":
                    print("  HOLD — skipping slot.")
                    await asyncio.sleep(8)
                    continue

                # ── STEP 5a: buy (flip on sell, with retry) ────────────────────
                # Before committing to a flip, re-poll the ORIGINAL direction
                # up to `retry_original_buy` times (default 3).  Rationale: a
                # single "sell" from STEP 4 can be a transient — give the
                # original side multiple chances to recover.
                #   • Any retry returning non-sell wins → keep original
                #     direction, no flip.
                #   • Any retry returning "hold" → skip the slot (same as the
                #     pre-STEP-5a hold check above).
                #   • All retries still "sell" → flip as before.
                retry_original_buy = 2
                if signal == "sell":
                    for _attempt in range(1, retry_original_buy + 1):
                        print(f"  [STEP 5a RETRY {_attempt}/{retry_original_buy}] "
                              f"re-polling {direction.upper()} before flipping …")
                        signal = await poll_for_signal(
                            c, ticker, direction,
                            btc=btc,
                            interval_s=1, window=20, max_ticks=300,
                        )
                        print(f"  [STEP 5a RETRY {_attempt}] → {signal.upper()}")
                        if signal != "sell":
                            break

                    # A retry may have produced a hold — honour the same
                    # skip-slot semantics as the earlier hold check.
                    if signal == "hold":
                        print("  [STEP 5a] HOLD after retry — skipping slot.")
                        await asyncio.sleep(8)
                        continue

                    if signal == "sell":
                        # All retries still say sell → flip.
                        direction = flip(direction)
                        print(f" FLIP-BUY SELL signal → flipped → {direction.upper()} "
                              f"(after {retry_original_buy} retries)")
                        mode = "FLIP-BUY"
                    else:
                        # Retry rescued the original direction.
                        print(f"  [STEP 5a] Retry rescued {direction.upper()} "
                              f"(signal={signal.upper()}) — no flip.")
                        mode = "BUY"
                else:
                    mode = "BUY"
                
                # ── STEP 5b: Confirming flip  Added by User ────────────────────────────────
                if mode == "FLIP-BUY":
                    signal = await poll_for_signal(
                        c, ticker,direction,
                        btc=btc,
                        isItFlip=True, interval_s=0.75, window=20, max_ticks=300,
                    )
                # ── STEP 5c: buy (flip on sell) Added by User ────────────────────────────────
                if signal == "sell":
                    direction = flip(direction)
                    print(f" ORIGINAL-BUY  SELL signal → flipped → {direction.upper()}")
                    mode = "ORIGINAL-BUY"
                else:
                    mode = "BUY"

                if mode == "ORIGINAL-BUY":
                    signal = await poll_for_signal(
                        c, ticker,direction,
                        btc=btc,
                        isItFlip=True, interval_s=0.75, window=20, max_ticks=200,
                    )
                    if signal == "hold":
                       # Fall back to the BTC monitor's latest non-hold
                       # directional signal (string), NOT the monitor object
                       # itself — assigning `btc` here yielded a printout like
                       # "Signal → <BtcVidyaMonitor object at 0x…>" and made
                       # every downstream signal == "sell" / "hold" check miss.
                       signal = btc.latestBtcVidyaSignal()
                       print(f"  STEP 5c HOLD → falling back to BTC monitor: {signal.upper()}")

                # ── STEP 5c: buy (flip on sell) Added by User ────────────────────────────────
                if signal == "sell":
                    direction = flip(direction)
                    print(f"  SELL signal → flipped → {direction.upper()}")
                    mode = "FLIP-BUY"
                else:
                    mode = "BUY"  
                  

                if signal == "hold":
                    print("  HOLD — skipping slot.")
                    await asyncio.sleep(8)
                    continue
                    
                print(f"  Signal → {signal}")
                
                # ── Entry price band guard: wait for bid to enter band ───────
                # Polls every 3 s until bid is within [MIN_ENTRY_CENTS,
                # MAX_ENTRY_CENTS] AND both BTC and Kalshi signals still favour
                # the trade. Exits when market window expires.
                _band_buf: deque[float] = deque(maxlen=20)
                _band_ready             = False
                _window_expired         = False
                _lotto_triggered        = False  # set True when lotto fires inside band loop
                _lotto_resp             = None   # resp from lotto order placed inside band loop
                _band_wait_lotto_placed = False  # one-shot guard for band-wait side-bet lotto
                _band_loop_start        = _utc_now()    # track 20s rescan timer

                while True:
                    _age = (_utc_now() - market_opened).total_seconds()
                    if _age > TIME_SEC_TO_ORDER:
                        print(f"  ⚠ Market window expired while waiting for "
                              f"band entry ({_age:.0f}s) — next market.")
                        _window_expired = True
                        break

                    _peek = await _bid_price(c, ticker, direction)
                    if _peek is None:
                        await asyncio.sleep(3)
                        continue

                    _band_buf.append(_peek)
                    _bid_cents = _peek * 100

                    # ── Lotto check: place immediately, store resp, continue ──
                    if (not DO_YOU_HAVE_STOP_SELL and LOTTO_TRADE
                            and _age < 320 and _bid_cents < 14):
                        print(f"  [LOTTO] 🎰 {direction} Bid={_bid_cents:.0f}¢ < 14¢  "
                              f"age={_age:.0f}s — placing {LOTTO_CONTRACTS} × 15¢ now!")
                        _lotto_resp      = await place_buy(c, ticker, direction,
                                                           buy_at_cents=15,
                                                           contracts=LOTTO_CONTRACTS)
                        _lotto_triggered = True
                        _band_ready      = True
                        break

                    _btc_sig   = btc.latestBtcVidyaSignal()
                    _btc_ok    = (direction == "yes" and _btc_sig == "buy") or \
                                 (direction == "no"  and _btc_sig == "sell")
                    _kal_sig   = compute_signal(_band_buf) if len(_band_buf) >= 20 else "hold"
                    _in_band   = MIN_ENTRY_CENTS <= _bid_cents <= MAX_ENTRY_CENTS

                    if _in_band and _btc_ok and _kal_sig not in ("strong_sell"):
                        print(f"  ✓ Entry conditions met — "
                              f"bid={_peek:.4f} ({_bid_cents:.0f}¢)  "
                              f"BTC={_btc_sig.upper()} BTC_OK > {_btc_ok}  Kalshi={_kal_sig.upper()}")
                        _band_ready = True
                        break

                    print(f"  ⏳ Waiting {direction} — bid={_peek:.4f} ({_bid_cents:.0f}¢) "
                          f"[band:{'Y' if _in_band else 'N'}]  "
                          f"BTC={_btc_sig.upper()}[{'Y' if _btc_ok else 'N'}]  "
                          f"Kalshi={_kal_sig.upper()}  age={_age:.0f}s")

                    # ── Band-wait side-bet lotto ──────────────────────────────
                    # While waiting for the main entry conditions, if the
                    # CURRENT direction's bid is very high AND there is still
                    # meaningful time left in the 15-min cycle, plant an
                    # asymmetric "free option" on the OPPOSITE side at 4¢
                    # (LOTTO_CONTRACTS), then on fill place a TP SELL for
                    # half of the position at 10¢.  Fires AT MOST ONCE per
                    # slot (guarded by _band_wait_lotto_placed); does NOT
                    # break the band loop — the regular non-lotto entry
                    # search continues alongside.  Mirrors Trigger C's
                    # shape but lives inside the band guard instead of the
                    # NO-STOP monitor.
                    BAND_LOTTO_BID_CENTS         = 93     # min current-dir bid (¢)
                    BAND_LOTTO_TIME_REMAINING_S  = 300    # min seconds left
                    BAND_LOTTO_MARKET_LEN_S      = 900    # 15-min Kalshi cycle
                    BAND_LOTTO_BUY_CENTS         = 4
                    BAND_LOTTO_TP_CENTS          = 11
                    BAND_LOTTO_FILL_TIMEOUT_S    = 60
                    _bl_time_remaining = max(0, BAND_LOTTO_MARKET_LEN_S - _age)
                    if (not _band_wait_lotto_placed
                            and _bid_cents > BAND_LOTTO_BID_CENTS
                            and _bl_time_remaining > BAND_LOTTO_TIME_REMAINING_S):
                        _bl_flip_dir = flip(direction)
                        _bl_tp_count = max(1, LOTTO_CONTRACTS // 2)
                        print(f"  [BAND-LOTTO] 🎰 {direction.upper()} bid="
                              f"{_bid_cents:.0f}¢ > {BAND_LOTTO_BID_CENTS}¢ "
                              f"with {_bl_time_remaining:.0f}s remaining — "
                              f"flipped lotto buy {LOTTO_CONTRACTS} × "
                              f"{_bl_flip_dir.upper()} @ "
                              f"{BAND_LOTTO_BUY_CENTS}¢, then TP "
                              f"{_bl_tp_count} × @ {BAND_LOTTO_TP_CENTS}¢ "
                              f"on fill.  (Main band loop continues.)")
                        # Set guard BEFORE awaits so an exception path
                        # can't cause re-fire on the next 3s tick.
                        _band_wait_lotto_placed = True
                        try:
                            _bl_buy_order = _mk_order(
                                ticker, "buy", _bl_flip_dir,
                                LOTTO_CONTRACTS, BAND_LOTTO_BUY_CENTS,
                            )
                            _dry = "[DRY] " if DRY_RUN else ""
                            print(f"  {_dry}[BAND-LOTTO] buy order: {_bl_buy_order}")
                            if not DRY_RUN:
                                await c.req(
                                    "POST", ORDER_CREATE_PATH,
                                    body=_bl_buy_order,
                                )
                        except Exception as e:
                            print(f"  [BAND-LOTTO] buy submit failed: {e}")

                        if DRY_RUN:
                            print(f"  [DRY] [BAND-LOTTO] would await fill "
                                  f"then TP {_bl_tp_count}/{LOTTO_CONTRACTS}"
                                  f" × {_bl_flip_dir.upper()} @ "
                                  f"{BAND_LOTTO_TP_CENTS}¢")
                        else:
                            print(f"  [BAND-LOTTO] waiting up to "
                                  f"{BAND_LOTTO_FILL_TIMEOUT_S}s for lotto "
                                  f"buy to fill …  (band loop paused "
                                  f"during this wait)")
                            try:
                                _bl_filled = await await_fill(
                                    c, ticker,
                                    timeout=BAND_LOTTO_FILL_TIMEOUT_S,
                                )
                            except Exception as e:
                                print(f"  [BAND-LOTTO] await_fill failed: {e}")
                                _bl_filled = False

                            if _bl_filled:
                                try:
                                    # never-sell-naked: this path builds and
                                    # POSTs its own order, so it bypasses
                                    # place_tp_sell and needs the guard here.
                                    _bl_n = await sellable_contracts(
                                        c, ticker, _bl_flip_dir,
                                        _bl_tp_count, tag="BAND-LOTTO",
                                    )
                                    if _bl_n > 0:
                                        _bl_tp_order = _mk_order(
                                            ticker, "sell", _bl_flip_dir,
                                            _bl_n, BAND_LOTTO_TP_CENTS,
                                        )
                                        print(f"  [BAND-LOTTO] TP "
                                              f"{_bl_n}/{LOTTO_CONTRACTS}"
                                              f" × {_bl_flip_dir.upper()} @ "
                                              f"{BAND_LOTTO_TP_CENTS}¢: "
                                              f"{_bl_tp_order}")
                                        await c.req(
                                            "POST", ORDER_CREATE_PATH,
                                            body=_bl_tp_order,
                                        )
                                except Exception as e:
                                    print(f"  [BAND-LOTTO] TP submit "
                                          f"failed: {e}")
                            else:
                                print(f"  [BAND-LOTTO] buy did not fill "
                                      f"within {BAND_LOTTO_FILL_TIMEOUT_S}s; "
                                      f"skipping TP.")

                    # ── Re-poll rescan after 20s without _band_ready ──────────
                    # If the regular 3s poll hasn't found entry conditions in
                    # 20s, run a tighter 40-tick × 0.75s scan (~30s).  If bid is in
                    # band AND signal=buy AND BTC aligned → accept and proceed.
                    # Otherwise reset the 20s timer and keep the outer loop going.
                    _band_elapsed = (_utc_now() - _band_loop_start).total_seconds()
                    if _band_elapsed >= 20:
                        print(f"  [BAND] 20s without entry — "
                              f"quick rescan: 40 ticks × 0.75s …")
                        _rescan_buf: deque[float] = deque(maxlen=40)
                        for _ in range(40):
                            _rf = asyncio.create_task(_bid_price(c, ticker, direction))
                            _rt = asyncio.create_task(asyncio.sleep(0.75))
                            _rp = await _rf
                            await _rt
                            if _rp is not None:
                                _rescan_buf.append(_rp)

                        _rescan_live    = await _bid_price(c, ticker, direction)
                        _rescan_sig     = compute_signal(_rescan_buf) if len(_rescan_buf) >= 40 else "hold"
                        _rescan_btc     = btc.latestBtcVidyaSignal() if btc else "hold"
                        _rescan_btc_ok  = (
                            (direction == "yes" and _rescan_btc == "buy") or
                            (direction == "no"  and _rescan_btc == "sell")
                        )
                        _rescan_cents   = int(round(_rescan_live * 100)) if _rescan_live else 0
                        _rescan_in_band = MIN_ENTRY_CENTS <= _rescan_cents <= MAX_ENTRY_CENTS

                        print(f"  [BAND RESCAN] {direction} bid={_rescan_cents}¢  "
                              f"sig={_rescan_sig.upper()}  "
                              f"BTC={_rescan_btc.upper()}  "
                              f"band={'Y' if _rescan_in_band else 'N'}  "
                              f"BTC_ok={'Y' if _rescan_btc_ok else 'N'}")

                        if _rescan_in_band and _rescan_sig == "buy" and _rescan_btc_ok:
                            print(f"  [BAND RESCAN] Y All conditions met — "
                                  f"reconfirming direction (V1/V2/V3) before "
                                  f"placing order …")

                            # ── Direction reconfirmation (best-of-3) ─────────
                            # Mirror STEP 9a's voter logic so a market that
                            # has drifted while we waited at the band can
                            # still flip us out of a trade that no longer
                            # matches the consensus.  V1 always votes; V2
                            # and V3 may abstain; ties broken by V1.
                            RC_V2_BUFFER = 15.0
                            _rc_yes = _rc_no = 0

                            # V1 — settled-market momentum
                            _rc_v1, _ = await determine_direction(c)
                            if _rc_v1 == "yes":
                                _rc_yes += 1
                            else:
                                _rc_no  += 1

                            # V2 — live BTC vs strike (±$15 dead band)
                            _rc_live = btc.last_price if btc else None
                            _rc_v2: str = "abstain"
                            if _rc_live is not None and btc_to_beat is not None:
                                if _rc_live > btc_to_beat + RC_V2_BUFFER:
                                    _rc_v2 = "yes"
                                    _rc_yes += 1
                                elif _rc_live < btc_to_beat - RC_V2_BUFFER:
                                    _rc_v2 = "no"
                                    _rc_no  += 1

                            # V3 — BTC strong signal
                            _rc_strong = (btc.btcSignalWithStrength()
                                          if btc else "hold")
                            if _rc_strong in ("buy", "strong_buy"):
                                _rc_v3 = "yes"
                                _rc_yes += 1
                            elif _rc_strong in ("sell", "strong_sell"):
                                _rc_v3 = "no"
                                _rc_no  += 1
                            else:
                                _rc_v3 = "abstain"

                            # Tally → confirmed direction (V1 breaks ties)
                            if _rc_yes > _rc_no:
                                _rc_confirmed = "yes"
                            elif _rc_no > _rc_yes:
                                _rc_confirmed = "no"
                            else:
                                _rc_confirmed = _rc_v1

                            print(f"  [BAND RESCAN RECONFIRM] "
                                  f"V1={_rc_v1.upper()}  "
                                  f"V2={_rc_v2.upper()}  V3={_rc_v3.upper()}  "
                                  f"→ {_rc_confirmed.upper()} "
                                  f"(YES={_rc_yes} NO={_rc_no})  "
                                  f"current={direction.upper()}")

                            if _rc_confirmed != direction:
                                print(f"  [BAND RESCAN] ✗ Direction mismatch — "
                                      f"reconfirmed {_rc_confirmed.upper()} "
                                      f"≠ current {direction.upper()}. "
                                      f"Skipping order, resetting timer, "
                                      f"continuing poll …")
                                _band_loop_start = _utc_now()
                                continue

                            print(f"  [BAND RESCAN] ✓ Direction confirmed "
                                  f"{direction.upper()} — proceeding.")
                            if _rescan_live:
                                _peek = _rescan_live   # refresh peek for planning_to_buy
                            _band_ready = True
                            break

                        # Rescan failed — reset timer, skip 3s sleep (rescan ~30s)
                        print(f"  [BAND RESCAN] Conditions not met — "
                              f"resetting timer, continuing poll …")
                        _band_loop_start = _utc_now()
                        continue

                    await asyncio.sleep(3)

                if _window_expired:
                    break

                # ── Trading hours gate ────────────────────────────────────────
                # Configurable via .env:
                #   HALT_START_TIME[1..9] / HALT_END_TIME[1..9]  (multiple windows)
                #   HALT_START_TIME      / HALT_END_TIME         (legacy single)
                #   HALT_TIMEZONE, HALT_MACHINE_SHUTDOWN
                # Halt fires if local time is inside ANY configured window
                # (midnight-wrapping windows like 22:15→02:45 supported).
                _local_now  = datetime.now(ZoneInfo(HALT_TIMEZONE))
                _local_time = _local_now.time()
                _matched_win = _in_halt_window(_local_time)
                if _matched_win is not None:
                    _s, _e = _matched_win
                    await _halt_and_shutdown(
                        c, ticker,
                        reason_tag="TRADING-HOURS HALT",
                        reason_msg=(f"Local time {_local_now.strftime('%H:%M')} "
                                    f"({HALT_TIMEZONE}) is inside halt window "
                                    f"{_s.strftime('%H:%M')}–{_e.strftime('%H:%M')}."),
                    )
                    return

                # ── STEP 5f: BTC strong-signal block ──────────────────────────
                # Final safety gate before placing the buy.  Reject the trade
                # if the BTC monitor has seen a strong signal opposing our
                # direction within the recent lookback window.
                #
                #   direction = "yes"  → block if any recent "strong_sell"
                #                        (BTC strongly falling)
                #   direction = "no"   → block if any recent "strong_buy"
                #                        (BTC strongly rising)
                #
                # Lookback = 20 ticks × 15s ≈ last 5 minutes.  If blocked,
                # skip this trade slot (continue) so the next slot re-runs
                # all gates with fresh data.
                if btc and btc.hasRecentStrongAgainst(direction, lookback=20):
                    _opp = "strong_sell" if direction == "yes" else "strong_buy"
                    print(f"  [STEP 5f] BLOCKED — recent {_opp.upper()} in "
                          f"btc.strength_history (last 20 ticks); refusing "
                          f"to buy {direction.upper()}. Skipping slot.")
                    await asyncio.sleep(5)
                    continue

                # ── NO-TRADE window (user 08/03): stay alive, enter nothing.
                _ntw = _in_no_trade_window()
                if _ntw is not None:
                    print(f"  [NO-TRADE] local time inside "
                          f"{_ntw[0]:%H:%M}-{_ntw[1]:%H:%M} - skipping this "
                          f"slot; monitoring only")
                    await asyncio.sleep(60)
                    continue

                planning_to_buy = int(round(_peek * 100))

                # Dynamic contract count for buy-only mode (no stop/sell)
                #if not DO_YOU_HAVE_STOP_SELL:
                # common bot contract (user 08/03): %-of-PV sizing removed;
                # NO-STOP mode sizes like every other path — fixed CONTRACTS.
                _buy_contracts = max(1, CONTRACTS)
                print(f"  [BUY PLAN] NO-STOP mode: fixed {_buy_contracts} contracts "
                          f"÷ {_peek} = {_buy_contracts} contracts")
                #else:
                #    _buy_contracts = CONTRACTS

                # ── Lotto: order already placed inside band loop — just pick up resp ──
                if _lotto_triggered:
                    planning_to_buy = 15
                    _buy_contracts  = LOTTO_CONTRACTS
                    resp            = _lotto_resp
                else:
                    print(f"  [BUY PLAN] Placing order at live bid ~ {planning_to_buy}¢")

                    # ── Pre-order entry for elevated bid ranges (70–74¢ and ≥75¢) ──
                    # Phase 1 : poll until bid falls to the discounted target price.
                    # Phase 2 : run 30-tick × 0.75s scan; require BUY signal + BTC.
                    # Deadline : stop waiting 300s before the 15-min market closes
                    #            (KXBTC15M contract duration = 900s → deadline = 600s
                    #             after market open).
                    if 78 > planning_to_buy > 73 or planning_to_buy >= 78:
                        if 78 > planning_to_buy > 73:
                            _target_cents = planning_to_buy - 5    # wait for -5¢ drop
                            _order_offset = 5
                        else:                                        # planning_to_buy >= 75
                            _target_cents = planning_to_buy - 11   # wait for -11¢ drop
                            _order_offset = 10

                        _MARKET_DURATION_S = 800        # 15-min binary contract
                        _WAIT_DEADLINE_S   = _MARKET_DURATION_S - 300  # 600s after open
                      # ── PRICE is above 70 cents : wait for bid to fall  and reenter ──
                        # ── Phase 1: wait for bid to fall to target ─────────────
                        _bid_fallen = False
                        print(f"  [PRE-BUY] Phase 1 — waiting for bid ≤ {_target_cents}¢  "
                              f"(deadline: {_WAIT_DEADLINE_S}s after market open) …")
                        while True:
                            _age = (_utc_now() - market_opened).total_seconds()
                            if _age >= _WAIT_DEADLINE_S:
                                print(f"  [PRE-BUY] ⏰ Deadline reached ({_age:.0f}s) — "
                                      f"bid never fell to {_target_cents}¢. Skipping trade.")
                                break

                            _live = await _bid_price(c, ticker, direction)
                            if _live is not None:
                                _live_cents = int(round(_live * 100))
                                if _live_cents <= _target_cents:
                                    print(f"  [PRE-BUY] ✓ Bid fell to {_live_cents}¢ "
                                          f"≤ {_target_cents}¢ (age={_age:.0f}s) "
                                          f"— running confirmation scan …")
                                    _bid_fallen = True
                                    break
                                print(f"  [PRE-BUY] {direction} bid={_live_cents}¢  "
                                      f"target≤{_target_cents}¢  age={_age:.0f}s — waiting …")
                            await asyncio.sleep(2)

                        if not _bid_fallen:
                            resp = None
                        else:
                            # ── Phase 2: 20-tick × 0.75s confirmation scan ───
                            _pre_buf: deque[float] = deque(maxlen=20)
                            print(f"  [PRE-BUY] Phase 2 — confirmation scan for {direction}"
                                  f"20 ticks × 0.75s …")
                            for _ in range(20):
                                _pf = asyncio.create_task(_bid_price(c, ticker, direction))
                                _pt = asyncio.create_task(asyncio.sleep(0.50))
                                _pp = await _pf
                                await _pt
                                if _pp is not None:
                                    _pre_buf.append(_pp)

                            _pre_sig    = compute_signal(_pre_buf) if len(_pre_buf) >= 20 else "hold"
                            _pre_btc    = btc.latestBtcVidyaSignal() if btc else "hold"
                            _pre_btc_ok = (
                                (direction == "yes" and _pre_btc == "buy") or
                                (direction == "no"  and _pre_btc == "sell")
                            )
                            print(f"  [PRE-BUY] sig={_pre_sig.upper()}  "
                                  f"BTC={_pre_btc.upper()}  "
                                  f"aligned={'Y' if _pre_btc_ok else 'N'}  "
                                  f"n={len(_pre_buf)}")

                            if _pre_sig != "buy" or not _pre_btc_ok:
                                print(f"  [PRE-BUY] Signal/BTC not aligned — skipping order.")
                                resp = None
                            else:
                                resp = await place_buy(c, ticker, direction,
                                                       buy_at_cents=(planning_to_buy - _order_offset),
                                                       contracts=_buy_contracts)
                    else:
                        # bid ≤ 69¢ — low enough, place directly without extra wait
                        resp = await place_buy(c, ticker, direction, contracts=_buy_contracts)
                if resp is None:
                    await asyncio.sleep(5)
                    continue

                odata = resp.get("order", {})

                # ── STEP 6: wait fill → TP/SL calc → TP sell ─────────────────
                filled = await await_fill(c, ticker, timeout=120)
                if not filled:
                    await cancel_all(c)
                    await asyncio.sleep(3)
                    continue

                btc_spot_at_buy = btc.last_price

                avg_cents = float(odata.get(
                    f"{direction}_price", (planning_to_buy+3)))
                cost_str  = odata.get("taker_fill_cost_dollars", "0")
                fee_str   = odata.get("taker_fees_dollars", "0")
                fill_cost = round(float(cost_str) + float(fee_str), 4)
                if fill_cost < 0.5:
                    fill_cost = round(((planning_to_buy-4) / 100) * _buy_contracts, 4)
                entry_total = fill_cost

                avg_cents = int(round(float(fill_cost / _buy_contracts), 2) * 100)

                tp_cents, sl_total = _tp_sl(avg_cents, _buy_contracts)

                print(f"  Entry: {_buy_contracts} × {avg_cents:.0f}¢ = "
                      f"${entry_total:.2f}  |  TP {tp_cents}¢  |  "
                      f"SL ${sl_total:.2f}")

                pos = await position_for(c, ticker)
                real_contracts = pos["contracts"] if (pos and pos["contracts"] > 0) else _buy_contracts
                ordered_direction = direction
                if not DO_YOU_HAVE_STOP_SELL:
                    # ── NO STOP/SELL MODE ────────────────────────────────────
                    # After a buy fill, run a passive 15s-tick monitor until the
                    # Kalshi 15-min window is about to close.  Each tick computes:
                    #
                    #   V2: live BTC vs strike (±$7 dead band)
                    #         live > strike+7 → "yes"
                    #         live < strike-7 → "no"
                    #         else            → abstain
                    #
                    #   V3: btc.btcSignalWithStrength() — STRONG variants only
                    #         "strong_buy"  → "yes"
                    #         "strong_sell" → "no"
                    #         anything else → mirrors ordered_direction
                    #                         (silences abstain in tally)
                    #
                    # Two independent SELL triggers fire on each tick.  The
                    # first to match wins (we break after placing the sell):
                    #
                    #   TRIGGER A — V3 TRANSITION (preferred, runs first):
                    #     A strong-signal flip between two consecutive ticks
                    #     (e.g. strong_buy → strong_sell, or vice versa) is
                    #     treated as a regime change.  We cancel resting
                    #     orders and place a SELL on our held side:
                    #       • if latest live bid > avg_cents → sell @ bid
                    #         (escape near break-even / small profit)
                    #       • else → sell @ (avg_cents − 15)¢ (controlled loss)
                    #     prev_v3_strong is tracked across ticks; only
                    #     strong-to-strong transitions count (a hold/
                    #     mirrored tick does NOT update prev_v3_strong,
                    #     so we keep watching for the next real flip).
                    #
                    #   TRIGGER B — V2 & V3 STABLE OPPOSITION:
                    #     V2 (±$7) and V3 (strong) both vote the SAME side
                    #     and that side is OPPOSITE to ordered_direction
                    #     → cut-loss SELL @ (avg_cents − 10)¢.
                    #
                    # Aligned / split votes / no transition → print only,
                    # keep watching.
                    NO_STOP_MON_INTERVAL_S = 15
                    NO_STOP_MON_MAX_AGE_S  = 870   # 15-min cycle − 30s safety
                    NO_STOP_BUFFER         = 7.0
                    NO_STOP_CUT_BELOW      = 20    # cents below avg (Trigger B)
                    NO_STOP_TRANS_BELOW    = 15    # cents below avg (Trigger A fallback)
                    _cut_price = max(1, int(round(avg_cents - NO_STOP_CUT_BELOW)))
                    _trans_fallback_price = max(1, int(round(avg_cents - NO_STOP_TRANS_BELOW)))

                    print(f"  [NO-STOP] DO_YOU_HAVE_STOP_SELL=False — "
                          f"15s monitor.  "
                          f"Trigger A: V3 flip → SELL @ max(bid, "
                          f"{_trans_fallback_price}¢).  "
                          f"Trigger B: V2 & V3 oppose "
                          f"{ordered_direction.upper()} → SELL @ "
                          f"{_cut_price}¢.")

                    _cut_loss_placed     = False   # any sell trigger fired
                    prev_v3_strong: str | None = None   # tracks last STRONG V3 (yes/no)
                    while True:
                        _age = (_utc_now() - market_opened).total_seconds()
                        if _age >= NO_STOP_MON_MAX_AGE_S:
                            print(f"  [NO-STOP MON] Age {_age:.0f}s >= "
                                  f"{NO_STOP_MON_MAX_AGE_S}s — stopping monitor.")
                            break

                        # V2 — live BTC vs strike ±$15
                        _live = btc.last_price if btc else None
                        v2: str | None = None
                        if _live is not None and btc_to_beat is not None:
                            if _live > btc_to_beat + NO_STOP_BUFFER:
                                v2 = "yes"
                            elif _live < btc_to_beat - NO_STOP_BUFFER:
                                v2 = "no"

                        # V3 — STRONG signals only
                        _strong = btc.btcSignalWithStrength() if btc else "hold"
                        v3: str | None = None
                        if _strong == "strong_buy":
                            v3 = "yes"
                        elif _strong == "strong_sell":
                            v3 = "no"
                        else:
                            v3 = ordered_direction

                        # Map this tick's V3 strong signal into yes/no for
                        # transition tracking (Trigger A).  Non-strong ticks
                        # leave the tracker untouched so the next true flip
                        # still registers as a transition.
                        cur_v3_strong: str | None = None
                        if _strong == "strong_buy":
                            cur_v3_strong = "yes"
                        elif _strong == "strong_sell":
                            cur_v3_strong = "no"

                        _v2_tag = (v2 or "abstain").upper()
                        _v3_tag = (v3 or "abstain").upper()
                        _live_s = f"${_live:,.2f}" if _live is not None else "N/A"
                        _prev_tag = (prev_v3_strong or "—").upper()
                        print(f"  [NO-STOP MON age={_age:.0f}s] "
                              f"V2 live={_live_s} vs strike "
                              f"${btc_to_beat:,.2f}±{NO_STOP_BUFFER:.0f} → {_v2_tag}  |  "
                              f"V3 strong={_strong.upper()} → {_v3_tag}  "
                              f"(prev={_prev_tag})  |  "
                              f"ordered={ordered_direction.upper()}")

                        # ── TRIGGER C: high-bid profit lock + flipped lotto ──
                        # When the position is deeply in profit (live bid
                        # > 92¢) AND there is still meaningful time left
                        # in the 15-min cycle (> 300s remaining, i.e.
                        # age < 600s), fire-sell to lock the gain and
                        # plant a LOTTO_CONTRACTS buy on the opposite
                        # side at 5¢ for an asymmetric "free option" on a
                        # reversal.  Checked BEFORE A and B because a
                        # profitable exit always beats a cut-loss.
                        NO_STOP_C_TIME_REMAINING_S = 300   # min seconds left
                        NO_STOP_C_BID_CENTS        = 94    # min profit-bid (¢)
                        NO_STOP_C_FLIP_BUY_CENTS   = 4     # lotto buy price
                        NO_STOP_C_MARKET_LEN_S     = 900   # 15-min Kalshi cycle
                        _time_remaining = max(0, NO_STOP_C_MARKET_LEN_S - _age)
                        if _time_remaining > NO_STOP_C_TIME_REMAINING_S:
                            _ord_bid_d   = await _bid_price(c, ticker, ordered_direction)
                            _ord_bid_c   = (int(round(_ord_bid_d * 100))
                                            if _ord_bid_d is not None else None)
                            if (_ord_bid_c is not None
                                    and _ord_bid_c > NO_STOP_C_BID_CENTS):
                                _flip_dir = flip(ordered_direction)
                                print(f"  [NO-STOP MON] TRIGGER C — live bid "
                                      f"{_ord_bid_c}¢ > {NO_STOP_C_BID_CENTS}¢ "
                                      f"with {_time_remaining:.0f}s remaining. "
                                      f"Locking profit + lotto buy on flip "
                                      f"({_flip_dir.upper()}).")
                                # 1. cancel any resting orders
                                try:
                                    await cancel_all(c)
                                except Exception as e:
                                    print(f"  [NO-STOP MON] cancel_all "
                                          f"failed: {e}")
                                # 2. fire-sell the current position
                                try:
                                    await _fire_sale(
                                        c, ticker, ordered_direction,
                                        real_contracts,
                                    )
                                    await asyncio.sleep(2)
                                except Exception as e:
                                    print(f"  [NO-STOP MON] fire-sale "
                                          f"failed: {e}")
                                # 3. plant the flipped lotto buy at 5¢
                                try:
                                    _lotto_order = _mk_order(
                                        ticker, "buy", _flip_dir,
                                        LOTTO_CONTRACTS,
                                        NO_STOP_C_FLIP_BUY_CENTS,
                                    )
                                    _dry = "[DRY] " if DRY_RUN else ""
                                    print(f"  {_dry}[NO-STOP MON] Trigger C "
                                          f"lotto buy {LOTTO_CONTRACTS} × "
                                          f"{_flip_dir.upper()} @ "
                                          f"{NO_STOP_C_FLIP_BUY_CENTS}¢: "
                                          f"{_lotto_order}")
                                    if not DRY_RUN:
                                        await c.req(
                                            "POST", ORDER_CREATE_PATH,
                                            body=_lotto_order,
                                        )
                                except Exception as e:
                                    print(f"  [NO-STOP MON] Trigger C lotto "
                                          f"buy failed: {e}")
                                # 3b. Wait for the lotto buy to fill, then
                                # place a take-profit SELL on the FLIPPED
                                # side for HALF of LOTTO_CONTRACTS @ 12¢.
                                # If LOTTO_CONTRACTS is odd, ceil/floor
                                # both round to int division (10 -> 5,
                                # 11 -> 5).  Floors at 1 so an odd 1-
                                # contract lotto still emits a TP order.
                                #
                                # await_fill() polls resting_orders for the
                                # ticker; it returns True once BOTH the
                                # fire-sale and the lotto buy have cleared
                                # the book.  The fire-sale @5c fills near-
                                # instantly against the >92c bid; the lotto
                                # buy @5c may take seconds-to-minutes (or
                                # never fill if no one sells that low).  If
                                # await_fill times out we skip the TP and
                                # log the trade as usual.
                                NO_STOP_C_LOTTO_FILL_TIMEOUT_S = 180
                                NO_STOP_C_LOTTO_TP_CENTS       = 9
                                _lotto_tp_count = max(1, LOTTO_CONTRACTS // 2)
                                if DRY_RUN:
                                    print(f"  [DRY] [NO-STOP MON] Trigger C — "
                                          f"would await lotto-buy fill then "
                                          f"place TP SELL "
                                          f"{_lotto_tp_count}/{LOTTO_CONTRACTS}"
                                          f" × {_flip_dir.upper()} @ "
                                          f"{NO_STOP_C_LOTTO_TP_CENTS}¢")
                                else:
                                    print(f"  [NO-STOP MON] Trigger C — "
                                          f"waiting up to "
                                          f"{NO_STOP_C_LOTTO_FILL_TIMEOUT_S}s "
                                          f"for lotto buy to fill …")
                                    try:
                                        _lotto_filled = await await_fill(
                                            c, ticker,
                                            timeout=NO_STOP_C_LOTTO_FILL_TIMEOUT_S,
                                        )
                                    except Exception as e:
                                        print(f"  [NO-STOP MON] Trigger C "
                                              f"await_fill failed: {e}")
                                        _lotto_filled = False

                                    if _lotto_filled:
                                        try:
                                            # never-sell-naked (builds its own
                                            # order, so it needs the guard here)
                                            _lt_n = await sellable_contracts(
                                                c, ticker, _flip_dir,
                                                _lotto_tp_count,
                                                tag="NO-STOP MON",
                                            )
                                            if _lt_n <= 0:
                                                raise _SkipSell()
                                            _lotto_tp_order = _mk_order(
                                                ticker, "sell", _flip_dir,
                                                _lt_n,
                                                NO_STOP_C_LOTTO_TP_CENTS,
                                            )
                                            print(f"  [NO-STOP MON] Trigger C "
                                                  f"lotto TP "
                                                  f"{_lotto_tp_count}/"
                                                  f"{LOTTO_CONTRACTS} × "
                                                  f"{_flip_dir.upper()} @ "
                                                  f"{NO_STOP_C_LOTTO_TP_CENTS}¢"
                                                  f": {_lotto_tp_order}")
                                            await c.req(
                                                "POST", ORDER_CREATE_PATH,
                                                body=_lotto_tp_order,
                                            )
                                        except Exception as e:
                                            print(f"  [NO-STOP MON] Trigger C "
                                                  f"lotto TP failed: {e}")
                                    else:
                                        print(f"  [NO-STOP MON] Trigger C — "
                                              f"lotto buy did not fill within "
                                              f"{NO_STOP_C_LOTTO_FILL_TIMEOUT_S}"
                                              f"s; skipping TP placement.")
                                # 4. CSV log row (Trigger C).  Uses live
                                # bid as the expected exit price (fire-sale
                                # at 5¢ limit fills against the resting
                                # bid, which is what the sell will hit).
                                try:
                                    _exit_total_C = (_ord_bid_c / 100.0) * real_contracts
                                    _pv_after_C   = await portfolio_balance(c)
                                    _, _adp_C     = await determine_direction(c)
                                    log_trade(
                                        ticker=ticker, mode=mode,
                                        direction=ordered_direction,
                                        contracts=real_contracts,
                                        entry=avg_cents,
                                        exit_=_exit_total_C,
                                        pnl=_exit_total_C - entry_total,
                                        result="NO_SL_TRIG_C_HIGH_BID",
                                        pv=_pv_after_C,
                                        btc_to_beat=btc_to_beat,
                                        btc_spot_at_buy=btc_spot_at_buy,
                                        btc_spot_at_sell=(btc.last_price if btc else None),
                                        actual_direction_previous=_adp_C,
                                    )
                                except Exception as e:
                                    print(f"  [NO-STOP MON] Trigger C CSV "
                                          f"log failed: {e}")
                                _cut_loss_placed = True
                                break

                        # ── TRIGGER A: V3 strong-signal transition ───────────
                        # Strong-to-strong flip across consecutive ticks
                        # (yes→no or no→yes).  Sell at the live bid when it
                        # beats our entry cost, otherwise at (avg − 15)¢.
                        if (prev_v3_strong is not None
                                and cur_v3_strong is not None
                                and cur_v3_strong != prev_v3_strong):
                            _bid_dollars = await _bid_price(c, ticker, ordered_direction)
                            _bid_cents   = (int(round(_bid_dollars * 100))
                                            if _bid_dollars is not None else None)
                            if _bid_cents is not None and _bid_cents > avg_cents:
                                _trans_price = _bid_cents
                                _trans_src   = (f"live bid {_bid_cents}¢ "
                                                f"(> avg {avg_cents}¢)")
                            else:
                                _trans_price = _trans_fallback_price
                                _bid_show    = (f"{_bid_cents}¢" if _bid_cents is not None
                                                else "N/A")
                                _trans_src   = (f"avg-{NO_STOP_TRANS_BELOW} = "
                                                f"{_trans_price}¢ (bid={_bid_show})")

                            print(f"  [NO-STOP MON] V3 TRANSITION "
                                  f"{prev_v3_strong.upper()} → {cur_v3_strong.upper()} — "
                                  f"cancelling resting orders, then SELL "
                                  f"{real_contracts} × {ordered_direction.upper()} "
                                  f"@ {_trans_src}")
                            try:
                                await cancel_all(c)
                            except Exception as e:
                                print(f"  [NO-STOP MON] cancel_all failed: {e}")
                            try:
                                # never-sell-naked: cancel_all above may have
                                # raced a TP fill, leaving nothing to sell.
                                _tr_n = real_contracts if DRY_RUN else (
                                    await sellable_contracts(
                                        c, ticker, ordered_direction,
                                        real_contracts, tag="NO-STOP MON"))
                                if _tr_n <= 0:
                                    raise _SkipSell()
                                _trans_order = _mk_order(
                                    ticker, "sell", ordered_direction,
                                    _tr_n, 15,
                                )
                                _dry = "[DRY] " if DRY_RUN else ""
                                print(f"  {_dry}[NO-STOP MON] "
                                      f"transition sell order: {_trans_order}")
                                if not DRY_RUN:
                                    await c.req(
                                        "POST", ORDER_CREATE_PATH,
                                        body=_trans_order,
                                    )
                            except Exception as e:
                                print(f"  [NO-STOP MON] transition sell "
                                      f"failed: {e}")
                            # Update tracker before breaking so the final
                            # state reflects the firing tick.
                            prev_v3_strong   = cur_v3_strong
                            _cut_loss_placed = True

                            # ── CSV log row (Trigger A) ─────────────────
                            # Recorded at order-placement time using the
                            # LIMIT price as the expected exit.  Actual fill
                            # may differ if the sell rests/partially fills.
                            try:
                                _exit_total_A = (_trans_price / 100.0) * real_contracts
                                _pv_after_A   = await portfolio_balance(c)
                                _, _adp_A     = await determine_direction(c)
                                log_trade(
                                    ticker=ticker, mode=mode,
                                    direction=ordered_direction,
                                    contracts=real_contracts,
                                    entry=avg_cents,
                                    exit_=_exit_total_A,
                                    pnl=_exit_total_A - entry_total,
                                    result="NO_SL_TRIG_A_V3_FLIP",
                                    pv=_pv_after_A,
                                    btc_to_beat=btc_to_beat,
                                    btc_spot_at_buy=btc_spot_at_buy,
                                    btc_spot_at_sell=(btc.last_price if btc else None),
                                    actual_direction_previous=_adp_A,
                                )
                            except Exception as e:
                                print(f"  [NO-STOP MON] Trigger A CSV "
                                      f"log failed: {e}")
                            break

                        # Update the V3 strong tracker only on strong ticks,
                        # so non-strong (hold / abstain) gaps don't reset
                        # our memory of the most recent strong direction.
                        if cur_v3_strong is not None:
                            prev_v3_strong = cur_v3_strong

                        # ── TRIGGER B: V2 & V3 both oppose ordered ───────────
                        # Both vote the same non-abstain way?
                        if v2 is not None and v2 == v3:
                            if v2 == ordered_direction:
                                # Aligned with our order — no action.
                                pass
                            else:
                                # Both vote AGAINST our order — cut loss.
                                print(f"  [NO-STOP MON] V2 & V3 both say "
                                      f"{v2.upper()} but we ordered "
                                      f"{ordered_direction.upper()} — "
                                      f"placing cut-loss SELL "
                                      f"{real_contracts} × {ordered_direction.upper()} "
                                      f"@ {_cut_price}¢")
                                try:
                                    # never-sell-naked
                                    _ct_n = real_contracts if DRY_RUN else (
                                        await sellable_contracts(
                                            c, ticker, ordered_direction,
                                            real_contracts, tag="NO-STOP MON"))
                                    if _ct_n <= 0:
                                        raise _SkipSell()
                                    _cut_order = _mk_order(
                                        ticker, "sell", ordered_direction,
                                        _ct_n, 20,
                                    )
                                    _dry = "[DRY] " if DRY_RUN else ""
                                    print(f"  {_dry}[NO-STOP MON] "
                                          f"cut-loss order: {_cut_order}")
                                    if not DRY_RUN:
                                        await c.req(
                                            "POST", ORDER_CREATE_PATH,
                                            body=_cut_order,
                                        )
                                except Exception as e:
                                    print(f"  [NO-STOP MON] Cut-loss "
                                          f"sell failed: {e}")
                                _cut_loss_placed = True

                                # ── CSV log row (Trigger B) ─────────────
                                # Recorded at order-placement time using the
                                # cut LIMIT price as the expected exit.
                                # Actual fill may differ.
                                try:
                                    _exit_total_B = (_cut_price / 100.0) * real_contracts
                                    _pv_after_B   = await portfolio_balance(c)
                                    _, _adp_B     = await determine_direction(c)
                                    log_trade(
                                        ticker=ticker, mode=mode,
                                        direction=ordered_direction,
                                        contracts=real_contracts,
                                        entry=avg_cents,
                                        exit_=_exit_total_B,
                                        pnl=_exit_total_B - entry_total,
                                        result="NO_SL_TRIG_B_V2V3_OPP",
                                        pv=_pv_after_B,
                                        btc_to_beat=btc_to_beat,
                                        btc_spot_at_buy=btc_spot_at_buy,
                                        btc_spot_at_sell=(btc.last_price if btc else None),
                                        actual_direction_previous=_adp_B,
                                    )
                                except Exception as e:
                                    print(f"  [NO-STOP MON] Trigger B CSV "
                                          f"log failed: {e}")
                                break

                        await asyncio.sleep(NO_STOP_MON_INTERVAL_S)

                    # ── CSV log: only for the age-timeout path ───────────
                    # Triggers A and B already wrote their own rows at
                    # order-placement time, so here we ONLY log when the
                    # monitor exited via the 870s age cap (no sell placed).
                    if not _cut_loss_placed:
                        pv_after = await portfolio_balance(c)
                        _, actual_direction_previous1 = await determine_direction(c)
                        log_trade(
                            ticker=ticker, mode=mode, direction=ordered_direction,
                            contracts=_buy_contracts,
                            entry=avg_cents,
                            exit_=0.0, pnl=0.0,
                            result="NO_SL_TRADE",
                            pv=pv_after,
                            btc_to_beat=btc_to_beat,
                            btc_spot_at_buy=btc_spot_at_buy,
                            btc_spot_at_sell=(btc.last_price if btc else None),
                            actual_direction_previous=actual_direction_previous1,
                        )
                    break  # skip remaining trade slots; outer loop picks next market

                await place_tp_sell(c, ticker, direction, real_contracts, tp_cents)

                # ── STEP 7: monitor ───────────────────────────────────────────
                exit_reason, min_bid, max_bid = await monitor_trade(
                    c, ticker, direction,
                    entry_total     = entry_total,
                    entry_avg_cents = avg_cents,
                    tp_cents        = tp_cents,
                    sl_total        = sl_total,
                    buy_contracts   = _buy_contracts,
                    btc             = btc,
                )
                btc_spot_at_sell = btc.last_price

                # ── STEP 8: log to CSV ────────────────────────────────────────
                pv_after = await portfolio_balance(c)

                if exit_reason == "TAKE_PROFIT":
                    exit_price = (tp_cents / 100) * real_contracts
                elif exit_reason in ("STOP_LOSS", "SELL_SIGNAL"):
                    exit_price = (FIRE_SALE_CENTS / 100) * real_contracts
                else:
                    exit_price = 0.0

                pnl = exit_price - entry_total

                # ── Compute MAX_LOSS_PCT / MAX_PROFIT_PCT for tuning .env ─────
                # MAX_LOSS_PCT  (TP wins only):  drawdown trough vs entry
                # MAX_PROFIT_PCT (SL/SELL_SIGNAL): peak gain vs entry
                max_loss_pct: float | None = None
                max_profit_pct: float | None = None
                if avg_cents > 0:
                    if exit_reason == "TAKE_PROFIT" and min_bid is not None:
                        min_bid_cents = min_bid * 100
                        max_loss_pct  = (avg_cents - min_bid_cents) / avg_cents * 100
                    elif exit_reason in ("STOP_LOSS", "SELL_SIGNAL") and max_bid is not None:
                        max_bid_cents  = max_bid * 100
                        max_profit_pct = abs(avg_cents - max_bid_cents) / avg_cents * 100

                log_trade(
                    ticker=ticker, mode=mode, direction=direction,
                    contracts=real_contracts,
                    entry=avg_cents, exit_=exit_price,
                    pnl=pnl, result=exit_reason, pv=pv_after,
                    btc_to_beat=btc_to_beat,
                    btc_spot_at_buy=btc_spot_at_buy,
                    btc_spot_at_sell=btc_spot_at_sell,
                    max_loss_pct=max_loss_pct,
                    max_profit_pct=max_profit_pct,
                    actual_direction_previous=actual_direction_previous,
                )

                extras = ""
                if max_loss_pct is not None:
                    extras = f"  worst drawdown={max_loss_pct:.1f}%"
                elif max_profit_pct is not None:
                    extras = f"  best gain={max_profit_pct:.1f}%"
                print(f"  [LOG] {exit_reason}  PnL=${pnl:+.2f}  "
                      f"Portfolio=${pv_after:.2f}{extras}")

                # ── Profit-ratchet the MIN-PV floor on a WIN (ratchets up only)
                if pnl > 0 and _floor_buffer is not None:
                    _new_floor = max(DO_NOT_BUY_IF_PORTFOLIO_BELOW,
                                     int(round(pv_after - _floor_buffer)))
                    if _new_floor > DO_NOT_BUY_IF_PORTFOLIO_BELOW:
                        print(f"  [MIN-PV] win (+${pnl:.2f}) — floor "
                              f"${DO_NOT_BUY_IF_PORTFOLIO_BELOW} → ${_new_floor} "
                              f"(pv ${pv_after:.2f} − buffer ${_floor_buffer:.2f})")
                        DO_NOT_BUY_IF_PORTFOLIO_BELOW = _new_floor

                await asyncio.sleep(8)

            print(f"\n[BOT] Done with {ticker}. Next market …\n")

    except KeyboardInterrupt:
        print("\n[BOT] Ctrl-C received. Cancelling orders …")
        await cancel_all(c)
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        await btc.stop()
        await c.close()
        print("[BOT] Session closed.")
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        _log_fh.close()


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  ENTRY POINT                                                             ║
# ╚════════════════════════════════════════════════════════════════════════════╝
if __name__ == "__main__":
    asyncio.run(run())