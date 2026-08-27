# LLY 5m Super-Signal research — 2026-07-15 15:33 CST

_60 sessions of 5-minute LLY (yfinance, incl. pre-market) · entries ['full_0845_1400', 'am_0845_1130', 'mid_1030_1300', 'pm_1130_1400'] (CST) · entry = next bar open · TP 0.3% ≤ 48 bars · SL 0.3% ≤ 48 bars · time-stop at bar 48 close · same-bar TP+SL = stop (conservative)._
_win_rate counts time-stop scratches as non-wins (strict); tp_before_sl ignores scratches._
_GEX/options-flow: no free historical feed — neutral hook only (see signals.GEX_NOTE)._

## Best configs with ≥2 signal/day (strict win-rate)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | above_vwap+adi_up+above_pivot | 0.0 | 1.2 | am_0845_1130 | 168 | 2.8 | 95 | 73 | 0 | 56.5 | 56.5 | 1.3 | 6.6 | 1.8 | 10.7 |
| LONG | above_vwap+above_pivot | 0.0 | 1.2 | am_0845_1130 | 226 | 3.77 | 126 | 100 | 0 | 55.8 | 55.8 | 1.26 | 7.8 | 2.4 | 11.4 |
| SHORT | hist_turn_dn+cvd_dn | 0.0 | 0.8 | full_0845_1400 | 124 | 2.07 | 69 | 48 | 7 | 55.6 | 59.0 | 1.41 | 6.12 | 2.11 | 25.7 |
| SHORT | below_vwap+hist_turn_dn+cvd_dn | 0.0 | 0.8 | full_0845_1400 | 124 | 2.07 | 69 | 48 | 7 | 55.6 | 59.0 | 1.41 | 6.12 | 2.11 | 25.7 |
| SHORT | hist_turn_dn+weak_close | 0.0 | 0.8 | am_0845_1130 | 144 | 2.4 | 80 | 63 | 1 | 55.6 | 55.9 | 1.27 | 5.08 | 3.3 | 19.8 |
| LONG | above_vwap+adi_up+above_pivot | 0.5 | 1.2 | am_0845_1130 | 160 | 2.67 | 89 | 71 | 0 | 55.6 | 55.6 | 1.25 | 5.4 | 2.1 | 10.4 |
| LONG | above_vwap+cvd_up | 0.8 | 1.2 | am_0845_1130 | 160 | 2.67 | 89 | 71 | 0 | 55.6 | 55.6 | 1.25 | 5.4 | 1.8 | 12.3 |
| LONG | adi_up+cvd_up | 0.8 | 1.2 | am_0845_1130 | 139 | 2.32 | 77 | 62 | 0 | 55.4 | 55.4 | 1.24 | 4.5 | 1.8 | 11.3 |
| LONG | above_vwap+adi_up+cvd_up | 0.8 | 1.2 | am_0845_1130 | 139 | 2.32 | 77 | 62 | 0 | 55.4 | 55.4 | 1.24 | 4.5 | 1.8 | 11.3 |
| LONG | above_vwap+delta_surge+above_pivot | 0.0 | 0.8 | full_0845_1400 | 132 | 2.2 | 73 | 57 | 2 | 55.3 | 56.2 | 1.27 | 4.66 | 1.9 | 13.2 |
| LONG | above_vwap+delta_surge+above_pivot | 0.0 | 1.2 | full_0845_1400 | 132 | 2.2 | 73 | 57 | 2 | 55.3 | 56.2 | 1.27 | 4.66 | 1.9 | 13.2 |
| LONG | adi_up+above_pivot+cvd_up | 0.0 | 1.2 | am_0845_1130 | 154 | 2.57 | 85 | 69 | 0 | 55.2 | 55.2 | 1.23 | 4.8 | 2.1 | 10.8 |
| LONG | above_vwap+above_pivot | 0.8 | 1.2 | am_0845_1130 | 147 | 2.45 | 81 | 66 | 0 | 55.1 | 55.1 | 1.23 | 4.5 | 1.8 | 11.3 |
| LONG | delta_surge+above_pivot+cvd_up | 0.0 | 0.8 | full_0845_1400 | 120 | 2.0 | 66 | 53 | 1 | 55.0 | 55.5 | 1.24 | 3.8 | 1.9 | 13.1 |
| LONG | delta_surge+above_pivot+cvd_up | 0.0 | 1.2 | full_0845_1400 | 120 | 2.0 | 66 | 53 | 1 | 55.0 | 55.5 | 1.24 | 3.8 | 1.9 | 13.1 |

