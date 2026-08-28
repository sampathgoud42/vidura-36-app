# Kalshi BTC Hourly Bot — `bot_kalshi_btc60.py`

Hourly-series companion to the BTC-15 bot. It trades Kalshi's **`KXBTCD`** series
("BTC at `<hour>` EDT") one hour at a time, reusing the v1 infrastructure
(`KalshiClient`, order/fill/position helpers, CSV + rotating log) and the v3
direction engine (Coinbase best-of-3).

> Direction comes from Coinbase momentum (`v3.determine_direction_v3`); entries
> are gated on support/resistance proximity; every hour is force-flat by the
> 45-minute mark.

---

## Run

```bash
# standalone
cd kalshi/
python bot_kalshi_btc60.py

# or via the root dispatcher
PLATFORM=kalshi_60 python bot.py
```

Outputs (written next to the bot unless `BOT_CSV_PATH` / `BOT_LOG_*` override):

| File | What |
|---|---|
| `btc60_trade_history.csv` | one row per completed hour (shared schema with v1) |
| `kalshi_btc_60_YYYYMMDD.log` | daily rotating console log (Central time) |

---

## The `KXBTCD` market structure

`KXBTCD` keeps **many hourly events open at once**, each settling at a specific
top-of-hour (the ticker suffix is the EDT close hour):

```
KXBTCD-26JUN1519   → closes 23:00Z = 7PM EDT
KXBTCD-26JUN1817   → closes 21:00Z = 5PM EDT
```

Each event holds ~80–190 **strike markets** (`…-T<strike>`,
`floor_strike = X`, `strike_type = "greater"`) — YES pays if BTC ≥ X at close.
Bids surface as `yes_bid` / `no_bid` (cents) or `yes_bid_dollars` /
`no_bid_dollars` (the bot reads either).

- **Current hour** = the *soonest-closing* open event.
- The chosen strike's `floor_strike` is stored as **`btc_to_beat`**.

---

## Configuration

### btc60-specific (`.env`)

| Variable | Default | Description |
|---|---|---|
| `KALSHI_SERIES_60` | `KXBTCD` | Hourly series ticker |
| `BTC60_ENTRY_BID_LO` | `40` | Min bid (¢) for the chosen-direction strike |
| `BTC60_ENTRY_BID_HI` | `50` | Max bid (¢) for the chosen-direction strike |
| `BTC60_SR_PROXIMITY_USD` | `30` | Live BTC must be within this of an S/R level to enter |
| `BTC60_RECHECK_S` | `10` | Re-target / re-check interval (s) |
| `BTC60_FILL_TIMEOUT_S` | `30` | Wait for a buy to fill before re-checking (s) |
| `BTC60_START_DELAY_S` | `30` | Settle time after an hour becomes current (s) |
| `BTC60_EXIT_BEFORE_CLOSE_MIN` | `15` | Hard deadline = close − this (i.e. 45 min into the hour) |

### Reused from v1 (`bot_kalshi_btc15.py`)

| Variable | Purpose in btc60 |
|---|---|
| `DRY_RUN_MODE` | `TRUE` → simulate orders (no POST); GETs still hit the API |
| `CONTRACTS_PV_PCT` | Position size = this % of portfolio value ÷ entry price |
| `KALSHI_PROFIT_PCT` | Take-profit target % above entry (TP capped at 91¢) |
| `KALSHI_STOP_PCT` | Used by `_tp_sl` to compute the stop notional |
| `DO_NOT_BUY_IF_PORTFOLIO_BELOW` | MIN-PV floor; trips the halt below |
| `FIRE_SALE_CENTS` | Price used for forced fire-sells (~5¢) |

> **Halts:** the hourly loop enforces **only** the MIN-PV floor
> (`DO_NOT_BUY_IF_PORTFOLIO_BELOW`) — on breach it cancels, flattens, and (if
> `HALT_MACHINE_SHUTDOWN=TRUE`) shuts down. It does **not** apply v1's
> time-window or `TARGET_PORTFOLIO_PCT` halts.

---

## Per-hour flow

