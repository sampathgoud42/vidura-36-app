#!/usr/bin/env python3
"""
bot_kalshi_btc60_burst.py — Kalshi BTC HOURLY bot (research-signal edition)
==========================================================================
Strategy: btc60_bot_trsategy.md (this folder).

SIGNAL SOURCE (owner change 2026-07-13): the bot's own S1/S2/S3 committee
and its 48h/timebox revalidation are REMOVED.  The ONLY input is now the
super_research/btc_research playbook, delivered by the companion provider
bot (btc60_research_signal_bot.py) through a JSON handoff file:

    btc60_research_signal.json   {direction, signal, signal_price,
                                  bar_epoch, acc_tp_before_sl_pct, ...}

Each 5-minute research signal is consumed once (keyed by bar_epoch).  The
provider already applies the research session-window / noise gates, so
this bot no longer time-boxes by UTC hour — it applies only its own
EXECUTION gates and trades the picked strike.

EXECUTION (unchanged from the committee edition):
  * strike of the current KXBTCD hourly event whose signal-side bid is
    closest to 50c within $500 of the research signal price (YES=LONG,
    NO=SHORT), maker entry at bid, only 30-70c, cancel if unfilled 3 min.
  * TP  = entry + 20c (resting maker sell)
  * SL  = entry − 15c (taker flatten)
  * TIME-STOP = 30 min after entry
  * hard flatten ≥ 5 min before market close; one position at a time.

BANKROLL (real-money rules, per account owner 2026-07-10):
  * seeded at $100 on FIRST launch (btc60_burst_state.json)
  * each trade risks at most 25% of the CURRENT bankroll
  * daily reset at 08:00 AMERICA/CHICAGO: if the day ended in profit,
    bankroll = day_start + 50% of profit (other 50% is "banked" and
    never risked again); if loss, bankroll carries unchanged.

Secrets: same as fable5 — btc.env names customer_folder/default_customer;
that folder's .env + .pem are the only credential source.
DRY_RUN_MODE=TRUE (default) trades a paper book; the launcher .bat sets
FALSE for live.
"""
from __future__ import annotations

# ── trading parameters ───────────────────────────────────────────────────────
BANKROLL_SEED      = float(__import__("os").getenv("BTC_BANKROLL", "100") or 100)
                             # $ first-launch bankroll (desk-injected)
MAX_PV_PCT         = 25.0    # max % of bankroll per trade (owner's spec)
FIXED_CONTRACTS    = int(__import__("os").getenv("KALSHI_CONTRACTS", "1") or 1)
                             # common bot contract (user 08/03): FIXED size on
                             # every buy, desk-injected; the MAX_PV_PCT
                             # fallback sizing is removed.
# Stop once the bank (risked + banked) has grown by this percent on the seed.
BURST_TARGET_PCT   = float(__import__("os").getenv("BTC60_TARGET_PCT", "0") or 0)
# ... or SHRUNK by this percent: the capital-protection mirror (user 08/03).
BURST_BANK_SL_PCT  = float(__import__("os").getenv("BTC60_BANK_SL_PCT", "0") or 0)

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

TP_CENTS           = 20      # take-profit offset
# Per-trade profit target as a PERCENT over entry (user 07/30). When set it
# replaces the flat +20c offset, which is a very different trade from a 30c
# entry than from a 70c one: tp = entry x (1 + pct/100).
TP_PCT_OVERRIDE    = float(__import__("os").getenv("BTC60_TP_PCT", "0") or 0)
SL_CENTS           = 15      # stop-loss offset
# Per-trade stop override, mirroring TP_PCT_OVERRIDE below: a percent BELOW
# entry rather than a fixed 15c, so the stop scales with the entry price the
# way the user's number implies. Unset (0) keeps the fixed offset.
SL_PCT_OVERRIDE    = float(__import__("os").getenv("BTC60_SL_PCT", "0") or 0)
TIME_STOP_MIN      = 30      # signal horizon
ENTRY_BID_LO       = 30      # entry band widened 40-65 -> 30-70 (owner,
ENTRY_BID_HI       = 70      # 2026-07-12, after repeated ATM price-gate misses)
ENTRY_BID_SWEET    = 50      # strike selection targets the bid closest to
                             # this (owner 2026-07-12: scan adjacent strikes
                             # for a 40-60c bid instead of strict ATM)
MAX_STRIKE_DIST    = 500     # never reach more than $500 from spot
RESTART_EXIT_CODE  = 42      # bot exits with this after the 08:00 reset;
                             # the launcher .bat sees it and relaunches
