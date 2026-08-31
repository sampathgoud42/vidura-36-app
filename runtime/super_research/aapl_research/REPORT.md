# AAPL 5m Super-Signal research — 2026-07-15 15:03 CST

_60 sessions of 5-minute AAPL (yfinance, incl. pre-market) · entries ['full_0845_1400', 'am_0845_1130', 'mid_1030_1300', 'pm_1130_1400'] (CST) · entry = next bar open · TP 0.3% ≤ 48 bars · SL 0.3% ≤ 48 bars · time-stop at bar 48 close · same-bar TP+SL = stop (conservative)._
_win_rate counts time-stop scratches as non-wins (strict); tp_before_sl ignores scratches._
_GEX/options-flow: no free historical feed — neutral hook only (see signals.GEX_NOTE)._

## Best configs with ≥2 signal/day (strict win-rate)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHORT | below_vwap+cvd_dn | 0.8 | 0.8 | am_0845_1130 | 240 | 4.0 | 142 | 98 | 0 | 59.2 | 59.2 | 1.45 | 13.2 | 4.5 | 25.0 |
| LONG | above_vwap+adi_up+above_pivot | 0.8 | 1.2 | am_0845_1130 | 171 | 2.85 | 100 | 70 | 1 | 58.5 | 58.8 | 1.43 | 9.05 | 2.1 | 24.7 |
| LONG | delta_surge+above_pivot+strong_close | 0.5 | 0.8 | am_0845_1130 | 142 | 2.37 | 83 | 58 | 1 | 58.5 | 58.9 | 1.43 | 7.55 | 3.3 | 23.0 |
| LONG | delta_surge+above_pivot+strong_close | 0.5 | 1.2 | am_0845_1130 | 142 | 2.37 | 83 | 58 | 1 | 58.5 | 58.9 | 1.43 | 7.55 | 3.3 | 23.0 |
| LONG | above_vwap+delta_surge+above_pivot | 0.0 | 0.8 | am_0845_1130 | 151 | 2.52 | 88 | 62 | 1 | 58.3 | 58.7 | 1.42 | 7.85 | 3.3 | 24.9 |
| LONG | above_vwap+delta_surge+above_pivot | 0.0 | 1.2 | am_0845_1130 | 151 | 2.52 | 88 | 62 | 1 | 58.3 | 58.7 | 1.42 | 7.85 | 3.3 | 24.9 |
| LONG | delta_surge+above_pivot+strong_close | 0.0 | 0.8 | am_0845_1130 | 153 | 2.55 | 89 | 63 | 1 | 58.2 | 58.6 | 1.42 | 7.85 | 3.9 | 22.8 |
| LONG | delta_surge+above_pivot+strong_close | 0.0 | 1.2 | am_0845_1130 | 153 | 2.55 | 89 | 63 | 1 | 58.2 | 58.6 | 1.42 | 7.85 | 3.9 | 22.8 |
| LONG | above_vwap+above_pivot | 0.8 | 1.2 | am_0845_1130 | 213 | 3.55 | 124 | 88 | 1 | 58.2 | 58.5 | 1.41 | 10.85 | 2.35 | 25.2 |
| SHORT | adi_dn+cvd_dn | 0.8 | 0.8 | am_0845_1130 | 203 | 3.38 | 118 | 85 | 0 | 58.1 | 58.1 | 1.39 | 9.9 | 4.5 | 26.3 |
| SHORT | below_vwap+adi_dn+cvd_dn | 0.8 | 0.8 | am_0845_1130 | 203 | 3.38 | 118 | 85 | 0 | 58.1 | 58.1 | 1.39 | 9.9 | 4.5 | 26.3 |
| LONG | above_vwap+adi_up+above_pivot | 0.5 | 1.2 | am_0845_1130 | 224 | 3.73 | 130 | 91 | 3 | 58.0 | 58.8 | 1.45 | 12.23 | 2.7 | 26.7 |
| LONG | above_pivot+cvd_up | 0.8 | 1.2 | am_0845_1130 | 162 | 2.7 | 94 | 67 | 1 | 58.0 | 58.4 | 1.41 | 8.15 | 3.0 | 25.4 |
| LONG | above_vwap+above_pivot+cvd_up | 0.8 | 1.2 | am_0845_1130 | 162 | 2.7 | 94 | 67 | 1 | 58.0 | 58.4 | 1.41 | 8.15 | 3.0 | 25.4 |
| LONG | above_vwap+delta_surge+above_pivot | 0.5 | 0.8 | am_0845_1130 | 143 | 2.38 | 83 | 59 | 1 | 58.0 | 58.5 | 1.41 | 7.25 | 3.3 | 25.3 |

