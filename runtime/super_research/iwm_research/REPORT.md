# IWM 5m Super-Signal research — 2026-07-15 14:28 CST

_60 sessions of 5-minute IWM (yfinance, incl. pre-market) · entries ['full_0845_1400', 'am_0845_1130', 'mid_1030_1300', 'pm_1130_1400'] (CST) · entry = next bar open · TP 0.3% ≤ 48 bars · SL 0.3% ≤ 48 bars · time-stop at bar 48 close · same-bar TP+SL = stop (conservative)._
_win_rate counts time-stop scratches as non-wins (strict); tp_before_sl ignores scratches._
_GEX/options-flow: no free historical feed — neutral hook only (see signals.GEX_NOTE)._

## Best configs with ≥2 signal/day (strict win-rate)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHORT | below_pivot+cvd_dn | 0.5 | 0.8 | mid_1030_1300 | 171 | 2.85 | 99 | 55 | 17 | 57.9 | 64.3 | 1.8 | 13.5 | 3.31 | 51.1 |
| SHORT | below_vwap+below_pivot+cvd_dn | 0.5 | 0.8 | mid_1030_1300 | 171 | 2.85 | 99 | 55 | 17 | 57.9 | 64.3 | 1.8 | 13.5 | 3.31 | 51.1 |
| SHORT | adi_dn+below_pivot+weak_close | 0.5 | 0.8 | mid_1030_1300 | 147 | 2.45 | 84 | 51 | 12 | 57.1 | 62.2 | 1.62 | 9.8 | 3.62 | 54.7 |
| SHORT | below_pivot+cvd_dn | 0.0 | 0.8 | mid_1030_1300 | 176 | 2.93 | 100 | 58 | 18 | 56.8 | 63.3 | 1.73 | 13.07 | 3.31 | 51.6 |
| SHORT | below_vwap+below_pivot+cvd_dn | 0.0 | 0.8 | mid_1030_1300 | 176 | 2.93 | 100 | 58 | 18 | 56.8 | 63.3 | 1.73 | 13.07 | 3.31 | 51.6 |
| SHORT | adi_dn+below_pivot+weak_close | 0.0 | 0.8 | mid_1030_1300 | 150 | 2.5 | 85 | 51 | 14 | 56.7 | 62.5 | 1.66 | 10.36 | 3.62 | 55.4 |
| SHORT | adi_dn+below_pivot+cvd_dn | 0.5 | 0.8 | mid_1030_1300 | 145 | 2.42 | 81 | 52 | 12 | 55.9 | 60.9 | 1.55 | 8.79 | 3.5 | 48.4 |
| SHORT | adi_dn+below_pivot | 0.5 | 0.8 | mid_1030_1300 | 233 | 3.88 | 127 | 86 | 20 | 54.5 | 59.6 | 1.48 | 12.69 | 4.82 | 54.7 |
| SHORT | below_vwap+adi_dn+below_pivot | 0.8 | 0.8 | mid_1030_1300 | 132 | 2.2 | 72 | 52 | 8 | 54.5 | 58.1 | 1.38 | 6.05 | 3.85 | 46.3 |
| SHORT | adi_dn+below_pivot+cvd_dn | 0.0 | 0.8 | mid_1030_1300 | 149 | 2.48 | 81 | 55 | 13 | 54.4 | 59.6 | 1.48 | 8.06 | 3.34 | 49.0 |
| SHORT | hist_turn_dn+weak_close | 0.0 | 0.8 | am_0845_1130 | 129 | 2.15 | 70 | 56 | 3 | 54.3 | 55.6 | 1.26 | 4.33 | 3.3 | 47.8 |
| SHORT | hist_turn_dn+weak_close | 0.5 | 0.8 | am_0845_1130 | 129 | 2.15 | 70 | 56 | 3 | 54.3 | 55.6 | 1.26 | 4.33 | 3.3 | 47.8 |
| SHORT | below_pivot+weak_close+cvd_dn | 0.0 | 0.8 | am_0845_1130 | 157 | 2.62 | 85 | 66 | 6 | 54.1 | 56.3 | 1.27 | 5.46 | 3.62 | 39.8 |
| SHORT | below_pivot+weak_close+cvd_dn | 0.5 | 0.8 | am_0845_1130 | 157 | 2.62 | 85 | 66 | 6 | 54.1 | 56.3 | 1.27 | 5.46 | 3.62 | 39.8 |
| SHORT | below_vwap+adi_dn+below_pivot | 0.5 | 0.8 | mid_1030_1300 | 191 | 3.18 | 103 | 72 | 16 | 53.9 | 58.9 | 1.42 | 9.23 | 5.3 | 52.2 |