ENTRY_FILL_WAIT_S  = 180     # cancel unfilled maker buy after 3 min
LAST_ENTRY_MINUTE  = 25      # entry minute-of-hour cutoff (time-stop must fit)
FLATTEN_BEFORE_MIN = 5       # hard-flatten deadline before close
# One trade per market by default (user 07/30) — an hourly event IS the
# market here. Shared name with the other BTC engines.
MAX_TRADES_PER_HOUR = int(__import__("os").getenv("MAX_TRADES_PER_MARKET", "1"))
MIN_BANKROLL_HALT  = 25.0
DAILY_LOSS_HALT_PCT = 10.0   # stop for the day at −10% of day-start
RESET_HOUR_LOCAL   = 8       # daily bankroll reset, America/Chicago
SERIES             = "KXBTCD"
POLL_S             = 10

# research-signal handoff (written by btc60_research_signal_bot.py)
HANDOFF_NAME       = "btc60_research_signal.json"
HANDOFF_MAX_AGE_S  = 240     # ignore a signal whose bar is older than this
                             # (a stale handoff from a previous session)

import asyncio
import base64
import csv
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import aiohttp
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as _padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from dotenv import load_dotenv

_HERE = Path(__file__).resolve().parent          # .../kalshi/btc/btc60
_ROOT = _HERE.parent                             # .../kalshi/btc
_LOCAL = ZoneInfo("America/Chicago")

load_dotenv(_ROOT / "btc.env")                   # customer_folder / default_customer

# ── secrets from the customer folder (same scheme as fable5) ─────────────────
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
    sys.exit(f"[SECRETS] no .env in customer folder {_CUSTOMER_DIR}")

BASE_URI   = os.getenv("BASE_URI", "https://external-api.kalshi.com/trade-api/v2")
API_KEY_ID = os.getenv("KALSHI_API_KEY_ID", "")
DRY_RUN    = os.getenv("DRY_RUN_MODE", "TRUE").upper() == "TRUE"

def _resolve_pem() -> Path:
    raw = os.getenv("KALSHI_PRIVATE_KEY", "kalshi_private.pem")
    p = Path(raw)
    if p.is_absolute() and p.is_file():
        return p
    cand = _CUSTOMER_DIR / p.name
    if cand.is_file():
        return cand.resolve()
    pems = sorted(_CUSTOMER_DIR.glob("*.pem"))
    if pems:
        return pems[0].resolve()
    raise FileNotFoundError(f"no PEM in {_CUSTOMER_DIR}")

# ── files ────────────────────────────────────────────────────────────────────
_SUFFIX    = "_paper" if DRY_RUN else ""
CSV_FILE   = _HERE / f"btc60_burst_trade_history{_SUFFIX}.csv"
STATE_FILE = _HERE / f"btc60_burst_state{_SUFFIX}.json"
HANDOFF_FILE = _HERE / HANDOFF_NAME
LOG_FILE   = _HERE / f"btc60_burst_{datetime.now():%Y%m%d}.log"
LOCK_FILE  = _HERE / f"btc60_burst{_SUFFIX}.lock"

_CSV_COLS = ["timestamp", "event", "ticker", "signal", "side", "strike",
             "contracts", "entry_cents", "exit_cents", "exit_reason",
             "pnl_dollars", "bankroll_after", "banked_total", "spot_at_entry",
             "signal_acc", "utc_hour"]


class _Tee:
    def __init__(self, *streams): self._streams = streams
    def write(self, data):
        for s in self._streams:
            try: s.write(data)
            except Exception: pass
        self.flush()
    def flush(self):
        for s in self._streams:
            try: s.flush()
            except Exception: pass


def _utc_now() -> datetime: return datetime.now(timezone.utc)
def _ts_ms() -> str: return str(int(_utc_now().timestamp() * 1000))
def _log(tag: str, msg: str) -> None:
    # all log timestamps in CST/CDT (America/Chicago); internals stay UTC
    print(f"[{tag} {datetime.now(_LOCAL):%H:%M:%S} CST] {msg}")


