# BTC-15 — default engine (v7, the V7 DMI-stack engine)

Default version per `app/domains/botstation/builtin.py`: **v7**
(`v7_bot_kalshi_btc15.py`). That file is ~20 lines: the engine itself is
[`runtime/prediction-trade/kalshi/v7_engine.py`](../../../v7_engine.py),
shared with the other three V7 bots, and the entry rule is
`app/domains/botstation/dmi_stack.py`.

## The rule

Read BTC's own row on the desk's **CRYPTO** board — the same module the
panel renders from, so the bot and the screen cannot disagree — and require
all four timeframes to point the same way:

```
BTC 79381.00  1m 15↑  2m 37↑  5m 50↑  10m 34↑   ->  buy YES
BTC 79381.00  1m 15↓  2m 37↓  5m 50↓  10m 34↓   ->  buy NO
anything else                                       ->  stand aside
```

Three gates, all of which must pass:

| Gate | Rule |
|---|---|
| DMI stack | 1m, 2m, 5m and 10m all `call`, or all `put`. A blank or flat column blocks — an unknown is not agreement. |
| Timing | strictly **5–300 s** after the market opened (`entry_open_s` / `entry_close_s`). |
| Price | **30–65 c** on the side being bought (`min_price_c` / `max_price_c`). Refused, never clamped. |

Take-profit +20%, stop −40% of the entry, both configurable per launch.

## Order lifecycle

The buy rests at best-bid + 1c, so it usually does **not** fill immediately.
Nothing is monitored until it does: the resting order is remembered, each pass
asks whether it has become a position, and only a real fill opens the ledger
row, rests the take-profit and arms the stop. A market that already has an
order working never receives a second one.

Every sell — take-profit and stop alike — goes through
[`sell_guard.confirm`](../../../sell_guard.py), the desk-wide check shared
by every bot on this desk: there **is** a position on the side being sold, and
there is **no** pending or resting order on the ticker, each read twice ten
seconds apart. The stop cancels its own resting take-profit first, since that
order would otherwise block it.

## Older versions

v2, v3, v4, v5 and v6 remain selectable. Everything below this line documents them and is
unchanged.

---

## A naming note (v2/v3/v4 only)

`v2_bot_kalshi_btc15.py` does `import bot_kalshi_btc15 as v1` and reuses
that module's Kalshi client, `compute_signal`, `determine_direction`,
bankroll/halt logic and constants. `bot_kalshi_btc15.py` **does** exist on
disk: it is a ~50-line shim that re-exports twelve names from
`v4_bot_kalshi_btc15.py`, which is where the real implementation lives. So
despite the local alias name `v1`, **v2's base engine is v4's code** — the
`v1` name in v2's source is stale, not a separate real "v1" version. The
sports bots and the V7 engine import the same shim for the same reason: it is
the desk's shared Kalshi client and order helpers, not anything BTC-specific.

(An earlier revision of this file claimed that shim did not exist and that a
meta-path finder in `bot_launcher.py` stood in for it. The launcher does
install such a finder, but it is a fallback — the file is present, and the
bot station launches these scripts directly rather than through the launcher,
so the file is what actually satisfies the import.)

## Signal source (v2/v4)

No CSV or external ML API — computed locally from two sources:

- `compute_signal(buf)` (v4, line 959) — applied to a rolling deque of
  the **contract's own bid price**, polled from Kalshi.
- `BtcVidyaMonitor` (`../monitor.py`) — a shared Coinbase BTC-USD spot
  poller (15s cadence) combining a CUSUM event filter (López de Prado
  AFML, k=1.5σ EWMA) with a 4-indicator confluence vote (VIDYA fast/slow
  gap, ROC, CMO, slope acceleration; `MIN_VOTES=2`). Agreement on both →
  `strong_buy`/`strong_sell`; one side only → `buy`/`sell`; disagreement
  → `hold`.

  (`cb_btc_signal.py` sits in the same package but is a separate,
  currently-unused Coinbase-auth module — v2 does not import it.)

