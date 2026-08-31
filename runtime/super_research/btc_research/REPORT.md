# BTC 5m Super-Signal research (24×7) — 2026-07-25 19:35 CST

_60 sessions of 5-minute BTC (yfinance, 24×7) · entries ['full_day', 'asia_0_8', 'us_8_16', 'eve_16_24'] (CST) · entry = next bar open · TP 80.0 pt ≤ 12 bars · SL 50.0 pt ≤ 12 bars · time-stop at bar 12 close · same-bar TP+SL = stop (conservative)._
_win_rate counts time-stop scratches as non-wins (strict); tp_before_sl ignores scratches._
_GEX/options-flow: no free historical feed — neutral hook only (see signals.GEX_NOTE)._

## Best configs with ≥1 signal/day (strict win-rate)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_points | max_drawdown_pts | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | macd_x_up+hist_turn_up | 0.9 | 1.2 | full_day | 61 | 1.02 | 31 | 30 | 0 | 50.8 | 50.8 | 1.65 | 980.0 | 370.0 | 11.9 |
| LONG | macd_x_up+hist_turn_up | 0.9 | 0.8 | full_day | 62 | 1.03 | 31 | 31 | 0 | 50.0 | 50.0 | 1.6 | 930.0 | 370.0 | 11.8 |
| LONG | above_pivot+bull_div | 0.6 | 0.8 | full_day | 92 | 1.53 | 45 | 45 | 2 | 48.9 | 50.0 | 1.63 | 1409.19 | 640.0 | 12.6 |
| LONG | above_pivot+bull_div | 0.6 | 1.2 | full_day | 92 | 1.53 | 45 | 45 | 2 | 48.9 | 50.0 | 1.63 | 1409.19 | 640.0 | 12.6 |
| LONG | vwap_reclaim+hist_turn_up | 1.2 | 1.2 | full_day | 72 | 1.2 | 35 | 34 | 3 | 48.6 | 50.7 | 1.67 | 1144.4 | 320.0 | 15.0 |
| LONG | vwap_reclaim+above_vwap+hist_turn_up | 1.2 | 1.2 | full_day | 72 | 1.2 | 35 | 34 | 3 | 48.6 | 50.7 | 1.67 | 1144.4 | 320.0 | 15.0 |
| LONG | vwap_reclaim+above_vwap | 0.9 | 0.8 | eve_16_24 | 66 | 1.1 | 32 | 33 | 1 | 48.5 | 49.2 | 1.56 | 927.81 | 282.19 | 12.0 |
| LONG | above_vwap+macd_x_up_neg | 0.9 | 1.2 | full_day | 65 | 1.08 | 31 | 33 | 1 | 47.7 | 48.4 | 1.54 | 882.84 | 310.0 | 11.4 |
| LONG | above_vwap+macd_x_up+macd_x_up_neg | 0.9 | 1.2 | full_day | 65 | 1.08 | 31 | 33 | 1 | 47.7 | 48.4 | 1.54 | 882.84 | 310.0 | 11.4 |
| LONG | vwap_reclaim+above_vwap | 0.6 | 0.8 | eve_16_24 | 82 | 1.37 | 39 | 41 | 2 | 47.6 | 48.8 | 1.53 | 1087.49 | 320.32 | 12.1 |
| LONG | vwap_reclaim+above_vwap | 0.9 | 1.2 | eve_16_24 | 63 | 1.05 | 30 | 32 | 1 | 47.6 | 48.4 | 1.51 | 817.81 | 232.19 | 12.2 |
| SHORT | poc_reject_dn+adi_dn+below_pivot | 0.6 | 1.2 | full_day | 63 | 1.05 | 30 | 33 | 0 | 47.6 | 47.6 | 1.45 | 750.0 | 270.0 | 9.9 |
| SHORT | macd_x_dn+macd_x_dn_pos | 0.9 | 1.2 | asia_0_8 | 61 | 1.02 | 29 | 28 | 4 | 47.5 | 50.9 | 1.61 | 879.75 | 220.0 | 15.6 |
| LONG | above_vwap+macd_x_up_neg | 0.9 | 0.8 | full_day | 66 | 1.1 | 31 | 34 | 1 | 47.0 | 47.7 | 1.49 | 832.84 | 310.0 | 11.4 |
| LONG | above_vwap+macd_x_up+macd_x_up_neg | 0.9 | 0.8 | full_day | 66 | 1.1 | 31 | 34 | 1 | 47.0 | 47.7 | 1.49 | 832.84 | 310.0 | 11.4 |

