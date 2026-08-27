# MU 5m Super-Signal research — 2026-07-15 15:34 CST

_60 sessions of 5-minute MU (yfinance, incl. pre-market) · entries ['full_0845_1400', 'am_0845_1130', 'mid_1030_1300', 'pm_1130_1400'] (CST) · entry = next bar open · TP 0.3% ≤ 48 bars · SL 0.3% ≤ 48 bars · time-stop at bar 48 close · same-bar TP+SL = stop (conservative)._
_win_rate counts time-stop scratches as non-wins (strict); tp_before_sl ignores scratches._
_GEX/options-flow: no free historical feed — neutral hook only (see signals.GEX_NOTE)._

## Best configs with ≥2 signal/day (strict win-rate)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| SHORT | adi_dn+below_pivot | 0.8 | 0.8 | pm_1130_1400 | 158 | 2.63 | 81 | 77 | 0 | 51.3 | 51.3 | 1.05 | 1.2 | 3.0 | 7.2 |
| LONG | hist_turn_up+strong_close | 0.5 | 0.8 | pm_1130_1400 | 145 | 2.42 | 74 | 71 | 0 | 51.0 | 51.0 | 1.04 | 0.9 | 5.4 | 8.4 |
| LONG | above_pivot+hist_turn_up | 0.0 | 0.8 | full_0845_1400 | 185 | 3.08 | 94 | 91 | 0 | 50.8 | 50.8 | 1.03 | 0.9 | 3.3 | 7.5 |
| LONG | above_pivot+hist_turn_up | 0.5 | 0.8 | full_0845_1400 | 185 | 3.08 | 94 | 91 | 0 | 50.8 | 50.8 | 1.03 | 0.9 | 3.3 | 7.5 |
| LONG | adi_up+above_pivot+hist_turn_up | 0.0 | 0.8 | full_0845_1400 | 122 | 2.03 | 62 | 60 | 0 | 50.8 | 50.8 | 1.03 | 0.6 | 2.7 | 7.4 |
| LONG | adi_up+above_pivot+hist_turn_up | 0.5 | 0.8 | full_0845_1400 | 122 | 2.03 | 62 | 60 | 0 | 50.8 | 50.8 | 1.03 | 0.6 | 2.7 | 7.4 |
| SHORT | adi_dn+below_pivot | 0.0 | 0.8 | pm_1130_1400 | 236 | 3.93 | 119 | 117 | 0 | 50.4 | 50.4 | 1.02 | 0.6 | 4.8 | 7.2 |
| LONG | above_pivot+hist_turn_up+strong_close | 0.0 | 0.8 | full_0845_1400 | 159 | 2.65 | 80 | 79 | 0 | 50.3 | 50.3 | 1.01 | 0.3 | 2.7 | 7.4 |
| LONG | above_pivot+hist_turn_up+strong_close | 0.5 | 0.8 | full_0845_1400 | 159 | 2.65 | 80 | 79 | 0 | 50.3 | 50.3 | 1.01 | 0.3 | 2.7 | 7.4 |
| LONG | hist_turn_up+strong_close | 0.0 | 0.8 | pm_1130_1400 | 147 | 2.45 | 74 | 73 | 0 | 50.3 | 50.3 | 1.01 | 0.3 | 6.0 | 8.3 |
| SHORT | adi_dn+below_pivot | 0.5 | 0.8 | pm_1130_1400 | 232 | 3.87 | 116 | 116 | 0 | 50.0 | 50.0 | 1.0 | -0.0 | 4.8 | 7.3 |
| SHORT | below_pivot+weak_close | 0.0 | 0.8 | pm_1130_1400 | 204 | 3.4 | 102 | 102 | 0 | 50.0 | 50.0 | 1.0 | -0.0 | 4.8 | 7.2 |
| LONG | above_vwap+above_pivot+hist_turn_up | 0.0 | 0.8 | full_0845_1400 | 123 | 2.05 | 61 | 62 | 0 | 49.6 | 49.6 | 0.98 | -0.3 | 2.7 | 7.4 |
| LONG | above_vwap+above_pivot+hist_turn_up | 0.5 | 0.8 | full_0845_1400 | 123 | 2.05 | 61 | 62 | 0 | 49.6 | 49.6 | 0.98 | -0.3 | 2.7 | 7.4 |
| SHORT | adi_dn+below_pivot+weak_close | 0.0 | 0.8 | pm_1130_1400 | 142 | 2.37 | 70 | 72 | 0 | 49.3 | 49.3 | 0.97 | -0.6 | 2.7 | 7.1 |

