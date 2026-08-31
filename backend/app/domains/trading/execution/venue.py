"""The venue seam: every call that reaches a broker goes through here.

The credential is KEYWORD-ONLY on every function, and the subject of the call
comes first: an order id, a contract, a symbol. It read better the other way
round until the tests were written against it -- a caller substituting this
module wants to say "cancel THIS order", and having to accept a credential it
does not care about as the first positional argument makes every substitution
carry a parameter it will not use.

Module-level functions rather than a class hierarchy, on purpose. This is the
boundary between "our logic" and "someone else's money", and it needs to be
the easiest thing in the codebase to substitute — in a test, in a dry run, and
in the paper venue. A function that can be replaced with one line is a seam;
an injected object graph is a design someone has to learn first.

Everything here is stateless and takes an explicit credential. Nothing caches
a client between calls, because a cached client is a credential held in memory
for longer than the work needed it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.tenancy.credentials import VenueCredential

logger = logging.getLogger(__name__)

# Order states the venue still considers live. Anything else is finished, one
# way or another.
LIVE_ORDER_STATUSES = frozenset({"open", "partially_filled", "pending",
                                 "accepted", "queued"})


class VenueError(RuntimeError):
    """The venue refused or could not be reached.

    Carries the venue's own message where there is one, but callers must NOT
    pass it through to an API response unfiltered: a 401 body can contain the
    token that was rejected.
    """

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PlacedOrder:
    order_id: str
    status: str
    raw: dict


def _client(cred: VenueCredential, *, sandbox: bool):
    """Build a broker client for one call.

    Imported lazily so that a process which never trades — a migration, the
    doctor, a test of the ledger — does not need the broker library or a
    credential just to import this module.
    """
    from app.services.tradier_client import TradierClient, TradierCredentials

    return TradierClient(TradierCredentials(
        access_token=cred.token,
        account_id=cred.account_id or "",
        sandbox=sandbox,
        base_url=cred.base_url or "",
    ))


# ---- reads ----------------------------------------------------------------

def held_quantity(occ_symbol: str, *, cred: VenueCredential,
                  sandbox: bool = True) -> float:
    """How many contracts the ACCOUNT actually holds.

    A fill is not a position: the order can report filled a beat before the
    holding is on the books, and selling into that gap is what the venue
    rejects. Every exit decision asks this rather than trusting our own row.
    """
    client = _client(cred, sandbox=sandbox)
    try:
        for row in client.positions():
            if row.get("symbol") == occ_symbol:
                return abs(float(row.get("quantity") or 0))
        return 0.0
    finally:
        client.close()


def order_status(order_id: str, *, cred: VenueCredential,
                 sandbox: bool = True) -> dict:
    client = _client(cred, sandbox=sandbox)
    try:
        return client.order_status(order_id)
    finally:
        client.close()


def working_orders_for(occ_symbol: str, *, cred: VenueCredential,
                       side: str | None = None, sandbox: bool = True) -> list[dict]:
    """Orders the venue still has working for this contract.

    Guard 4. Our database can be wrong — an order can land while the write
    that records it fails — so the account is asked as well as our own rows.
    This is the same argument the sell path already made, applied to buys.
    """
    client = _client(cred, sandbox=sandbox)
    try:
        out = []
        for order in client.orders():
            if order.get("option_symbol") != occ_symbol:
                continue
            if (order.get("status") or "").lower() not in LIVE_ORDER_STATUSES:
                continue
            if side and order.get("side") != side:
                continue
            out.append(order)
        return out
    finally:
        client.close()


def working_orders_after_place(occ_symbol: str, *, cred: VenueCredential,
                               side: str | None = None,
                               sandbox: bool = True) -> list[dict]:
    """Guard 5's re-read, as its own function so it is separately observable.

    Same query as working_orders_for. Kept distinct because the two answer
    different questions — "may I place one?" and "did exactly one land?" — and
    a single name would make the settle-and-confirm step invisible in a stack
    trace.
    """
    return working_orders_for(occ_symbol, cred=cred, side=side, sandbox=sandbox)


def resting_sells(occ_symbol: str, *, cred: VenueCredential,
                  sandbox: bool = True) -> list[dict]:
    return working_orders_for(occ_symbol, cred=cred, side="sell_to_close",
                              sandbox=sandbox)


def bid_for(occ_symbol: str, *, cred: VenueCredential,
            sandbox: bool = True) -> float | None:
    """The current bid. What the monitored stop compares against.

    This called client.option_quote, which does not exist -- the method is
    client.quote -- and the AttributeError went straight into a bare
    ``except Exception: return None``. So this returned None for EVERY
    position, on every pass, and the stop monitor read that as "no bid
    available yet" rather than "this code is broken". A stop that can never
    read a price can never fire.

    Two changes, and the second matters more than the first. The name is
    fixed; and the except no longer covers programmer error. A network
    failure is an ordinary, expected outcome that deserves None and a retry
    next pass. A missing attribute is a bug, and on the stop path a bug must
    be loud rather than indistinguishable from a quiet market.
    """
    from app.services.tradier_client import TradierError

    client = _client(cred, sandbox=sandbox)
    try:
        quote = client.quote(occ_symbol)
        bid = float(quote.get("bid") or 0)
        return bid if bid > 0 else None
    except (TradierError, OSError, ValueError, TypeError):
        # The venue was unreachable, or answered without a usable bid. The
        # monitor treats this as "no reading this pass" and its heartbeat
        # goes stale if it keeps happening, which is what stops new entries.
        return None
    finally:
        client.close()


def quotes(symbols: list[str], *, cred: VenueCredential,
           sandbox: bool = True) -> list[dict]:
    """Batch quotes -- one request however many symbols.

    Symbols the venue does not recognise are simply ABSENT from the response
    rather than returned empty, so callers that lay out one row per requested
    symbol have to fill the gaps themselves.
    """
    client = _client(cred, sandbox=sandbox)
    try:
        return list(client.quotes(symbols))
    finally:
        client.close()


def expirations(symbol: str, *, cred: VenueCredential,
                sandbox: bool = True) -> list[str]:
    """Listed expiries for a symbol.

    Here rather than in the router because the router had been building its
    own client for this -- two seams instead of one, and the second was
    invisible to anything substituting the first.
    """
    client = _client(cred, sandbox=sandbox)
    try:
        return list(client.expirations(symbol))
    finally:
        client.close()


def option_chain(symbol: str, expiration: str, *, cred: VenueCredential,
                 sandbox: bool = True) -> list[dict]:
    client = _client(cred, sandbox=sandbox)
    try:
        # client.chain, not client.option_chain. The seam is named for the
        # domain concept and the client for the vendor endpoint; getting that
        # mapping wrong raised AttributeError inside callers that caught
        # Exception, so the chain board and the contract picker both reported
        # "no contracts" rather than "this code calls a method that does not
        # exist". Verified against TradierClient by test_venue_seam.
        return list(client.chain(symbol, expiration))
    finally:
        client.close()


def market_session(*, cred: VenueCredential) -> dict:
    """A short-lived market-data streaming session: ``{sessionid, url}``.

    PRODUCTION ONLY, and deliberately so rather than by oversight: the sandbox
    token is refused with "Required scope(s): scope-stream". That is safe --
    a market session can only read quotes, never place an order -- and paper
    trading against real prices is the entire point of the desk.

    What travels to the browser is the session id, not the account token. The
    id expires in five minutes and buys nothing but a quote feed.
    """
    client = _client(cred, sandbox=False)
    try:
        return client.market_session()
    finally:
        client.close()


def timesales(symbol: str, *, cred: VenueCredential, interval: str = "5min",
              start: str | None = None, sandbox: bool = True) -> list[dict]:
    """Intraday bars.

    Only the intervals the venue serves natively are passed through. Anything
    coarser is folded from these by indicators.aggregate -- asking the venue
    for a 2-minute bar returns nothing useful, and doing the fold at each call
    site is how two boards end up disagreeing about the same instrument.
    """
    client = _client(cred, sandbox=sandbox)
    try:
        return list(client.timesales(symbol, interval, start=start))
    finally:
        client.close()


def balance(*, cred: VenueCredential, sandbox: bool = True) -> dict:
    client = _client(cred, sandbox=sandbox)
    try:
        return client.balances()
    finally:
        client.close()


# ---- writes ---------------------------------------------------------------

def place_buy(*, cred: VenueCredential, underlying: str, occ_symbol: str,
              quantity: int, price: float, sandbox: bool = True) -> PlacedOrder:
    client = _client(cred, sandbox=sandbox)
    try:
        order = client.place_option_order(
            underlying=underlying, occ_symbol=occ_symbol,
            side="buy_to_open", quantity=quantity,
            order_type="limit", price=price,
        )
        return PlacedOrder(str(order["id"]), str(order.get("status", "")), order)
    finally:
        client.close()


def place_sell(*, cred: VenueCredential, underlying: str, occ_symbol: str,
               quantity: int, price: float, duration: str = "gtc",
               sandbox: bool = True) -> PlacedOrder:
    """The resting take-profit."""
    client = _client(cred, sandbox=sandbox)
    try:
        order = client.place_option_order(
            underlying=underlying, occ_symbol=occ_symbol,
            side="sell_to_close", quantity=quantity,
            order_type="limit", price=price, duration=duration,
        )
        return PlacedOrder(str(order["id"]), str(order.get("status", "")), order)
    finally:
        client.close()


def place_stop(*, cred: VenueCredential, underlying: str, occ_symbol: str,
               quantity: int, stop_price: float, sandbox: bool = True) -> PlacedOrder:
    """The stop that RESTS AT THE VENUE.

    This is the layer that actually closes the hole Phase 3 found: with it, a
    stop survives this process dying. Without it the stop exists only inside a
    Python loop, and a crash leaves a live position with an armed profit-taker
    and no downside protection.

    A venue that refuses this must not fail silently — the caller marks the
    position monitored_only and says so, rather than implying protection that
    is not there.
    """
    client = _client(cred, sandbox=sandbox)
    try:
        order = client.place_option_order(
            underlying=underlying, occ_symbol=occ_symbol,
            side="sell_to_close", quantity=quantity,
            order_type="stop", price=stop_price, duration="gtc",
        )
        return PlacedOrder(str(order["id"]), str(order.get("status", "")), order)
    finally:
        client.close()


def sell_to_close(*, cred: VenueCredential, underlying: str, occ_symbol: str,
                  quantity: int, price: float | None = None,
                  sandbox: bool = True) -> PlacedOrder:
    """Exit now. Limit at mid when the spread is wide, market when it is not."""
    client = _client(cred, sandbox=sandbox)
    try:
        if price is None:
            order = client.place_option_order(
                underlying=underlying, occ_symbol=occ_symbol,
                side="sell_to_close", quantity=quantity, order_type="market")
        else:
            order = client.place_option_order(
                underlying=underlying, occ_symbol=occ_symbol,
                side="sell_to_close", quantity=quantity,
                order_type="limit", price=price)
        return PlacedOrder(str(order["id"]), str(order.get("status", "")), order)
    finally:
        client.close()


def cancel_order(order_id: str, *, cred: VenueCredential,
                 sandbox: bool = True) -> None:
    client = _client(cred, sandbox=sandbox)
    try:
        client.cancel_order(order_id)
    except Exception as exc:                            # noqa: BLE001
        # A cancel that fails because the order is already gone is a success
        # for every caller's purpose. Log and continue rather than aborting an
        # exit because the thing we wanted removed removed itself.
        logger.info("cancel %s: %s", order_id, exc)
    finally:
        client.close()
