"""The LONG-TERM (SIM) venue: an in-house paper broker.

A third venue beside Tradier's live account and its sandbox, labelled
"LONG-TERM (SIM)" wherever it shows -- it is simulated, and never presented
as a real account. ``SimClient`` answers the same calls ``TradierClient``
does (balances, positions, orders, order status, place, cancel), so the venue
seam (execution.venue) hands one out for a simulated credential and nothing
above it changes. Market data -- quotes, chains, expirations, bars -- is
Tradier's own, read through the operator's real credential.

FILLS are judged against those real quotes, on every read, as a broker
would: a limit buy fills once the ask is at or under its limit (at the ask),
a limit sell once the bid is at or over it (at the bid), a market order at
the ask or the bid, a stop once the bid falls to it (at the bid). Only in the
regular session (clock.is_regular_session); a day order left open past its
day expires. A buy needs the cash; a sell may not exceed what is held less
what other working sells already claim -- the same rejections Tradier gives,
raised as a 400 so every caller treats them as "not placed".

The account, holdings and orders are tables (models.SimAccount, SimHolding,
SimOrder), one account per operator, so it survives restarts.
"""

from __future__ import annotations

import logging
from datetime import timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import select

from app.domains.trading.models import SimAccount, SimHolding, SimOrder
from app.domains.trading.risk import clock
from app.platform.db.base import utcnow
from app.platform.db.repository import TenantRepository
from app.platform.db.session import session_scope
from app.services.tradier_client import TradierError

logger = logging.getLogger(__name__)

LABEL = "LONG-TERM (SIM)"
OPTION_MULTIPLIER = 100
WORKING = ("open", "pending")
BUY_SIDES = ("buy", "buy_to_open")
SELL_SIDES = ("sell", "sell_to_close")