## Highest strict win-rate overall (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | hist_turn_up+rvol_thrust_up | 0.0 | 0.8 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | above_vwap+hist_turn_up+rvol_thrust_up | 0.0 | 0.8 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | hist_turn_up+strong_close+rvol_thrust_up | 0.0 | 0.8 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | hist_turn_up+strong_close+above_vwap_v | 0.0 | 0.8 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | hist_turn_up+rvol_thrust_up+above_vwap_v | 0.0 | 0.8 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | hist_turn_up+rvol_thrust_up | 0.0 | 1.2 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | above_vwap+hist_turn_up+rvol_thrust_up | 0.0 | 1.2 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | hist_turn_up+strong_close+rvol_thrust_up | 0.0 | 1.2 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | hist_turn_up+strong_close+above_vwap_v | 0.0 | 1.2 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | hist_turn_up+rvol_thrust_up+above_vwap_v | 0.0 | 1.2 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| SHORT | below_vwap+r1_reject | 0.5 | 0.8 | mid_1030_1300 | 15 | 0.25 | 13 | 2 | 0 | 86.7 | 86.7 | 6.5 | 3.3 | 0.3 | 57.7 |
| LONG | above_pivot+hist_turn_up+rvol_thrust_up | 0.8 | 0.8 | full_0845_1400 | 13 | 0.22 | 11 | 2 | 0 | 84.6 | 84.6 | 5.5 | 2.7 | 0.3 | 14.2 |
| LONG | above_pivot+hist_turn_up+rvol_thrust_up | 0.8 | 1.2 | full_0845_1400 | 13 | 0.22 | 11 | 2 | 0 | 84.6 | 84.6 | 5.5 | 2.7 | 0.3 | 14.2 |
| LONG | hist_turn_up+above_vwap_v | 0.0 | 0.8 | am_0845_1130 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 17.3 |
| LONG | above_vwap+hist_turn_up+above_vwap_v | 0.0 | 0.8 | am_0845_1130 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 17.3 |

## Highest TP-before-SL rate (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | hist_turn_up+rvol_thrust_up | 0.0 | 0.8 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | above_vwap+hist_turn_up+rvol_thrust_up | 0.0 | 0.8 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | hist_turn_up+strong_close+rvol_thrust_up | 0.0 | 0.8 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | hist_turn_up+strong_close+above_vwap_v | 0.0 | 0.8 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | hist_turn_up+rvol_thrust_up+above_vwap_v | 0.0 | 0.8 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | hist_turn_up+rvol_thrust_up | 0.0 | 1.2 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | above_vwap+hist_turn_up+rvol_thrust_up | 0.0 | 1.2 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | hist_turn_up+strong_close+rvol_thrust_up | 0.0 | 1.2 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | hist_turn_up+strong_close+above_vwap_v | 0.0 | 1.2 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | hist_turn_up+rvol_thrust_up+above_vwap_v | 0.0 | 1.2 | am_0845_1130 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.0 | 18.5 |
| LONG | vwap_reclaim+above_vwap_v | 0.0 | 0.8 | full_0845_1400 | 14 | 0.23 | 8 | 1 | 5 | 57.1 | 88.9 | 2.65 | 1.49 | 0.3 | 71.8 |
| LONG | vwap_reclaim_v+above_vwap_v | 0.0 | 0.8 | full_0845_1400 | 14 | 0.23 | 8 | 1 | 5 | 57.1 | 88.9 | 2.65 | 1.49 | 0.3 | 71.8 |
| LONG | vwap_reclaim+above_vwap+above_vwap_v | 0.0 | 0.8 | full_0845_1400 | 14 | 0.23 | 8 | 1 | 5 | 57.1 | 88.9 | 2.65 | 1.49 | 0.3 | 71.8 |
| LONG | vwap_reclaim+vwap_reclaim_v+above_vwap_v | 0.0 | 0.8 | full_0845_1400 | 14 | 0.23 | 8 | 1 | 5 | 57.1 | 88.9 | 2.65 | 1.49 | 0.3 | 71.8 |
| LONG | above_vwap+vwap_reclaim_v+above_vwap_v | 0.0 | 0.8 | full_0845_1400 | 14 | 0.23 | 8 | 1 | 5 | 57.1 | 88.9 | 2.65 | 1.49 | 0.3 | 71.8 |


