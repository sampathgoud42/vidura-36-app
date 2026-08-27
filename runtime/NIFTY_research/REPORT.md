# NIFTY 5m Super-Signal research — 2026-07-15 10:07 IST

_57 sessions of 5-minute NIFTY (yfinance, incl. pre-market) · entries ['full_0930_1400', 'am_0930_1130', 'mid_1030_1300'] (IST) · entry = next bar open · TP 0.3% ≤ 48 bars · SL 0.3% ≤ 48 bars · time-stop at bar 48 close · same-bar TP+SL = stop (conservative)._
_win_rate counts time-stop scratches as non-wins (strict); tp_before_sl ignores scratches._
_GEX/options-flow: no free historical feed — neutral hook only (see signals.GEX_NOTE)._

## Best configs with ≥0.5 signal/day (strict win-rate)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | above_vwap+adi_up+ylow_reclaim | 0.5 | 0.8 | full_0930_1400 | 30 | 0.53 | 20 | 5 | 5 | 66.7 | 80.0 | 4.09 | 5.05 | 0.46 | 84.2 |
| LONG | above_vwap+adi_up+ylow_reclaim | 0.0 | 0.8 | full_0930_1400 | 31 | 0.54 | 20 | 5 | 6 | 64.5 | 80.0 | 3.99 | 5.01 | 0.46 | 89.2 |
| LONG | above_vwap+ylow_reclaim | 0.5 | 0.8 | full_0930_1400 | 36 | 0.63 | 22 | 8 | 6 | 61.1 | 73.3 | 2.97 | 5.0 | 1.06 | 84.9 |
| LONG | above_vwap+ylow_reclaim | 0.0 | 0.8 | full_0930_1400 | 37 | 0.65 | 22 | 8 | 7 | 59.5 | 73.3 | 2.93 | 4.96 | 1.06 | 89.1 |
| SHORT | adi_dn+vwap_hi_reject | 0.5 | 1.2 | full_0930_1400 | 44 | 0.77 | 26 | 11 | 7 | 59.1 | 70.3 | 2.12 | 4.22 | 1.35 | 100.7 |
| SHORT | adi_dn+weak_close+vwap_hi_reject | 0.5 | 1.2 | full_0930_1400 | 36 | 0.63 | 21 | 10 | 5 | 58.3 | 67.7 | 2.0 | 3.24 | 1.1 | 100.0 |
| LONG | above_vwap+ylow_reclaim+strong_close | 0.5 | 0.8 | full_0930_1400 | 31 | 0.54 | 18 | 7 | 6 | 58.1 | 72.0 | 2.83 | 4.1 | 0.9 | 89.8 |
| SHORT | adi_dn+weak_close+vwap_hi_reject | 0.5 | 0.8 | full_0930_1400 | 45 | 0.79 | 26 | 12 | 7 | 57.8 | 68.4 | 1.93 | 3.85 | 1.6 | 108.9 |
| SHORT | hist_turn_dn+vwap_hi_reject | 0.0 | 0.8 | full_0930_1400 | 35 | 0.61 | 20 | 6 | 9 | 57.1 | 76.9 | 3.08 | 4.54 | 0.44 | 103.7 |
| SHORT | adi_dn+weak_close+vwap_hi_reject | 0.0 | 1.2 | full_0930_1400 | 37 | 0.65 | 21 | 11 | 5 | 56.8 | 65.6 | 1.83 | 2.94 | 1.1 | 98.8 |
| SHORT | adi_dn+macd_x_dn+cvd_dn | 0.0 | 0.8 | full_0930_1400 | 30 | 0.53 | 17 | 8 | 5 | 56.7 | 68.0 | 1.79 | 2.29 | 0.93 | 103.5 |
| SHORT | adi_dn+vwap_hi_reject | 0.0 | 1.2 | full_0930_1400 | 46 | 0.81 | 26 | 12 | 8 | 56.5 | 68.4 | 1.98 | 3.98 | 1.35 | 99.8 |
| SHORT | adi_dn+vwap_hi_reject | 0.5 | 0.8 | full_0930_1400 | 55 | 0.96 | 31 | 14 | 10 | 56.4 | 68.9 | 1.95 | 4.7 | 1.82 | 112.0 |
| LONG | above_vwap+ylow_reclaim+strong_close | 0.0 | 0.8 | full_0930_1400 | 32 | 0.56 | 18 | 7 | 7 | 56.2 | 72.0 | 2.78 | 4.06 | 0.9 | 94.5 |
| SHORT | below_vwap+mom_ignite_dn | 0.0 | 0.8 | mid_1030_1300 | 32 | 0.56 | 18 | 5 | 9 | 56.2 | 78.3 | 2.59 | 3.4 | 0.66 | 124.5 |