## Highest strict win-rate overall (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | vwap_reclaim+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 11 | 0.18 | 11 | 0 | 0 | 100.0 | 100.0 | inf | 3.3 | 0.0 | 9.5 |
| LONG | above_vwap+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 11 | 0.18 | 11 | 0 | 0 | 100.0 | 100.0 | inf | 3.3 | 0.0 | 9.5 |
| LONG | vwap_reclaim+above_vwap+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 11 | 0.18 | 11 | 0 | 0 | 100.0 | 100.0 | inf | 3.3 | 0.0 | 9.5 |
| LONG | vwap_reclaim+above_vwap | 0.8 | 1.2 | mid_1030_1300 | 11 | 0.18 | 11 | 0 | 0 | 100.0 | 100.0 | inf | 3.3 | 0.0 | 9.5 |
| LONG | vwap_reclaim+vwap_reclaim_v | 0.8 | 1.2 | mid_1030_1300 | 11 | 0.18 | 11 | 0 | 0 | 100.0 | 100.0 | inf | 3.3 | 0.0 | 9.5 |
| LONG | above_vwap+vwap_reclaim_v | 0.8 | 1.2 | mid_1030_1300 | 11 | 0.18 | 11 | 0 | 0 | 100.0 | 100.0 | inf | 3.3 | 0.0 | 9.5 |
| LONG | vwap_reclaim+above_vwap+vwap_reclaim_v | 0.8 | 1.2 | mid_1030_1300 | 11 | 0.18 | 11 | 0 | 0 | 100.0 | 100.0 | inf | 3.3 | 0.0 | 9.5 |
| LONG | adi_up+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |
| LONG | strong_close+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |
| LONG | vwap_reclaim+adi_up+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |
| LONG | vwap_reclaim+strong_close+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |
| LONG | above_vwap+adi_up+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |
| LONG | above_vwap+strong_close+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |
| LONG | vwap_reclaim+adi_up | 0.8 | 1.2 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |
| LONG | vwap_reclaim+strong_close | 0.8 | 1.2 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |

## Highest TP-before-SL rate (≥10 trades)

| direction | combo | noise_k | vol_mult | window | trades | trades_per_day | wins | stops | scratch | win_rate | tp_before_sl | profit_factor | net_pct | max_drawdown_pct | avg_hold_min |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| LONG | vwap_reclaim+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 11 | 0.18 | 11 | 0 | 0 | 100.0 | 100.0 | inf | 3.3 | 0.0 | 9.5 |
| LONG | above_vwap+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 11 | 0.18 | 11 | 0 | 0 | 100.0 | 100.0 | inf | 3.3 | 0.0 | 9.5 |
| LONG | vwap_reclaim+above_vwap+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 11 | 0.18 | 11 | 0 | 0 | 100.0 | 100.0 | inf | 3.3 | 0.0 | 9.5 |
| LONG | vwap_reclaim+above_vwap | 0.8 | 1.2 | mid_1030_1300 | 11 | 0.18 | 11 | 0 | 0 | 100.0 | 100.0 | inf | 3.3 | 0.0 | 9.5 |
| LONG | vwap_reclaim+vwap_reclaim_v | 0.8 | 1.2 | mid_1030_1300 | 11 | 0.18 | 11 | 0 | 0 | 100.0 | 100.0 | inf | 3.3 | 0.0 | 9.5 |
| LONG | above_vwap+vwap_reclaim_v | 0.8 | 1.2 | mid_1030_1300 | 11 | 0.18 | 11 | 0 | 0 | 100.0 | 100.0 | inf | 3.3 | 0.0 | 9.5 |
| LONG | vwap_reclaim+above_vwap+vwap_reclaim_v | 0.8 | 1.2 | mid_1030_1300 | 11 | 0.18 | 11 | 0 | 0 | 100.0 | 100.0 | inf | 3.3 | 0.0 | 9.5 |
| LONG | adi_up+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |
| LONG | strong_close+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |
| LONG | vwap_reclaim+adi_up+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |
| LONG | vwap_reclaim+strong_close+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |
| LONG | above_vwap+adi_up+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |
| LONG | above_vwap+strong_close+vwap_reclaim_v | 0.8 | 0.8 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |
| LONG | vwap_reclaim+adi_up | 0.8 | 1.2 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |
| LONG | vwap_reclaim+strong_close | 0.8 | 1.2 | mid_1030_1300 | 10 | 0.17 | 10 | 0 | 0 | 100.0 | 100.0 | inf | 3.0 | 0.0 | 10.0 |


