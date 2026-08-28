#!/usr/bin/env python3
"""
bot_kalshi_btc60.py — Kalshi BTC HOURLY-series bot (e.g. "BTC at 6PM EDT").
==========================================================================
A simple hourly bot built on the v1/v3 infrastructure.  Per hour:

  1. Wait 30s, then determine direction via v3.determine_direction_v3
     (Coinbase best-of-3 5/10/15-min signals).
  2. Get support/resistance from the last 24h of 5-min candles
     (get_support_resistance("24h", "5m")).
  3. Get finer support/resistance from the last 1h of 1-min candles
     (get_support_resistance("1h", "1m")).
  4. Within the current hour's event, pick the strike market whose bid for the
     chosen direction is in [ENTRY_BID_LO, ENTRY_BID_HI] (40-50¢) and store its
     strike as `btc_to_beat`.
     4.1 Re-check `btc_to_beat` every RECHECK_S (10s) until an order fills.
     4.2 If `btc_to_beat` changes, cancel pending orders, flatten any position
         on the old market, and re-target the new strike.
  5. Read the live BTC price (Coinbase) and gate on S/R proximity:
     5.1 YES (above X) → enter only when price is within SR_PROXIMITY_USD of a
         SUPPORT level; NO (below X) → near a RESISTANCE level.
     5.2 Size via CONTRACTS_PV_PCT of portfolio value.
     5.3 On fill, place a take-profit sell at KALSHI_PROFIT_PCT.
  6. Monitor until resting orders AND position are both zero.
  7. Wait for the next hour's market and repeat.

Hourly series = KXBTCD.  Each hourly event (e.g. KXBTCD-26JUN1519, which
closes 23:00 UTC = 7PM EDT) holds ~190 "X or above" strike markets
(ticker …-T<strike>, floor_strike=X, strike_type="greater"): YES = BTC ≥ X.
Bids are exposed as yes_bid_dollars / no_bid_dollars.  The near-the-money
strike whose YES bid sits in 40-50¢ is the entry target (its strike →
btc_to_beat).  Override the series via KALSHI_SERIES_60 if needed.

Run:
    python bot_kalshi_btc60.py     (or PLATFORM=kalshi_60 python bot.py)
"""
from __future__ import annotations

import asyncio
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ── Make the shared btc/ package and the v1/v3 modules importable ────────────
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))   # project root → `import btc`
sys.path.insert(0, str(_HERE))          # kalshi/      → `import bot_kalshi_btc15`

# Separate btc60 outputs (set BEFORE importing v1/v3 so their CSV/log binds here).
os.environ.setdefault("BOT_CSV_PATH",   str(_HERE / "btc60_trade_history.csv"))
os.environ.setdefault("BOT_LOG_PREFIX", "kalshi_btc_60_")

import bot_kalshi_btc15 as v1                       # noqa: E402  (infra)
import v3_bot_kalshi_btc15 as v3                    # noqa: E402  (determine_direction_v3)
from btc import BtcVidyaMonitor                     # noqa: E402  (live spot)
from btc.cb_btc_signal import get_support_resistance  # noqa: E402

# ── Reused v1 infrastructure ─────────────────────────────────────────────────
KalshiClient        = v1.KalshiClient
_bid_price          = v1._bid_price
place_buy           = v1.place_buy
await_fill          = v1.await_fill
place_tp_sell       = v1.place_tp_sell
_tp_sl              = v1._tp_sl
_fire_sale          = v1._fire_sale
position_for        = v1.position_for
resting_orders      = v1.resting_orders
cancel_all          = v1.cancel_all
portfolio_balance   = v1.portfolio_balance
init_csv            = v1.init_csv
log_trade           = v1.log_trade
_in_halt_window     = v1._in_halt_window
_halt_and_shutdown  = v1._halt_and_shutdown
_RotatingLogFile    = v1._RotatingLogFile
_Tee                = v1._Tee
_utc_now            = v1._utc_now
_cst_now            = v1._cst_now

DRY_RUN                       = v1.DRY_RUN
CONTRACTS_PV_PCT              = v1.CONTRACTS_PV_PCT
PROFIT_PCT                    = v1.PROFIT_PCT
DO_NOT_BUY_IF_PORTFOLIO_BELOW = v1.DO_NOT_BUY_IF_PORTFOLIO_BELOW
HALT_TIMEZONE                 = v1.HALT_TIMEZONE
FIRE_SALE_CENTS               = v1.FIRE_SALE_CENTS

