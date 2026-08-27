# QQQ 5m Super-Signal research — 2026-07-15 14:28 CST

_60 sessions of 5-minute QQQ (yfinance, incl. pre-market) · entries ['full_0845_1400', 'am_0845_1130', 'mid_1030_1300', 'pm_1130_1400'] (CST) · entry = next bar open · TP 0.3% ≤ 48 bars · SL 0.3% ≤ 48 bars · time-stop at bar 48 close · same-bar TP+SL = stop (conservative)._
_win_rate counts time-stop scratches as non-wins (strict); tp_before_sl ignores scratches._
_GEX/options-flow: no free historical feed — neutral hook only (see signals.GEX_NOTE)._

## Best configs with ≥2 signal/day (strict win-rate)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHORT | adi_dn+below_pivot | 0.0 | 0.8 | am_0845_1130 | 271 | 4.52 | 154 | 116 | 1 | 56.8 | 57.0 | 1.32 | 11.16 | 8.94 | 29.8 |
| SHORT | adi_dn+below_pivot | 0.8 | 0.8 | am_0845_1130 | 210 | 3.5 | 119 | 90 | 1 | 56.7 | 56.9 | 1.31 | 8.46 | 6.84 | 27.3 |
| SHORT | adi_dn+below_pivot | 0.5 | 0.8 | am_0845_1130 | 269 | 4.48 | 152 | 116 | 1 | 56.5 | 56.7 | 1.3 | 10.56 | 8.94 | 29.7 |
| SHORT | below_vwap+below_pivot | 0.8 | 0.8 | am_0845_1130 | 257 | 4.28 | 145 | 110 | 2 | 56.4 | 56.9 | 1.3 | 10.08 | 7.14 | 27.7 |
| SHORT | adi_dn+below_pivot | 0.8 | 1.2 | am_0845_1130 | 149 | 2.48 | 83 | 65 | 1 | 55.7 | 56.1 | 1.26 | 5.16 | 5.34 | 25.7 |
| SHORT | below_vwap+below_pivot | 0.5 | 1.2 | mid_1030_1300 | 126 | 2.1 | 70 | 53 | 3 | 55.6 | 56.9 | 1.33 | 5.28 | 3.3 | 44.4 |
| SHORT | below_vwap+adi_dn+below_pivot | 0.8 | 0.8 | am_0845_1130 | 184 | 3.07 | 102 | 81 | 1 | 55.4 | 55.7 | 1.25 | 6.06 | 5.94 | 26.6 |
| SHORT | below_vwap+below_pivot | 0.0 | 1.2 | mid_1030_1300 | 127 | 2.12 | 70 | 54 | 3 | 55.1 | 56.5 | 1.31 | 4.98 | 3.6 | 44.1 |
| SHORT | adi_dn+below_pivot | 0.0 | 1.2 | am_0845_1130 | 174 | 2.9 | 95 | 78 | 1 | 54.6 | 54.9 | 1.21 | 4.86 | 6.54 | 27.8 |
| SHORT | below_vwap+below_pivot | 0.0 | 0.8 | am_0845_1130 | 327 | 5.45 | 178 | 146 | 3 | 54.4 | 54.9 | 1.21 | 9.18 | 10.32 | 30.8 |
| SHORT | below_pivot+cvd_dn_v | 0.8 | 0.8 | full_0845_1400 | 162 | 2.7 | 88 | 64 | 10 | 54.3 | 57.9 | 1.34 | 6.7 | 2.9 | 33.6 |
| SHORT | below_vwap+below_pivot+cvd_dn_v | 0.8 | 0.8 | full_0845_1400 | 162 | 2.7 | 88 | 64 | 10 | 54.3 | 57.9 | 1.34 | 6.7 | 2.9 | 33.6 |
| SHORT | below_pivot+cvd_dn+cvd_dn_v | 0.8 | 0.8 | full_0845_1400 | 162 | 2.7 | 88 | 64 | 10 | 54.3 | 57.9 | 1.34 | 6.7 | 2.9 | 33.6 |
| SHORT | below_pivot+cvd_dn_v | 0.8 | 1.2 | full_0845_1400 | 162 | 2.7 | 88 | 64 | 10 | 54.3 | 57.9 | 1.34 | 6.7 | 2.9 | 33.6 |
| SHORT | below_vwap+below_pivot+cvd_dn_v | 0.8 | 1.2 | full_0845_1400 | 162 | 2.7 | 88 | 64 | 10 | 54.3 | 57.9 | 1.34 | 6.7 | 2.9 | 33.6 |