# ══════════════════════════════════════════════════════════════════════════
#  RESEARCH-SIGNAL HANDOFF  (written by btc60_research_signal_bot.py)
#  This bot's ONLY signal input — the old S1/S2/S3 committee, the Coinbase
#  candle feed, and the 48h/timebox revalidation are all removed.
# ══════════════════════════════════════════════════════════════════════════
def read_handoff() -> dict | None:
    """Return the latest research signal payload, or None when there is no
    file / it can't be parsed.  Freshness + de-duplication are handled by
    the caller (via bar_epoch)."""
    try:
        if HANDOFF_FILE.is_file():
            return json.loads(HANDOFF_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        _log("SIG", f"handoff read failed: {e}")
    return None


# ══════════════════════════════════════════════════════════════════════════
#  BANKROLL  (seed $100, 25%/trade cap, 08:00 America/Chicago profit-skim)
# ══════════════════════════════════════════════════════════════════════════
class Bankroll:
    def __init__(self) -> None:
        self.bankroll = BANKROLL_SEED
        self.banked = 0.0                       # skimmed profit, never risked
        self.day_start = BANKROLL_SEED
        self.last_reset_date = ""               # local date of last 8AM reset
        self.n_trades = 0
        self.last_signal_bar = 0                # bar_epoch of last consumed signal
        self._load()

    def _load(self) -> None:
        # Fresh session on EVERY start (user 08/03): bankroll, banked profit
        # and day_start reset to the seed. last_signal_bar alone is RESTORED
        # — it is the stale-signal guard, and wiping it would re-trade a bar
        # this bot already consumed before the restart.
        try:
            if STATE_FILE.is_file():
                s = json.loads(STATE_FILE.read_text())
                self.last_signal_bar = int(s.get("last_signal_bar", 0))
                prev = float(s.get("bankroll", 0) or 0) + float(s.get("banked", 0) or 0)
                if prev:
                    _log("BANK", f"previous session equity ${prev:.2f} — "
                                 f"fresh session reseeds ${BANKROLL_SEED:.2f}")
            else:
                _log("BANK", f"FIRST LAUNCH — bankroll seeded ${BANKROLL_SEED:.2f}")
        except Exception as e:
            _log("BANK", f"state read failed ({e}) — using seed")
        self.bankroll = BANKROLL_SEED
        self.banked = 0.0
        self.day_start = BANKROLL_SEED
        self.n_trades = 0
        self.last_reset_date = datetime.now(_LOCAL).strftime("%Y-%m-%d")
        self._save()

    def _save(self) -> None:
        STATE_FILE.write_text(json.dumps({
            "bankroll": round(self.bankroll, 2),
            "banked": round(self.banked, 2),
            "day_start": round(self.day_start, 2),
            "last_reset_date": self.last_reset_date,
            "n_trades": self.n_trades,
            "last_signal_bar": self.last_signal_bar,
            "updated": _utc_now().isoformat()}, indent=2))

    def settle(self, pnl: float) -> None:
        self.bankroll += pnl
        self.n_trades += 1
        self._save()

    def set_last_signal_bar(self, bar_epoch: int) -> None:
        """Persist the last consumed research bar so a restart never
        re-trades the same signal."""
        self.last_signal_bar = int(bar_epoch)
        self._save()

    def maybe_daily_reset(self) -> bool:
        """At/after 08:00 America/Chicago, once per local day:
        profit day  -> bankroll = day_start + 50% of profit (rest banked)
        loss day    -> bankroll unchanged.  day_start := bankroll.
        Returns True when a reset was performed (caller restarts the bot)."""
        now = datetime.now(_LOCAL)
        today = now.strftime("%Y-%m-%d")
        if now.hour < RESET_HOUR_LOCAL or self.last_reset_date == today:
            return False
        pnl = self.bankroll - self.day_start
        if pnl > 0:
            skim = round(pnl / 2, 2)
            self.banked += skim
            self.bankroll = round(self.day_start + pnl - skim, 2)
            _log("BANK", f"08:00 reset: day pnl +${pnl:.2f} -> bankroll "
                         f"${self.bankroll:.2f}, banked +${skim:.2f} "
                         f"(total ${self.banked:.2f})")
        else:
            _log("BANK", f"08:00 reset: day pnl ${pnl:+.2f} (loss/flat) — "
                         f"bankroll stays ${self.bankroll:.2f}")
        self.day_start = self.bankroll
        self.last_reset_date = today
        self._save()
        return True

    def day_loss_pct(self) -> float:
        if self.day_start <= 0:
            return 0.0
        return max(0.0, (self.day_start - self.bankroll) / self.day_start * 100)


# ══════════════════════════════════════════════════════════════════════════
#  SINGLE-INSTANCE LOCK  (verbatim from fable5 — it caught a real incident)
# ══════════════════════════════════════════════════════════════════════════
def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5).stdout
            return str(pid) in out
        except Exception:
            return True
    try:
        os.kill(pid, 0); return True
    except ProcessLookupError:
        return False
    except Exception:
        return True


def _acquire_lock() -> None:
    if LOCK_FILE.is_file():
        raw = LOCK_FILE.read_text().strip()
        old = int(raw) if raw.isdigit() else None
        if old and _pid_alive(old):
            sys.exit(f"[LOCK] another instance running (PID {old})")
        print(f"[LOCK] stale lock (PID {old}) — taking over")
    LOCK_FILE.write_text(str(os.getpid()))


