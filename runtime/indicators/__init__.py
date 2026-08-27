"""
btc — Shared BTC spot-price monitor used by both the Kalshi and Polymarket
BTC-15M binary-trading bots.

Public API:
    from btc import BtcVidyaMonitor, SignalT
"""
from .monitor import BtcVidyaMonitor, SignalT

__all__ = ["BtcVidyaMonitor", "SignalT"]
