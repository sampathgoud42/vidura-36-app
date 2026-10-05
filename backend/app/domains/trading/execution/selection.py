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
from decimal import ROUND_HALF_UP, Decimal


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


# ---- how the buy is priced --------------------------------------------------
# Three ways to bid, chosen on the ticket:
#
#   smart   smart_limit above: the mid on a wide spread, the ask on a tight
#           one. It rests until it fills or the day ends.
#   market  a market order: it takes whatever the offer is when it arrives.
#   limit   the MARK less a discount, to the cent -- 1.03 at 10% off is
#           0.927, bid 0.93 -- withdrawn by the monitor if it has not filled
#           within LIMIT_CANCEL_S.
ORDER_TYPES = ("smart", "market", "limit")
LIMIT_CANCEL_S = 15 * 60
_CENT = Decimal("0.01")


def mark_price(bid: float, ask: float) -> Decimal | None:
    """The mark: the middle of a two-sided quote, exactly (1.02 / 1.05 is
    1.035). None without both sides -- a discount taken off a one-sided
    "mark" is a discount off a price nobody is quoting."""
    if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
        return None
    return (Decimal(str(bid)) + Decimal(str(ask))) / 2


def discounted_limit(mark: Decimal, discount_pct: float) -> float:
    """mark x (1 - discount), rounded to the cent with halves going UP, the
    way a person rounds a price: 0.927 -> 0.93, 0.945 -> 0.95. Binary floats
    would have sent some halves down (0.945 is stored as 0.94499...)."""
    raw = mark * (Decimal(100) - Decimal(str(discount_pct))) / Decimal(100)
    return float(raw.quantize(_CENT, rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class BuyPrice:
    """What to send, and what one contract is sized at."""
    order_type: str
    limit: float | None           # None for a market order
    sizing_price: float           # the price the budget is divided by
    mark: float | None            # the quote's mark, when it has one
    discount_pct: float | None    # limit orders only


def buy_price(order_type: str, bid: float, ask: float,
              discount_pct: float = 0.0) -> BuyPrice:
    """How to bid on this quote. ValueError when the quote cannot carry the
    order type asked for; callers turn that into a refusal.

    A market order is sized at the ask -- what it is expected to pay -- and a
    limit at its own limit, since that is what it spends if it fills."""
    if order_type not in ORDER_TYPES:
        raise ValueError(f"unknown order type {order_type!r}")
    if not ask or ask <= 0:
        raise ValueError("there is no offer to buy from")
    mark = mark_price(bid, ask)
    if order_type == "market":
        return BuyPrice("market", None, round(float(ask), 2),
                        float(mark) if mark is not None else None, None)
    if order_type == "smart":
        px = smart_limit(bid or 0.0, ask)
        return BuyPrice("smart", px, px, float(mark) if mark is not None else None, None)
    if mark is None:
        raise ValueError("there is no two-sided quote, so no mark to take a discount from")
    px = discounted_limit(mark, discount_pct)
    if px < 0.01:
        raise ValueError(f"{discount_pct:g}% under a mark of {mark} rounds to nothing")
    return BuyPrice("limit", px, px, float(mark), float(discount_pct))


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


# How the open-interest pick scores a strike -- for the order to FILL: what
# the market holds (open interest), what it is trading today (volume), and how
# tight the quote is against its own price (a wide spread is where a limit
# sits unfilled). A strike held, active and tight ranks first; an old OI pile
# nobody trades today, or a penny contract quoted 0.01 x 0.02, ranks lower.
OI_WEIGHT = 0.4
VOLUME_WEIGHT = 0.4
SPREAD_WEIGHT = 0.2


def rank_by_open_interest(chain: list[dict], side: str, spot: float) -> list[dict]:
    """Contracts of one side, out of the money, best liquidity first.

    The open-interest pick, which ignores delta: a CALL must have its strike
    ABOVE the underlying's price and a PUT below it. Among those, each strike
    is scored on open interest and today's volume, each as a share of the
    largest on this side of this expiry, and on how tight its quote is:

        score = OI_WEIGHT * oi / max_oi + VOLUME_WEIGHT * volume / max_volume
              + SPREAD_WEIGHT * (1 - min(1, (ask - bid) / mid))

    highest first; more open interest breaks a tie. ``_score`` rides on each
    contract so a preview can show why it ranked where it did. A two-sided
    quote is required here as it is in pick_contract: no bid, no exit, no
    entry.
    """
    rows = []
    for opt in chain:
        if (opt.get("option_type") or "").lower() != side:
            continue
        try:
            strike = float(opt.get("strike"))
        except (TypeError, ValueError):
            continue
        if (side == "call" and strike <= spot) or (side == "put" and strike >= spot):
            continue
        bid = float(opt.get("bid") or 0)
        ask = float(opt.get("ask") or 0)
        if bid <= 0 or ask <= 0:
            continue
        rows.append((int(opt.get("open_interest") or 0), int(opt.get("volume") or 0),
                     ask - bid, opt))
    if not rows:
        return []
    max_oi = max(r[0] for r in rows) or 1
    max_vol = max(r[1] for r in rows) or 1
    scored = []
    for oi, vol, spread, opt in rows:
        mid = (float(opt["bid"]) + float(opt["ask"])) / 2
        tight = 1 - min(1.0, spread / mid) if mid > 0 else 0.0
        score = (OI_WEIGHT * oi / max_oi + VOLUME_WEIGHT * vol / max_vol
                 + SPREAD_WEIGHT * tight)
        scored.append((-score, -oi, spread, opt, score))
    scored.sort(key=lambda r: r[:3])
    out = []
    for _, _, _, opt, score in scored:
        picked = dict(opt)
        delta = (opt.get("greeks") or {}).get("delta")
        picked["_delta"] = float(delta) if delta is not None else None
        picked["_score"] = round(score, 3)
        out.append(picked)
    return out


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