def _release_lock() -> None:
    try:
        if LOCK_FILE.is_file() and LOCK_FILE.read_text().strip() == str(os.getpid()):
            LOCK_FILE.unlink()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════
#  KALSHI CLIENT + ORDER HELPERS  (lifted from fable5, unchanged behavior)
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
        return {"Content-Type": "application/json",
                "KALSHI-ACCESS-KEY": API_KEY_ID,
                "KALSHI-ACCESS-TIMESTAMP": ts,
                "KALSHI-ACCESS-SIGNATURE": self._sign(
                    ts, method.upper(), f"/trade-api/v2{path}"),
                "Cache-Control": "no-cache"}

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
        raise RuntimeError(f"{method} {path} failed after {retries}: {last}")


ORDER_CREATE_PATH = "/portfolio/events/orders"


def _mk_order(ticker: str, action: str, side: str, count: int,
              price_cents: int) -> dict:
    if side == "yes":
        v2_side, yes_cents = ("bid" if action == "buy" else "ask"), price_cents
    else:
        v2_side, yes_cents = ("ask" if action == "buy" else "bid"), 100 - price_cents
    return {"ticker": ticker, "side": v2_side, "count": f"{int(count):.2f}",
            "price": f"{yes_cents / 100.0:.4f}",
            "time_in_force": "good_till_canceled",
            "self_trade_prevention_type": "taker_at_cross",
            "client_order_id": str(uuid.uuid4())}


class PaperBook:
    def __init__(self) -> None:
        self.position: dict | None = None
        self.resting: list[dict] = []

PAPER = PaperBook()


async def account_cash(c: KalshiClient) -> float:
    if DRY_RUN:
        return 1e9
    d = await c.req("GET", "/portfolio/balance")
    return d.get("balance", 0) / 100.0


async def position_for(c: KalshiClient, ticker: str) -> tuple[int, str | None]:
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
        if not tk.startswith(f"{event}-") or fp == 0:
            continue
        side = "yes" if fp > 0 else "no"
        nn = abs(int(fp))
        avg = None
        try:
            exp = float(p.get("market_exposure_dollars", "0"))
            if nn > 0 and exp > 0:
                avg = max(1, min(99, int(round(100 * exp / nn))))
        except Exception:
            pass
        return tk, nn, side, avg
    return None


async def resting_orders(c: KalshiClient, ticker: str | None = None) -> list[dict]:
    if DRY_RUN:
        return [o for o in PAPER.resting if ticker is None or o["ticker"] == ticker]
    d = await c.req("GET", "/portfolio/orders", params={"status": "resting"})
    return [o for o in d.get("orders", [])
            if ticker is None or o.get("ticker") == ticker]


async def cancel_all(c: KalshiClient) -> None:
    if DRY_RUN:
        PAPER.resting.clear(); return
    orders = [o for o in await resting_orders(c)
              if (o.get("ticker") or "").startswith(SERIES)]
    if not orders:
        return
    _log("CANCEL", f"cancelling {len(orders)} resting {SERIES} order(s)")
    results = await asyncio.gather(
        *(c.req("DELETE", f"/portfolio/events/orders/{o['order_id']}")
          for o in orders), return_exceptions=True)
    failed = [r for r in results if isinstance(r, Exception)]
    if failed:
        _log("CANCEL", f"{len(failed)}/{len(orders)} cancel(s) FAILED: {failed[0]!r}")


async def place_order(c: KalshiClient, ticker: str, action: str, side: str,
                      count: int, price_cents: int, tag: str) -> bool:
    body = _mk_order(ticker, action, side, count, price_cents)
    _log(tag, f"{'[DRY] ' if DRY_RUN else ''}{action.upper()} {side.upper()} "
              f"x{count} @ {price_cents}c on {ticker}")
    if DRY_RUN:
        PAPER.resting.append({"ticker": ticker, "action": action, "side": side,
                              "price": price_cents, "count": count})
        return True
    try:
        await c.req("POST", ORDER_CREATE_PATH, body=body)
        return True
    except Exception as e:
        _log(tag, f"order FAILED: {e}")
        return False


# ── market data helpers (from fable5) ────────────────────────────────────────
def _cents(m: dict, key: str) -> int | None:
    raw = m.get(key)
    if raw is not None:
        try: return int(round(float(raw)))
        except Exception: pass
    raw = m.get(f"{key}_dollars")
    if raw is not None:
        try: return int(round(float(raw) * 100))
        except Exception: pass
    return None


