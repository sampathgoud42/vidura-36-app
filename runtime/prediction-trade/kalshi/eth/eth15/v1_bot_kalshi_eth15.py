#!/usr/bin/env python
"""ETH-15 v1 — trade when ETH's five-column DMI board is mostly agreed and building.

Read across the five timeframes the CRYPTO panel shows for ETH -- 2m, 5m, 10m,
15m and 30m -- the side (the column's colour) and the ADX slope (its arrow):

    at least 4 of 5 CALL, 2m ADX rising ↑, at least 3 of 5 rising ↑   -> buy YES
    at least 4 of 5 PUT,  2m ADX rising ↑, at least 3 of 5 rising ↑   -> buy NO
    anything else                                                    -> stand aside

    enter only 5-300 seconds after the market opened
    pay only 30c-65c on the side being bought
    take profit +15%, stop -40%, both armed only after the buy fills

THE RISING COUNT IS OVER THE WHOLE STACK, not just the agreeing timeframes,
and 2m leads: its ADX must be rising, and it is one of the three.

The same engine as BTC-15 v9 and gold/silver/oil v5 -- the rule is
``app.domains.botstation.dmi_stack.read_stacked`` and the loop is
``kalshi/dmi_engine.py`` -- so this file is only the few facts that make it
ETH: Kalshi's KXETH15M series and the CRYPTO board's ``eth`` row.

Usage:
    v1_bot_kalshi_eth15.py [--live] [--once]

Paper is the default; --live is the only way to reach real money and is
refused outright when the server is locked to paper.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# parents[2]: eth15 -> eth -> kalshi, where the shared engine lives.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import dmi_engine                                        # noqa: E402

PROFILE = dmi_engine.Profile(
    bot_key="eth15",
    version="v1",
    series=os.getenv("BOTETH_SERIES", "KXETH15M"),
    board="crypto",
    row_key="eth",
    rule="stacked",
)

if __name__ == "__main__":
    raise SystemExit(dmi_engine.main(PROFILE))
