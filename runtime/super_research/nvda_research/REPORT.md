# NVDA 5m Super-Signal research — 2026-07-15 15:11 CST

_60 sessions of 5-minute NVDA (yfinance, incl. pre-market) · entries ['full_0845_1400', 'am_0845_1130', 'mid_1030_1300', 'pm_1130_1400'] (CST) · entry = next bar open · TP 0.3% ≤ 48 bars · SL 0.3% ≤ 48 bars · time-stop at bar 48 close · same-bar TP+SL = stop (conservative)._
_win_rate counts time-stop scratches as non-wins (strict); tp_before_sl ignores scratches._
_GEX/options-flow: no free historical feed — neutral hook only (see signals.GEX_NOTE)._

## Best configs with ≥2 signal/day (strict win-rate)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | above_vwap+above_pivot+strong_close | 0.8 | 0.8 | mid_1030_1300 | 133 | 2.22 | 80 | 53 | 0 | 60.2 | 60.2 | 1.51 | 8.1 | 3.3 | 23.6 |
| LONG | strong_close+cvd_up | 0.0 | 0.8 | mid_1030_1300 | 238 | 3.97 | 142 | 95 | 1 | 59.7 | 59.9 | 1.48 | 13.91 | 6.3 | 22.7 |
| LONG | above_vwap+strong_close+cvd_up | 0.0 | 0.8 | mid_1030_1300 | 238 | 3.97 | 142 | 95 | 1 | 59.7 | 59.9 | 1.48 | 13.91 | 6.3 | 22.7 |
| LONG | above_vwap+strong_close | 0.8 | 0.8 | mid_1030_1300 | 183 | 3.05 | 109 | 74 | 0 | 59.6 | 59.6 | 1.47 | 10.5 | 3.6 | 22.6 |
| LONG | adi_up+strong_close+cvd_up | 0.0 | 0.8 | mid_1030_1300 | 220 | 3.67 | 130 | 89 | 1 | 59.1 | 59.4 | 1.45 | 12.11 | 6.6 | 21.9 |
| LONG | above_vwap+adi_up+above_pivot | 0.8 | 0.8 | mid_1030_1300 | 159 | 2.65 | 94 | 65 | 0 | 59.1 | 59.1 | 1.45 | 8.7 | 4.2 | 21.5 |
| LONG | above_vwap+above_pivot | 0.8 | 0.8 | mid_1030_1300 | 229 | 3.82 | 135 | 92 | 2 | 59.0 | 59.5 | 1.45 | 12.65 | 4.2 | 24.3 |
| SHORT | below_vwap+cvd_dn_v | 0.0 | 0.8 | pm_1130_1400 | 124 | 2.07 | 73 | 47 | 4 | 58.9 | 60.8 | 1.55 | 7.91 | 2.28 | 23.3 |
| SHORT | cvd_dn+cvd_dn_v | 0.0 | 0.8 | pm_1130_1400 | 124 | 2.07 | 73 | 47 | 4 | 58.9 | 60.8 | 1.55 | 7.91 | 2.28 | 23.3 |
| SHORT | below_vwap+cvd_dn+cvd_dn_v | 0.0 | 0.8 | pm_1130_1400 | 124 | 2.07 | 73 | 47 | 4 | 58.9 | 60.8 | 1.55 | 7.91 | 2.28 | 23.3 |
| SHORT | below_vwap+cvd_dn | 0.0 | 1.2 | pm_1130_1400 | 124 | 2.07 | 73 | 47 | 4 | 58.9 | 60.8 | 1.55 | 7.91 | 2.28 | 23.3 |
| SHORT | below_vwap+cvd_dn_v | 0.0 | 1.2 | pm_1130_1400 | 124 | 2.07 | 73 | 47 | 4 | 58.9 | 60.8 | 1.55 | 7.91 | 2.28 | 23.3 |
| SHORT | cvd_dn+cvd_dn_v | 0.0 | 1.2 | pm_1130_1400 | 124 | 2.07 | 73 | 47 | 4 | 58.9 | 60.8 | 1.55 | 7.91 | 2.28 | 23.3 |
| SHORT | below_vwap+cvd_dn+cvd_dn_v | 0.0 | 1.2 | pm_1130_1400 | 124 | 2.07 | 73 | 47 | 4 | 58.9 | 60.8 | 1.55 | 7.91 | 2.28 | 23.3 |
| SHORT | below_vwap+cvd_dn_v | 0.5 | 0.8 | pm_1130_1400 | 124 | 2.07 | 73 | 47 | 4 | 58.9 | 60.8 | 1.55 | 7.91 | 2.28 | 23.3 |

