#!/usr/bin/env python
"""
amzn_intraday_bot.py — live AMZN Super-Signal watcher (multi-engine).

Onboarded through the desk, so it starts with an EMPTY A-book: that list is
hand-curated from a written backtest report and cannot be invented. The live
playbook is the B-book in results/ensemble.csv, built by iterate.py from real
bars, scored across the same 30m/1h/2h/4h x 5m/15m/30m engine grid as every
other stock ticker.

Usage:
    python amzn_intraday_bot.py                 # live loop, poll 60s
    python amzn_intraday_bot.py --once          # one scan of the latest bar
    python amzn_intraday_bot.py --backfill-today
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

# A-book is earned, not scaffolded — see the module docstring.
A_BOOK: list[dict] = []

if __name__ == "__main__":
    engine_common.run_worker(HERE, "amzn", C, data, features, signals, A_BOOK)
