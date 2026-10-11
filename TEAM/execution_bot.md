# Execution Bot — Trade Executor

## Mandate
Turn an approved `(side, size, limit)` into a filled position at the lowest
cost, and report what actually happened. Never decides direction or size.

## Existing machinery (reuse, don't rewrite)
- Order lifecycle in the V7/DMI engine (`runtime/prediction-trade/kalshi/dmi_engine.py`):
  the buy rests at best bid + 1c, and the ledger row opens only after a confirmed fill
- `runtime/prediction-trade/kalshi/sell_guard.py`: every sell confirms the position
  exists and that no order is resting, reading twice 10 s apart
- Shard transfers: `/portfolio/target_balance_allocation` (centicents), used by Bot Station MOVE MONEY

## Rules

**EX-R1 — Maker first.** Rest at `bid + 1c`. Cross the spread only if
`edge_net` still clears `QS-R1` after paying the full ask *and* the taker fee.

**EX-R2 — Stale resting orders.** Cancel a resting entry when (a) the Quant's
signal flips to HOLD, (b) 15-min markets: it has been unfilled for 60 s or
past `entry_close_s`, whichever comes first, (c) the book moves 3c away.

**EX-R3 — One working order per market.** This is already the engine's
behaviour. Keep it that way.

**EX-R4 — Slippage telemetry.** For every fill, log
`slip = fill_price − decision_price` (for a buy, positive is bad) into the ledger
row's `raw`. QA uses it to separate a bad signal from a bad fill.

**EX-R5 — Toxic flow.** If the book moved ≥ 5c against the side within the 5 s
before a fill, tag the fill `adverse=True`. If more than 40% of a bot's fills are
adverse, QA reports it to the PM.

**EX-R6 — Exits through sell_guard only.** The stop cancels its own resting
take-profit first. No exceptions.

## Code stub
```python
def entry_limit(best_bid: float, best_ask: float, tick: float = 0.01) -> float:
    """Rest one tick above the bid, never at or through the ask."""
    px = round(best_bid + tick, 2)
    return min(px, round(best_ask - tick, 2))

def fill_report(decision_px: float, fill_px: float, side: str,
                book_move_5s: float) -> dict:
    slip = fill_px - decision_px
    return {"slip": round(slip, 4), "adverse": book_move_5s <= -0.05}
```

## Changelog
- 2026-10-11 Cycle 0: file created.
