# COIN 5m Super-Signal research — 2026-07-15 15:41 CST

_60 sessions of 5-minute COIN (yfinance, incl. pre-market) · entries ['full_0845_1400', 'am_0845_1130', 'mid_1030_1300', 'pm_1130_1400'] (CST) · entry = next bar open · TP 0.3% ≤ 48 bars · SL 0.3% ≤ 48 bars · time-stop at bar 48 close · same-bar TP+SL = stop (conservative)._
_win_rate counts time-stop scratches as non-wins (strict); tp_before_sl ignores scratches._
_GEX/options-flow: no free historical feed — neutral hook only (see signals.GEX_NOTE)._

## Best configs with ≥2 signal/day (strict win-rate)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHORT | below_vwap+below_pivot | 0.8 | 1.2 | pm_1130_1400 | 143 | 2.38 | 81 | 62 | 0 | 56.6 | 56.6 | 1.31 | 5.7 | 4.2 | 9.9 |
| SHORT | hist_turn_dn+weak_close | 0.5 | 0.8 | pm_1130_1400 | 141 | 2.35 | 79 | 62 | 0 | 56.0 | 56.0 | 1.27 | 5.1 | 2.1 | 11.3 |
| SHORT | hist_turn_dn+weak_close | 0.0 | 0.8 | pm_1130_1400 | 143 | 2.38 | 80 | 63 | 0 | 55.9 | 55.9 | 1.27 | 5.1 | 2.1 | 11.3 |
| SHORT | below_vwap+weak_close | 0.5 | 1.2 | pm_1130_1400 | 120 | 2.0 | 67 | 53 | 0 | 55.8 | 55.8 | 1.26 | 4.2 | 2.4 | 10.3 |
| SHORT | below_vwap+adi_dn+below_pivot | 0.0 | 1.2 | pm_1130_1400 | 137 | 2.28 | 76 | 61 | 0 | 55.5 | 55.5 | 1.25 | 4.5 | 3.9 | 9.9 |
| SHORT | below_vwap+weak_close | 0.0 | 1.2 | pm_1130_1400 | 121 | 2.02 | 67 | 54 | 0 | 55.4 | 55.4 | 1.24 | 3.9 | 2.4 | 10.4 |
| SHORT | adi_dn+below_pivot+cvd_dn_v | 0.0 | 0.8 | pm_1130_1400 | 123 | 2.05 | 68 | 55 | 0 | 55.3 | 55.3 | 1.24 | 3.9 | 3.9 | 10.1 |
| SHORT | adi_dn+below_pivot+cvd_dn | 0.0 | 1.2 | pm_1130_1400 | 123 | 2.05 | 68 | 55 | 0 | 55.3 | 55.3 | 1.24 | 3.9 | 3.9 | 10.1 |
| SHORT | adi_dn+below_pivot+cvd_dn_v | 0.0 | 1.2 | pm_1130_1400 | 123 | 2.05 | 68 | 55 | 0 | 55.3 | 55.3 | 1.24 | 3.9 | 3.9 | 10.1 |
| SHORT | below_vwap+adi_dn+below_pivot | 0.5 | 1.2 | pm_1130_1400 | 134 | 2.23 | 74 | 60 | 0 | 55.2 | 55.2 | 1.23 | 4.2 | 3.9 | 9.9 |
| SHORT | adi_dn+below_pivot+cvd_dn_v | 0.5 | 0.8 | pm_1130_1400 | 120 | 2.0 | 66 | 54 | 0 | 55.0 | 55.0 | 1.22 | 3.6 | 3.9 | 10.1 |
| SHORT | adi_dn+below_pivot+cvd_dn | 0.5 | 1.2 | pm_1130_1400 | 120 | 2.0 | 66 | 54 | 0 | 55.0 | 55.0 | 1.22 | 3.6 | 3.9 | 10.1 |
| SHORT | adi_dn+below_pivot+cvd_dn_v | 0.5 | 1.2 | pm_1130_1400 | 120 | 2.0 | 66 | 54 | 0 | 55.0 | 55.0 | 1.22 | 3.6 | 3.9 | 10.1 |
| SHORT | below_pivot+cvd_dn_v | 0.0 | 0.8 | pm_1130_1400 | 139 | 2.32 | 76 | 63 | 0 | 54.7 | 54.7 | 1.21 | 3.9 | 4.5 | 10.3 |
| SHORT | below_vwap+below_pivot+cvd_dn_v | 0.0 | 0.8 | pm_1130_1400 | 139 | 2.32 | 76 | 63 | 0 | 54.7 | 54.7 | 1.21 | 3.9 | 4.5 | 10.3 |