def _strike(m: dict) -> float | None:
    raw = m.get("floor_strike") or m.get("strike_price") or m.get("cap_strike")
    try: return float(raw) if raw is not None else None
    except Exception: return None


def _parse_dt(s: str | None) -> datetime | None:
    if not s: return None
    try: return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception: return None


async def open_markets(c: KalshiClient) -> list[dict]:
    d = await c.req("GET", "/markets", params={
        "series_ticker": SERIES, "status": "open", "limit": 1000})
    return d.get("markets", [])


async def market_bid(c: KalshiClient, ticker: str, side: str) -> int | None:
    try:
        d = await c.req("GET", f"/markets/{ticker}", params={"_": _ts_ms()})
        return _cents(d.get("market", {}), f"{side}_bid")
    except Exception as e:
        _log("BID", f"read failed: {e}")
        return None


async def current_hour_event(c: KalshiClient) -> tuple[str, datetime] | None:
    """Soonest-closing open KXBTCD event within 65 min, or None."""
    try:
        now = _utc_now()
        closes: dict[str, datetime] = {}
        for m in await open_markets(c):
            ev, ct = m.get("event_ticker"), _parse_dt(m.get("close_time"))
            if not ev or ct is None or ct <= now:
                continue
            if ct > now + timedelta(minutes=65):
                continue
            if ev not in closes or ct < closes[ev]:
                closes[ev] = ct
        if closes:
            ev = min(closes, key=lambda k: closes[k])
            return ev, closes[ev]
    except Exception as e:
        _log("MARKET", f"event poll error: {e}")
    return None


async def pick_strike(c: KalshiClient, event: str, spot: float, side: str
                      ) -> tuple[str, float, int] | None:
    """(ticker, strike, bid) of the event strike whose SIGNAL-SIDE bid is
    closest to ENTRY_BID_SWEET (2026-07-12 owner tweak: scan adjacent
    strikes for a ~40-60c contract instead of strictly nearest-to-spot).
    Only strikes within MAX_STRIKE_DIST of spot and bids inside
    [ENTRY_BID_LO, ENTRY_BID_HI] qualify; ties break to the strike
    nearest spot.  Bids come from the same /markets payload (no extra
    round-trips); the maker limit re-quotes at order time anyway."""
    best = None
    for m in await open_markets(c):
        if m.get("event_ticker") != event:
            continue
        stk = _strike(m)
        if stk is None or abs(stk - spot) > MAX_STRIKE_DIST:
            continue
        bid = _cents(m, f"{side}_bid")
        if bid is None or not (ENTRY_BID_LO <= bid <= ENTRY_BID_HI):
            continue
        key = (abs(bid - ENTRY_BID_SWEET), abs(stk - spot))
        if best is None or key < best[0]:
            best = (key, m["ticker"], stk, bid)
    return (best[1], best[2], best[3]) if best else None


# ══════════════════════════════════════════════════════════════════════════
#  TRADE LIFECYCLE
# ══════════════════════════════════════════════════════════════════════════
def init_csv() -> None:
    if not CSV_FILE.exists():
        with CSV_FILE.open("w", newline="") as f:
            csv.writer(f).writerow(_CSV_COLS)


def log_trade(**kw) -> None:
    with CSV_FILE.open("a", newline="") as f:
        csv.writer(f).writerow([kw.get(c, "") for c in _CSV_COLS])


async def flatten(c: KalshiClient, ticker: str) -> int | None:
    """Cancel all + sell any position at escalating prices (fable5 logic)."""
    await cancel_all(c)
    contracts, side = await position_for(c, ticker)
    if contracts <= 0:
        return None
    px = None
    for i, undercut in enumerate((0, 2, 4)):
        bid = await market_bid(c, ticker, side)
        px = max(1, (bid if bid is not None else 3) - undercut)
        _log("FLAT", f"{'selling' if i == 0 else f'attempt {i+1}'} "
                     f"{contracts} {side.upper()} @ {px}c")
        await place_order(c, ticker, "sell", side, contracts, px, "FLAT")
        if DRY_RUN:
            PAPER.resting.clear(); PAPER.position = None
            return px
        await asyncio.sleep(5)
        contracts, side = await position_for(c, ticker)
        if contracts <= 0:
            return px
        await cancel_all(c)
    _log("FLAT", "fire-sale @ 2c")
    await place_order(c, ticker, "sell", side, contracts, 2, "FLAT")
    await asyncio.sleep(5)
    contracts, _s = await position_for(c, ticker)
    if contracts > 0:
        _log("FLAT", f"WARNING: still holding {contracts} — manual attention")
    return 2


