#!/usr/bin/env python
"""Gold-15 v3 — trade the quarter-hour only when the whole DMI stack agrees.

    GOLD 405.24  1m 15↑  2m 37↑  5m 50↑  10m 34↑   ->  buy YES
    GOLD 405.24  1m 15↓  2m 37↓  5m 50↓  10m 34↓   ->  buy NO
    anything else                                ->  stand aside

    enter only 5-300 seconds after the market opened
    pay only 30c-65c on the side being bought

That is the COMMODITIES panel's own gold row, read the way an operator reads
it. The rule and the loop are shared with the other commodities and with BTC
-- see ``kalshi/dmi_engine.py`` for the engine and
``app.domains.botstation.dmi_stack`` for the rule -- so this file is only the
four facts that make it gold.

WHAT CHANGED FROM v2. v2 scored gold with its own DMI over its own yfinance
fetch, on its own 1m/2m timeframes, at period 9 -- a second implementation of
an indicator the desk already computes, which could and did disagree with the
board on screen. v3 reads the board itself, all four timeframes, and requires
every one of them to point the same way.

WHERE THE NUMBERS COME FROM. The board prefers Tradier bars on the tracking
ETF (GLD) during market hours and falls back to the futures feed (GC=F)
otherwise. A bot subprocess holds no Tradier credential, so in practice this
engine reads the futures feed -- which is why every pass logs which source
answered.

Usage:
    v3_bot_kalshi_gold15.py [--live] [--once]

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
    version="v3",
    series=os.getenv("BOTGOLD_SERIES", "KXGOLD15M"),
    board="commodities",
    row_key="gold15",
)

if __name__ == "__main__":
    raise SystemExit(dmi_engine.main(PROFILE))