## Highest strict win-rate overall (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | above_vwap+above_pivot+macd_x_up | 0.0 | 0.8 | mid_1030_1300 | 14 | 0.23 | 13 | 1 | 0 | 92.9 | 92.9 | 13.0 | 3.6 | 0.3 | 7.5 |
| LONG | adi_up+above_pivot+macd_x_up | 0.0 | 0.8 | mid_1030_1300 | 14 | 0.23 | 13 | 1 | 0 | 92.9 | 92.9 | 13.0 | 3.6 | 0.3 | 6.8 |
| LONG | above_vwap+above_pivot+macd_x_up | 0.5 | 0.8 | mid_1030_1300 | 13 | 0.22 | 12 | 1 | 0 | 92.3 | 92.3 | 12.0 | 3.3 | 0.3 | 7.3 |
| LONG | adi_up+above_pivot+macd_x_up | 0.5 | 0.8 | mid_1030_1300 | 13 | 0.22 | 12 | 1 | 0 | 92.3 | 92.3 | 12.0 | 3.3 | 0.3 | 6.5 |
| LONG | above_pivot+macd_x_up+cvd_up | 0.0 | 0.8 | mid_1030_1300 | 12 | 0.2 | 11 | 1 | 0 | 91.7 | 91.7 | 11.0 | 3.0 | 0.3 | 6.7 |
| LONG | above_pivot+macd_x_up+cvd_up | 0.5 | 0.8 | mid_1030_1300 | 11 | 0.18 | 10 | 1 | 0 | 90.9 | 90.9 | 10.0 | 2.7 | 0.3 | 6.4 |
| LONG | above_pivot+macd_x_up | 0.0 | 0.8 | mid_1030_1300 | 17 | 0.28 | 15 | 2 | 0 | 88.2 | 88.2 | 7.5 | 3.9 | 0.3 | 7.9 |
| LONG | above_pivot+macd_x_up | 0.5 | 0.8 | mid_1030_1300 | 16 | 0.27 | 14 | 2 | 0 | 87.5 | 87.5 | 7.0 | 3.6 | 0.3 | 7.8 |
| LONG | adi_up+strong_close+vwap_lo_bounce | 0.8 | 1.2 | am_0845_1130 | 12 | 0.2 | 10 | 2 | 0 | 83.3 | 83.3 | 5.0 | 2.4 | 0.3 | 6.2 |
| LONG | above_pivot+macd_x_up+strong_close | 0.0 | 0.8 | mid_1030_1300 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 8.2 |
| LONG | above_pivot+strong_close+mom_ignite_up | 0.0 | 1.2 | pm_1130_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 7.3 |
| LONG | above_pivot+macd_x_up+strong_close | 0.5 | 0.8 | mid_1030_1300 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 8.2 |
| LONG | above_pivot+strong_close+mom_ignite_up | 0.5 | 1.2 | pm_1130_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 7.3 |
| SHORT | adi_dn+orb_break_dn | 0.8 | 0.8 | pm_1130_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 8.2 |
| LONG | above_vwap+above_pivot+macd_x_up | 0.0 | 0.8 | pm_1130_1400 | 16 | 0.27 | 13 | 3 | 0 | 81.2 | 81.2 | 4.33 | 3.0 | 0.9 | 9.4 |

