"""
bot_btc_15_2.py — btc-15 signal follower for Kalshi KXBTC15M markets.

Kalshi client + API usage lifted from v4_bot_kalshi_btc15.py (RSA-PSS signed
V2 endpoints).  Strategy per user spec:

  * whenever a NEW BTC-15 market opens, derive its quarter mark T
  * refresh <project>\\runtime\\indicators\\btc15_signal_report.csv
    via ``btc15_quarter.bat 1`` (past 24h only) on the :02/:17/:32/:47 cadence —
    the ±2m windows for mark T complete at T+2m, so the fresh record (a PENDING
    row: direction known, is_matched=NA) lands ~T+2m50s
  * the signal is checked (and printed) at T+2m30s; if the CSV has not updated
    yet, keep polling every 2s until it appears — then direction LONG → buy
    YES, SHORT → buy NO — no other entry filter — but ONLY while the side's
    ask is inside the strict [MIN_CENTS, MAX_CENTS] price band (limit at band
    max, GTC)
  * at market minute TP_AT_MIN, double-confirm the open position via the
    positions API and rest a SELL at TP_CENTS for the held side/quantity
  * NO stop-loss — anything unsold rides to settlement

Run it exactly like v4: from your ``customers/<name>/`` folder, so
``load_dotenv()`` picks up that folder's ``.env`` (KALSHI_API_KEY_ID,
KALSHI_PRIVATE_KEY, BASE_URI) and the relative pem path resolves there.
Trade log + state files are CWD-relative too, so they land per-customer.

Env (independent of v4's flags so this bot cannot go live by accident):
  BOT152_DRY_RUN    TRUE/FALSE   default TRUE  (log orders, don't send)
  BOT152_CONTRACTS  int          default 1
  KALSHI_API_KEY_ID / KALSHI_PRIVATE_KEY / BASE_URI — same as v4.
"""
from __future__ import annotations

import asyncio
import base64
import csv
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding as _padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from dotenv import load_dotenv

# Force UTF-8 stdout/stderr: on Windows, redirecting output to a file (or a
# non-UTF-8 console codepage) makes Python default to cp1252, which cannot
# encode the arrows/cent-signs/checkmarks used throughout this bot's log
# lines (crashed a real run: 'charmap' codec can't encode '→'). This
# must run before any log() call.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# Load the CUSTOMER folder's .env first (CWD — the launch pattern), then fall
# back to the walk-up .env for anything missing.  Bare load_dotenv() resolves
# from the script's directory, NOT the CWD, and would silently skip the
# customer's credentials.
if not (Path.cwd() / ".env").exists():
    sys.exit(
        "bot_btc_15_2: no .env in the current directory.\n"
        "Launch this bot FROM your customer folder so its credentials + pem resolve:\n"
        "    cd D:\\_projects\\vidura-36-app\\customers\\suma\n"
        "    python D:\\_projects\\vidura-36-app\\runtime\\prediction-trade\\kalshi\\btc\\btc15\\v5_bot_btc_15_2.py"
    )
load_dotenv(Path.cwd() / ".env")
load_dotenv()

# ── config (v4-compatible auth, bot-specific safety flags) ───────────────────
BASE_URI          = os.getenv("BASE_URI", "https://external-api.kalshi.com/trade-api/v2")
API_KEY_ID        = os.getenv("KALSHI_API_KEY_ID", "")
PRIVATE_KEY_PATH  = os.getenv("KALSHI_PRIVATE_KEY", "kalshi_private.pem")
ORDER_CREATE_PATH = os.getenv("KALSHI_ORDER_PATH", "/portfolio/events/orders")
SERIES            = "KXBTC15M"

DRY_RUN     = os.getenv("BOT152_DRY_RUN", "TRUE").upper() == "TRUE"
CONTRACTS   = int(os.getenv("BOT152_CONTRACTS", "1"))

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

