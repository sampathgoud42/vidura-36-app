#!/usr/bin/env python
"""Gold-15 v5 — trade when the five-column DMI board is mostly agreed and building.

Read across the five timeframes the COMMODITIES panel shows -- 2m, 5m, 10m, 15m
and 30m -- the side (the column's colour) and the ADX slope (its arrow):

    at least 4 of 5 CALL, 2m ADX rising ↑, at least 3 of 5 rising ↑   -> buy YES
    at least 4 of 5 PUT,  2m ADX rising ↑, at least 3 of 5 rising ↑   -> buy NO
    anything else                                                    -> stand aside

    enter only 5-300 seconds after the market opened
    pay only 30c-65c on the side being bought
    take profit +15%, stop -40%, both armed only after the buy fills

THE RISING COUNT IS OVER THE WHOLE STACK, not just the agreeing timeframes,
and 2m leads: its ADX must be rising, and it is one of the three.

WHAT CHANGED FROM v4. v4 read four columns (1m-10m), three of four on a
side and three of four rising. This reads the board as it is drawn now, asks
four of five, and puts 2m's slope first. Both stay selectable. The rule is
``app.domains.botstation.dmi_stack.read_stacked``; the loop is
``kalshi/dmi_engine.py``, shared by BTC, gold, silver and oil.

Usage:
    v5_bot_kalshi_gold15.py [--live] [--once]

Paper is the default; --live is the only way to reach real money and is
refused outright when the server is locked to paper.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# parents[2]: gold15 -> commodities -> kalshi, where the shared engine lives.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import dmi_engine                                        # noqa: E402

PROFILE = dmi_engine.Profile(
    bot_key="gold15",
    version="v5",
    series=os.getenv("BOTGOLD_SERIES", "KXGOLD15M"),
    board="commodities",
    row_key="gold15",
    rule="stacked",
)

if __name__ == "__main__":
    raise SystemExit(dmi_engine.main(PROFILE))