## Highest strict win-rate overall (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHORT | adi_dn+below_pivot+rsi_thrust_dn | 0.0 | 0.8 | pm_1130_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 26.0 |
| SHORT | adi_dn+below_pivot+rsi_thrust_dn | 0.0 | 1.2 | pm_1130_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 26.0 |
| SHORT | adi_dn+below_pivot+rsi_thrust_dn | 0.5 | 0.8 | pm_1130_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 26.0 |
| SHORT | adi_dn+below_pivot+rsi_thrust_dn | 0.5 | 1.2 | pm_1130_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 26.0 |
| SHORT | adi_dn+below_pivot+rsi_thrust_dn | 0.8 | 0.8 | pm_1130_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 26.0 |
| SHORT | adi_dn+below_pivot+rsi_thrust_dn | 0.8 | 1.2 | pm_1130_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 26.0 |
| SHORT | below_pivot+macd_x_dn+cvd_dn_v | 0.8 | 0.8 | pm_1130_1400 | 13 | 0.22 | 11 | 1 | 1 | 84.6 | 91.7 | 11.73 | 3.22 | 0.3 | 19.2 |
| SHORT | below_vwap+below_pivot+macd_x_dn | 0.8 | 1.2 | pm_1130_1400 | 13 | 0.22 | 11 | 1 | 1 | 84.6 | 91.7 | 11.73 | 3.22 | 0.3 | 19.2 |
| SHORT | adi_dn+below_pivot+macd_x_dn | 0.8 | 1.2 | pm_1130_1400 | 13 | 0.22 | 11 | 1 | 1 | 84.6 | 91.7 | 11.73 | 3.22 | 0.3 | 19.2 |
| SHORT | below_pivot+macd_x_dn+cvd_dn | 0.8 | 1.2 | pm_1130_1400 | 13 | 0.22 | 11 | 1 | 1 | 84.6 | 91.7 | 11.73 | 3.22 | 0.3 | 19.2 |
| SHORT | below_pivot+macd_x_dn+cvd_dn_v | 0.8 | 1.2 | pm_1130_1400 | 13 | 0.22 | 11 | 1 | 1 | 84.6 | 91.7 | 11.73 | 3.22 | 0.3 | 19.2 |
| SHORT | below_vwap+orb_break_dn | 0.0 | 0.8 | pm_1130_1400 | 12 | 0.2 | 10 | 2 | 0 | 83.3 | 83.3 | 5.0 | 2.4 | 0.3 | 19.2 |
| SHORT | below_pivot+rsi_thrust_dn | 0.0 | 0.8 | pm_1130_1400 | 12 | 0.2 | 10 | 2 | 0 | 83.3 | 83.3 | 5.0 | 2.4 | 0.3 | 23.8 |
| SHORT | weak_close+orb_break_dn | 0.0 | 0.8 | pm_1130_1400 | 12 | 0.2 | 10 | 2 | 0 | 83.3 | 83.3 | 5.0 | 2.4 | 0.3 | 19.2 |
| SHORT | below_vwap+weak_close+orb_break_dn | 0.0 | 0.8 | pm_1130_1400 | 12 | 0.2 | 10 | 2 | 0 | 83.3 | 83.3 | 5.0 | 2.4 | 0.3 | 19.2 |