# STRICT entry price band: buy only while the signal side's ask is inside
# [MIN_CENTS, MAX_CENTS]; the limit order is placed at MAX_CENTS.
MIN_CENTS   = int(os.getenv("BOT152_MIN_CENTS", "35"))
MAX_CENTS   = int(os.getenv("BOT152_MAX_CENTS", "45"))
BUY_AT_CENTS = MAX_CENTS
# dynamic band: if the side's ask is already ABOVE WIDE_TRIGGER when the signal
# arrives (market ran our way), accept a pullback entry up to WIDE_MAX instead.
WIDE_TRIGGER_CENTS = int(os.getenv("BOT152_WIDE_TRIGGER_CENTS", "60"))
WIDE_MAX_CENTS     = int(os.getenv("BOT152_WIDE_MAX_CENTS", "55"))
# take-profit: at market minute TP_AT_MIN (mark+10m), if a position is open in
# the current market, rest a sell at TP_CENTS for the held side/quantity.
TP_CENTS    = int(os.getenv("BOT152_TP_CENTS", "90"))
TP_AT_MIN   = int(os.getenv("BOT152_TP_AT_MIN", "10"))
# Per-trade profit target as a PERCENT OVER ENTRY (user 07/30). When > 0 this
# replaces the fixed TP_CENTS price: tp = entry x (1 + pct/100), clamped to
# 1-99c. 0 keeps the historical behaviour (a flat 90c sell regardless of what
# the fill cost), which pays very differently from a 45c entry than a 70c one.
TP_PCT      = float(os.getenv("BOT152_TP_PCT", "0") or 0)
# band watcher: async poll cadence and how close to market close entries stop.
# 180s = watch until market minute 12; NO orders in the last 3 minutes even if
# the price is in range (user rule).
BAND_POLL_SEC    = float(os.getenv("BOT152_BAND_POLL_SEC", "1"))
CLOSE_BUFFER_SEC = int(os.getenv("BOT152_CLOSE_BUFFER_SEC", "180"))

# vendored runtime: resolve the indicators folder from THIS file's location
# (…/runtime/prediction-trade/kalshi/btc/btc15 -> …/runtime/indicators) so the
# bot never reaches back into the original 38trades checkout.
_INDICATORS = Path(__file__).resolve().parents[4] / "indicators"
SIGNAL_CSV  = Path(os.getenv("BTC15_SIGNAL_CSV",
                             str(_INDICATORS / "btc15_signal_report.csv")))
QUARTER_BAT = Path(os.getenv("BTC15_QUARTER_BAT",
                             str(_INDICATORS / "btc15_quarter.bat")))
REFRESH_HOURS    = "2"             # bat arg = hours: fast past-2h refresh
SIGNAL_CHECK_SEC = int(os.getenv("BOT152_SIGNAL_CHECK_SEC", "150"))  # first CSV check at T+2:30
SIGNAL_POLL_SEC  = float(os.getenv("BOT152_SIGNAL_POLL_SEC", "2"))
REFRESH_MINUTES  = (2, 17, 32, 47)

TRADES_CSV = Path(os.getenv("BOT152_CSV_PATH", "bot_btc_15_2_trades.csv"))
STATE_FILE = Path(os.getenv("BOT152_STATE_PATH", "bot_btc_15_2_state.json"))
LOG_FILE   = Path(os.getenv("BOT152_LOG_PATH", "btc-15-2.log"))   # CWD-relative (per customer)
_CT = ZoneInfo("America/Chicago")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_ct() -> datetime:
    return datetime.now(_CT)


def _ts_ms() -> str:
    return str(int(_now_utc().timestamp() * 1000))


