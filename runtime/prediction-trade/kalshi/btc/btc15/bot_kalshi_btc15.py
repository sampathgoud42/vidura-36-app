"""The shared Kalshi trading primitives the sports bots import.

Every sports script opens with some variant of

    sys.path.insert(0, .../kalshi/btc/btc15)
    import bot_kalshi_btc15 as v1

and that module was never vendored into this project -- only v2 through v5
were. So the import failed at load, and it failed for ALL of them:
bot_kalshi_main, bot_kalshi_sports_v1, bot_kalshi_sports_v2,
bot_kalshi_parley, and kalshi_sports itself. Four registered bot versions that
could not start.

The failure was invisible, which is what made it expensive. The launcher
started the process, the process died on this import before writing anywhere
the desk could see (stdout and stderr both went to DEVNULL), and the run row
still said "running" -- so the Bot Station displayed a live bot that had been
dead since the instant it launched.

Rather than vendor a whole sixth BTC script, this re-exports the twelve names
the sports code actually uses from v4, which is the version they were written
against: the same async RSA-PSS-signed client and the same order helpers.

Re-exported EXPLICITLY rather than with `import *`, for two reasons: three of
the names begin with an underscore and `*` would skip them silently, and a
listed set fails loudly here if v4 ever drops one instead of failing much
later inside a bot placing an order.
"""

from __future__ import annotations

from v4_bot_kalshi_btc15 import (  # noqa: F401
    DRY_RUN,
    HALT_MACHINE_SHUTDOWN,
    ORDER_CREATE_PATH,
    KalshiClient,
    _bid_price,
    _cst_now,
    _mk_order,
    place_buy,
    place_tp_sell,
    portfolio_balance,
    position_for,
    resting_orders,
)

__all__ = [
    "DRY_RUN", "HALT_MACHINE_SHUTDOWN", "ORDER_CREATE_PATH", "KalshiClient",
    "_bid_price", "_cst_now", "_mk_order", "place_buy", "place_tp_sell",
    "portfolio_balance", "position_for", "resting_orders",
]
