# Gold-15 — default engine (v2)

Default version per `app/services/bot_registry.py`: **v2** (`v2_bot_kalshi_gold15.py`).
v1 (`bot_kalshi_gold15.py`, Yahoo trend/volume score) is still selectable
but no longer runs by default.

## Signal source

v2 replaces v1's Yahoo trend/volume score with the DI-dominance DMI engine
ported from the `tradier-bot` project's commodities scanner
(`runtime/indicators/commodity_dmi.py`, shared by all three v2 commodity
bots):

- Pulls the last ~5 days of 1-minute OHLC bars for `GC=F` (gold futures)
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

## Per-market decision sequence (`handle_market` in `v2_bot_kalshi_gold15.py`)

1. A new `KXGOLD15M` market is discovered; its quarter mark `T` is derived
   from the market's `close_time`.
2. Waits until `T + BOTGOLD_SIGNAL_CHECK_SEC` (default 150s / 2m30s).
3. From that point, polls `score_commodity_dmi("gold15")` every
   `BOTGOLD_SIGNAL_POLL_SEC` (default 2s) until either a signal appears or
   the band deadline passes. Unlike v1, there is **no dependency on a
   previous-mark CSV or quarter-bat refresh** — the DMI signal is computed
   fresh, in-process, every time.
4. No 1m/2m agreement before the deadline → the market is skipped, no buy.
5. On agreement: `direction="LONG"` → buy `yes`, `direction="SHORT"` → buy `no`.

## Entry price

- Price band: `BOTGOLD_MIN_CENTS`–`BOTGOLD_MAX_CENTS` (default 35–49c).
  Widens to `BOTGOLD_MIN_CENTS`–`BOTGOLD_WIDE_MAX_CENTS` (default 55c) if
  the side's initial ask is already above `BOTGOLD_WIDE_TRIGGER_CENTS`
  (default 60c).
- Waits (polling `BOTGOLD_BAND_POLL_SEC`, default 1s) until the ask lands
  inside the band, or the deadline (`close - BOTGOLD_CLOSE_BUFFER_SEC`,
  default 180s before close) passes without ever landing in range — in
  which case the market is skipped.
- Buys at the band's upper bound as a limit price.
- Size: `BOTGOLD_CONTRACTS` (default 1), fixed — not bankroll-scaled.

## Exit

**No stop-loss — anything unsold rides to settlement.** At market minute
`BOTGOLD_TP_AT_MIN` (default 10), the bot double-confirms the held
position (two position checks 2s apart, aborts the sell if the side
changed between checks) and rests a limit SELL at `BOTGOLD_TP_CENTS`
(default 90c). This is enforced server-side too:
`app/services/bot_manager.py`'s `_NO_STOP_LOSS` set includes
`("gold15", "v2")` — the API refuses a `sl_pct` start request for this
engine rather than silently ignore it.

## Safety guards

- `BOTGOLD_DRY_RUN` (default `TRUE`) — independent of every other bot's
  dry-run flag, so this bot cannot go live by accident.
- `run.bat`/`bot_manager.py` force `BOTGOLD_DRY_RUN=TRUE` whenever the
  station isn't explicitly started in live mode.
- Requires a `.env` in the launch cwd (Kalshi credentials + PEM) or exits
  immediately at startup.