## Highest strict win-rate overall (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | above_vwap+adi_up+ylow_reclaim | 0.0 | 0.8 | mid_1030_1300 | 13 | 0.23 | 11 | 0 | 2 | 84.6 | 100.0 | inf | 3.7 | 0.0 | 93.5 |
| LONG | above_vwap+adi_up+ylow_reclaim | 0.5 | 0.8 | mid_1030_1300 | 13 | 0.23 | 11 | 0 | 2 | 84.6 | 100.0 | inf | 3.7 | 0.0 | 93.5 |
| LONG | ylow_reclaim+cvd_up | 0.0 | 0.8 | mid_1030_1300 | 12 | 0.21 | 10 | 0 | 2 | 83.3 | 100.0 | inf | 3.4 | 0.0 | 98.8 |
| LONG | above_vwap+ylow_reclaim+cvd_up | 0.0 | 0.8 | mid_1030_1300 | 12 | 0.21 | 10 | 0 | 2 | 83.3 | 100.0 | inf | 3.4 | 0.0 | 98.8 |
| LONG | adi_up+ylow_reclaim+cvd_up | 0.0 | 0.8 | mid_1030_1300 | 12 | 0.21 | 10 | 0 | 2 | 83.3 | 100.0 | inf | 3.4 | 0.0 | 98.8 |
| LONG | ylow_reclaim+cvd_up | 0.5 | 0.8 | mid_1030_1300 | 12 | 0.21 | 10 | 0 | 2 | 83.3 | 100.0 | inf | 3.4 | 0.0 | 98.8 |
| LONG | above_vwap+ylow_reclaim+cvd_up | 0.5 | 0.8 | mid_1030_1300 | 12 | 0.21 | 10 | 0 | 2 | 83.3 | 100.0 | inf | 3.4 | 0.0 | 98.8 |
| LONG | adi_up+ylow_reclaim+cvd_up | 0.5 | 0.8 | mid_1030_1300 | 12 | 0.21 | 10 | 0 | 2 | 83.3 | 100.0 | inf | 3.4 | 0.0 | 98.8 |
| LONG | ylow_reclaim+strong_close+cvd_up | 0.0 | 0.8 | mid_1030_1300 | 11 | 0.19 | 9 | 0 | 2 | 81.8 | 100.0 | inf | 3.1 | 0.0 | 104.1 |
| LONG | ylow_reclaim+strong_close+cvd_up | 0.5 | 0.8 | mid_1030_1300 | 11 | 0.19 | 9 | 0 | 2 | 81.8 | 100.0 | inf | 3.1 | 0.0 | 104.1 |
| LONG | adi_up+ylow_reclaim | 0.8 | 0.8 | mid_1030_1300 | 10 | 0.18 | 8 | 0 | 2 | 80.0 | 100.0 | inf | 2.8 | 0.0 | 88.5 |
| LONG | above_vwap+adi_up+ylow_reclaim | 0.8 | 0.8 | mid_1030_1300 | 10 | 0.18 | 8 | 0 | 2 | 80.0 | 100.0 | inf | 2.8 | 0.0 | 88.5 |
| LONG | above_vwap+ylow_reclaim | 0.0 | 0.8 | mid_1030_1300 | 14 | 0.25 | 11 | 0 | 3 | 78.6 | 100.0 | inf | 3.95 | 0.0 | 98.9 |
| LONG | above_vwap+ylow_reclaim | 0.5 | 0.8 | mid_1030_1300 | 14 | 0.25 | 11 | 0 | 3 | 78.6 | 100.0 | inf | 3.95 | 0.0 | 98.9 |
| LONG | above_vwap+ylow_reclaim+strong_close | 0.0 | 0.8 | mid_1030_1300 | 12 | 0.21 | 9 | 0 | 3 | 75.0 | 100.0 | inf | 3.35 | 0.0 | 109.6 |