## Highest strict win-rate overall (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHORT | adi_dn+r1_reject | 0.0 | 0.8 | am_0845_1130 | 21 | 0.35 | 18 | 3 | 0 | 85.7 | 85.7 | 6.0 | 4.5 | 0.3 | 32.4 |
| SHORT | adi_dn+r1_reject | 0.5 | 0.8 | am_0845_1130 | 21 | 0.35 | 18 | 3 | 0 | 85.7 | 85.7 | 6.0 | 4.5 | 0.3 | 32.4 |
| SHORT | adi_dn+r1_reject | 0.8 | 0.8 | am_0845_1130 | 18 | 0.3 | 15 | 3 | 0 | 83.3 | 83.3 | 5.0 | 3.6 | 0.3 | 30.8 |
| SHORT | adi_dn+r1_reject | 0.0 | 1.2 | am_0845_1130 | 17 | 0.28 | 14 | 3 | 0 | 82.4 | 82.4 | 4.67 | 3.3 | 0.3 | 27.4 |
| SHORT | adi_dn+r1_reject | 0.5 | 1.2 | am_0845_1130 | 17 | 0.28 | 14 | 3 | 0 | 82.4 | 82.4 | 4.67 | 3.3 | 0.3 | 27.4 |
| LONG | vwap_reclaim+adi_up+macd_x_up | 0.0 | 0.8 | am_0845_1130 | 11 | 0.18 | 9 | 1 | 1 | 81.8 | 90.0 | 9.53 | 2.56 | 0.3 | 63.2 |
| LONG | vwap_reclaim+adi_up+macd_x_up | 0.5 | 0.8 | am_0845_1130 | 11 | 0.18 | 9 | 1 | 1 | 81.8 | 90.0 | 9.53 | 2.56 | 0.3 | 63.2 |
| LONG | adi_up+s1_bounce+strong_close | 0.8 | 0.8 | am_0845_1130 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 39.1 |
| SHORT | delta_dump+r1_reject | 0.0 | 0.8 | am_0845_1130 | 16 | 0.27 | 13 | 3 | 0 | 81.2 | 81.2 | 4.33 | 3.0 | 0.3 | 28.8 |
| SHORT | adi_dn+delta_dump+r1_reject | 0.0 | 0.8 | am_0845_1130 | 16 | 0.27 | 13 | 3 | 0 | 81.2 | 81.2 | 4.33 | 3.0 | 0.3 | 28.8 |
| SHORT | adi_dn+r1_reject+weak_close | 0.0 | 0.8 | am_0845_1130 | 16 | 0.27 | 13 | 3 | 0 | 81.2 | 81.2 | 4.33 | 3.0 | 0.3 | 39.4 |
| SHORT | delta_dump+r1_reject | 0.0 | 1.2 | am_0845_1130 | 16 | 0.27 | 13 | 3 | 0 | 81.2 | 81.2 | 4.33 | 3.0 | 0.3 | 28.8 |
| SHORT | adi_dn+delta_dump+r1_reject | 0.0 | 1.2 | am_0845_1130 | 16 | 0.27 | 13 | 3 | 0 | 81.2 | 81.2 | 4.33 | 3.0 | 0.3 | 28.8 |
| SHORT | delta_dump+r1_reject | 0.5 | 0.8 | am_0845_1130 | 16 | 0.27 | 13 | 3 | 0 | 81.2 | 81.2 | 4.33 | 3.0 | 0.3 | 28.8 |
| SHORT | adi_dn+delta_dump+r1_reject | 0.5 | 0.8 | am_0845_1130 | 16 | 0.27 | 13 | 3 | 0 | 81.2 | 81.2 | 4.33 | 3.0 | 0.3 | 28.8 |