```
        ┌──────────────────────────────────────────────────────────────┐
        │ wait_for_hour_event(after_close=last_close)                   │
        │   → soonest-closing open KXBTCD event closing AFTER the last  │
        │     one traded  (strict hour-by-hour advance)                 │
        └───────────────────────────────┬──────────────────────────────┘
                                         │
                 (1) sleep START_DELAY_S (30s)
                                         │
                 (1) determine_direction_v3(c) → YES | NO  (+score)
                                         │   Coinbase best-of-3 (5/10/15-min)
                                         │
                 (2) get_support_resistance("24h","5m")   ── supports[]/
                 (3) get_support_resistance("1h","1m")       resistances[]
                                         │
        ┌────────────────────────────────▼─────────────────────────────┐
        │ ENTRY LOOP   (until filled, or entry_deadline reached)        │
        │ entry_deadline = event_close − EXIT_BEFORE_CLOSE_MIN          │
        │                                                              │
        │  (4)  find_target_market(event, direction)                   │
        │        → strike whose {direction}_bid ∈ [40,50]¢, nearest    │
        │          the band midpoint;  strike → btc_to_beat            │
        │  (4.2) btc_to_beat changed?  → flatten old strike, re-target │
        │                                                              │
        │  (5)  S/R proximity gate on live Coinbase price:             │
        │         YES → within $30 of a SUPPORT                        │
        │         NO  → within $30 of a RESISTANCE                     │
        │        not near → wait RECHECK_S and re-loop                 │
        │                                                              │
        │  (5.1) pv < MIN-PV floor?  → HALT + (optional) shutdown      │
        │  (5.2) size = ceil(CONTRACTS_PV_PCT% × pv ÷ entry_price)     │
        │  (5.2) place_buy(strike, direction, entry_bid, size)         │
        │        await_fill(FILL_TIMEOUT_S)                            │
        │          filled → exit loop;  not filled → cancel, re-check  │
        └────────────────────────────────┬─────────────────────────────┘
                                         │ filled
                 (5.3) TP = entry_avg × (1+PROFIT_PCT%), cap 91¢
                       place_tp_sell(strike, direction, contracts, TP)
                                         │
        ┌────────────────────────────────▼─────────────────────────────┐
        │ (6) _wait_flat(strike, deadline)                             │
        │      poll position + resting orders until both 0 (TP filled) │
        │      at entry_deadline (45-min mark):                        │
        │        active position?  → cancel all + FIRE-SELL            │
        │        no position?      → cancel any resting orders only    │
        └────────────────────────────────┬─────────────────────────────┘
                                         │
                 result = BTC60_TP  (exit≈TP)   |  BTC60_DEADLINE_FIRESELL (exit≈5¢)
                 log_trade(...) → btc60_trade_history.csv
                                         │
                 (7) last_close = event_close;  sleep 5s;  loop
```

### Step notes

- **Step 1 — direction.** `determine_direction_v3` returns `YES` when Coinbase
  5/10/15-min momentum leans bullish, else `NO`. The 30s settle lets the new
  hour's book populate first.
- **Steps 2–3 — S/R.** Six supports and six resistances are pooled from the
  24h/5m and 1h/1m floor-trader pivots.
- **Step 4 — target + `btc_to_beat`.** Among the current event's strikes, the
  one whose **chosen-direction** bid is in 40–50¢ (closest to 45) is the target;
  its strike is `btc_to_beat`. If a different strike enters the band on a later
  pass, the bot **flattens the old one and re-targets** (4.2).
- **Step 5 — S/R gate + sizing.** Entry only fires when live BTC is within
  `$SR_PROXIMITY_USD` of a *support* (YES) or *resistance* (NO). Size scales
  with portfolio value and the entry price.
- **Step 5.3 / 6 — exit.** A take-profit sell is rested immediately on fill;
  the position must be flat by the **45-minute mark** (`close − 15 min`) or it's
  force-flattened via fire-sell. Result is logged as `BTC60_TP` or
  `BTC60_DEADLINE_FIRESELL`.
- **Step 7 — advance.** `last_close = event_close` guarantees the next
  `wait_for_hour_event` selects the *next* hour, even though many events are
  open concurrently.

---

## Dry-run trace (annotated)

Captured with `DRY_RUN_MODE=TRUE` (no real orders placed):

```
[CFG] series=KXBTCD  bid-band=40-50¢  SR±$30  CONTRACTS_PV_PCT=15.0  PROFIT_PCT=20.0  DRY_RUN=True
[MARKET60] ✓ event KXBTCD-26JUN1817 (closes 2026-06-18 21:00Z)     ← current hour
  [DIR v3] best-of-3 → NO  (majority NO (3/0))                      ← step 1
  [DIR v3]   5m=SELL 🔴  10m=SELL 🔴  15m=SELL 🔴  score=-2  live=$64,286.48
  [SR60] supports=[63297.0, 62307.51, 60764.01, 64102.32, ...]     ← steps 2-3
  [SR60] resistances=[65829.99, 67373.49, 68362.98, 64560.16, ...]
  [ENTRY60] target KXBTCD-26JUN1817-T64249.99  strike(btc_to_beat)=64,250  no_bid=47¢   ← step 4
  [ENTRY60] live $64,289 not within $30 of a resistance — waiting …                     ← step 5 gate held
```

Here direction is **NO**, so it looks for live BTC near a **resistance**; at
\$64,289 the nearest resistance (\$64,560) is >\$30 away, so it correctly
**waits** rather than entering. It re-checks every `RECHECK_S` until either the
gate passes (→ buy) or the 45-min deadline aborts the hour.

---

## Known issue — Windows console encoding

On Windows, when stdout is a `cp1252` console **or redirected to a file**,
printing the `✓` (U+2713) in `wait_for_hour_event` raises
`'charmap' codec can't encode character '✓'`. Because that print is inside
the function's `try/except`, the error is swallowed as a repeating
`[MARKET60] poll error` and the bot **never returns an event** (it spins
forever). Workarounds:

- Run in a UTF-8 console / set `PYTHONUTF8=1` (or `chcp 65001`), **or**
- replace the Unicode glyphs (`✓`, etc.) with ASCII in the bot's prints.

The standalone `monitor_bot.py` is deliberately ASCII-only to avoid this.