# ── btc60 config ─────────────────────────────────────────────────────────────
SERIES_60        = os.getenv("KALSHI_SERIES_60", "KXBTCD")  # Kalshi hourly BTC
ENTRY_BID_LO     = int(os.getenv("BTC60_ENTRY_BID_LO", "40"))   # ¢
ENTRY_BID_HI     = int(os.getenv("BTC60_ENTRY_BID_HI", "50"))   # ¢
SR_PROXIMITY_USD = float(os.getenv("BTC60_SR_PROXIMITY_USD", "30"))
RECHECK_S        = int(os.getenv("BTC60_RECHECK_S", "10"))
FILL_TIMEOUT_S   = int(os.getenv("BTC60_FILL_TIMEOUT_S", "30"))
START_DELAY_S    = int(os.getenv("BTC60_START_DELAY_S", "30"))   # step-1 wait
# Hard deadline: buy AND sell must be done by 45 min into the hour (= this many
# minutes BEFORE the event close).  If not, cancel all orders + fire-sell.
EXIT_BEFORE_CLOSE_MIN = int(os.getenv("BTC60_EXIT_BEFORE_CLOSE_MIN", "15"))


def _strike_of(market: dict) -> float | None:
    raw = (market.get("strike_price") or market.get("floor_strike")
           or market.get("cap_strike"))
    try:
        return float(raw) if raw is not None else None
    except Exception:
        return None


def _dir_bid_cents(market: dict, direction: str) -> int | None:
    """Bid (cents) for `direction` from a /markets list entry."""
    raw = market.get(f"{direction}_bid")
    if raw is not None:
        try:
            return int(round(float(raw)))
        except Exception:
            pass
    raw = market.get(f"{direction}_bid_dollars")
    if raw is not None:
        try:
            return int(round(float(raw) * 100))
        except Exception:
            pass
    return None


def _near_any(price: float, levels: list[float], tol: float) -> tuple[bool, float | None]:
    """True + the nearest level if `price` is within `tol` of any level > 0."""
    best = None
    for lv in levels:
        if lv and lv > 0 and abs(price - lv) <= tol:
            if best is None or abs(price - lv) < abs(price - best):
                best = lv
    return (best is not None), best


async def _open_hour_markets(c: KalshiClient) -> list[dict]:
    d = await c.req("GET", "/markets", params={
        "series_ticker": SERIES_60, "status": "open", "limit": 1000,
    })
    return d.get("markets", [])


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


async def wait_for_hour_event(
    c: KalshiClient, after_close: datetime | None,
) -> tuple[str, datetime]:
    """
    Return (event_ticker, close_time) for the SOONEST-closing open KXBTCD
    event whose close_time is in the future and strictly AFTER ``after_close``.

    KXBTCD keeps several hourly events open at once, so we always pick the one
    closing next (the current hour).  Passing the previous event's close_time
    as ``after_close`` advances strictly hour-by-hour to the next market.
    Blocks (polling every 5s) until such an event exists.
    """
    print(f"[MARKET60] waiting for next hourly event (series={SERIES_60}"
          + (f", after {after_close.strftime('%H:%MZ')}" if after_close else "")
          + ") …")
    while True:
        try:
            now = _utc_now()
            closes: dict[str, datetime] = {}   # event → earliest market close
            for m in await _open_hour_markets(c):
                ev = m.get("event_ticker")
                ct = _parse_dt(m.get("close_time"))
                if not ev or ct is None or ct <= now:
                    continue
                if after_close is not None and ct <= after_close:
                    continue
                if ev not in closes or ct < closes[ev]:
                    closes[ev] = ct
            if closes:
                ev = min(closes, key=lambda k: closes[k])
                print(f"[MARKET60] ✓ event {ev} (closes "
                      f"{closes[ev].strftime('%Y-%m-%d %H:%MZ')})")
                return ev, closes[ev]
        except Exception as e:
            print(f"[MARKET60] poll error: {e}")
        await asyncio.sleep(5)