## Highest TP-before-SL rate (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | vwap_reclaim+macd_x_up | 0.0 | 0.8 | am_0845_1130 | 12 | 0.2 | 9 | 1 | 2 | 75.0 | 90.0 | 10.04 | 2.71 | 0.3 | 77.9 |
| LONG | vwap_reclaim+above_vwap+macd_x_up | 0.0 | 0.8 | am_0845_1130 | 12 | 0.2 | 9 | 1 | 2 | 75.0 | 90.0 | 10.04 | 2.71 | 0.3 | 77.9 |
| LONG | vwap_reclaim+macd_x_up | 0.5 | 0.8 | am_0845_1130 | 12 | 0.2 | 9 | 1 | 2 | 75.0 | 90.0 | 10.04 | 2.71 | 0.3 | 77.9 |
| LONG | vwap_reclaim+above_vwap+macd_x_up | 0.5 | 0.8 | am_0845_1130 | 12 | 0.2 | 9 | 1 | 2 | 75.0 | 90.0 | 10.04 | 2.71 | 0.3 | 77.9 |
| LONG | vwap_reclaim+adi_up+macd_x_up | 0.0 | 0.8 | am_0845_1130 | 11 | 0.18 | 9 | 1 | 1 | 81.8 | 90.0 | 9.53 | 2.56 | 0.3 | 63.2 |
| LONG | vwap_reclaim+adi_up+macd_x_up | 0.5 | 0.8 | am_0845_1130 | 11 | 0.18 | 9 | 1 | 1 | 81.8 | 90.0 | 9.53 | 2.56 | 0.3 | 63.2 |
| LONG | vwap_reclaim+above_pivot+macd_x_up | 0.0 | 0.8 | full_0845_1400 | 11 | 0.18 | 8 | 1 | 2 | 72.7 | 88.9 | 9.04 | 2.41 | 0.3 | 63.6 |
| LONG | vwap_reclaim+macd_x_up_neg | 0.0 | 0.8 | am_0845_1130 | 11 | 0.18 | 8 | 1 | 2 | 72.7 | 88.9 | 9.04 | 2.41 | 0.3 | 82.3 |
| LONG | vwap_reclaim+above_vwap+macd_x_up_neg | 0.0 | 0.8 | am_0845_1130 | 11 | 0.18 | 8 | 1 | 2 | 72.7 | 88.9 | 9.04 | 2.41 | 0.3 | 82.3 |
| LONG | vwap_reclaim+macd_x_up+macd_x_up_neg | 0.0 | 0.8 | am_0845_1130 | 11 | 0.18 | 8 | 1 | 2 | 72.7 | 88.9 | 9.04 | 2.41 | 0.3 | 82.3 |
| LONG | vwap_reclaim+above_pivot+macd_x_up | 0.5 | 0.8 | full_0845_1400 | 11 | 0.18 | 8 | 1 | 2 | 72.7 | 88.9 | 9.04 | 2.41 | 0.3 | 63.6 |
| LONG | vwap_reclaim+macd_x_up_neg | 0.5 | 0.8 | am_0845_1130 | 11 | 0.18 | 8 | 1 | 2 | 72.7 | 88.9 | 9.04 | 2.41 | 0.3 | 82.3 |
| LONG | vwap_reclaim+above_vwap+macd_x_up_neg | 0.5 | 0.8 | am_0845_1130 | 11 | 0.18 | 8 | 1 | 2 | 72.7 | 88.9 | 9.04 | 2.41 | 0.3 | 82.3 |
| LONG | vwap_reclaim+macd_x_up+macd_x_up_neg | 0.5 | 0.8 | am_0845_1130 | 11 | 0.18 | 8 | 1 | 2 | 72.7 | 88.9 | 9.04 | 2.41 | 0.3 | 82.3 |
| LONG | vwap_reclaim+above_pivot+macd_x_up | 0.8 | 0.8 | full_0845_1400 | 11 | 0.18 | 8 | 1 | 2 | 72.7 | 88.9 | 9.04 | 2.41 | 0.3 | 63.6 |


## ITERATION 2 — greedy precision ensemble (2026-07-15 14:37 CST)

_316 composites unioned (each ≥70% strict / ≥85% tp-before-sl on its own); book constrained to ≥75% strict win-rate._

- **trades:** 85 (1.42/day, 38/60 days covered)
- **strict win-rate:** 75.3%  ·  **tp-before-sl:** 83.1%
- **profit factor:** 5.03  ·  **net:** 16.06%  ·  **maxDD:** 0.9%
- **avg hold:** 49.3 min