async def await_entry_fill(c: KalshiClient, ticker: str, side: str,
                           limit_cents: int, contracts: int) -> int:
    """Wait ENTRY_FILL_WAIT_S for the maker buy; return filled contracts."""
    deadline = _utc_now() + timedelta(seconds=ENTRY_FILL_WAIT_S)
    while _utc_now() < deadline:
        if DRY_RUN:
            bid = await market_bid(c, ticker, side)
            if bid is not None and bid <= limit_cents:
                PAPER.resting.clear()
                PAPER.position = {"ticker": ticker, "side": side,
                                  "contracts": contracts}
                _log("FILL", f"[DRY] filled {contracts} @ {limit_cents}c")
                return contracts
        else:
            held, _ = await position_for(c, ticker)
            if held >= contracts:
                _log("FILL", f"filled {held} @ {limit_cents}c")
                return held
            pending = await resting_orders(c, ticker)
            if held > 0 and not pending:
                _log("FILL", f"partial fill {held}/{contracts}")
                return held
            if not pending and held == 0:
                await asyncio.sleep(3)
                held, _ = await position_for(c, ticker)
                if held:
                    return held
                _log("FILL", "order gone without fill")
                return 0
        await asyncio.sleep(POLL_S)
    _log("FILL", "3-min fill window over — cancelling")
    await cancel_all(c)
    held, _ = await position_for(c, ticker)
    return held


async def monitor_position(c: KalshiClient, ticker: str, side: str,
                           entry: int, contracts: int,
                           deadline: datetime) -> tuple[str, int]:
    """TP +20c (resting maker), SL −15c (taker), TIME-STOP, hard deadline."""
    # half-UP, not round()'s banker's rounding: 30c +15% is 34.5 and round()
    # would give 34, delivering 13.3% instead of the 15% asked for.
    tp = (min(99, max(entry + 1, int(entry * (1 + TP_PCT_OVERRIDE / 100.0) + 0.5)))
          if TP_PCT_OVERRIDE > 0 else min(99, entry + TP_CENTS))
    # half-UP for the same reason as the TP above: banker's rounding would
    # under-deliver the stop the operator asked for.
    sl = (max(1, min(entry - 1, int(entry * (1 - SL_PCT_OVERRIDE / 100.0) + 0.5)))
          if SL_PCT_OVERRIDE > 0 else max(1, entry - SL_CENTS))
    time_stop = _utc_now() + timedelta(minutes=TIME_STOP_MIN)
    hard = min(deadline, time_stop)
    await place_order(c, ticker, "sell", side, contracts, tp, "TP")
    _log("TRADE", f"holding {contracts} {side.upper()} @ {entry}c | "
                  f"TP {tp}c SL {sl}c | time-stop "
                  f"{time_stop.astimezone(_LOCAL):%H:%M:%S} CST")
    while True:
        now = _utc_now()
        if now >= hard:
            reason = "TIME_STOP" if hard == time_stop and now >= time_stop \
                else "DEADLINE_FLATTEN"
            px = await flatten(c, ticker)
            return (reason, px if px is not None else tp)
        bid = await market_bid(c, ticker, side)
        if bid is not None and bid > 0:
            if DRY_RUN and bid >= tp:
                PAPER.resting.clear(); PAPER.position = None
                return ("TAKE_PROFIT", tp)
            if bid <= sl:
                _log("MON", f"SL: bid {bid} <= {sl}")
                px = await flatten(c, ticker)
                return ("STOP_LOSS", px if px is not None else sl)
        if not DRY_RUN:
            held, _ = await position_for(c, ticker)
            if held == 0:
                return ("TAKE_PROFIT", tp)
        await asyncio.sleep(POLL_S)


