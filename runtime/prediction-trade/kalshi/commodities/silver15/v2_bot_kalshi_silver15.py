"""
v2_bot_kalshi_silver15.py — Silver 15-minute DMI signal follower for Kalshi KXSILVER15M markets.

Kalshi client + market/order/TP plumbing lifted unchanged from
bot_kalshi_silver15.py (v1). The only thing v2 replaces is the signal: instead
of v1's previous-mark CSV gate + live Yahoo trend/volume score
(commodity_score.py), v2 decides call/put with the DI-dominance DMI engine
ported from the tradier-bot project (runtime/indicators/commodity_dmi.py) —
+DI vs -DI on 1-min bars and on synthesized 2-min bars, tradable only when
both timeframes agree. No CSV, no quarter-bat refresh: the signal is
computed fresh, in-process, each time a market needs one.

  * whenever a NEW SILVER-15 market opens, derive its quarter mark T
  * signal is checked at T+2m30s; direction LONG -> buy YES, SHORT -> buy NO
    — ONLY while the side's ask is inside the price band
  * at market minute TP_AT_MIN, double-confirm position and rest a SELL at TP_CENTS
  * no stop-loss — anything unsold rides to settlement

Run from your ``customers/<name>/`` folder so ``load_dotenv()`` picks up that
folder's ``.env`` (KALSHI_API_KEY_ID, KALSHI_PRIVATE_KEY, BASE_URI).

Env (independent flags so this bot cannot go live by accident):
  BOTSILVER_DRY_RUN    TRUE/FALSE   default TRUE
  BOTSILVER_CONTRACTS  int          default 1
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
        "v2_bot_kalshi_silver15: no .env in the current directory.\n"
        "Launch this bot FROM your customer folder so its credentials + pem resolve:\n"
        "    cd D:\\_projects\\tradier-bot\\customers\\suma\n"
        "    python .../v2_bot_kalshi_silver15.py"
    )
load_dotenv(Path.cwd() / ".env")
load_dotenv()

# ── config ──────────────────────────────────────────────────────────────────
BASE_URI          = os.getenv("BASE_URI", "https://external-api.kalshi.com/trade-api/v2")
API_KEY_ID        = os.getenv("KALSHI_API_KEY_ID", "")
PRIVATE_KEY_PATH  = os.getenv("KALSHI_PRIVATE_KEY", "kalshi_private.pem")
ORDER_CREATE_PATH = os.getenv("KALSHI_ORDER_PATH", "/portfolio/events/orders")
SERIES            = os.getenv("BOTSILVER_SERIES", "KXSILVER15M")

DRY_RUN     = os.getenv("BOTSILVER_DRY_RUN", "TRUE").upper() == "TRUE"
CONTRACTS   = int(os.getenv("BOTSILVER_CONTRACTS", "1"))
MIN_CENTS   = int(os.getenv("BOTSILVER_MIN_CENTS", "35"))
MAX_CENTS   = int(os.getenv("BOTSILVER_MAX_CENTS", "49"))
BUY_AT_CENTS = MAX_CENTS
WIDE_TRIGGER_CENTS = int(os.getenv("BOTSILVER_WIDE_TRIGGER_CENTS", "60"))
WIDE_MAX_CENTS     = int(os.getenv("BOTSILVER_WIDE_MAX_CENTS", "55"))
TP_CENTS    = int(os.getenv("BOTSILVER_TP_CENTS", "90"))
TP_AT_MIN   = int(os.getenv("BOTSILVER_TP_AT_MIN", "10"))
BAND_POLL_SEC    = float(os.getenv("BOTSILVER_BAND_POLL_SEC", "1"))
CLOSE_BUFFER_SEC = int(os.getenv("BOTSILVER_CLOSE_BUFFER_SEC", "180"))

_INDICATORS = Path(__file__).resolve().parents[4] / "indicators"
if str(_INDICATORS) not in sys.path:
    sys.path.insert(0, str(_INDICATORS))
from commodity_dmi import score_commodity_dmi

SIGNAL_CHECK_SEC = int(os.getenv("BOTSILVER_SIGNAL_CHECK_SEC", "150"))
SIGNAL_POLL_SEC  = float(os.getenv("BOTSILVER_SIGNAL_POLL_SEC", "2"))

TRADES_CSV = Path(os.getenv("BOTSILVER_CSV_PATH", "v2_bot_silver15_trades.csv"))
STATE_FILE = Path(os.getenv("BOTSILVER_STATE_PATH", "v2_bot_silver15_state.json"))
LOG_FILE   = Path(os.getenv("BOTSILVER_LOG_PATH", "v2_silver-15.log"))
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
            sys.exit(f"v2_bot_kalshi_silver15: private key not found: {pem}")
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
               "m1_side", "m2_side", "live_price"]


def log_trade(ticker: str, mark: datetime, sc: dict, side: str, resp: dict | None,
              ask: int | None = None, action: str = "buy", price: int | None = None,
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
                    action, sc.get("direction", ""), side,
                    price if price is not None else BUY_AT_CENTS,
                    ask if ask is not None else "",
                    contracts if contracts is not None else CONTRACTS,
                    DRY_RUN, oid, sc.get("m1_side", ""), sc.get("m2_side", ""),
                    sc.get("live_price", "")])


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

    check_at = mark + timedelta(seconds=SIGNAL_CHECK_SEC)
    if _now_ct() < check_at:
        await asyncio.sleep((check_at - _now_ct()).total_seconds())

    sc = None
    while _now_ct() < band_deadline:
        try:
            sc = await asyncio.to_thread(score_commodity_dmi, "silver15", True)
        except Exception as e:
            log(f"[DMI ] {ticker}: score check failed ({e}) -- retrying")
            sc = None
        if sc and sc.get("direction"):
            break
        if sc is not None:
            log(f"[DMI ] {ticker}: bars={sc.get('bars_1m')} "
                f"1m={sc.get('m1_side')} 2m={sc.get('m2_side')} -- no agreement yet")
        await asyncio.sleep(SIGNAL_POLL_SEC)

    if not sc or not sc.get("direction"):
        log(f"[DMI ] {ticker}: no 1m/2m DI agreement before deadline -- skipping")
        return

    direction = sc["direction"]
    side = "yes" if direction == "LONG" else "no"
    log(f"[SIG ] {mark:%H:%M} {direction}  (1m={sc['m1_side']} 2m={sc['m2_side']}  "
        f"price={sc.get('live_price')})")

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
    log_trade(ticker, mark, sc, side, resp, ask, price=band_hi)
    st["traded"][ticker] = f"{mark:%m/%d/%Y %H:%M}"
    save_state(st)
    asyncio.create_task(tp_seller(c, ticker, side, mark))


async def main() -> None:
    log(f"v2_bot_kalshi_silver15 starting  DRY_RUN={DRY_RUN}  contracts={CONTRACTS}  "
        f"entry band {MIN_CENTS}-{MAX_CENTS}c (widen to <={WIDE_MAX_CENTS}c when "
        f"initial ask>{WIDE_TRIGGER_CENTS}c)  "
        f"TP sell @{TP_CENTS}c at market min {TP_AT_MIN}  "
        f"series={SERIES}  engine=DMI(period={9})")
    log(f"auth: key_id ...{API_KEY_ID[-4:] if API_KEY_ID else 'MISSING'}  "
        f"pem={Path(PRIVATE_KEY_PATH).resolve()}  cwd={Path.cwd()}")
    st = load_state()
    c = KalshiClient()
    seen: set[str] = set(st["traded"])
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