## Highest strict win-rate overall (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | above_pivot+vwap_lo_bounce | 0.0 | 0.8 | pm_1130_1400 | 12 | 0.2 | 10 | 2 | 0 | 83.3 | 83.3 | 5.0 | 2.4 | 0.3 | 33.3 |
| LONG | above_pivot+vwap_lo_bounce | 0.5 | 0.8 | pm_1130_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 33.2 |
| LONG | above_pivot+vwap_lo_bounce | 0.8 | 0.8 | pm_1130_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 33.2 |
| SHORT | below_vwap+orb_break_dn_v | 0.0 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 21.4 |
| SHORT | weak_close+orb_break_dn_v | 0.0 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 19.5 |
| SHORT | below_vwap+orb_break_dn+orb_break_dn_v | 0.0 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 21.4 |
| SHORT | weak_close+orb_break_dn+orb_break_dn_v | 0.0 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 19.5 |
| SHORT | below_vwap+orb_break_dn_v | 0.0 | 1.2 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 21.4 |
| SHORT | weak_close+orb_break_dn_v | 0.0 | 1.2 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 19.5 |
| SHORT | below_vwap+orb_break_dn+orb_break_dn_v | 0.0 | 1.2 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 21.4 |
| SHORT | weak_close+orb_break_dn+orb_break_dn_v | 0.0 | 1.2 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 19.5 |
| SHORT | below_vwap+orb_break_dn_v | 0.5 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 21.4 |
| SHORT | weak_close+orb_break_dn_v | 0.5 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 19.5 |
| SHORT | below_vwap+orb_break_dn+orb_break_dn_v | 0.5 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 21.4 |
| SHORT | weak_close+orb_break_dn+orb_break_dn_v | 0.5 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 19.5 |

## Highest TP-before-SL rate (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | above_pivot+vwap_lo_bounce | 0.0 | 0.8 | pm_1130_1400 | 12 | 0.2 | 10 | 2 | 0 | 83.3 | 83.3 | 5.0 | 2.4 | 0.3 | 33.3 |
| LONG | above_pivot+vwap_lo_bounce | 0.5 | 0.8 | pm_1130_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 33.2 |
| LONG | above_pivot+vwap_lo_bounce | 0.8 | 0.8 | pm_1130_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 33.2 |
| SHORT | below_vwap+orb_break_dn_v | 0.0 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 21.4 |
| SHORT | weak_close+orb_break_dn_v | 0.0 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 19.5 |
| SHORT | below_vwap+orb_break_dn+orb_break_dn_v | 0.0 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 21.4 |
| SHORT | weak_close+orb_break_dn+orb_break_dn_v | 0.0 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 19.5 |
| SHORT | below_vwap+orb_break_dn_v | 0.0 | 1.2 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 21.4 |
| SHORT | weak_close+orb_break_dn_v | 0.0 | 1.2 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 19.5 |
| SHORT | below_vwap+orb_break_dn+orb_break_dn_v | 0.0 | 1.2 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 21.4 |
| SHORT | weak_close+orb_break_dn+orb_break_dn_v | 0.0 | 1.2 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 19.5 |
| SHORT | below_vwap+orb_break_dn_v | 0.5 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 21.4 |
| SHORT | weak_close+orb_break_dn_v | 0.5 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 19.5 |
| SHORT | below_vwap+orb_break_dn+orb_break_dn_v | 0.5 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.3 | 21.4 |
| SHORT | weak_close+orb_break_dn+orb_break_dn_v | 0.5 | 0.8 | full_0845_1400 | 11 | 0.18 | 9 | 2 | 0 | 81.8 | 81.8 | 4.5 | 2.1 | 0.6 | 19.5 |


