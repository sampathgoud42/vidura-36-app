#!/usr/bin/env python
"""BTC-15 v7 — trade the quarter-hour only when BTC's whole DMI stack agrees.

    BTC 79381.00  1m 15↑  2m 37↑  5m 50↑  10m 34↑   ->  buy YES
    BTC 79381.00  1m 15↓  2m 37↓  5m 50↓  10m 34↓   ->  buy NO
    anything else                                    ->  stand aside

    enter only 5-300 seconds after the market opened
    pay only 30c-65c on the side being bought

That is the CRYPTO panel's own BTC row, read the way an operator reads it. The
rule and the loop are shared with gold, silver and oil -- see
``kalshi/dmi_engine.py`` for the engine and
``app.domains.botstation.dmi_stack`` for the rule -- so this file is only the
four facts that make it BTC.

WHAT CHANGED FROM v6. v6 asked three different coins (BTC, ETH, SOL) whether
they agreed, and used only the board's headline ``signal``, which is itself
just the 1m and 2m sides matching -- so the 5m and 10m columns on screen were
never consulted. v7 asks the instrument being traded about all four of its own
timeframes instead, and opens the window at 5 seconds rather than 60 so the
front of the move is not already gone.

Usage:
    v7_bot_kalshi_btc15.py [--live] [--once]

Paper is the default; --live is the only way to reach real money and is
refused outright when the server is locked to paper.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# parents[2]: btc15 -> btc -> kalshi, where the shared engine lives.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import dmi_engine                                        # noqa: E402

PROFILE = dmi_engine.Profile(
    bot_key="btc15",
    version="v7",
    series=os.getenv("BOTBTC_SERIES", "KXBTC15M"),
    board="crypto",
    row_key="btc",
)

if __name__ == "__main__":
    raise SystemExit(dmi_engine.main(PROFILE))