## ITERATION 2 — greedy precision ensemble (2026-07-15 15:41 CST)

_809 composites unioned (each ≥70% strict / ≥85% tp-before-sl on its own); book constrained to ≥75% strict win-rate._

- **trades:** 57 (0.95/day, 36/60 days covered)
- **strict win-rate:** 84.2%  ·  **tp-before-sl:** 84.2%
- **profit factor:** 5.33  ·  **net:** 11.7%  ·  **maxDD:** 0.6%
- **avg hold:** 8.6 min

Configs (see results/ensemble.csv):

  - `LONG:vwap_reclaim+above_vwap|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 11 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 11 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 11 trades
  - `LONG:above_vwap+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 11 trades
  - `LONG:above_vwap+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 11 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 11 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 11 trades
  - `LONG:vwap_reclaim+adi_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:vwap_reclaim+strong_close|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:adi_up+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:adi_up+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:strong_close+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:strong_close+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:vwap_reclaim+adi_up+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:vwap_reclaim+adi_up+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:above_vwap+adi_up+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:above_vwap+adi_up+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 10 trades
  - `LONG:vwap_reclaim+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+adi_up+strong_close|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:adi_up+strong_close+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:adi_up+strong_close+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim_v+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim_v+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+strong_close|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+adi_up+strong_close+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+adi_up+strong_close+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+adi_up+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+adi_up+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+adi_up+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+adi_up+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:above_vwap+adi_up+strong_close+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:above_vwap+adi_up+strong_close+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:above_vwap+adi_up+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:above_vwap+adi_up+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:above_vwap+adi_up+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:above_vwap+adi_up+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 9 trades
  - `LONG:vwap_reclaim+above_pivot|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_pivot|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_pivot|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_pivot+vwap_reclaim_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_pivot+vwap_reclaim_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_pivot+vwap_reclaim_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_pivot+vwap_reclaim_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_pivot+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_pivot+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+vwap_reclaim_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+vwap_reclaim_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+vwap_reclaim_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+vwap_reclaim_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+adi_up+strong_close+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+adi_up+strong_close+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+adi_up+strong_close+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:adi_up+strong_close+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:adi_up+strong_close+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:adi_up+strong_close+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:adi_up+strong_close+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 8 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_pivot+strong_close+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+above_pivot|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+above_pivot|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+above_pivot|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+strong_close|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+strong_close|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+strong_close|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+vwap_reclaim_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+vwap_reclaim_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+vwap_reclaim_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+vwap_reclaim_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close+vwap_reclaim_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close+vwap_reclaim_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close+vwap_reclaim_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close+vwap_reclaim_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+above_pivot+strong_close+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_vwap+adi_up+above_pivot+vwap_reclaim_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_vwap+adi_up+above_pivot+vwap_reclaim_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_vwap+adi_up+above_pivot+vwap_reclaim_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_vwap+adi_up+above_pivot+vwap_reclaim_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_vwap+adi_up+above_pivot+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_vwap+adi_up+above_pivot+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_vwap+above_pivot+strong_close+vwap_reclaim_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_vwap+above_pivot+strong_close+vwap_reclaim_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_vwap+above_pivot+strong_close+vwap_reclaim_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_vwap+above_pivot+strong_close+vwap_reclaim_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_vwap+above_pivot+strong_close+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 7 trades
  - `LONG:above_vwap+above_pivot+strong_close+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 7 trades
  - `SHORT:adi_dn+below_pivot+orb_break_dn|nk0.0|vm0.8|pm_1130_1400` — 100.0% on 7 trades
  - `SHORT:adi_dn+below_pivot+orb_break_dn|nk0.5|vm0.8|pm_1130_1400` — 100.0% on 7 trades
  - `SHORT:below_vwap+adi_dn+below_pivot+orb_break_dn|nk0.0|vm0.8|pm_1130_1400` — 100.0% on 7 trades
  - `SHORT:below_vwap+adi_dn+below_pivot+orb_break_dn|nk0.5|vm0.8|pm_1130_1400` — 100.0% on 7 trades
  - `SHORT:adi_dn+below_pivot+orb_break_dn+cvd_dn|nk0.0|vm0.8|pm_1130_1400` — 100.0% on 7 trades
  - `SHORT:adi_dn+below_pivot+orb_break_dn+cvd_dn|nk0.5|vm0.8|pm_1130_1400` — 100.0% on 7 trades
  - `LONG:vwap_reclaim+rvol_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+rvol_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_lo_bounce|nk0.8|vm1.2|pm_1130_1400` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+rvol_thrust_up+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+rvol_thrust_up+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+cvd_up+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+cvd_up+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+above_pivot+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rvol_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rvol_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+strong_close|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+strong_close|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+strong_close|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+above_pivot+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+strong_close+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+strong_close+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+cvd_up+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+cvd_up+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+cvd_up+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+cvd_up+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+above_pivot+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+cvd_up+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim+cvd_up+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+strong_close+vwap_reclaim_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+strong_close+vwap_reclaim_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+strong_close+vwap_reclaim_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+strong_close+vwap_reclaim_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+strong_close+vwap_reclaim_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+strong_close+vwap_reclaim_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+above_pivot+vwap_reclaim_v+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up+cvd_up_v|nk0.0|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up+cvd_up_v|nk0.0|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up+cvd_up_v|nk0.5|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up+cvd_up_v|nk0.5|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up+cvd_up_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:above_pivot+vwap_reclaim_v+cvd_up+cvd_up_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+cvd_up+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|mid_1030_1300` — 100.0% on 6 trades
  - `LONG:vwap_reclaim_v+cvd_up+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|mid_1030_1300` — 100.0% on 6 trades
  - `SHORT:adi_dn+below_pivot+weak_close+orb_break_dn|nk0.0|vm0.8|pm_1130_1400` — 100.0% on 6 trades
  - `SHORT:adi_dn+below_pivot+weak_close+orb_break_dn|nk0.5|vm0.8|pm_1130_1400` — 100.0% on 6 trades
  - `LONG:macd_x_up+hist_turn_up|nk0.0|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:macd_x_up+hist_turn_up|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:macd_x_up+hist_turn_up|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:macd_x_up+hist_turn_up+strong_close|nk0.0|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:macd_x_up+hist_turn_up+strong_close|nk0.5|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `LONG:macd_x_up+hist_turn_up+strong_close|nk0.8|vm0.8|am_0845_1130` — 87.5% on 8 trades
  - `SHORT:below_pivot+weak_close+orb_break_dn|nk0.0|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_pivot+weak_close+orb_break_dn|nk0.5|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+below_pivot+weak_close+orb_break_dn|nk0.0|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `SHORT:below_vwap+below_pivot+weak_close+orb_break_dn|nk0.5|vm0.8|pm_1130_1400` — 87.5% on 8 trades
  - `LONG:vwap_reclaim+rvol_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+rvol_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+rvol_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+rvol_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:yhigh_break+hist_turn_up|nk0.0|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:yhigh_break+hist_turn_up|nk0.5|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+vwap_lo_bounce|nk0.0|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_pivot+vwap_lo_bounce|nk0.5|vm1.2|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:adi_up+yhigh_break+cvd_up|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:yhigh_break+above_pivot+hist_turn_up|nk0.0|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:yhigh_break+above_pivot+hist_turn_up|nk0.5|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+adi_up+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rvol_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rvol_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rvol_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rvol_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+strong_close+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+above_vwap+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+strong_close+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+strong_close+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+strong_close+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+strong_close+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+strong_close+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+strong_close+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+adi_up+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+strong_close+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up+cvd_up_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up+cvd_up_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up+cvd_up_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up+cvd_up_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim+cvd_up+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+yhigh_break+cvd_up|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+adi_up+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rvol_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:above_vwap+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:adi_up+yhigh_break+above_pivot+cvd_up|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:adi_up+yhigh_break+strong_close+cvd_up|nk0.8|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `LONG:adi_up+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:adi_up+strong_close+vwap_reclaim_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:adi_up+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+rvol_thrust_up+above_vwap_v|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:strong_close+vwap_reclaim_v+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up+cvd_up_v+rsi_thrust_up|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up+cvd_up_v+rsi_thrust_up|nk0.0|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up+cvd_up_v+rsi_thrust_up|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up+cvd_up_v+rsi_thrust_up|nk0.5|vm1.2|mid_1030_1300` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up+cvd_up_v+rsi_thrust_up|nk0.8|vm0.8|full_0845_1400` — 85.7% on 7 trades
  - `LONG:vwap_reclaim_v+cvd_up+cvd_up_v+rsi_thrust_up|nk0.8|vm1.2|full_0845_1400` — 85.7% on 7 trades
  - `SHORT:vwap_loss+below_pivot|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:vwap_loss+below_pivot|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:vwap_loss+below_vwap+below_pivot|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:vwap_loss+below_vwap+below_pivot|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:vwap_loss+below_pivot+weak_close|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:vwap_loss+below_pivot+weak_close|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:vwap_loss+below_vwap+below_pivot+weak_close|nk0.0|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:vwap_loss+below_vwap+below_pivot+weak_close|nk0.5|vm0.8|mid_1030_1300` — 85.7% on 7 trades
  - `SHORT:below_pivot+weak_close+orb_break_dn+cvd_dn|nk0.0|vm0.8|pm_1130_1400` — 85.7% on 7 trades
  - `SHORT:below_pivot+weak_close+orb_break_dn+cvd_dn|nk0.5|vm0.8|pm_1130_1400` — 85.7% on 7 trades


