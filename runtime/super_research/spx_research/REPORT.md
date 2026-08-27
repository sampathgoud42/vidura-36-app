# SPX 5m Super-Signal research — 2026-07-15 14:55 CST

_60 sessions of 5-minute SPX (yfinance, incl. pre-market) · entries ['full_0845_1400', 'am_0845_1130', 'mid_1030_1300', 'pm_1130_1400'] (CST) · entry = next bar open · TP 0.3% ≤ 48 bars · SL 0.3% ≤ 48 bars · time-stop at bar 48 close · same-bar TP+SL = stop (conservative)._
_win_rate counts time-stop scratches as non-wins (strict); tp_before_sl ignores scratches._
_GEX/options-flow: no free historical feed — neutral hook only (see signals.GEX_NOTE)._

## Best configs with ≥2 signal/day (strict win-rate)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHORT | below_vwap+adi_dn+below_pivot | 0.0 | 0.8 | am_0845_1130 | 258 | 4.3 | 133 | 88 | 37 | 51.6 | 60.2 | 1.55 | 15.18 | 8.74 | 92.1 |
| SHORT | below_pivot+cvd_dn | 0.0 | 0.8 | am_0845_1130 | 260 | 4.33 | 134 | 90 | 36 | 51.5 | 59.8 | 1.49 | 13.86 | 9.13 | 92.4 |
| SHORT | below_vwap+below_pivot+cvd_dn | 0.0 | 0.8 | am_0845_1130 | 260 | 4.33 | 134 | 90 | 36 | 51.5 | 59.8 | 1.49 | 13.86 | 9.13 | 92.4 |
| SHORT | below_pivot+weak_close+cvd_dn | 0.0 | 0.8 | am_0845_1130 | 167 | 2.78 | 86 | 60 | 21 | 51.5 | 58.9 | 1.44 | 8.31 | 7.54 | 94.5 |
| SHORT | below_pivot+cvd_dn | 0.5 | 0.8 | am_0845_1130 | 255 | 4.25 | 131 | 89 | 35 | 51.4 | 59.5 | 1.47 | 13.2 | 9.13 | 91.9 |
| SHORT | below_vwap+below_pivot+cvd_dn | 0.5 | 0.8 | am_0845_1130 | 255 | 4.25 | 131 | 89 | 35 | 51.4 | 59.5 | 1.47 | 13.2 | 9.13 | 91.9 |
| SHORT | below_vwap+adi_dn+below_pivot | 0.5 | 0.8 | am_0845_1130 | 252 | 4.2 | 129 | 87 | 36 | 51.2 | 59.7 | 1.52 | 14.22 | 8.74 | 91.2 |
| SHORT | below_pivot+weak_close+cvd_dn | 0.5 | 0.8 | am_0845_1130 | 164 | 2.73 | 84 | 59 | 21 | 51.2 | 58.7 | 1.43 | 8.01 | 7.54 | 94.3 |
| SHORT | below_vwap+below_pivot | 0.0 | 0.8 | am_0845_1130 | 362 | 6.03 | 185 | 113 | 64 | 51.1 | 62.1 | 1.62 | 22.96 | 10.98 | 98.7 |
| SHORT | adi_dn+below_pivot+cvd_dn | 0.0 | 0.8 | am_0845_1130 | 221 | 3.68 | 112 | 81 | 28 | 50.7 | 58.0 | 1.42 | 10.61 | 8.43 | 90.0 |
| SHORT | below_vwap+below_pivot | 0.5 | 0.8 | am_0845_1130 | 352 | 5.87 | 178 | 112 | 62 | 50.6 | 61.4 | 1.58 | 21.23 | 11.16 | 98.0 |
| SHORT | adi_dn+below_pivot+cvd_dn | 0.5 | 0.8 | am_0845_1130 | 216 | 3.6 | 109 | 80 | 27 | 50.5 | 57.7 | 1.4 | 9.95 | 8.43 | 89.4 |
| SHORT | below_pivot+weak_close | 0.0 | 0.8 | am_0845_1130 | 248 | 4.13 | 125 | 90 | 33 | 50.4 | 58.1 | 1.4 | 11.19 | 8.36 | 92.1 |
| SHORT | adi_dn+below_pivot | 0.0 | 0.8 | am_0845_1130 | 311 | 5.18 | 156 | 115 | 40 | 50.2 | 57.6 | 1.4 | 14.22 | 12.46 | 88.1 |
| SHORT | below_pivot+weak_close | 0.5 | 0.8 | am_0845_1130 | 242 | 4.03 | 121 | 88 | 33 | 50.0 | 57.9 | 1.38 | 10.59 | 8.06 | 92.0 |

