"""Picking the contract and sizing the order — the T-1 rules, in one place.

Two of these are the kind of arithmetic that looks obviously right and is
obviously wrong once, expensively:

THE SIGNED DELTA BAND. An operator says "0.25 to 0.45" as a magnitude, because
that is how moneyness is spoken. On the tape it is signed: a call's delta runs
0..+1 and a put's runs 0..-1. So one spoken band means two different searches.
Matching on absolute value found the right contracts by accident of magnitude
while being unable to tell a correctly-signed put from a wrongly-signed one,
and it recorded every put's entry delta as positive.

THE x100 MULTIPLIER. An option contract covers 100 shares. Sizing that forgets
it orders a hundred times the intended quantity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def delta_band(side: str, delta_min: float, delta_max: float) -> tuple[float, float]:
    """The signed range this side actually trades in."""
    lo, hi = sorted((abs(delta_min), abs(delta_max)))
    if side == "call":
        return lo, hi
    return -hi, -lo


def smart_limit(bid: float, ask: float) -> float:
    """Mid when the spread is wide, ask when it is a cent or two.

    Chasing the mid on a two-cent spread just means not getting filled.
    """
    if ask <= 0:
        return 0.0
    if bid <= 0:
        return round(ask, 2)
    if (ask - bid) <= 0.02:
        return round(ask, 2)
    return round((bid + ask) / 2, 2)


def pick_contract(chain: list[dict], side: str, delta_min: float,
                  delta_max: float) -> dict | None:
    """The contract whose delta sits closest to the middle of its signed band.

    Requires a live TWO-SIDED quote: an option with no bid cannot be exited,
    so it must never be entered. Ties break toward the tighter spread.
    """
    lo, hi = delta_band(side, delta_min, delta_max)
    target = (lo + hi) / 2

    candidates = []
    for opt in chain:
        if (opt.get("option_type") or "").lower() != side:
            continue
        greeks = opt.get("greeks") or {}
        delta = greeks.get("delta")
        if delta is None:
            continue
        delta = float(delta)
        if not (lo <= delta <= hi):
            continue
        bid = float(opt.get("bid") or 0)
        ask = float(opt.get("ask") or 0)
        # No bid, no exit, no entry.
        if bid <= 0 or ask <= 0:
            continue
        candidates.append((abs(delta - target), ask - bid, opt, delta))

    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0], c[1]))
    _, _, opt, delta = candidates[0]
    picked = dict(opt)
    picked["_delta"] = delta
    return picked


@dataclass(frozen=True)
class Sizing:
    contracts: int
    budget_usd: float
    band_low_usd: float
    band_high_usd: float
    per_contract_usd: float
    total_usd: float

    def explain(self) -> str:
        return (f"{self.contracts} contract(s) at ${self.per_contract_usd:.2f} "
                f"= ${self.total_usd:.2f}, against a ${self.budget_usd:.2f} "
                f"budget (band ${self.band_low_usd:.2f}-${self.band_high_usd:.2f})")


def size_contracts(buying_power: float, buy_pct: float, price: float, *,
                   tolerance_pct: float = 25.0, min_contracts: int = 1) -> Sizing:
    """How many contracts, and the arithmetic that says why.

    buy_pct is a TARGET, not a cap. Contracts are indivisible, so a strict
    floor against the budget misses the trade in both directions: on a $50
    budget a $60 contract sizes to zero — even though it is the contract the
    delta band asked for — and a $30 contract sizes to one, leaving $20 parked.

    So the budget carries a tolerance band, and the rule is: aim at the budget,
    accept any whole number of contracts whose total lands inside the band.
    """
    if price <= 0:
        return Sizing(0, 0.0, 0.0, 0.0, 0.0, 0.0)

    budget = buying_power * (buy_pct / 100.0)
    band_low = budget * (1 - tolerance_pct / 100.0)
    band_high = budget * (1 + tolerance_pct / 100.0)
    per_contract = price * 100          # the multiplier the shorthand omits

    inside = math.floor(budget / per_contract)
    total = inside * per_contract

    if inside == 0:
        # Nothing fits the budget. One lot, if it fits under the ceiling.
        if per_contract <= band_high:
            inside, total = 1, per_contract
    elif total < band_low:
        # Under the floor: one more lot, if that stays under the ceiling.
        if (inside + 1) * per_contract <= band_high:
            inside += 1
            total = inside * per_contract

    if inside == 0 and min_contracts and min_contracts * per_contract <= band_high:
        inside, total = min_contracts, min_contracts * per_contract

    return Sizing(contracts=int(inside), budget_usd=round(budget, 2),
                  band_low_usd=round(band_low, 2), band_high_usd=round(band_high, 2),
                  per_contract_usd=round(per_contract, 2), total_usd=round(total, 2))
