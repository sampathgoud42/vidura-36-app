# Sports & Parlay Specialist *(added for this project)*

## Why this role exists
parley is the desk's busiest live bot (103 settled trades) and its biggest
loser (−$107.66). It trades Kalshi multi-leg combos (`KXMVECROSSCATEGORY-…`),
whose price is not the product of the leg prices. Kalshi's combo pricing
already prices in leg correlation and a margin. A combo is only +EV if our leg
probabilities are better than the market's *and* the legs are combined
correctly. The repo already has the domain pieces in
`runtime/prediction-trade/kalshi/sports/sport_adapters/` (baseball, basketball,
cricket, golf, hockey, soccer, tennis) and models in
`runtime/prediction-trade/sports/` (tennis predict_v1–v6, baseball4cast).

## Rules

**SP-R1 — Leg-level q.** Each leg's `q` comes from its sport adapter or model,
never from the leg's own Kalshi price. A leg with no independent `q` makes
`q_leg = p_leg`. The combo then has no edge and the answer is HOLD.

**SP-R2 — Correlation.** Same-game legs are positively correlated, so
multiplying their `q`s understates the joint probability, and the combo market
knows that. Cross-game legs can be treated as independent. Until we have a
same-game correlation model, **only trade cross-game combos.**

**SP-R3 — Combo q vs price.** `q_combo = Π q_leg` (cross-game only). Trade only
if `q_combo − p_combo − fee ≥ 0.04`. That's above QS-R1 because of combo margin.

**SP-R4 — Live-game decay.** For in-play legs, every leg `q` older than 30 s is
stale (scores change). Re-pull before every order.

## Code stub
```python
from math import prod

def combo_q(legs: list[dict]) -> float | None:
    """legs: [{'q': float|None, 'game_id': str}] -- cross-game only."""
    if any(l["q"] is None for l in legs):
        return None
    games = [l["game_id"] for l in legs]
    if len(games) != len(set(games)):
        return None          # same-game legs: SP-R2, no model yet
    return prod(l["q"] for l in legs)
```

## Changelog
- 2026-10-11 Cycle 0: created from the parley loss concentration.