def _f(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _mult(asset: str) -> int:
    return OPTION_MULTIPLIER if asset == "option" else 1


def _ct_date(moment):
    """The desk's (Central) date of a naive-UTC moment."""
    return moment.replace(tzinfo=timezone.utc).astimezone(clock.now().tzinfo).date()


def mark_of(quote: dict | None, asset: str) -> float:
    """What a holding is worth now: an option at its mid (else its bid, else
    its last), shares at their last trade (else the mid)."""
    q = quote or {}
    bid, ask, last = _f(q.get("bid")), _f(q.get("ask")), _f(q.get("last"))
    mid = (bid + ask) / 2 if bid > 0 and ask > 0 else 0.0
    if asset == "option":
        return mid or bid or last
    return last or mid


def account(db, tenant_id: str) -> SimAccount | None:
    return db.scalar(TenantRepository(db, tenant_id).query(SimAccount))


class SimClient:
    """A TradierClient's account half, simulated; its market half, Tradier's."""

    def __init__(self, tenant_id: str, data_client):
        self.tenant_id = tenant_id
        self.data = data_client
        self.creds = SimpleNamespace(sandbox=True, account_id=f"SIM-{tenant_id[:8].upper()}")

    def close(self) -> None:
        self.data.close()

    # ---- market data: Tradier's ------------------------------------------------
    def quote(self, symbol: str) -> dict:
        return self.data.quote(symbol)

    def quotes(self, symbols: list[str]) -> list[dict]:
        return self.data.quotes(symbols)

    def chain(self, symbol: str, expiration: str) -> list[dict]:
        return self.data.chain(symbol, expiration)

    def expirations(self, symbol: str) -> list[str]:
        return self.data.expirations(symbol)

    def timesales(self, *args, **kwargs) -> list[dict]:
        return self.data.timesales(*args, **kwargs)

    def market_session(self) -> dict:
        return self.data.market_session()

    def _quotes(self, symbols) -> dict[str, dict]:
        wanted = sorted({s for s in symbols if s})
        if not wanted:
            return {}
        try:
            got = self.data.quotes(wanted)
        except Exception as exc:                        # noqa: BLE001
            logger.info("sim: quotes unavailable (%s)", type(exc).__name__)
            return {}
        return {str(q.get("symbol") or "").upper(): q for q in got}

    # ---- matching ----------------------------------------------------------------
    def _match(self) -> None:
        """Fill whatever the quotes now allow, expire stale day orders."""
        now = utcnow()
        today = clock.today()
        with session_scope() as db:
            repo = TenantRepository(db, self.tenant_id)
            open_orders = db.scalars(repo.query(SimOrder).where(SimOrder.status.in_(WORKING))
                                     .order_by(SimOrder.id)).all()
            if not open_orders:
                return
            for o in open_orders:
                if o.duration == "day" and _ct_date(o.created_at) < today:
                    o.status, o.reason = "expired", "a day order, left open past its day"
            live = [o for o in open_orders if o.status in WORKING]
            if not live or not clock.is_regular_session():
                return
            acct = account(db, self.tenant_id)
            if acct is None:
                return
            quotes = self._quotes(o.symbol for o in live)
            for o in live:
                q = quotes.get(o.symbol.upper())
                if not q:
                    continue
                px = self._fill_price(o, q)
                if px:
                    self._fill(db, acct, o, px, now)

    @staticmethod
    def _fill_price(o: SimOrder, q: dict) -> float | None:
        bid, ask = _f(q.get("bid")), _f(q.get("ask"))
        if o.asset == "equity" and ask <= 0:
            ask = _f(q.get("last"))
        if o.asset == "equity" and bid <= 0:
            bid = _f(q.get("last"))
        if o.side in BUY_SIDES:
            if ask <= 0:
                return None
            if o.order_type == "market":
                return ask
            if o.order_type == "limit" and o.price is not None and ask <= o.price + 1e-9:
                return ask
            return None
        if bid <= 0:
            return None
        if o.order_type == "market":
            return bid
        if o.order_type == "limit" and o.price is not None and bid >= o.price - 1e-9:
            return bid
        if o.order_type == "stop" and o.stop_price is not None and bid <= o.stop_price + 1e-9:
            return bid
        return None

    def _fill(self, db, acct: SimAccount, o: SimOrder, px: float, now) -> None:
        repo = TenantRepository(db, self.tenant_id)
        mult = _mult(o.asset)
        qty = float(o.quantity)
        held = db.scalar(repo.query(SimHolding).where(SimHolding.symbol == o.symbol))
        if o.side in BUY_SIDES:
            cost = px * qty * mult
            if acct.cash + 1e-6 < cost:
                o.status, o.reason = "rejected", "not enough simulated cash at the fill"
                return
            acct.cash = round(acct.cash - cost, 2)
            if held is None:
                held = SimHolding(asset=o.asset, symbol=o.symbol, underlying=o.underlying,
                                  quantity=qty, avg_price=px, opened_at=now)
                repo.add(held)
            else:
                total = held.quantity + qty
                held.avg_price = (held.avg_price * held.quantity + px * qty) / total
                held.quantity = total
            o.realized = None
        else:
            if held is None or held.quantity + 1e-9 < qty:
                o.status, o.reason = "rejected", "selling more than the simulated holding"
                return
            acct.cash = round(acct.cash + px * qty * mult, 2)
            o.realized = round((px - held.avg_price) * qty * mult, 2)
            held.quantity = round(held.quantity - qty, 6)
            if held.quantity <= 1e-9:
                db.delete(held)
        o.status, o.avg_fill_price, o.exec_quantity, o.filled_at = "filled", px, qty, now

    # ---- orders --------------------------------------------------------------------
    def _place(self, *, asset: str, symbol: str, underlying: str, side: str, quantity,
               order_type: str, price, duration: str) -> dict:
        qty = float(quantity)
        if qty <= 0:
            raise TradierError("quantity must be positive", status=400)
        if order_type not in ("market", "limit", "stop"):
            raise TradierError(f"order type {order_type!r} is not supported", status=400)
        if order_type in ("limit", "stop") and (price is None or float(price) <= 0):
            raise TradierError(f"a {order_type} order needs a price", status=400)
        side = side.lower()
        if side not in BUY_SIDES + SELL_SIDES:
            raise TradierError(f"unknown side {side!r}", status=400)
        mult = _mult(asset)
        with session_scope() as db:
            repo = TenantRepository(db, self.tenant_id)
            acct = account(db, self.tenant_id)
            if acct is None:
                raise TradierError("no simulated account for this operator", status=400)
            working = db.scalars(repo.query(SimOrder).where(SimOrder.status.in_(WORKING))).all()
            if side in BUY_SIDES:
                est = float(price) if order_type == "limit" else mark_of(
                    self._quotes([symbol]).get(symbol.upper()), asset)
                committed = sum((w.price or 0) * w.quantity * _mult(w.asset)
                                for w in working if w.side in BUY_SIDES)
                if est <= 0:
                    raise TradierError(f"no price for {symbol} to buy at", status=400)
                if est * qty * mult > acct.cash - committed + 1e-6:
                    raise TradierError(
                        f"not enough simulated buying power: {est * qty * mult:,.2f} needed, "
                        f"{acct.cash - committed:,.2f} available", status=400)
            else:
                held = db.scalar(repo.query(SimHolding).where(SimHolding.symbol == symbol))
                claimed = sum(w.quantity for w in working
                              if w.side in SELL_SIDES and w.symbol == symbol)
                if held is None or held.quantity - claimed + 1e-9 < qty:
                    raise TradierError(
                        f"selling {qty:g} of {symbol}, but only "
                        f"{max(0.0, (held.quantity if held else 0) - claimed):g} is held and "
                        f"not already offered", status=400)
            order = SimOrder(
                asset=asset, symbol=symbol, underlying=underlying, side=side, quantity=qty,
                order_type=order_type,
                price=float(price) if order_type == "limit" else None,
                stop_price=float(price) if order_type == "stop" else None,
                duration=duration if duration in ("day", "gtc") else "day",
                status="open", exec_quantity=0.0)
            repo.add(order)
            db.flush()
            order_id = order.id
        self._match()
        return {"id": order_id, "status": "ok"}

    def place_option_order(self, *, underlying: str, occ_symbol: str, side: str,
                           quantity: int, order_type: str = "limit",
                           price: float | None = None, duration: str = "day") -> dict:
        return self._place(asset="option", symbol=occ_symbol.upper(),
                           underlying=underlying.upper(), side=side, quantity=quantity,
                           order_type=order_type, price=price, duration=duration)

    def place_equity_order(self, *, symbol: str, side: str, quantity: float,
                           order_type: str = "market", price: float | None = None,
                           duration: str = "day") -> dict:
        return self._place(asset="equity", symbol=symbol.upper(), underlying=symbol.upper(),
                           side=side, quantity=quantity, order_type=order_type,
                           price=price, duration=duration)

    @staticmethod
    def _order_view(o: SimOrder) -> dict:
        option = o.asset == "option"
        return {
            "id": o.id, "class": "option" if option else "equity",
            "symbol": o.underlying, "option_symbol": o.symbol if option else None,
            "side": o.side, "quantity": o.quantity, "type": o.order_type,
            "price": o.price, "stop_price": o.stop_price, "duration": o.duration,
            "status": o.status, "avg_fill_price": o.avg_fill_price or 0.0,
            "exec_quantity": o.exec_quantity,
            "remaining_quantity": 0.0 if o.status == "filled" else o.quantity,
            "last_fill_price": o.avg_fill_price or 0.0, "reason_description": o.reason,
            "create_date": o.created_at.isoformat() + "Z" if o.created_at else None,
            "transaction_date": (o.filled_at or o.updated_at).isoformat() + "Z"
            if (o.filled_at or o.updated_at) else None,
            "tag": "sim",
        }

    def orders(self) -> list[dict]:
        self._match()
        with session_scope() as db:
            rows = db.scalars(TenantRepository(db, self.tenant_id).query(SimOrder)
                              .order_by(SimOrder.id.desc()).limit(500)).all()
            return [self._order_view(o) for o in rows]

    def order_status(self, order_id) -> dict:
        self._match()
        with session_scope() as db:
            o = db.scalar(TenantRepository(db, self.tenant_id).query(SimOrder)
                          .where(SimOrder.id == int(order_id)))
            if o is None:
                raise TradierError(f"no simulated order {order_id}", status=404)
            return self._order_view(o)

    def cancel_order(self, order_id) -> dict:
        with session_scope() as db:
            o = db.scalar(TenantRepository(db, self.tenant_id).query(SimOrder)
                          .where(SimOrder.id == int(order_id)))
            if o is None:
                raise TradierError(f"no simulated order {order_id}", status=404)
            if o.status not in WORKING:
                raise TradierError(f"order {order_id} is already {o.status}", status=400)
            o.status, o.reason = "canceled", "canceled"
            return {"id": o.id, "status": "ok"}

    def resting_sells(self, occ_symbol: str) -> list[dict]:
        want = (occ_symbol or "").upper()
        return [o for o in self.orders()
                if o["option_symbol"] == want and o["side"] in SELL_SIDES
                and o["status"] in WORKING]

    # ---- account ---------------------------------------------------------------------
    def positions(self) -> list[dict]:
        self._match()
        with session_scope() as db:
            rows = db.scalars(TenantRepository(db, self.tenant_id).query(SimHolding)
                              .order_by(SimHolding.id)).all()
            return [{"id": h.id, "symbol": h.symbol, "quantity": h.quantity,
                     "cost_basis": round(h.avg_price * h.quantity * _mult(h.asset), 2),
                     "date_acquired": h.opened_at.isoformat() + "Z" if h.opened_at else None}
                    for h in rows]

    def holdings(self) -> list[dict]:
        """Every holding with its mark, value and unrealised P&L -- the board's
        LONG-TERM (SIM) list."""
        self._match()
        with session_scope() as db:
            rows = db.scalars(TenantRepository(db, self.tenant_id).query(SimHolding)
                              .order_by(SimHolding.id)).all()
            held = [(h.asset, h.symbol, h.underlying, h.quantity, h.avg_price, h.opened_at)
                    for h in rows]
        quotes = self._quotes(s for _, s, *_ in held)
        out = []
        for asset, symbol, underlying, qty, avg, opened in held:
            q = quotes.get(symbol.upper())
            mark = mark_of(q, asset) or avg
            mult = _mult(asset)
            prev = _f((q or {}).get("prevclose"))
            out.append({
                "asset": asset, "symbol": symbol, "underlying": underlying,
                "quantity": qty, "avg_price": round(avg, 4), "mark": round(mark, 4),
                "value": round(mark * qty * mult, 2),
                "cost": round(avg * qty * mult, 2),
                "pl": round((mark - avg) * qty * mult, 2),
                "pl_pct": round(100 * (mark / avg - 1), 2) if avg else None,
                "day_change_pct": round(100 * (mark / prev - 1), 2) if prev and asset == "equity" else None,
                "opened_at": opened.isoformat() + "Z" if opened else None,
            })
        return out

    def balances(self) -> dict:
        rows = self.holdings()
        today = clock.today()
        with session_scope() as db:
            repo = TenantRepository(db, self.tenant_id)
            acct = account(db, self.tenant_id)
            cash = float(acct.cash) if acct else 0.0
            label = acct.label if acct else LABEL
            filled = db.scalars(repo.query(SimOrder).where(
                SimOrder.status == "filled",
                SimOrder.filled_at >= utcnow() - timedelta(days=2))).all()
            close_pl = sum(o.realized or 0.0 for o in filled
                           if o.filled_at and _ct_date(o.filled_at) == today)
            working = db.scalars(repo.query(SimOrder).where(SimOrder.status.in_(WORKING))).all()
            committed = sum((w.price or 0) * w.quantity * _mult(w.asset)
                            for w in working if w.side in BUY_SIDES)
        value = sum(r["value"] for r in rows)
        open_pl = sum(r["pl"] for r in rows)
        return {
            "total_equity": round(cash + value, 2),
            "total_cash": round(cash, 2),
            "option_buying_power": round(max(0.0, cash - committed), 2),
            "open_pl": round(open_pl, 2),
            "close_pl": round(close_pl, 2),
            "day_pl": round(open_pl + close_pl, 2),
            "market_value": round(value, 2),
            "account_id": self.creds.account_id,
            "sandbox": True,
            "simulated": True,
            "venue_label": label,
        }


# ---- the account: open it, seed it, choose it ------------------------------------

def is_active(db, tenant_id: str) -> bool:
    """Whether this operator's board trades the simulator rather than
    Tradier's sandbox when it is not live."""
    acct = account(db, tenant_id)
    return bool(acct and acct.active)


def set_active(db, tenant_id: str, active: bool) -> None:
    acct = account(db, tenant_id)
    if acct is None:
        if not active:
            return
        raise ValueError("there is no LONG-TERM (SIM) account yet -- seed it first")
    acct.active = bool(active)


# The starting mix: shares bought at the price of the moment, by weight.
SEED_MIX = (("SPY", 0.25), ("QQQ", 0.20), ("MSFT", 0.15), ("NVDA", 0.15),
            ("AAPL", 0.13), ("GOOGL", 0.12))


def seed(tenant_id: str, data_client, *, total: float, cash: float,
         mix=SEED_MIX) -> dict:
    """Open (or reset) the account at exactly ``total``: ``cash`` in cash and
    the rest in shares of ``mix`` at their current prices -- whole shares, with
    the first name's lot taking the remainder fractionally so the total is
    exact. Holdings and orders are cleared; the account is not made active."""
    invest = round(total - cash, 2)
    if invest < 0:
        raise ValueError("cash cannot exceed the total")
    sim = SimClient(tenant_id, data_client)
    quotes = sim._quotes(sym for sym, _ in mix)
    prices = {sym: mark_of(quotes.get(sym), "equity") for sym, _ in mix}
    missing = [sym for sym, px in prices.items() if px <= 0]
    if missing:
        raise ValueError(f"no price for {', '.join(missing)}")
    lots = {sym: int(invest * w // prices[sym]) for sym, w in mix}
    spent = sum(lots[s] * prices[s] for s in lots)
    first = mix[0][0]
    extra = round((invest - spent) / prices[first], 6)
    lots[first] = lots[first] + extra
    now = utcnow()
    with session_scope() as db:
        repo = TenantRepository(db, tenant_id)
        for row in db.scalars(repo.query(SimHolding)).all():
            db.delete(row)
        for row in db.scalars(repo.query(SimOrder)).all():
            db.delete(row)
        acct = account(db, tenant_id)
        if acct is None:
            acct = SimAccount(label=LABEL, active=False, cash=0.0)
            repo.add(acct)
        acct.cash = round(cash, 2)
        acct.seeded_equity = round(total, 2)
        acct.seeded_at = now
        for sym, qty in lots.items():
            if qty > 0:
                repo.add(SimHolding(asset="equity", symbol=sym, underlying=sym,
                                    quantity=qty, avg_price=prices[sym], opened_at=now))
    return {"total": round(cash + sum(lots[s] * prices[s] for s in lots), 2),
            "cash": round(cash, 2),
            "holdings": {s: {"quantity": lots[s], "price": prices[s],
                             "value": round(lots[s] * prices[s], 2)} for s in lots}}