## Highest strict win-rate overall (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHORT | vwap_loss+below_pivot+hist_turn_dn | 0.0 | 1.2 | full_0845_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 17.0 |
| SHORT | vwap_loss+below_pivot+hist_turn_dn | 0.5 | 1.2 | full_0845_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 17.0 |
| SHORT | vwap_loss+below_pivot+weak_close | 0.0 | 1.2 | am_0845_1130 | 12 | 0.2 | 10 | 2 | 0 | 83.3 | 83.3 | 5.0 | 2.4 | 0.6 | 27.5 |
| SHORT | vwap_loss+below_pivot+weak_close | 0.5 | 1.2 | am_0845_1130 | 12 | 0.2 | 10 | 2 | 0 | 83.3 | 83.3 | 5.0 | 2.4 | 0.6 | 27.5 |
| SHORT | vwap_loss+below_pivot+weak_close | 0.8 | 1.2 | am_0845_1130 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 28.2 |
| SHORT | below_pivot+macd_x_dn | 0.0 | 0.8 | am_0845_1130 | 10 | 0.17 | 8 | 2 | 0 | 80.0 | 80.0 | 4.0 | 1.8 | 0.3 | 36.0 |
| SHORT | adi_dn+below_pivot+macd_x_dn | 0.0 | 0.8 | am_0845_1130 | 10 | 0.17 | 8 | 2 | 0 | 80.0 | 80.0 | 4.0 | 1.8 | 0.3 | 36.0 |
| SHORT | below_pivot+macd_x_dn | 0.5 | 0.8 | am_0845_1130 | 10 | 0.17 | 8 | 2 | 0 | 80.0 | 80.0 | 4.0 | 1.8 | 0.3 | 36.0 |
| SHORT | adi_dn+below_pivot+macd_x_dn | 0.5 | 0.8 | am_0845_1130 | 10 | 0.17 | 8 | 2 | 0 | 80.0 | 80.0 | 4.0 | 1.8 | 0.3 | 36.0 |
| SHORT | vwap_loss+below_pivot | 0.0 | 1.2 | am_0845_1130 | 14 | 0.23 | 11 | 3 | 0 | 78.6 | 78.6 | 3.67 | 2.4 | 0.9 | 27.9 |
| SHORT | vwap_loss+below_vwap+below_pivot | 0.0 | 1.2 | am_0845_1130 | 14 | 0.23 | 11 | 3 | 0 | 78.6 | 78.6 | 3.67 | 2.4 | 0.9 | 27.9 |
| SHORT | vwap_loss+below_pivot | 0.5 | 1.2 | am_0845_1130 | 14 | 0.23 | 11 | 3 | 0 | 78.6 | 78.6 | 3.67 | 2.4 | 0.9 | 27.9 |
| SHORT | vwap_loss+below_vwap+below_pivot | 0.5 | 1.2 | am_0845_1130 | 14 | 0.23 | 11 | 3 | 0 | 78.6 | 78.6 | 3.67 | 2.4 | 0.9 | 27.9 |
| SHORT | vwap_loss+below_pivot+hist_turn_dn | 0.8 | 0.8 | full_0845_1400 | 14 | 0.23 | 11 | 3 | 0 | 78.6 | 78.6 | 3.67 | 2.4 | 0.3 | 24.3 |
| LONG | poc_reject_up+delta_surge+above_pivot | 0.8 | 0.8 | full_0845_1400 | 13 | 0.22 | 10 | 3 | 0 | 76.9 | 76.9 | 3.33 | 2.1 | 0.3 | 28.5 |

