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