## Highest strict win-rate overall (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_points | max_drawdown_pts | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | macd_x_up_neg+hist_turn_up | 0.9 | 0.8 | eve_16_24 | 10 | 0.17 | 8 | 2 | 0 | 80.0 | 80.0 | 6.4 | 540.0 | 50.0 | 10.0 |
| LONG | macd_x_up+macd_x_up_neg+hist_turn_up | 0.9 | 0.8 | eve_16_24 | 10 | 0.17 | 8 | 2 | 0 | 80.0 | 80.0 | 6.4 | 540.0 | 50.0 | 10.0 |
| LONG | macd_x_up_neg+hist_turn_up | 0.9 | 1.2 | eve_16_24 | 10 | 0.17 | 8 | 2 | 0 | 80.0 | 80.0 | 6.4 | 540.0 | 50.0 | 10.0 |
| LONG | macd_x_up+macd_x_up_neg+hist_turn_up | 0.9 | 1.2 | eve_16_24 | 10 | 0.17 | 8 | 2 | 0 | 80.0 | 80.0 | 6.4 | 540.0 | 50.0 | 10.0 |
| LONG | above_vwap+above_pivot+macd_x_up_neg | 0.9 | 1.2 | asia_0_8 | 11 | 0.18 | 8 | 3 | 0 | 72.7 | 72.7 | 4.27 | 490.0 | 50.0 | 18.2 |
| LONG | above_vwap+macd_x_up_neg | 1.2 | 1.2 | asia_0_8 | 11 | 0.18 | 8 | 3 | 0 | 72.7 | 72.7 | 4.27 | 490.0 | 100.0 | 11.4 |
| LONG | above_vwap+macd_x_up+macd_x_up_neg | 1.2 | 1.2 | asia_0_8 | 11 | 0.18 | 8 | 3 | 0 | 72.7 | 72.7 | 4.27 | 490.0 | 100.0 | 11.4 |
| SHORT | macd_x_dn_pos+hist_turn_dn | 0.6 | 0.8 | asia_0_8 | 11 | 0.18 | 8 | 3 | 0 | 72.7 | 72.7 | 4.27 | 490.0 | 150.0 | 13.6 |
| SHORT | macd_x_dn+macd_x_dn_pos+hist_turn_dn | 0.6 | 0.8 | asia_0_8 | 11 | 0.18 | 8 | 3 | 0 | 72.7 | 72.7 | 4.27 | 490.0 | 150.0 | 13.6 |
| SHORT | macd_x_dn_pos+hist_turn_dn | 0.6 | 1.2 | asia_0_8 | 11 | 0.18 | 8 | 3 | 0 | 72.7 | 72.7 | 4.27 | 490.0 | 150.0 | 13.6 |
| SHORT | macd_x_dn+macd_x_dn_pos+hist_turn_dn | 0.6 | 1.2 | asia_0_8 | 11 | 0.18 | 8 | 3 | 0 | 72.7 | 72.7 | 4.27 | 490.0 | 150.0 | 13.6 |
| LONG | above_vwap+macd_x_up_neg+hist_turn_up | 0.6 | 0.8 | full_day | 10 | 0.17 | 7 | 3 | 0 | 70.0 | 70.0 | 3.73 | 410.0 | 50.0 | 9.5 |
| LONG | vwap_reclaim+above_pivot+macd_x_up_neg | 0.6 | 0.8 | asia_0_8 | 10 | 0.17 | 7 | 3 | 0 | 70.0 | 70.0 | 3.73 | 410.0 | 100.0 | 15.0 |
| LONG | above_vwap+macd_x_up_neg+hist_turn_up | 0.6 | 1.2 | full_day | 10 | 0.17 | 7 | 3 | 0 | 70.0 | 70.0 | 3.73 | 410.0 | 50.0 | 9.5 |
| LONG | above_vwap+macd_x_up_neg+hist_turn_up | 0.9 | 0.8 | full_day | 10 | 0.17 | 7 | 3 | 0 | 70.0 | 70.0 | 3.73 | 410.0 | 50.0 | 9.5 |

