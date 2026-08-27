# Kalshi BTC-15M Async Trading Bot

Fully asynchronous, profit-oriented algo for Kalshi's **KXBTC15M** series — 15-minute binary contracts on BTC price direction (YES = price up, NO = price down).

---

## Requirements

```bash
pip install aiohttp cryptography python-dotenv numpy pandas
```

### Recommended — via the root dispatcher

The repo now ships a unified dispatcher at the project root.  Set `PLATFORM=kalshi` in the **root** `.env` and run:

```bash
python bot.py
```

The dispatcher:
- reads `PLATFORM` from the root `.env` (`kalshi` or `polymarket`),
- `chdir`s to the project root so relative paths resolve,
- exports `BOT_CSV_PATH`, `BOT_LOG_PREFIX=bot_`, `BOT_LOG_DIR` so both subbots share one CSV and one log file,
- imports and runs `kalshi.bot_kalshi_btc15.run()`.

Both Kalshi and Polymarket rows land in the same `trade_history.csv` (each row tagged with a `platform` column), and both write to the same `bot_YYYYMMDD.log` at the project root.

### Standalone

```bash
cd kalshi/
python bot_kalshi_btc15.py
```

Standalone mode also works: the bot inserts the project root onto `sys.path` so the shared `btc.BtcVidyaMonitor` import resolves either way.  Without `BOT_CSV_PATH` / `BOT_LOG_DIR` set, CSV and log default to the current working directory.

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `PLATFORM` | `kalshi` | Dispatcher switch — `kalshi` or `polymarket`. Read by root `bot.py` only |
| `KALSHI_API_KEY_ID` | — | Kalshi API key UUID |
| `KALSHI_PRIVATE_KEY` | `kalshi_private.pem` | RSA private key path |
| `KALSHI_CONTRACTS` | `30` | Contracts per trade (used when `DO_YOU_HAVE_STOP_SELL=TRUE`) |
| `KALSHI_PROFIT_PCT` | `15` | Take-profit target (%) |
| `KALSHI_STOP_PCT` | `55` | Stop-loss threshold (%) |
| `DRY_RUN_MODE` | `TRUE` | `FALSE` for live trading |
| `TIME_SEC_TO_ORDER` | `450` | Max market age (seconds) to enter |
| `MAX_TRADES_PER_MARKET` | `1` | Trades allowed per 15-min window |
| `DO_NOT_BUY_IF_PORTFOLIO_BELOW` | `15` | Halt if portfolio < this ($). On halt: cancel resting orders, fire-sell any open position, then (if `HALT_MACHINE_SHUTDOWN=TRUE`) shutdown the machine |
| `TARGET_PORTFOLIO_PCT` | `0` | Daily profit cap (%). Once today's portfolio is ≥ `day_start × (1 + TARGET_PORTFOLIO_PCT/100)`, stop placing new orders. `0` disables. Day-start baseline is persisted per-date in `kalshi_day_start_<YYYYMMDD>.txt` next to the CSV so the target survives bot restarts within the same CST day. Example: day-start $100, `TARGET_PORTFOLIO_PCT=50` → halt at PV ≥ $150. Respects `HALT_MACHINE_SHUTDOWN` |
| `MIN_ENTRY_CENTS` | `34` | Min bid to enter (cents) |
| `MAX_ENTRY_CENTS` | `80` | Max bid to enter (cents) |
| `BTC_COLD_START_DEFAULT` | `buy` | BTC signal during monitor warmup: `buy` / `sell` / `hold` |
| `HALT_START_TIME` | `06:15` | (Legacy single-window) start of trading halt window (24-hour HH:MM). Combined with any numbered windows below |
| `HALT_END_TIME` | `10:45` | (Legacy single-window) end of trading halt window (24-hour HH:MM) |
| `HALT_START_TIME1` … `HALT_START_TIME9` | — | Multi-window form. Define matching pairs `HALT_START_TIMEn` / `HALT_END_TIMEn` to halt during multiple intervals per day. Halt fires if local time is inside **any** configured window |
| `HALT_END_TIME1` … `HALT_END_TIME9` | — | Pair end for each numbered window. A window where `end < start` (e.g. `22:15`→`02:45`) wraps midnight |
| `HALT_TIMEZONE` | `America/Chicago` | IANA timezone for all halt windows (DST-aware) |
| `HALT_MACHINE_SHUTDOWN` | `TRUE` | `TRUE` = shut down PC on halt, `FALSE` = exit bot only |
| `DO_YOU_HAVE_STOP_SELL` | `TRUE` | `FALSE` = buy-only mode: skip TP sell + STEP 9 monitor; instead run a passive 15s-tick monitor for up to 870s with three triggers checked in order (first match wins): **C.** time_remaining > 300s AND live bid > 92¢ → fire-sell to lock profit + place flipped lotto buy (`LOTTO_CONTRACTS × 5¢`); once that buy fills (await_fill 60s timeout), place a TP SELL for `LOTTO_CONTRACTS // 2` × flipped side @ 12¢ → CSV `result="NO_SL_TRIG_C_HIGH_BID"` (one row, original position's profit-lock only); **A.** V3 strong-signal flip across ticks (yes↔no) → cancel resting + SELL at `max(live_bid, avg_cents − 15)¢` → CSV `result="NO_SL_TRIG_A_V3_FLIP"`; **B.** V2 (±$7) and V3 (strong) both oppose ordered direction → cut-loss SELL at `(avg_cents − 10)¢` → CSV `result="NO_SL_TRIG_B_V2V3_OPP"`. Age-timeout (none fired) → `result="NO_SL_TRADE"`. Each trigger logs its own CSV row at order-placement time using the limit price as expected exit. |
| `CONTRACTS_PV_PCT` | `25` | % of portfolio to size contracts when `DO_YOU_HAVE_STOP_SELL=FALSE`; formula: `ceil((PCT/100 × PV) / 0.56)` |
| `SENTIMENT_SIZE` | `100` | Rolling directional event buffer for standard signal scan (runtime override: 50) |
| `SELL_PCT_THRESHOLD` | `0.55` | Sell ratio threshold for standard scan — runtime value: `0.54` (54%) |
| `SENTIMENT_SIZE1` | `33` | Rolling event buffer for flip confirmation scan (runtime override: 40) |
| `SELL_PCT_THRESHOLD1` | `0.65` | Sell ratio threshold for flip confirmation scan — runtime value: `0.55` (55%) |
| `LOTTO_TRADE` | `FALSE` | Enable lotto trades (fun/high-risk); only active when `DO_YOU_HAVE_STOP_SELL=FALSE` |
| `LOTTO_CONTRACTS` | `10` | Contracts to buy on a lotto trade |
| `MAX_LOSS_RATE` | `33` | Risk management halt base. Bot halts when cumulative **PV Returns** drop below a profit-ratcheted floor derived from this value (see *Profit-ratchet* below). Default 33 → base halt at PV Returns < −33%. On halt, fire-sell open positions and stop the bot (respects `HALT_MACHINE_SHUTDOWN`) |

> **Note:** `SENTIMENT_SIZE` / `SELL_PCT_THRESHOLD` values inside `poll_for_signal()` are hardcoded locals that override the `.env` globals at runtime. The `.env` values serve as documentation defaults only.

---

## Full Trade Flow

```
START
  │
  ├─► [LOG]  Open/rotate $BOT_LOG_PREFIX$YYYYMMDD.log
  │          (bot_YYYYMMDD.log via dispatcher; kalshi_btc_15_YYYYMMDD.log standalone)
  │          Archive any stale same-prefix .log files → ./archive/
  │
  ├─► [BTC Monitor] Start shared btc.BtcVidyaMonitor — Coinbase poll every 15s
  │                 (CUSUM event filter + 4-indicator confluence vote)
  │
  └─► OUTER LOOP ──────────────────────────────────────────────────────────────┐
        │                                                                       │
   STEP 1: Wait for fresh KXBTC15M market                                      │
        │   • Poll Kalshi every 5s for an open KXBTC15M market                 │
        │   • Skip markets older than TIME_SEC_TO_ORDER (450s)                 │
        │   • Skip the just-closed ticker to avoid re-entering                 │
        │                                                                       │
        │   ── INNER LOOP (up to MAX_TRADES_PER_MARKET per market) ───────────  │
        │                                                                       │
        │   [WIN RATE] Before each trade slot, reads trade_history.csv and     │
        │   computes prediction accuracy across five metrics:                   │
        │     SUCCESS — direction match AND portfolio grew                      │
        │     FAIL    — direction wrong AND portfolio dropped                   │
        │     MIXED   — any other combination (right dir but PV dropped, etc.) │
        │     PV+ rate — % of trade pairs where portfolio grew (any direction) │
        │     PV Returns — (last_pv − first_pv) / first_pv × 100              │
        │                  total return across all recorded trades              │
        │     Rows with missing direction or portfolio_value are skipped.       │
        │     • Prints: "Prediction SUCESS rate: XX.X% (TOTAL: N; SUCCESS: N; │
        │       FAIL: N)  |  LOSS rate: XX.X%  MIXED: N  |  PV + rate: XX.X%  │
        │       (N/N  has +portfolio)  |  PV Returns: +XX.XX%"                 │
        │                                                                       │
        │   [LOSS RATE HALT] Immediately after WIN RATE print:                 │
        │   • _gain_pct = parsed PV Returns % (GAIN_RATE, e.g. -7.20)         │
        │   • Profit-ratchet sets the halt floor (highest tier first):         │
        │       PV Returns > 100%  → floor = MAX_LOSS_RATE−275  (−242%)        │
        │       PV Returns >  75%  → floor = MAX_LOSS_RATE−175  (−142%)        │
        │       PV Returns >  50%  → floor = MAX_LOSS_RATE−75   ( −42%)        │
        │       otherwise          → floor = −MAX_LOSS_RATE     ( −33%)        │
        │   ┌─ _gain_pct < floor?                                               │
        │   │     YES → fire-sell any open position on this ticker             │
        │   │           if HALT_MACHINE_SHUTDOWN=TRUE → os shutdown (30s)      │
        │   │           print "[HALT] Bot halting now." → return (exit bot)    │
        │   │     NO  → continue to portfolio balance check                    │
        │                                                                       │
   STEP 2: Portfolio check                                                      │
        │   • Fetch current balance                                             │
        │   ┌─ balance < DO_NOT_BUY_IF_PORTFOLIO_BELOW ($15)?                  │
        │   │     YES → _halt_and_shutdown() — cancel orders, fire-sell        │
        │   │           any open position, shutdown machine if                 │
        │   │           HALT_MACHINE_SHUTDOWN=TRUE, return                      │
        │   │     NO  → continue to TARGET-PV check                             │
        │                                                                       │
        │   • [TARGET-PV] Daily profit cap (only if TARGET_PORTFOLIO_PCT > 0): │
        │       • Read day-start baseline from                                  │
        │         kalshi_day_start_<YYYYMMDD>.txt (CST date) next to CSV       │
        │       • If file missing, seed it with current portfolio value         │
        │       • target_pv = day_start × (1 + TARGET_PORTFOLIO_PCT/100)       │
        │       • Print: "[TARGET-PV] Day-start=$X  Target=$Y (+P%)  Today=±%" │
        │   ┌─ portfolio ≥ target_pv?                                           │
        │   │     YES → "[TARGET-PV] HIT — no new orders today."                │
        │   │           if HALT_MACHINE_SHUTDOWN=TRUE → shutdown /s /f /t 30   │
        │   │           return (exit bot)                                       │
        │   │     NO  → continue                                                │
        │                                                                       │
   STEP 3: Determine direction — best of 3 voters                              │
        │   Direction = majority of three independent voters.  V1 always       │
        │   votes; V2 and V3 may abstain.  Ties are broken by V1 (settled     │
        │   markets, always available).                                         │
        │                                                                       │
        │   V1  Settled-market momentum (determine_direction)                  │
        │       • Fetch last 6 settled KXBTC15M outcomes (yes/no)              │
        │       • Take majority vote → initial direction                        │
        │       • Tie-break 1: majority of most recent 3 outcomes              │
        │       • Tie-break 2: side with more total occurrences                 │
        │       • ALWAYS returns "yes" or "no" — never abstains.                │
        │       • Also yields actual_direction_previous (most recent settled    │
        │         outcome) used by the CSV log + win-rate calc.                │
        │                                                                       │
        │   V2  Live BTC vs market strike  (±$15 dead band)                    │
        │       • btc_to_beat = market.strike_price | floor_strike | cap_strike│
        │       • live_btc    = btc.last_price (shared monitor, 15s polls)     │
        │       ┌──────────────────────────────────────────────────────────┐   │
        │       │ live_btc > strike + 15  →  YES                            │   │
        │       │ live_btc < strike - 15  →  NO                             │   │
        │       │ within ±15 of strike    →  abstain (no vote contributed)  │   │
        │       │ live_btc or strike None →  abstain                        │   │
        │       └──────────────────────────────────────────────────────────┘   │
        │                                                                       │
        │   V3  BTC strong signal  (btc.btcSignalWithStrength())               │
        │       (Careful: BTC monitor's "buy"/"sell" map to YES/NO          │
        │        on the Kalshi contract — buy=YES, sell=NO.)                   │
        │       ┌──────────────────────────────────────────────────────────┐   │
        │       │ strong_buy  | buy   →  YES                                │   │
        │       │ strong_sell | sell  →  NO                                 │   │
        │       │ hold                →  abstain                            │   │
        │       └──────────────────────────────────────────────────────────┘   │
        │                                                                       │
        │   Tally → direction                                                   │
        │       votes_yes > votes_no → YES                                      │
        │       votes_no  > votes_yes → NO                                      │
        │       tie (only possible when one voter abstains and the other       │
        │            two split, or all but V1 abstain) → V1's vote breaks it    │
        │                                                                       │
        │   Logs:                                                               │
        │     [DIR] Best-of-3 vote → YES  (YES=2  NO=1)                        │
        │     [DIR]  V1 settled-markets : YES                                   │
        │     [DIR]  V2 live-vs-strike  : YES     (live $68,100 > $68,015)     │
        │     [DIR]  V3 strong-signal   : NO      (btcSignalWithStrength=SELL) │
        │                                                                       │
   STEP 4: Entry signal scan (poll_for_signal)                                 │
        │   • Poll bid price for chosen direction every 1s                     │
        │   • Feed prices into a rolling deque(maxlen=20)                      │
        │   • Compute signal from deque once 20 ticks accumulated:             │
        │                                                                       │
        │     compute_signal() evaluation order:                                │
        │     ┌─────────────────────────────────────────────────────────┐      │
        │     │ 0. STRONG_SELL (crash floor — fires immediately)        │      │
        │     │    latest < 0.26 AND recent-8-high ≥ 0.38               │      │
        │     │    latest < 0.36 AND recent-8-high ≥ 0.50               │      │
        │     │    latest < 0.32 AND recent-8-high ≥ 0.45               │      │
        │     │    → return "strong_sell" (treated as "sell" at caller) │      │
        │     │                                                         │      │
        │     │ 1. BUY (all 3 gates must pass)                          │      │
        │     │    B1. EMA(3) > EMA(10)                                 │      │
        │     │    B2. OLS slope > 0                                    │      │
        │     │    B3. upticks > downticks (last 9 ticks)               │      │
        │     │    → return "buy"                                       │      │
        │     │                                                         │      │
        │     │ 2. SELL (all 3 gates must pass)                         │      │
        │     │    X1. EMA(3) < EMA(10)                                 │      │
        │     │    X2. OLS slope < 0                                    │      │
        │     │    X3. downticks > upticks (last 9 ticks)               │      │
        │     │    → return "sell" (unless STRONG_SELL qualifies)       │      │
        │     │                                                         │      │
        │     │ 3. STRONG_SELL (gates S1–S6, in addition to SELL)       │      │
        │     │    S1. EMA gap > 0.5 × σ                                │      │
        │     │    S2. |slope| > 1.0 × σ  AND slope < 0                 │      │
        │     │    S3. 7 of last 8 ticks non-increasing                 │      │
        │     │    S4. Peak-to-current drop > max(12%, 2.5×σ/peak)     │      │
        │     │    S5. Second-half slope < first-half slope             │      │
        │     │    S6. Latest price < EMA(10)                           │      │
        │     │    → return "strong_sell"                               │      │
        │     │                                                         │      │
        │     │ 4. HOLD — default if no signal fires                    │      │
        │     └─────────────────────────────────────────────────────────┘      │
        │                                                                       │
        │   • Collect last 50 directional ticks (ignore "hold")                │
        │   • Simultaneously fill price_buf (maxlen=50) with raw bid prices    │
        │   • Once 50 events accumulated, evaluate with BTC + Kalshi gate:     │
        │                                                                       │
        │     Runtime thresholds:                                               │
        │       standard scan      → SENTIMENT_SIZE=50  SELL_PCT=54%           │
        │       flip confirm scan  → SENTIMENT_SIZE=40  SELL_PCT=55%           │
        │                                                                       │
        │     is_drop_real (computed once per decision tick):                   │
        │       max(oldest-15 prices in price_buf)                              │
        │         − min(newest-15 prices in price_buf) ≥ 0.10                  │
        │       True  = price has genuinely fallen ≥ 10¢ from old highs        │
        │       False = price is flat or rising                                 │
        │                                                                       │
        │     BTC VIDYA + Kalshi sentiment + is_drop_real check:               │
        │     ┌─────────────────────────────────────────────────────────┐      │
        │     │ CONFIRM BUY (primary — all four gates must pass):        │      │
        │     │   direction=YES and BTC=buy                             │      │
        │     │     AND sells ≤ 54%  AND NOT is_drop_real → "buy"      │      │
        │     │   direction=NO  and BTC=sell                            │      │
        │     │     AND sells ≤ 54%  AND NOT is_drop_real → "buy"      │      │
        │     │   (if is_drop_real=True, price is falling — block buy) │      │
        │     │                                                         │      │
        │     │ FLIP (BTC gate OR sentiment+drop gate):                 │      │
        │     │   direction=YES and BTC=sell  → "sell"  (BTC alone)    │      │
        │     │   sells > 54% AND is_drop_real → "sell"  (both needed) │      │
        │     │   direction=NO  and BTC=buy   → "sell"  (BTC alone)    │      │
        │     │   sells > 54% AND is_drop_real → "sell"  (both needed) │      │
        │     │   (high sell ratio alone no longer flips — needs       │      │
        │     │    confirmed price drop to avoid false flips on noise)  │      │
        │     │                                                         │      │
        │     │ ADDITIONAL BUY signals (secondary pass):                │      │
        │     │   direction=NO  and BTC=sell                           │      │
        │     │     AND buy_ratio > 72%  AND NOT is_drop_real → "buy" │      │
        │     │   direction=YES and BTC=buy                            │      │
        │     │     AND buy_ratio > 72%  AND NOT is_drop_real → "buy" │      │
        │     │   (all three gates required: BTC aligned, Kalshi >72%  │      │
        │     │    buy-sided, and no confirmed price drop)              │      │
        │     │   buy_ratio = buys / len(sentiment)                    │      │
        │     │                                                         │      │
        │     │ otherwise: keep polling                                  │      │
        │     └─────────────────────────────────────────────────────────┘      │
        │                                                                       │
        │   • Early-exit (mathematical short-circuit, both directions)         │
        │     Active once sentiment fill ≥ 30 events AND < SENTIMENT_SIZE.    │
        │     The 30-event floor guards against sparse-data false-triggers.   │
        │                                                                       │
        │     A. SELL UNREACHABLE → return BUY                                  │
        │        max_possible_sells = sells + (SENTIMENT_SIZE − len(sentiment))│
        │        max_possible_ratio = max_possible_sells / SENTIMENT_SIZE      │
        │        If max_possible_ratio < SELL_PCT_THRESHOLD → SELL can never  │
        │        fire (turning every remaining slot into a sell still falls   │
        │        below threshold).  Return "buy" → STEP 5a → STEP 5d.         │
        │        Examples (standard scan, threshold 54%):                       │
        │          S/B=0/30  → max 0+20 = 20/50 = 40% < 54% → BUY              │
        │          S/B=6/30  → max 26/50 = 52% < 54% → BUY                    │
        │          S/B=7/30  → max 27/50 = 54% (NOT strictly <) → keep        │
        │                                                                       │
        │     B. SELL GUARANTEED → return SELL  (symmetric mirror of A)        │
        │        min_possible_ratio = sells / SENTIMENT_SIZE                   │
        │        If min_possible_ratio > SELL_PCT_THRESHOLD → no number of     │
        │        future buys can pull the final ratio back below threshold.   │
        │        Return "sell" → STEP 5a → sell-retry → STEP 5b flip-confirm.  │
        │        Examples (standard scan, threshold 54%):                       │
        │          S/B=28/30 → min 28/50 = 56% > 54% → SELL                   │
        │          S/B=29/30 → min 29/50 = 58% > 54% → SELL                   │
        │          S/B=27/30 → min 27/50 = 54% (NOT strictly >) → keep        │
        │                                                                       │
        │     Both checks live inside poll_for_signal, so they automatically  │
        │     apply to ALL three callers (STEP 4 initial scan, STEP 5b flip-  │
        │     confirm, STEP 5c original-buy-confirm) with each caller's own    │
        │     SENTIMENT_SIZE / SELL_PCT_THRESHOLD.                              │
        │                                                                       │
        │   • If max_ticks exhausted with no confirmed decision:               │
        │       return btc_sig (latestBtcVidyaSignal result) — always          │
        │       returns a directional signal, never skips the slot.            │
        │                                                                       │
   STEP 5a: Route on entry signal (with sell-retry)                            │
        │                                                                       │
        │   signal = "hold"                                                     │
        │     → Skip this trade slot, wait 8s, try next slot                   │
        │                                                                       │
        │   signal = "buy"                                                      │
        │     → mode = "BUY", keep current direction                            │
        │     → proceed to STEP 5d (entry price guard)                         │
        │                                                                       │
        │   signal = "sell"                                                     │
        │     → Before flipping, retry poll_for_signal on the ORIGINAL         │
        │       direction up to `retry_original_buy` = 3 times (same params    │
        │       as STEP 4: interval_s=1, window=20, max_ticks=300).            │
        │                                                                       │
        │       For each attempt 1..3:                                          │
        │         print "[STEP 5a RETRY N/3] re-polling DIR before flipping …" │
        │         re-run poll_for_signal on the original direction              │
        │         print "[STEP 5a RETRY N] → <result>"                          │
        │         if result != "sell" → break early                             │
        │                                                                       │
        │       After the retry loop:                                           │
        │       ┌─ retry result = "hold"                                        │
        │       │   → "[STEP 5a] HOLD after retry — skipping slot."             │
        │       │   → sleep 8s, continue (same as the pre-5a hold check)        │
        │       ├─ retry result = "buy"                                         │
        │       │   → "[STEP 5a] Retry rescued <DIR> (signal=BUY) — no flip."   │
        │       │   → mode = "BUY", keep ORIGINAL direction                     │
        │       │   → proceed to STEP 5d                                        │
        │       └─ all 3 retries still "sell"                                   │
        │           → Flip direction (yes↔no)                                  │
        │           → print "FLIP-BUY SELL signal → flipped → DIR              │
        │              (after 3 retries)"                                       │
        │           → mode = "FLIP-BUY"                                        │
        │           → proceed to STEP 5b (flip confirmation)                   │
        │                                                                       │
   STEP 5b: Flip confirmation (only for FLIP-BUY)                             │
        │   • Run a second poll_for_signal on the NEW (flipped) direction      │
        │   • Tighter params: 40-event buffer, 55% sell threshold, 300 ticks  │
        │                                                                       │
        │   signal = "sell" (flipped direction also looks bearish)             │
        │     → Flip back to ORIGINAL direction                                 │
        │     → mode = "ORIGINAL-BUY" → proceed to STEP 5c                    │
        │                                                                       │
        │   signal = "buy"                                                      │
        │     → mode = "BUY" (trade the flipped direction)                     │
        │     → proceed to band guard                                           │
        │                                                                       │
        │   signal = "hold"                                                     │
        │     → mode = "BUY" (else branch), caught by hold check below         │
        │     → skip trade slot, wait 8s                                        │
        │                                                                       │
   STEP 5c: ORIGINAL-BUY confirmation (only when direction flipped twice)      │
        │   • Run a third poll_for_signal back on the ORIGINAL direction       │
        │   • Same tighter params: 40-event buffer, 55% threshold, 100 ticks  │
        │                                                                       │
        │   signal = "sell" (original direction also bearish — double flip)    │
        │     → Flip BACK to flipped direction                                  │
        │     → mode = "FLIP-BUY" → buy flipped direction                     │
        │                                                                       │
        │   signal = "buy"                                                      │
        │     → mode = "BUY" → buy original direction                          │
        │                                                                       │
        │   signal = "hold"                                                     │
        │     → skip trade slot, wait 8s                                        │
        │                                                                       │
        │   Direction state summary across all three polls:                     │
        │     STEP 4 sell  → direction = FLIPPED                               │
        │     STEP 5b sell → direction = ORIGINAL                              │
        │     STEP 5c sell → direction = FLIPPED  (double-flip, buy flipped)   │
        │     STEP 5c buy  → direction = ORIGINAL (buy original)               │
        │                                                                       │
   STEP 5d: Entry price band guard (wait loop + 20s rescan)                   │
        │   • Polls bid every 3s; waits until ALL 3 conditions pass:          │
        │       1. bid within [MIN_ENTRY_CENTS, MAX_ENTRY_CENTS]               │
        │       2. BTC signal agrees with direction                             │
        │       3. Kalshi compute_signal not "sell" or "strong_sell"           │
        │   • Each tick prints: band✓/✗  BTC✓/✗  Kalshi signal  elapsed age  │
        │                                                                       │
        │   ┌─ All 3 pass → "✓ Entry conditions met" → proceed                │
        │   ├─ Market age > TIME_SEC_TO_ORDER → abandon, next market           │
        │   └─ 20s elapsed without entry → trigger RESCAN:                     │
        │         • Run 40-tick × 0.75s quick scan (~30s)                      │
        │         • Fetch fresh live bid after scan                             │
        │         • Check: bid in band  AND  signal="buy"  AND  BTC aligned    │
        │         ├─ PASS → DIRECTION RECONFIRMATION (best-of-3, mirrors      │
        │         │         STEP 9a):                                          │
        │         │           V1 = determine_direction(c)  (always votes)     │
        │         │           V2 = btc.last_price vs strike ±$15  (or abstain)│
        │         │           V3 = btc.btcSignalWithStrength()                │
        │         │                 {buy,strong_buy} → YES,                   │
        │         │                 {sell,strong_sell} → NO,                  │
        │         │                 hold → abstain                            │
        │         │         Tally → confirmed_dir (V1 breaks ties)            │
        │         │         Print:                                            │
        │         │           [BAND RESCAN RECONFIRM] V1=… V2=… V3=…          │
        │         │           → DIR (YES=n NO=n)  current=DIR                 │
        │         │         ┌─ confirmed_dir == current direction              │
        │         │         │     → update _peek, _band_ready=True, proceed   │
        │         │         └─ confirmed_dir != current direction              │
        │         │             → "[BAND RESCAN] ✗ Direction mismatch …"      │
        │         │               reset 20s timer, continue polling           │
        │         └─ FAIL → reset 20s timer, continue polling (no extra sleep) │
        │                                                                       │
   STEP 5e: Trading hours halt gate                                            │
        │   • Checked immediately after band guard confirms entry               │
        │   • Reads HALT_TIMEZONE plus halt windows from .env:                  │
        │       - legacy: HALT_START_TIME / HALT_END_TIME                       │
        │       - multi : HALT_START_TIME[1..9] / HALT_END_TIME[1..9]           │
        │     Both forms are combined into one list at startup; the list is     │
        │     logged once at session start as                                   │
        │       [HALT] Halt windows (TZ): HH:MM-HH:MM, HH:MM-HH:MM, …          │
        │   • A window where end < start (e.g. 22:15→02:45) wraps midnight     │
        │     and matches on either side of 00:00.                              │
        │   ┌─ Local time inside ANY configured window?                         │
        │   │     YES →                                                         │
        │   │       0. Log which window matched                                 │
        │   │       1. Cancel all resting orders                               │
        │   │       2. Fire-sale any open position for this ticker @ 5¢        │
        │   │       3. If HALT_MACHINE_SHUTDOWN=TRUE → shutdown /s /f /t 30   │
        │   │       4. Return from bot (finally block closes session cleanly)  │
        │   └─ NO  → proceed to STEP 5f                                        │
        │                                                                       │
   STEP 5f: BTC strong-signal block                                            │
        │   • Final safety gate before placing the buy.                         │
        │   • Calls btc.hasRecentStrongAgainst(direction, lookback=20):         │
        │       direction=YES → blocked if any "strong_sell" in last 20         │
        │                       strength_history ticks (~5 min)                 │
        │                       (BTC strongly falling → bad to buy YES)         │
        │       direction=NO  → blocked if any "strong_buy" in last 20          │
        │                       strength_history ticks (~5 min)                 │
        │                       (BTC strongly rising → bad to buy NO)           │
        │   ┌─ BLOCKED → "[STEP 5f] BLOCKED — recent STRONG_<X> in              │
        │   │             btc.strength_history; refusing to buy DIR.             │
        │   │             Skipping slot." → sleep 5s, continue                  │
        │   └─ CLEAR   → proceed to STEP 6                                      │
        │                                                                       │
   STEP 6: Place buy order (two-phase entry for elevated bids)                 │
        │   • planning_to_buy = last confirmed bid from band guard (cents)     │
        │                                                                       │
        │   • Contract sizing:                                                  │
        │       DO_YOU_HAVE_STOP_SELL=TRUE  → use KALSHI_CONTRACTS             │
        │       DO_YOU_HAVE_STOP_SELL=FALSE → ceil((CONTRACTS_PV_PCT/100       │
        │                                          × portfolio_value) / 0.56)  │
        │                                                                       │
        │   bid ≤ 73¢ → place directly at BUY_CENTS (95¢ aggressive limit)    │
        │                                                                       │
        │   bid 74–77¢ or ≥ 78¢ → TWO-PHASE pre-order check:                 │
        │                                                                       │
        │   ┌─ Phase 1: Wait for bid to fall to target ──────────────────────┐ │
        │   │  bid 74–77¢ → wait until live bid ≤ (planning_to_buy − 5¢)    │ │
        │   │  bid ≥ 78¢  → wait until live bid ≤ (planning_to_buy − 11¢)   │ │
        │   │  Poll every 3s. Deadline: 500s after market open               │ │
        │   │  (300s before effective deadline at 800s)                      │ │
        │   │  Deadline hit → resp=None → skip trade slot                    │ │
        │   └─────────────────────────────────────────────────────────────────┘ │
        │                                                                       │
        │   ┌─ Phase 2: Confirmation scan (once bid hits target) ─────────────┐ │
        │   │  Run 20-tick × 0.75s scan (~15s) into fresh deque(maxlen=20)   │ │
        │   │  compute_signal must return "buy"                               │ │
        │   │  BTC signal must align (YES→buy / NO→sell)                     │ │
        │   │  PASS → place_buy at discount offset                            │ │
        │   │    bid 74–77¢ → buy at (planning_to_buy − 5¢)                  │ │
        │   │    bid ≥ 78¢  → buy at (planning_to_buy − 10¢)                 │ │
        │   │  FAIL → resp=None → skip trade slot                            │ │
        │   └─────────────────────────────────────────────────────────────────┘ │
        │                                                                       │
        │   • Wait up to 120s for fill (check resting orders every 4s)         │
        │   ┌─ Not filled in 120s → cancel all, skip to next trade slot        │
        │   └─ Filled → continue                                                │
        │                                                                       │
        │   ── BUY-ONLY MODE (DO_YOU_HAVE_STOP_SELL=FALSE) ────────────────── │
        │   • Skip TP sell + STEP 9 monitor entirely.                          │
        │   • Run a passive 15s-tick monitor until the 15-min market is ~30s   │
        │     from close (max age 870s).  Each tick computes:                  │
        │                                                                       │
        │       V2 = live BTC vs strike (±$7 dead band):                        │
        │             live > strike + 7 → "yes"                                 │
        │             live < strike - 7 → "no"                                  │
        │             else / data missing → abstain                             │
        │                                                                       │
        │       V3 = btc.btcSignalWithStrength() — STRONG ONLY:                 │
        │             "strong_buy"  → "yes"                                     │
        │             "strong_sell" → "no"                                      │
        │             {buy, sell, hold} → silenced (mirrors ordered_direction   │
        │                                 in tally so a non-strong tick does    │
        │                                 NOT count as an opposing vote)        │
        │                                                                       │
        │     Each tick prints:                                                 │
        │       [NO-STOP MON age=Xs] V2 live=$L vs strike $S±7 → YES/NO/ABSTAIN│
        │                            V3 strong=… → YES/NO  (prev=YES/NO/—)     │
        │                            ordered=YES/NO                             │
        │                                                                       │
        │   Three independent triggers fire on each tick (C → A → B order).  │
        │   First match wins; we break after placing the order(s).             │
        │                                                                       │
        │   TRIGGER C — HIGH-BID PROFIT LOCK + flipped lotto (checked first)    │
        │       Activates when the position is deeply in profit AND there is   │
        │       meaningful time left in the 15-min cycle:                       │
        │         time_remaining = max(0, 900 − age) > 300s   (i.e. age < 600s)│
        │         AND live bid for ordered_direction > 92¢                      │
        │                                                                       │
        │       Action (in order):                                              │
        │         1. cancel_all() — kill any resting orders on this ticker      │
        │         2. _fire_sale(ordered_direction, real_contracts)              │
        │              → limit SELL @ 5¢ that fills against the resting high   │
        │                bid (~92¢) and locks in the gain                       │
        │         3. _mk_order(buy, flip(ordered_direction),                    │
        │                      LOTTO_CONTRACTS, 5)                              │
        │              → plant an asymmetric "free option" on a late-cycle     │
        │                reversal: deep-OTM buy on the opposite side at 5¢     │
        │         3b. await_fill(timeout=60s) on the lotto buy, then if        │
        │             FILLED → place a TP SELL on the flipped side for         │
        │             HALF of LOTTO_CONTRACTS (= LOTTO_CONTRACTS // 2,         │
        │             floored at 1) @ 12¢.                                      │
        │             Example: LOTTO_CONTRACTS=10 → buy 10 × flip @ 5¢,        │
        │             once filled → TP SELL 5 × flip @ 12¢ (140% gain on       │
        │             the half, the remaining 5 ride free toward settlement).  │
        │             If await_fill times out (no one sells to us at 5¢ in    │
        │             60s) → skip the TP placement, log as usual.              │
        │             DRY_RUN prints both the buy and the would-be TP payload  │
        │             without submitting either.                                │
        │         4. Log a CSV row IMMEDIATELY with                             │
        │            result="NO_SL_TRIG_C_HIGH_BID" (exit_price uses the live  │
        │            bid as the expected sell fill).  The lotto buy + TP are   │
        │            NOT logged as separate CSV rows — only the profit-locking │
        │            sell of our original position.                             │
        │       set _cut_loss_placed = True; break monitor                      │
        │                                                                       │
        │   TRIGGER A — V3 strong-signal TRANSITION (checked after C)           │
        │       Tracks prev_v3_strong across ticks.  Only strong ticks update   │
        │       it; hold / regular buy / regular sell leave it untouched so a   │
        │       gap between two strong signals still counts as a transition.    │
        │                                                                       │
        │       Fires when prev_v3_strong is set AND cur_v3_strong is set AND   │
        │       they DIFFER (yes→no or no→yes).                                 │
        │                                                                       │
        │       Action: fetch live bid for ordered_direction:                   │
        │         • bid > avg_cents → cancel resting orders, SELL @ bid         │
        │           (escape near break-even / small profit)                     │
        │         • else (bid ≤ avg or bid=None) → cancel resting orders,       │
        │           SELL @ max(1, avg_cents − 15)¢ (controlled loss)            │
        │       Then log a CSV row IMMEDIATELY at order-placement time          │
        │       with result="NO_SL_TRIG_A_V3_FLIP" (see CSV row spec below).    │
        │       set _cut_loss_placed = True; break monitor                      │
        │                                                                       │
        │   TRIGGER B — V2 & V3 STABLE OPPOSITION (checked after A)             │
        │     Decision when V2 != None and V2 == V3:                            │
        │       both vote == ordered_direction  → print only, keep watching     │
        │       both vote != ordered_direction  → cut-loss SELL @ max(1,        │
        │           avg_cents − 10)¢ on ordered side                            │
        │           (e.g. avg=64¢ → cut SELL @ 54¢)                             │
        │         Then log a CSV row IMMEDIATELY at order-placement time        │
        │         with result="NO_SL_TRIG_B_V2V3_OPP".                          │
        │         set _cut_loss_placed = True; break monitor                    │
        │     Otherwise (one or both abstain, or they disagree) → keep watching │
        │                                                                       │
        │   ── CSV row (per trigger) ────────────────────────────────────────   │
        │   Written immediately after the sell order is placed (NOT at the      │
        │   end of the monitor).  Uses the LIMIT price as the expected exit;    │
        │   actual fill may differ if the order rests / partially fills.        │
        │     ticker           = current market ticker                          │
        │     mode             = unchanged from STEP 5a outcome                 │
        │     direction        = ordered_direction (the side we sold)           │
        │     contracts        = real_contracts (actual filled buy count)       │
        │     entry_price      = avg_cents                                      │
        │     exit_price       = (sell_limit_cents / 100) × real_contracts (USD)│
        │                          Trigger A: sell_limit_cents = _trans_price   │
        │                                     (= live bid OR avg_cents − 15)    │
        │                          Trigger B: sell_limit_cents = _cut_price     │
        │                                     (= avg_cents − 10)                │
        │                          Trigger C: sell_limit_cents = live bid (¢)   │
        │                                     (fire-sale at 5¢ limit fills      │
        │                                      against the high resting bid)    │
        │                          Note: Trigger C ALSO places a separate buy   │
        │                          on the FLIPPED side (LOTTO_CONTRACTS × 5¢);  │
        │                          that buy is NOT logged here — only the       │
        │                          profit-locking sell row.                     │
        │     pnl              = exit_price − entry_total (USD)                 │
        │     result           = "NO_SL_TRIG_A_V3_FLIP"   (Trigger A)           │
        │                        "NO_SL_TRIG_B_V2V3_OPP"  (Trigger B)           │
        │                        "NO_SL_TRIG_C_HIGH_BID"  (Trigger C)           │
        │     portfolio_value  = fresh balance after the sell submission        │
        │     BTC_TO_BEAT      = btc_to_beat                                    │
        │     BTC_SPOT_PRICE_AT_BUY  = captured at fill (btc_spot_at_buy)       │
        │     BTC_SPOT_PRICE_AT_SELL = btc.last_price at trigger time           │
        │     actual_direction_previous = fresh fetch via determine_direction() │
        │                                                                       │
        │   ── CSV row (age-timeout path, no trigger fired) ───────────────     │
        │   Written ONCE after the while loop exits via the 870s age cap:       │
        │     result = "NO_SL_TRADE"                                            │
        │     exit_price = 0.0,  pnl = 0.0                                      │
        │     contracts = _buy_contracts (we never sold)                        │
        │                                                                       │
        │   • Break inner loop → wait for next market                           │
        │                                                                       │
   STEP 7: Compute TP / SL from fill cost                                      │
        │   • avg_cents  = fill_cost / _buy_contracts × 100  (rounded)         │
        │   • tp_cents   = avg_cents × (1 + PROFIT_PCT/100), capped at 91¢    │
        │   • notional   = (avg_cents/100) × _buy_contracts                    │
        │   • sl_total   = notional × (1 − STOP_PCT/100)                       │
        │     ↑ Always uses _buy_contracts (the actual contracts bought for   │
        │       this trade) — NOT the module-level KALSHI_CONTRACTS constant. │
        │       Critical when DO_YOU_HAVE_STOP_SELL=FALSE because contracts    │
        │       are sized dynamically via CONTRACTS_PV_PCT and will not match  │
        │       KALSHI_CONTRACTS.                                              │
        │                                                                       │
        │   Example A (KALSHI_CONTRACTS=30, filled at 65¢, STOP_PCT=55):       │
        │     _buy_contracts = 30                                              │
        │     fill_cost  = $19.50                                               │
        │     tp_cents   = 65 × 1.15 = 74¢ → TP sell @ 74¢                   │
        │     notional   = 0.65 × 30 = $19.50                                  │
        │     sl_total   = $19.50 × 0.45 = $8.78 → exit if value < $8.78      │
        │                                                                       │
        │   Example B (DO_YOU_HAVE_STOP_SELL=FALSE, PV-sized to 29 contracts,  │
        │              filled at 69¢, STOP_PCT=55):                            │
        │     _buy_contracts = 29   (NOT KALSHI_CONTRACTS)                     │
        │     fill_cost  = $20.01                                              │
        │     tp_cents   = 69 × 1.20 = 83¢ → TP sell @ 83¢                   │
        │     notional   = 0.69 × 29 = $20.01                                  │
        │     sl_total   = $20.01 × 0.45 ≈ $9.00 → exit if value < $9.00      │
        │                                                                       │
   STEP 8: Place take-profit sell order                                        │
        │   • Limit sell: CONTRACTS × tp_cents on same direction               │
        │   • Order rests on book — fills automatically if market reaches TP   │
        │                                                                       │
   STEP 9: Monitor open position (monitor_trade)                               │
        │   • Poll bid every 1s into deque(maxlen=20)                          │
        │   • Verify position exists (wait up to 60s for it to appear)         │
        │   • Track cumulative sell/buy signal events (sell_pct_to_compare)    │
        │   • Track min_bid and max_bid seen (for CSV tuning columns)          │
        │                                                                       │
        │   Exit triggers (evaluated in order every tick):                     │
        │                                                                       │
        │   [T1] TAKE PROFIT                                                   │
        │     Position contracts drop to 0 AND no resting orders               │
        │     → TP sell filled on exchange; return "TAKE_PROFIT"               │
        │                                                                       │
        │   [T2] STOP LOSS                                                     │
        │     live_value (bid × contracts) ≤ sl_total                          │
        │     → Cancel all resting orders                                       │
        │     → Fire-sale: limit sell @ 5¢ (emergency exit)                   │
        │     → Return "STOP_LOSS"                                             │
        │                                                                       │
        │   [T3] STRONG_SELL signal                                            │
        │     compute_signal = "strong_sell"                                   │
        │     AND current loss > 15% of entry                                  │
        │     → Cancel all, fire-sale @ 5¢                                    │
        │     → Return "SELL_SIGNAL"                                           │
        │                                                                       │
        │   [T4] BEARISH SENTIMENT + BTC CONTRADICTION                         │
        │     After ≥ 100 non-hold signal events:                              │
        │     sell_ratio ≥ 57%  AND  loss > 15%                               │
        │     AND BTC signal contradicts held direction:                        │
        │       direction=YES → BTC="sell"                                     │
        │       direction=NO  → BTC="buy"                                      │
        │     → Cancel all, fire-sale @ 5¢                                    │
        │     → Return "SELL_SIGNAL"                                           │
        │                                                                       │
        │   [T5] WRONG-TIME ENTRY — early sell on heavy bearish sentiment      │
        │     current tick signal = "sell"                                     │
        │     AND sell_pct_to_compare > monitor_sell_ratio_compare            │
        │         sell_pct_to_compare    = cumulative sells% (integer %)       │
        │         monitor_sell_ratio_compare = (MONITOR_SELL_RATIO×100)+15     │
        │                               = (57%+15) = 72%                      │
        │     AND total_events > 100                                           │
        │     → Cancel all, fire-sale @ 5¢                                    │
        │     → Return "SELL_SIGNAL"                                           │
        │                                                                       │
   STEP 10: Log trade to CSV                                                   │
        │   Timestamp in Central US time (YYYY-MM-DD HH:MM)                   │
        │   CSV path = $BOT_CSV_PATH (default trade_history.csv).              │
        │   When run via the root dispatcher both bots share one file at the   │
        │   project root; rows are tagged with a "platform" first column so    │
        │   each bot filters to its own rows when computing win rate.          │
        │   Columns: platform, timestamp, ticker,                              │
        │             BTC_TO_BEAT, BTC_SPOT_PRICE_AT_BUY, BTC_SPOT_PRICE_AT_SELL,│
        │             mode, direction, actual_direction_previous, contracts,   │
        │             entry_price, exit_price, pnl, result, portfolio_value,   │
        │             returns, MAX_LOSS_PCT, MAX_PROFIT_PCT                    │
        │                                                                       │
        │   platform                — "kalshi" or "polymarket"                 │
        │   BTC_TO_BEAT              — Kalshi market strike price              │
        │   BTC_SPOT_PRICE_AT_BUY   — Coinbase spot when fill confirmed        │
        │   BTC_SPOT_PRICE_AT_SELL  — Coinbase spot when position closed       │
        │   actual_direction_previous — most recent settled market outcome     │
        │                              used to compute prediction win rate      │
        │   entry_price             — avg fill price per contract in cents     │
        │                            e.g. 65 = filled at 65¢/contract          │
        │                            (avg_cents = fill_cost / contracts × 100) │
        │   returns                 — portfolio % change vs previous row       │
        │                            e.g. "+3.45%" or "-12.10%"                │
        │                            blank on first-ever trade row             │
        │   MAX_LOSS_PCT   (TP wins)  — worst drawdown before trade won        │
        │   MAX_PROFIT_PCT (SL/SELL)  — best gain seen before trade reversed   │
        │   (Use these to tune KALSHI_STOP_PCT and KALSHI_PROFIT_PCT)          │
        │                                                                       │
        └─► Wait 8s → next trade slot → back to OUTER LOOP ────────────────────┘
```

---

## BTC VIDYA Monitor (Background)

Runs continuously from bot start.  Lives in the shared `btc/` package (`from btc import BtcVidyaMonitor`) — both the Kalshi and Polymarket bots import the **same** monitor instance class, so fixing logic here fixes both bots.

Polls `api.coinbase.com` for BTC-USD spot price every **15 seconds** into a rolling window of 120 ticks (~30 min of context).

### Signal pipeline (CUSUM event filter + 4-vote confluence)

The monitor combines two layers in `_compute_signal()`:

**1. CUSUM event filter (primary trigger).**
Symmetric López de Prado CUSUM (AFML Ch.2) over log-returns of the 15s spot ticks, with an EWMA realized-vol estimate setting the threshold:

| Constant | Value | Meaning |
|---|---|---|
| `CUSUM_K` | `1.5` | Threshold in σ_EWMA units (AFML default) |
| `EWMA_LAMBDA` | `0.94` | RiskMetrics decay (~20-tick half-life) |
| absolute floor | `0.5 bp` | Hard `h` floor while EWMA vol warms up (<10 ticks) |

Fires `buy` when `S⁺ ≥ h`, `sell` when `−S⁻ ≥ h`, resetting the relevant accumulator on each fire.  This solves the structural failure of static thresholds in calm BTC regimes (events get sampled in volatility units, not absolute bps).

**2. 4-indicator confluence vote (legacy momentum stack).**

A directional vote requires `> MIN_VOTES` (currently > 2 → at least 3 votes, strictly greater than the opposing side):

| # | Indicator | Buy vote | Sell vote |
|---|---|---|---|
| I1 | VIDYA fast/slow gap (vol-adaptive threshold) | gap > +threshold | gap < −threshold |
| I2 | Rate of Change (last 8 ticks = ~2 min) | ROC > +threshold | ROC < −threshold |
| I3 | Chande Momentum Oscillator | CMO > +0.15 | CMO < −0.15 |
| I4 | Slope acceleration (2nd half vs 1st half) | accel > 0 AND gap > 0 | accel < 0 AND gap < 0 |

**VIDYA** (Variable Index Dynamic Average) adjusts its smoothing factor by |CMO| — more responsive in trending conditions, quieter in choppy markets.  The vote threshold floor `GAP_THRESHOLD = 0.0001` (1 bp) was lowered from the original 5 bp so the gates actually fire on BTC's normal 15s micro-noise; CUSUM acts as confirmation/veto, the vote provides the directional anchor.

**3. Agreement gate.**

| CUSUM | Vote | Final signal |
|---|---|---|
| directional | directional, same way | that direction (logged as `[STRONG BUY] from BTC`) |
| directional | directional, opposite | `hold` (disagreement) |
| `hold` | directional (> MIN_VOTES) | vote direction |
| directional | `hold` | `hold` (current gate; CUSUM-only fallback is commented out) |
| `hold` | `hold` | `hold` |

Each tick logs e.g.:
```
[BTC 23:34:01] spot=$67,432.10  fast=$67,425.80  slow=$67,410.45  votes B/S=3/0  CUSUM=BUY  buf=87/120  → BUY
```

### Signal Methods

Two public methods expose the BTC signal to the rest of the bot:

| Method | Used in | Logic |
|---|---|---|
| `latestBtcVidyaSignal()` | Step 4 (`poll_for_signal`) only | Returns latest non-hold signal once ≥5 non-holds exist; `BTC_COLD_START_DEFAULT` during warmup |
| `btcSignalByVoteDiff(min_diff=2)` | All other BTC checks (band guard, rescan, pre-buy, monitor T4) — no longer used in STEP 3, which now compares live spot to the market strike directly | Fires `buy`/`sell` when vote margin ≥ 2; **never returns `hold`** — falls back to most recent non-hold signal when diff < 2 (`BTC_COLD_START_DEFAULT` during warmup) |

`btcSignalByVoteDiff` also logs a transition line whenever the signal changes:
```
  [BTC-DIFF 23:34:01] votes B/S=2/0  HOLD → BUY
```

### Cold-Start Behaviour

Until at least **5 non-hold signals** have been emitted, `latestBtcVidyaSignal()` returns `BTC_COLD_START_DEFAULT` (configurable):

| Setting | Effect |
|---|---|
| `hold` | Blocks all BTC-gated trades during warmup (safest) |
| `buy` | Allows buys, blocks flips (optimistic) |
| `sell` | Allows flips, blocks buys (pessimistic) |

---

## Logging

### Session Log — `bot_YYYYMMDD.log`

All `stdout` and `stderr` output is mirrored to a dated log file via the `_RotatingLogFile` / `_Tee` classes.  When launched via the root dispatcher, the prefix and directory come from env vars set by `bot.py`:

| Env var | Default (standalone) | Dispatcher value |
|---|---|---|
| `BOT_LOG_PREFIX` | `kalshi_btc_15_` | `bot_` |
| `BOT_LOG_DIR` | `.` (cwd) | project root |

So a dispatcher run produces `bot_YYYYMMDD.log` at the project root, while a standalone run produces `kalshi_btc_15_YYYYMMDD.log` in the kalshi/ folder.

- **On startup**: any same-prefix `*.log` files from previous dates are automatically moved to `./archive/`
- **At midnight rollover**: the current log file is closed, archived, and a new dated file is opened — transparently, mid-session
- **On shutdown**: file is flushed and closed cleanly in the `finally` block

All log line timestamps (`[POLL]`, `[BTC]`, `[BTC-DIFF]`, `[MON]`) are emitted in **Central US time (CST/CDT)** via the `_cst_now()` helper, regardless of machine timezone. `_utc_now()` is still used internally for duration/deadline arithmetic.

### Prediction Win Rate

Printed before every trade slot:

```
[WIN RATE] Prediction SUCESS rate: 62.5% (TOTAL: 16; SUCCESS: 10; FAIL: 4  )  |  LOSS rate: 25.0% MIXED: 2  |  PV + rate: 58.3% (7/12  has +portfolio)  |  PV Returns: +18.45%
```

Computed from `trade_history.csv` over consecutive row pairs (i, i+1):

| Category | Conditions | Meaning |
|---|---|---|
| **SUCCESS** | direction match AND portfolio grew | Prediction correct AND money made |
| **FAIL (LOSS)** | direction wrong AND portfolio dropped | Prediction wrong AND money lost |
| **MIXED** | any other combination | Right direction but PV dropped, or wrong direction but PV grew |

Additional metrics:

| Metric | Formula | Meaning |
|---|---|---|
| **LOSS rate** | `FAIL / total × 100` | % of trades that were clean losses |
| **PV + rate** | `pairs where PV grew / total pairs × 100` | Portfolio grew regardless of direction |
| **PV Returns** | `(last_pv − first_pv) / first_pv × 100` | Total return from first to latest trade row (e.g. `+18.45%` or `−5.30%`) |

Pairs where `direction`, `actual_direction_previous`, or `portfolio_value` is missing in either record are skipped entirely. `PV Returns` is omitted when fewer than 2 parseable portfolio values exist.

---

## Decision Summary

```
Entry scan result         BTC signal      Kalshi sells   is_drop_real   Action
──────────────────────────────────────────────────────────────────────────────────
dir=YES, BTC=buy          agrees          ≤ 54%          False          BUY YES ✓ (primary)
dir=NO,  BTC=sell         agrees          ≤ 54%          False          BUY NO  ✓ (primary)
any direction             agrees          ≤ 54%          True           keep polling (drop blocks buy)
any direction             against dir     any            any            FLIP (BTC gate alone)
any direction             any             > 54%          True           FLIP (sentiment + drop)
any direction             any             > 54%          False          keep polling (no confirmed drop)
dir=NO,  BTC=sell         sell            buy_ratio>72%  False          BUY NO  ✓ (secondary — BTC + strong buys + no drop)
dir=YES, BTC=buy          buy             buy_ratio>72%  False          BUY YES ✓ (secondary — BTC + strong buys + no drop)
any                       hold            any            any            keep polling
sentiment ≥ 30  AND  max possible sell_ratio < SELL_PCT_THRESHOLD          return BUY  (SELL math-impossible early-exit)
sentiment ≥ 30  AND  sells / SENTIMENT_SIZE > SELL_PCT_THRESHOLD           return SELL (SELL math-guaranteed early-exit)
max_ticks exhausted       any             any            any            return btc_sig (latestBtcVidyaSignal — never hold)

STEP 3 direction — best of 3 voters (majority wins, V1 breaks ties)
──────────────────────────────────────────────────────────────────────
V1  Settled-market momentum (last 6 settled outcomes, majority + recent-3 tiebreak)
    Always votes YES or NO — never abstains.
V2  Live BTC vs market strike ±$15
    live > strike+15 → YES  |  live < strike-15 → NO  |  in band / data missing → abstain
V3  btc.btcSignalWithStrength()
    {buy, strong_buy} → YES  |  {sell, strong_sell} → NO  |  hold → abstain

Tally → direction
  votes_yes > votes_no  → YES
  votes_no  > votes_yes → NO
  tie                    → V1 breaks (V1 always has 1 vote)

Flip confirmation (STEP 5b)           Action
──────────────────────────────────────────────────────────────────────
buy  (flipped dir)                    BUY flipped direction   mode=BUY
sell (flipped dir)                    poll original dir again (STEP 5c)
hold                                  skip trade slot

ORIGINAL-BUY confirmation (STEP 5c)  Action
──────────────────────────────────────────────────────────────────────
buy  (original dir)                   BUY original direction  mode=BUY
sell (original dir, double flip)      BUY flipped direction   mode=FLIP-BUY
hold                                  skip trade slot

Band guard (STEP 5d)                 Action
──────────────────────────────────────────────────────────────────────
bid in band + BTC ok + Kalshi ok      proceed to buy
20s elapsed without entry             run 40-tick × 0.75s rescan
  rescan: band + buy + BTC ok         RECONFIRM direction (best-of-3, V1/V2/V3)
    reconfirmed == current direction    proceed to buy (fresh _peek)
    reconfirmed != current direction    reset timer, continue polling
  rescan: any condition fails          reset timer, continue polling
market window expires                 move to next market (no trade)

Lotto trade (STEP 5d, inside band guard loop)
──────────────────────────────────────────────────────────────────────
Conditions: DO_YOU_HAVE_STOP_SELL=FALSE  AND  LOTTO_TRADE=TRUE
            market age < 320s  AND  live bid < 14¢
Action:     place LOTTO_CONTRACTS × 15¢ immediately inside the loop
            store resp, set _lotto_triggered=True, break band guard
            skip normal sizing/pre-order; go straight to fill-wait & log

STEP 6 pre-order phases (bid 74–77¢ and ≥78¢ only)
──────────────────────────────────────────────────────────────────────────────
Phase 1 target           bid 74–77¢ → wait for live bid ≤ (ptb − 5¢)
                         bid ≥ 78¢  → wait for live bid ≤ (ptb − 11¢)
                         Deadline   → 500s after market open → skip trade
Phase 2 scan             20 ticks × 0.75s, compute_signal == "buy", BTC aligned
  PASS bid 74–77¢        buy at (planning_to_buy − 5¢)
  PASS bid ≥ 78¢         buy at (planning_to_buy − 10¢)
  FAIL any               skip trade slot
bid ≤ 73¢               place directly at 95¢ (no Phase 1/2)

Monitor exit trigger    Condition                                    Action
──────────────────────────────────────────────────────────────────────────────
TAKE_PROFIT             Position closed, TP filled                   Log win, next trade
STOP_LOSS               Live value ≤ SL floor                        Fire-sale @ 5¢, log loss
SELL_SIGNAL [T3]        STRONG_SELL signal + loss > 15%              Fire-sale @ 5¢, log loss
SELL_SIGNAL [T4]        Sells ≥ 57% + loss > 15% + BTC contradicts  Fire-sale @ 5¢, log loss
SELL_SIGNAL [T5]        sell signal + sells% > 72% + events > 100   Fire-sale @ 5¢, log loss

Risk management halts   Condition                                    Action
──────────────────────────────────────────────────────────────────────────────
All four halts below route through the shared _halt_and_shutdown() helper:
   1. cancel_all() — cancel every resting order
   2. position_for(ticker) — if open, fire-sell @ 5¢ (direction inferred
      from the position's signed position_fp, so no UnboundLocalError if
      the trade-slot local `direction` was never assigned)
   3. if HALT_MACHINE_SHUTDOWN=TRUE → os.system("shutdown /s /f /t 30")
   4. return from run()

LOSS-RATE HALT          PV Returns < profit-ratcheted floor          → _halt_and_shutdown()
[MAX_LOSS_RATE]         floor = -33% base, relaxed to -42/-142/-242%
                        as cumulative gains pass 50/75/100%
                        Checked once per trade slot (after WIN RATE)
MIN-PV HALT             portfolio_value < DO_NOT_BUY_IF_PORTFOLIO_BELOW  → _halt_and_shutdown()
[DO_NOT_BUY_IF_…]       Checked once per trade slot (after LOSS-RATE)
TARGET-PV HALT          portfolio_value ≥ day_start × (1 + TPP/100)      → _halt_and_shutdown()
[TARGET_PORTFOLIO_PCT]  TPP = TARGET_PORTFOLIO_PCT; 0 disables
                        Day-start baseline persisted in
                        kalshi_day_start_<YYYYMMDD>.txt (CST)
                        Checked once per trade slot (after MIN-PV)
TRADING-HOURS HALT      local time inside ANY configured halt window     → _halt_and_shutdown()
[HALT_*_TIME]           Windows: HALT_START_TIME / HALT_END_TIME +
                        HALT_START_TIME[1..9] / HALT_END_TIME[1..9]
                        (end < start wraps midnight, e.g. 22:15→02:45)
                        Checked at market open and before each buy
```

---

## File Structure

```
<project root>/
├── bot.py                       Unified dispatcher (reads PLATFORM env, runs subbot)
├── .env                         Shared configuration (PLATFORM + all bot vars)
├── trade_history.csv            Shared trade log — "platform" first column
├── kalshi_day_start_YYYYMMDD.txt  Day-start portfolio baseline for TARGET_PORTFOLIO_PCT
│                                  (auto-created next to the CSV; rolls over at CST midnight)
├── bot_YYYYMMDD.log             Today's session log (stdout + stderr, dispatcher mode)
├── archive/
│     └── bot_YYYYMMDD.log       Previous days' logs (auto-archived at startup / midnight)
├── btc/
│     ├── __init__.py            Re-exports BtcVidyaMonitor, SignalT
│     └── monitor.py             Shared BTC spot monitor (CUSUM + 4-vote confluence)
├── kalshi/
│     ├── bot_kalshi_btc15.py    Kalshi subbot
│     ├── README.md              ← this file
│     └── kalshi_private.pem     RSA private key for API signing
└── polymarket/
      ├── bot_polymarket_btc15.py
      └── PM_README.md
```

In standalone mode (`python kalshi/bot_kalshi_btc15.py`) the CSV and log files instead land in the kalshi/ folder as `trade_history.csv` and `kalshi_btc_15_YYYYMMDD.log`, since `BOT_CSV_PATH` / `BOT_LOG_PREFIX` / `BOT_LOG_DIR` are unset.
