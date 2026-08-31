"""The Kalshi seam: every call that reaches the prediction venue.

Separate from the trading domain's Tradier seam on purpose. They are
different venues with different instruments, different auth (a bearer token
versus a signed request), and different meanings for the word "portfolio" --
so they get different modules rather than one with a mode flag.

The private key is passed as CONTENT, never as a path. It lives encrypted in
the database, and the only way to hand a path to the client would be to
decrypt it onto disk, which would undo the encryption for as long as that
file existed.
"""

from __future__ import annotations

import logging

from app.tenancy.credentials import VenueCredential

logger = logging.getLogger(__name__)


class KalshiUnavailable(RuntimeError):
    """The venue refused or could not be reached.

    Never carries the venue's own text to a caller that might return it: a
    401 body can contain the key id that was rejected.
    """


def _client(cred: VenueCredential):
    """Build a client for one call. Imported lazily so a process that never
    touches Kalshi does not need the signing library to start."""
    from app.services.kalshi_client import DEFAULT_BASE, KalshiClient

    if not cred.private_key_pem:
        raise KalshiUnavailable("this operator has no Kalshi private key")
    return KalshiClient(
        cred.token,                       # the API key id IS the identity
        private_key_pem=cred.private_key_pem,
        base_uri=cred.base_url or DEFAULT_BASE,
    )


def portfolio(cred: VenueCredential) -> dict:
    """Settled cash, open-position mark-to-market, and their total.

    The same definition the bots print as [TARGET-PV], so the desk and the bot
    logs agree about what the account is worth. Kalshi returns both figures in
    CENTS; the client converts.

    Total moves with open positions rather than only on settlement, which is
    what makes it a portfolio value rather than a cash balance.
    """
    client = _client(cred)
    try:
        return client.portfolio()
    except Exception as exc:                            # noqa: BLE001
        logger.info("kalshi portfolio: %s", type(exc).__name__)
        raise KalshiUnavailable("Kalshi could not be reached") from exc


def exchange_status(cred: VenueCredential) -> dict:
    client = _client(cred)
    try:
        return client.exchange_status()
    except Exception as exc:                            # noqa: BLE001
        raise KalshiUnavailable("Kalshi could not be reached") from exc

def settlements(cred: VenueCredential, *, limit: int = 200) -> list[dict]:
    """Markets that have RESOLVED, with what each position paid out.

    The bots record a trade when they enter and cannot record the outcome:
    resolution happens hours later at the exchange, long after the process
    that opened the position has exited. So an "open" row in the ledger means
    "nobody has looked", not "still open" -- and left alone it stays open
    forever while the bot's own P&L estimate stands in for the real one.

    This is the read that replaces the estimate with the fact.
    """
    client = _client(cred)
    try:
        return list(client.settlements(limit=limit))
    except Exception as exc:                            # noqa: BLE001
        logger.info("kalshi settlements: %s", type(exc).__name__)
        raise KalshiUnavailable("Kalshi could not be reached") from exc
    finally:
        client.close()

def positions(cred: VenueCredential, *, limit: int = 200) -> list[dict]:
    """Per-market position and Kalshi's OWN realized P&L.

    The most useful of the three reads, because the exchange has already done
    the arithmetic. ``position_fp`` is the net contracts still held -- zero
    means flat, which is the difference between "still running" and "finished
    and nobody wrote it down". ``realized_pnl_dollars`` is what the round trip
    actually made, fees included, so a closed trade does not have to be
    reconstructed from its fills.
    """
    client = _client(cred)
    try:
        return list(client.positions(limit=limit))
    except Exception as exc:                            # noqa: BLE001
        logger.info("kalshi positions: %s", type(exc).__name__)
        raise KalshiUnavailable("Kalshi could not be reached") from exc
    finally:
        client.close()


def fills(cred: VenueCredential, *, limit: int = 500) -> list[dict]:
    """Individual executions. The last resort for reconstructing a round trip.

    Only consulted when neither the settlement feed nor the position feed
    knows about a ticker -- which happens for markets old enough to have
    aged out of both.
    """
    client = _client(cred)
    try:
        return list(client.fills(limit=limit))
    except Exception as exc:                            # noqa: BLE001
        logger.info("kalshi fills: %s", type(exc).__name__)
        raise KalshiUnavailable("Kalshi could not be reached") from exc
    finally:
        client.close()

def orderbook(cred: VenueCredential, ticker: str, *, depth: int = 10) -> dict:
    """Resting bids and asks for one market.

    Read before sending anything at a COMBINED market: one created through the
    collection endpoint starts with an empty book, and an empty book quotes as
    zero -- indistinguishable from a market priced at nothing unless you look.
    """
    client = _client(cred)
    try:
        return client.orderbook(ticker, depth=depth)
    except Exception as exc:                            # noqa: BLE001
        raise KalshiUnavailable("Kalshi could not be reached") from exc
    finally:
        client.close()


