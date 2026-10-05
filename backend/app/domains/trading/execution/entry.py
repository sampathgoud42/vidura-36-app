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


# How a strike is chosen: by the delta band, or by open interest.
PICKS = ("delta", "open_interest")


# Near Expiry off: the first expiry at least this many days out.
FAR_MIN_DAYS = 7
# What a position bought on a far expiry is marked with, so it is held over
# the close and recorded as rolled over (risk.rollover) -- the same mark the
# desk's 🌙 carry switch sets.
CARRY_MARK = " +carry"


def choose_expiration(expirations: list[str], *, zero_dte: bool,
                      near_expiry: bool = True) -> str:
    """Which listed expiry to buy:

      0DTE on                    the nearest, today included
      0DTE off, Near Expiry on   the nearest after today
      0DTE off, Near Expiry off  the first at least FAR_MIN_DAYS out

    A same-day contract with hours left is a different trade from the one a
    delta band describes, so it has to be requested rather than fallen into.
    """
    from datetime import timedelta

    today = clock.today()
    floor = (today + timedelta(days=FAR_MIN_DAYS)).isoformat() \
        if not zero_dte and not near_expiry else today.isoformat()
    for exp in sorted(expirations):
        if exp == today.isoformat() and not zero_dte:
            continue
        if exp >= floor:
            return exp
    return sorted(expirations)[-1]


def far_expiry(zero_dte: bool, near_expiry: bool) -> bool:
    """True when the buy is on a 7+ day expiry -- held over the close."""
    return not zero_dte and not near_expiry


def _carry(strategy: str, zero_dte: bool, near_expiry: bool) -> str:
    """The strategy a far-expiry position is opened under: marked to roll over."""
    if not far_expiry(zero_dte, near_expiry) or strategy.endswith(CARRY_MARK):
        return strategy
    return (strategy[:64 - len(CARRY_MARK)] + CARRY_MARK)


def load_chain(symbol: str, *, cred, sandbox: bool, expiration: str | None = None,
               zero_dte: bool = False, near_expiry: bool = True) -> tuple[list[dict], str]:
    """The chain to pick from, and the expiration it belongs to.

    Goes through the venue seam like every other broker call, so substituting
    the venue substitutes all of the outbound calls rather than the half that
    was easy to notice.
    """
    listed = venue_mod.expirations(symbol, cred=cred, sandbox=sandbox)
    if not listed:
        raise ExecutionRefused(f"no listed expirations for {symbol}", status_code=404)
    expiration = expiration or choose_expiration(listed, zero_dte=zero_dte,
                                                 near_expiry=near_expiry)
    return venue_mod.option_chain(symbol, expiration, cred=cred, sandbox=sandbox), expiration


def open_managed(db, *, tenant_id: str, cred, symbol: str, side: str, buy_pct: float,
                 tp_pct: float, sl_pct: float, delta_min: float, delta_max: float,
                 tolerance_pct: float, sandbox: bool, strategy: str,
                 expiration: str | None = None, zero_dte: bool = False,
                 allow_add: bool = False, min_contracts: int = 1,
                 order_type: str = "smart", discount_pct: float = 0.0,
                 pick: str = "delta", near_expiry: bool = True) -> Position:
    """Pick, price, size and place one managed entry through orders.open_position.

    ``order_type`` is how the buy is priced (selection.buy_price): "smart" --
    what every entry did before there was a choice, and still the auto-trader's
    -- "market", or "limit" at the mark less ``discount_pct``, withdrawn after
    selection.LIMIT_CANCEL_S unfilled. The size is taken at that price.

    ``min_contracts`` refuses rather than rounds up: sizing below the floor
    means the account cannot carry this trade at the configured risk, and
    taking it anyway would be trading a size nobody chose.

    ``pick`` is how the strike is chosen: "delta" (the band, as always) or
    "open_interest" -- the expiry's most-held out-of-the-money strike, the
    next most-held when that one cannot be placed (open_by_open_interest).
    The strikes passed over are written on the position's note.

    ``near_expiry`` off (with 0DTE off) buys the first expiry 7+ days out, and
    the position is opened marked to roll over at the close (CARRY_MARK).
    """
    strategy = _carry(strategy, zero_dte, near_expiry)
    if pick not in PICKS:
        raise ExecutionRefused(f"unknown strike pick '{pick}' -- one of {', '.join(PICKS)}")
    if pick == "open_interest":
        pos, passed = open_by_open_interest(
            db, tenant_id=tenant_id, cred=cred, symbol=symbol, side=side,
            buy_pct=buy_pct, tp_pct=tp_pct, sl_pct=sl_pct, tolerance_pct=tolerance_pct,
            sandbox=sandbox, strategy=strategy, expiration=expiration, zero_dte=zero_dte,
            near_expiry=near_expiry, allow_add=allow_add, min_contracts=min_contracts,
            order_type=order_type, discount_pct=discount_pct)
        pos.note = (pos.note or "") + " — strike by open interest" + (
            f"; passed over {'; '.join(passed)}" if passed else "")
        pos.note = pos.note[:1000]
        return pos
    chain, expiration = load_chain(symbol, cred=cred, sandbox=sandbox,
                                   expiration=expiration, zero_dte=zero_dte,
                                   near_expiry=near_expiry)
    opt = selection.pick_contract(chain, side, delta_min, delta_max)
    if opt is None:
        lo, hi = selection.delta_band(side, delta_min, delta_max)
        raise ExecutionRefused(
            f"no {side} on {symbol} {expiration} with a delta in {lo:+g}..{hi:+g} "
            f"and a two-sided quote", status_code=404)

    try:
        price = selection.buy_price(order_type, float(opt.get("bid") or 0),
                                    float(opt.get("ask") or 0), discount_pct)
    except ValueError as exc:
        raise ExecutionRefused(f"{opt['symbol']}: {exc}", status_code=409) from None
    buying_power = float(
        (venue_mod.balance(cred=cred, sandbox=sandbox) or {}).get("option_buying_power") or 0)
    sizing = selection.size_contracts(buying_power, buy_pct, price.sizing_price,
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
        limit_price=price.limit, buy_pct=buy_pct, tolerance_pct=tolerance_pct,
        tp_pct=tp_pct, sl_pct=sl_pct, sandbox=sandbox, strategy=strategy,
        allow_add=allow_add, zero_dte=zero_dte, order_type=price.order_type,
        discount_pct=price.discount_pct, mark=price.mark,
        cancel_after_s=selection.LIMIT_CANCEL_S if price.order_type == "limit" else None)


