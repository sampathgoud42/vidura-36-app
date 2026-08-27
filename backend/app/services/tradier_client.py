"""Thin synchronous client for the Tradier brokerage REST API.

Two environments, each with its OWN host, token and account id, configured in
the customer .env:

    sandbox -> TRADIER_SANDBOX_URI / _TOKEN / _ACCOUNT_ID   (Tradier's paper venue)
    live    -> TRADIER_PROD_URI    / _TOKEN / _ACCOUNT_ID

The sandbox is a REAL separate venue, not a dry-run flag — so a paper session
can never leak an order into the live account by a flag being read wrong.
Two gates keep it that way: TBOT_PAPER_ONLY pins every client to sandbox
when set, and ``normalize_base_url`` refuses to build a client whose host
belongs to the other environment.

Quirk this module absorbs so callers never see it: Tradier collapses
single-element arrays into bare objects ("quotes.quote" is a dict for one
symbol, a list for two). ``_as_list`` normalizes every such site.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

PROD_HOST = "api.tradier.com"
SANDBOX_HOST = "sandbox.tradier.com"
PROD_BASE = f"https://{PROD_HOST}/v1"
SANDBOX_BASE = f"https://{SANDBOX_HOST}/v1"
TIMEOUT_S = 20


class TradierError(RuntimeError):
    """Transport or API-level failure, with the HTTP status when known."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _as_list(node: Any) -> list:
    """Tradier returns one-element collections as a bare object."""
    if node is None or node == "null":
        return []
    return node if isinstance(node, list) else [node]


def normalize_base_url(uri: str | None, *, sandbox: bool) -> str:
    """Turn a configured host into a full API base, and refuse a crossed venue.

    The customer .env carries bare hosts (``sandbox.tradier.com``), so scheme
    and the ``/v1`` suffix are filled in here. The host check is the load-
    bearing part: with BOTH environments configured in one file, a copy-paste
    slip in TRADIER_SANDBOX_URI is otherwise an order on the live account.
    """
    want_host = SANDBOX_HOST if sandbox else PROD_HOST
    if not (uri or "").strip():
        return SANDBOX_BASE if sandbox else PROD_BASE
    raw = uri.strip().rstrip("/")
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower()
    if not host:
        raise TradierError(f"unusable Tradier URI: {uri!r}")
    other_host = PROD_HOST if sandbox else SANDBOX_HOST
    if host == other_host:
        raise TradierError(
            f"refusing to build a {'sandbox' if sandbox else 'live'} Tradier "
            f"client pointed at {host} — check TRADIER_"
            f"{'SANDBOX' if sandbox else 'PROD'}_URI in the customer .env"
        )
    if host != want_host:
        logger.warning("Tradier %s venue on non-standard host %s",
                       "sandbox" if sandbox else "live", host)
    path = parsed.path.rstrip("/")
    if not path:
        path = "/v1"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


@dataclass
class TradierCredentials:
    access_token: str
    account_id: str
    sandbox: bool
    # Full API base, already normalized. None falls back to the built-in host
    # for this environment.
    base_url: str | None = None