def combined_market(cred: VenueCredential, collection: str,
                    legs: list[dict]) -> dict:
    """Create-or-return the single contract that pays on ALL of these legs.

    A parlay is one instrument, not several. Buying the legs separately would
    be N independent bets, each paying on its own -- a completely different
    payout from the product this returns.
    """
    client = _client(cred)
    try:
        return client.create_combined_market(collection, legs)
    except Exception as exc:                            # noqa: BLE001
        logger.warning("kalshi refused a combination in %s over %d legs: %s",
                       collection, len(legs), exc)
        raise KalshiUnavailable(
            f"the combination could not be created: {exc}") from exc
    finally:
        client.close()


def collections(cred: VenueCredential, *, limit: int = 100) -> list[dict]:
    client = _client(cred)
    try:
        return client.multivariate_collections(limit=limit)
    except Exception as exc:                            # noqa: BLE001
        raise KalshiUnavailable("Kalshi could not be reached") from exc
    finally:
        client.close()


def place_order(cred: VenueCredential, *, ticker: str, count: int,
                side: str = "yes", action: str = "buy",
                order_type: str = "limit", price_c: int | None = None,
                client_order_id: str | None = None) -> dict:
    """Send one order.

    ``client_order_id`` is the exchange's own idempotency key and is REQUIRED
    by this seam rather than optional: a retry that invents a new id is a
    second position, and the whole point of retrying is that we do not know
    whether the first attempt landed.
    """
    if not client_order_id:
        raise ValueError(
            "client_order_id is required — without it a retry becomes a "
            "second order")
    client = _client(cred)
    try:
        return client.create_order(
            ticker=ticker, side=side, action=action, count=count,
            order_type=order_type, price_c=price_c,
            client_order_id=client_order_id)
    except Exception as exc:                            # noqa: BLE001
        # The exception TEXT, not just its class. KalshiApiError carries the
        # HTTP status and the exchange's own reason, and logging only the
        # class name threw away the single thing that explains a refusal --
        # every rejected order read "KalshiApiError" and no more, which is
        # indistinguishable from a network blip and says nothing about
        # whether the fault is ours, the account's or the market's.
        logger.warning("kalshi refused %s %s x%d @ %sc: %s",
                       action, ticker, count, price_c, exc)
        raise KalshiUnavailable(f"the order was not accepted: {exc}") from exc
    finally:
        client.close()

# ---- RFQ -----------------------------------------------------------------
#
# Which side to accept, and what it costs. This is the one part of the flow
# the published docs do not state, so the reasoning is written down rather
# than assumed:
#
#   Kalshi rejects a quote when `yes_bid + no_bid > $1`. That constraint only
#   makes sense if both numbers are prices the MAKER pays -- buying YES at a
#   and NO at b costs a+b and pays exactly $1, so a maker quoting both sides
#   needs a+b <= 1. They are bids, and a bid is what someone else sells into.
#
#   So the requester SELLS the side it accepts. Selling NO is the same trade
#   as buying YES, at 1 - no_bid. To BUY YES, accept "no".
#
# It is an inference, so it is a named constant rather than a literal buried
# in a call, and the engine checks the resulting cost against its own ceiling
# before it accepts anything.
BUY_YES_ACCEPTS = "no"


def buy_yes_cost_c(quote: dict) -> float | None:
    """What buying YES through this quote costs, in cents. None if it cannot.

    A maker declines a side by quoting it at zero. A no_bid of zero is not
    "YES costs 100c" -- it is no offer at all, and reading it as a price is
    how a declined quote becomes a trade at the worst possible number.
    """
    raw = quote.get("no_bid_dollars")
    if raw in (None, ""):
        return None
    try:
        no_bid = float(raw)
    except (TypeError, ValueError):
        return None
    if no_bid <= 0 or no_bid >= 1.0:
        # A NO bid at or above a dollar prices YES at zero or less. That is
        # not a free parlay, it is a quote to distrust, and buying "for
        # nothing" on the strength of it is the one outcome worth refusing
        # outright.
        return None
    # Kept to two decimals, not whole cents. A long-shot parlay trades at
    # fractions of a cent -- today's ticket filled at 0.4c -- and rounding
    # that to an integer reported it as free.
    return round((1.0 - no_bid) * 100, 2)


