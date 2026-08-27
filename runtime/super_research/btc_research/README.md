# btc_research — BTC 5m Super-Signal research (spy_research mirrored)

Standalone quantitative research pipeline (nothing reused from the repo's
existing signal stack): engineer a noise-filtered composite signal that
captures an **+80-point BTC move before a 50-point adverse drop within 30
minutes** on 5-minute candles. BTC is **24×7** — entries are open **all day**
(00:00–23:59 CST) across four session buckets (full_day, asia_0_8, us_8_16,
eve_16_24).

## Trade rules
| rule | value |
|---|---|
| entry | next bar **open** after the signal bar closes (no lookahead) |
| target | +80 pts (in trade direction) within **12** bars (60 min) |
| stop | 50 pts adverse, monitored only the first **6** bars (30 min) |
| time stop | flat at bar-12 close if TP never hit; capped at the 23:59 day boundary |
| tie | TP+SL touched in the same bar → counted as a **stop** (conservative) |

`win_rate` is strict (time-stop scratches count against it); `tp_before_sl`
compares only resolved trades.

## Verdict under TP 80 / SL 50, 24×7 all-day (61 sessions)
Opening entries around the clock roughly doubles the signal rate vs. the 9–14
window and the edge is **two-sided**, concentrated in the **overnight
`asia_0_8` (00:00–08:00 CST)** window. Under the desk's "A-book = TP-before-SL
> 95%" rule, **nothing clears 95%** across the full day with the tighter 50-pt
stop, so BTC produces **0 A-book** — the whole playbook is B-book:
- **B-book:** greedy ensemble (57 candidates) — **40 trades · 34–6 · 85.0%
  strict & TP-before-SL** · PF 9.07 · +2420 pts · **0.66 signals/day** · avg
  hold 12 min.
- Top setups (all labelled B): LONG `above_vwap+above_pivot+macd_x_up_neg+strong_close`
  (asia_0_8, 8/9) · SHORT `adi_dn+delta_dump+macd_x_dn_pos+hist_turn_dn`
  (asia_0_8, 6/7).

Bot runs continuously (see schedule/, 00:00 daily keep-alive, no stop task).
In-sample over 61 sessions — re-validate forward before trading.

## Files
| file | role |
|---|---|
| `config.py` | every knob: session times, TP/SL/bars, indicator params, grid axes |
| `data.py` | connectors — `YFinanceConnector` (60d of 5m incl. pre-market, disk-cached) + `RobinhoodConnector` stub with the same interface for the live env |
| `features.py` | levels (y-H/L/C, pre-market H/L, floor pivots P/S1/S2/R1/R2), VWAP, volume-profile POC, ADI, volume-delta proxy, MACD (+cross/divergence), ATR, noise inputs, neutral GEX hook |
| `signals.py` | 15 bull + 15 bear boolean blocks + the ATR/volume noise gate |
| `backtest.py` | outcome engine (rules above) + metrics (win rate, PF, maxDD, avg hold) |
| `research.py` | v1 grid: all 2–3 block composites × noise filters × entry windows → `results/all_configs.csv`, `REPORT.md` |
| `iterate.py` | v2: 4-block precision stacking + greedy **ensemble** (union of near-perfect composites until ≥1 signal/day) → `results/iteration2_stacks.csv`, `results/ensemble*.csv`, appends to `REPORT.md` |
| `btc_intraday_bot.py` | **live watcher**: polls completed 5m bars 9:00–14:00 CST for the A-book (hardcoded) + B-book (parsed from `results/ensemble.csv`); overlapping variants collapse to one row per bar+direction with a `confluence` count → `btc_intraday_signals.csv` (CST timestamps, accuracies, signal/target/stop prices + deadlines, VWAP/POC/pivot/ATR context). `--once`, `--backfill-today`, `--poll N` |

## Run
```bash
python research.py    # full grid (~1 min on cached data)
python iterate.py     # precision stacking + ensemble
```

## Honest limitations
- yfinance caps 5m history at ~60 days — every number here is in-sample over
  that window. Validate forward before trusting any "near-100%" config.
- **GEX / options flow:** no free historical gamma-exposure source; the
  pipeline exposes a neutral `gex_bias` hook (excluded from the grid while
  neutral so it can't fake accuracy). Wire a paid feed (SpotGamma etc.) into
  `features.build()` to activate the `gex_*` blocks.
- Volume delta is an intrabar-position proxy (no tick data at this timeframe).
- Fills are assumed at bar open/level touch with no slippage or commissions.

## BTC-specific adaptations
- crypto trades 24×7: the session is the full CST calendar day; the
  "pre-market" levels are the OVERNIGHT range 00:00–09:00 CST
- floor pivots / y-levels come from the prior full calendar day
- POC bins are $25 (six-figure instrument)
- entry window kept at 9:00–14:00 CST for comparability with SPY
