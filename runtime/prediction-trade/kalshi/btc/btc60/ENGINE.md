# BTC-60 — default engine (fable5)

Default version per `app/services/bot_registry.py`: **fable5**
(`bot_kalshi_btc60_fable5.py`). `burst` (`bot_kalshi_btc60_burst.py`) is
still selectable but not the default.

## Signal source

The side (YES/NO) itself is simple — spot vs. strike — but three
independent, unrelated gates must all agree before it's tradable:

- **Direction**: `side = "yes" if spot >= strike else "no"`
  (`pick_candidate`, line 798). `spot` is Coinbase spot price from
  `BtcVidyaMonitor` (15s poll, local `btc` package); `strike` comes from
  the Kalshi market's strike field (`_strike()`, lines 644–649).
- **POC confirmation**: `poc_agrees()` (lines 731–733) requires the
  volume Point-of-Control color from `LiquiditySR`/`lsr_run()` (local
  `btc.liquidity_sr` module) to match the side — Green for YES, Red for
  NO. Refreshed at most every 150s (`POC_REFRESH_S`, `PocCache.refresh`,
  lines 708–728).
- **STRONG-signal confirmation**: `strong_confirms()` (lines 750–756)
  requires the most recent `strong_buy`/`strong_sell` tick in
  `btc.strength_history`, within the last 20 ticks (~5 min at 15s
  polling, `STRONG_CONFIRM_LOOKBACK_TICKS`), to agree with the side.
- **Exhaustion filter (NET30)**: `_net30_in_favor()` (lines 759–772)
  computes the signed 30-minute USD net move; the candidate is rejected
  unless it falls in `[NET30_LO, NET30_HI]` = `[0, 60]` (lines 213–214,
  808–811) — filters out entries chasing an already-exhausted move.

No agreement on any of the three → the candidate is skipped
(`GATE ... no recent STRONG BTC signal confirms the side`, etc.).

## Per-market decision sequence

Each hourly `KXBTCD` event is fetched via `current_hour_event()` (only
events closing within 65 minutes are accepted). Entry window:
`entry_open = hour_open + 10min` to `entry_cutoff = hour_open + 30min`
(`ENTRY_START_MIN`=10, `ENTRY_CUTOFF_MIN`=30). The main loop polls every
`POLL_S` (10s) inside that window and, before evaluating candidates,
checks in order: profit target reached, bank stop-loss, portfolio-floor
halt, an existing open position (adopted rather than double-bought), and
a NO-TRADE quiet-hour window (`NO_TRADE_TIMES`/`HALT_TIMEZONE`, default
`17:00-19:30,05:00-08:00` America/Chicago). Only then does
`pick_candidate` run. A market is skipped entirely if: already past
`entry_cutoff`, no strike satisfies bid-band + POC + STRONG + NET30,
`MAX_TRADES_PER_MARKET` (default 1) is reached, or account cash can't
fund even 1 contract.

## Entry price

Among strikes passing every gate, the bot picks the favorite side's live
bid within `[ENTRY_BID_LO, ENTRY_BID_HI]` = `[65, 80]` cents, closest to
`ENTRY_BID_SWEET` = 72c. YES-side candidates need a 5c pricier bid floor
(`YES_BID_LO_BONUS`). Placed as a resting maker buy at that bid.

Size: fixed, not bankroll-scaled — `contracts = max(1, KALSHI_CONTRACTS)`
(default 1), capped by whole-account cash as a hard spend ceiling.

## Exit

Hold-to-TP/SL/deadline, never to settlement (`monitor_position`):

| Env var | Default | Meaning |
|---|---|---|
| `BTC60_TP_PCT` | 15.0% | take-profit: `entry * 1.15` |
| `BTC60_SL_PCT` | 30.0% | stop-loss: `entry * 0.70` |
| `FLATTEN_BEFORE_CLOSE_MIN` (const) | 5 min | force-flatten before close regardless of P&L |

TP/SL env overrides take precedence over the learner/state file's
internally-tuned values once set.

## Safety guards

- `DRY_RUN_MODE` (default `TRUE`) — paper-trades via `PaperBook`.
- Single-instance PID lock (`_acquire_lock`/`_release_lock`) — prevents
  two copies double-trading the shared bankroll.
- Profit-target halt: `BTC60_TARGET_PCT` (0 = disabled).
- Bank stop-loss halt: `BTC60_BANK_SL_PCT` (0 = disabled).
- Portfolio floor: `BTC60_MIN_BANKROLL` (0 = disabled by default).
- Account-cash spend cap — never exceeds the shared account's available
  cash.
- NO-TRADE quiet-hour windows (`NO_TRADE_TIMES`/`HALT_TIMEZONE`).
- Never stacks positions — adopts any existing open position instead of
  buying a second one.