## Highest TP-before-SL rate (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHORT | vwap_loss+below_pivot+hist_turn_dn | 0.0 | 1.2 | full_0845_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 17.0 |
| SHORT | vwap_loss+below_pivot+hist_turn_dn | 0.5 | 1.2 | full_0845_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 17.0 |
| SHORT | vwap_loss+below_pivot+cvd_dn | 0.8 | 0.8 | full_0845_1400 | 20 | 0.33 | 14 | 2 | 4 | 70.0 | 87.5 | 3.73 | 3.07 | 0.3 | 39.0 |
| LONG | above_vwap_v+mom_ignite_up | 0.0 | 0.8 | pm_1130_1400 | 14 | 0.23 | 7 | 1 | 6 | 50.0 | 87.5 | 4.79 | 1.91 | 0.3 | 73.9 |
| LONG | above_vwap+above_vwap_v+mom_ignite_up | 0.0 | 0.8 | pm_1130_1400 | 14 | 0.23 | 7 | 1 | 6 | 50.0 | 87.5 | 4.79 | 1.91 | 0.3 | 73.9 |
| LONG | above_vwap_v+cvd_up+mom_ignite_up | 0.0 | 0.8 | pm_1130_1400 | 14 | 0.23 | 7 | 1 | 6 | 50.0 | 87.5 | 4.79 | 1.91 | 0.3 | 73.9 |
| LONG | above_vwap_v+cvd_up_v+mom_ignite_up | 0.0 | 0.8 | pm_1130_1400 | 14 | 0.23 | 7 | 1 | 6 | 50.0 | 87.5 | 4.79 | 1.91 | 0.3 | 73.9 |
| LONG | above_vwap_v+mom_ignite_up | 0.0 | 1.2 | pm_1130_1400 | 14 | 0.23 | 7 | 1 | 6 | 50.0 | 87.5 | 4.79 | 1.91 | 0.3 | 73.9 |
| LONG | above_vwap+above_vwap_v+mom_ignite_up | 0.0 | 1.2 | pm_1130_1400 | 14 | 0.23 | 7 | 1 | 6 | 50.0 | 87.5 | 4.79 | 1.91 | 0.3 | 73.9 |
| LONG | above_vwap_v+cvd_up+mom_ignite_up | 0.0 | 1.2 | pm_1130_1400 | 14 | 0.23 | 7 | 1 | 6 | 50.0 | 87.5 | 4.79 | 1.91 | 0.3 | 73.9 |
| LONG | above_vwap_v+cvd_up_v+mom_ignite_up | 0.0 | 1.2 | pm_1130_1400 | 14 | 0.23 | 7 | 1 | 6 | 50.0 | 87.5 | 4.79 | 1.91 | 0.3 | 73.9 |
| SHORT | vwap_loss+below_pivot | 0.0 | 0.8 | pm_1130_1400 | 12 | 0.2 | 7 | 1 | 4 | 58.3 | 87.5 | 2.54 | 1.27 | 0.59 | 44.2 |
| SHORT | vwap_loss+below_vwap+below_pivot | 0.0 | 0.8 | pm_1130_1400 | 12 | 0.2 | 7 | 1 | 4 | 58.3 | 87.5 | 2.54 | 1.27 | 0.59 | 44.2 |
| SHORT | vwap_loss+adi_dn+below_pivot | 0.0 | 0.8 | pm_1130_1400 | 12 | 0.2 | 7 | 1 | 4 | 58.3 | 87.5 | 2.54 | 1.27 | 0.59 | 44.2 |
| SHORT | vwap_loss+below_pivot+cvd_dn | 0.0 | 0.8 | pm_1130_1400 | 12 | 0.2 | 7 | 1 | 4 | 58.3 | 87.5 | 2.54 | 1.27 | 0.59 | 44.2 |