## Highest TP-before-SL rate (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | above_vwap+above_pivot+macd_x_up | 0.0 | 0.8 | mid_1030_1300 | 14 | 0.23 | 13 | 1 | 0 | 92.9 | 92.9 | 13.0 | 3.6 | 0.3 | 7.5 |
| LONG | adi_up+above_pivot+macd_x_up | 0.0 | 0.8 | mid_1030_1300 | 14 | 0.23 | 13 | 1 | 0 | 92.9 | 92.9 | 13.0 | 3.6 | 0.3 | 6.8 |
| LONG | above_vwap+above_pivot+macd_x_up | 0.5 | 0.8 | mid_1030_1300 | 13 | 0.22 | 12 | 1 | 0 | 92.3 | 92.3 | 12.0 | 3.3 | 0.3 | 7.3 |
| LONG | adi_up+above_pivot+macd_x_up | 0.5 | 0.8 | mid_1030_1300 | 13 | 0.22 | 12 | 1 | 0 | 92.3 | 92.3 | 12.0 | 3.3 | 0.3 | 6.5 |
| LONG | above_pivot+macd_x_up+cvd_up | 0.0 | 0.8 | mid_1030_1300 | 12 | 0.2 | 11 | 1 | 0 | 91.7 | 91.7 | 11.0 | 3.0 | 0.3 | 6.7 |
| LONG | above_pivot+macd_x_up+cvd_up | 0.5 | 0.8 | mid_1030_1300 | 11 | 0.18 | 10 | 1 | 0 | 90.9 | 90.9 | 10.0 | 2.7 | 0.3 | 6.4 |
| LONG | above_pivot+macd_x_up | 0.0 | 0.8 | mid_1030_1300 | 17 | 0.28 | 15 | 2 | 0 | 88.2 | 88.2 | 7.5 | 3.9 | 0.3 | 7.9 |
| LONG | above_pivot+macd_x_up | 0.5 | 0.8 | mid_1030_1300 | 16 | 0.27 | 14 | 2 | 0 | 87.5 | 87.5 | 7.0 | 3.6 | 0.3 | 7.8 |
| LONG | adi_up+strong_close+vwap_lo_bounce | 0.8 | 1.2 | am_0845_1130 | 12 | 0.2 | 10 | 2 | 0 | 83.3 | 83.3 | 5.0 | 2.4 | 0.3 | 6.2 |
| LONG | above_pivot+macd_x_up+strong_close | 0.0 | 0.8 | mid_1030_1300 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 8.2 |
| LONG | above_pivot+strong_close+mom_ignite_up | 0.0 | 1.2 | pm_1130_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 7.3 |
| LONG | above_pivot+macd_x_up+strong_close | 0.5 | 0.8 | mid_1030_1300 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 8.2 |
| LONG | above_pivot+strong_close+mom_ignite_up | 0.5 | 1.2 | pm_1130_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 7.3 |
| SHORT | adi_dn+orb_break_dn | 0.8 | 0.8 | pm_1130_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 8.2 |
| LONG | above_vwap+above_pivot+macd_x_up | 0.0 | 0.8 | pm_1130_1400 | 16 | 0.27 | 13 | 3 | 0 | 81.2 | 81.2 | 4.33 | 3.0 | 0.9 | 9.4 |


## ITERATION 2 — greedy precision ensemble (2026-07-15 15:50 CST)

_421 composites unioned (each ≥70% strict / ≥85% tp-before-sl on its own); book constrained to ≥75% strict win-rate._

- **trades:** 49 (0.82/day, 29/60 days covered)
- **strict win-rate:** 87.8%  ·  **tp-before-sl:** 87.8%
- **profit factor:** 7.17  ·  **net:** 11.1%  ·  **maxDD:** 0.3%
- **avg hold:** 6.9 min

