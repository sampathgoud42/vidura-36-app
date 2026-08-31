"""Minimal synchronous Kalshi trade-api/v2 client (RSA-PSS request signing).

Ported from the canonical async client in the 38trades repo
(v4_bot_kalshi_btc15.py) with the import-time env reads converted to
constructor parameters so one API process can serve many users.

Signature scheme: RSA-PSS(SHA256, MGF1-SHA256, salt=digest length) over
``f"{timestamp_ms}{METHOD}/trade-api/v2{path}"`` — the bare path only,
query params are never signed.
"""

from __future__ import annotations

import base64
import os
import time
from pathlib import Path
from typing import Any

import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

DEFAULT_BASE = "https://external-api.kalshi.com/trade-api/v2"
API_PREFIX = "/trade-api/v2"


# Kalshi retired the V1 order endpoint; V2 lives under /portfolio/events.
# Same env override the runtime bot publishes, so both can be pointed
# elsewhere together.
ORDER_CREATE_PATH = os.getenv("KALSHI_ORDER_PATH", "/portfolio/events/orders")


class KalshiAuthError(Exception):
    pass


class KalshiApiError(Exception):
    def __init__(self, status_code: int, body: str):
        super().__init__(f"Kalshi API {status_code}: {body[:300]}")
        self.status_code = status_code
        self.body = body