async def find_target_market(c: KalshiClient, event: str, direction: str
                             ) -> tuple[str, float, int] | None:
    """
    Among the event's open strike markets, return (ticker, strike, bid_cents)
    for the one whose `direction` bid is in [ENTRY_BID_LO, ENTRY_BID_HI],
    preferring the bid closest to the band midpoint.  None if no match.
    """
    best = None  # (distance_to_mid, ticker, strike, bid)
    mid = (ENTRY_BID_LO + ENTRY_BID_HI) / 2
    for m in await _open_hour_markets(c):
        if (m.get("event_ticker") or m.get("ticker")) != event:
            continue
        strike = _strike_of(m)
        bid = _dir_bid_cents(m, direction)
        if strike is None or bid is None:
            continue
        if ENTRY_BID_LO <= bid <= ENTRY_BID_HI:
            dist = abs(bid - mid)
            if best is None or dist < best[0]:
                best = (dist, m["ticker"], strike, bid)
    return (best[1], best[2], best[3]) if best else None


async def _flatten(c: KalshiClient, ticker: str, direction: str) -> None:
    """Cancel resting orders and fire-sell any open position on `ticker`."""
    try:
        await cancel_all(c)
        await asyncio.sleep(1)
        pos = await position_for(c, ticker)
        if pos and pos["contracts"] > 0:
            print(f"  [FLAT] fire-selling {pos['contracts']} on {ticker}")
            await _fire_sale(c, ticker, direction, pos["contracts"])
            await asyncio.sleep(2)
    except Exception as e:
        print(f"  [FLAT] failed: {e}")


async def _wait_flat(c: KalshiClient, ticker: str, direction: str,
                     deadline: datetime) -> str:
    """
    Wait until the position AND resting orders are both zero on `ticker`
    (i.e. the TP sell filled).  If still holding at ``deadline`` (the 45-min
    mark), cancel all orders and FIRE-SELL the position.

    Returns "FLAT" if it exited cleanly, "DEADLINE_FIRESELL" if forced out.
    """
    while _utc_now() < deadline:
        pos = await position_for(c, ticker)
        pending = await resting_orders(c, ticker)
        n = pos["contracts"] if pos else 0
        if n == 0 and not pending:
            print(f"  [MON60] flat on {ticker} — position 0, no resting orders.")
            return "FLAT"
        print(f"  [MON60] holding {n}, resting {len(pending)}  "
              f"(deadline {deadline.strftime('%H:%MZ')}) — waiting …")
        await asyncio.sleep(RECHECK_S)

    # Deadline reached.  Fire-sell ONLY if an active position exists for THIS
    # market; otherwise just cancel any leftover resting orders.
    pos = await position_for(c, ticker)
    n = pos["contracts"] if pos else 0
    if n > 0:
        print(f"  [MON60] 45-min deadline ({deadline.strftime('%H:%MZ')}) — active "
              f"{n} on {ticker}; cancel all + fire-sell.")
        await _flatten(c, ticker, direction)
        return "DEADLINE_FIRESELL"
    print(f"  [MON60] 45-min deadline ({deadline.strftime('%H:%MZ')}) — no active "
          f"position on {ticker}; cancelling any resting orders only.")
    try:
        await cancel_all(c)
    except Exception as e:
        print(f"  [MON60] cancel_all failed: {e}")
    return "DEADLINE_NO_POSITION"


