# Sports — default engine (main)

Default version per `app/services/bot_registry.py`: **main**
(`bot_kalshi_main.py`). `bot_kalshi_sports_v1.py`/`v2.py` are still
selectable but not the default — and are also imported *by* `main` as the
per-sport evaluation backends. See
[ENGINE_parley.md](ENGINE_parley.md) for the parlay bot, which reuses this
engine's plumbing.

Multi-sport: plugs in per-sport adapters from `sport_adapters/` (contract
in `sport_adapters/base.py`). Only **tennis** and **baseball** are live
(`MAIN_SPORTS_LIST`); basketball/cricket/hockey/soccer/golf are stubs and
never trade.

## Signal source

No single global model — each adapter's `evaluate()` does the work and
returns a signal dict; the engine just consumes `action`/`bid`/`confidence`.

- **Tennis** (`sport_adapters/tennis.py` → `bot_kalshi_sports_v1` →
  `tennis/predict_v5.py`): a rule-based situation engine (double-break /
  set-lead / server-holding heuristics, situations A–F or fallback) picks
  the side and a confidence *label*, not a numeric probability. That raw
  signal is then gated by a **fixed price band + situational whitelist**
  — not a model-edge threshold: `entry_gate()` requires the bid strictly
  in **50–62c** (no env override), plus one of: F1 (bid ≤59c, situation
  not A/E), F2 (fallback), F3 (ITF-M, 06:00–11:00 CST), F4 (WTA + `high`
  confidence). A "ghost guard" refuses to trade in the ambiguous window
  between sets.
- **Baseball** (`sport_adapters/baseball.py` → `bot_kalshi_sports_v2` →
  `baseball/prediction_baseball_v1.py`): a real numeric win-probability
  model — normal-approximation of remaining run-differential using RE24
  base/out expected runs + home-field decay — compared against the
  market's live YES bid as the implied probability:
  `edge_c = model_WP*100 - live_bid`. A BUY requires
  `edge_c >= BASEBALL_MIN_EDGE_C` (default 6c) inside
  `BASEBALL_BID_LO`–`HI` (30–84c), plus an external "sports4cast" win%
  gate ≥ `BASEBALL_4CAST_MIN_PCT` (50%).

## Per-event decision sequence

Each discovered match gets its own polling task running `adapter.evaluate()`
every `adapter.cfg.poll_s`. A BUY signal is acted on only if
`SPORT_PLACE_ORDERS=TRUE`, the leader's bid isn't already "decided"
(`leader_bid > SPORT_DECIDED_BID` = 90c), and a market/side resolves.
`execute_trade()` then gates, in order:

1. Profit-target halt.
2. Global pause.
3. **Never buy NO** — this engine only ever buys the favored side's YES.
4. Spread stability (`SPORT_SPREAD_MAX_C` = 3c, waits/re-validates up to
   `SPORT_SPREAD_TIMEOUT_S` = 120s).
5. **One-entry-per-match-ever** persistent ledger
   (`match_ledger.json`).
6. API-reconciled day/week loss "brake" (tennis: −$60/day, −$150/week).
7. Per-sport bank cap (`SportBook.can_buy`).
8. Match-exposure check (no existing position/resting order already).

Baseball additionally requires inning ≥ `BASEBALL_MIN_INNING` (3), and
inning ≥ 5 for medium-confidence signals.

## Entry price and size

Limit price = signal bid + `<SPORT>_PRICE_BUMP_C`: tennis uses 0 (rests
at bid, maker-only, 60s fill window then cancel — never chases);
baseball defaults to `SPORT_PRICE_BUMP_C` = 5c.

Size is **fixed contracts per sport**, not bankroll-scaled: tennis flat
`TENNIS_CONTRACTS` = 20 (confidence can only shrink this, never grow it);
baseball sizes 1.5x larger (`ultra_mult`) on `CONF_ULTRA` edge. Cost is
checked against the sport's own dollar bank, not the whole portfolio.

## Exit

- **Tennis**: fixed 97c TP (`TENNIS_TP_CEILING_C`), entry-relative stop
  at `entry - 20c` (`TENNIS_STOP_LOSS_C`) with a 1-strike confirm, plus a
  30c hard floor backstop (`SL_FLOOR_C`). No favorite-comeback firesell
  unless `TENNIS_FIRESELL_EXITS=TRUE`.
- **Baseball**: scalp TP at `+BASEBALL_SCALP_PCT%` (default 10%), stop at
  `entry - BASEBALL_STOP_LOSS_C` (18c), plus an immediate "score-flip"
  exit if a bought leading team falls behind
  (`BASEBALL_SCORE_FLIP_EXIT`).
- A generic guardian enforces global price bands
  (`SPORT_TP_CEILING_C` = 97c, `SPORT_SL_FLOOR_C` = 9c) every
  `SPORT_TP_GUARD_S` (120s) regardless of adapter, on top of any
  sport-specific TP.

## Safety guards

- `MAIN_PAPER` (default `TRUE`) — simulates the whole pipeline against
  live quotes with no real orders.
- `SPORT_MAX_CONCURRENCY` (12) concurrent match watchers.
- Per-sport bank drawdown halt (`<SPORT>_STOP_LOSS_PCT`).
- Global portfolio target/loss floor drain-and-halt
  (`TARGET_PORTFOLIO_PCT`, `SPORT_LOSS_LIMIT_USD`/`PCT`).
- Day/week API-reconciled loss brakes.
- `SPORT_SELL_CONFIRMS` (3) never-sell-naked triple-confirm.
- Startup adoption of pre-existing positions into the same guardian, so a
  restart never orphans an open position.