## FINAL VERDICT — A-BOOK PRECISION UNION (MU, +/-0.30% in 4h, entry >=08:45, TP by 14:35 CST, 60 sessions)

Goal (max A-book signals/day at near-perfect precision) — precision frontier reached: **0.63/day** is the max the >95% bar allows here.

| metric | value |
|--------|-------|
| resolved trades | 38 (38 target / 0 stop / 0 scratch) |
| **TP-before-SL** | **100.0%** (0 stops) |
| strict win-rate | 100.0% |
| **frequency** | **0.63/day** (28/60 sessions) |
| net | +11.4% |

### A-book families (live `A_BOOK` in mu_intraday_bot.py)

| # | direction | signal (blocks) | window | gate | trades | TP-b-SL | strict |
|---|-----------|-----------------|--------|------|--------|---------|--------|
| 1 | LONG | `vwap_reclaim+above_vwap` | mid_1030_1300 | 0.8/1.2 | 11 | 100% | 100% |
| 2 | SHORT | `adi_dn+below_pivot+orb_break_dn` | pm_1130_1400 | 0.0/0.8 | 7 | 100% | 100% |
| 3 | LONG | `above_pivot+vwap_lo_bounce` | pm_1130_1400 | 0.8/1.2 | 6 | 100% | 100% |
| 4 | LONG | `macd_x_up+hist_turn_up` | am_0845_1130 | 0.0/1.2 | 5 | 100% | 100% |
| 5 | SHORT | `vwap_loss+adi_dn+below_pivot` | mid_1030_1300 | 0.0/0.8 | 5 | 100% | 100% |
| 6 | SHORT | `vwap_loss+adi_dn+hist_turn_dn` | mid_1030_1300 | 0.0/0.8 | 5 | 100% | 100% |
| 7 | SHORT | `vwap_loss+hist_turn_dn+cvd_dn` | mid_1030_1300 | 0.0/0.8 | 5 | 100% | 100% |

**Read this before trading.** In-sample results on one ~3-month regime (~59 sessions). A-book families were selected because they rarely/never stopped in-sample — treat the TP-before-SL figure as an upper bound; the residual risk is the SCRATCH rate (time-stops at the 4h/14:35 deadline). Forward-validate before sizing. Desk session rule enforced in the engine: signals only after 08:45 CST, TP truncated at 14:35 CST.
