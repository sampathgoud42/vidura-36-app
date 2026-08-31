"""Guard 6: refuse, never clamp.

Every rule here answers with the arithmetic that produced the refusal. None of
them quietly adjusts a value into range, because a clamped stop-loss is a stop
the operator did not choose and would never be told about — they would see the
order go through and assume their number was used.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


class RiskRefused(ValueError):
    """A pre-trade rule said no. The message is shown to the operator."""

    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class Bounds:
    """Desk-wide limits. Configurable, but never silently exceeded."""

    tp_pct_min: float = 0.01
    tp_pct_max: float = 500.0
    sl_pct_min: float = 0.01
    sl_pct_max: float = 99.0
    buy_pct_min: float = 0.01
    buy_pct_max: float = 100.0
    max_contracts_per_order: int = 500


DEFAULT_BOUNDS = Bounds()


def validate_entry(*, side: str, buy_pct: float, tp_pct: float, sl_pct: float,
                   expiration: str | None = None, contracts: int | None = None,
                   bounds: Bounds = DEFAULT_BOUNDS,
                   today: date | None = None) -> None:
    """Everything checkable before the venue is touched."""
    if side not in ("call", "put"):
        raise RiskRefused(f"side must be 'call' or 'put', got {side!r}")

    if not (bounds.buy_pct_min <= buy_pct <= bounds.buy_pct_max):
        raise RiskRefused(
            f"buy_pct {buy_pct:g} is outside {bounds.buy_pct_min:g}"
            f"-{bounds.buy_pct_max:g}: a size of zero is not an order, and "
            f"over 100% is more than the account has"
        )

    if tp_pct <= 0:
        raise RiskRefused(
            f"tp_pct {tp_pct:g} would put the target at or below entry — "
            f"that is not a take-profit"
        )
    if tp_pct > bounds.tp_pct_max:
        raise RiskRefused(f"tp_pct {tp_pct:g} exceeds the desk limit "
                          f"{bounds.tp_pct_max:g}")

    # The stop is the one that can silently become "no stop at all".
    if sl_pct <= 0:
        raise RiskRefused(
            f"sl_pct {sl_pct:g} is not a stop: the exit would sit at or above "
            f"entry and would fire immediately"
        )
    if sl_pct >= 100:
        raise RiskRefused(
            f"sl_pct {sl_pct:g} prices the stop at or below zero, which no "
            f"venue can rest and which means the position has no floor"
        )
    if sl_pct > bounds.sl_pct_max:
        raise RiskRefused(f"sl_pct {sl_pct:g} exceeds the desk limit "
                          f"{bounds.sl_pct_max:g}")

    if contracts is not None:
        if contracts <= 0:
            raise RiskRefused(f"contracts must be positive, got {contracts}")
        if contracts > bounds.max_contracts_per_order:
            raise RiskRefused(
                f"{contracts} contracts exceeds the per-order limit of "
                f"{bounds.max_contracts_per_order}")

    if expiration:
        try:
            exp = date.fromisoformat(expiration)
        except ValueError:
            raise RiskRefused(
                f"expiration {expiration!r} is not a date (YYYY-MM-DD)") from None
        if exp < (today or date.today()):
            raise RiskRefused(
                f"expiration {expiration} is in the past — that contract "
                f"cannot be opened")


def exit_prices(entry: float, tp_pct: float, sl_pct: float) -> tuple[float, float]:
    """Target and stop, from the entry actually filled.

    Rounded AWAY from the operator in both directions: the target up, the stop
    down. A rounding that moved the stop closer to entry would tighten a risk
    limit nobody asked to tighten.
    """
    import math

    tp = math.ceil(entry * (1 + tp_pct / 100.0) * 100) / 100
    sl = math.floor(entry * (1 - sl_pct / 100.0) * 100) / 100
    if sl <= 0:
        raise RiskRefused(
            f"a {sl_pct:g}% stop on an entry of {entry:.2f} prices the exit at "
            f"{sl:.2f}; the position would have no floor"
        )
    return tp, sl