## Highest strict win-rate overall (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHORT | below_pivot+orb_break_dn | 0.5 | 0.8 | pm_1130_1400 | 22 | 0.37 | 16 | 5 | 1 | 72.7 | 76.2 | 2.94 | 3.17 | 0.6 | 65.0 |
| SHORT | below_pivot+weak_close+orb_break_dn | 0.5 | 0.8 | pm_1130_1400 | 20 | 0.33 | 14 | 5 | 1 | 70.0 | 73.7 | 2.58 | 2.57 | 0.6 | 62.2 |
| LONG | vwap_reclaim+vwap_lo_bounce+cvd_up_v | 0.0 | 0.8 | full_0845_1400 | 10 | 0.17 | 7 | 2 | 1 | 70.0 | 77.8 | 3.29 | 1.46 | 0.34 | 65.0 |
| LONG | adi_up+vwap_lo_bounce+cvd_up_v | 0.0 | 0.8 | full_0845_1400 | 10 | 0.17 | 7 | 3 | 0 | 70.0 | 70.0 | 2.33 | 1.2 | 0.6 | 41.5 |
| LONG | strong_close+vwap_lo_bounce+cvd_up_v | 0.0 | 0.8 | full_0845_1400 | 10 | 0.17 | 7 | 2 | 1 | 70.0 | 77.8 | 3.29 | 1.46 | 0.64 | 62.0 |
| LONG | vwap_reclaim_v+vwap_lo_bounce+cvd_up | 0.0 | 0.8 | full_0845_1400 | 10 | 0.17 | 7 | 2 | 1 | 70.0 | 77.8 | 3.29 | 1.46 | 0.34 | 65.0 |
| LONG | vwap_reclaim_v+vwap_lo_bounce+cvd_up_v | 0.0 | 0.8 | full_0845_1400 | 10 | 0.17 | 7 | 2 | 1 | 70.0 | 77.8 | 3.29 | 1.46 | 0.34 | 65.0 |
| LONG | above_pivot+above_vwap_v | 0.0 | 0.8 | pm_1130_1400 | 10 | 0.17 | 7 | 2 | 1 | 70.0 | 77.8 | 3.4 | 1.48 | 0.3 | 30.5 |
| LONG | above_vwap+above_pivot+above_vwap_v | 0.0 | 0.8 | pm_1130_1400 | 10 | 0.17 | 7 | 2 | 1 | 70.0 | 77.8 | 3.4 | 1.48 | 0.3 | 30.5 |
| LONG | vwap_reclaim+vwap_lo_bounce+cvd_up | 0.0 | 1.2 | full_0845_1400 | 10 | 0.17 | 7 | 2 | 1 | 70.0 | 77.8 | 3.29 | 1.46 | 0.34 | 65.0 |
| LONG | vwap_reclaim+vwap_lo_bounce+cvd_up_v | 0.0 | 1.2 | full_0845_1400 | 10 | 0.17 | 7 | 2 | 1 | 70.0 | 77.8 | 3.29 | 1.46 | 0.34 | 65.0 |
| LONG | adi_up+vwap_lo_bounce+cvd_up | 0.0 | 1.2 | full_0845_1400 | 10 | 0.17 | 7 | 3 | 0 | 70.0 | 70.0 | 2.33 | 1.2 | 0.6 | 41.5 |
| LONG | adi_up+vwap_lo_bounce+cvd_up_v | 0.0 | 1.2 | full_0845_1400 | 10 | 0.17 | 7 | 3 | 0 | 70.0 | 70.0 | 2.33 | 1.2 | 0.6 | 41.5 |
| LONG | strong_close+vwap_lo_bounce+cvd_up | 0.0 | 1.2 | full_0845_1400 | 10 | 0.17 | 7 | 2 | 1 | 70.0 | 77.8 | 3.29 | 1.46 | 0.64 | 62.0 |
| LONG | strong_close+vwap_lo_bounce+cvd_up_v | 0.0 | 1.2 | full_0845_1400 | 10 | 0.17 | 7 | 2 | 1 | 70.0 | 77.8 | 3.29 | 1.46 | 0.64 | 62.0 |

