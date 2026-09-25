#!/usr/bin/env python
"""WTI Oil-15 v4 — trade when MOST of the DMI stack agrees and is building.

Two counts, taken independently across the four timeframes the COMMODITIES
panel shows. The panel prints the side as a COLOUR (green call, red put) and
the ADX slope as the arrow beside the number, and v4 reads both:

    OIL 88.93  1m 15 call↑  2m 37 call↑  5m 50 put↑  10m 34 call↓  -> YES
    OIL 88.93  1m 15 put↓   2m 37 put↑   5m 50 put↑  10m 34 put↑   -> NO

    at least 3 of 4 CALL  and at least 3 of 4 rising ↑   ->  buy YES
    at least 3 of 4 PUT   and at least 3 of 4 rising ↑   ->  buy NO
    anything else                                        ->  stand aside

    enter only 5-300 seconds after the market opened
    pay only 30c-65c on the side being bought

THE RISING COUNT IS OVER THE WHOLE STACK, not over the agreeing side. The
first line above is the case that settles it: three calls, three rising -- but
only TWO of the calls are rising.

WHAT CHANGED FROM v3. v3 required all four timeframes on the same side and
ignored the slope entirely. v4 accepts three of four and asks the slope for
the conviction v3 got from the fourth timeframe. Both stay selectable.

WHERE THE NUMBERS COME FROM. The board prefers Tradier bars on the tracking
ETF (USO) during market hours and falls back to the futures feed (CL=F)
otherwise. A bot subprocess holds no Tradier credential, so in practice this
engine reads the futures feed -- which is why every pass logs which source
answered.

Usage:
    v4_bot_kalshi_oil15.py [--live] [--once]

Paper is the default; --live is the only way to reach real money and is
refused outright when the server is locked to paper.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# parents[2]: oil15 -> commodities -> kalshi, where the shared engine lives.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import dmi_engine                                        # noqa: E402

PROFILE = dmi_engine.Profile(
    bot_key="oil15",
    version="v4",
    series=os.getenv("BOTOIL_SERIES", "KXOIL15M"),
    board="commodities",
    row_key="oil15",
    rule="majority",
)

if __name__ == "__main__":
    raise SystemExit(dmi_engine.main(PROFILE))
