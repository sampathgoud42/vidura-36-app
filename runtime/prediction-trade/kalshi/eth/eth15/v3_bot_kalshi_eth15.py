#!/usr/bin/env python
"""ETH-15 v3 — PREDICT-15: buy the call at T+2, while the last 24h says it pays.

At T+2 minutes into each Kalshi fifteen-minute ETH window, buy $1 of the
PREDICT-15 call (YES or NO, the digital-option fair value of the price
against the strike blended with Kalshi's mid) at the live ask, immediate-or-
cancel, and hold it to settlement -- but only while a replay of this same rule
over the last 24 hours, at the real Kalshi quotes with the fee, is profitable.
The loop is ``kalshi/predict15_engine.py``; the research is
docs/research/predict-15.md.

Usage:
    v3_bot_kalshi_eth15.py [--live] [--once]

Paper is the default; --live is the only way to reach real money and is
refused outright when the server is locked to paper.
"""

from __future__ import annotations

import sys
from pathlib import Path

# parents[2]: eth15 -> eth -> kalshi, where the shared engine lives.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import predict15_engine                                  # noqa: E402

PROFILE = predict15_engine.Profile(bot_key="eth15", version="v3", coin="ETH")

if __name__ == "__main__":
    raise SystemExit(predict15_engine.main(PROFILE))