## Highest TP-before-SL rate (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHORT | r1_reject+weak_close+cvd_dn | 0.8 | 0.8 | full_0845_1400 | 19 | 0.32 | 10 | 1 | 8 | 52.6 | 90.9 | 3.21 | 2.14 | 0.89 | 108.7 |
| SHORT | r1_reject+weak_close+cvd_dn | 0.8 | 0.8 | am_0845_1130 | 16 | 0.27 | 10 | 1 | 5 | 62.5 | 90.9 | 3.75 | 2.28 | 0.83 | 112.5 |
| LONG | poc_reject_up+strong_close | 0.0 | 0.8 | pm_1130_1400 | 19 | 0.32 | 8 | 1 | 10 | 42.1 | 88.9 | 4.44 | 2.32 | 0.23 | 68.2 |
| LONG | poc_reject_up+strong_close | 0.5 | 0.8 | pm_1130_1400 | 18 | 0.3 | 8 | 1 | 9 | 44.4 | 88.9 | 4.22 | 2.17 | 0.23 | 64.7 |
| LONG | poc_reject_up+adi_up | 0.0 | 0.8 | mid_1030_1300 | 15 | 0.25 | 8 | 1 | 6 | 53.3 | 88.9 | 5.35 | 2.47 | 0.57 | 92.3 |
| LONG | poc_reject_up+adi_up | 0.5 | 0.8 | mid_1030_1300 | 13 | 0.22 | 7 | 1 | 5 | 53.8 | 87.5 | 4.55 | 2.02 | 0.57 | 90.8 |
| LONG | poc_reject_up+vwap_lo_bounce | 0.0 | 0.8 | full_0845_1400 | 11 | 0.18 | 7 | 1 | 3 | 63.6 | 87.5 | 5.15 | 1.77 | 0.3 | 77.7 |
| LONG | poc_reject_up+vwap_lo_bounce | 0.5 | 0.8 | full_0845_1400 | 11 | 0.18 | 7 | 1 | 3 | 63.6 | 87.5 | 5.15 | 1.77 | 0.3 | 77.7 |
| SHORT | hist_turn_dn+orb_break_dn | 0.8 | 0.8 | pm_1130_1400 | 10 | 0.17 | 7 | 1 | 2 | 70.0 | 87.5 | 3.64 | 1.52 | 0.3 | 65.5 |
| SHORT | hist_turn_dn+weak_close+orb_break_dn | 0.8 | 0.8 | pm_1130_1400 | 10 | 0.17 | 7 | 1 | 2 | 70.0 | 87.5 | 3.64 | 1.52 | 0.3 | 65.5 |
| SHORT | r1_reject+cvd_dn | 0.8 | 0.8 | full_0845_1400 | 24 | 0.4 | 12 | 2 | 10 | 50.0 | 85.7 | 2.72 | 2.35 | 0.95 | 109.0 |
| SHORT | below_vwap+r1_reject+cvd_dn | 0.8 | 0.8 | full_0845_1400 | 24 | 0.4 | 12 | 2 | 10 | 50.0 | 85.7 | 2.72 | 2.35 | 0.95 | 109.0 |
| SHORT | r1_reject+cvd_dn | 0.8 | 0.8 | am_0845_1130 | 19 | 0.32 | 12 | 2 | 5 | 63.2 | 85.7 | 3.28 | 2.58 | 0.83 | 107.4 |
| SHORT | below_vwap+r1_reject+cvd_dn | 0.8 | 0.8 | am_0845_1130 | 19 | 0.32 | 12 | 2 | 5 | 63.2 | 85.7 | 3.28 | 2.58 | 0.83 | 107.4 |
| SHORT | r1_reject+weak_close+cvd_dn | 0.0 | 0.8 | full_0845_1400 | 23 | 0.38 | 10 | 2 | 11 | 43.5 | 83.3 | 2.3 | 1.79 | 1.21 | 111.5 |


