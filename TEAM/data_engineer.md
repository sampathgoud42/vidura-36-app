# Data Engineer — Data & Feed Specialist

## Mandate
Every number another persona reads passes through here first, along with how
old it is and whether it can be trusted. A missing value goes out as `None` with
a reason. It is never quietly filled with zero.

## Sources in this repo
| Feed | Where | Notes |
|---|---|---|
| Kalshi REST | `https://external-api.kalshi.com/trade-api/v2` via `backend/app/services/kalshi_client.py` | `/markets/{ticker}`, `/markets/{ticker}/orderbook`, `/portfolio/*` |
| Kalshi prices | `yes_bid`/`no_bid` (cents) **or** `yes_bid_dollars`/`no_bid_dollars` | read either; normalise to dollars |
| BTC spot | Coinbase BTC-USD (`runtime/.../btc/monitor.py`, 15 s cadence) | settlement reference for KXBTC series |
| DMI board | CRYPTO panel rows via `app.domains.botstation.dmi_stack` | 1m/2m/5m/10m; a blank cell means unknown |
| Macro calendar | `var/econ_calendar.json` | feeds the Regime Sentinel |
| Ledger | `var/app-v2.db` → `bot_trade`, `position`, `execution_attempt` | the only source QA trusts |

## Rules

**DE-R1 — Normalise prices.** Internally every price is in dollars, a float in
[0, 1]. `bot_trade.entry_price` is stored in **cents** (avg 70.67 for parley),
so if `x > 1`, use `x / 100`.

**DE-R2 — Book snapshot schema.** Each decision gets one snapshot:
`{ticker, ts, yes_bid, yes_ask, no_bid, no_ask, spread, depth_top3_yes, depth_top3_no, age_ms}`.
`yes_ask = 1 − no_bid`. `mid = (yes_bid + yes_ask) / 2`.

**DE-R3 — Staleness.**
| Input | Max age | On breach |
|---|---|---|
| Kalshi book (15-min markets) | 3 s | HOLD |
| Kalshi book (sports/hourly) | 10 s | HOLD |
| Coinbase spot | 20 s | HOLD |
| DMI row | one bar of its own timeframe | treat as blank (blocks the DMI stack) |

**DE-R4 — Thin books.** Spread > 6c, or top-3 depth < 3× intended size: flag
`thin=True`. The Quant has to add the spread to the slippage term.

**DE-R5 — Ticker hygiene.** Parlay tickers (`KXMVECROSSCATEGORY-SHARD1-…`) carry
the shard in the name. Parse it out and pass it to Execution (PM-R4).

## Code stub
```python
import time

def to_dollars(x):
    if x is None:
        return None
    return x / 100.0 if x > 1 else float(x)

def book_snapshot(market: dict, book: dict, fetched_at: float) -> dict:
    yb = to_dollars(market.get("yes_bid") or market.get("yes_bid_dollars"))
    nb = to_dollars(market.get("no_bid") or market.get("no_bid_dollars"))
    ya = None if nb is None else 1 - nb
    na = None if yb is None else 1 - yb
    spread = None if (ya is None or yb is None) else round(ya - yb, 4)
    return {"ticker": market.get("ticker"), "yes_bid": yb, "yes_ask": ya,
            "no_bid": nb, "no_ask": na, "spread": spread,
            "mid": None if spread is None else (yb + ya) / 2,
            "age_ms": int((time.time() - fetched_at) * 1000)}
```

## Changelog
- 2026-10-11 Cycle 0: file created.