## ITERATION 2 — greedy precision ensemble (2026-07-15 15:40 CST)

_329 composites unioned (each ≥70% strict / ≥85% tp-before-sl on its own); book constrained to ≥75% strict win-rate._

- **trades:** 29 (0.48/day, 19/60 days covered)
- **strict win-rate:** 82.8%  ·  **tp-before-sl:** 85.7%
- **profit factor:** 6.03  ·  **net:** 6.04%  ·  **maxDD:** 0.3%
- **avg hold:** 26.4 min

Configs (see results/ensemble.csv):

  - `SHORT:below_vwap+orb_break_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:below_vwap+orb_break_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:below_vwap+orb_break_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:below_vwap+orb_break_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:orb_break_dn+orb_break_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:orb_break_dn+orb_break_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:orb_break_dn+orb_break_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:orb_break_dn+orb_break_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 7 trades
  - `SHORT:weak_close+orb_break_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:weak_close+orb_break_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:weak_close+orb_break_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:weak_close+orb_break_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn_v+cvd_dn|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn_v+cvd_dn|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn_v+cvd_dn|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn_v+cvd_dn|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn_v+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn_v+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn_v+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn_v+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:weak_close+orb_break_dn+orb_break_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:weak_close+orb_break_dn+orb_break_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:weak_close+orb_break_dn+orb_break_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:weak_close+orb_break_dn+orb_break_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+cvd_dn+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+cvd_dn+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+cvd_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+cvd_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+orb_break_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+orb_break_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+orb_break_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+orb_break_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 100.0% on 6 trades
  - `SHORT:orb_break_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn_v+cvd_dn|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn_v+cvd_dn|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn_v+cvd_dn|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn_v+cvd_dn|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn_v+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn_v+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn_v+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn_v+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+cvd_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+cvd_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+cvd_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+cvd_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+orb_break_dn_v|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+orb_break_dn_v|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+orb_break_dn_v|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+orb_break_dn_v|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 88.9% on 9 trades
  - `SHORT:weak_close+orb_break_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn_v+cvd_dn|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn_v+cvd_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn_v+cvd_dn|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn_v+cvd_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn_v+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn_v+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn_v+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn_v+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v+cvd_dn|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v+cvd_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v+cvd_dn|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v+cvd_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+cvd_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+cvd_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+cvd_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn+cvd_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 87.5% on 8 trades
  - `SHORT:weak_close+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 87.5% on 8 trades
  - `LONG:above_pivot+strong_close+vwap_lo_bounce|nk0.0|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:orb_break_dn+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:orb_break_dn+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:orb_break_dn_v+cvd_dn|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:orb_break_dn_v+cvd_dn|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:orb_break_dn_v+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:orb_break_dn_v+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn_v|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn_v|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn_v|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn_v|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+yhigh_reject+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+yhigh_reject+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+yhigh_reject+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+yhigh_reject+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn_v+cvd_dn|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn_v+cvd_dn|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn_v+cvd_dn|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn_v+cvd_dn|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+weak_close+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+weak_close+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+weak_close+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+weak_close+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+cvd_dn+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+cvd_dn+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+cvd_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+cvd_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:orb_break_dn+cvd_dn+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:orb_break_dn+cvd_dn+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+weak_close+orb_break_dn_v|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+weak_close+orb_break_dn_v|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+weak_close+orb_break_dn_v|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+weak_close+orb_break_dn_v|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn+orb_break_dn_v|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn+orb_break_dn_v|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn+orb_break_dn_v|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn+orb_break_dn_v|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn_v+cvd_dn|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn_v+cvd_dn|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn_v+cvd_dn|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn_v+cvd_dn|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+adi_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+yhigh_reject+weak_close+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+yhigh_reject+weak_close+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+yhigh_reject+weak_close+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+yhigh_reject+weak_close+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+yhigh_reject+cvd_dn+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+yhigh_reject+cvd_dn+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+yhigh_reject+cvd_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+yhigh_reject+cvd_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+orb_break_dn_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+weak_close+orb_break_dn+orb_break_dn_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+orb_break_dn+cvd_dn+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:below_vwap+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn_v+cvd_dn|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn_v+cvd_dn|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn_v+cvd_dn|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn_v+cvd_dn|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn_v+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn_v+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn_v+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+weak_close+orb_break_dn_v+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+orb_break_dn_v+cvd_dn|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+orb_break_dn_v+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+cvd_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+cvd_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+cvd_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn+cvd_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.0|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:adi_dn+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.5|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+weak_close+cvd_dn+cvd_dn_v|nk0.0|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+weak_close+cvd_dn+cvd_dn_v|nk0.0|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+weak_close+cvd_dn+cvd_dn_v|nk0.5|vm0.8|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:yhigh_reject+weak_close+cvd_dn+cvd_dn_v|nk0.5|vm1.2|am_0845_1130` — 85.7% on 7 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:orb_break_dn+orb_break_dn_v+cvd_dn+cvd_dn_v|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:macd_x_dn_pos+hist_turn_dn|nk0.0|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:macd_x_dn_pos+hist_turn_dn|nk0.5|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:macd_x_dn_pos+hist_turn_dn|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:macd_x_dn+macd_x_dn_pos+hist_turn_dn|nk0.0|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:macd_x_dn+macd_x_dn_pos+hist_turn_dn|nk0.5|vm0.8|full_0845_1400` — 75.0% on 8 trades
  - `SHORT:macd_x_dn+macd_x_dn_pos+hist_turn_dn|nk0.8|vm0.8|full_0845_1400` — 75.0% on 8 trades