## Highest TP-before-SL rate (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHORT | below_pivot+macd_x_dn+cvd_dn_v | 0.8 | 0.8 | pm_1130_1400 | 13 | 0.22 | 11 | 1 | 1 | 84.6 | 91.7 | 11.73 | 3.22 | 0.3 | 19.2 |
| SHORT | below_vwap+below_pivot+macd_x_dn | 0.8 | 1.2 | pm_1130_1400 | 13 | 0.22 | 11 | 1 | 1 | 84.6 | 91.7 | 11.73 | 3.22 | 0.3 | 19.2 |
| SHORT | adi_dn+below_pivot+macd_x_dn | 0.8 | 1.2 | pm_1130_1400 | 13 | 0.22 | 11 | 1 | 1 | 84.6 | 91.7 | 11.73 | 3.22 | 0.3 | 19.2 |
| SHORT | below_pivot+macd_x_dn+cvd_dn | 0.8 | 1.2 | pm_1130_1400 | 13 | 0.22 | 11 | 1 | 1 | 84.6 | 91.7 | 11.73 | 3.22 | 0.3 | 19.2 |
| SHORT | below_pivot+macd_x_dn+cvd_dn_v | 0.8 | 1.2 | pm_1130_1400 | 13 | 0.22 | 11 | 1 | 1 | 84.6 | 91.7 | 11.73 | 3.22 | 0.3 | 19.2 |
| SHORT | adi_dn+below_pivot+rsi_thrust_dn | 0.0 | 0.8 | pm_1130_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 26.0 |
| SHORT | adi_dn+below_pivot+rsi_thrust_dn | 0.0 | 1.2 | pm_1130_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 26.0 |
| SHORT | adi_dn+below_pivot+rsi_thrust_dn | 0.5 | 0.8 | pm_1130_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 26.0 |
| SHORT | adi_dn+below_pivot+rsi_thrust_dn | 0.5 | 1.2 | pm_1130_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 26.0 |
| SHORT | adi_dn+below_pivot+rsi_thrust_dn | 0.8 | 0.8 | pm_1130_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 26.0 |
| SHORT | adi_dn+below_pivot+rsi_thrust_dn | 0.8 | 1.2 | pm_1130_1400 | 10 | 0.17 | 9 | 1 | 0 | 90.0 | 90.0 | 9.0 | 2.4 | 0.3 | 26.0 |
| SHORT | below_pivot+macd_x_dn+weak_close | 0.8 | 1.2 | pm_1130_1400 | 10 | 0.17 | 8 | 1 | 1 | 80.0 | 88.9 | 8.73 | 2.32 | 0.3 | 21.5 |
| SHORT | below_pivot+macd_x_dn+cvd_dn_v | 0.8 | 0.8 | full_0845_1400 | 16 | 0.27 | 13 | 2 | 1 | 81.2 | 86.7 | 6.86 | 3.52 | 0.3 | 17.2 |
| SHORT | below_pivot+macd_x_dn+cvd_dn_v | 0.8 | 1.2 | full_0845_1400 | 16 | 0.27 | 13 | 2 | 1 | 81.2 | 86.7 | 6.86 | 3.52 | 0.3 | 17.2 |
| SHORT | below_pivot+macd_x_dn+cvd_dn_v | 0.0 | 0.8 | pm_1130_1400 | 14 | 0.23 | 11 | 2 | 1 | 78.6 | 84.6 | 5.86 | 2.92 | 0.3 | 18.2 |


## ITERATION 2 — greedy precision ensemble (2026-07-15 15:20 CST)

_318 composites unioned (each ≥70% strict / ≥85% tp-before-sl on its own); book constrained to ≥75% strict win-rate._

- **trades:** 60 (1.0/day, 31/60 days covered)
- **strict win-rate:** 83.3%  ·  **tp-before-sl:** 84.7%
- **profit factor:** 5.64  ·  **net:** 12.52%  ·  **maxDD:** 0.3%
- **avg hold:** 15.8 min