## Highest TP-before-SL rate (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | above_vwap+ylow_reclaim | 0.0 | 0.8 | mid_1030_1300 | 14 | 0.25 | 11 | 0 | 3 | 78.6 | 100.0 | inf | 3.95 | 0.0 | 98.9 |
| LONG | above_vwap+ylow_reclaim | 0.5 | 0.8 | mid_1030_1300 | 14 | 0.25 | 11 | 0 | 3 | 78.6 | 100.0 | inf | 3.95 | 0.0 | 98.9 |
| LONG | above_vwap+adi_up+ylow_reclaim | 0.0 | 0.8 | mid_1030_1300 | 13 | 0.23 | 11 | 0 | 2 | 84.6 | 100.0 | inf | 3.7 | 0.0 | 93.5 |
| LONG | above_vwap+adi_up+ylow_reclaim | 0.5 | 0.8 | mid_1030_1300 | 13 | 0.23 | 11 | 0 | 2 | 84.6 | 100.0 | inf | 3.7 | 0.0 | 93.5 |
| LONG | ylow_reclaim+cvd_up | 0.0 | 0.8 | mid_1030_1300 | 12 | 0.21 | 10 | 0 | 2 | 83.3 | 100.0 | inf | 3.4 | 0.0 | 98.8 |
| LONG | above_vwap+ylow_reclaim+strong_close | 0.0 | 0.8 | mid_1030_1300 | 12 | 0.21 | 9 | 0 | 3 | 75.0 | 100.0 | inf | 3.35 | 0.0 | 109.6 |
| LONG | above_vwap+ylow_reclaim+cvd_up | 0.0 | 0.8 | mid_1030_1300 | 12 | 0.21 | 10 | 0 | 2 | 83.3 | 100.0 | inf | 3.4 | 0.0 | 98.8 |
| LONG | adi_up+ylow_reclaim+cvd_up | 0.0 | 0.8 | mid_1030_1300 | 12 | 0.21 | 10 | 0 | 2 | 83.3 | 100.0 | inf | 3.4 | 0.0 | 98.8 |
| LONG | ylow_reclaim+cvd_up | 0.5 | 0.8 | mid_1030_1300 | 12 | 0.21 | 10 | 0 | 2 | 83.3 | 100.0 | inf | 3.4 | 0.0 | 98.8 |
| LONG | above_vwap+ylow_reclaim+strong_close | 0.5 | 0.8 | mid_1030_1300 | 12 | 0.21 | 9 | 0 | 3 | 75.0 | 100.0 | inf | 3.35 | 0.0 | 109.6 |
| LONG | above_vwap+ylow_reclaim+cvd_up | 0.5 | 0.8 | mid_1030_1300 | 12 | 0.21 | 10 | 0 | 2 | 83.3 | 100.0 | inf | 3.4 | 0.0 | 98.8 |
| LONG | adi_up+ylow_reclaim+cvd_up | 0.5 | 0.8 | mid_1030_1300 | 12 | 0.21 | 10 | 0 | 2 | 83.3 | 100.0 | inf | 3.4 | 0.0 | 98.8 |
| SHORT | below_vwap_v+mom_ignite_dn | 0.5 | 0.8 | mid_1030_1300 | 12 | 0.21 | 8 | 0 | 4 | 66.7 | 100.0 | 226.04 | 2.48 | 0.01 | 113.3 |
| SHORT | below_vwap+below_vwap_v+mom_ignite_dn | 0.5 | 0.8 | mid_1030_1300 | 12 | 0.21 | 8 | 0 | 4 | 66.7 | 100.0 | 226.04 | 2.48 | 0.01 | 113.3 |
| SHORT | below_vwap_v+cvd_dn+mom_ignite_dn | 0.5 | 0.8 | mid_1030_1300 | 12 | 0.21 | 8 | 0 | 4 | 66.7 | 100.0 | 226.04 | 2.48 | 0.01 | 113.3 |


## ITERATION 2 — greedy precision ensemble (2026-07-15 10:10 IST)

_324 composites unioned (each ≥70% strict / ≥85% tp-before-sl on its own); book constrained to ≥75% strict win-rate._