def log(msg: str) -> None:
    """Tee every log line: console (live watching) + btc-15-2.log (audit/monitor)."""
    line = f"[{_now_ct():%m/%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass                                   # logging must never kill the bot


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  Kalshi client — same signing/endpoints as v4_bot_kalshi_btc15.py         ║
# ╚════════════════════════════════════════════════════════════════════════════╝
class KalshiClient:
    def __init__(self) -> None:
        pem = Path(PRIVATE_KEY_PATH)
        if not pem.is_absolute():
            pem = Path.cwd() / pem
        if not pem.exists():
            sys.exit(
                f"bot_btc_15_2: private key not found: {pem}\n"
                "KALSHI_PRIVATE_KEY resolves relative to the folder you launch from —\n"
                "run the bot from your customers/<name>/ folder (e.g. customers\\suma)."
            )
        raw = pem.read_bytes()
        self._pk = load_pem_private_key(raw, password=None)
        self._session: aiohttp.ClientSession | None = None
        self._mu = asyncio.Lock()

    def _sign(self, ts: str, method: str, path: str) -> str:
        sig = self._pk.sign(
            f"{ts}{method}{path}".encode(),
            _padding.PSS(mgf=_padding.MGF1(hashes.SHA256()),
                         salt_length=_padding.PSS.DIGEST_LENGTH),
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

    async def _sess(self) -> aiohttp.ClientSession:
        async with self._mu:
            if self._session is None or self._session.closed:
                self._session = aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300,
                                                   enable_cleanup_closed=True),
                    timeout=aiohttp.ClientTimeout(total=12, connect=4),
                )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def req(self, method: str, path: str, *, params: dict | None = None,
                  body: dict | None = None, retries: int = 3) -> dict:
        url, last = f"{BASE_URI}{path}", None
        sess = await self._sess()
        for attempt in range(1, retries + 1):
            hdrs = self._auth_headers(method, path)
            try:
                async with sess.request(method.upper(), url, headers=hdrs,
                                        params=params, json=body) as r:
                    txt = await r.text()
                    if r.status >= 400:
                        raise RuntimeError(f"HTTP {r.status}: {txt}")
                    return json.loads(txt)
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as e:
                last = e
                if attempt < retries:
                    await asyncio.sleep(0.4 * attempt)
        raise RuntimeError(f"Failed after {retries} tries: {last}") from last


def _mk_order(ticker: str, action: str, side: str, count: int, price_cents: int) -> dict:
    """Kalshi V2 create-order body (verbatim mapping from v4):
    buy YES @p -> bid p/100 · buy NO @p -> ask (100-p)/100."""
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


async def place_buy(c: KalshiClient, ticker: str, side: str,
                    buy_at: int = BUY_AT_CENTS) -> dict | None:
    order = _mk_order(ticker, "buy", side, CONTRACTS, buy_at)
    tag = "[DRY] " if DRY_RUN else ""
    log(f"  {tag}[BUY] {side.upper()} ×{CONTRACTS} @ {buy_at}¢  {ticker}")
    if DRY_RUN:
        return {"order": {"order_id": f"DRY-{uuid.uuid4().hex[:8]}", "status": "dry_run"}}
    try:
        r = await c.req("POST", ORDER_CREATE_PATH, body=order)
        log(f"  [BUY] resp: {json.dumps(r)[:300]}")
        return r
    except Exception as e:
        log(f"  [BUY] FAILED: {e}")
        return None


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  Signal refresh — btc15_quarter.bat 1 (past 24h) at :02/:17/:32/:47       ║
# ╚════════════════════════════════════════════════════════════════════════════╝
_refresh_lock = asyncio.Lock()
_last_refresh_kick: datetime | None = None