## Highest TP-before-SL rate (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_points | max_drawdown_pts | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | macd_x_up_neg+hist_turn_up | 0.9 | 0.8 | eve_16_24 | 10 | 0.17 | 8 | 2 | 0 | 80.0 | 80.0 | 6.4 | 540.0 | 50.0 | 10.0 |
| LONG | macd_x_up+macd_x_up_neg+hist_turn_up | 0.9 | 0.8 | eve_16_24 | 10 | 0.17 | 8 | 2 | 0 | 80.0 | 80.0 | 6.4 | 540.0 | 50.0 | 10.0 |
| LONG | macd_x_up_neg+hist_turn_up | 0.9 | 1.2 | eve_16_24 | 10 | 0.17 | 8 | 2 | 0 | 80.0 | 80.0 | 6.4 | 540.0 | 50.0 | 10.0 |
| LONG | macd_x_up+macd_x_up_neg+hist_turn_up | 0.9 | 1.2 | eve_16_24 | 10 | 0.17 | 8 | 2 | 0 | 80.0 | 80.0 | 6.4 | 540.0 | 50.0 | 10.0 |
| LONG | above_vwap+above_pivot+macd_x_up_neg | 0.9 | 1.2 | asia_0_8 | 11 | 0.18 | 8 | 3 | 0 | 72.7 | 72.7 | 4.27 | 490.0 | 50.0 | 18.2 |
| LONG | above_vwap+macd_x_up_neg | 1.2 | 1.2 | asia_0_8 | 11 | 0.18 | 8 | 3 | 0 | 72.7 | 72.7 | 4.27 | 490.0 | 100.0 | 11.4 |
| LONG | above_vwap+macd_x_up+macd_x_up_neg | 1.2 | 1.2 | asia_0_8 | 11 | 0.18 | 8 | 3 | 0 | 72.7 | 72.7 | 4.27 | 490.0 | 100.0 | 11.4 |
| SHORT | macd_x_dn_pos+hist_turn_dn | 0.6 | 0.8 | asia_0_8 | 11 | 0.18 | 8 | 3 | 0 | 72.7 | 72.7 | 4.27 | 490.0 | 150.0 | 13.6 |
| SHORT | macd_x_dn+macd_x_dn_pos+hist_turn_dn | 0.6 | 0.8 | asia_0_8 | 11 | 0.18 | 8 | 3 | 0 | 72.7 | 72.7 | 4.27 | 490.0 | 150.0 | 13.6 |
| SHORT | macd_x_dn_pos+hist_turn_dn | 0.6 | 1.2 | asia_0_8 | 11 | 0.18 | 8 | 3 | 0 | 72.7 | 72.7 | 4.27 | 490.0 | 150.0 | 13.6 |
| SHORT | macd_x_dn+macd_x_dn_pos+hist_turn_dn | 0.6 | 1.2 | asia_0_8 | 11 | 0.18 | 8 | 3 | 0 | 72.7 | 72.7 | 4.27 | 490.0 | 150.0 | 13.6 |
| LONG | above_vwap+macd_x_up_neg+hist_turn_up | 0.6 | 0.8 | full_day | 10 | 0.17 | 7 | 3 | 0 | 70.0 | 70.0 | 3.73 | 410.0 | 50.0 | 9.5 |
| LONG | vwap_reclaim+above_pivot+macd_x_up_neg | 0.6 | 0.8 | asia_0_8 | 10 | 0.17 | 7 | 3 | 0 | 70.0 | 70.0 | 3.73 | 410.0 | 100.0 | 15.0 |
| LONG | above_vwap+macd_x_up_neg+hist_turn_up | 0.6 | 1.2 | full_day | 10 | 0.17 | 7 | 3 | 0 | 70.0 | 70.0 | 3.73 | 410.0 | 50.0 | 9.5 |
| LONG | above_vwap+macd_x_up_neg+hist_turn_up | 0.9 | 0.8 | full_day | 10 | 0.17 | 7 | 3 | 0 | 70.0 | 70.0 | 3.73 | 410.0 | 50.0 | 9.5 |