# How many strikes the open-interest pick works down its list before it
# gives a signal up -- six, as the operator set it. Each try is a full guarded
# order; past six refusals the caller says why on screen and moves on.
OI_MAX_TRIES = 6


def _definitely_not_placed(exc: Exception) -> bool:
    """True only when the order certainly did not reach the book: a guard
    refused before the venue was touched, or the venue answered with a 4xx
    rejection. Anything else -- unreachable, a 5xx, an answer without an
    order id -- may have left an order working, and trying another strike on
    top of it would be the duplicate every guard here exists to prevent."""
    from app.domains.trading.risk.validation import RiskRefused
    from app.services.tradier_client import TradierError

    if isinstance(exc, (ExecutionRefused, RiskRefused)):
        return True
    status = getattr(exc, "status", None)
    return isinstance(exc, TradierError) and status is not None and 400 <= status < 500


def open_by_open_interest(db, *, tenant_id: str, cred, symbol: str, side: str,
                          buy_pct: float, tp_pct: float, sl_pct: float,
                          tolerance_pct: float, sandbox: bool, strategy: str,
                          expiration: str | None = None, zero_dte: bool = False,
                          near_expiry: bool = True,
                          allow_add: bool = False, min_contracts: int = 1,
                          order_type: str = "smart", discount_pct: float = 0.0,
                          max_tries: int = OI_MAX_TRIES) -> tuple[Position, list[str]]:
    """One managed entry on the nearest expiry's most-held out-of-the-money
    strike, whatever its delta -- and, when that order cannot be placed, the
    next most-held, and so on, up to ``max_tries``.

    Priced, sized and guarded exactly as open_managed: the same buy_price,
    size_contracts and orders.open_position. Returns the position and what
    was tried before it, one line per strike passed over."""
    strategy = _carry(strategy, zero_dte, near_expiry)
    chain, expiration = load_chain(symbol, cred=cred, sandbox=sandbox,
                                   expiration=expiration, zero_dte=zero_dte,
                                   near_expiry=near_expiry)
    quote = next(iter(venue_mod.quotes([symbol], cred=cred, sandbox=sandbox)), None) or {}
    spot = float(quote.get("last") or quote.get("close") or 0)
    if spot <= 0:
        raise ExecutionRefused(f"no price for {symbol}, so no side of it to pick from",
                               status_code=404)
    ranked = selection.rank_by_open_interest(chain, side, spot)
    if not ranked:
        raise ExecutionRefused(
            f"no {side} on {symbol} {expiration} {'above' if side == 'call' else 'below'} "
            f"{spot:.2f} with a two-sided quote", status_code=404)
    buying_power = float(
        (venue_mod.balance(cred=cred, sandbox=sandbox) or {}).get("option_buying_power") or 0)
    passed: list[str] = []
    for opt in ranked[:max_tries]:
        label = f"{opt['symbol']} (OI {int(opt.get('open_interest') or 0):,})"
        try:
            price = selection.buy_price(order_type, float(opt.get("bid") or 0),
                                        float(opt.get("ask") or 0), discount_pct)
        except ValueError as exc:                       # no mark to take a discount from
            passed.append(f"{label}: {exc}")
            continue
        try:
            sizing = selection.size_contracts(buying_power, buy_pct, price.sizing_price,
                                              tolerance_pct=tolerance_pct)
            if sizing.contracts < max(1, min_contracts):
                raise ExecutionRefused(f"sized to {sizing.contracts}: {sizing.explain()}",
                                       status_code=409)
            pos = orders.open_position(
                db, tenant_id=tenant_id, cred=cred, symbol=symbol, side=side,
                occ_symbol=opt["symbol"], underlying=symbol,
                strike=float(opt.get("strike") or 0), expiration=expiration,
                delta=opt.get("_delta"), contracts=sizing.contracts,
                limit_price=price.limit, buy_pct=buy_pct, tolerance_pct=tolerance_pct,
                tp_pct=tp_pct, sl_pct=sl_pct, sandbox=sandbox, strategy=strategy,
                allow_add=allow_add, zero_dte=zero_dte, order_type=price.order_type,
                discount_pct=price.discount_pct, mark=price.mark,
                cancel_after_s=selection.LIMIT_CANCEL_S if price.order_type == "limit" else None)
            return pos, passed
        except Exception as exc:
            if not _definitely_not_placed(exc):
                raise
            passed.append(f"{label}: {exc}")
    raise ExecutionRefused(f"none of the {len(passed)} most-held {side}s on {symbol} could "
                           f"be bought -- " + "; ".join(passed)[:900], status_code=409)
