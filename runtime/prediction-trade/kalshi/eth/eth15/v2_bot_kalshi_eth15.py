#!/usr/bin/env python
"""ETH-15 v2 — trade the CRYPTO board's confirmed headline, CALL ✓ / PUT ✓.

The same engine as BTC-15 v10, on ETH's row: the board's signal is 2m, 5m
and 15m on one side, and the ✓ is 30m on that side too.

    CALL ✓ and 30m call    -> buy YES
    PUT ✓  and 30m put     -> buy NO
    anything else          -> stand aside (mixed, no ✓, 30m disagreeing)

    enter only 30-300 seconds after the market opened
    bid only 35c-69c on the side being bought
    take profit +15%, stop -30%, both armed only after the buy fills

v1 (the stacked rule) stays selectable. The rule is
``app.domains.botstation.dmi_stack.read_confirmed``; the loop is
``kalshi/dmi_engine.py``. This file is only the few facts that make it ETH:
Kalshi's KXETH15M series and the CRYPTO board's ``eth`` row.

Usage:
    v2_bot_kalshi_eth15.py [--live] [--once]

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
    version="v2",
    series=os.getenv("BOTETH_SERIES", "KXETH15M"),
    board="crypto",
    row_key="eth",
    rule="confirmed",
)

if __name__ == "__main__":
    raise SystemExit(dmi_engine.main(PROFILE))
