# Parley — default (and only) engine (v1)

Default version per `app/services/bot_registry.py`: **v1**
(`bot_kalshi_parley.py`). Same family as the sports bot — it imports
`bot_kalshi_main.py` (as `eng`: config bootstrap, spread gate, sell-confirm,
trade CSV, P&L reconciliation), `bot_kalshi_sports_v1.py` (as `tv1`/`v1`:
order placement, `DRY_RUN`), and `sport_adapters` (the shared bank-risk
gate). See [../sports/ENGINE_main.md](ENGINE_main.md) for the leg-scoring
plumbing this reuses.

## Leg selection and combining

A leg is a single live match where exactly one participant's YES bid is
strictly above `PARLEY_MIN_PROB_C` (default 80c) — decided in
`_qualify_tennis` (currently the only qualifier; tennis-only via
`_QUALIFIERS`). Gates, in order:

1. A live scoreboard exists and isn't completed.
2. The match is at least in set `PARLEY_MIN_SET` (default 2).
3. Exactly one participant's `yes_bid > MIN_PROB_C` — if **both** sides
   clear the threshold, the match is rejected as an inconsistent book.
4. Unless `PARLEY_LEAD_SCOPE=off` (default `current`), the favored
   participant must actually be leading games in the specified set.

Before qualification even runs, `_collect_legs` filters out markets that
are postponed/delayed/cancelled, stale beyond `CFG.max_live_hours`, or
not confirmed live by the sport adapter (e.g. SofaScore for tennis). Legs
are always the **YES side of the leading participant** — never NO.
Qualifying legs sort by probability descending; the scan needs
`len(legs) >= PARLEY_MIN_LEGS` (floor 2) to proceed, and truncates to
`PARLEY_MAX_LEGS` if set (default 0 = no cap).

Legs are combined via Kalshi's multivariate-event-collection endpoint:
`_pick_collection` finds an open collection whose events are a superset
of the legs' events and whose size range fits the leg count;
`_create_combined_market` then creates/fetches the combined market.

## Decision sequence (`_enter`, scan loop every `SCAN_S`=60s)

Skip immediately if: `BOOK.halted` (bank drawdown halt), already
`len(_OPEN) >= PARLEY_MAX_OPEN` (default 1), or inside
`PARLEY_COOLDOWN_S` (default 900s) since the last entry. Otherwise:

1. Combo key = sorted leg tickers; if already traded within
   `PARLEY_LEDGER_KEEP_DAYS` (default 3), skip.
2. A hosting collection must exist.
3. Combined market is priced: theoretical = product of leg
   probabilities; empty book falls back to theoretical (with a
   limit-fallback path gated by `PARLEY_LIMIT_FALLBACK`). Rejected if the
   entry price is below `PARLEY_MIN_PRICE_C` (2c) or the ask exceeds
   `PARLEY_MAX_PRICE_C` (95c).
4. `BOOK.can_buy(cost_usd)` — bank gate: rejects if halted or cost
   exceeds remaining bank (`bank + min(0, realized_pnl) − open_cost`).
5. `_brake_check` — API-reconciled day/week loss brakes
   (`PARLEY_DAY_LOSS_HALT_USD`=60, `PARLEY_WEEK_LOSS_HALT_USD`=150),
   computed from real fills+settlements; **fails safe** — halts on API
   error rather than trading blind.
6. If `PARLEY_PLACE_ORDERS=FALSE`, it's signal-only: no order, ledger not
   burned.

The ledger entry is written *before* the order to prevent a double-entry
on crash.

## Entry price and size

`limit_c = min(MAX_PRICE_C, ask + PARLEY_SLIPPAGE_C)` (slippage default
3c). Sent as a marketable IOC buy (Kalshi V2 has no market order type —
this emulates one): `side="bid"`, `time_in_force="immediate_or_cancel"`.
Contracts = `max(1, PARLEY_CONTRACTS)` (default 10). If the combined
market's book is empty and `PARLEY_LIMIT_FALLBACK=TRUE`, it instead rests
a GTC maker buy at the theoretical price for up to `PARLEY_FILL_WAIT_S`
(30s), polling every `PARLEY_FILL_POLL_S` (5s); unfilled resting orders
are cancelled.

## Exit

Managed by `_guardian`, polling every `PARLEY_GUARD_S` (120s):

| Env var | Default | Meaning |
|---|---|---|
| `PARLEY_TP_CEILING_C` | 97c | take-profit resting sell |
| `PARLEY_STOP_LOSS_C` | 20c | entry-relative stop: `entry - 20c` |
| `PARLEY_STOP_CONFIRM` | 1 | consecutive cycles required before a stop fires |
| `PARLEY_SL_FLOOR_C` | 15c | hard floor — exits regardless of entry-relative math |

Both TP and stop exits go through `eng._exit_position(..., risk_off=True)`
— TP can be deferred by the spread guard, but a loss cut cannot. There is
no hold-to-settlement path by design: combos not hit by TP/stop just ride
until Kalshi settles them (closure detected via position disappearance).

## Safety guards

- `PARLEY_PAPER` (default `FALSE`) — paper mode simulates the buy, no
  real order. `PARLEY_PAPER_CREATE_MARKET` (default `TRUE`) controls
  whether paper mode still creates a real combined market on Kalshi to
  price against, or prices purely theoretically.
- One-entry-per-combination persistent ledger, survives restarts —
  written before the order, only released on a confirmed zero-fill.
- `PARLEY_MAX_OPEN` (default 1) concurrent parlays;
  `PARLEY_COOLDOWN_S` (default 900s) between entries.
- Bank drawdown halt via `SportBook`/`PARLEY_STOP_LOSS_PCT` (default
  50%) — halts new buys, not existing positions.
- API-reconciled day/week loss brakes, fail-safe on API error.
- Never sells naked — every TP/stop exit triple-confirms an open
  position first via `eng._confirm_open_position`.
- `PARLEY_PLACE_ORDERS` (default `TRUE`) can be set `FALSE` for
  signal-only dry runs; `v1.DRY_RUN` also short-circuits real order
  submission independently.