## ITERATION 2 — greedy precision ensemble (2026-07-15 15:00 CST)

_93 composites unioned (each ≥70% strict / ≥85% tp-before-sl on its own); book constrained to ≥75% strict win-rate._

- **trades:** 33 (0.55/day, 24/60 days covered)
- **strict win-rate:** 75.8%  ·  **tp-before-sl:** 92.6%
- **profit factor:** 6.96  ·  **net:** 6.51%  ·  **maxDD:** 0.3%
- **avg hold:** 77.3 min

Configs (see results/ensemble.csv):

  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up|nk0.0|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up|nk0.5|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up|nk0.8|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up_v|nk0.0|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up_v|nk0.0|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up_v|nk0.5|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up_v|nk0.5|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close+cvd_up|nk0.0|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close+cvd_up|nk0.5|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close+cvd_up|nk0.8|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close+cvd_up_v|nk0.0|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close+cvd_up_v|nk0.0|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close+cvd_up_v|nk0.5|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close+cvd_up_v|nk0.5|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up|nk0.0|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up|nk0.0|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up|nk0.5|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up|nk0.5|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.0|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.0|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.5|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.5|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v+cvd_up|nk0.0|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v+cvd_up|nk0.0|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v+cvd_up|nk0.5|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v+cvd_up|nk0.5|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v+cvd_up_v|nk0.0|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v+cvd_up_v|nk0.0|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v+cvd_up_v|nk0.5|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v+cvd_up_v|nk0.5|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:r1_reject+orb_break_dn|nk0.0|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:r1_reject+orb_break_dn|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `SHORT:r1_reject+orb_break_dn|nk0.5|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:r1_reject+orb_break_dn|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `SHORT:r1_reject+orb_break_dn|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:r1_reject+orb_break_dn|nk0.8|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `SHORT:below_vwap+r1_reject+orb_break_dn|nk0.0|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:below_vwap+r1_reject+orb_break_dn|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `SHORT:below_vwap+r1_reject+orb_break_dn|nk0.5|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:below_vwap+r1_reject+orb_break_dn|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `SHORT:below_vwap+r1_reject+orb_break_dn|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:below_vwap+r1_reject+orb_break_dn|nk0.8|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `SHORT:r1_reject+weak_close+orb_break_dn|nk0.0|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:r1_reject+weak_close+orb_break_dn|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `SHORT:r1_reject+weak_close+orb_break_dn|nk0.5|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:r1_reject+weak_close+orb_break_dn|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `SHORT:r1_reject+weak_close+orb_break_dn|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:r1_reject+weak_close+orb_break_dn|nk0.8|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `SHORT:below_vwap+r1_reject+weak_close+orb_break_dn|nk0.0|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:below_vwap+r1_reject+weak_close+orb_break_dn|nk0.0|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `SHORT:below_vwap+r1_reject+weak_close+orb_break_dn|nk0.5|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:below_vwap+r1_reject+weak_close+orb_break_dn|nk0.5|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `SHORT:below_vwap+r1_reject+weak_close+orb_break_dn|nk0.8|vm0.8|full_0845_1400` — 83.3% on 6 trades
  - `SHORT:below_vwap+r1_reject+weak_close+orb_break_dn|nk0.8|vm0.8|am_0845_1130` — 83.3% on 6 trades
  - `LONG:poc_reject_up+strong_close+vwap_lo_bounce|nk0.0|vm0.8|full_0845_1400` — 77.8% on 9 trades
  - `LONG:poc_reject_up+strong_close+vwap_lo_bounce|nk0.5|vm0.8|full_0845_1400` — 77.8% on 9 trades
  - `SHORT:below_pivot+hist_turn_dn+orb_break_dn|nk0.8|vm0.8|pm_1130_1400` — 77.8% on 9 trades
  - `SHORT:below_pivot+hist_turn_dn+weak_close+orb_break_dn|nk0.8|vm0.8|pm_1130_1400` — 77.8% on 9 trades
  - `LONG:poc_reject_up+strong_close+vwap_lo_bounce|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+vwap_lo_bounce+cvd_up|nk0.0|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+vwap_lo_bounce+cvd_up|nk0.5|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+vwap_lo_bounce+cvd_up|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+vwap_lo_bounce+cvd_up_v|nk0.0|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+vwap_lo_bounce+cvd_up_v|nk0.0|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+vwap_lo_bounce+cvd_up_v|nk0.5|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+vwap_lo_bounce+cvd_up_v|nk0.5|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+vwap_lo_bounce+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+vwap_lo_bounce+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+vwap_lo_bounce+cvd_up|nk0.0|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+vwap_lo_bounce+cvd_up|nk0.0|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+vwap_lo_bounce+cvd_up|nk0.5|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+vwap_lo_bounce+cvd_up|nk0.5|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+vwap_lo_bounce+cvd_up|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+vwap_lo_bounce+cvd_up|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+vwap_lo_bounce+cvd_up_v|nk0.0|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+vwap_lo_bounce+cvd_up_v|nk0.0|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+vwap_lo_bounce+cvd_up_v|nk0.5|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+vwap_lo_bounce+cvd_up_v|nk0.5|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+vwap_lo_bounce+cvd_up_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+vwap_lo_bounce+cvd_up_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:below_vwap+below_pivot+hist_turn_dn+orb_break_dn|nk0.8|vm0.8|pm_1130_1400` — 75.0% on 8 trades


