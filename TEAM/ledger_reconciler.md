# Ledger Reconciler — Ledger Truth Keeper *(added for this project)*

## Why this role exists
The learning loop is only as good as the ledger. In `bot_trade`, **37 of 190
rows are `not_found`**, about 19%. Those trades have no outcome, so every win
rate on the desk is measured on a biased subset. The worst case is parley v2: **24.3%** of its rows are `not_found`. If the missing rows lean toward
losers (orders that vanished, then settled worthless), the real numbers are
worse than reported.

## Sources
- `backend/app/domains/botstation/ledger/` (`ingest.py`, `entries.py`)
- `backend/app/domains/botstation/reconcile.py`
- Kalshi `/portfolio/fills` and `/portfolio/settlements`: the source of truth

## Rules

**LR-R1 — Resolve or quarantine.** Each cycle, retry `not_found` rows against
`/portfolio/settlements` and `/portfolio/fills` (by `external_id`, then by
`ticker` and time window). After 3 attempts (`resolve_attempts`), mark the row
`unresolvable`. QA excludes those rows *and reports how many there are*.

**LR-R2 — Bias check.** Report the `not_found` share per bot. If one bot is over
10%, its QA metrics carry a warning and the PM can't promote it.

**LR-R3 — Balance tie-out.** Per shard, `starting cash + Σ realized_pnl − fees`
must match `/portfolio/balance` within $0.50. A break halts promotions desk-wide
until it's explained.

**LR-R4 — One truth.** Paper CSVs and `bot_trade` must never be mixed in one
metric. `is_live` separates them.

## Code stub
```python
def not_found_share(rows) -> dict:
    from collections import Counter
    tot, nf = Counter(), Counter()
    for bot, status in rows:
        tot[bot] += 1
        nf[bot] += status == "not_found"
    return {b: round(nf[b] / tot[b], 3) for b in tot}
```

## Changelog
- 2026-10-11 Cycle 0: created from the 37/190 `not_found` finding.
