"""A broker that does not exist, behaving predictably.

The suite has to be able to place an order without a Tradier account, a
network, or anyone's money. Everything outbound goes through
``app.domains.trading.execution.venue``, so substituting that one module
substitutes the whole boundary — which is the reason it was built as
module-level functions rather than an object graph.

This fake is deliberately NOT clever. It fills nothing on its own, moves no
prices, and simulates no latency. Tests that need a fill say so explicitly, so
what is being asserted stays visible in the test rather than hidden in here.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field


@dataclass
class FakeVenue:
    """One account's worth of state, in memory."""

    option_buying_power: float = 10_000.0
    held: dict[str, float] = field(default_factory=dict)
    orders: dict[str, dict] = field(default_factory=dict)
    bids: dict[str, float] = field(default_factory=dict)
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1))
    # Set by a test that wants the next place_stop to be refused, which is how
    # "the venue would not rest a stop" is exercised without a real venue.
    refuse_stop: bool = False

    def next_id(self, prefix: str) -> str:
        return f"{prefix}-{next(self._ids)}"

    # ---- chain ----------------------------------------------------------
    def chain(self, symbol: str, expiration: str) -> list[dict]:
        """A small, deterministic chain with real signed deltas.

        Puts carry NEGATIVE deltas, because that is the thing the selection
        code has to get right and a fake that returned magnitudes would let
        the bug back in without any test noticing.
        """
        out = []
        for i, strike in enumerate((440, 445, 450, 455, 460)):
            for side in ("call", "put"):
                delta = 0.15 + i * 0.10
                out.append({
                    "symbol": f"{symbol}{expiration.replace('-', '')}"
                              f"{'C' if side == 'call' else 'P'}{strike}",
                    "option_type": side,
                    "strike": float(strike),
                    "expiration_date": expiration,
                    "bid": 1.00 + i * 0.10,
                    "ask": 1.06 + i * 0.10,
                    "greeks": {"delta": delta if side == "call" else -delta},
                })
        return out


_ACCOUNTS: dict[str, FakeVenue] = {}


def account_for(cred) -> FakeVenue:
    """One fake account per credential token, so two operators are distinct."""
    return _ACCOUNTS.setdefault(cred.token, FakeVenue())


def reset() -> None:
    _ACCOUNTS.clear()


# ---- the substituted venue functions -------------------------------------

def install(monkeypatch) -> None:
    """Point the venue seam at the fake, for the whole test."""
    from app.domains.trading.execution import venue

    def expirations(symbol, *, cred=None, sandbox=True):
        from app.domains.trading.risk import clock
        from datetime import timedelta
        today = clock.today()
        # Today plus a few days out, so 0DTE and non-0DTE both have a target.
        return [(today + timedelta(days=d)).isoformat() for d in (0, 2, 7, 30)]

    def option_chain(symbol, expiration, *, cred=None, sandbox=True):
        return account_for(cred).chain(symbol, expiration)

    def balance(*, cred=None, sandbox=True):
        return {"option_buying_power": account_for(cred).option_buying_power}

    def held_quantity(occ_symbol, *, cred=None, sandbox=True):
        return account_for(cred).held.get(occ_symbol, 0.0)

    def working_orders_for(occ_symbol, *, cred=None, side=None, sandbox=True):
        acct = account_for(cred)
        return [o for o in acct.orders.values()
                if o["option_symbol"] == occ_symbol
                and o["status"] in ("open", "pending")
                and (side is None or o["side"] == side)]

    def working_orders_after_place(occ_symbol, *, cred=None, side=None, sandbox=True):
        return working_orders_for(occ_symbol, cred=cred, side=side, sandbox=sandbox)

    def resting_sells(occ_symbol, *, cred=None, sandbox=True):
        return working_orders_for(occ_symbol, cred=cred, side="sell_to_close",
                                  sandbox=sandbox)

    def order_status(order_id, *, cred=None, sandbox=True):
        return account_for(cred).orders.get(order_id, {"status": "open"})

    def bid_for(occ_symbol, *, cred=None, sandbox=True):
        return account_for(cred).bids.get(occ_symbol)

    def _place(cred, *, side, occ_symbol, quantity, prefix, **kw):
        acct = account_for(cred)
        oid = acct.next_id(prefix)
        acct.orders[oid] = {"id": oid, "option_symbol": occ_symbol,
                            "side": side, "quantity": quantity,
                            "status": "open", **kw}
        return venue.PlacedOrder(oid, "open", acct.orders[oid])

    def place_buy(*, cred, underlying, occ_symbol, quantity, price, sandbox=True):
        return _place(cred, side="buy_to_open", occ_symbol=occ_symbol,
                      quantity=quantity, prefix="buy", price=price)

    def place_sell(*, cred, underlying, occ_symbol, quantity, price,
                   duration="gtc", sandbox=True):
        return _place(cred, side="sell_to_close", occ_symbol=occ_symbol,
                      quantity=quantity, prefix="tp", price=price)

    def place_stop(*, cred, underlying, occ_symbol, quantity, stop_price,
                   sandbox=True):
        if account_for(cred).refuse_stop:
            raise RuntimeError("venue refused the stop order")
        return _place(cred, side="sell_to_close", occ_symbol=occ_symbol,
                      quantity=quantity, prefix="stop", stop_price=stop_price)

    def sell_to_close(*, cred, underlying, occ_symbol, quantity, price=None,
                      sandbox=True):
        return _place(cred, side="sell_to_close", occ_symbol=occ_symbol,
                      quantity=quantity, prefix="sell", price=price)

    def cancel_order(order_id, *, cred=None, sandbox=True):
        acct = account_for(cred)
        if order_id in acct.orders:
            acct.orders[order_id]["status"] = "canceled"

    for name, fn in (
        ("expirations", expirations), ("option_chain", option_chain),
        ("balance", balance), ("held_quantity", held_quantity),
        ("working_orders_for", working_orders_for),
        ("working_orders_after_place", working_orders_after_place),
        ("resting_sells", resting_sells), ("order_status", order_status),
        ("bid_for", bid_for), ("place_buy", place_buy),
        ("place_sell", place_sell), ("place_stop", place_stop),
        ("sell_to_close", sell_to_close), ("cancel_order", cancel_order),
    ):
        monkeypatch.setattr(venue, name, fn)
