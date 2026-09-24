"""One entry path for every way a position is opened.

The manual BUY and the auto-trader decide WHEN differently and nothing else.
The chain to read, the contract to pick, the price to bid, the size to take
and every guard around the order are the same trade either way, so they live
here once, and both call it. An automated trader is the last place to accept
a second copy: the level-cross watcher's own copy had drifted from the
selection functions it called until every one of its orders raised.

What wraps this differs by caller and stays with them: the manual route owns
its request's idempotency and HTTP answers, the auto-trader its signal's.
"""

from __future__ import annotations

from app.domains.trading.execution import orders, selection
from app.domains.trading.execution import venue as venue_mod
from app.domains.trading.execution.orders import ExecutionRefused
from app.domains.trading.models import Position
from app.domains.trading.risk import clock


def choose_expiration(expirations: list[str], *, zero_dte: bool) -> str:
    """Nearest listed expiry, skipping today unless 0DTE was asked for.

    A same-day contract with hours left is a different trade from the one a
    delta band describes, so it has to be requested rather than fallen into.
    """
    today = clock.today().isoformat()
    for exp in sorted(expirations):
        if exp == today and not zero_dte:
            continue
        if exp >= today:
            return exp
    return sorted(expirations)[-1]


def load_chain(symbol: str, *, cred, sandbox: bool, expiration: str | None = None,
               zero_dte: bool = False) -> tuple[list[dict], str]:
    """The chain to pick from, and the expiration it belongs to.

    Goes through the venue seam like every other broker call, so substituting
    the venue substitutes all of the outbound calls rather than the half that
    was easy to notice.
    """
    listed = venue_mod.expirations(symbol, cred=cred, sandbox=sandbox)
    if not listed:
        raise ExecutionRefused(f"no listed expirations for {symbol}", status_code=404)
    expiration = expiration or choose_expiration(listed, zero_dte=zero_dte)
    return venue_mod.option_chain(symbol, expiration, cred=cred, sandbox=sandbox), expiration


def open_managed(db, *, tenant_id: str, cred, symbol: str, side: str, buy_pct: float,
                 tp_pct: float, sl_pct: float, delta_min: float, delta_max: float,
                 tolerance_pct: float, sandbox: bool, strategy: str,
                 expiration: str | None = None, zero_dte: bool = False,
                 allow_add: bool = False, min_contracts: int = 1) -> Position:
    """Pick, price, size and place one managed entry through orders.open_position.

    ``min_contracts`` refuses rather than rounds up: sizing below the floor
    means the account cannot carry this trade at the configured risk, and
    taking it anyway would be trading a size nobody chose.
    """
    chain, expiration = load_chain(symbol, cred=cred, sandbox=sandbox,
                                   expiration=expiration, zero_dte=zero_dte)
    opt = selection.pick_contract(chain, side, delta_min, delta_max)
    if opt is None:
        lo, hi = selection.delta_band(side, delta_min, delta_max)
        raise ExecutionRefused(
            f"no {side} on {symbol} {expiration} with a delta in {lo:+g}..{hi:+g} "
            f"and a two-sided quote", status_code=404)

    limit_price = selection.smart_limit(float(opt.get("bid") or 0), float(opt["ask"]))
    buying_power = float(
        (venue_mod.balance(cred=cred, sandbox=sandbox) or {}).get("option_buying_power") or 0)
    sizing = selection.size_contracts(buying_power, buy_pct, limit_price,
                                      tolerance_pct=tolerance_pct)
    if sizing.contracts < 1:
        raise ExecutionRefused(f"sized to zero: {sizing.explain()}", status_code=409)
    if sizing.contracts < min_contracts:
        raise ExecutionRefused(
            f"sized below the {min_contracts}-contract minimum: {sizing.explain()}",
            status_code=409)

    return orders.open_position(
        db, tenant_id=tenant_id, cred=cred, symbol=symbol, side=side,
        occ_symbol=opt["symbol"], underlying=symbol, strike=float(opt.get("strike") or 0),
        expiration=expiration, delta=opt.get("_delta"), contracts=sizing.contracts,
        limit_price=limit_price, buy_pct=buy_pct, tolerance_pct=tolerance_pct,
        tp_pct=tp_pct, sl_pct=sl_pct, sandbox=sandbox, strategy=strategy,
        allow_add=allow_add, zero_dte=zero_dte)