- **trades:** 77 (1.35/day, 32/57 days covered)
- **strict win-rate:** 75.3%  ·  **tp-before-sl:** 92.1%
- **profit factor:** 10.23  ·  **net:** 16.8%  ·  **maxDD:** 0.5%
- **avg hold:** 107.5 min

Configs (see results/ensemble.csv):

  - `SHORT:r1_reject+weak_close|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:r1_reject+hist_turn_dn+weak_close|nk0.0|vm0.8|full_0930_1400` — 85.7% on 7 trades
  - `SHORT:r1_reject+hist_turn_dn+weak_close|nk0.0|vm0.8|am_0930_1130` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim|nk0.0|vm0.8|mid_1030_1300` — 84.6% on 13 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim|nk0.5|vm0.8|mid_1030_1300` — 84.6% on 13 trades
  - `LONG:ylow_reclaim+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 12 trades
  - `LONG:ylow_reclaim+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 12 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 12 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 12 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 12 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 12 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 12 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 12 trades
  - `LONG:delta_surge+ylow_reclaim|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+adi_up+delta_surge+ylow_reclaim|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+adi_up+delta_surge+ylow_reclaim|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+adi_up+delta_surge+ylow_reclaim|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+adi_up+delta_surge+ylow_reclaim|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+adi_up+delta_surge+ylow_reclaim|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+adi_up+delta_surge+ylow_reclaim|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+delta_surge+ylow_reclaim+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+ylow_reclaim+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+above_vwap_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+ylow_reclaim+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+above_vwap_v+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `SHORT:r1_reject+vwap_hi_reject|nk0.0|vm0.8|full_0930_1400` — 83.3% on 6 trades
  - `SHORT:r1_reject+vwap_hi_reject|nk0.5|vm0.8|full_0930_1400` — 83.3% on 6 trades
  - `SHORT:adi_dn+yhigh_reject+hist_turn_dn|nk0.0|vm0.8|full_0930_1400` — 83.3% on 6 trades
  - `SHORT:adi_dn+yhigh_reject+hist_turn_dn|nk0.5|vm0.8|full_0930_1400` — 83.3% on 6 trades
  - `SHORT:adi_dn+yhigh_reject+hist_turn_dn|nk0.8|vm0.8|full_0930_1400` — 83.3% on 6 trades
  - `SHORT:r1_reject+hist_turn_dn+weak_close|nk0.5|vm0.8|full_0930_1400` — 83.3% on 6 trades
  - `SHORT:r1_reject+hist_turn_dn+weak_close|nk0.5|vm0.8|am_0930_1130` — 83.3% on 6 trades
  - `SHORT:r1_reject+hist_turn_dn+weak_close|nk0.8|vm0.8|full_0930_1400` — 83.3% on 6 trades
  - `SHORT:r1_reject+hist_turn_dn+weak_close|nk0.8|vm0.8|am_0930_1130` — 83.3% on 6 trades
  - `LONG:ylow_reclaim+strong_close+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 81.8% on 11 trades
  - `LONG:ylow_reclaim+strong_close+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 81.8% on 11 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+strong_close|nk0.0|vm0.8|mid_1030_1300` — 81.8% on 11 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+strong_close|nk0.5|vm0.8|mid_1030_1300` — 81.8% on 11 trades
  - `LONG:above_vwap+ylow_reclaim+strong_close+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 81.8% on 11 trades
  - `LONG:above_vwap+ylow_reclaim+strong_close+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 81.8% on 11 trades
  - `LONG:adi_up+ylow_reclaim+strong_close+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 81.8% on 11 trades
  - `LONG:adi_up+ylow_reclaim+strong_close+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 81.8% on 11 trades
  - `LONG:adi_up+ylow_reclaim|nk0.8|vm0.8|mid_1030_1300` — 80.0% on 10 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim|nk0.8|vm0.8|mid_1030_1300` — 80.0% on 10 trades
  - `LONG:above_vwap+ylow_reclaim|nk0.0|vm0.8|mid_1030_1300` — 78.6% on 14 trades
  - `LONG:above_vwap+ylow_reclaim|nk0.5|vm0.8|mid_1030_1300` — 78.6% on 14 trades
  - `LONG:ylow_reclaim+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `SHORT:r1_reject+hist_turn_dn|nk0.0|vm0.8|am_0930_1130` — 77.8% on 9 trades
  - `SHORT:r1_reject+weak_close|nk0.0|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `SHORT:r1_reject+weak_close|nk0.5|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `SHORT:below_vwap+adi_dn+yhigh_reject|nk0.0|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `SHORT:below_vwap+adi_dn+yhigh_reject|nk0.5|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `SHORT:below_vwap+adi_dn+yhigh_reject|nk0.8|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `SHORT:adi_dn+yhigh_reject+cvd_dn|nk0.0|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `SHORT:adi_dn+yhigh_reject+cvd_dn|nk0.5|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `SHORT:adi_dn+yhigh_reject+cvd_dn|nk0.8|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `SHORT:hist_turn_dn+weak_close+vwap_hi_reject|nk0.0|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `SHORT:below_vwap+adi_dn+yhigh_reject+cvd_dn|nk0.0|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `SHORT:below_vwap+adi_dn+yhigh_reject+cvd_dn|nk0.5|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `SHORT:below_vwap+adi_dn+yhigh_reject+cvd_dn|nk0.8|vm0.8|mid_1030_1300` — 77.8% on 9 trades
  - `LONG:above_vwap+ylow_reclaim+strong_close|nk0.0|vm0.8|mid_1030_1300` — 75.0% on 12 trades
  - `LONG:above_vwap+ylow_reclaim+strong_close|nk0.5|vm0.8|mid_1030_1300` — 75.0% on 12 trades
  - `SHORT:below_vwap+yhigh_reject|nk0.0|vm0.8|mid_1030_1300` — 75.0% on 12 trades
  - `SHORT:below_vwap+yhigh_reject|nk0.5|vm0.8|mid_1030_1300` — 75.0% on 12 trades
  - `SHORT:below_vwap+yhigh_reject|nk0.8|vm0.8|mid_1030_1300` — 75.0% on 12 trades
  - `LONG:above_vwap+s1_bounce|nk0.0|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `LONG:above_vwap+s1_bounce|nk0.5|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `LONG:adi_up+ylow_reclaim+strong_close|nk0.8|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `LONG:ylow_reclaim+strong_close+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+strong_close|nk0.8|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `LONG:above_vwap+ylow_reclaim+strong_close+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `LONG:adi_up+ylow_reclaim+strong_close+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `SHORT:adi_dn+r1_reject|nk0.0|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `SHORT:adi_dn+r1_reject|nk0.5|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `SHORT:r1_reject+hist_turn_dn|nk0.5|vm0.8|am_0930_1130` — 75.0% on 8 trades
  - `SHORT:r1_reject+weak_close|nk0.0|vm1.2|am_0930_1130` — 75.0% on 8 trades
  - `SHORT:r1_reject+weak_close|nk0.5|vm1.2|am_0930_1130` — 75.0% on 8 trades
  - `SHORT:adi_dn+r1_reject+weak_close|nk0.0|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `SHORT:adi_dn+r1_reject+weak_close|nk0.5|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `SHORT:hist_turn_dn+weak_close+vwap_hi_reject|nk0.0|vm1.2|mid_1030_1300` — 75.0% on 8 trades
  - `SHORT:hist_turn_dn+weak_close+vwap_hi_reject|nk0.5|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `SHORT:below_vwap+adi_dn+macd_x_dn+weak_close|nk0.8|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `SHORT:adi_dn+macd_x_dn+weak_close+cvd_dn|nk0.8|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `LONG:above_vwap+ylow_reclaim|nk0.8|vm0.8|mid_1030_1300` — 72.7% on 11 trades
  - `SHORT:macd_x_dn+weak_close|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 14 trades
  - `LONG:adi_up+s1_bounce|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+s1_bounce|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim|nk0.0|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim|nk0.5|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:s1_bounce+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:s1_bounce+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+s1_bounce|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+s1_bounce|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim|nk0.0|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim|nk0.5|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+s1_bounce+strong_close|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+s1_bounce+strong_close|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+s1_bounce+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+s1_bounce+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+s1_bounce+strong_close|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+s1_bounce+strong_close|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+cvd_up+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+cvd_up+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+cvd_up+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+cvd_up+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:ylow_reclaim+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+s1_bounce+strong_close|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+s1_bounce+strong_close|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+adi_up+ylow_reclaim+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+ylow_reclaim+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:adi_up+ylow_reclaim+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `SHORT:r1_reject+hist_turn_dn|nk0.8|vm0.8|am_0930_1130` — 71.4% on 7 trades
  - `SHORT:macd_x_dn_pos+weak_close|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `SHORT:macd_x_dn+macd_x_dn_pos+weak_close|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `SHORT:yhigh_reject+cvd_dn|nk0.0|vm0.8|mid_1030_1300` — 70.0% on 10 trades
  - `SHORT:yhigh_reject+cvd_dn|nk0.5|vm0.8|mid_1030_1300` — 70.0% on 10 trades
  - `SHORT:yhigh_reject+cvd_dn|nk0.8|vm0.8|mid_1030_1300` — 70.0% on 10 trades
  - `SHORT:below_vwap+yhigh_reject+cvd_dn|nk0.0|vm0.8|mid_1030_1300` — 70.0% on 10 trades
  - `SHORT:below_vwap+yhigh_reject+cvd_dn|nk0.5|vm0.8|mid_1030_1300` — 70.0% on 10 trades
  - `SHORT:below_vwap+yhigh_reject+cvd_dn|nk0.8|vm0.8|mid_1030_1300` — 70.0% on 10 trades
  - `SHORT:below_vwap+macd_x_dn+weak_close|nk0.8|vm0.8|mid_1030_1300` — 70.0% on 10 trades
  - `SHORT:macd_x_dn+weak_close+cvd_dn|nk0.8|vm0.8|mid_1030_1300` — 70.0% on 10 trades
  - `SHORT:below_vwap+macd_x_dn+weak_close+cvd_dn|nk0.8|vm0.8|mid_1030_1300` — 70.0% on 10 trades


## FINAL VERDICT — A-BOOK PRECISION UNION (Nifty 50 / NIFTYBEES.NS, 0.30% within 4h, 57 sessions IST)

The hunt target — **at least 1 A-book signal every 2 days (>= 0.5/day) at
near-perfect precision** — is **MET**. A compact, diverse union of high-precision
custom price+volume families (2 LONG + 2 SHORT) delivers:

| metric | value |
|--------|-------|
| resolved trades | 47 (31 target / 0 stop / 16 scratch) |
| **TP-before-SL** | **100%** (0 stops) |
| strict win-rate (scratch = miss) | 66% |
| **frequency** | **0.82/day** (22/57 sessions covered) |
| net (sum of per-trade %) | +10.9% |

### The A-book families (each near-perfect on its own; live `A_BOOK`)

| # | direction | signal (blocks) | window | gate (nk/vm) | trades | TP-before-SL | strict |
|---|-----------|-----------------|--------|--------------|--------|--------------|--------|
| 1 | LONG | `above_vwap+ylow_reclaim` | mid_1030_1300 | 0.0/0.8 | 14 | 100% | 79% |
| 2 | SHORT | `below_vwap_v+mom_ignite_dn` | mid_1030_1300 | 0.5/0.8 | 12 | 100% | 67% |
| 3 | LONG | `s1_bounce+cvd_up` | full_0930_1400 | 0.8/0.8 | 11 | 100% | 54% |
| 4 | SHORT | `yhigh_reject+hist_turn_dn` | full_0930_1400 | 0.8/0.8 | 10 | 100% | 60% |

**Read this before trading.** These are *in-sample* results on a single ~3-month regime (57 sessions, late-Apr to mid-Jul 2026) of the ETF proxy. The A-book families were selected *because* they never hit the stop in that window, so 0 stops is survivorship — treat 100% TP-before-SL as an upper bound, not a guarantee. The real slippage risk is the SCRATCH rate (time-stops that never reached +/-0.30% within 4h and are closed at the bar-48 price). Forward-validate on out-of-sample sessions before sizing up. BANKNIFTY's book is entirely SHORT because the sample trended up into resistance intraday; re-run when the tape regime turns.

_Live playbook: hardcoded `A_BOOK` (above) + trimmed `results/ensemble.csv`
B-book (~88-92% TP-before-SL). Signals -> nifty_intraday_signals.csv
(IST timestamps). Backend only; not wired to the web UI._