async def run_refresh(reason: str) -> None:
    """Run the quarter bat with DAYS=1; serialized so runs never overlap."""
    global _last_refresh_kick
    if _refresh_lock.locked():
        return
    async with _refresh_lock:
        _last_refresh_kick = _now_ct()
        log(f"[REFRESH] quarter signals {REFRESH_HOURS}h  ({reason})")
        try:
            if os.name == "nt" and QUARTER_BAT.is_file():
                # Windows: the bat, exactly as always
                proc = await asyncio.create_subprocess_exec(
                    "cmd", "/c", str(QUARTER_BAT), REFRESH_HOURS,
                    cwd=str(QUARTER_BAT.parent),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(proc.wait(), timeout=240)
            else:
                # POSIX (or bat missing): run what the bat runs, directly —
                # cmd.exe does not exist there and a silent failure here
                # would leave the bot trading on stale signals
                for argv in (
                    [sys.executable, str(QUARTER_BAT.parent / "btc15_signal.py"),
                     "--hours", str(REFRESH_HOURS)],
                    [sys.executable, str(QUARTER_BAT.parent / "bake_btc15_dashboard.py")],
                ):
                    proc = await asyncio.create_subprocess_exec(
                        *argv, cwd=str(QUARTER_BAT.parent),
                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                    await asyncio.wait_for(proc.wait(), timeout=240)
            log(f"[REFRESH] done (rc={proc.returncode})")
        except Exception as e:
            log(f"[REFRESH] error: {e}")


def ensure_refresh(reason: str) -> None:
    """Kick a refresh unless one ran/started within the last 60s."""
    if _refresh_lock.locked():
        return
    if _last_refresh_kick and (_now_ct() - _last_refresh_kick).total_seconds() < 60:
        return
    asyncio.create_task(run_refresh(reason))


async def refresh_scheduler() -> None:
    """Fire the past-24h refresh at :02 / :17 / :32 / :47 (CT) while running."""
    while True:
        now = _now_ct()
        nxt = None
        for m in REFRESH_MINUTES:
            cand = now.replace(minute=m, second=0, microsecond=0)
            if cand > now:
                nxt = cand
                break
        if nxt is None:                                   # past :47 → next hour :02
            nxt = (now + timedelta(hours=1)).replace(minute=REFRESH_MINUTES[0],
                                                     second=0, microsecond=0)
        await asyncio.sleep(max(1.0, (nxt - now).total_seconds()))
        ensure_refresh(f"scheduler {nxt:%H:%M}")


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  Signal CSV lookup                                                        ║
# ╚════════════════════════════════════════════════════════════════════════════╝
def read_rows(marks: list[datetime]) -> dict[datetime, dict]:
    """Rows for the given CT quarter marks in one pass (tolerates mid-write reads)."""
    want = {(f"{m:%m/%d/%Y}", f"{m:%H:%M}"): m for m in marks}
    out: dict[datetime, dict] = {}
    try:
        with open(SIGNAL_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = (row.get("date"), row.get("15minute"))
                if key in want:
                    out[want[key]] = row
                    if len(out) == len(want):
                        break
    except Exception as e:
        log(f"[CSV] read error (will retry): {e}")
    return out


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  Market discovery — same /markets usage as v4                             ║
# ╚════════════════════════════════════════════════════════════════════════════╝
def _mark_for_market(m: dict) -> datetime | None:
    """Quarter mark T for a KXBTC15M market: close_time − 15 min, in CT."""
    ct = m.get("close_time") or ""
    try:
        close = datetime.fromisoformat(ct.replace("Z", "+00:00")).astimezone(_CT)
    except ValueError:
        return None
    mark = close - timedelta(minutes=15)
    if mark.minute % 15:                                   # not a clean quarter grid
        mark = mark.replace(minute=(mark.minute // 15) * 15, second=0, microsecond=0)
    return mark.replace(second=0, microsecond=0)


async def side_ask_cents(c: KalshiClient, ticker: str, side: str) -> int | None:
    """Current ask (cents) for buying ``side`` on ``ticker``; None on error.

    The external-api V2 surface quotes STRING DOLLARS (``no_ask_dollars``:
    "0.5700"); older surfaces use integer cents (``no_ask``: 57).  Accept both
    — reading only the cents field returned None forever on this host and left
    the band watcher blind (live bug found 07/24).
    """
    try:
        d = await c.req("GET", f"/markets/{ticker}")
        mk = d.get("market", d)
        v = mk.get(f"{side}_ask_dollars")
        if v not in (None, ""):
            cents = int(round(float(v) * 100))
            return cents if cents > 0 else None          # 0.0000 = no quote yet
        v = mk.get(f"{side}_ask")
        return int(v) if v not in (None, "", 0) else None
    except Exception as e:
        log(f"[PRICE] {ticker}: {e}")
        return None


async def wait_for_band(c: KalshiClient, ticker: str, side: str,
                        deadline: datetime, lo: int, hi: int) -> int | None:
    """Async band watcher: poll the side's ask every BAND_POLL_SEC and return
    the ask the moment it is inside [lo, hi]; None at deadline."""
    last_logged, last_log_t = None, _now_ct() - timedelta(seconds=60)
    while _now_ct() < deadline:
        ask = await side_ask_cents(c, ticker, side)
        if ask is not None and lo <= ask <= hi:
            return ask
        if ask is not None and (ask != last_logged
                                or (_now_ct() - last_log_t).total_seconds() >= 15):
            log(f"[BAND] {ticker}: {side.upper()} ask {ask}¢ outside "
                f"{lo}–{hi}¢ — watching (until {deadline:%H:%M:%S})")
            last_logged, last_log_t = ask, _now_ct()
        await asyncio.sleep(BAND_POLL_SEC)
    return None


async def early_price_printer(c: KalshiClient, ticker: str, side: str,
                              stop: asyncio.Event) -> None:
    """Pre-signal visibility: from market open until the real signal arrives,
    print the ask for the PREVIOUS record's side.  PRINT-ONLY — never orders;
    the actual entry side comes from this mark's own signal later."""
    last_logged, last_log_t = None, _now_ct() - timedelta(seconds=60)
    while not stop.is_set():
        ask = await side_ask_cents(c, ticker, side)
        if ask is not None and (ask != last_logged
                                or (_now_ct() - last_log_t).total_seconds() >= 15):
            log(f"[BAND] {ticker}: {side.upper()} ask {ask}¢ (prev-side, pre-signal) — watching")
            last_logged, last_log_t = ask, _now_ct()
        try:
            await asyncio.wait_for(stop.wait(), timeout=BAND_POLL_SEC)
        except asyncio.TimeoutError:
            pass


async def wait_for_new_market(c: KalshiClient, seen: set[str]) -> dict:
    log(f"[MARKET] scanning for next {SERIES} market …")
    while True:
        try:
            d = await c.req("GET", "/markets", params={
                "series_ticker": SERIES, "status": "open", "limit": 5})
            best, best_open = None, None
            for m in d.get("markets", []):
                if m["ticker"] in seen or not m.get("open_time"):
                    continue
                ot = datetime.fromisoformat(m["open_time"].replace("Z", "+00:00"))
                if best_open is None or ot > best_open:
                    best, best_open = m, ot
            if best:
                return best
        except Exception as e:
            log(f"[MARKET] poll error: {e}")
        await asyncio.sleep(3)


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  State + trade log                                                        ║
# ╚════════════════════════════════════════════════════════════════════════════╝
def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"traded": {}}


def save_state(st: dict) -> None:
    st["traded"] = dict(list(st["traded"].items())[-500:])      # keep it bounded
    STATE_FILE.write_text(json.dumps(st, indent=1))


_TRADE_COLS = ["timestamp_ct", "ticker", "mark", "action", "direction", "side",
               "price_cents", "ask_cents", "contracts", "dry_run", "order_id",
               "best_move", "btc_current15", "prev_matched", "prev_momentum"]


def log_trade(ticker: str, mark: datetime, row: dict, side: str, resp: dict | None,
              prev_m: str = "NA", prev_mom: str = "NA", ask: int | None = None,
              action: str = "buy", price: int | None = None,
              contracts: int | None = None) -> None:
    new = not TRADES_CSV.exists()
    with open(TRADES_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(_TRADE_COLS)
        oid = ""
        if resp and isinstance(resp.get("order"), dict):
            oid = resp["order"].get("order_id", "")
        w.writerow([f"{_now_ct():%m/%d/%Y %H:%M:%S}", ticker, f"{mark:%m/%d/%Y %H:%M}",
                    action, row.get("direction", ""), side,
                    price if price is not None else BUY_AT_CENTS,
                    ask if ask is not None else "",
                    contracts if contracts is not None else CONTRACTS,
                    DRY_RUN, oid, row.get("best_move", ""),
                    row.get("btc_current15", ""), prev_m, prev_mom])


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  Take-profit seller — market minute 10                                    ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def position_contracts(c: KalshiClient, ticker: str) -> int:
    """Signed open position for ``ticker`` (+N = YES held, -N = NO held).

    Field-name defensive: this API surface uses ``_fp`` string variants
    (e.g. ``position_fp``: "10.00") alongside/instead of integer ``position``.
    """
    try:
        d = await c.req("GET", "/portfolio/positions", params={"ticker": ticker})
        for p in d.get("market_positions", []):
            if p.get("ticker") == ticker:
                log(f"[TP  ] raw position entry: {json.dumps(p)[:220]}")
                for key in ("position", "position_fp", "quantity", "quantity_fp"):
                    v = p.get(key)
                    if v not in (None, ""):
                        return int(round(float(v)))
                return 0
    except Exception as e:
        log(f"[TP  ] {ticker}: position check error: {e}")
    return 0


def _tp_price(entry_c: int | None) -> int:
    """Take-profit price for a fill at ``entry_c``: BOT152_TP_PCT over entry
    when a percent target is set, else the flat TP_CENTS.

    Rounds half UP, not with round()'s banker's rounding: 70c +15% is 80.5,
    and round() would give 80 — quietly delivering 14.3% instead of the 15%
    that was asked for. Always at least entry+1 so a small percent on a cheap
    fill can never target a loss.
    """
    if TP_PCT > 0 and entry_c:
        target = int(entry_c * (1 + TP_PCT / 100.0) + 0.5)
        return max(entry_c + 1, min(99, target))
    return TP_CENTS


async def tp_seller(c: KalshiClient, ticker: str, side: str, mark: datetime,
                    entry_c: int | None = None) -> None:
    """At mark+TP_AT_MIN (or 30s after a late entry): if an open position
    exists, rest a sell at the take-profit price.

    That price is BOT152_TP_PCT over ``entry_c`` when a percent target is set,
    otherwise the flat TP_CENTS."""
    tp_c = _tp_price(entry_c)
    due = max(mark + timedelta(minutes=TP_AT_MIN),
              _now_ct() + timedelta(seconds=30))
    delay = (due - _now_ct()).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)
    if DRY_RUN:
        log(f"  [DRY] [TP ] {ticker}: would verify position and SELL "
            f"{side.upper()} ×{CONTRACTS} @ {tp_c}¢"
            + (f" (entry {entry_c}¢ +{TP_PCT:g}%)" if TP_PCT > 0 and entry_c else ""))
        log_trade(ticker, mark, {}, side, None, action="sell", price=tp_c)
        return
    # ── DOUBLE-CONFIRM the position (partial fills!): two reads ~2s apart; the
    # sell quantity is ALWAYS the latest API value, never the intended buy size.
    pos1 = await position_contracts(c, ticker)
    if pos1 == 0:
        log(f"[TP  ] {ticker}: no open position at market minute {TP_AT_MIN} — no sell")
        return
    await asyncio.sleep(2)
    pos2 = await position_contracts(c, ticker)
    if pos2 == 0:
        log(f"[TP  ] {ticker}: position vanished on re-check ({pos1} → 0) — no sell")
        return
    if (pos1 > 0) != (pos2 > 0):
        log(f"[TP  ] {ticker}: position SIDE changed between checks ({pos1} → {pos2}) — aborting sell")
        return
    if pos2 != pos1:
        log(f"[TP  ] {ticker}: position drifted between checks ({pos1} → {pos2}) — using latest")
    pos = pos2
    held_side, held = ("yes" if pos > 0 else "no"), abs(pos)
    if held_side != side:
        log(f"[TP  ] {ticker}: held side {held_side.upper()} differs from signal side "
            f"{side.upper()} — selling what is actually held")
    order = _mk_order(ticker, "sell", held_side, held, tp_c)
    log(f"  [TP ] SELL {held_side.upper()} ×{held} @ {tp_c}¢  {ticker}  "
        + (f"(entry {entry_c}¢ +{TP_PCT:g}%, " if TP_PCT > 0 and entry_c else "(")
        + f"confirmed {pos1}→{pos2})")
    try:
        r = await c.req("POST", ORDER_CREATE_PATH, body=order)
        log(f"  [TP ] resp: {json.dumps(r)[:200]}")
        log_trade(ticker, mark, {}, held_side, r, action="sell",
                  price=tp_c, contracts=held)
    except Exception as e:
        log(f"  [TP ] FAILED: {e}")


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  Per-market handler                                                       ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def handle_market(c: KalshiClient, m: dict, st: dict) -> None:
    ticker = m["ticker"]
    mark = _mark_for_market(m)
    if mark is None:
        log(f"[SKIP] {ticker}: no parsable close_time")
        return
    if ticker in st["traded"]:
        log(f"[SKIP] {ticker}: already traded")
        return
    now = _now_ct()
    close = mark + timedelta(minutes=15)
    band_deadline = close - timedelta(seconds=CLOSE_BUFFER_SEC)
    if now >= band_deadline:                               # too late to enter at all
        log(f"[SKIP] {ticker}: too late (market closes {close:%H:%M})")
        return
    log(f"[NEW ] {ticker}  mark {mark:%m/%d %H:%M} CT  close {close:%H:%M}")

    # ── parallel pre-signal price feed: from market open, print the ask for
    # the PREVIOUS record's side (print-only; orders wait for THIS mark's signal)
    prev_mark = mark - timedelta(minutes=15)
    early_stop = asyncio.Event()
    prev0 = read_rows([prev_mark]).get(prev_mark)
    prev_dir = str((prev0 or {}).get("direction", "")).upper()
    if prev_dir in ("LONG", "SHORT"):
        pside = "yes" if prev_dir == "LONG" else "no"
        log(f"[BAND] {ticker}: pre-signal watch on prev-side {pside.upper()} "
            f"({prev_mark:%H:%M} was {prev_dir})")
        asyncio.create_task(early_price_printer(c, ticker, pside, early_stop))

    row = prev = None
    try:
        # kick the refresh at T+2:00 (the bat sleeps 30s → fetch lands ~T+2:30)
        ready_at = mark + timedelta(minutes=2)
        if now < ready_at:
            await asyncio.sleep((ready_at - now).total_seconds())
        ensure_refresh(f"mark {mark:%H:%M}")

        # the signal should be printable by T+2:30 — check then; if the CSV
        # hasn't updated yet, keep polling every SIGNAL_POLL_SEC until it
        # appears (bounded only by the entry deadline).
        check_at = mark + timedelta(seconds=SIGNAL_CHECK_SEC)
        if _now_ct() < check_at:
            await asyncio.sleep((check_at - _now_ct()).total_seconds())
        announced = False
        while _now_ct() < band_deadline:
            rows = read_rows([mark, prev_mark])
            row, prev = rows.get(mark), rows.get(prev_mark)
            if row:
                break
            if not announced:
                log(f"[SIG ] {ticker}: no signal in CSV at +{SIGNAL_CHECK_SEC}s — waiting for update")
                announced = True
            await asyncio.sleep(SIGNAL_POLL_SEC)
    finally:
        early_stop.set()                       # real signal known (or given up)
    if not row:
        log(f"[SIG ] {ticker}: no signal appeared before entry deadline — skipping")
        return

    # prev-record flags are logged for analysis only — no entry filter
    pm  = str((prev or {}).get("is_matched", "NA")).upper()
    pmm = str((prev or {}).get("momentum",  "NA")).upper()

    direction = str(row.get("direction", "")).upper()
    if direction not in ("LONG", "SHORT"):
        log(f"[SIG ] {ticker}: unusable direction {direction!r} — skipping")
        return
    side = "yes" if direction == "LONG" else "no"
    log(f"[SIG ] {mark:%H:%M} {direction}  best_move={row.get('best_move')}  "
        f"minus={row.get('minus_min')}–{row.get('minus_max')}  "
        f"plus={row.get('plus_min')}–{row.get('plus_max')}")

    # ── freshness: the signal row must have been created WITHIN this market's
    # 15-minute window (created_on in [close-15m, close]) — no stale signals.
    created = str(row.get("created_on", ""))
    try:
        cdt = datetime.strptime(created, "%m/%d/%Y %H:%M:%S").replace(tzinfo=_CT)
    except ValueError:
        cdt = None
    if cdt is None or not (close - timedelta(minutes=15) <= cdt <= close):
        log(f"[SIG ] {ticker}: created_on {created!r} not within this market's "
            f"window ({mark:%H:%M}–{close:%H:%M}) — stale signal, skipping")
        return

    # ── dynamic band: if the market already ran our way (ask > trigger) when
    # the signal arrived, accept a pullback entry up to WIDE_MAX.
    first_ask = None
    for _ in range(3):
        first_ask = await side_ask_cents(c, ticker, side)
        if first_ask is not None:
            break
        await asyncio.sleep(1)
    band_lo, band_hi = MIN_CENTS, MAX_CENTS
    if first_ask is not None and first_ask > WIDE_TRIGGER_CENTS:
        band_hi = WIDE_MAX_CENTS
        log(f"[BAND] {ticker}: initial {side.upper()} ask {first_ask}¢ > "
            f"{WIDE_TRIGGER_CENTS}¢ — widening band to {band_lo}–{band_hi}¢")

    # ── async band watcher: enter the INSTANT the ask hits the band, any
    # time from now until shortly before close.
    ask = await wait_for_band(c, ticker, side, band_deadline, band_lo, band_hi)
    if ask is None:
        log(f"[BAND] {ticker}: never inside {band_lo}–{band_hi}¢ before "
            f"{band_deadline:%H:%M:%S} — skipping")
        return
    log(f"[BAND] {ticker}: {side.upper()} ask {ask}¢ IN RANGE — buying @ {band_hi}¢ limit")

    # ── NO-TRADE window (user 08/03): stay alive, enter nothing. Checked at
    # ORDER time — the band wait above can carry the flow into a window.
    _ntw = _in_no_trade_window()
    if _ntw is not None:
        log(f"[NO-TRADE] {ticker}: local time inside "
            f"{_ntw[0]:%H:%M}-{_ntw[1]:%H:%M} - not buying")
        return

    resp = await place_buy(c, ticker, side, band_hi)
    log_trade(ticker, mark, row, side, resp, pm, pmm, ask, price=band_hi)
    st["traded"][ticker] = f"{mark:%m/%d/%Y %H:%M}"
    save_state(st)
    # take-profit leg runs in the background at market minute TP_AT_MIN;
    # no stop-loss — anything unsold rides to settlement.
    asyncio.create_task(tp_seller(c, ticker, side, mark, entry_c=band_hi))


async def main() -> None:
    log(f"bot_btc_15_2 starting  DRY_RUN={DRY_RUN}  contracts={CONTRACTS}  "
        f"entry band {MIN_CENTS}–{MAX_CENTS}¢ (widen to ≤{WIDE_MAX_CENTS}¢ when "
        f"initial ask>{WIDE_TRIGGER_CENTS}¢)  "
        + (f"TP +{TP_PCT:g}% over entry" if TP_PCT > 0 else f"TP sell @{TP_CENTS}¢")
        + f" at market min {TP_AT_MIN}  series={SERIES}")
    log(f"auth: key_id …{API_KEY_ID[-4:] if API_KEY_ID else 'MISSING'}  "
        f"pem={Path(PRIVATE_KEY_PATH).resolve()}  cwd={Path.cwd()}")
    log(f"signal csv: {SIGNAL_CSV}")
    if not SIGNAL_CSV.exists():
        log("[WARN] signal CSV missing — first refresh will create it")
    st = load_state()
    c = KalshiClient()
    seen: set[str] = set(st["traded"])
    asyncio.create_task(refresh_scheduler())
    try:
        while True:
            m = await wait_for_new_market(c, seen)
            seen.add(m["ticker"])
            try:
                await handle_market(c, m, st)
            except Exception as e:
                log(f"[ERR ] {m['ticker']}: {e}")
    finally:
        await c.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nbye")
        sys.exit(0)
