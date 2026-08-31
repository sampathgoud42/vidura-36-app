"""
bot_kalshi_gold15.py — Gold 15-minute signal follower for Kalshi KXGOLD15M markets.

Kalshi client + API usage lifted from v5_bot_btc_15_2.py (RSA-PSS signed
V2 endpoints).  Strategy identical to btc15 v5, adapted for gold:

  * whenever a NEW GOLD-15 market opens, derive its quarter mark T
  * refresh the signal CSV via the gold quarter bat at :02/:17/:32/:47 cadence
  * signal is checked at T+2m30s; direction LONG → buy YES, SHORT → buy NO
    — ONLY while the side's ask is inside the price band
  * at market minute TP_AT_MIN, double-confirm position and rest a SELL at TP_CENTS
  * no stop-loss — anything unsold rides to settlement

Run from your ``customers/<name>/`` folder so ``load_dotenv()`` picks up that
folder's ``.env`` (KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY, BASE_URI).

Env (independent flags so this bot cannot go live by accident):
  BOTGOLD_DRY_RUN    TRUE/FALSE   default TRUE
  BOTGOLD_CONTRACTS  int          default 1
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

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

if not (Path.cwd() / ".env").exists():
    sys.exit(
        "bot_kalshi_gold15: no .env in the current directory.\n"
        "Launch this bot FROM your customer folder so its credentials + pem resolve:\n"
        "    cd D:\\_projects\\vidura-36-app\\customers\\suma\n"
        "    python .../bot_kalshi_gold15.py"
    )
load_dotenv(Path.cwd() / ".env")
load_dotenv()

# ── config ──────────────────────────────────────────────────────────────────
BASE_URI          = os.getenv("BASE_URI", "https://external-api.kalshi.com/trade-api/v2")
API_KEY_ID        = os.getenv("KALSHI_API_KEY_ID", "")
PRIVATE_KEY_PATH  = os.getenv("KALSHI_PRIVATE_KEY", "kalshi_private.pem")
ORDER_CREATE_PATH = os.getenv("KALSHI_ORDER_PATH", "/portfolio/events/orders")
SERIES            = os.getenv("BOTGOLD_SERIES", "KXGOLD15M")

DRY_RUN     = os.getenv("BOTGOLD_DRY_RUN", "TRUE").upper() == "TRUE"
CONTRACTS   = int(os.getenv("BOTGOLD_CONTRACTS", "1"))
MIN_CENTS   = int(os.getenv("BOTGOLD_MIN_CENTS", "35"))
MAX_CENTS   = int(os.getenv("BOTGOLD_MAX_CENTS", "49"))
BUY_AT_CENTS = MAX_CENTS
WIDE_TRIGGER_CENTS = int(os.getenv("BOTGOLD_WIDE_TRIGGER_CENTS", "60"))
WIDE_MAX_CENTS     = int(os.getenv("BOTGOLD_WIDE_MAX_CENTS", "55"))
TP_CENTS    = int(os.getenv("BOTGOLD_TP_CENTS", "90"))
TP_AT_MIN   = int(os.getenv("BOTGOLD_TP_AT_MIN", "10"))
BAND_POLL_SEC    = float(os.getenv("BOTGOLD_BAND_POLL_SEC", "1"))
CLOSE_BUFFER_SEC = int(os.getenv("BOTGOLD_CLOSE_BUFFER_SEC", "180"))

_INDICATORS = Path(__file__).resolve().parents[4] / "indicators"
if str(_INDICATORS) not in sys.path:
    sys.path.insert(0, str(_INDICATORS))
from commodity_score import score_commodity

SIGNAL_CSV  = Path(os.getenv("GOLD15_SIGNAL_CSV",
                             str(_INDICATORS / "gold15_signal_report.csv")))
QUARTER_BAT = Path(os.getenv("GOLD15_QUARTER_BAT",
                             str(_INDICATORS / "commodity15_quarter.bat")))
REFRESH_HOURS    = "2"
SIGNAL_CHECK_SEC = int(os.getenv("BOTGOLD_SIGNAL_CHECK_SEC", "150"))
SIGNAL_POLL_SEC  = float(os.getenv("BOTGOLD_SIGNAL_POLL_SEC", "2"))
REFRESH_MINUTES  = (2, 17, 32, 47)

TRADES_CSV = Path(os.getenv("BOTGOLD_CSV_PATH", "bot_gold15_trades.csv"))
STATE_FILE = Path(os.getenv("BOTGOLD_STATE_PATH", "bot_gold15_state.json"))
LOG_FILE   = Path(os.getenv("BOTGOLD_LOG_PATH", "gold-15.log"))
_CT = ZoneInfo("America/Chicago")


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_ct() -> datetime:
    return datetime.now(_CT)


def _ts_ms() -> str:
    return str(int(_now_utc().timestamp() * 1000))


def log(msg: str) -> None:
    line = f"[{_now_ct():%m/%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


class KalshiClient:
    def __init__(self) -> None:
        pem = Path(PRIVATE_KEY_PATH)
        if not pem.is_absolute():
            pem = Path.cwd() / pem
        if not pem.exists():
            sys.exit(f"bot_kalshi_gold15: private key not found: {pem}")
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
    log(f"  {tag}[BUY] {side.upper()} x{CONTRACTS} @ {buy_at}c  {ticker}")
    if DRY_RUN:
        return {"order": {"order_id": f"DRY-{uuid.uuid4().hex[:8]}", "status": "dry_run"}}
    try:
        r = await c.req("POST", ORDER_CREATE_PATH, body=order)
        log(f"  [BUY] resp: {json.dumps(r)[:300]}")
        return r
    except Exception as e:
        log(f"  [BUY] FAILED: {e}")
        return None


# ── Signal refresh ──────────────────────────────────────────────────────────
_refresh_lock = asyncio.Lock()
_last_refresh_kick: datetime | None = None


async def run_refresh(reason: str) -> None:
    global _last_refresh_kick
    if _refresh_lock.locked():
        return
    async with _refresh_lock:
        _last_refresh_kick = _now_ct()
        log(f"[REFRESH] quarter signals {REFRESH_HOURS}h  ({reason})")
        try:
            if os.name == "nt" and QUARTER_BAT.is_file():
                proc = await asyncio.create_subprocess_exec(
                    "cmd", "/c", str(QUARTER_BAT), REFRESH_HOURS,
                    cwd=str(QUARTER_BAT.parent),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(proc.wait(), timeout=240)
            else:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, str(QUARTER_BAT.parent / "commodity15_signal.py"),
                    "--hours", str(REFRESH_HOURS), "--symbols", "gold15",
                    cwd=str(QUARTER_BAT.parent),
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(proc.wait(), timeout=240)
            log(f"[REFRESH] done (rc={proc.returncode})")
        except Exception as e:
            log(f"[REFRESH] error: {e}")


def ensure_refresh(reason: str) -> None:
    if _refresh_lock.locked():
        return
    if _last_refresh_kick and (_now_ct() - _last_refresh_kick).total_seconds() < 60:
        return
    asyncio.create_task(run_refresh(reason))


async def refresh_scheduler() -> None:
    while True:
        now = _now_ct()
        nxt = None
        for m in REFRESH_MINUTES:
            cand = now.replace(minute=m, second=0, microsecond=0)
            if cand > now:
                nxt = cand
                break
        if nxt is None:
            nxt = (now + timedelta(hours=1)).replace(minute=REFRESH_MINUTES[0],
                                                     second=0, microsecond=0)
        await asyncio.sleep(max(1.0, (nxt - now).total_seconds()))
        ensure_refresh(f"scheduler {nxt:%H:%M}")


# ── Signal CSV lookup ───────────────────────────────────────────────────────
def read_rows(marks: list[datetime]) -> dict[datetime, dict]:
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


# ── Market discovery ────────────────────────────────────────────────────────
def _mark_for_market(m: dict) -> datetime | None:
    ct = m.get("close_time") or ""
    try:
        close = datetime.fromisoformat(ct.replace("Z", "+00:00")).astimezone(_CT)
    except ValueError:
        return None
    mark = close - timedelta(minutes=15)
    if mark.minute % 15:
        mark = mark.replace(minute=(mark.minute // 15) * 15, second=0, microsecond=0)
    return mark.replace(second=0, microsecond=0)


async def side_ask_cents(c: KalshiClient, ticker: str, side: str) -> int | None:
    try:
        d = await c.req("GET", f"/markets/{ticker}")
        mk = d.get("market", d)
        v = mk.get(f"{side}_ask_dollars")
        if v not in (None, ""):
            cents = int(round(float(v) * 100))
            return cents if cents > 0 else None
        v = mk.get(f"{side}_ask")
        return int(v) if v not in (None, "", 0) else None
    except Exception as e:
        log(f"[PRICE] {ticker}: {e}")
        return None


async def wait_for_band(c: KalshiClient, ticker: str, side: str,
                        deadline: datetime, lo: int, hi: int) -> int | None:
    last_logged, last_log_t = None, _now_ct() - timedelta(seconds=60)
    while _now_ct() < deadline:
        ask = await side_ask_cents(c, ticker, side)
        if ask is not None and lo <= ask <= hi:
            return ask
        if ask is not None and (ask != last_logged
                                or (_now_ct() - last_log_t).total_seconds() >= 15):
            log(f"[BAND] {ticker}: {side.upper()} ask {ask}c outside "
                f"{lo}-{hi}c -- watching (until {deadline:%H:%M:%S})")
            last_logged, last_log_t = ask, _now_ct()
        await asyncio.sleep(BAND_POLL_SEC)
    return None


async def early_price_printer(c: KalshiClient, ticker: str, side: str,
                              stop: asyncio.Event) -> None:
    last_logged, last_log_t = None, _now_ct() - timedelta(seconds=60)
    while not stop.is_set():
        ask = await side_ask_cents(c, ticker, side)
        if ask is not None and (ask != last_logged
                                or (_now_ct() - last_log_t).total_seconds() >= 15):
            log(f"[BAND] {ticker}: {side.upper()} ask {ask}c (prev-side, pre-signal) -- watching")
            last_logged, last_log_t = ask, _now_ct()
        try:
            await asyncio.wait_for(stop.wait(), timeout=BAND_POLL_SEC)
        except asyncio.TimeoutError:
            pass


async def wait_for_new_market(c: KalshiClient, seen: set[str]) -> dict:
    log(f"[MARKET] scanning for next {SERIES} market ...")
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


# ── State + trade log ───────────────────────────────────────────────────────
def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {"traded": {}}


def save_state(st: dict) -> None:
    st["traded"] = dict(list(st["traded"].items())[-500:])
    STATE_FILE.write_text(json.dumps(st, indent=1))


_TRADE_COLS = ["timestamp_ct", "ticker", "mark", "action", "direction", "side",
               "price_cents", "ask_cents", "contracts", "dry_run", "order_id",
               "best_move", "gold_current15", "prev_matched", "prev_momentum"]


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
                    row.get("gold_current15", ""), prev_m, prev_mom])


# ── Take-profit seller ─────────────────────────────────────────────────────
async def position_contracts(c: KalshiClient, ticker: str) -> int:
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


async def tp_seller(c: KalshiClient, ticker: str, side: str, mark: datetime) -> None:
    due = max(mark + timedelta(minutes=TP_AT_MIN),
              _now_ct() + timedelta(seconds=30))
    delay = (due - _now_ct()).total_seconds()
    if delay > 0:
        await asyncio.sleep(delay)
    if DRY_RUN:
        log(f"  [DRY] [TP ] {ticker}: would verify position and SELL "
            f"{side.upper()} x{CONTRACTS} @ {TP_CENTS}c")
        log_trade(ticker, mark, {}, side, None, action="sell", price=TP_CENTS)
        return
    pos1 = await position_contracts(c, ticker)
    if pos1 == 0:
        log(f"[TP  ] {ticker}: no open position at market minute {TP_AT_MIN} -- no sell")
        return
    await asyncio.sleep(2)
    pos2 = await position_contracts(c, ticker)
    if pos2 == 0:
        log(f"[TP  ] {ticker}: position vanished on re-check ({pos1} -> 0) -- no sell")
        return
    if (pos1 > 0) != (pos2 > 0):
        log(f"[TP  ] {ticker}: position SIDE changed between checks ({pos1} -> {pos2}) -- aborting sell")
        return
    if pos2 != pos1:
        log(f"[TP  ] {ticker}: position drifted between checks ({pos1} -> {pos2}) -- using latest")
    pos = pos2
    held_side, held = ("yes" if pos > 0 else "no"), abs(pos)
    if held_side != side:
        log(f"[TP  ] {ticker}: held side {held_side.upper()} differs from signal side "
            f"{side.upper()} -- selling what is actually held")
    order = _mk_order(ticker, "sell", held_side, held, TP_CENTS)
    log(f"  [TP ] SELL {held_side.upper()} x{held} @ {TP_CENTS}c  {ticker}  "
        f"(confirmed {pos1}->{pos2})")
    try:
        r = await c.req("POST", ORDER_CREATE_PATH, body=order)
        log(f"  [TP ] resp: {json.dumps(r)[:200]}")
        log_trade(ticker, mark, {}, held_side, r, action="sell",
                  price=TP_CENTS, contracts=held)
    except Exception as e:
        log(f"  [TP ] FAILED: {e}")



# ── Per-market handler ──────────────────────────────────────────────────────
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
    if now >= band_deadline:
        log(f"[SKIP] {ticker}: too late (market closes {close:%H:%M})")
        return
    log(f"[NEW ] {ticker}  mark {mark:%m/%d %H:%M} CT  close {close:%H:%M}")

    prev_mark = mark - timedelta(minutes=15)
    early_stop = asyncio.Event()
    prev0 = read_rows([prev_mark]).get(prev_mark)
    prev_dir = str((prev0 or {}).get("direction", "")).upper()
    if prev_dir in ("LONG", "SHORT"):
        pside = "yes" if prev_dir == "LONG" else "no"
        log(f"[BAND] {ticker}: pre-signal watch on prev-side {pside.upper()} "
            f"({prev_mark:%H:%M} was {prev_dir})")
        asyncio.create_task(early_price_printer(c, ticker, pside, early_stop))

    prev = None
    try:
        ready_at = mark + timedelta(minutes=2)
        if now < ready_at:
            await asyncio.sleep((ready_at - now).total_seconds())
        ensure_refresh(f"mark {mark:%H:%M}")

        check_at = mark + timedelta(seconds=SIGNAL_CHECK_SEC)
        if _now_ct() < check_at:
            await asyncio.sleep((check_at - _now_ct()).total_seconds())
        announced = False
        while _now_ct() < band_deadline:
            rows = read_rows([prev_mark])
            prev = rows.get(prev_mark)
            if prev and str(prev.get("direction", "")).upper() in ("LONG", "SHORT"):
                break
            if not announced:
                log(f"[SIG ] {ticker}: no prev-mark signal yet -- waiting")
                announced = True
            await asyncio.sleep(SIGNAL_POLL_SEC)
    finally:
        early_stop.set()
    if not prev or str(prev.get("direction", "")).upper() not in ("LONG", "SHORT"):
        log(f"[SIG ] {ticker}: no prev-mark signal before deadline -- skipping")
        return

    pm  = str(prev.get("is_matched", "NA")).upper()
    pmm = str(prev.get("momentum",  "NA")).upper()
    prev_direction = str(prev.get("direction", "")).upper()

    try:
        sc = await asyncio.to_thread(score_commodity, "gold15", True)
        overall = sc.get("overall_score", 0)
        sig_txt = sc.get("signal", "NEUTRAL")
        log(f"[SCORE] {ticker}: prev={prev_direction}  commodity score {overall:+d} ({sig_txt})")
    except Exception as e:
        log(f"[SCORE] {ticker}: score check failed ({e}) -- skipping")
        return

    if overall == 0:
        log(f"[SCORE] {ticker}: NEUTRAL score -- skipping")
        return
    direction = "LONG" if overall > 0 else "SHORT"
    side = "yes" if direction == "LONG" else "no"
    log(f"[SIG ] {mark:%H:%M} {direction} (score {overall:+d}, prev {prev_direction})  "
        f"prev best_move={prev.get('best_move')}")

    first_ask = None
    for _ in range(3):
        first_ask = await side_ask_cents(c, ticker, side)
        if first_ask is not None:
            break
        await asyncio.sleep(1)
    band_lo, band_hi = MIN_CENTS, MAX_CENTS
    if first_ask is not None and first_ask > WIDE_TRIGGER_CENTS:
        band_hi = WIDE_MAX_CENTS
        log(f"[BAND] {ticker}: initial {side.upper()} ask {first_ask}c > "
            f"{WIDE_TRIGGER_CENTS}c -- widening band to {band_lo}-{band_hi}c")

    ask = await wait_for_band(c, ticker, side, band_deadline, band_lo, band_hi)
    if ask is None:
        log(f"[BAND] {ticker}: never inside {band_lo}-{band_hi}c before "
            f"{band_deadline:%H:%M:%S} -- skipping")
        return
    log(f"[BAND] {ticker}: {side.upper()} ask {ask}c IN RANGE -- buying @ {band_hi}c limit")

    resp = await place_buy(c, ticker, side, band_hi)
    log_trade(ticker, mark, row, side, resp, pm, pmm, ask, price=band_hi)
    st["traded"][ticker] = f"{mark:%m/%d/%Y %H:%M}"
    save_state(st)
    asyncio.create_task(tp_seller(c, ticker, side, mark))


async def main() -> None:
    log(f"bot_kalshi_gold15 starting  DRY_RUN={DRY_RUN}  contracts={CONTRACTS}  "
        f"entry band {MIN_CENTS}-{MAX_CENTS}c (widen to <={WIDE_MAX_CENTS}c when "
        f"initial ask>{WIDE_TRIGGER_CENTS}c)  "
        f"TP sell @{TP_CENTS}c at market min {TP_AT_MIN}  "
        f"series={SERIES}")
    log(f"auth: key_id ...{API_KEY_ID[-4:] if API_KEY_ID else 'MISSING'}  "
        f"pem={Path(PRIVATE_KEY_PATH).resolve()}  cwd={Path.cwd()}")
    log(f"signal csv: {SIGNAL_CSV}")
    if not SIGNAL_CSV.exists():
        log("[WARN] signal CSV missing -- first refresh will create it")
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