Configs (see results/ensemble.csv):

  - `LONG:above_vwap+above_pivot+macd_x_up|nk0.0|vm0.8|mid_1030_1300` — 92.9% on 14 trades
  - `LONG:adi_up+above_pivot+macd_x_up|nk0.0|vm0.8|mid_1030_1300` — 92.9% on 14 trades
  - `LONG:above_vwap+above_pivot+macd_x_up|nk0.5|vm0.8|mid_1030_1300` — 92.3% on 13 trades
  - `LONG:adi_up+above_pivot+macd_x_up|nk0.5|vm0.8|mid_1030_1300` — 92.3% on 13 trades
  - `LONG:above_vwap+adi_up+above_pivot+macd_x_up|nk0.0|vm0.8|mid_1030_1300` — 92.3% on 13 trades
  - `LONG:above_pivot+macd_x_up+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 91.7% on 12 trades
  - `LONG:above_vwap+adi_up+above_pivot+macd_x_up|nk0.5|vm0.8|mid_1030_1300` — 91.7% on 12 trades
  - `LONG:above_vwap+above_pivot+macd_x_up+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 91.7% on 12 trades
  - `LONG:adi_up+above_pivot+macd_x_up+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 91.7% on 12 trades
  - `LONG:above_pivot+macd_x_up+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 90.9% on 11 trades
  - `LONG:above_vwap+above_pivot+macd_x_up+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 90.9% on 11 trades
  - `LONG:adi_up+above_pivot+macd_x_up+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 90.9% on 11 trades
  - `LONG:above_vwap+above_pivot+macd_x_up+strong_close|nk0.0|vm0.8|mid_1030_1300` — 88.9% on 9 trades
  - `LONG:above_vwap+above_pivot+macd_x_up+strong_close|nk0.5|vm0.8|mid_1030_1300` — 88.9% on 9 trades
  - `LONG:above_pivot+macd_x_up|nk0.0|vm0.8|mid_1030_1300` — 88.2% on 17 trades
  - `LONG:above_pivot+macd_x_up|nk0.5|vm0.8|mid_1030_1300` — 87.5% on 16 trades
  - `LONG:above_vwap+above_pivot+mom_ignite_up|nk0.0|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+mom_ignite_up|nk0.5|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+macd_x_up+hist_turn_up|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+macd_x_up+hist_turn_up|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+macd_x_up+hist_turn_up|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+cvd_up+mom_ignite_up|nk0.0|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+cvd_up+mom_ignite_up|nk0.5|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+cvd_up_v+mom_ignite_up|nk0.0|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+cvd_up_v+mom_ignite_up|nk0.0|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+cvd_up_v+mom_ignite_up|nk0.5|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+cvd_up_v+mom_ignite_up|nk0.5|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+adi_up+above_pivot+mom_ignite_up|nk0.0|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+adi_up+above_pivot+mom_ignite_up|nk0.5|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+macd_x_up+hist_turn_up|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+macd_x_up+hist_turn_up|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+macd_x_up+hist_turn_up|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+strong_close+mom_ignite_up|nk0.0|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+strong_close+mom_ignite_up|nk0.5|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+cvd_up+mom_ignite_up|nk0.0|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+cvd_up+mom_ignite_up|nk0.5|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+cvd_up_v+mom_ignite_up|nk0.0|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+cvd_up_v+mom_ignite_up|nk0.0|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+cvd_up_v+mom_ignite_up|nk0.5|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_vwap+above_pivot+cvd_up_v+mom_ignite_up|nk0.5|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:adi_up+above_pivot+macd_x_up+strong_close|nk0.0|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `LONG:adi_up+above_pivot+macd_x_up+strong_close|nk0.5|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `LONG:adi_up+above_pivot+cvd_up+mom_ignite_up|nk0.0|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:adi_up+above_pivot+cvd_up+mom_ignite_up|nk0.5|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:adi_up+above_pivot+cvd_up_v+mom_ignite_up|nk0.0|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:adi_up+above_pivot+cvd_up_v+mom_ignite_up|nk0.0|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:adi_up+above_pivot+cvd_up_v+mom_ignite_up|nk0.5|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:adi_up+above_pivot+cvd_up_v+mom_ignite_up|nk0.5|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+macd_x_up+hist_turn_up+strong_close|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+macd_x_up+hist_turn_up+strong_close|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+macd_x_up+hist_turn_up+strong_close|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+strong_close+cvd_up+mom_ignite_up|nk0.0|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+strong_close+cvd_up+mom_ignite_up|nk0.5|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+strong_close+cvd_up_v+mom_ignite_up|nk0.0|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+strong_close+cvd_up_v+mom_ignite_up|nk0.0|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+strong_close+cvd_up_v+mom_ignite_up|nk0.5|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+strong_close+cvd_up_v+mom_ignite_up|nk0.5|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+cvd_up+cvd_up_v+mom_ignite_up|nk0.0|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+cvd_up+cvd_up_v+mom_ignite_up|nk0.0|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+cvd_up+cvd_up_v+mom_ignite_up|nk0.5|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+cvd_up+cvd_up_v+mom_ignite_up|nk0.5|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn|nk0.8|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn|nk0.0|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn|nk0.0|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn|nk0.5|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn|nk0.5|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn|nk0.8|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn|nk0.8|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn|nk0.0|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn|nk0.0|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn|nk0.5|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn|nk0.5|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn|nk0.8|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn|nk0.8|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+delta_dump+hist_turn_dn|nk0.0|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+delta_dump+hist_turn_dn|nk0.0|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+delta_dump+hist_turn_dn|nk0.5|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+delta_dump+hist_turn_dn|nk0.5|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+delta_dump+hist_turn_dn|nk0.8|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+delta_dump+hist_turn_dn|nk0.8|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+below_pivot+hist_turn_dn|nk0.0|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+below_pivot+hist_turn_dn|nk0.0|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+below_pivot+hist_turn_dn|nk0.5|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+below_pivot+hist_turn_dn|nk0.5|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+below_pivot+hist_turn_dn|nk0.8|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+below_pivot+hist_turn_dn|nk0.8|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+delta_dump+below_pivot+hist_turn_dn|nk0.0|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+delta_dump+below_pivot+hist_turn_dn|nk0.0|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+delta_dump+below_pivot+hist_turn_dn|nk0.5|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+delta_dump+below_pivot+hist_turn_dn|nk0.5|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+delta_dump+below_pivot+hist_turn_dn|nk0.8|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+delta_dump+below_pivot+hist_turn_dn|nk0.8|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+below_pivot+hist_turn_dn+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+below_pivot+hist_turn_dn+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+below_pivot+hist_turn_dn+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+below_pivot+hist_turn_dn+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+below_pivot+hist_turn_dn+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:adi_dn+below_pivot+hist_turn_dn+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 87.5% on 8 trades
  - `LONG:above_pivot+macd_x_up_neg|nk0.0|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+macd_x_up_neg|nk0.5|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+above_pivot+mom_ignite_up|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:adi_up+macd_x_up+hist_turn_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+macd_x_up+macd_x_up_neg|nk0.0|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+macd_x_up+macd_x_up_neg|nk0.5|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+cvd_up+mom_ignite_up|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+cvd_up_v+mom_ignite_up|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+cvd_up_v+mom_ignite_up|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:macd_x_up+hist_turn_up+cvd_up|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:macd_x_up+hist_turn_up+cvd_up|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:macd_x_up+hist_turn_up+cvd_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+above_pivot+mom_ignite_up|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+above_pivot+strong_close+mom_ignite_up|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+above_pivot+cvd_up+mom_ignite_up|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+above_pivot+cvd_up_v+mom_ignite_up|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+above_pivot+cvd_up_v+mom_ignite_up|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+macd_x_up+hist_turn_up+cvd_up|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+macd_x_up+hist_turn_up+cvd_up|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+macd_x_up+hist_turn_up+cvd_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:adi_up+above_pivot+cvd_up+mom_ignite_up|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:adi_up+above_pivot+cvd_up_v+mom_ignite_up|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:adi_up+above_pivot+cvd_up_v+mom_ignite_up|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:adi_up+macd_x_up+hist_turn_up+strong_close|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+macd_x_up+strong_close+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_pivot+macd_x_up+strong_close+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_pivot+strong_close+cvd_up+mom_ignite_up|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+strong_close+cvd_up_v+mom_ignite_up|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+strong_close+cvd_up_v+mom_ignite_up|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+cvd_up+cvd_up_v+mom_ignite_up|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+cvd_up+cvd_up_v+mom_ignite_up|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:macd_x_up+hist_turn_up+strong_close+cvd_up|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:macd_x_up+hist_turn_up+strong_close+cvd_up|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:macd_x_up+hist_turn_up+strong_close+cvd_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+hist_turn_dn+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+weak_close+orb_break_dn|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+weak_close|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+weak_close|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+weak_close|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+weak_close|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+weak_close|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+weak_close|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+cvd_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+cvd_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+cvd_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+cvd_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+cvd_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+cvd_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+cvd_dn_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+cvd_dn_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+cvd_dn_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+cvd_dn_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+cvd_dn_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+delta_dump+hist_turn_dn+cvd_dn_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+weak_close+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+weak_close+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+weak_close+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+weak_close+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+weak_close+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+weak_close+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_vwap+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+cvd_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+cvd_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+cvd_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+cvd_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+cvd_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+cvd_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+cvd_dn_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+cvd_dn_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+cvd_dn_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+cvd_dn_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+cvd_dn_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+delta_dump+hist_turn_dn+cvd_dn_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+weak_close+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+weak_close+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+weak_close+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+weak_close+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+weak_close+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+weak_close+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v+cvd_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v+cvd_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v+cvd_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v+cvd_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v+cvd_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v+cvd_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v+cvd_dn_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v+cvd_dn_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v+cvd_dn_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v+cvd_dn_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v+cvd_dn_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:adi_dn+hist_turn_dn+below_vwap_v+cvd_dn_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+weak_close|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+weak_close|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+weak_close|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+weak_close|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+weak_close|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+weak_close|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+cvd_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+cvd_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+cvd_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+cvd_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+cvd_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+cvd_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+cvd_dn_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+cvd_dn_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+cvd_dn_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+cvd_dn_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+cvd_dn_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+below_pivot+hist_turn_dn+cvd_dn_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+weak_close+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+weak_close+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+weak_close+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+weak_close+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+weak_close+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+weak_close+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v+cvd_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v+cvd_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v+cvd_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v+cvd_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v+cvd_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v+cvd_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v+cvd_dn_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v+cvd_dn_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v+cvd_dn_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v+cvd_dn_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v+cvd_dn_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+below_vwap_v+cvd_dn_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn+cvd_dn_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn+cvd_dn_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn+cvd_dn_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn+cvd_dn_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn+cvd_dn_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:delta_dump+hist_turn_dn+cvd_dn+cvd_dn_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+weak_close+rvol_thrust_dn|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+weak_close+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+weak_close+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+weak_close+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+weak_close+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+weak_close+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+weak_close+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+hist_turn_dn+rvol_thrust_dn+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+rvol_thrust_dn+below_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+rvol_thrust_dn+below_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+rvol_thrust_dn+below_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+rvol_thrust_dn+below_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+rvol_thrust_dn+below_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:hist_turn_dn+weak_close+rvol_thrust_dn+below_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 85.7% on 7 trades


