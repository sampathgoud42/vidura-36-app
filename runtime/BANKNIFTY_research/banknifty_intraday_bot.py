#!/usr/bin/env python
"""
banknifty_intraday_bot.py — live BANKNIFTY Super-Signal watcher (multi-engine).

Watches completed candles of the BANKNIFTY ETF proxy during the research entry
window (09:30 – 14:00 IST) for the playbook discovered by research.py/
iterate.py, on FOUR horizon engines x THREE candle sizes — TP/SL must resolve
within 1h/2h/3h/4h on 5m/15m/30m candles (super_research/engine_common). The
researched pair (5m candles, 4h horizon) keeps its playbook accuracies as-is;
every other pair is re-scored daily against the bar cache
(results/engine_scores.json) and keeps only configs clearing the research
floor there:

  * A-book — the hand-picked precision setups (REPORT.md FINAL VERDICT),
    hardcoded below with their researched backtest accuracy.
  * B-book — every ensemble composite from results/ensemble.csv (if present),
    parsed dynamically so a re-run of iterate.py refreshes the live playbook.

Every fresh signal appends one row PER QUALIFYING ENGINE PAIR to
banknifty_intraday_signals.csv (IST timestamps despite the template's _cst column
names; `engine` + `tf` columns) — same TP/SL prices, pair-scaled deadlines.
The Indian paper trader (indian_paper_trader.py) merges same-moment rows,
grades the cross-engine agreement, and paper-trades the result.

Usage:
    python banknifty_intraday_bot.py                 # live loop, poll 60s
    python banknifty_intraday_bot.py --poll 120
    python banknifty_intraday_bot.py --once          # one scan of the latest bar
    python banknifty_intraday_bot.py --backfill-today  # emit everything today fired
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "super_research"))   # -> engine_common
sys.path.insert(0, str(HERE))

import config as C             # noqa: E402
import data                    # noqa: E402
import features                # noqa: E402
import signals                 # noqa: E402
import engine_common           # noqa: E402

# ── the playbook ──────────────────────────────────────────────────────────────
# A-book: FINAL VERDICT precision setups (60-session backtest, results/)
A_BOOK = [
    {"book": "A", "direction": "SHORT", "combo": ["vwap_loss", "delta_dump"],
     "window": "am_0930_1130", "nk": 0.8, "vm": 0.8,
     "acc_strict": 100.0, "acc_tpsl": 100.0, "bt_trades": 9},
    {"book": "A", "direction": "SHORT", "combo": ["yhigh_reject", "cvd_dn"],
     "window": "full_0930_1400", "nk": 0.8, "vm": 0.8,
     "acc_strict": 100.0, "acc_tpsl": 100.0, "bt_trades": 8},
    {"book": "A", "direction": "SHORT", "combo": ["below_pivot", "hist_turn_dn", "vwap_hi_reject"],
     "window": "full_0930_1400", "nk": 0.0, "vm": 1.2,
     "acc_strict": 100.0, "acc_tpsl": 100.0, "bt_trades": 7},
    {"book": "A", "direction": "SHORT", "combo": ["below_vwap", "yhigh_reject"],
     "window": "mid_1030_1300", "nk": 0.0, "vm": 0.8,
     "acc_strict": 100.0, "acc_tpsl": 100.0, "bt_trades": 7},
    {"book": "A", "direction": "SHORT", "combo": ["adi_dn", "below_vwap_v", "vwap_hi_reject"],
     "window": "full_0930_1400", "nk": 0.8, "vm": 0.8,
     "acc_strict": 100.0, "acc_tpsl": 100.0, "bt_trades": 6},
    {"book": "A", "direction": "SHORT", "combo": ["vwap_loss", "rvol_thrust_dn", "cvd_dn"],
     "window": "am_0930_1130", "nk": 0.8, "vm": 0.8,
     "acc_strict": 100.0, "acc_tpsl": 100.0, "bt_trades": 9},
    {"book": "A", "direction": "SHORT", "combo": ["vwap_loss", "delta_dump", "below_pivot"],
     "window": "full_0930_1400", "nk": 0.8, "vm": 0.8,
     "acc_strict": 100.0, "acc_tpsl": 100.0, "bt_trades": 7},
    {"book": "A", "direction": "SHORT", "combo": ["vwap_loss", "below_pivot", "rvol_thrust_dn"],
     "window": "full_0930_1400", "nk": 0.8, "vm": 0.8,
     "acc_strict": 100.0, "acc_tpsl": 100.0, "bt_trades": 7},
]

if __name__ == "__main__":
    engine_common.run_worker(HERE, "banknifty", C, data, features, signals, A_BOOK)
