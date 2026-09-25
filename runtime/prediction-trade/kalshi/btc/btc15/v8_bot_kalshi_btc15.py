#!/usr/bin/env python
"""BTC-15 v8 — trade when MOST of BTC's DMI stack agrees and is building.

Two counts, taken independently across the four timeframes the CRYPTO panel
shows. The panel prints the side as a COLOUR (green call, red put) and the
ADX slope as the arrow beside the number, and v8 reads both:

    BTC 79381.00  1m 15 call↑  2m 37 call↑  5m 50 put↑  10m 34 call↓  -> YES
    BTC 79381.00  1m 15 put↓   2m 37 put↑   5m 50 put↑  10m 34 put↑   -> NO

    at least 3 of 4 CALL  and at least 3 of 4 rising ↑   ->  buy YES
    at least 3 of 4 PUT   and at least 3 of 4 rising ↑   ->  buy NO
    anything else                                        ->  stand aside

    enter only 5-300 seconds after the market opened
    pay only 30c-65c on the side being bought

THE RISING COUNT IS OVER THE WHOLE STACK, not over the agreeing side. The
first line above is the case that settles it: three calls, three rising -- but
only TWO of the calls are rising. A rule that wanted three rising calls would
stand that one down, and it is the example this engine was asked for.

WHAT CHANGED FROM v7. v7 required all four timeframes on the same side and
ignored the slope entirely. That is the strictest reading of the board, and it
stands aside on a stack that is three-quarters convinced -- which on a
fifteen-minute market is most of them. v8 accepts three of four, and asks the
slope for the conviction v7 got from the fourth timeframe: a stack that is
mostly one way AND building is a different thing from one that is mostly one
way and fading.

Both are still selectable. The rule and the loop are shared with gold, silver
and oil -- see ``kalshi/dmi_engine.py`` for the engine and
``app.domains.botstation.dmi_stack`` for the rule -- so this file is only the
few facts that make it BTC.

Usage:
    v8_bot_kalshi_btc15.py [--live] [--once]

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
    version="v8",
    series=os.getenv("BOTBTC_SERIES", "KXBTC15M"),
    board="crypto",
    row_key="btc",
    rule="majority",
)

if __name__ == "__main__":
    raise SystemExit(dmi_engine.main(PROFILE))