## ITERATION 2 — greedy precision ensemble (2026-07-15 14:35 CST)

_128 composites unioned (each ≥70% strict / ≥85% tp-before-sl on its own); book constrained to ≥75% strict win-rate._

- **trades:** 72 (1.2/day, 40/60 days covered)
- **strict win-rate:** 76.4%  ·  **tp-before-sl:** 85.9%
- **profit factor:** 5.1  ·  **net:** 13.65%  ·  **maxDD:** 0.6%
- **avg hold:** 45.1 min

Configs (see results/ensemble.csv):

  - `SHORT:vwap_loss+below_pivot+hist_turn_dn|nk0.0|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn|nk0.5|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:vwap_loss+below_vwap+below_pivot+hist_turn_dn|nk0.0|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:vwap_loss+below_vwap+below_pivot+hist_turn_dn|nk0.5|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:vwap_loss+below_pivot+weak_close+cvd_dn|nk0.0|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:vwap_loss+below_pivot+weak_close+cvd_dn|nk0.5|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:vwap_loss+below_pivot+weak_close+cvd_dn|nk0.8|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:vwap_loss+below_vwap+below_pivot+hist_turn_dn|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn+weak_close|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn+weak_close|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn+cvd_dn|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn+cvd_dn|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn+cvd_dn|nk0.8|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:vwap_loss+below_pivot+weak_close+cvd_dn|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn+cvd_dn|nk0.8|vm0.8|full_0845_1400` — 90.9% on 11 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn|nk0.0|vm1.2|full_0845_1400` — 90.0% on 10 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn|nk0.5|vm1.2|full_0845_1400` — 90.0% on 10 trades
  - `SHORT:vwap_loss+below_vwap+below_pivot+hist_turn_dn|nk0.0|vm1.2|full_0845_1400` — 90.0% on 10 trades
  - `SHORT:vwap_loss+below_vwap+below_pivot+hist_turn_dn|nk0.5|vm1.2|full_0845_1400` — 90.0% on 10 trades
  - `SHORT:vwap_loss+adi_dn+below_pivot+hist_turn_dn|nk0.8|vm0.8|full_0845_1400` — 90.0% on 10 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn|nk0.8|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:vwap_loss+below_pivot+cvd_dn|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `SHORT:vwap_loss+below_pivot+cvd_dn|nk0.5|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `SHORT:vwap_loss+below_pivot+cvd_dn|nk0.8|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `SHORT:vwap_loss+below_vwap+below_pivot+hist_turn_dn|nk0.8|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:vwap_loss+below_vwap+below_pivot+cvd_dn|nk0.0|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `SHORT:vwap_loss+below_vwap+below_pivot+cvd_dn|nk0.5|vm1.2|am_0845_1130` — 88.9% on 9 trades
  - `SHORT:vwap_loss+below_vwap+below_pivot+cvd_dn|nk0.8|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn+weak_close|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn+weak_close|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn+cvd_dn|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn+cvd_dn|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+r1_reject|nk0.0|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+r1_reject|nk0.5|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+r1_reject|nk0.8|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_pivot+macd_x_dn|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:vwap_loss+below_pivot+cvd_dn|nk0.8|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:vwap_loss+below_vwap+below_pivot+cvd_dn|nk0.8|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:vwap_loss+adi_dn+below_pivot+hist_turn_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:vwap_loss+adi_dn+below_pivot+hist_turn_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:vwap_loss+adi_dn+below_pivot+weak_close|nk0.0|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:vwap_loss+adi_dn+below_pivot+weak_close|nk0.5|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn+weak_close|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn+cvd_dn|nk0.0|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn+cvd_dn|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:vwap_loss+below_pivot+hist_turn_dn+cvd_dn|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+macd_x_up_neg|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_pivot+macd_x_up+macd_x_up_neg|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_pivot+macd_x_up_neg+strong_close|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_pivot+macd_x_up_neg+strong_close|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_pivot+macd_x_up+macd_x_up_neg+strong_close|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:above_pivot+macd_x_up+macd_x_up_neg+strong_close|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+yhigh_reject|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+yhigh_reject|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot|nk0.0|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+below_vwap+delta_dump+below_pivot|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+below_vwap+delta_dump+below_pivot|nk0.0|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+below_vwap+delta_dump+below_pivot|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+below_vwap+delta_dump+below_pivot|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+adi_dn+delta_dump+below_pivot|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+adi_dn+delta_dump+below_pivot|nk0.0|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+adi_dn+delta_dump+below_pivot|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+adi_dn+delta_dump+below_pivot|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+adi_dn+below_pivot+hist_turn_dn|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+adi_dn+below_pivot+hist_turn_dn|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+adi_dn+below_pivot+hist_turn_dn|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:vwap_loss+adi_dn+below_pivot+weak_close|nk0.8|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+adi_dn+below_pivot+cvd_dn|nk0.0|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+adi_dn+below_pivot+cvd_dn|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+adi_dn+below_pivot+cvd_dn|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot+hist_turn_dn|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot+hist_turn_dn|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot+hist_turn_dn|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot+hist_turn_dn|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot+weak_close|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot+weak_close|nk0.0|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot+weak_close|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot+weak_close|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+below_pivot+macd_x_dn|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn+cvd_dn|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+cvd_dn|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+above_pivot+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:delta_surge+above_pivot+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+above_pivot+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+delta_surge+above_pivot+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 83.3% on 6 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+vwap_lo_bounce|nk0.0|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+vwap_lo_bounce|nk0.5|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:adi_up+above_pivot+hist_turn_up+vwap_lo_bounce|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:vwap_loss+below_pivot+weak_close+cvd_dn|nk0.0|vm1.2|full_0845_1400` — 76.9% on 13 trades
  - `SHORT:vwap_loss+below_pivot+weak_close+cvd_dn|nk0.5|vm1.2|full_0845_1400` — 76.9% on 13 trades
  - `SHORT:vwap_loss+below_pivot+weak_close+cvd_dn|nk0.8|vm1.2|full_0845_1400` — 75.0% on 12 trades
  - `LONG:above_pivot+macd_x_up_neg|nk0.8|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:delta_surge+above_pivot+vwap_lo_bounce|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:delta_surge+above_pivot+vwap_lo_bounce|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_pivot+macd_x_up+macd_x_up_neg|nk0.8|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:adi_up+delta_surge+above_pivot+vwap_lo_bounce|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+delta_surge+above_pivot+vwap_lo_bounce|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:vwap_loss+adi_dn+hist_turn_dn|nk0.0|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:vwap_loss+adi_dn+hist_turn_dn|nk0.5|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:vwap_loss+adi_dn+hist_turn_dn|nk0.8|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:vwap_loss+below_vwap+adi_dn+hist_turn_dn|nk0.0|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:vwap_loss+below_vwap+adi_dn+hist_turn_dn|nk0.5|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:vwap_loss+below_vwap+adi_dn+hist_turn_dn|nk0.8|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:vwap_loss+adi_dn+hist_turn_dn+cvd_dn|nk0.0|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:vwap_loss+adi_dn+hist_turn_dn+cvd_dn|nk0.5|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:vwap_loss+adi_dn+hist_turn_dn+cvd_dn|nk0.8|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:vwap_loss+hist_turn_dn+weak_close+cvd_dn|nk0.0|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:vwap_loss+hist_turn_dn+weak_close+cvd_dn|nk0.5|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `SHORT:vwap_loss+hist_turn_dn+weak_close+cvd_dn|nk0.8|vm0.8|pm_1130_1400` — 75.0% on 8 trades
  - `LONG:above_pivot+above_vwap_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_pivot+above_vwap_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+above_pivot+above_vwap_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_vwap+above_pivot+above_vwap_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_pivot+above_vwap_v+cvd_up+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_pivot+above_vwap_v+cvd_up+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_pivot+above_vwap_v+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 71.4% on 7 trades
  - `LONG:above_pivot+above_vwap_v+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 71.4% on 7 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot+cvd_dn|nk0.0|vm0.8|full_0845_1400` — 70.0% on 10 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot+cvd_dn|nk0.0|vm1.2|full_0845_1400` — 70.0% on 10 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot+cvd_dn|nk0.5|vm0.8|full_0845_1400` — 70.0% on 10 trades
  - `SHORT:vwap_loss+delta_dump+below_pivot+cvd_dn|nk0.5|vm1.2|full_0845_1400` — 70.0% on 10 trades


## FINAL VERDICT — A-BOOK PRECISION UNION (IWM, +/-0.30% in 4h, entry >=08:45, TP by 14:35 CST, 60 sessions)

Goal (max A-book signals/day at near-perfect precision) — precision frontier reached: **0.7/day** is the max the >95% bar allows here.

| metric | value |
|--------|-------|
| resolved trades | 42 (35 target / 0 stop / 7 scratch) |
| **TP-before-SL** | **100.0%** (0 stops) |
| strict win-rate | 83.3% |
| **frequency** | **0.7/day** (30/60 sessions) |
| net | +10.8% |

### A-book families (live `A_BOOK` in iwm_intraday_bot.py)

| # | direction | signal (blocks) | window | gate | trades | TP-b-SL | strict |
|---|-----------|-----------------|--------|------|--------|---------|--------|
| 1 | LONG | `above_vwap+above_pivot+macd_x_up_neg+strong_close` | full_0845_1400 | 0.0/0.8 | 8 | 100% | 62% |
| 2 | SHORT | `vwap_loss+below_pivot+hist_turn_dn` | am_0845_1130 | 0.0/1.2 | 7 | 100% | 100% |
| 3 | LONG | `above_pivot+above_vwap_v+rsi_thrust_up` | mid_1030_1300 | 0.8/0.8 | 7 | 100% | 71% |
| 4 | LONG | `adi_up+above_pivot+hist_turn_up+vwap_lo_bounce` | full_0845_1400 | 0.0/0.8 | 6 | 100% | 83% |
| 5 | SHORT | `below_vwap+r1_reject+weak_close` | mid_1030_1300 | 0.0/0.8 | 5 | 100% | 100% |
| 6 | LONG | `above_pivot+macd_x_up_neg+strong_close` | am_0845_1130 | 0.0/0.8 | 7 | 100% | 86% |
| 7 | LONG | `vwap_reclaim+vwap_lo_bounce` | full_0845_1400 | 0.0/0.8 | 5 | 100% | 100% |
| 8 | SHORT | `vwap_loss+below_pivot+weak_close+cvd_dn` | am_0845_1130 | 0.0/1.2 | 7 | 100% | 100% |
| 9 | LONG | `delta_surge+above_pivot+rsi_thrust_up` | mid_1030_1300 | 0.8/0.8 | 6 | 100% | 83% |

**Read this before trading.** In-sample results on one ~3-month regime (~59 sessions). A-book families were selected because they rarely/never stopped in-sample — treat the TP-before-SL figure as an upper bound; the residual risk is the SCRATCH rate (time-stops at the 4h/14:35 deadline). Forward-validate before sizing. Desk session rule enforced in the engine: signals only after 08:45 CST, TP truncated at 14:35 CST.
