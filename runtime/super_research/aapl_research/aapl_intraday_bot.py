#!/usr/bin/env python
"""
aapl_intraday_bot.py — live AAPL Super-Signal watcher (multi-engine).

Watches completed 5-minute AAPL candles during the research entry window
(8:45 AM – 2:00 PM CST) for the playbook discovered by research.py/iterate.py,
on FOUR horizon engines — TP/SL must resolve within 1h/2h/3h/4h. The 4h engine
is the researched original (accuracies as-is); 1h/2h/3h re-score the same
playbook at their horizon via engine_common (daily, results/engine_scores.json)
and only keep configs that still clear the research floor there:

  * A-book — the hand-picked "never-stopped" precision setups (REPORT.md
    FINAL VERDICT), hardcoded below with their 4h backtest accuracy.
  * B-book — every ensemble composite from results/ensemble.csv (if present),
    parsed dynamically so a re-run of iterate.py refreshes the live playbook.

Every fresh signal appends one row PER QUALIFYING ENGINE to
aapl_intraday_signals.csv (CST timestamps, `engine` column) — same TP/SL
prices, engine-scaled deadlines. The category supervisor merges same-bar rows
across engines into the central A/B ledgers and grades the agreement:
2 engines = HOT · 3 = SUPER HOT · 4 = SUPER++ HOT.

Usage:
    python aapl_intraday_bot.py                 # live loop, poll 60s
    python aapl_intraday_bot.py --poll 120
    python aapl_intraday_bot.py --once          # one scan of the latest bar
    python aapl_intraday_bot.py --backfill-today  # emit everything today fired
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))    # super_research/ -> engine_common
sys.path.insert(0, str(HERE))

import config as C             # noqa: E402
import data                    # noqa: E402
import features                # noqa: E402
import signals                 # noqa: E402
import engine_common           # noqa: E402

# ── the playbook ──────────────────────────────────────────────────────────────
# A-book: FINAL VERDICT precision setups (60-session backtest, results/)
A_BOOK = [
    {"book": "A", "direction": "LONG", "combo": ["above_pivot", "hist_turn_up", "rvol_thrust_up"],
     "window": "am_0845_1130", "nk": 0.0, "vm": 0.8,
     "acc_strict": 100.0, "acc_tpsl": 100.0, "bt_trades": 8},
    {"book": "A", "direction": "LONG", "combo": ["yhigh_break", "hist_turn_up", "strong_close"],
     "window": "pm_1130_1400", "nk": 0.0, "vm": 0.8,
     "acc_strict": 85.7, "acc_tpsl": 100.0, "bt_trades": 7},
    {"book": "A", "direction": "SHORT", "combo": ["hist_turn_dn", "cvd_dn", "rsi_thrust_dn"],
     "window": "full_0845_1400", "nk": 0.8, "vm": 0.8,
     "acc_strict": 83.3, "acc_tpsl": 100.0, "bt_trades": 6},
    {"book": "A", "direction": "LONG", "combo": ["macd_x_up", "hist_turn_up", "strong_close", "cvd_up"],
     "window": "full_0845_1400", "nk": 0.0, "vm": 1.2,
     "acc_strict": 100.0, "acc_tpsl": 100.0, "bt_trades": 7},
    {"book": "A", "direction": "LONG", "combo": ["vwap_reclaim", "rvol_thrust_up"],
     "window": "am_0845_1130", "nk": 0.0, "vm": 0.8,
     "acc_strict": 100.0, "acc_tpsl": 100.0, "bt_trades": 6},
    {"book": "A", "direction": "LONG", "combo": ["yhigh_break", "hist_turn_up"],
     "window": "mid_1030_1300", "nk": 0.8, "vm": 0.8,
     "acc_strict": 100.0, "acc_tpsl": 100.0, "bt_trades": 6},
]

if __name__ == "__main__":
    engine_common.run_worker(HERE, "aapl", C, data, features, signals, A_BOOK)