## FINAL VERDICT — A-BOOK PRECISION UNION (LLY, +/-0.30% in 4h, entry >=08:45, TP by 14:35 CST, 60 sessions)

Goal (max A-book signals/day at near-perfect precision) — precision frontier reached: **0.62/day** is the max the >95% bar allows here.

| metric | value |
|--------|-------|
| resolved trades | 37 (37 target / 0 stop / 0 scratch) |
| **TP-before-SL** | **100.0%** (0 stops) |
| strict win-rate | 100.0% |
| **frequency** | **0.62/day** (21/60 sessions) |
| net | +11.1% |

### A-book families (live `A_BOOK` in lly_intraday_bot.py)

| # | direction | signal (blocks) | window | gate | trades | TP-b-SL | strict |
|---|-----------|-----------------|--------|------|--------|---------|--------|
| 1 | SHORT | `below_vwap+orb_break_dn_v` | am_0845_1130 | 0.0/0.8 | 7 | 100% | 100% |
| 2 | LONG | `s1_bounce+ylow_reclaim` | pm_1130_1400 | 0.0/0.8 | 5 | 100% | 100% |
| 3 | LONG | `hist_turn_up+vwap_lo_bounce` | pm_1130_1400 | 0.8/0.8 | 5 | 100% | 100% |
| 4 | LONG | `poc_reject_up+hist_turn_up+cvd_up` | full_0845_1400 | 0.8/0.8 | 5 | 100% | 100% |
| 5 | SHORT | `r1_reject+yhigh_reject` | mid_1030_1300 | 0.0/0.8 | 5 | 100% | 100% |
| 6 | SHORT | `below_vwap+poc_reject_dn+below_pivot` | pm_1130_1400 | 0.0/0.8 | 5 | 100% | 100% |
| 7 | SHORT | `yhigh_reject+hist_turn_dn+cvd_dn` | full_0845_1400 | 0.0/0.8 | 5 | 100% | 100% |
| 8 | SHORT | `orb_break_dn+below_vwap_v` | full_0845_1400 | 0.0/0.8 | 5 | 100% | 100% |

**Read this before trading.** In-sample results on one ~3-month regime (~59 sessions). A-book families were selected because they rarely/never stopped in-sample — treat the TP-before-SL figure as an upper bound; the residual risk is the SCRATCH rate (time-stops at the 4h/14:35 deadline). Forward-validate before sizing. Desk session rule enforced in the engine: signals only after 08:45 CST, TP truncated at 14:35 CST.
