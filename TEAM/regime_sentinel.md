# Regime Sentinel — Regime & Event Sentinel *(added for this project)*

## Why this role exists
The 15-minute family (btc15, gold15, silver15, oil15, combo15, signal15) is all
momentum/DMI signals. Those have edge when the market trends and give it back
when it chops. signal15 went 2/11, and every entry between 40c and 65c lost. That
is the profile of a trend signal firing into a range. Something has to say
"not now" independently of the signal itself.

## Rules

**RS-R1 — Regime label per instrument, refreshed every 5-min bar.**
- `TREND`: ADX(14, 5m) ≥ 25 and rising, and |VWAP slope| above its 20-day median
- `CHOP`: ADX < 20, or price crossed VWAP ≥ 4 times in the last 60 min
- `UNKNOWN`: anything else, or the data is stale (DE-R3)

Momentum bots may enter only in `TREND`.

**RS-R2 — Macro blackouts.** Using `var/econ_calendar.json`, no new 15-min entries
from 5 min before to 15 min after any high-impact release (CPI, NFP, FOMC, PCE,
GDP). For oil, add the EIA inventory release. For gold and silver, add FOMC
pressers in full.

**RS-R3 — Volatility shock.** If 1-min realised vol is > 3× its 24 h median, all
15-min entries pause for 10 min. Model q (QS-R3 #1) is invalid during a jump.

**RS-R4 — Session awareness.** Commodities trade thin outside their main
sessions. Outside 08:00–13:30 CT, require `edge_net ≥ 0.05` on gold, silver
and oil.

## Code stub
```python
def regime(adx: float, adx_prev: float, vwap_crosses_60m: int,
           stale: bool) -> str:
    if stale or adx is None:
        return "UNKNOWN"
    if adx < 20 or vwap_crosses_60m >= 4:
        return "CHOP"
    if adx >= 25 and adx > adx_prev:
        return "TREND"
    return "UNKNOWN"
```

## Changelog
- 2026-10-11 Cycle 0: created from the signal15 chop-loss pattern (hypothesis; QA to verify on tagged trades).
