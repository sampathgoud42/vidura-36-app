#!/usr/bin/env python3
"""
monitor_bot.py — independent YES/NO bid-price logger for Kalshi BTC markets.
============================================================================
Every POLL_S seconds (default 15s):

  • Kalshi BTC-15 (KXBTC15M) → kbtc-15.log — the current 15-min binary's YES/NO
    bid, one header per window then a [bid-price] line each tick:
        [KXBTC15M-26JUN180015-15] [yes and no] bid price live data for every 15 seconds
        [bid-price] [18:46:15] ['yes': 58, 'no':41]

  • Kalshi BTC 1H (KXBTCD) → kbtc-60.log — for the CLOCK-BASED current-hour event
    (same build_hour_event as bot_kalshi_btc60_liquidity), three blocks each tick:
        [BTC 01:55:30] spot=$63,674.11  fast=$63,675.34  slow=$63,677.38  votes B/S=0/3  CUSUM=HOLD  buf=24/120  → SELL
        [LSR 01:55:30] LIVE: 63,680 **POC : 63,378 (Green)** S/R : {S1=63,678, ... R1=63,757}
        [LSR ENTRY60L 01:55:30] [KXBTCD-26JUN2004-T63699.99 strike=63,700]  [bid-price] ['yes': 30, 'no':70]
        [LSR ENTRY60L 01:55:30] [KXBTCD-26JUN2004-T63799.99 strike=63,800]  [bid-price] ['yes': 51, 'no':49]
    The [LSR ENTRY60L] lines cover every strike whose YES or NO bid is in
    [SUB_BID_LO, SUB_BID_HI] (default 30-65c).

Bids arrive as ``{side}_bid`` (cents) or ``{side}_bid_dollars`` (dollars); both
are handled.

All timestamps are Central US time (CST/CDT, America/Chicago).  Auth + HTTP
reuse the v1 ``KalshiClient`` (RSA-PSS request signing); only read-only GETs are
made, so this never places or cancels orders.

Run:
    python monitor_bot.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# ── Reuse the v1 KalshiClient (auth + signed GETs) ────────────────────────────
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))            # project root → `import btc`
sys.path.insert(0, str(_HERE / "kalshi"))

import bot_kalshi_btc15 as v1            # noqa: E402  (auth/client infra)
from btc import BtcVidyaMonitor          # noqa: E402  (live BTC signal)
from btc.liquidity_sr import run as lsr_run   # noqa: E402  (POC / S-R / bias)

KalshiClient = v1.KalshiClient
_utc_now     = v1._utc_now
_cst_now     = v1._cst_now
_CST         = v1._CST                                # ZoneInfo("America/Chicago")

# ── Config ────────────────────────────────────────────────────────────────────
SERIES_15 = os.getenv("MON_SERIES_15", "KXBTC15M")   # Kalshi BTC-15
SERIES_60 = os.getenv("MON_SERIES_60", "KXBTCD")     # Kalshi BTC hourly
POLL_S    = int(os.getenv("MON_POLL_S", "15"))       # sample cadence (seconds)
LOG_15    = _HERE / os.getenv("MON_LOG_15", "kbtc-15.log")
LOG_60    = _HERE / os.getenv("MON_LOG_60", "kbtc-60.log")

# Hourly (KXBTCD) submarket scan: in kbtc-60.log, list every strike in the
# current-hour event whose YES or NO bid is in [SUB_BID_LO, SUB_BID_HI] cents.
SUB_BID_LO        = int(os.getenv("MON_SUB_BID_LO", "30"))
SUB_BID_HI        = int(os.getenv("MON_SUB_BID_HI", "65"))

# Clock-based current-hour event — identical logic to bot_kalshi_btc60_liquidity:
# the hour's KXBTCD contract settles at the NEXT top of the hour (Eastern), and
# the event ticker encodes that settlement date+hour (SERIES_60-YYMONDDHH).
_ET  = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")
_MON = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
        "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def _settlement_dt(now_et: datetime) -> datetime:
    floored = now_et.replace(minute=0, second=0, microsecond=0)
    return floored if now_et == floored else floored + timedelta(hours=1)


def build_hour_event(now_utc: datetime | None = None) -> tuple[str, datetime]:
    """(event_ticker, close_time_utc) for the current hour, from the clock."""
    now_utc = now_utc or _utc_now()
    settle_et = _settlement_dt(now_utc.astimezone(_ET))
    ticker = (f"{SERIES_60}-{settle_et.year % 100:02d}{_MON[settle_et.month - 1]}"
              f"{settle_et.day:02d}{settle_et.hour:02d}")
    return ticker, settle_et.astimezone(_UTC)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _bid_cents(m: dict, side: str) -> int | None:
    """YES/NO bid in whole cents from a market dict ({side}_bid or _dollars)."""
    raw = m.get(f"{side}_bid")
    if raw is not None:
        try:
            return int(round(float(raw)))
        except Exception:
            pass
    raw = m.get(f"{side}_bid_dollars")
    if raw is not None:
        try:
            return int(round(float(raw) * 100))
        except Exception:
            pass
    return None


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _cst_str(dt: datetime | None, fmt: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    """Render any datetime in Central (CST/CDT)."""
    if dt is None:
        return "?"
    return dt.astimezone(_CST).strftime(fmt)


def _append(path: Path, line: str) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


async def _open_markets(c: KalshiClient, series: str) -> list[dict]:
    d = await c.req("GET", "/markets", params={
        "series_ticker": series, "status": "open", "limit": 1000,
    })
    return d.get("markets", [])


def _pick_soonest(markets: list[dict]) -> dict | None:
    """KXBTC15M: the open market whose close_time is nearest in the future."""
    now = _utc_now()
    best, best_ct = None, None
    for m in markets:
        ct = _parse_dt(m.get("close_time"))
        if ct is None or ct <= now:
            continue
        if best is None or ct < best_ct:
            best, best_ct = m, ct
    return best


def _strike_of(market: dict) -> float | None:
    raw = (market.get("strike_price") or market.get("floor_strike")
           or market.get("cap_strike"))
    try:
        return float(raw) if raw is not None else None
    except Exception:
        return None


def _btc_line(btc, ts: str) -> str:
    """Reconstruct the BtcVidyaMonitor signal line for the log."""
    price = getattr(btc, "last_price", None)
    fast = getattr(btc, "last_fast", None)
    slow = getattr(btc, "last_slow", None)
    votes = getattr(btc, "last_votes", (0, 0)) or (0, 0)
    cusum = (getattr(btc, "last_cusum", "hold") or "hold").upper()
    buf = getattr(btc, "buf", None)
    bufn = len(buf) if buf is not None else 0
    win = getattr(btc, "WINDOW_SIZE", 0)
    sig = (getattr(btc, "signal", "hold") or "hold").upper()
    spot = f"${price:,.2f}" if price else "N/A"
    fs = f"${fast:,.2f}" if fast else "N/A"
    ss = f"${slow:,.2f}" if slow else "N/A"
    return (f"[BTC {ts}] spot={spot}  fast={fs}  slow={ss}  "
            f"votes B/S={votes[0]}/{votes[1]}  CUSUM={cusum}  "
            f"buf={bufn}/{win}  → {sig}")


def _lsr_line(lsr: dict, btc, ts: str) -> str:
    """Reconstruct the LiquiditySR LIVE/POC/S-R line for the log."""
    live = getattr(btc, "last_price", None) or lsr.get("live_price")
    live_str = f"{live:,.0f}" if live else "n/a"
    poc = lsr.get("poc")
    poc_str = f"{poc['price']:,.0f} ({poc['color']})" if poc else "n/a"
    sr_str = ", ".join(
        f"{x['label']}={x['price']:,.0f}" + (" *POC" if x["is_poc"] else "")
        for x in lsr.get("levels", [])) or "n/a"
    return f"[LSR {ts}] LIVE: {live_str} **POC : {poc_str}** S/R : {{{sr_str}}}"


async def monitor_hourly_60(c: KalshiClient, btc, log_path: Path) -> None:
    """
    Every POLL_S, append to kbtc-60.log (for the clock-based current-hour event):
      • the BTC signal line,
      • the LiquiditySR LIVE/POC/S-R line,
      • one [LSR ENTRY60L] line per strike whose YES or NO bid is in
        [SUB_BID_LO, SUB_BID_HI].
    """
    last_event: str | None = None
    while True:
        timer = asyncio.create_task(asyncio.sleep(POLL_S))   # drift-free cadence
        try:
            ts = _cst_now().strftime("%H:%M:%S")
            cur_ev, ev_close = build_hour_event()
            if cur_ev != last_event:
                last_event = cur_ev
                print(f"[KBTC60] monitoring {cur_ev} (closes {_cst_str(ev_close)})",
                      flush=True)

            # 1) BTC signal line
            _append(log_path, _btc_line(btc, ts))

            # 2) LiquiditySR line
            try:
                lsr = await lsr_run(verbose=False)
                _append(log_path, _lsr_line(lsr, btc, ts))
            except Exception as e:
                _append(log_path, f"[LSR {ts}] error: {e}")

            # 3) in-range submarket bids for the current event
            n = 0
            for m in await _open_markets(c, SERIES_60):
                if m.get("event_ticker") != cur_ev:
                    continue
                strike = _strike_of(m)
                if strike is None:
                    continue
                yes = _bid_cents(m, "yes")
                no = _bid_cents(m, "no")
                in_range = ((yes is not None and SUB_BID_LO <= yes <= SUB_BID_HI)
                            or (no is not None and SUB_BID_LO <= no <= SUB_BID_HI))
                if not in_range:
                    continue
                _append(log_path, f"[LSR ENTRY60L {ts}] [{m['ticker']} "
                        f"strike={strike:,.0f}]  [bid-price] "
                        f"['yes': {yes}, 'no':{no}]")
                n += 1
            print(f"[KBTC60] {ts} logged BTC/LSR + {n} submarkets", flush=True)
        except Exception as e:
            print(f"[KBTC60] error: {e}", flush=True)
        await timer


async def monitor_series(c: KalshiClient, series: str, log_path: Path,
                         picker, label: str) -> None:
    """Lock onto the current market for `series`, log YES/NO bids every POLL_S."""
    cur_ticker: str | None = None
    cur_close: datetime | None = None

    while True:
        timer = asyncio.create_task(asyncio.sleep(POLL_S))   # drift-free cadence
        try:
            now = _utc_now()
            # (Re)select whenever we have no market, the current one has closed,
            # or a newer market has taken over → continuously rolls onto new
            # markets as they open.
            need_pick = (cur_ticker is None or cur_close is None
                         or now >= cur_close)
            if need_pick:
                m = picker(await _open_markets(c, series))
                if m is None:
                    print(f"[{label}] no open market - waiting for one to open ...",
                          flush=True)
                    cur_ticker, cur_close = None, None
                    await timer
                    continue
                cur_ticker = m["ticker"]
                cur_close = _parse_dt(m.get("close_time"))
                hdr = (f"[{cur_ticker}] [yes and no] bid price live data "
                       f"for every {POLL_S} seconds")
                _append(log_path, hdr)
                print(f"[{label}] monitoring {cur_ticker} "
                      f"(closes {_cst_str(cur_close)})", flush=True)

            # Freshest bids straight from the single-market endpoint.
            md = await c.req("GET", f"/markets/{cur_ticker}")
            mk = md.get("market", {})

            # Refresh close + detect an early/settled close → roll next tick.
            ct2 = _parse_dt(mk.get("close_time"))
            if ct2:
                cur_close = ct2
            status = str(mk.get("status") or "").lower()
            if status in ("closed", "settled", "finalized", "determined",
                          "inactive", "canceled", "cancelled"):
                print(f"[{label}] {cur_ticker} status={status} - rolling to next",
                      flush=True)
                cur_ticker, cur_close = None, None
                await timer
                continue

            yes = _bid_cents(mk, "yes")
            no = _bid_cents(mk, "no")
            ts = _cst_now().strftime("%H:%M:%S")        # Central time
            line = f"[bid-price] [{ts}] ['yes': {yes}, 'no':{no}]"
            _append(log_path, line)
            print(f"[{label}] {cur_ticker}  {line}", flush=True)
        except Exception as e:
            print(f"[{label}] error: {e}", flush=True)
        await timer


async def run() -> None:
    print(f"[MON] start - {SERIES_15}->{LOG_15.name}, {SERIES_60}->{LOG_60.name}, "
          f"every {POLL_S}s (read-only)", flush=True)
    c = KalshiClient()
    btc = BtcVidyaMonitor()
    btc.start()
    try:
        await asyncio.gather(
            monitor_series(c, SERIES_15, LOG_15, _pick_soonest, "KBTC15"),
            monitor_hourly_60(c, btc, LOG_60),
        )
    finally:
        try:
            await btc.stop()
        except Exception:
            pass
        try:
            await c.close()
        except Exception:
            pass


def main() -> None:
    # UTF-8 stdout/stderr so unicode (e.g. the BTC "→") never crashes on cp1252.
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n[MON] stopped.", flush=True)


if __name__ == "__main__":
    main()