## ITERATION 2 — greedy precision ensemble (2026-07-25 19:37 CST)

_51 composites unioned (each ≥70% strict / ≥85% tp-before-sl on its own); book constrained to ≥75% strict win-rate._

- **trades:** 46 (0.77/day, 26/60 days covered)
- **strict win-rate:** 82.6%  ·  **tp-before-sl:** 82.6%
- **profit factor:** 7.6  ·  **net:** 2640.0 pts  ·  **maxDD:** 100.0 pts
- **avg hold:** 9.0 min

Configs (see results/ensemble.csv):

  - `LONG:vwap_reclaim+adi_up+macd_x_up_neg+strong_close|nk1.2|vm0.8|full_day` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up_neg+strong_close|nk1.2|vm1.2|full_day` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+delta_surge+macd_x_up_neg+strong_close|nk1.2|vm0.8|full_day` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+delta_surge+macd_x_up_neg+strong_close|nk1.2|vm1.2|full_day` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up_neg|nk1.2|vm0.8|full_day` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up_neg|nk1.2|vm1.2|full_day` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+delta_surge+macd_x_up_neg|nk1.2|vm0.8|full_day` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+delta_surge+macd_x_up_neg|nk1.2|vm1.2|full_day` — 88.9% on 9 trades
  - `LONG:poc_reject_up+delta_surge+strong_close|nk1.2|vm0.8|us_8_16` — 88.9% on 9 trades
  - `LONG:poc_reject_up+delta_surge+strong_close|nk1.2|vm1.2|us_8_16` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+macd_x_up_neg|nk1.2|vm0.8|full_day` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+macd_x_up_neg|nk1.2|vm1.2|full_day` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+delta_surge+macd_x_up_neg|nk1.2|vm0.8|full_day` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+delta_surge+macd_x_up_neg|nk1.2|vm1.2|full_day` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+adi_up+delta_surge+macd_x_up_neg|nk1.2|vm0.8|full_day` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+adi_up+delta_surge+macd_x_up_neg|nk1.2|vm1.2|full_day` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up+macd_x_up_neg|nk1.2|vm0.8|full_day` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up+macd_x_up_neg|nk1.2|vm1.2|full_day` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+delta_surge+macd_x_up+macd_x_up_neg|nk1.2|vm0.8|full_day` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+delta_surge+macd_x_up+macd_x_up_neg|nk1.2|vm1.2|full_day` — 88.9% on 9 trades
  - `LONG:poc_reject_up+adi_up+delta_surge+strong_close|nk1.2|vm0.8|us_8_16` — 88.9% on 9 trades
  - `LONG:poc_reject_up+adi_up+delta_surge+strong_close|nk1.2|vm1.2|us_8_16` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up+strong_close|nk1.2|vm0.8|full_day` — 87.5% on 8 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up+strong_close|nk1.2|vm1.2|full_day` — 87.5% on 8 trades
  - `LONG:vwap_reclaim+delta_surge+macd_x_up+strong_close|nk1.2|vm0.8|full_day` — 87.5% on 8 trades
  - `LONG:vwap_reclaim+delta_surge+macd_x_up+strong_close|nk1.2|vm1.2|full_day` — 87.5% on 8 trades
  - `LONG:above_vwap+adi_up+macd_x_up_neg+strong_close|nk1.2|vm0.8|asia_0_8` — 87.5% on 8 trades
  - `LONG:above_vwap+adi_up+macd_x_up_neg+strong_close|nk1.2|vm1.2|asia_0_8` — 87.5% on 8 trades
  - `LONG:above_vwap+ylow_reclaim+strong_close|nk1.2|vm0.8|us_8_16` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+delta_surge+above_pivot+macd_x_up_neg|nk0.6|vm0.8|full_day` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+delta_surge+above_pivot+macd_x_up_neg|nk0.6|vm1.2|full_day` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+delta_surge+above_pivot+macd_x_up_neg|nk0.9|vm0.8|full_day` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+delta_surge+above_pivot+macd_x_up_neg|nk0.9|vm1.2|full_day` — 85.7% on 7 trades
  - `LONG:above_vwap+poc_reject_up+delta_surge+hist_turn_up|nk0.9|vm0.8|eve_16_24` — 85.7% on 7 trades
  - `LONG:above_vwap+poc_reject_up+delta_surge+hist_turn_up|nk0.9|vm1.2|eve_16_24` — 85.7% on 7 trades
  - `LONG:above_vwap+poc_reject_up+delta_surge+strong_close|nk1.2|vm0.8|us_8_16` — 85.7% on 7 trades
  - `LONG:above_vwap+poc_reject_up+delta_surge+strong_close|nk1.2|vm1.2|us_8_16` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+above_pivot+macd_x_up_neg|nk1.2|vm0.8|asia_0_8` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+above_pivot+macd_x_up_neg|nk1.2|vm1.2|asia_0_8` — 85.7% on 7 trades
  - `LONG:above_vwap+delta_surge+macd_x_up_neg+strong_close|nk1.2|vm0.8|asia_0_8` — 85.7% on 7 trades
  - `LONG:above_vwap+delta_surge+macd_x_up_neg+strong_close|nk1.2|vm1.2|asia_0_8` — 85.7% on 7 trades
  - `LONG:above_vwap+above_pivot+macd_x_up_neg+strong_close|nk1.2|vm1.2|asia_0_8` — 85.7% on 7 trades
  - `LONG:poc_reject_up+delta_surge+above_pivot+strong_close|nk1.2|vm0.8|us_8_16` — 85.7% on 7 trades
  - `LONG:poc_reject_up+delta_surge+above_pivot+strong_close|nk1.2|vm1.2|us_8_16` — 85.7% on 7 trades
  - `SHORT:vwap_loss+macd_x_dn+hist_turn_dn|nk0.6|vm0.8|asia_0_8` — 85.7% on 7 trades
  - `SHORT:vwap_loss+macd_x_dn+hist_turn_dn|nk0.6|vm1.2|asia_0_8` — 85.7% on 7 trades
  - `SHORT:vwap_loss+below_vwap+macd_x_dn+hist_turn_dn|nk0.6|vm0.8|asia_0_8` — 85.7% on 7 trades
  - `SHORT:vwap_loss+below_vwap+macd_x_dn+hist_turn_dn|nk0.6|vm1.2|asia_0_8` — 85.7% on 7 trades
  - `SHORT:vwap_loss+macd_x_dn+hist_turn_dn+weak_close|nk0.6|vm0.8|asia_0_8` — 85.7% on 7 trades
  - `SHORT:vwap_loss+macd_x_dn+hist_turn_dn+weak_close|nk0.6|vm1.2|asia_0_8` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+macd_x_dn+hist_turn_dn|nk0.6|vm0.8|asia_0_8` — 85.7% on 7 trades