# ╔════════════════════════════════════════════════════════════════════════════╗
# ║  MAIN LOOP                                                               ║
# ╚════════════════════════════════════════════════════════════════════════════╝
async def run() -> None:
    _log_fh    = _RotatingLogFile()
    sys.stdout = _Tee(sys.__stdout__, _log_fh)
    sys.stderr = _Tee(sys.__stderr__, _log_fh)
    print(f"[LOG] btc60 session started — logging to {_log_fh.name}")
    print(f"[CFG] series={SERIES_60}  bid-band={ENTRY_BID_LO}-{ENTRY_BID_HI}¢  "
          f"SR±${SR_PROXIMITY_USD:.0f}  CONTRACTS_PV_PCT={CONTRACTS_PV_PCT}  "
          f"PROFIT_PCT={PROFIT_PCT}  DRY_RUN={DRY_RUN}")

    init_csv()
    c = KalshiClient()
    btc = BtcVidyaMonitor()
    btc.start()

    last_close: datetime | None = None
    try:
        while True:
            # ── Step 7 entry point: wait for the (next) hour's event ─────────
            # Picks the soonest-closing open event that closes AFTER the one we
            # just traded → strict hour-by-hour advance (KXBTCD keeps several
            # hourly events open concurrently).
            event, event_close = await wait_for_hour_event(c, after_close=last_close)

            # ── Step 1: settle 30s, then determine direction ────────────────
            await asyncio.sleep(START_DELAY_S)
            direction, live_dir_btc, score = await v3.determine_direction_v3(c)
            print(f"  [DIR60] {direction.upper()} (score {score:+d})")

            # ── Steps 2 & 3: support/resistance (24h/5m and 1h/1m) ──────────
            sr24 = await get_support_resistance("24h", "5m", verbose=False)
            sr1  = await get_support_resistance("1h", "1m", verbose=False)
            supports    = [sr24["S1"], sr24["S2"], sr24["S3"],
                           sr1["S1"],  sr1["S2"],  sr1["S3"]]
            resistances = [sr24["R1"], sr24["R2"], sr24["R3"],
                           sr1["R1"],  sr1["R2"],  sr1["R3"]]
            print(f"  [SR60] supports={[s for s in supports if s]}")
            print(f"  [SR60] resistances={[r for r in resistances if r]}")

            # ── Steps 4 & 5: re-target + S/R-gated entry until filled ───────
            filled = False
            target_ticker: str | None = None
            target_strike: float | None = None
            btc_to_beat: float | None = None
            entry_bid = 0
            _buy_contracts = 0
            resp = None

            # Hard 45-min deadline (EXIT_BEFORE_CLOSE_MIN before close): both
            # the buy and the sell must be done by here, else cancel + fire-sell.
            entry_deadline = event_close - timedelta(minutes=EXIT_BEFORE_CLOSE_MIN)

            while not filled:
                if _utc_now() >= entry_deadline:
                    print(f"  [ENTRY60] 45-min deadline "
                          f"({entry_deadline.strftime('%H:%MZ')}) reached, no fill "
                          f"— cancel all + abandon this hour.")
                    if target_ticker is not None:
                        await _flatten(c, target_ticker, direction)
                    else:
                        await cancel_all(c)
                    break

                found = await find_target_market(c, event, direction)
                if found is None:
                    print(f"  [ENTRY60] no {direction.upper()} strike with bid in "
                          f"{ENTRY_BID_LO}-{ENTRY_BID_HI}¢ — waiting …")
                    await asyncio.sleep(RECHECK_S)
                    continue
                tk, strike, bid = found

                # 4.2 btc_to_beat changed → flatten old, re-target.
                if target_ticker is not None and tk != target_ticker:
                    print(f"  [ENTRY60] btc_to_beat changed "
                          f"{btc_to_beat}→{strike} — flattening old & re-targeting.")
                    await _flatten(c, target_ticker, direction)
                target_ticker, target_strike, btc_to_beat, entry_bid = tk, strike, strike, bid
                print(f"  [ENTRY60] target {tk}  strike(btc_to_beat)={strike:,.0f}  "
                      f"{direction}_bid={bid}¢")

                # 5.x S/R proximity gate on the live Coinbase price.
                price = btc.last_price
                if price is None:
                    await asyncio.sleep(RECHECK_S)
                    continue
                if direction == "yes":
                    near, lvl = _near_any(price, supports, SR_PROXIMITY_USD)
                    zone = "support"
                else:
                    near, lvl = _near_any(price, resistances, SR_PROXIMITY_USD)
                    zone = "resistance"
                if not near:
                    print(f"  [ENTRY60] live ${price:,.0f} not within "
                          f"${SR_PROXIMITY_USD:.0f} of a {zone} — waiting …")
                    await asyncio.sleep(RECHECK_S)
                    continue
                print(f"  [ENTRY60] live ${price:,.0f} near {zone} ${lvl:,.0f} — "
                      f"placing {direction.upper()} order.")

                # 5.2 size via CONTRACTS_PV_PCT.
                pv = await portfolio_balance(c)
                if pv < DO_NOT_BUY_IF_PORTFOLIO_BELOW:
                    await _halt_and_shutdown(
                        c, target_ticker, reason_tag="MIN-PV HALT",
                        reason_msg=(f"Portfolio ${pv:.2f} < "
                                    f"${DO_NOT_BUY_IF_PORTFOLIO_BELOW} — halting."))
                    return
                _peek = max(0.01, entry_bid / 100.0)
                _buy_contracts = max(1, math.ceil((CONTRACTS_PV_PCT / 100.0 * pv) / _peek))
                print(f"  [SIZE60] {CONTRACTS_PV_PCT}% of ${pv:.2f} ÷ {_peek:.2f} "
                      f"= {_buy_contracts} contracts")

                resp = await place_buy(c, target_ticker, direction,
                                       buy_at_cents=entry_bid, contracts=_buy_contracts)
                if resp is None:
                    await asyncio.sleep(RECHECK_S)
                    continue

                if await await_fill(c, target_ticker, timeout=FILL_TIMEOUT_S):
                    filled = True
                else:
                    print("  [ENTRY60] not filled — cancel & re-check btc_to_beat.")
                    await cancel_all(c)
                    await asyncio.sleep(RECHECK_S)

            if filled and resp is not None:
                # ── 5.3: avg cost + take-profit sell ────────────────────────
                odata = resp.get("order", {})
                cost_str = odata.get("taker_fill_cost_dollars", "0")
                fee_str  = odata.get("taker_fees_dollars", "0")
                fill_cost = round(float(cost_str) + float(fee_str), 4)
                if fill_cost < 0.5:
                    fill_cost = round((entry_bid / 100.0) * _buy_contracts, 4)
                entry_total = fill_cost
                avg_cents = int(round(float(fill_cost / _buy_contracts), 2) * 100)
                tp_cents, sl_total = _tp_sl(avg_cents, _buy_contracts)
                print(f"  Entry: {_buy_contracts} × {avg_cents}¢ = ${entry_total:.2f}  "
                      f"|  TP {tp_cents}¢")

                pos = await position_for(c, target_ticker)
                real_contracts = pos["contracts"] if (pos and pos["contracts"] > 0) else _buy_contracts
                # The held position must match the size we bought before we rest
                # the TP sell.  A mismatch means the buy is only partially filled
                # (the rest is still resting) — wait for it to complete, then
                # re-read so the TP covers every contract we actually hold.
                if real_contracts != _buy_contracts:
                    print(f"  [TP] position {real_contracts} != bought "
                          f"{_buy_contracts} — awaiting full fill ...")
                    await await_fill(c, target_ticker, timeout=FILL_TIMEOUT_S)
                    pos = await position_for(c, target_ticker)
                    real_contracts = (pos["contracts"]
                                      if (pos and pos["contracts"] > 0) else _buy_contracts)
                    print(f"  [TP] position now {real_contracts}")
                await place_tp_sell(c, target_ticker, direction, real_contracts, tp_cents)

                # ── Step 6: monitor until flat, or fire-sell at the 45-min mark
                flat_reason = await _wait_flat(c, target_ticker, direction,
                                               entry_deadline)
                # Exit price/result by how we left the position:
                #   FLAT / DEADLINE_NO_POSITION → position closed (TP) ≈ tp_cents
                #   DEADLINE_FIRESELL           → forced fire-sell    ≈ 5¢
                if flat_reason == "DEADLINE_FIRESELL":
                    exit_cents, result = FIRE_SALE_CENTS, "BTC60_DEADLINE_FIRESELL"
                else:
                    exit_cents, result = tp_cents, "BTC60_TP"

                # ── log the trade ───────────────────────────────────────────
                try:
                    pv_after = await portfolio_balance(c)
                    exit_total = (exit_cents / 100.0) * real_contracts
                    log_trade(
                        ticker=target_ticker, mode="BUY", direction=direction,
                        contracts=real_contracts, entry=avg_cents,
                        exit_=exit_total, pnl=exit_total - entry_total,
                        result=result, pv=pv_after,
                        btc_to_beat=btc_to_beat, btc_spot_at_buy=btc.last_price,
                        btc_spot_at_sell=btc.last_price,
                    )
                except Exception as e:
                    print(f"  [LOG60] log_trade failed: {e}")

            # ── Step 7: advance to the next hour's market ───────────────────
            # Record this event's close so the next wait_for_hour_event picks
            # the event closing AFTER it (i.e. the next hour).
            last_close = event_close
            await asyncio.sleep(5)
    finally:
        try:
            await btc.stop()
        except Exception:
            pass
        try:
            await c.close()
        except Exception:
            pass
        try:
            _log_fh.close()
        except Exception:
            pass


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