class TradierClient:
    def __init__(self, creds: TradierCredentials):
        self.creds = creds
        # Re-validated here, not just at load: every path that builds a client
        # goes through this constructor.
        self.base = normalize_base_url(creds.base_url, sandbox=creds.sandbox)
        self._s = requests.Session()
        self._s.headers.update({
            "Authorization": f"Bearer {creds.access_token}",
            "Accept": "application/json",
        })

    # ── plumbing ────────────────────────────────────────────────────────────
    def _req(self, method: str, path: str, *, params: dict | None = None,
             data: dict | None = None) -> dict:
        url = f"{self.base}{path}"
        try:
            r = self._s.request(method, url, params=params, data=data,
                                timeout=TIMEOUT_S)
        except requests.RequestException as exc:
            raise TradierError(f"Tradier unreachable: {exc}") from exc
        if r.status_code >= 400:
            # Tradier sends error text bodies; keep them, they say WHY
            raise TradierError(
                f"Tradier HTTP {r.status_code}: {r.text[:300]}", r.status_code
            )
        try:
            return r.json() or {}
        except ValueError as exc:
            raise TradierError(f"Tradier sent non-JSON: {r.text[:200]}") from exc

    def close(self) -> None:
        self._s.close()

    # ── account ─────────────────────────────────────────────────────────────
    def profile(self) -> dict:
        return self._req("GET", "/user/profile").get("profile", {})

    def balances(self) -> dict:
        """Flat view of the numbers the desk needs.

        ``option_buying_power`` is the sizing base: margin accounts report it
        under balances.margin, cash accounts under balances.cash — and using
        total_cash on a margin account would size against money options
        cannot actually spend.
        """
        b = self._req(
            "GET", f"/accounts/{self.creds.account_id}/balances"
        ).get("balances", {}) or {}
        margin = b.get("margin") or {}
        cash = b.get("cash") or {}
        obp = (b.get("option_buying_power")
               or margin.get("option_buying_power")
               or cash.get("cash_available")
               or b.get("total_cash") or 0)
        open_pl = float(b.get("open_pl") or 0)
        close_pl = float(b.get("close_pl") or 0)   # today's realized P&L
        return {
            "total_equity": float(b.get("total_equity") or 0),
            "total_cash": float(b.get("total_cash") or 0),
            "option_buying_power": float(obp or 0),
            "open_pl": open_pl,
            "close_pl": close_pl,
            "day_pl": open_pl + close_pl,          # what "today" cost or made
            "account_id": self.creds.account_id,
            "sandbox": self.creds.sandbox,
        }

    # ── market data ─────────────────────────────────────────────────────────
    def expirations(self, symbol: str) -> list[str]:
        d = self._req("GET", "/markets/options/expirations",
                      params={"symbol": symbol})
        return [str(x) for x in _as_list((d.get("expirations") or {}).get("date"))]

    def chain(self, symbol: str, expiration: str) -> list[dict]:
        d = self._req("GET", "/markets/options/chains",
                      params={"symbol": symbol, "expiration": expiration,
                              "greeks": "true"})
        return _as_list((d.get("options") or {}).get("option"))

    def quote(self, occ_symbol: str) -> dict:
        d = self._req("GET", "/markets/quotes", params={"symbols": occ_symbol})
        quotes = _as_list((d.get("quotes") or {}).get("quote"))
        if not quotes:
            raise TradierError(f"no quote for {occ_symbol}")
        return quotes[0]

    def quotes(self, symbols: list[str]) -> list[dict]:
        """Batch quotes — one request however many symbols. Symbols Tradier
        does not recognize are simply absent from the response (they land in
        ``unmatched_symbols``), so callers must fill gaps themselves."""
        d = self._req("GET", "/markets/quotes",
                      params={"symbols": ",".join(symbols)})
        return _as_list((d.get("quotes") or {}).get("quote"))

    def timesales(self, symbol: str, interval: str = "1min",
                  start: str | None = None, end: str | None = None) -> list[dict]:
        """Intraday bars for today: ``[{time, timestamp, open, high, low, close,
        volume, vwap}]``. The seed a live chart needs — the socket only starts
        producing from the moment you connect."""
        params: dict[str, Any] = {"symbol": symbol, "interval": interval}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        d = self._req("GET", "/markets/timesales", params=params)
        return _as_list((d.get("series") or {}).get("data"))

    # ── streaming ───────────────────────────────────────────────────────────
    def market_session(self) -> dict:
        """A market streaming session: ``{sessionid, url}``.

        Production only — the sandbox token comes back 401 "Required scope(s):
        scope-stream". The id is valid for five minutes to CONNECT with.
        """
        d = self._req("POST", "/markets/events/session")
        stream = d.get("stream") or {}
        if not stream.get("sessionid"):
            raise TradierError(f"no streaming session in response: {str(d)[:200]}")
        return stream

    # ── orders ──────────────────────────────────────────────────────────────
    def place_option_order(self, *, underlying: str, occ_symbol: str, side: str,
                           quantity: int, order_type: str = "limit",
                           price: float | None = None,
                           duration: str = "day") -> dict:
        data = {
            "class": "option",
            "symbol": underlying,
            "option_symbol": occ_symbol,
            "side": side,                      # buy_to_open | sell_to_close
            "quantity": str(int(quantity)),
            "type": order_type,                # limit | market
            "duration": duration,              # day | gtc
        }
        if order_type == "limit":
            if price is None:
                raise TradierError("limit order needs a price")
            data["price"] = f"{price:.2f}"
        d = self._req("POST", f"/accounts/{self.creds.account_id}/orders",
                      data=data)
        order = d.get("order") or {}
        if not order.get("id"):
            raise TradierError(f"order not accepted: {d}")
        return order

    def positions(self) -> list[dict]:
        """What the account actually HOLDS: ``[{symbol, quantity, cost_basis}]``.

        A fill is not the same thing as a position: the order can report
        filled a beat before the holding is on the books, and a
        sell_to_close against a position the venue does not think you have
        is rejected.
        """
        d = self._req("GET", f"/accounts/{self.creds.account_id}/positions")
        node = d.get("positions")
        if not node or node == "null":
            return []
        return _as_list(node.get("position"))

    # statuses that mean an order is still working at the venue
    LIVE_ORDER_STATUSES = ("open", "partially_filled", "pending", "submitted",
                           "accepted", "queued")

    def orders(self) -> list[dict]:
        """Every order on the account, newest first."""
        d = self._req("GET", f"/accounts/{self.creds.account_id}/orders",
                      params={"includeTags": "false"})
        node = d.get("orders")
        if not node or node == "null":
            return []
        return _as_list(node.get("order"))

    def resting_sells(self, occ_symbol: str) -> list[dict]:
        """Every sell on this contract that is still working.

        The account is the authority on what is resting. Trusting our own
        stored order id instead would miss a sell placed by anything else —
        including a second copy of this monitor.

        Plural on purpose: several positions can legitimately hold the same
        contract, each with its own exit, so the question is never "is there
        a sell?" but "how many contracts are already spoken for?".
        """
        want = (occ_symbol or "").upper()
        out = []
        for o in self.orders():
            sym = (o.get("option_symbol") or o.get("symbol") or "").upper()
            side = (o.get("side") or "").lower()
            status = (o.get("status") or "").lower()
            if sym == want and side.startswith("sell") \
                    and status in self.LIVE_ORDER_STATUSES:
                out.append(o)
        return out

    def order_status(self, order_id: int | str) -> dict:
        d = self._req(
            "GET", f"/accounts/{self.creds.account_id}/orders/{order_id}"
        )
        return d.get("order") or {}

    def cancel_order(self, order_id: int | str) -> dict:
        d = self._req(
            "DELETE", f"/accounts/{self.creds.account_id}/orders/{order_id}"
        )
        return d.get("order") or {}