# ══════════════════════════════════════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════
async def run_bot() -> int | None:
    _acquire_lock()
    log_fh = LOG_FILE.open("a", encoding="utf-8")
    sys.stdout = _Tee(sys.__stdout__, log_fh)
    sys.stderr = _Tee(sys.__stderr__, log_fh)

    bank = Bankroll()
    init_csv()

    _size_desc = (f"fixed {FIXED_CONTRACTS} contract(s)/trade"
                  if FIXED_CONTRACTS > 0 else f"max/trade={MAX_PV_PCT}%")
    _log("CFG", f"DRY_RUN={DRY_RUN} bankroll=${bank.bankroll:.2f} "
                f"banked=${bank.banked:.2f} {_size_desc} "
                f"TP+{TP_CENTS}c SL-{SL_CENTS}c time-stop {TIME_STOP_MIN}m")
    _log("CFG", f"signal source: research handoff {HANDOFF_FILE.name} "
                f"(committee/timeboxes removed)")
    if not DRY_RUN:
        _log("CFG", "*** LIVE MODE — REAL MONEY ***")

    c = KalshiClient()

    last_bar = bank.last_signal_bar          # de-dup key across restarts
    trades_this_hour = 0
    hour_key = None
    try:
        while True:
            # self-heal: re-assert the lock if something external removed it
            # (observed 2026-07-11: lock vanished while the bot kept running,
            # leaving a duplicate launch unblocked)
            try:
                if not LOCK_FILE.is_file():
                    LOCK_FILE.write_text(str(os.getpid()))
                    _log("LOCK", "lock file was missing — re-asserted")
            except Exception:
                pass

            if bank.maybe_daily_reset():
                # The 08:00 bankroll reset already happened in-process above.
                # If launched under the wrapper .bat (BTC_RESTART_ON_RESET=1),
                # exit 42 so it relaunches with a fresh day-stamped log; when
                # launched directly (no wrapper), just keep running.
                if os.getenv("BTC_RESTART_ON_RESET") == "1":
                    _log("RESTART", "08:00 daily reset done — exiting for a "
                                    "fresh day log (wrapper will relaunch)")
                    return RESTART_EXIT_CODE
                _log("BANK", "08:00 daily reset done — continuing in-process")

            # halts
            if bank.bankroll < MIN_BANKROLL_HALT:
                _log("HALT", f"bankroll ${bank.bankroll:.2f} < "
                             f"${MIN_BANKROLL_HALT} — stopping")
                return
            # ── BANK-TARGET (common bot contract, user 08/03). Total equity
            # = risked bankroll + skimmed profit: the 08:00 skim moves wins
            # into `banked`, and a target that ignored it could never be hit.
            if BURST_TARGET_PCT > 0 and (bank.bankroll + bank.banked) >= \
                    BANKROLL_SEED * (1 + BURST_TARGET_PCT / 100.0):
                _log("BANK-TARGET", f"TP reached on bank: ${bank.bankroll:.2f} + "
                                    f"banked ${bank.banked:.2f} = "
                                    f"+{BURST_TARGET_PCT:.0f}% on "
                                    f"${BANKROLL_SEED:.2f} - stopping")
                return
            if BURST_BANK_SL_PCT > 0 and (bank.bankroll + bank.banked) <= \
                    BANKROLL_SEED * (1 - BURST_BANK_SL_PCT / 100.0):
                _log("BANK-SL", f"SL HIT on Bank: ${bank.bankroll:.2f} + banked "
                                f"${bank.banked:.2f} <= -{BURST_BANK_SL_PCT:.0f}% "
                                f"on ${BANKROLL_SEED:.2f} - stopping")
                return
            if bank.day_loss_pct() >= DAILY_LOSS_HALT_PCT:
                _log("HALT", f"daily loss {bank.day_loss_pct():.1f}% ≥ "
                             f"{DAILY_LOSS_HALT_PCT}% — idle until 08:00 reset")
                await asyncio.sleep(300)
                continue

            # ── read the research-signal handoff ────────────────────────────
            sig = read_handoff()
            if not sig:
                await asyncio.sleep(POLL_S)
                continue
            bar_epoch = int(sig.get("bar_epoch", 0))
            if bar_epoch <= last_bar:
                await asyncio.sleep(POLL_S)      # already traded / no new signal
                continue

            direction = sig.get("direction")
            spot = float(sig.get("signal_price") or 0)
            signal_name = sig.get("signal", "?")
            acc = sig.get("acc_tp_before_sl_pct")
            now = _utc_now()

            # freshness: don't act on a stale handoff left by a prior session
            age_s = now.timestamp() - bar_epoch
            if age_s > HANDOFF_MAX_AGE_S:
                _log("SIG", f"stale signal {signal_name} {direction} "
                            f"(bar {age_s/60:.0f} min old) — skipping")
                last_bar = bar_epoch
                bank.set_last_signal_bar(bar_epoch)
                continue
            if direction not in ("LONG", "SHORT") or spot <= 0:
                last_bar = bar_epoch
                bank.set_last_signal_bar(bar_epoch)
                continue

            _log("SIG", f"research signal {direction} {signal_name} "
                        f"(acc {acc}%) @ spot ${spot:,.0f}")

            hk = now.strftime("%Y%m%d%H")
            if hk != hour_key:
                hour_key, trades_this_hour = hk, 0

            # ── EXECUTION gates (unchanged from the committee edition) ───────
            def _consume():
                nonlocal last_bar
                last_bar = bar_epoch
                bank.set_last_signal_bar(bar_epoch)

            if now.minute > LAST_ENTRY_MINUTE:
                _log("GATE", f"signal at :{now.minute:02d} — too late in the "
                             f"hour for a {TIME_STOP_MIN}m stop"); _consume(); continue
            if trades_this_hour >= MAX_TRADES_PER_HOUR:
                _log("GATE", "hourly trade cap reached"); _consume(); continue

            ev = await current_hour_event(c)
            if ev is None:
                _log("GATE", "no open hourly event"); _consume(); continue
            event, close_time = ev
            deadline = close_time - timedelta(minutes=FLATTEN_BEFORE_MIN)
            if now + timedelta(minutes=TIME_STOP_MIN) > deadline:
                _log("GATE", "time-stop would cross the flatten deadline")
                _consume(); continue

            if await event_position(c, event):
                _log("GATE", "already holding a position this event")
                _consume(); continue

            side = "yes" if direction == "LONG" else "no"
            picked = await pick_strike(c, event, spot, side)
            if picked is None:
                _log("GATE", f"no strike within ${MAX_STRIKE_DIST:.0f} of "
                             f"spot has a {side} bid in "
                             f"[{ENTRY_BID_LO},{ENTRY_BID_HI}]")
                _consume(); continue
            ticker, strike, bid = picked

            # common bot contract (user 08/03): always fixed — the %-of-
            # bankroll fallback is removed, contracts means contracts
            contracts = max(1, FIXED_CONTRACTS)
            cost = contracts * bid / 100
            cash = await account_cash(c)
            if cost > cash:
                contracts = int(cash // (bid / 100))
                if contracts < 1:
                    _log("GATE", f"account cash ${cash:.2f} can't fund 1 "
                                 f"contract"); _consume(); continue
                cost = contracts * bid / 100

            # ── NO-TRADE window (user 08/03): the signal is CONSUMED, not
            # deferred — trading it after the window would act on a stale bar.
            _ntw = _in_no_trade_window()
            if _ntw is not None:
                _consume()
                _log("NO-TRADE", f"local time inside "
                                 f"{_ntw[0]:%H:%M}-{_ntw[1]:%H:%M} - "
                                 f"{signal_name} consumed, no entry")
                continue

            # committing to the trade — mark the signal consumed now so a
            # crash mid-trade can't re-fire the same bar on restart
            _consume()
            _sz = (f"fixed {contracts}x" if FIXED_CONTRACTS > 0
                   else f"{contracts}x ≤ {MAX_PV_PCT:.0f}% of "
                        f"${bank.bankroll:.2f}")
            _log("ENTRY", f"{signal_name} {direction} → {ticker} {side.upper()} "
                          f"strike={strike:,.0f} bid={bid}c spot=${spot:,.0f} "
                          f"| {_sz} (~${cost:.2f})")

            if not await place_order(c, ticker, "buy", side, contracts, bid,
                                     "BUY"):
                continue
            real = await await_entry_fill(c, ticker, side, bid, contracts)
            if real <= 0:
                continue

            reason, exit_c = await monitor_position(c, ticker, side, bid,
                                                    real, deadline)
            fee = 0.07 * (exit_c / 100) * (1 - exit_c / 100) * real \
                if reason != "TAKE_PROFIT" else 0.0
            pnl = (exit_c - bid) / 100 * real - fee
            bank.settle(pnl)
            trades_this_hour += 1
            _log("EXIT", f"{reason} @ {exit_c}c | pnl ${pnl:+.2f} | bankroll "
                         f"${bank.bankroll:.2f} (banked ${bank.banked:.2f})")
            log_trade(timestamp=f"{datetime.now(_LOCAL):%Y-%m-%d %H:%M:%S} CST",
                      event=event, ticker=ticker, signal=signal_name, side=side,
                      strike=strike, contracts=real, entry_cents=bid,
                      exit_cents=exit_c, exit_reason=reason,
                      pnl_dollars=round(pnl, 2),
                      bankroll_after=round(bank.bankroll, 2),
                      banked_total=round(bank.banked, 2),
                      spot_at_entry=round(spot, 2),
                      signal_acc=acc if acc is not None else "",
                      utc_hour=now.hour)
    finally:
        try: await cancel_all(c)
        except Exception: pass
        try: await c.close()
        except Exception: pass
        try: log_fh.close()
        except Exception: pass
        _release_lock()


def main() -> None:
    rc = asyncio.run(run_bot())
    sys.exit(rc or 0)          # 42 = daily-reset restart (see launcher .bat)


if __name__ == "__main__":
    main()