class KalshiClient:
    def __init__(
        self,
        api_key_id: str,
        private_key_path: str | Path | None = None,
        base_uri: str = DEFAULT_BASE,
        *,
        private_key_pem: str | bytes | None = None,
        pem_password: str | None = None,
        timeout: float = 15.0,
    ):
        self.api_key_id = api_key_id
        self.base_uri = base_uri.rstrip("/")
        self.timeout = timeout
        # The key may arrive as CONTENT rather than a path. Credentials now
        # live encrypted in the database, and the only way to hand this a path
        # would be to decrypt the key and write it to disk -- which would
        # undo the encryption for as long as that file existed, and longer if
        # anything went wrong before it was cleaned up.
        if private_key_pem is not None:
            raw = (private_key_pem.encode() if isinstance(private_key_pem, str)
                   else private_key_pem)
        elif private_key_path is not None:
            raw = Path(private_key_path).read_bytes()
        else:
            raise KalshiAuthError(
                "no private key given: pass private_key_pem or "
                "private_key_path")
        password = pem_password.encode() if pem_password else None
        try:
            key = serialization.load_pem_private_key(raw, password=password)
        except TypeError as exc:
            # Key is encrypted but no/who password given (or vice versa).
            raise KalshiAuthError(f"PEM password problem: {exc}") from exc
        except ValueError as exc:
            raise KalshiAuthError(f"Could not parse private key PEM: {exc}") from exc
        if not isinstance(key, rsa.RSAPrivateKey):
            raise KalshiAuthError("Private key is not an RSA key")
        self._key = key
        self._session = requests.Session()

    # -- signing --------------------------------------------------------
    def _sign(self, ts_ms: str, method: str, path: str) -> str:
        message = f"{ts_ms}{method}{API_PREFIX}{path}".encode()
        signature = self._key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode()

    def _headers(self, method: str, path: str) -> dict[str, str]:
        ts_ms = str(int(time.time() * 1000))
        return {
            "Content-Type": "application/json",
            "KALSHI-ACCESS-KEY": self.api_key_id,
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,
            "KALSHI-ACCESS-SIGNATURE": self._sign(ts_ms, method, path),
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        url = self.base_uri + path
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                resp = self._session.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=self._headers(method.upper(), path),
                    timeout=self.timeout,
                )
                if resp.status_code < 400:
                    return resp.json() if resp.content else {}
                # 4xx other than 429 will not improve on retry.
                if resp.status_code != 429 and resp.status_code < 500:
                    raise KalshiApiError(resp.status_code, resp.text)
                last_exc = KalshiApiError(resp.status_code, resp.text)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
            time.sleep(0.4 * attempt)
        raise last_exc if last_exc else RuntimeError("unreachable")

    # -- read-only convenience wrappers ---------------------------------
    def balance_cents(self) -> int:
        return int(self.request("GET", "/portfolio/balance").get("balance", 0))

    def portfolio(self) -> dict[str, float]:
        """Cash, open-position market value, and their total, in dollars.

        Same definition the bots use for [TARGET-PV] (see bot_kalshi_main
        ``_portfolio_value``): Kalshi's /portfolio/balance returns settled cash
        as ``balance`` and the mark-to-market value of open positions as
        ``portfolio_value``, both in CENTS. Total = the two summed, so this
        moves with open positions rather than only on settlement.
        """
        d = self.request("GET", "/portfolio/balance")
        cash = float(d.get("balance", 0)) / 100.0
        positions = float(d.get("portfolio_value", 0)) / 100.0
        return {
            "cash_usd": round(cash, 2),
            "positions_usd": round(positions, 2),
            "total_usd": round(cash + positions, 2),
        }

    def exchange_status(self) -> dict[str, Any]:
        return self.request("GET", "/exchange/status")

    # Hard ceiling on cursor-following: 10 pages x limit. Protects against a
    # runaway cursor while still covering accounts far past one page.
    _MAX_PAGES = 10

    def _paged(self, path: str, key: str, params: dict[str, Any]) -> list[dict]:
        """Follow Kalshi's cursor until exhausted (or _MAX_PAGES)."""
        out: list[dict] = []
        cursor: str | None = None
        for _ in range(self._MAX_PAGES):
            p = dict(params)
            if cursor:
                p["cursor"] = cursor
            data = self.request("GET", path, params=p)
            out.extend(data.get(key) or [])
            cursor = data.get("cursor")
            if not cursor:
                break
        return out

    def positions(self, ticker: str | None = None, limit: int = 100) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        return self._paged("/portfolio/positions", "market_positions", params)

    def fills(self, ticker: str | None = None, limit: int = 100) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        return self._paged("/portfolio/fills", "fills", params)

    def settlements(self, limit: int = 100) -> list[dict]:
        return self._paged("/portfolio/settlements", "settlements", {"limit": limit})

    # -- order books and orders -----------------------------------------
    def orderbook(self, ticker: str, depth: int = 10) -> dict:
        """Resting bids and asks for one market, in dollars.

        Worth reading before sending anything at a combined market: a combo
        created through the collection endpoint is born with an EMPTY book,
        so "the price is 0" and "nobody is quoting" look identical from the
        quote fields alone.
        """
        d = self.request("GET", f"/markets/{ticker}/orderbook",
                         params={"depth": depth})
        return d.get("orderbook") or {}

    def create_order(self, *, ticker: str, side: str, action: str,
                     count: int, order_type: str = "limit",
                     price_c: int | None = None,
                     client_order_id: str | None = None,
                     time_in_force: str | None = None) -> dict:
        """Place one order.

        ``client_order_id`` is passed through to the exchange, which treats it
        as an idempotency key: the same id twice is one order, not two. The
        caller supplies it rather than this method generating one, because a
        retry has to reuse the ORIGINAL id to be absorbed -- generating a
        fresh one here would turn every retry into a second position.
        """
        import uuid

        if order_type != "limit":
            # V2 has no `type` field, and this codebase has never sent a market
            # order -- parley is explicit that a limit is the whole safety
            # story into a thin book. Refusing beats guessing a body shape on
            # a path that spends money.
            raise ValueError(
                f"only limit orders are supported here, not {order_type!r}")
        if price_c is None:
            raise ValueError("a limit order needs a price")

        # The V2 book is SINGLE-SIDED and quoted from the YES leg: `bid` buys
        # YES, `ask` sells YES, and `price` is always the YES price in
        # dollars. A NO order is the complementary YES order at 1 - p.
        #
        # The old body -- side=yes|no, action=buy|sell, yes_price in cents,
        # POSTed to /portfolio/orders -- is the V1 shape, and Kalshi now
        # answers it with HTTP 410 deprecated_v1_order_endpoint. Every parley
        # order was refused for that reason and no other: the account, the
        # credential and the combination were all fine.
        #
        # This mirrors `_mk_order` in the runtime btc15 bot, which has been on
        # V2 all along -- which is why only the backend path was failing.
        if side == "yes":
            v2_side = "bid" if action == "buy" else "ask"
            yes_c = int(price_c)
        else:
            v2_side = "ask" if action == "buy" else "bid"
            yes_c = 100 - int(price_c)

        body: dict[str, Any] = {
            "ticker": ticker,
            "side": v2_side,                        # bid = buy YES
            # Fractional. contracts_fp takes 0.01-contract increments, and a
            # dollar budget almost never divides into whole contracts -- the
            # fills that work on this account are all fractional (85.05,
            # 119.81, 34.11), because they were sized from an amount to spend
            # rather than a number to buy.
            "count": f"{float(count):.2f}",
            "price": f"{yes_c / 100.0:.4f}",        # YES price, in dollars
            "time_in_force": time_in_force or "good_till_canceled",
            # Left as the runtime bot has always sent it. It correlates with
            # the unfilled combo orders on this account, but that is the
            # correlation of a shared cause -- those were all API-placed
            # resting limits -- not the reason: 53 btc15 orders carrying the
            # same value filled normally.
            "self_trade_prevention_type": "taker_at_cross",
            "client_order_id": client_order_id or str(uuid.uuid4()),
        }
        d = self.request("POST", ORDER_CREATE_PATH, json_body=body)
        return d.get("order") or d

    # ---- RFQ: how a combo actually trades --------------------------------
    #
    # A combined market is created on demand and no automated maker follows
    # it, so its book is empty and a limit order into it rests until it
    # expires -- which is what every parley order did while reporting a
    # successful placement. Kalshi's mechanism for a market with no book is
    # to ask for a price: the taker broadcasts an RFQ, makers answer, the
    # taker accepts one, and the fill is immediate.
    #
    # This account's own history shows the difference plainly. Every combo
    # buy that executed was sized by COST, not by count -- 29.82 x $0.320 and
    # 32.84 x $0.290 and 34.11 x $0.279 are all $9.52, three attempts to
    # spend the same amount -- and every one filled at creation. The orders
    # that died were whole-contract limits sent through this client.
    #
    # target_cost_dollars is therefore what gets sent: the stake IS the
    # instruction, and letting the exchange derive the fractional count from
    # it is what produces those numbers.

    def create_rfq(self, *, market_ticker: str, target_cost_dollars: float,
                   rest_remainder: bool = False) -> dict:
        """Ask makers for a price. Returns {"id": ...}. Buys nothing.

        rest_remainder defaults to FALSE. When true, whatever the quote does
        not fill is placed on the public book after the execution timeout --
        and the caller already rests its own limit when no quote is taken, so
        the pair would put TWO orders on one combo and hold double the
        intended position if both filled. One instruction, one order.
        """
        return self.request("POST", "/communications/rfqs", json_body={
            "market_ticker": market_ticker,
            "target_cost_dollars": f"{float(target_cost_dollars):.4f}",
            "rest_remainder": bool(rest_remainder),
            # Only one open RFQ is allowed per market ticker; without this a
            # second pass on the same combo is refused with 409 Conflict.
            "replace_existing": True,
        })

    def account_user_id(self) -> str:
        """This account's user id, fetched once and remembered.

        Quotes cannot be listed without saying whose they are: with neither
        filter the endpoint answers 403 "Either creator_user_id or
        rfq_creator_user_id must be filled", which is a missing parameter
        rather than a permission problem. As the party that raised the RFQ we
        are the rfq_creator.

        It is the ACCOUNT user id, not the public communications id that
        GET /communications/id returns -- passing that one is rejected with
        "You cannot request the quotes of another user". Orders carry it, so
        it is read from there rather than guessed.
        """
        if getattr(self, "_account_user_id", None) is None:
            uid = ""
            for path, key in (("/portfolio/orders", "orders"),
                              ("/portfolio/fills", "fills")):
                try:
                    d = self.request("GET", path, params={"limit": 1})
                except Exception:                       # noqa: BLE001
                    continue
                for row in (d.get(key) or []):
                    uid = row.get("user_id") or ""
                    if uid:
                        break
                if uid:
                    break
            self._account_user_id = uid
        return self._account_user_id

    def rfq_quotes(self, rfq_id: str) -> list[dict]:
        uid = self.account_user_id()
        if not uid:
            raise KalshiApiError(
                400, "no account user id available to list quotes with")
        d = self.request("GET", "/communications/quotes", params={
            "rfq_id": rfq_id, "rfq_creator_user_id": uid,
        })
        return d.get("quotes") or []

    def accept_quote(self, rfq_id: str, quote_id: str, side: str) -> dict:
        if side not in ("yes", "no"):
            raise ValueError(f"accepted_side must be yes or no, not {side!r}")
        return self.request(
            "PUT", f"/communications/rfqs/{rfq_id}/quotes/{quote_id}/accept",
            json_body={"accepted_side": side}) or {}

    def delete_rfq(self, rfq_id: str) -> dict:
        return self.request("DELETE", f"/communications/rfqs/{rfq_id}") or {}

    def cancel_order(self, order_id: str) -> dict:
        return self.request("DELETE", f"/portfolio/orders/{order_id}")

    def orders(self, ticker: str | None = None, status: str | None = None,
               limit: int = 100) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if ticker:
            params["ticker"] = ticker
        if status:
            params["status"] = status
        return self._paged("/portfolio/orders", "orders", params)

    # -- multivariate (combo) markets ------------------------------------
    def multivariate_collections(self, limit: int = 100) -> list[dict]:
        d = self.request("GET", "/multivariate_event_collections",
                         params={"limit": limit})
        return d.get("multivariate_contracts") or []

    def collection_detail(self, collection: str) -> dict:
        """One collection: which events it can host, and how many legs.

        A combined market is not free-form -- it can only be built from events
        the collection lists, between its size_min and size_max. A parlay
        assembled from the best legs on the board will usually fit no
        collection at all, which is why the legs have to be chosen INSIDE one.
        """
        d = self.request("GET",
                         f"/multivariate_event_collections/{collection}")
        body = d.get("multivariate_contract", d)
        return {
            "collection_ticker": collection,
            "series_ticker": body.get("series_ticker", ""),
            "events": set(body.get("associated_event_tickers") or []),
            "size_min": int(body.get("size_min") or 2),
            "size_max": int(body.get("size_max") or 0),
        }

    def create_combined_market(self, collection: str,
                               legs: list[dict]) -> dict:
        """Create-or-return the combined market for a set of legs.

        This is what makes a parlay a parlay. Buying the legs as separate
        contracts would be N independent bets that each pay on their own; a
        combined market is ONE contract that pays only if every leg resolves
        YES, which is the product of the legs and an entirely different
        payout.

        The endpoint is create-or-return: the first caller for a given set of
        legs creates the market and later callers get the same one back, so
        calling it twice is safe. ``with_market_payload`` returns the quotes
        in the same round trip.

        A brand-new combined market is born with an EMPTY order book -- no
        automated maker quotes it -- so its bid and ask come back at zero and
        a market order into it fills nothing. That is the safe outcome rather
        than a bug, but the caller has to know it, which is why the returned
        payload keeps the raw quotes instead of defaulting them to a number.
        """
        legs_body = [{"event_ticker": leg["event_ticker"],
                      "market_ticker": leg["market_ticker"],
                      "side": leg.get("side", "yes")} for leg in legs]
        d = self.request("POST",
                         f"/multivariate_event_collections/{collection}",
                         json_body={"selected_markets": legs_body,
                                    "with_market_payload": True})
        market = d.get("market") or {}
        return {
            "ticker": d.get("market_ticker") or market.get("ticker", ""),
            "event_ticker": d.get("event_ticker", ""),
            "status": str(market.get("status", "")).lower(),
            "yes_bid_dollars": market.get("yes_bid_dollars"),
            "yes_ask_dollars": market.get("yes_ask_dollars"),
        }

    def close(self) -> None:
        self._session.close()