Configs (see results/ensemble.csv):

  - `SHORT:below_pivot+orb_break_dn|nk0.0|vm1.2|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+orb_break_dn|nk0.5|vm1.2|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+orb_break_dn|nk0.8|vm1.2|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+orb_break_dn_v|nk0.0|vm0.8|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+orb_break_dn_v|nk0.0|vm1.2|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+orb_break_dn_v|nk0.5|vm0.8|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+orb_break_dn_v|nk0.5|vm1.2|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+orb_break_dn_v|nk0.8|vm0.8|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+orb_break_dn_v|nk0.8|vm1.2|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v|nk0.0|vm0.8|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v|nk0.0|vm1.2|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v|nk0.5|vm0.8|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v|nk0.5|vm1.2|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v|nk0.8|vm0.8|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v|nk0.8|vm1.2|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+orb_break_dn+orb_break_dn_v|nk0.0|vm0.8|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+orb_break_dn+orb_break_dn_v|nk0.0|vm1.2|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+orb_break_dn+orb_break_dn_v|nk0.5|vm0.8|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+orb_break_dn+orb_break_dn_v|nk0.5|vm1.2|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+orb_break_dn+orb_break_dn_v|nk0.8|vm0.8|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+orb_break_dn+orb_break_dn_v|nk0.8|vm1.2|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+weak_close+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+weak_close+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+weak_close+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+weak_close+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+weak_close+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+weak_close+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 100.0% on 6 trades
  - `SHORT:adi_dn+below_pivot+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 90.0% on 10 trades
  - `SHORT:adi_dn+below_pivot+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 90.0% on 10 trades
  - `SHORT:adi_dn+below_pivot+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 90.0% on 10 trades
  - `SHORT:adi_dn+below_pivot+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 90.0% on 10 trades
  - `SHORT:adi_dn+below_pivot+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 90.0% on 10 trades
  - `SHORT:adi_dn+below_pivot+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 90.0% on 10 trades
  - `SHORT:macd_x_dn+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:macd_x_dn+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:macd_x_dn+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:macd_x_dn+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:macd_x_dn+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:macd_x_dn+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+macd_x_dn+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+macd_x_dn+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+macd_x_dn+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+macd_x_dn+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+macd_x_dn+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+macd_x_dn+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_pivot+weak_close+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:below_pivot+weak_close+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:below_pivot+weak_close+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:below_pivot+weak_close+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:below_pivot+weak_close+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:below_pivot+weak_close+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:macd_x_dn+weak_close+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:macd_x_dn+weak_close+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:macd_x_dn+weak_close+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:macd_x_dn+weak_close+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:macd_x_dn+weak_close+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:macd_x_dn+weak_close+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:weak_close+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+cvd_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+adi_dn+below_pivot+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+adi_dn+below_pivot+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+adi_dn+below_pivot+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+adi_dn+below_pivot+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+adi_dn+below_pivot+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+adi_dn+below_pivot+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+weak_close+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+weak_close+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+weak_close+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+weak_close+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+weak_close+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+weak_close+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+cvd_dn+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+cvd_dn+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+cvd_dn+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+cvd_dn+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+cvd_dn+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+cvd_dn+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+below_pivot+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+macd_x_dn+weak_close+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+macd_x_dn+weak_close+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+macd_x_dn+weak_close+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+macd_x_dn+weak_close+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+macd_x_dn+weak_close+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+macd_x_dn+weak_close+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:adi_dn+orb_break_dn+cvd_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:weak_close+orb_break_dn+cvd_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `LONG:poc_reject_up+above_pivot|nk0.8|vm0.8|mid_1030_1300` — 87.5% on 8 trades
  - `SHORT:orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:adi_dn+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:below_pivot+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:orb_break_dn+cvd_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+macd_x_dn+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+macd_x_dn+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+macd_x_dn+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+macd_x_dn+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+macd_x_dn+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+macd_x_dn+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:below_vwap+below_pivot+weak_close+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+below_pivot+weak_close+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+below_pivot+weak_close+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+below_pivot+weak_close+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+below_pivot+weak_close+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+below_pivot+weak_close+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+below_pivot+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+weak_close+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+weak_close+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+weak_close+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+weak_close+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+weak_close+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+weak_close+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:adi_dn+below_pivot+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:adi_dn+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:adi_dn+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:adi_dn+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:adi_dn+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:adi_dn+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:adi_dn+macd_x_dn+cvd_dn+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:adi_dn+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:adi_dn+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:adi_dn+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:adi_dn+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:adi_dn+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:adi_dn+macd_x_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:adi_dn+orb_break_dn+cvd_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:below_pivot+weak_close+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_pivot+weak_close+cvd_dn+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_pivot+weak_close+cvd_dn+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_pivot+weak_close+cvd_dn+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_pivot+weak_close+cvd_dn+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_pivot+weak_close+cvd_dn+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_pivot+weak_close+cvd_dn+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_pivot+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_pivot+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_pivot+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_pivot+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_pivot+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_pivot+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_pivot+orb_break_dn+cvd_dn+mom_ignite_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+weak_close+cvd_dn+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+weak_close+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:macd_x_dn+cvd_dn+cvd_dn_v+rsi_thrust_dn|nk0.8|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+cvd_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:poc_reject_up+adi_up+above_pivot|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:poc_reject_up+adi_up+above_pivot|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:poc_reject_up+adi_up+above_pivot|nk0.8|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+ylow_reclaim+strong_close|nk0.0|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+ylow_reclaim+strong_close|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+hist_turn_up+vwap_lo_bounce|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `LONG:adi_up+hist_turn_up+strong_close+vwap_lo_bounce|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:macd_x_dn+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:macd_x_dn+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:macd_x_dn+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:macd_x_dn+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:macd_x_dn+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:macd_x_dn+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn_pos|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+macd_x_dn+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+macd_x_dn+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+macd_x_dn+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+macd_x_dn+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+macd_x_dn+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+macd_x_dn+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:below_pivot+macd_x_dn_pos+weak_close|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:below_pivot+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:macd_x_dn+weak_close+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:macd_x_dn+weak_close+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:macd_x_dn+weak_close+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:macd_x_dn+weak_close+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:macd_x_dn+weak_close+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:macd_x_dn+weak_close+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+below_pivot+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+macd_x_dn_pos|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn_pos+weak_close|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+below_pivot+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:adi_dn+macd_x_dn+weak_close+rsi_thrust_dn|nk0.0|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+macd_x_dn+weak_close+rsi_thrust_dn|nk0.0|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+macd_x_dn+weak_close+rsi_thrust_dn|nk0.5|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+macd_x_dn+weak_close+rsi_thrust_dn|nk0.5|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+macd_x_dn+weak_close+rsi_thrust_dn|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+macd_x_dn+weak_close+rsi_thrust_dn|nk0.8|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:below_pivot+macd_x_dn+macd_x_dn_pos+weak_close|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:below_pivot+weak_close+orb_break_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_pivot+orb_break_dn+cvd_dn+mom_ignite_dn|nk0.8|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn|nk0.8|vm1.2|pm_1130_1400` — 84.6% on 13 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn|nk0.8|vm1.2|pm_1130_1400` — 84.6% on 13 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn|nk0.8|vm1.2|pm_1130_1400` — 84.6% on 13 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn_v|nk0.8|vm0.8|pm_1130_1400` — 84.6% on 13 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn_v|nk0.8|vm1.2|pm_1130_1400` — 84.6% on 13 trades
  - `SHORT:below_vwap+adi_dn+below_pivot+macd_x_dn|nk0.8|vm1.2|pm_1130_1400` — 84.6% on 13 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn+cvd_dn|nk0.8|vm1.2|pm_1130_1400` — 84.6% on 13 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn+cvd_dn_v|nk0.8|vm0.8|pm_1130_1400` — 84.6% on 13 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn+cvd_dn_v|nk0.8|vm1.2|pm_1130_1400` — 84.6% on 13 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+cvd_dn|nk0.8|vm1.2|pm_1130_1400` — 84.6% on 13 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+cvd_dn_v|nk0.8|vm0.8|pm_1130_1400` — 84.6% on 13 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+cvd_dn_v|nk0.8|vm1.2|pm_1130_1400` — 84.6% on 13 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn+cvd_dn_v|nk0.8|vm0.8|pm_1130_1400` — 84.6% on 13 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn+cvd_dn_v|nk0.8|vm1.2|pm_1130_1400` — 84.6% on 13 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 81.2% on 16 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 81.2% on 16 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 81.2% on 16 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 81.2% on 16 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 81.2% on 16 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 81.2% on 16 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 81.2% on 16 trades
  - `SHORT:below_pivot+macd_x_dn+cvd_dn+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 81.2% on 16 trades
  - `SHORT:below_pivot+macd_x_dn+weak_close|nk0.8|vm1.2|pm_1130_1400` — 80.0% on 10 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn+weak_close|nk0.8|vm1.2|pm_1130_1400` — 80.0% on 10 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+weak_close|nk0.8|vm1.2|pm_1130_1400` — 80.0% on 10 trades
  - `SHORT:below_pivot+macd_x_dn+weak_close+cvd_dn|nk0.8|vm1.2|pm_1130_1400` — 80.0% on 10 trades
  - `SHORT:below_pivot+macd_x_dn+weak_close+cvd_dn_v|nk0.8|vm0.8|pm_1130_1400` — 80.0% on 10 trades
  - `SHORT:below_pivot+macd_x_dn+weak_close+cvd_dn_v|nk0.8|vm1.2|pm_1130_1400` — 80.0% on 10 trades
  - `SHORT:below_pivot+macd_x_dn+below_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:below_pivot+macd_x_dn+below_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn+below_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:below_vwap+below_pivot+macd_x_dn+below_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+below_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:adi_dn+below_pivot+macd_x_dn+below_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:delta_dump+below_pivot+macd_x_dn+below_vwap_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:delta_dump+below_pivot+macd_x_dn+below_vwap_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:delta_dump+below_pivot+macd_x_dn+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:delta_dump+below_pivot+macd_x_dn+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:below_pivot+macd_x_dn+below_vwap_v+cvd_dn|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:below_pivot+macd_x_dn+below_vwap_v+cvd_dn|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:below_pivot+macd_x_dn+below_vwap_v+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:below_pivot+macd_x_dn+below_vwap_v+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 75.0% on 8 trades


## FINAL VERDICT — A-BOOK PRECISION UNION (NVDA, +/-0.30% in 4h, entry >=08:45, TP by 14:35 CST, 60 sessions)

Goal (max A-book signals/day at near-perfect precision) — precision frontier reached: **0.35/day** is the max the >95% bar allows here.

| metric | value |
|--------|-------|
| resolved trades | 21 (21 target / 0 stop / 0 scratch) |
| **TP-before-SL** | **100.0%** (0 stops) |
| strict win-rate | 100.0% |
| **frequency** | **0.35/day** (15/60 sessions) |
| net | +6.3% |

### A-book families (live `A_BOOK` in nvda_intraday_bot.py)

| # | direction | signal (blocks) | window | gate | trades | TP-b-SL | strict |
|---|-----------|-----------------|--------|------|--------|---------|--------|
| 1 | SHORT | `below_pivot+orb_break_dn` | pm_1130_1400 | 0.0/1.2 | 6 | 100% | 100% |
| 2 | LONG | `vwap_reclaim+hist_turn_up+cvd_up_v` | full_0845_1400 | 0.0/0.8 | 5 | 100% | 100% |
| 3 | SHORT | `below_pivot+macd_x_dn+rsi_thrust_dn` | full_0845_1400 | 0.0/0.8 | 6 | 100% | 100% |
| 4 | SHORT | `ylow_break+macd_x_dn` | full_0845_1400 | 0.0/0.8 | 5 | 100% | 100% |
| 5 | SHORT | `delta_dump+macd_x_dn+rsi_thrust_dn` | full_0845_1400 | 0.0/0.8 | 5 | 100% | 100% |
| 6 | SHORT | `below_vwap+macd_x_dn_pos` | pm_1130_1400 | 0.0/0.8 | 5 | 100% | 100% |
| 7 | SHORT | `macd_x_dn+orb_break_dn_v` | full_0845_1400 | 0.0/0.8 | 5 | 100% | 100% |

**Read this before trading.** In-sample results on one ~3-month regime (~59 sessions). A-book families were selected because they rarely/never stopped in-sample — treat the TP-before-SL figure as an upper bound; the residual risk is the SCRATCH rate (time-stops at the 4h/14:35 deadline). Forward-validate before sizing. Desk session rule enforced in the engine: signals only after 08:45 CST, TP truncated at 14:35 CST.