## FINAL VERDICT — A-BOOK PRECISION UNION (COIN, +/-0.30% in 4h, entry >=08:45, TP by 14:35 CST, 60 sessions)

Goal (max A-book signals/day at near-perfect precision) — precision frontier reached: **0.17/day** is the max the >95% bar allows here.

| metric | value |
|--------|-------|
| resolved trades | 10 (10 target / 0 stop / 0 scratch) |
| **TP-before-SL** | **100.0%** (0 stops) |
| strict win-rate | 100.0% |
| **frequency** | **0.17/day** (9/60 sessions) |
| net | +3.0% |

### A-book families (live `A_BOOK` in coin_intraday_bot.py)

| # | direction | signal (blocks) | window | gate | trades | TP-b-SL | strict |
|---|-----------|-----------------|--------|------|--------|---------|--------|
| 1 | LONG | `mom_ignite_up+rsi_thrust_up` | full_0845_1400 | 0.0/0.8 | 5 | 100% | 100% |
| 2 | SHORT | `vwap_loss+hist_turn_dn+weak_close+cvd_dn_v` | am_0845_1130 | 0.0/0.8 | 5 | 100% | 100% |

**Read this before trading.** In-sample results on one ~3-month regime (~59 sessions). A-book families were selected because they rarely/never stopped in-sample — treat the TP-before-SL figure as an upper bound; the residual risk is the SCRATCH rate (time-stops at the 4h/14:35 deadline). Forward-validate before sizing. Desk session rule enforced in the engine: signals only after 08:45 CST, TP truncated at 14:35 CST.