def position_for(cred: VenueCredential, ticker: str) -> dict | None:
    """This account's position in one market, or None.

    Used to read back what a fill ACTUALLY was. An RFQ is sized in dollars and
    the exchange decides the contract count from the price it fills at, so the
    size we asked for is not the size we got -- today's daily ticket asked for
    83.33 contracts at 6c and received 1162.79 at 0.4c. Recording the request
    instead of the result puts a number in the ledger that never existed.
    """
    for row in positions(cred):
        if str(row.get("ticker") or "") == ticker:
            return row
    return None


def request_quote(cred: VenueCredential, ticker: str,
                  target_cost_usd: float) -> str | None:
    """Broadcast an RFQ for a dollar amount. Returns its id. Buys nothing."""
    client = _client(cred)
    try:
        d = client.create_rfq(market_ticker=ticker,
                              target_cost_dollars=target_cost_usd)
        return d.get("id") or d.get("rfq_id")
    except Exception as exc:                            # noqa: BLE001
        logger.warning("kalshi refused an RFQ on %s for $%.2f: %s",
                       ticker, target_cost_usd, exc)
        raise KalshiUnavailable(
            f"the quote request was not accepted: {exc}") from exc
    finally:
        client.close()


def quotes_for(cred: VenueCredential, rfq_id: str) -> list[dict]:
    client = _client(cred)
    try:
        return client.rfq_quotes(rfq_id)
    except Exception as exc:                            # noqa: BLE001
        raise KalshiUnavailable(f"quotes could not be read: {exc}") from exc
    finally:
        client.close()


def accept_quote(cred: VenueCredential, rfq_id: str, quote_id: str,
                 side: str) -> dict:
    client = _client(cred)
    try:
        return client.accept_quote(rfq_id, quote_id, side)
    except Exception as exc:                            # noqa: BLE001
        logger.warning("kalshi refused acceptance of quote %s (%s): %s",
                       quote_id, side, exc)
        raise KalshiUnavailable(f"the quote was not accepted: {exc}") from exc
    finally:
        client.close()


def cancel_quote_request(cred: VenueCredential, rfq_id: str) -> None:
    """Withdraw an RFQ. Best effort -- it expires on its own regardless."""
    client = _client(cred)
    try:
        client.delete_rfq(rfq_id)
    except Exception as exc:                            # noqa: BLE001
        logger.info("could not withdraw RFQ %s (%s); it will expire",
                    rfq_id, type(exc).__name__)
    finally:
        client.close()


# A combined market's legs never change once it exists, so they are looked up
# once per ticker and kept. Without the cache this is one request per held
# combo per pass, forever, for an answer that cannot move.
_LEGS_CACHE: dict[str, list[dict]] = {}


def combo_legs(cred: VenueCredential, ticker: str) -> list[dict]:
    """The legs inside a combined market. Empty when it is not a combo.

    This is what makes a held parlay visible as its parts. /portfolio/positions
    reports a combo as ONE ticker -- KXMVECROSSCATEGORY-... -- and says nothing
    about what is inside it, so a tracker built from positions alone cannot
    tell that Real Madrid is already spoken for and will happily put it in the
    next parlay too. Kalshi does publish the legs, on the market itself.
    """
    if ticker in _LEGS_CACHE:
        return _LEGS_CACHE[ticker]
    client = _client(cred)
    try:
        data = client.request("GET", f"/markets/{ticker}")
        market = data.get("market") or data
        legs = market.get("mve_selected_legs") or []
        legs = [x for x in legs if isinstance(x, dict)]
    except Exception as exc:                            # noqa: BLE001
        # Not cached: an outage must not permanently teach us that a combo
        # has no legs, which would silently re-enable the double-booking
        # this exists to prevent.
        logger.warning("could not read the legs of %s: %s", ticker, exc)
        raise KalshiUnavailable(f"legs unavailable for {ticker}") from exc
    finally:
        client.close()
    _LEGS_CACHE[ticker] = legs
    return legs


def open_collections(cred: VenueCredential, *, limit: int = 100) -> list[dict]:
    """Every open multivariate collection, with the events each can host.

    Discovered rather than configured. A collection ticker typed into a form
    goes stale the moment Kalshi rotates them, and an engine that can only
    build parlays somebody remembered to name is an engine that mostly does
    not build parlays.
    """
    client = _client(cred)
    try:
        out = []
        for row in client.multivariate_collections(limit=limit):
            ticker = row.get("collection_ticker") or ""
            if not ticker:
                continue
            try:
                out.append(client.collection_detail(ticker))
            except Exception:                           # noqa: BLE001
                # One unreadable collection must not hide the rest.
                continue
        return out
    except Exception as exc:                            # noqa: BLE001
        logger.info("kalshi collections: %s", type(exc).__name__)
        raise KalshiUnavailable("Kalshi could not be reached") from exc
    finally:
        client.close()
