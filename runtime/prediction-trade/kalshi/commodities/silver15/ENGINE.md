# Silver-15 — default engine (v3, the V7 DMI-stack engine)

Default version per `app/domains/botstation/builtin.py`: **v3**
(`v3_bot_kalshi_silver15.py`). That file is ~20 lines: the engine itself is
[`runtime/prediction-trade/kalshi/v7_engine.py`](../../v7_engine.py),
shared with the other three V7 bots, and the entry rule is
`app/domains/botstation/dmi_stack.py`.

## The rule

Read silver's own row on the desk's **COMMODITIES** board — the same module the
panel renders from, so the bot and the screen cannot disagree — and require
all four timeframes to point the same way:

```
SILVER 66.59  1m 15↑  2m 37↑  5m 50↑  10m 34↑   ->  buy YES
SILVER 66.59  1m 15↓  2m 37↓  5m 50↓  10m 34↓   ->  buy NO
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
[`sell_guard.confirm`](../../sell_guard.py), the desk-wide check shared
by every bot on this desk: there **is** a position on the side being sold, and
there is **no** pending or resting order on the ticker, each read twice ten
seconds apart. The stop cancels its own resting take-profit first, since that
order would otherwise block it.

## Older versions

v1 and v2 remain selectable. Everything below this line documents them and is
unchanged.

---

## Signal source

v2 replaces v1's Yahoo trend/volume score with the DI-dominance DMI engine
ported from the `tradier-bot` project's commodities scanner
(`runtime/indicators/commodity_dmi.py`, shared by all three v2 commodity
bots):

- Pulls the last ~5 days of 1-minute OHLC bars for `SI=F` (silver futures)
  from Yahoo Finance (`yfinance`).
- Computes Wilder DMI (`period=9`) on those 1-minute bars, and again on
  2-minute bars built by merging consecutive 1-minute bars.
- **Side = whichever DI is bigger** — no ADX/DI threshold gates, just
  dominance: `+DI > -DI` → `call`, `-DI > +DI` → `put`
  (`commodity_dmi._commodity_side`).
- **A trade only fires when the 1-minute and 2-minute readings agree.**
  That agreement is the entire confirmation filter — this is the
  multi-timeframe check, not a separate indicator:

  ```python
  signal = m1_side if (m1_side and m1_side == m2_side) else None
  direction = {"call": "LONG", "put": "SHORT"}.get(signal)
  ```

## Per-market decision sequence (`handle_market` in `v2_bot_kalshi_silver15.py`)

1. A new `KXSILVER15M` market is discovered; its quarter mark `T` is derived
   from the market's `close_time`.
2. Waits until `T + BOTSILVER_SIGNAL_CHECK_SEC` (default 150s / 2m30s).
3. From that point, polls `score_commodity_dmi("silver15")` every
   `BOTSILVER_SIGNAL_POLL_SEC` (default 2s) until either a signal appears or
   the band deadline passes. Unlike v1, there is **no dependency on a
   previous-mark CSV or quarter-bat refresh** — the DMI signal is computed
   fresh, in-process, every time.
4. No 1m/2m agreement before the deadline → the market is skipped, no buy.
5. On agreement: `direction="LONG"` → buy `yes`, `direction="SHORT"` → buy `no`.

## Entry price

- Price band: `BOTSILVER_MIN_CENTS`–`BOTSILVER_MAX_CENTS` (default 35–49c).
  Widens to `BOTSILVER_MIN_CENTS`–`BOTSILVER_WIDE_MAX_CENTS` (default 55c) if
  the side's initial ask is already above `BOTSILVER_WIDE_TRIGGER_CENTS`
  (default 60c).
- Waits (polling `BOTSILVER_BAND_POLL_SEC`, default 1s) until the ask lands
  inside the band, or the deadline (`close - BOTSILVER_CLOSE_BUFFER_SEC`,
  default 180s before close) passes without ever landing in range — in
  which case the market is skipped.
- Buys at the band's upper bound as a limit price.
- Size: `BOTSILVER_CONTRACTS` (default 1), fixed — not bankroll-scaled.

## Exit

**No stop-loss — anything unsold rides to settlement.** At market minute
`BOTSILVER_TP_AT_MIN` (default 10), the bot double-confirms the held
position (two position checks 2s apart, aborts the sell if the side
changed between checks) and rests a limit SELL at `BOTSILVER_TP_CENTS`
(default 90c). This is enforced server-side too:
`app/services/bot_manager.py`'s `_NO_STOP_LOSS` set includes
`("silver15", "v2")` — the API refuses a `sl_pct` start request for this
engine rather than silently ignore it.

## Safety guards

- `BOTSILVER_DRY_RUN` (default `TRUE`) — independent of every other bot's
  dry-run flag, so this bot cannot go live by accident.
- `run.bat`/`bot_manager.py` force `BOTSILVER_DRY_RUN=TRUE` whenever the
  station isn't explicitly started in live mode.
- Requires a `.env` in the launch cwd (Kalshi credentials + PEM) or exits
  immediately at startup.