## FINAL VERDICT — A-BOOK PRECISION UNION (SPX, +/-0.30% in 4h, entry >=08:45, TP by 14:35 CST, 60 sessions)

Goal (max A-book signals/day at near-perfect precision) — precision frontier reached: **0.47/day** is the max the >95% bar allows here.

| metric | value |
|--------|-------|
| resolved trades | 28 (21 target / 0 stop / 7 scratch) |
| **TP-before-SL** | **100.0%** (0 stops) |
| strict win-rate | 75.0% |
| **frequency** | **0.47/day** (21/60 sessions) |
| net | +6.3% |

### A-book families (live `A_BOOK` in spx_intraday_bot.py)

| # | direction | signal (blocks) | window | gate | trades | TP-b-SL | strict |
|---|-----------|-----------------|--------|------|--------|---------|--------|
| 1 | LONG | `poc_reject_up+strong_close+vwap_lo_bounce` | full_0845_1400 | 0.0/0.8 | 9 | 100% | 78% |
| 2 | LONG | `vwap_reclaim+orb_break_up` | full_0845_1400 | 0.0/1.2 | 7 | 100% | 71% |
| 3 | LONG | `above_vwap+poc_reject_up` | mid_1030_1300 | 0.0/0.8 | 7 | 100% | 71% |
| 4 | SHORT | `r1_reject+orb_break_dn` | full_0845_1400 | 0.0/0.8 | 6 | 100% | 83% |
| 5 | LONG | `vwap_reclaim+adi_up+above_pivot` | full_0845_1400 | 0.0/1.2 | 7 | 100% | 71% |

**Read this before trading.** In-sample results on one ~3-month regime (~59 sessions). A-book families were selected because they rarely/never stopped in-sample — treat the TP-before-SL figure as an upper bound; the residual risk is the SCRATCH rate (time-stops at the 4h/14:35 deadline). Forward-validate before sizing. Desk session rule enforced in the engine: signals only after 08:45 CST, TP truncated at 14:35 CST.
