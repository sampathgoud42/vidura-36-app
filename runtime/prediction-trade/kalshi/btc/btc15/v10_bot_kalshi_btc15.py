#!/usr/bin/env python
"""BTC-15 v10 — trade the CRYPTO board's confirmed headline, CALL ✓ / PUT ✓.

The board's signal for BTC is 2m, 5m and 15m on one side; the ✓ beside it
is 30m on that side too. This engine trades exactly that, and checks the 30m
column itself as well:

    CALL ✓ and 30m call    -> buy YES
    PUT ✓  and 30m put     -> buy NO
    anything else          -> stand aside (mixed, no ✓, 30m disagreeing)

    enter only 30-300 seconds after the market opened
    bid only 35c-69c on the side being bought
    take profit +15%, stop -30%, both armed only after the buy fills

WHAT CHANGED FROM v9. v9 counted the five columns itself (four of five on a
side, 2m's ADX rising, three of five rising). This takes the board's own
signal and ✓, ignores the ADX slopes, enters later (30s, not 5s), pays a
narrower 35-69c, and stops out sooner (-30%, not -40%). Both stay
selectable. The rule is ``app.domains.botstation.dmi_stack.read_confirmed``;
the loop is ``kalshi/dmi_engine.py``.

Usage:
    v10_bot_kalshi_btc15.py [--live] [--once]

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
    version="v10",
    series=os.getenv("BOTBTC_SERIES", "KXBTC15M"),
    board="crypto",
    row_key="btc",
    rule="confirmed",
)

if __name__ == "__main__":
    raise SystemExit(dmi_engine.main(PROFILE))