Direction is decided by **best-of-4 voting**
(`determine_direction_v2`, v2 lines 181–249):

| Vote | Source | Behavior |
|---|---|---|
| V1 | `v1.determine_direction()` (→ v4's settled-market momentum) | never abstains |
| V2 | live BTC spot vs. strike ± `V2_STRIKE_BUFFER` ($4) | one retry after 5s if abstaining |
| V3 | `btcSignalWithStrength()` | buy/strong_buy→YES, sell/strong_sell→NO, hold→abstain |
| V4 | `btcSignalHourly()` | never abstains |

Ties break via V3 (not V4, despite what the docstring implies).

## Per-market decision sequence

Per 15-minute market (`MARKET_LEN_S=900`), up to `MAX_TRADES_PER_MARKET`
entry slots, gated shut once `time-to-close <= MIN_TIME_TO_CLOSE_S`
(470s) so no new entries fire too late.

1. Best-of-4 direction vote.
2. `poll_entry_signal_v2` — a 40-tick bid-sentiment scan; verdict is
   "sell" if the sell-ratio exceeds `SELL_PCT_THRESHOLD`.
3. If "sell" and `compute_buy_score() <= FLIP_BUY_SCORE` (−10), the
   engine **flips direction** rather than skipping.
4. `band_guard_v2` polls until: price sits in the cheap half of the
   entry band (relaxing to the full band after 70% of the order window
   elapses), the BTC-Vidya gate agrees with the side (bypassed on a
   flip), `compute_signal` isn't sell/strong_sell, and a ~30s
   `BUY_SCORE` conviction scan clears a price-tiered floor (`>2` if
   bid<40c, `>=-2` otherwise). The slot is skipped only if the order
   window (`TIME_SEC_TO_ORDER`) expires first.
5. A final `hasRecentStrongAgainst(direction, lookback=20)` check, plus a
   second time-to-close check, can still cancel the slot even after every
   gate above passes.

## Entry price and size

No fixed limit price — buys at whatever the latest confirmed in-band bid
is once every gate clears, between `MIN_ENTRY_CENTS` (42c, env
`MIN_ENTRY_CENTS`) and `MAX_ENTRY_CENTS` (80c, env `MAX_ENTRY_CENTS`).

Size is fixed contracts: `max(1, CONTRACTS)` where `CONTRACTS` = env
`KALSHI_CONTRACTS` (default **50**). The older `CONTRACTS_PV_PCT`
(portfolio-percent sizing, default 25%) is still read but no longer used
for order size — sizing was made fixed desk-wide (per in-code comment).

## Exit

Two layers, both optional/conditional — never an unconditional
hold-to-settlement:

- An optional resting take-profit limit sell (`place_tp_sell`), gated by
  `DO_YOU_HAVE_STOP_SELL`.
- `monitor_trade_v2` — always runs; can fire-sell on: `SELL_SCORE >=
  MON_SELL_SCORE_FIRE` (24) with BTC-against confirmation, bid >
  `MON_HIGH_BID_LOCK` (95c), bid 40–60c with ≤90s left, bid 60–70c with
  ≤45s left; otherwise rides to settlement if bid is already >70c late or
  time runs out. `FIRE_SALE_CENTS` (5c) is the emergency-exit floor
  price. Every sell trigger is gated by `MONITOR_SL_TRIGGER` (default
  `TRUE`) — set false and the monitor only observes/logs, never sells.

## Safety guards

- `DRY_RUN_MODE` env var (default `TRUE`, read as v4's `DRY_RUN`).
- `DO_NOT_BUY_IF_PORTFOLIO_BELOW` halt (default 0 = disabled).
- `TARGET_PORTFOLIO_PCT` daily-profit halt.
- Bankroll-level TP/SL halts (`BANKROLL.target_reached()` /
  `sl_reached()`).
- Trading-hours halt window (`HALT_TIMEZONE`) and a
  `_in_no_trade_window()` check — skips new entries but keeps monitoring
  any open position.