## ITERATION 2 — greedy precision ensemble (2026-07-15 15:13 CST)

_738 composites unioned (each ≥70% strict / ≥85% tp-before-sl on its own); book constrained to ≥75% strict win-rate._

- **trades:** 120 (2.0/day, 50/60 days covered)
- **strict win-rate:** 75.8%  ·  **tp-before-sl:** 82.0%
- **profit factor:** 4.43  ·  **net:** 21.5%  ·  **maxDD:** 0.6%
- **avg hold:** 38.2 min

Configs (see results/ensemble.csv):

  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 8 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 8 trades
  - `LONG:above_vwap+above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 8 trades
  - `LONG:above_vwap+above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 8 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 8 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 8 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 8 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 8 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 8 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 8 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 8 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 8 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 8 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 8 trades
  - `LONG:hist_turn_up+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:hist_turn_up+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+adi_up+hist_turn_up+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+adi_up+hist_turn_up+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+delta_surge+hist_turn_up+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+delta_surge+hist_turn_up+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+above_pivot+hist_turn_up+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+above_pivot+hist_turn_up+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+above_pivot+hist_turn_up+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+above_pivot+hist_turn_up+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+hist_turn_up+strong_close+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+hist_turn_up+strong_close+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+hist_turn_up+strong_close+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+hist_turn_up+strong_close+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:adi_up+delta_surge+hist_turn_up+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:adi_up+delta_surge+hist_turn_up+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:adi_up+hist_turn_up+strong_close+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:adi_up+hist_turn_up+strong_close+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:adi_up+hist_turn_up+strong_close+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:adi_up+hist_turn_up+strong_close+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+rvol_thrust_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+rvol_thrust_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+cvd_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+cvd_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:macd_x_up+hist_turn_up+strong_close+cvd_up|nk0.0|vm1.2|full_0845_1400` — 100.0% on 7 trades
  - `LONG:macd_x_up+hist_turn_up+strong_close+cvd_up|nk0.5|vm1.2|full_0845_1400` — 100.0% on 7 trades
  - `LONG:macd_x_up+hist_turn_up+strong_close+cvd_up|nk0.8|vm1.2|full_0845_1400` — 100.0% on 7 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:yhigh_break+hist_turn_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:yhigh_break+above_pivot+hist_turn_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+cvd_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+cvd_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+cvd_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+cvd_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+cvd_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+cvd_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+cvd_up|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+cvd_up|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+cvd_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+cvd_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+cvd_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+cvd_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v+cvd_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v+cvd_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v+cvd_up|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v+cvd_up|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:hist_turn_up+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 90.0% on 10 trades
  - `LONG:hist_turn_up+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 90.0% on 10 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 90.0% on 10 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 90.0% on 10 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 90.0% on 10 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 90.0% on 10 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 90.0% on 10 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 90.0% on 10 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 90.0% on 10 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 90.0% on 10 trades
  - `LONG:above_vwap+hist_turn_up+strong_close+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 90.0% on 10 trades
  - `LONG:above_vwap+hist_turn_up+strong_close+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 90.0% on 10 trades
  - `LONG:above_vwap+hist_turn_up+strong_close+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 90.0% on 10 trades
  - `LONG:above_vwap+hist_turn_up+strong_close+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 90.0% on 10 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 90.0% on 10 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 90.0% on 10 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 90.0% on 10 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 90.0% on 10 trades
  - `LONG:hist_turn_up+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+adi_up+hist_turn_up+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+adi_up+hist_turn_up+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+delta_surge+hist_turn_up+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+delta_surge+hist_turn_up+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+above_pivot+hist_turn_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+above_pivot+hist_turn_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+hist_turn_up+strong_close+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+hist_turn_up+strong_close+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+hist_turn_up+strong_close+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+hist_turn_up+strong_close+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+cvd_up|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+cvd_up|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:adi_up+delta_surge+hist_turn_up+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:adi_up+delta_surge+hist_turn_up+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:adi_up+hist_turn_up+strong_close+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:adi_up+hist_turn_up+strong_close+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:adi_up+hist_turn_up+strong_close+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:adi_up+hist_turn_up+strong_close+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+rvol_thrust_up|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+rvol_thrust_up|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+cvd_up|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+cvd_up|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+cvd_up_v|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+cvd_up_v|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v+cvd_up|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v+cvd_up|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v+cvd_up_v|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v+cvd_up_v|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v+cvd_up|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v+cvd_up|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v+cvd_up_v|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v+cvd_up_v|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up+cvd_up_v|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up+cvd_up_v|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `SHORT:below_vwap+r1_reject|nk0.8|vm0.8|mid_1030_1300` — 88.9% on 9 trades
  - `LONG:hist_turn_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+hist_turn_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+hist_turn_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+hist_turn_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+hist_turn_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:macd_x_up+hist_turn_up+cvd_up|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `LONG:macd_x_up+hist_turn_up+cvd_up|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `LONG:macd_x_up+hist_turn_up+cvd_up|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+adi_up+hist_turn_up+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+adi_up+hist_turn_up+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+adi_up+hist_turn_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+adi_up+hist_turn_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+delta_surge+hist_turn_up+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+delta_surge+hist_turn_up+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+delta_surge+hist_turn_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+delta_surge+hist_turn_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+hist_turn_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+hist_turn_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+hist_turn_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+hist_turn_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+macd_x_up+hist_turn_up+cvd_up|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+macd_x_up+hist_turn_up+cvd_up|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+macd_x_up+hist_turn_up+cvd_up|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+cvd_up|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+cvd_up|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_vwap+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+delta_surge+hist_turn_up+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+delta_surge+hist_turn_up+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+delta_surge+hist_turn_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+delta_surge+hist_turn_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+macd_x_up+hist_turn_up+cvd_up|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `LONG:adi_up+macd_x_up+hist_turn_up+cvd_up|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `LONG:adi_up+macd_x_up+hist_turn_up+cvd_up|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `LONG:adi_up+hist_turn_up+strong_close+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+hist_turn_up+strong_close+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+hist_turn_up+strong_close+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+hist_turn_up+strong_close+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+cvd_up|nk0.0|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+cvd_up|nk0.0|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.0|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.0|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+above_vwap_v|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+above_vwap_v|nk0.8|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+cvd_up_v|nk0.0|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+cvd_up_v|nk0.0|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+rvol_thrust_up|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+rvol_thrust_up|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+cvd_up_v|nk0.0|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+cvd_up_v|nk0.0|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+cvd_up|nk0.0|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+cvd_up|nk0.0|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.0|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.0|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v+cvd_up|nk0.0|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v+cvd_up|nk0.0|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v+cvd_up_v|nk0.0|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v+cvd_up_v|nk0.0|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+cvd_up|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+cvd_up|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+cvd_up_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+strong_close+rvol_thrust_up+cvd_up_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v+cvd_up|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v+cvd_up|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v+cvd_up_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+strong_close+above_vwap_v+cvd_up_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v+cvd_up|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v+cvd_up|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v+cvd_up_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+rvol_thrust_up+above_vwap_v+cvd_up_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up+cvd_up_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:hist_turn_up+rvol_thrust_up+cvd_up+cvd_up_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:hist_turn_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:hist_turn_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:below_vwap+r1_reject|nk0.5|vm0.8|mid_1030_1300` — 86.7% on 15 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+hist_turn_up|nk0.0|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+hist_turn_up|nk0.5|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+s1_bounce|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+s1_bounce|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+s1_bounce|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+s1_bounce+cvd_up|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:adi_up+s1_bounce+cvd_up|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:adi_up+s1_bounce+cvd_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:delta_surge+hist_turn_up+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+hist_turn_up+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:yhigh_break+hist_turn_up+strong_close|nk0.0|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:yhigh_break+hist_turn_up+strong_close|nk0.5|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:yhigh_break+hist_turn_up+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:yhigh_break+hist_turn_up+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:hist_turn_up+above_vwap_v+cvd_up|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:hist_turn_up+above_vwap_v+cvd_up|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:hist_turn_up+above_vwap_v+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:hist_turn_up+above_vwap_v+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+hist_turn_up|nk0.0|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+hist_turn_up|nk0.5|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+vwap_reclaim_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+vwap_reclaim_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+hist_turn_up+strong_close|nk0.0|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+hist_turn_up+strong_close|nk0.5|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+s1_bounce+cvd_up|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+s1_bounce+cvd_up|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+s1_bounce+cvd_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+delta_surge+hist_turn_up+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_vwap+delta_surge+hist_turn_up+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_vwap+yhigh_break+hist_turn_up+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+yhigh_break+hist_turn_up+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+hist_turn_up+above_vwap_v+cvd_up|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_vwap+hist_turn_up+above_vwap_v+cvd_up|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_vwap+hist_turn_up+above_vwap_v+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_vwap+hist_turn_up+above_vwap_v+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+delta_surge+hist_turn_up+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+delta_surge+hist_turn_up+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+cvd_up|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+cvd_up|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+hist_turn_up+above_vwap_v+cvd_up|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+hist_turn_up+above_vwap_v+cvd_up|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+hist_turn_up+above_vwap_v+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+hist_turn_up+above_vwap_v+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+cvd_up_v|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+cvd_up_v|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+cvd_up_v|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+cvd_up_v|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+cvd_up|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+cvd_up|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+hist_turn_up+rvol_thrust_up+cvd_up_v|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+hist_turn_up+above_vwap_v+cvd_up|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+hist_turn_up+above_vwap_v+cvd_up|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+hist_turn_up+above_vwap_v+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+hist_turn_up+above_vwap_v+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+hist_turn_up+cvd_up+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+hist_turn_up+cvd_up+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:yhigh_break+above_pivot+hist_turn_up+strong_close|nk0.0|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:yhigh_break+above_pivot+hist_turn_up+strong_close|nk0.5|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:yhigh_break+above_pivot+hist_turn_up+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:yhigh_break+above_pivot+hist_turn_up+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:yhigh_break+hist_turn_up+cvd_up+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:yhigh_break+hist_turn_up+cvd_up+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+macd_x_up+hist_turn_up+cvd_up|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+macd_x_up+hist_turn_up+cvd_up|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+macd_x_up+hist_turn_up+cvd_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v+cvd_up|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v+cvd_up|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v+cvd_up|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v+cvd_up|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v+cvd_up_v|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v+cvd_up_v|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_pivot+hist_turn_up+above_vwap_v+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:hist_turn_up+above_vwap_v+cvd_up+cvd_up_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:hist_turn_up+above_vwap_v+cvd_up+cvd_up_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_pivot+macd_x_dn_pos|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+cvd_dn_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+cvd_dn_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_pivot+macd_x_dn+macd_x_dn_pos|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:macd_x_dn_pos+weak_close+cvd_dn|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:macd_x_dn_pos+weak_close+cvd_dn|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+cvd_dn_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+cvd_dn_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+macd_x_dn_pos+weak_close+cvd_dn|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+macd_x_dn_pos+weak_close+cvd_dn|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+cvd_dn_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+cvd_dn_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:adi_dn+macd_x_dn_pos+weak_close+cvd_dn|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:adi_dn+macd_x_dn_pos+weak_close+cvd_dn|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+cvd_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+cvd_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+cvd_dn+cvd_dn_v|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+cvd_dn+cvd_dn_v|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:macd_x_dn+macd_x_dn_pos+weak_close+cvd_dn|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:macd_x_dn+macd_x_dn_pos+weak_close+cvd_dn|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 83.3% on 6 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 83.3% on 6 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 83.3% on 6 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 83.3% on 6 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 83.3% on 6 trades
  - `LONG:adi_up+hist_turn_up+strong_close+orb_break_up|nk0.0|vm1.2|full_0845_1400` — 81.8% on 11 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm0.8|full_0845_1400` — 80.0% on 15 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm1.2|full_0845_1400` — 80.0% on 15 trades
  - `LONG:above_vwap+above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm0.8|full_0845_1400` — 80.0% on 15 trades
  - `LONG:above_vwap+above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm1.2|full_0845_1400` — 80.0% on 15 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm0.8|full_0845_1400` — 80.0% on 15 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm1.2|full_0845_1400` — 80.0% on 15 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm0.8|full_0845_1400` — 80.0% on 15 trades
  - `LONG:delta_surge+above_pivot+hist_turn_up+rvol_thrust_up|nk0.0|vm1.2|full_0845_1400` — 80.0% on 15 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+rvol_thrust_up|nk0.0|vm0.8|full_0845_1400` — 80.0% on 15 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+rvol_thrust_up|nk0.0|vm1.2|full_0845_1400` — 80.0% on 15 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+above_vwap_v|nk0.0|vm0.8|full_0845_1400` — 80.0% on 15 trades
  - `LONG:above_pivot+hist_turn_up+strong_close+above_vwap_v|nk0.0|vm1.2|full_0845_1400` — 80.0% on 15 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|full_0845_1400` — 80.0% on 15 trades
  - `LONG:above_pivot+hist_turn_up+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|full_0845_1400` — 80.0% on 15 trades
  - `LONG:vwap_reclaim+hist_turn_up|nk0.0|vm0.8|pm_1130_1400` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+hist_turn_up|nk0.5|vm0.8|pm_1130_1400` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+hist_turn_up|nk0.0|vm0.8|pm_1130_1400` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+hist_turn_up|nk0.5|vm0.8|pm_1130_1400` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+hist_turn_up+strong_close|nk0.0|vm0.8|pm_1130_1400` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+hist_turn_up+strong_close|nk0.5|vm0.8|pm_1130_1400` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+hist_turn_up+strong_close|nk0.0|vm0.8|pm_1130_1400` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+hist_turn_up+strong_close|nk0.5|vm0.8|pm_1130_1400` — 80.0% on 10 trades
  - `LONG:adi_up+hist_turn_up+strong_close+orb_break_up|nk0.0|vm1.2|am_0845_1130` — 80.0% on 10 trades
  - `LONG:adi_up+hist_turn_up+strong_close+orb_break_up|nk0.5|vm1.2|full_0845_1400` — 80.0% on 10 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+orb_break_up|nk0.0|vm0.8|full_0845_1400` — 80.0% on 10 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+orb_break_up|nk0.0|vm1.2|full_0845_1400` — 80.0% on 10 trades
  - `LONG:hist_turn_up+strong_close+orb_break_up+cvd_up|nk0.0|vm1.2|full_0845_1400` — 80.0% on 10 trades
  - `LONG:above_vwap+macd_x_up+hist_turn_up+strong_close|nk0.0|vm1.2|full_0845_1400` — 77.8% on 9 trades
  - `LONG:above_vwap+macd_x_up+hist_turn_up+strong_close|nk0.5|vm1.2|full_0845_1400` — 77.8% on 9 trades
  - `LONG:above_vwap+macd_x_up+hist_turn_up+strong_close|nk0.8|vm1.2|full_0845_1400` — 77.8% on 9 trades
  - `LONG:adi_up+hist_turn_up+strong_close+orb_break_up|nk0.5|vm1.2|am_0845_1130` — 77.8% on 9 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+orb_break_up|nk0.0|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+orb_break_up|nk0.0|vm1.2|am_0845_1130` — 77.8% on 9 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+orb_break_up|nk0.5|vm0.8|full_0845_1400` — 77.8% on 9 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+orb_break_up|nk0.5|vm1.2|full_0845_1400` — 77.8% on 9 trades
  - `LONG:hist_turn_up+strong_close+orb_break_up+cvd_up|nk0.0|vm1.2|am_0845_1130` — 77.8% on 9 trades
  - `LONG:hist_turn_up+strong_close+orb_break_up+cvd_up|nk0.5|vm1.2|full_0845_1400` — 77.8% on 9 trades
  - `LONG:yhigh_break+hist_turn_up|nk0.0|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `LONG:yhigh_break+hist_turn_up|nk0.5|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `LONG:yhigh_break+above_pivot+hist_turn_up|nk0.0|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `LONG:yhigh_break+above_pivot+hist_turn_up|nk0.5|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `LONG:yhigh_break+hist_turn_up+strong_close|nk0.0|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `LONG:yhigh_break+hist_turn_up+strong_close|nk0.5|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `LONG:yhigh_break+hist_turn_up+cvd_up_v|nk0.0|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:yhigh_break+hist_turn_up+cvd_up_v|nk0.0|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:yhigh_break+hist_turn_up+cvd_up_v|nk0.5|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:yhigh_break+hist_turn_up+cvd_up_v|nk0.5|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+yhigh_break+hist_turn_up+cvd_up_v|nk0.0|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+yhigh_break+hist_turn_up+cvd_up_v|nk0.0|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+yhigh_break+hist_turn_up+cvd_up_v|nk0.5|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+yhigh_break+hist_turn_up+cvd_up_v|nk0.5|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+above_pivot+macd_x_up+hist_turn_up|nk0.0|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+above_pivot+macd_x_up+hist_turn_up|nk0.5|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+above_pivot+macd_x_up+hist_turn_up|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+hist_turn_up+strong_close+orb_break_up|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+orb_break_up|nk0.5|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:delta_surge+hist_turn_up+strong_close+orb_break_up|nk0.5|vm1.2|am_0845_1130` — 75.0% on 8 trades
  - `LONG:yhigh_break+above_pivot+hist_turn_up+strong_close|nk0.0|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `LONG:yhigh_break+above_pivot+hist_turn_up+strong_close|nk0.5|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `LONG:yhigh_break+above_pivot+hist_turn_up+cvd_up_v|nk0.0|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:yhigh_break+above_pivot+hist_turn_up+cvd_up_v|nk0.0|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:yhigh_break+above_pivot+hist_turn_up+cvd_up_v|nk0.5|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:yhigh_break+above_pivot+hist_turn_up+cvd_up_v|nk0.5|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:yhigh_break+hist_turn_up+cvd_up+cvd_up_v|nk0.0|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:yhigh_break+hist_turn_up+cvd_up+cvd_up_v|nk0.0|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:yhigh_break+hist_turn_up+cvd_up+cvd_up_v|nk0.5|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:yhigh_break+hist_turn_up+cvd_up+cvd_up_v|nk0.5|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_pivot+macd_x_up+hist_turn_up+strong_close|nk0.0|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_pivot+macd_x_up+hist_turn_up+strong_close|nk0.5|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_pivot+macd_x_up+hist_turn_up+strong_close|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:hist_turn_up+strong_close+orb_break_up+cvd_up|nk0.5|vm1.2|am_0845_1130` — 75.0% on 8 trades
  - `LONG:hist_turn_up+strong_close+orb_break_up+cvd_up|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:adi_dn+orb_break_dn|nk0.0|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:adi_dn+orb_break_dn|nk0.5|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn|nk0.0|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn|nk0.5|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:adi_dn+hist_turn_dn+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:adi_dn+hist_turn_dn+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn|nk0.0|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn|nk0.5|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:below_vwap+adi_dn+weak_close+orb_break_dn|nk0.0|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:below_vwap+adi_dn+weak_close+orb_break_dn|nk0.5|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:adi_dn+hist_turn_dn+weak_close+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:adi_dn+hist_turn_dn+weak_close+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 75.0% on 8 trades
  - `LONG:macd_x_up+hist_turn_up+strong_close+cvd_up|nk0.0|vm0.8|full_0845_1400` — 72.7% on 11 trades
  - `LONG:macd_x_up+hist_turn_up+strong_close+cvd_up|nk0.5|vm0.8|full_0845_1400` — 72.7% on 11 trades
  - `LONG:macd_x_up+hist_turn_up+strong_close+cvd_up|nk0.8|vm0.8|full_0845_1400` — 72.7% on 11 trades
  - `SHORT:hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 71.4% on 7 trades
  - `SHORT:hist_turn_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 71.4% on 7 trades


## FINAL VERDICT — A-BOOK PRECISION UNION (AAPL, +/-0.30% in 4h, entry >=08:45, TP by 14:35 CST, 60 sessions)

Goal (max A-book signals/day at near-perfect precision) — precision frontier reached: **0.53/day** is the max the >95% bar allows here.

| metric | value |
|--------|-------|
| resolved trades | 32 (30 target / 0 stop / 2 scratch) |
| **TP-before-SL** | **100.0%** (0 stops) |
| strict win-rate | 93.8% |
| **frequency** | **0.53/day** (24/60 sessions) |
| net | +9.3% |

### A-book families (live `A_BOOK` in aapl_intraday_bot.py)

| # | direction | signal (blocks) | window | gate | trades | TP-b-SL | strict |
|---|-----------|-----------------|--------|------|--------|---------|--------|
| 1 | LONG | `above_pivot+hist_turn_up+rvol_thrust_up` | am_0845_1130 | 0.0/0.8 | 8 | 100% | 100% |
| 2 | LONG | `yhigh_break+hist_turn_up+strong_close` | pm_1130_1400 | 0.0/0.8 | 7 | 100% | 86% |
| 3 | SHORT | `hist_turn_dn+cvd_dn+rsi_thrust_dn` | full_0845_1400 | 0.8/0.8 | 6 | 100% | 83% |
| 4 | LONG | `macd_x_up+hist_turn_up+strong_close+cvd_up` | full_0845_1400 | 0.0/1.2 | 7 | 100% | 100% |
| 5 | LONG | `vwap_reclaim+rvol_thrust_up` | am_0845_1130 | 0.0/0.8 | 6 | 100% | 100% |
| 6 | LONG | `yhigh_break+hist_turn_up` | mid_1030_1300 | 0.8/0.8 | 6 | 100% | 100% |

**Read this before trading.** In-sample results on one ~3-month regime (~59 sessions). A-book families were selected because they rarely/never stopped in-sample — treat the TP-before-SL figure as an upper bound; the residual risk is the SCRATCH rate (time-stops at the 4h/14:35 deadline). Forward-validate before sizing. Desk session rule enforced in the engine: signals only after 08:45 CST, TP truncated at 14:35 CST.