Configs (see results/ensemble.csv):

  - `LONG:adi_up+s1_bounce|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:adi_up+s1_bounce|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:adi_up+s1_bounce+strong_close|nk0.8|vm1.2|full_0845_1400` — 100.0% on 7 trades
  - `LONG:above_vwap+s1_bounce|nk0.0|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `LONG:above_vwap+s1_bounce|nk0.5|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `LONG:delta_surge+s1_bounce|nk0.8|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `LONG:delta_surge+s1_bounce|nk0.8|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `LONG:above_vwap+adi_up+s1_bounce|nk0.0|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `LONG:above_vwap+adi_up+s1_bounce|nk0.5|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `LONG:above_vwap+s1_bounce+strong_close|nk0.0|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `LONG:above_vwap+s1_bounce+strong_close|nk0.5|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `LONG:adi_up+delta_surge+s1_bounce|nk0.8|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `LONG:adi_up+delta_surge+s1_bounce|nk0.8|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `LONG:adi_up+s1_bounce+strong_close|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+s1_bounce+strong_close|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+s1_bounce+strong_close|nk0.8|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `LONG:above_vwap+adi_up+s1_bounce+strong_close|nk0.0|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `LONG:above_vwap+adi_up+s1_bounce+strong_close|nk0.5|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `LONG:adi_up+s1_bounce+strong_close|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `LONG:adi_up+s1_bounce+strong_close|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up+strong_close|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up+strong_close|nk0.5|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:adi_up+above_pivot+strong_close+vwap_lo_bounce|nk0.0|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:adi_up+above_pivot+strong_close+vwap_lo_bounce|nk0.5|vm0.8|am_0845_1130` — 88.9% on 9 trades
  - `LONG:adi_up+s1_bounce|nk0.8|vm1.2|am_0845_1130` — 87.5% on 8 trades
  - `LONG:delta_surge+s1_bounce|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `LONG:delta_surge+s1_bounce|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `LONG:delta_surge+s1_bounce|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `LONG:delta_surge+s1_bounce|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `LONG:adi_up+delta_surge+s1_bounce|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `LONG:adi_up+delta_surge+s1_bounce|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `LONG:adi_up+delta_surge+s1_bounce|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `LONG:adi_up+delta_surge+s1_bounce|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up+strong_close|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up_neg+strong_close|nk0.0|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up_neg+strong_close|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:vwap_reclaim+macd_x_up+strong_close+cvd_up|nk0.0|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:vwap_reclaim+macd_x_up+strong_close+cvd_up|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:vwap_reclaim+macd_x_up_neg+strong_close+cvd_up|nk0.0|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:vwap_reclaim+macd_x_up_neg+strong_close+cvd_up|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:adi_up+above_pivot+strong_close+vwap_lo_bounce|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:adi_dn+r1_reject|nk0.0|vm0.8|am_0845_1130` — 85.7% on 21 trades
  - `SHORT:adi_dn+r1_reject|nk0.5|vm0.8|am_0845_1130` — 85.7% on 21 trades
  - `LONG:adi_up+s1_bounce+strong_close|nk0.0|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+s1_bounce+strong_close|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:delta_surge+s1_bounce+strong_close|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:delta_surge+s1_bounce+strong_close|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:delta_surge+s1_bounce+strong_close|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:delta_surge+s1_bounce+strong_close|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+macd_x_up|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+macd_x_up|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+macd_x_up|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up_neg+strong_close|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+macd_x_up+strong_close+cvd_up|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+macd_x_up_neg+strong_close+cvd_up|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+delta_surge+s1_bounce+strong_close|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:adi_up+delta_surge+s1_bounce+strong_close|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:adi_up+delta_surge+s1_bounce+strong_close|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:adi_up+delta_surge+s1_bounce+strong_close|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:adi_up+s1_bounce+hist_turn_up+strong_close|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+s1_bounce+hist_turn_up+strong_close|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:orb_break_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:orb_break_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:orb_break_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:orb_break_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:orb_break_up_v+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:orb_break_up_v+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:orb_break_up_v+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:orb_break_up_v+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+orb_break_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+orb_break_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+orb_break_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+orb_break_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+orb_break_up_v+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+orb_break_up_v+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+orb_break_up_v+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+orb_break_up_v+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_pivot+orb_break_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_pivot+orb_break_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_pivot+orb_break_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_pivot+orb_break_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_pivot+orb_break_up_v+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_pivot+orb_break_up_v+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_pivot+orb_break_up_v+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_pivot+orb_break_up_v+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:orb_break_up+orb_break_up_v+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:orb_break_up+orb_break_up_v+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:orb_break_up+orb_break_up_v+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:orb_break_up+orb_break_up_v+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+macd_x_up_neg|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+macd_x_up_neg|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+macd_x_up_neg|nk0.8|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up+strong_close|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up+strong_close|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up+strong_close|nk0.8|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up+cvd_up|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up+cvd_up|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up+cvd_up|nk0.8|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up_neg+cvd_up|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up_neg+cvd_up|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up_neg+cvd_up|nk0.8|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+above_pivot+orb_break_up+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+above_pivot+orb_break_up+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+above_pivot+orb_break_up+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+above_pivot+orb_break_up+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+above_pivot+orb_break_up_v+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+above_pivot+orb_break_up_v+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+above_pivot+orb_break_up_v+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+above_pivot+orb_break_up_v+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+orb_break_up+orb_break_up_v+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+orb_break_up+orb_break_up_v+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+orb_break_up+orb_break_up_v+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_vwap+orb_break_up+orb_break_up_v+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_pivot+orb_break_up+orb_break_up_v+above_vwap_v|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_pivot+orb_break_up+orb_break_up_v+above_vwap_v|nk0.0|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_pivot+orb_break_up+orb_break_up_v+above_vwap_v|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:above_pivot+orb_break_up+orb_break_up_v+above_vwap_v|nk0.5|vm1.2|am_0845_1130` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up|nk0.0|vm0.8|am_0845_1130` — 81.8% on 11 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up|nk0.5|vm0.8|am_0845_1130` — 81.8% on 11 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+macd_x_up|nk0.0|vm0.8|am_0845_1130` — 81.8% on 11 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+macd_x_up|nk0.5|vm0.8|am_0845_1130` — 81.8% on 11 trades
  - `LONG:adi_up+s1_bounce|nk0.8|vm1.2|full_0845_1400` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up|nk0.8|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up_neg|nk0.0|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up_neg|nk0.5|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+macd_x_up+strong_close|nk0.0|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+macd_x_up+strong_close|nk0.5|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+macd_x_up+cvd_up|nk0.0|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+macd_x_up+cvd_up|nk0.5|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+macd_x_up_neg+cvd_up|nk0.0|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+macd_x_up_neg+cvd_up|nk0.5|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:adi_up+above_pivot+vwap_lo_bounce|nk0.0|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:adi_up+above_pivot+vwap_lo_bounce|nk0.5|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+macd_x_up|nk0.8|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+macd_x_up_neg|nk0.0|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+macd_x_up_neg|nk0.5|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up+strong_close|nk0.0|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up+strong_close|nk0.5|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up+cvd_up|nk0.0|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up+cvd_up|nk0.5|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up_neg+cvd_up|nk0.0|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up_neg+cvd_up|nk0.5|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up+macd_x_up_neg|nk0.0|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up+macd_x_up_neg|nk0.5|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up+cvd_up|nk0.0|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up+cvd_up|nk0.5|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up_neg+cvd_up|nk0.0|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up_neg+cvd_up|nk0.5|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+macd_x_up+macd_x_up_neg+cvd_up|nk0.0|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+macd_x_up+macd_x_up_neg+cvd_up|nk0.5|vm0.8|am_0845_1130` — 80.0% on 10 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up_neg|nk0.8|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+macd_x_up+strong_close|nk0.8|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+macd_x_up+cvd_up|nk0.8|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+macd_x_up_neg+strong_close|nk0.0|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+macd_x_up_neg+strong_close|nk0.5|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+macd_x_up_neg+cvd_up|nk0.8|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:adi_up+above_pivot+vwap_lo_bounce|nk0.8|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+macd_x_up_neg|nk0.8|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up+strong_close|nk0.8|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up+cvd_up|nk0.8|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up_neg+strong_close|nk0.0|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up_neg+strong_close|nk0.5|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up_neg+cvd_up|nk0.8|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+macd_x_up|nk0.0|vm0.8|full_0845_1400` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+macd_x_up|nk0.5|vm0.8|full_0845_1400` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+macd_x_up|nk0.8|vm0.8|full_0845_1400` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up+macd_x_up_neg|nk0.8|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up+cvd_up|nk0.8|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+adi_up+macd_x_up_neg+cvd_up|nk0.8|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up+strong_close|nk0.0|vm0.8|full_0845_1400` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up+strong_close|nk0.5|vm0.8|full_0845_1400` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up+strong_close|nk0.8|vm0.8|full_0845_1400` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up+cvd_up|nk0.0|vm0.8|full_0845_1400` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up+cvd_up|nk0.5|vm0.8|full_0845_1400` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up+cvd_up|nk0.8|vm0.8|full_0845_1400` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+macd_x_up+macd_x_up_neg+strong_close|nk0.0|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+macd_x_up+macd_x_up_neg+strong_close|nk0.5|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+macd_x_up+macd_x_up_neg+cvd_up|nk0.8|vm0.8|am_0845_1130` — 77.8% on 9 trades
  - `LONG:adi_up+s1_bounce+hist_turn_up+strong_close|nk0.0|vm0.8|full_0845_1400` — 77.8% on 9 trades
  - `LONG:adi_up+s1_bounce+hist_turn_up+strong_close|nk0.5|vm0.8|full_0845_1400` — 77.8% on 9 trades
  - `LONG:vwap_reclaim+macd_x_up|nk0.0|vm0.8|am_0845_1130` — 75.0% on 12 trades
  - `LONG:vwap_reclaim+macd_x_up|nk0.5|vm0.8|am_0845_1130` — 75.0% on 12 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up|nk0.0|vm0.8|am_0845_1130` — 75.0% on 12 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up|nk0.5|vm0.8|am_0845_1130` — 75.0% on 12 trades
  - `LONG:delta_surge+orb_break_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:delta_surge+orb_break_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:s1_bounce+strong_close|nk0.0|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `LONG:s1_bounce+strong_close|nk0.5|vm0.8|mid_1030_1300` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up|nk0.0|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up|nk0.5|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up|nk0.8|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+macd_x_up_neg+strong_close|nk0.8|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:above_vwap+delta_surge+orb_break_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+delta_surge+orb_break_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+delta_surge+orb_break_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+delta_surge+orb_break_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v|nk0.0|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v|nk0.0|vm1.2|am_0845_1130` — 75.0% on 8 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v|nk0.5|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v|nk0.5|vm1.2|am_0845_1130` — 75.0% on 8 trades
  - `LONG:adi_up+orb_break_up+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+orb_break_up+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+orb_break_up_v+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+orb_break_up_v+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:delta_surge+orb_break_up+orb_break_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:delta_surge+orb_break_up+orb_break_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:delta_surge+orb_break_up+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:delta_surge+orb_break_up+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:delta_surge+orb_break_up_v+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:delta_surge+orb_break_up_v+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up+above_vwap_v+cvd_up|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up+above_vwap_v+cvd_up|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up+above_vwap_v+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up+above_vwap_v+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up_v+above_vwap_v+cvd_up|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up_v+above_vwap_v+cvd_up|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up_v+above_vwap_v+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up_v+above_vwap_v+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+macd_x_up|nk0.0|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+macd_x_up|nk0.5|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+macd_x_up|nk0.8|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up_neg+strong_close|nk0.8|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+vwap_reclaim_v|nk0.0|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+vwap_reclaim_v|nk0.0|vm1.2|am_0845_1130` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+vwap_reclaim_v|nk0.5|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+vwap_reclaim_v|nk0.5|vm1.2|am_0845_1130` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up_neg+cvd_up|nk0.0|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up_neg+cvd_up|nk0.5|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up_neg+cvd_up|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+macd_x_up+macd_x_up_neg+strong_close|nk0.8|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:above_vwap+adi_up+delta_surge+orb_break_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+adi_up+delta_surge+orb_break_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+adi_up+above_pivot+vwap_reclaim_v|nk0.0|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:above_vwap+adi_up+above_pivot+vwap_reclaim_v|nk0.0|vm1.2|am_0845_1130` — 75.0% on 8 trades
  - `LONG:above_vwap+adi_up+above_pivot+vwap_reclaim_v|nk0.5|vm0.8|am_0845_1130` — 75.0% on 8 trades
  - `LONG:above_vwap+adi_up+above_pivot+vwap_reclaim_v|nk0.5|vm1.2|am_0845_1130` — 75.0% on 8 trades
  - `LONG:above_vwap+adi_up+orb_break_up+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+adi_up+orb_break_up+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+adi_up+orb_break_up_v+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+adi_up+orb_break_up_v+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+delta_surge+orb_break_up+orb_break_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+delta_surge+orb_break_up+orb_break_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+delta_surge+orb_break_up+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+delta_surge+orb_break_up+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+delta_surge+orb_break_up_v+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+delta_surge+orb_break_up_v+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+orb_break_up+above_vwap_v+cvd_up|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+orb_break_up+above_vwap_v+cvd_up|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+orb_break_up+above_vwap_v+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+orb_break_up+above_vwap_v+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+orb_break_up_v+above_vwap_v+cvd_up|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+orb_break_up_v+above_vwap_v+cvd_up|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+orb_break_up_v+above_vwap_v+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:above_vwap+orb_break_up_v+above_vwap_v+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+delta_surge+orb_break_up+orb_break_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+delta_surge+orb_break_up+orb_break_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+delta_surge+orb_break_up+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+delta_surge+orb_break_up+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+delta_surge+orb_break_up_v+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+delta_surge+orb_break_up_v+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+s1_bounce+hist_turn_up+strong_close|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+orb_break_up+orb_break_up_v+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:adi_up+orb_break_up+orb_break_up_v+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:delta_surge+orb_break_up+orb_break_up_v+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:delta_surge+orb_break_up+orb_break_up_v+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up+orb_break_up_v+above_vwap_v+cvd_up|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up+orb_break_up_v+above_vwap_v+cvd_up|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up+orb_break_up_v+above_vwap_v+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up+orb_break_up_v+above_vwap_v+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up+above_vwap_v+cvd_up+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up+above_vwap_v+cvd_up+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up_v+above_vwap_v+cvd_up+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:orb_break_up_v+above_vwap_v+cvd_up+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:below_pivot+macd_x_dn+mom_ignite_dn|nk0.0|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:below_pivot+macd_x_dn+mom_ignite_dn|nk0.5|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+macd_x_up|nk0.8|vm0.8|am_0845_1130` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+macd_x_up_neg|nk0.0|vm0.8|am_0845_1130` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+macd_x_up_neg|nk0.5|vm0.8|am_0845_1130` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up|nk0.8|vm0.8|am_0845_1130` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up_neg|nk0.0|vm0.8|am_0845_1130` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up_neg|nk0.5|vm0.8|am_0845_1130` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up|nk0.0|vm0.8|full_0845_1400` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up|nk0.5|vm0.8|full_0845_1400` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up|nk0.8|vm0.8|full_0845_1400` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+macd_x_up+macd_x_up_neg|nk0.0|vm0.8|am_0845_1130` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+macd_x_up+macd_x_up_neg|nk0.5|vm0.8|am_0845_1130` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+macd_x_up|nk0.0|vm0.8|full_0845_1400` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+macd_x_up|nk0.5|vm0.8|full_0845_1400` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+macd_x_up|nk0.8|vm0.8|full_0845_1400` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up+macd_x_up_neg|nk0.0|vm0.8|am_0845_1130` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up+macd_x_up_neg|nk0.5|vm0.8|am_0845_1130` — 72.7% on 11 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up_neg|nk0.0|vm0.8|am_0845_1130` — 71.4% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up_neg|nk0.5|vm0.8|am_0845_1130` — 71.4% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up_neg|nk0.8|vm0.8|am_0845_1130` — 71.4% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+macd_x_up_neg|nk0.0|vm0.8|am_0845_1130` — 71.4% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+macd_x_up_neg|nk0.5|vm0.8|am_0845_1130` — 71.4% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+macd_x_up_neg|nk0.8|vm0.8|am_0845_1130` — 71.4% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up+macd_x_up_neg|nk0.0|vm0.8|am_0845_1130` — 71.4% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up+macd_x_up_neg|nk0.5|vm0.8|am_0845_1130` — 71.4% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+macd_x_up+macd_x_up_neg|nk0.8|vm0.8|am_0845_1130` — 71.4% on 7 trades
  - `LONG:vwap_reclaim+macd_x_up_neg|nk0.8|vm0.8|am_0845_1130` — 70.0% on 10 trades
  - `LONG:orb_break_up+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 70.0% on 10 trades
  - `LONG:orb_break_up+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 70.0% on 10 trades
  - `LONG:orb_break_up_v+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 70.0% on 10 trades
  - `LONG:orb_break_up_v+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 70.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up_neg|nk0.8|vm0.8|am_0845_1130` — 70.0% on 10 trades
  - `LONG:vwap_reclaim+macd_x_up+macd_x_up_neg|nk0.8|vm0.8|am_0845_1130` — 70.0% on 10 trades
  - `LONG:above_vwap+orb_break_up+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 70.0% on 10 trades
  - `LONG:above_vwap+orb_break_up+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 70.0% on 10 trades
  - `LONG:above_vwap+orb_break_up_v+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 70.0% on 10 trades
  - `LONG:above_vwap+orb_break_up_v+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 70.0% on 10 trades
  - `LONG:orb_break_up+orb_break_up_v+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 70.0% on 10 trades
  - `LONG:orb_break_up+orb_break_up_v+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 70.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+macd_x_up+macd_x_up_neg|nk0.8|vm0.8|am_0845_1130` — 70.0% on 10 trades
  - `LONG:above_vwap+orb_break_up+orb_break_up_v+above_vwap_v|nk0.8|vm0.8|full_0845_1400` — 70.0% on 10 trades
  - `LONG:above_vwap+orb_break_up+orb_break_up_v+above_vwap_v|nk0.8|vm1.2|full_0845_1400` — 70.0% on 10 trades


## FINAL VERDICT — A-BOOK PRECISION UNION (QQQ, +/-0.30% in 4h, entry >=08:45, TP by 14:35 CST, 60 sessions)

Goal (max A-book signals/day at near-perfect precision) — precision frontier reached: **0.85/day** is the max the >95% bar allows here.

| metric | value |
|--------|-------|
| resolved trades | 51 (39 target / 0 stop / 12 scratch) |
| **TP-before-SL** | **100.0%** (0 stops) |
| strict win-rate | 76.5% |
| **frequency** | **0.85/day** (32/60 sessions) |
| net | +12.3% |

### A-book families (live `A_BOOK` in qqq_intraday_bot.py)

| # | direction | signal (blocks) | window | gate | trades | TP-b-SL | strict |
|---|-----------|-----------------|--------|------|--------|---------|--------|
| 1 | LONG | `vwap_reclaim+cvd_up` | mid_1030_1300 | 0.8/1.2 | 9 | 100% | 67% |
| 2 | LONG | `above_pivot+mom_ignite_up` | mid_1030_1300 | 0.5/1.2 | 9 | 100% | 56% |
| 3 | LONG | `vwap_reclaim+above_pivot+macd_x_up` | am_0845_1130 | 0.0/0.8 | 8 | 100% | 75% |
| 4 | LONG | `above_pivot+hist_turn_up+rvol_thrust_up` | am_0845_1130 | 0.0/0.8 | 8 | 100% | 62% |
| 5 | LONG | `adi_up+s1_bounce` | mid_1030_1300 | 0.0/0.8 | 7 | 100% | 100% |
| 6 | LONG | `adi_up+s1_bounce+strong_close` | full_0845_1400 | 0.8/1.2 | 7 | 100% | 100% |
| 7 | LONG | `delta_surge+orb_break_up_v` | am_0845_1130 | 0.0/0.8 | 5 | 100% | 100% |
| 8 | LONG | `delta_surge+s1_bounce` | full_0845_1400 | 0.8/0.8 | 6 | 100% | 100% |
| 9 | LONG | `orb_break_up+above_vwap_v+rsi_thrust_up` | full_0845_1400 | 0.0/0.8 | 5 | 100% | 100% |

**Read this before trading.** In-sample results on one ~3-month regime (~59 sessions). A-book families were selected because they rarely/never stopped in-sample — treat the TP-before-SL figure as an upper bound; the residual risk is the SCRATCH rate (time-stops at the 4h/14:35 deadline). Forward-validate before sizing. Desk session rule enforced in the engine: signals only after 08:45 CST, TP truncated at 14:35 CST.
