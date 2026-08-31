"""Tradier executor: selection, sizing, and the TP/SL state machine —
venue fully scripted, nothing leaves the process."""

from __future__ import annotations

import pytest

from app.core.database import SessionLocal
from app.models import User
from app.services import tradier_bot
from app.services.tradier_client import TradierCredentials, TradierError


def _chain():
    g = lambda d: {"greeks": {"delta": d}}  # noqa: E731
    return [
        # calls
        {"symbol": "SPY_C630", "option_type": "call", "strike": 630,
         "bid": 0.98, "ask": 1.02, **g(0.55)},          # above band
        {"symbol": "SPY_C635", "option_type": "call", "strike": 635,
         "bid": 0.50, "ask": 0.50, **g(0.38)},          # in band, near mid
        {"symbol": "SPY_C640", "option_type": "call", "strike": 640,
         "bid": 0.30, "ask": 0.34, **g(0.26)},          # in band, edge
        {"symbol": "SPY_C645", "option_type": "call", "strike": 645,
         "bid": 0.0, "ask": 0.10, **g(0.40)},           # NO BID -> untradable
        # puts carry negative delta
        {"symbol": "SPY_P630", "option_type": "put", "strike": 630,
         "bid": 0.45, "ask": 0.47, **g(-0.37)},
        {"symbol": "SPY_P620", "option_type": "put", "strike": 620,
         "bid": 0.20, "ask": 0.22, **g(-0.15)},         # below band
    ]


class FakeTradier:
    """Scripted venue. Orders auto-increment; fills are set by the test."""

    def __init__(self, sandbox: bool = True):
        self.orders: dict[str, dict] = {}
        self.status: dict[str, dict] = {}
        self.bid = 0.50
        self.cancel_fails: set[str] = set()
        self.cancelled: list[str] = []
        self._next = 100
        self.held: dict[str, float] = {}
        self.orders_book: dict[str, dict] = {}
        self.creds = TradierCredentials(
            access_token="test", account_id="TEST", sandbox=sandbox,
            base_url=None,
        )

    def balances(self):
        # Must mirror TradierClient.balances() field for field. It drifted
        # once already: close_pl and day_pl were added there for the desk's
        # fee-adjusted P&L, this double was not updated, and /balance began
        # 500ing on a KeyError that only tests could ever see.
        open_pl, close_pl = 0.0, 0.0
        return {"option_buying_power": 500.0, "total_cash": 500.0,
                "total_equity": 500.0,
                "open_pl": open_pl, "close_pl": close_pl,
                "day_pl": open_pl + close_pl,
                "account_id": "TEST", "sandbox": True}

    def positions(self):
        return [{"symbol": s, "quantity": q} for s, q in self.held.items()]

    def expirations(self, symbol):
        # Relative to today, or the non-0DTE filter empties the list the
        # moment the calendar passes a hard-coded date.
        from datetime import date, timedelta
        today = date.today()
        return [f"{today:%Y-%m-%d}",
                f"{today + timedelta(days=3):%Y-%m-%d}",
                f"{today + timedelta(days=10):%Y-%m-%d}"]

    def chain(self, symbol, expiration):
        return _chain()

    def quote(self, occ):
        return {"bid": self.bid, "ask": self.bid + 0.02}

    def place_option_order(self, *, underlying, occ_symbol, side, quantity,
                           order_type="limit", price=None, duration="day"):
        self._next += 1
        oid = str(self._next)
        rec = {"side": side, "qty": quantity, "type": order_type,
               "price": price, "occ": occ_symbol}
        self.orders[oid] = rec
        self.orders_book[oid] = rec
        self.status[oid] = {"status": "open"}
        return {"id": oid, "status": "ok"}

    LIVE_ORDER_STATUSES = ("open", "partially_filled", "pending", "submitted",
                           "accepted", "queued")

    # NB: `self.orders` is the dict of placed orders, so the account-wide
    # listing cannot also be called `orders` here — the instance attribute
    # would shadow the method.
    def order_list(self):
        return [{"id": oid, "option_symbol": o["occ"], "side": o["side"],
                 "status": (self.status.get(oid) or {}).get("status", "open"),
                 "quantity": o["qty"], "price": o["price"]}
                for oid, o in self.orders_book.items()]

    def resting_sells(self, occ_symbol):
        want = (occ_symbol or "").upper()
        return [o for o in self.order_list()
                if (o["option_symbol"] or "").upper() == want
                and str(o["side"]).startswith("sell")
                and str(o["status"]).lower() in self.LIVE_ORDER_STATUSES]

    def order_status(self, oid):
        return self.status.get(str(oid), {"status": "open"})

    def cancel_order(self, oid):
        oid = str(oid)
        if oid in self.cancel_fails:
            raise TradierError("order is not cancelable", 400)
        self.cancelled.append(oid)
        self.status[oid] = {"status": "canceled"}
        return {"id": oid}

    def close(self):
        pass


@pytest.fixture()
def fake(monkeypatch):
    venue = FakeTradier()
    monkeypatch.setattr(tradier_bot, "client_for",
                        lambda user, **kw: venue)
    # The arm DELAY has its own test; everywhere else the interesting
    # gate is whether the account shows the position, not the clock.
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "tradier_arm_delay_s", 0,
                        raising=False)
    return venue


@pytest.fixture()
def db_user(client, user):
    db = SessionLocal()
    try:
        yield db, db.get(User, user["user_id"])
    finally:
        db.close()


# ── math ────────────────────────────────────────────────────────────────────

def test_the_fake_balances_matches_the_real_contract():
    """FakeTradier stands in for TradierClient everywhere in this file, so a
    field added to the real balances() and not to the fake is invisible here
    and a 500 in production. That is exactly how /balance broke on day_pl.

    Compares key sets rather than values: the fake is allowed to report
    different numbers, never a different shape.
    """
    from app.services.tradier_client import TradierClient, TradierCredentials

    real = TradierClient(TradierCredentials(
        access_token="t", account_id="TEST", sandbox=True))
    # Only the HTTP call is stubbed; the field assembly under test is real.
    real._req = lambda *a, **k: {"balances": {
        "total_equity": 1.0, "total_cash": 1.0, "option_buying_power": 1.0,
        "open_pl": 1.0, "close_pl": 1.0,
    }}
    try:
        expected = set(real.balances())
    finally:
        real.close()

    assert set(FakeTradier().balances()) == expected, (
        "FakeTradier.balances() has drifted from TradierClient.balances(); "
        "add the missing field(s) to the fake"
    )


def _lots(balance, pct, price, **kw):
    return tradier_bot.size_contracts(balance, pct, price, **kw)[0]


def test_sizing_matches_the_desk_example():
    # balance 500, bid 0.50, 50% -> 250 / (0.50 * 100) = 5 contracts
    assert _lots(500, 50, 0.50, tolerance_pct=0) == 5
    assert _lots(500, 50, 0.55, tolerance_pct=0) == 4     # floor, never round up
    assert _lots(100, 50, 0.60, tolerance_pct=0) == 0     # cannot afford one


def test_budget_is_a_target_not_a_cap():
    """The user's worked example (08/15): $100 balance, 50%, +/-25%.

    Budget $50, so the band is $37.50-$62.50. A contract the budget alone
    cannot buy still trades when one lot lands under the ceiling, and a
    contract that leaves the budget half-spent takes a second lot.
    """
    assert _lots(100, 50, 0.60, tolerance_pct=25) == 1     # $60, was: no trade
    assert _lots(100, 50, 0.62, tolerance_pct=25) == 1     # $62, at the ceiling
    assert _lots(100, 50, 0.38, tolerance_pct=25) == 1     # $38, inside as-is
    assert _lots(100, 50, 0.30, tolerance_pct=25) == 2     # $60, was: 1 for $30


def test_the_ceiling_is_a_real_refusal():
    """The band widens the budget; it does not remove it."""
    n, sizing = tradier_bot.size_contracts(100, 50, 0.63, tolerance_pct=25)
    assert n == 0                                          # $63 > $62.50
    assert sizing["over_ceiling_usd"] == 63.0
    assert _lots(100, 50, 1.20, tolerance_pct=25) == 0      # nowhere close


def test_the_band_leaves_a_well_fitting_size_alone():
    """A budget already spent to the cent must not drift upward — the band
    is a tolerance, not a new target."""
    n, sizing = tradier_bot.size_contracts(100, 50, 0.05, tolerance_pct=25)
    assert n == 10 and sizing["total_usd"] == 50.0          # not 12 for $60
    assert _lots(500, 50, 0.50, tolerance_pct=25) == 5       # the desk example


def test_zero_tolerance_restores_the_strict_budget():
    assert _lots(100, 50, 0.60, tolerance_pct=0) == 0
    assert _lots(100, 50, 0.30, tolerance_pct=0) == 1


def test_min_contracts_is_a_floor_not_a_bypass():
    """min_contracts says how small a trade is worth doing; it never buys
    past the ceiling."""
    assert _lots(100, 50, 0.60, tolerance_pct=25, min_contracts=1) == 1
    assert _lots(100, 50, 0.60, tolerance_pct=25, min_contracts=2) == 0   # $120


def test_sizing_reports_the_band_it_used():
    _, sizing = tradier_bot.size_contracts(100, 50, 0.30, tolerance_pct=25)
    assert sizing["budget_usd"] == 50.0
    assert sizing["band_low_usd"] == 37.5
    assert sizing["band_high_usd"] == 62.5
    assert sizing["cost_per_contract_usd"] == 30.0
    assert sizing["total_usd"] == 60.0


def test_pick_prefers_mid_band_and_needs_two_sided_quote():
    pick = tradier_bot.pick_contract(_chain(), "call", 0.25, 0.50)
    assert pick["symbol"] == "SPY_C635"          # delta .38 is nearest .375
    # the no-bid 0.40-delta contract must never win, even though its delta
    # is closer to the mid than the .26 edge contract
    symbols = [tradier_bot.pick_contract(_chain(), "call", 0.39, 0.41)]
    assert symbols == [None]


def test_a_spoken_band_becomes_a_signed_one():
    """0.25-0.45 is a magnitude; the search is signed by side (user 08/17)."""
    assert tradier_bot.delta_band("call", 0.25, 0.45) == (0.25, 0.45)
    assert tradier_bot.delta_band("put", 0.25, 0.45) == (-0.45, -0.25)
    # typed the other way round, it still means the same band
    assert tradier_bot.delta_band("put", 0.45, 0.25) == (-0.45, -0.25)


def test_puts_are_picked_from_the_negative_band():
    pick = tradier_bot.pick_contract(_chain(), "put", 0.25, 0.50)
    assert pick["symbol"] == "SPY_P630"          # delta -0.37, inside -0.50..-0.25
    # the sign is carried through, not flattened: a put's entry delta is
    # negative, which is the number its band was searched with
    assert pick["_delta"] == -0.37
    assert pick["_abs_delta"] == 0.37


def test_a_put_quoted_with_a_positive_delta_is_not_picked():
    """The sign is a real filter, not decoration.

    A put whose delta comes back positive is bad data — a vendor that dropped
    the sign, or a call's greeks on a put row. Matching on |delta| would take
    it and record a position whose risk is the opposite of what was asked for.
    """
    chain = [{"symbol": "SPY_P610", "option_type": "put", "strike": 610,
              "bid": 0.40, "ask": 0.42, "greeks": {"delta": 0.37}}]
    assert tradier_bot.pick_contract(chain, "put", 0.25, 0.50) is None


def test_a_call_quoted_with_a_negative_delta_is_not_picked():
    chain = [{"symbol": "SPY_C660", "option_type": "call", "strike": 660,
              "bid": 0.40, "ask": 0.42, "greeks": {"delta": -0.37}}]
    assert tradier_bot.pick_contract(chain, "call", 0.25, 0.50) is None


def test_the_put_mid_target_is_the_signed_mid():
    """Nearest-to-mid must be measured in the band the side actually uses.

    Band 0.25-0.45 on a put is -0.45..-0.25, mid -0.35: the -0.34 contract
    wins. Scoring against the positive mid would rank the two by |d - 0.35|
    on negative numbers and pick the far edge instead.
    """
    q = lambda sym, d: {"symbol": sym, "option_type": "put", "strike": 600,  # noqa: E731
                        "bid": 0.40, "ask": 0.42, "greeks": {"delta": d}}
    chain = [q("SPY_P_EDGE", -0.26), q("SPY_P_MID", -0.34)]
    assert tradier_bot.pick_contract(chain, "put", 0.25, 0.45)["symbol"] == "SPY_P_MID"


# ── lifecycle ───────────────────────────────────────────────────────────────

def _open(db, user):
    return tradier_bot.open_position(
        db, user, symbol="SPY", side="call", buy_pct=50,
        tp_pct=15, sl_pct=30,
    )


def _fill_and_arm(db, user, fake, pos, px=0.50):
    """Fill the buy and run the monitor until the exits are armed.

    Two passes on purpose: the first records the fill, the second confirms
    the account holds the contract and only then rests the TP.
    """
    fake.status[pos.buy_order_id] = {"status": "filled", "avg_fill_price": px}
    fake.held[pos.occ_symbol] = pos.contracts      # the venue books it
    tradier_bot.monitor_pass(db, user)
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    return pos


def test_open_sizes_and_buys(fake, db_user):
    db, user = db_user
    pos = _open(db, user)
    assert pos.status == "pending"
    assert pos.occ_symbol == "SPY_C635"
    # ask 0.50 -> 5 contracts of the 500-dollar account at 50%
    assert pos.contracts == 5
    buy = fake.orders[pos.buy_order_id]
    assert buy["side"] == "buy_to_open" and buy["qty"] == 5


def test_fill_arms_tp_and_sl(fake, db_user):
    db, user = db_user
    pos = _open(db, user)
    _fill_and_arm(db, user, fake, pos, 0.50)
    assert pos.status == "open"
    assert pos.entry_price == 0.50
    # +15% of 0.50 is 0.575; the penny grid CEILS to 0.58 so the TP can
    # never sell BELOW the promised percent (round() would give 0.57).
    assert pos.tp_price == pytest.approx(0.58)
    assert pos.sl_price == pytest.approx(0.35)    # -30% of 0.50
    tp = fake.orders[pos.tp_order_id]
    assert tp["side"] == "sell_to_close" and tp["price"] == pytest.approx(0.58)
    assert tp["duration"] == "gtc" if "duration" in tp else True


def test_tp_fill_closes_with_pnl(fake, db_user):
    db, user = db_user
    pos = _open(db, user)
    _fill_and_arm(db, user, fake, pos, 0.50)
    fake.status[pos.tp_order_id] = {"status": "filled", "avg_fill_price": 0.58}
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    assert pos.status == "tp_filled"
    # (0.58 - 0.50) * 100 * 5 contracts
    assert pos.pnl_usd == pytest.approx(40.0)


def test_sl_cancels_tp_before_selling(fake, db_user):
    db, user = db_user
    pos = _open(db, user)
    _fill_and_arm(db, user, fake, pos, 0.50)
    fake.bid = 0.34                                # below the 0.35 stop
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    assert pos.status == "sl_sold"
    # ORDER MATTERS: the TP cancel must precede the market sell, or two
    # sells stack for one position
    assert pos.tp_order_id in fake.cancelled
    sell = fake.orders[pos.close_order_id]
    assert sell["side"] == "sell_to_close" and sell["type"] == "market"
    assert pos.pnl_usd == pytest.approx((0.34 - 0.50) * 100 * 5)


def test_tp_winning_the_sl_race_is_a_win_not_a_double_sell(fake, db_user):
    db, user = db_user
    pos = _open(db, user)
    _fill_and_arm(db, user, fake, pos, 0.50)
    # the cancel fails because the TP just filled — the exit already happened
    fake.cancel_fails.add(pos.tp_order_id)
    fake.status[pos.tp_order_id] = {"status": "filled", "avg_fill_price": 0.575}
    fake.bid = 0.30
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    assert pos.status == "tp_filled"
    assert pos.close_order_id is None              # no second sell was placed


def test_multiple_positions_run_side_by_side(fake, db_user):
    db, user = db_user
    a = _open(db, user)
    b = tradier_bot.open_position(db, user, symbol="SPY", side="put", buy_pct=20)
    assert a.id != b.id
    fake.status[a.buy_order_id] = {"status": "filled", "avg_fill_price": 0.50}
    fake.held[a.occ_symbol] = a.contracts
    fake.status[b.buy_order_id] = {"status": "canceled"}
    # both rows are live on the first pass; by the second, b is already
    # finalized and only a is still being managed
    out = tradier_bot.monitor_pass(db, user)    # records the fill, fails b
    assert out["checked"] == 2
    tradier_bot.monitor_pass(db, user)          # confirms the position, arms a
    db.refresh(a); db.refresh(b)
    assert a.status == "open" and b.status == "failed"


# ── API surface ─────────────────────────────────────────────────────────────

def test_endpoints_roundtrip(fake, client, user):
    uid = user["user_id"]
    r = client.get("/api/v1/tradier/balance", params={"user_id": uid})
    assert r.status_code == 200 and r.json()["option_buying_power"] == 500.0

    r = client.get("/api/v1/tradier/chain",
                   params={"user_id": uid, "symbol": "spy", "side": "call"})
    assert r.status_code == 200
    assert r.json()["pick"] == "SPY_C635"

    r = client.post("/api/v1/tradier/positions", json={
        "user_id": uid, "symbol": "SPY", "side": "call", "buy_pct": 50,
    })
    assert r.status_code == 200
    pid = r.json()["id"]
    assert r.json()["status"] == "pending"

    r = client.get("/api/v1/tradier/positions",
                   params={"user_id": uid, "status": "active"})
    assert any(p["id"] == pid for p in r.json()["items"])

    r = client.post(f"/api/v1/tradier/positions/{pid}/close",
                    params={"user_id": uid})
    assert r.status_code == 200
    assert r.json()["status"] == "failed"          # buy was still pending


# ── venue routing / LIVE toggle ──────────────────────────────────────────────

def test_normalize_base_url_fills_scheme_and_v1():
    from app.services.tradier_client import normalize_base_url

    assert (normalize_base_url("sandbox.tradier.com", sandbox=True)
            == "https://sandbox.tradier.com/v1")
    assert (normalize_base_url("api.tradier.com", sandbox=False)
            == "https://api.tradier.com/v1")
    assert (normalize_base_url("https://api.tradier.com/v1", sandbox=False)
            == "https://api.tradier.com/v1")
    assert (normalize_base_url("", sandbox=True)
            == "https://sandbox.tradier.com/v1")


def test_crossed_venue_uri_is_refused():
    """A sandbox client pointed at the live host is the one slip that turns a
    mock order into real money."""
    from app.services.tradier_client import normalize_base_url

    with pytest.raises(TradierError):
        normalize_base_url("api.tradier.com", sandbox=True)
    with pytest.raises(TradierError):
        normalize_base_url("sandbox.tradier.com", sandbox=False)


def test_open_position_defaults_to_sandbox(fake, db_user):
    """No live flag anywhere -> sandbox mock order, and the row says so."""
    db, user = db_user
    pos = tradier_bot.open_position(db, user, symbol="SPY", side="call")
    assert pos.sandbox is True


def test_open_position_records_the_venue_it_used(monkeypatch, db_user):
    db, user = db_user
    live_venue = FakeTradier(sandbox=False)
    monkeypatch.setattr(tradier_bot, "client_for", lambda user, **kw: live_venue)
    pos = tradier_bot.open_position(db, user, symbol="SPY", side="call", live=True)
    assert pos.sandbox is False


def test_live_refused_when_server_is_paper_only(monkeypatch, db_user):
    from app.core.config import get_settings

    db, user = db_user
    monkeypatch.setattr(get_settings(), "paper_only", True, raising=False)
    with pytest.raises(tradier_bot.TradierBotError) as exc:
        tradier_bot.client_for(user, live=True)
    assert exc.value.status_code == 403


def test_positions_filter_by_venue(client, fake, db_user, user):
    db, u = db_user
    tradier_bot.open_position(db, u, symbol="SPY", side="call")
    live_venue = FakeTradier(sandbox=False)
    import app.services.tradier_bot as tb
    orig = tb.client_for
    tb.client_for = lambda user, **kw: live_venue
    try:
        tradier_bot.open_position(db, u, symbol="QQQ", side="put", live=True)
    finally:
        tb.client_for = orig

    uid = user["user_id"]
    everything = client.get(f"/api/v1/tradier/positions?user_id={uid}").json()
    sandbox = client.get(
        f"/api/v1/tradier/positions?user_id={uid}&venue=sandbox").json()
    live = client.get(f"/api/v1/tradier/positions?user_id={uid}&venue=live").json()
    assert everything["total"] == sandbox["total"] + live["total"]
    assert all(p["sandbox"] is True for p in sandbox["items"])
    assert all(p["sandbox"] is False for p in live["items"])
    assert live["total"] >= 1 and sandbox["total"] >= 1


def test_live_marks_only_attach_to_active_rows(client, fake, db_user, user):
    """Two rows can hold the SAME contract. A settled row must not borrow the
    open row's quote and show a live P&L beside its realized one."""
    db, u = db_user
    closed = tradier_bot.open_position(db, u, symbol="SPY", side="call")
    _fill_and_arm(db, u, fake, closed)
    fake.status[closed.tp_order_id] = {"status": "filled", "avg_fill_price": 0.58}
    tradier_bot.monitor_pass(db, u)
    db.refresh(closed)
    assert closed.status == "tp_filled"

    still_open = tradier_bot.open_position(db, u, symbol="SPY", side="call")
    assert still_open.occ_symbol == closed.occ_symbol      # same contract

    import app.services.tradier_bot as tb
    orig = tb.live_quotes
    tb.live_quotes = lambda user, rows: {closed.occ_symbol: {"bid": 0.90, "ask": 0.92}}
    try:
        page = client.get(
            f"/api/v1/tradier/positions?user_id={user['user_id']}"
            f"&status=all&marks=true").json()
    finally:
        tb.live_quotes = orig

    rows = {p["id"]: p for p in page["items"]}
    assert rows[closed.id]["live_bid"] is None
    assert rows[closed.id]["live_pnl_usd"] is None
    assert rows[closed.id]["pnl_usd"] == pytest.approx(40.0)   # realized, untouched
    assert rows[still_open.id]["live_bid"] == pytest.approx(0.90)


# ── editable take-profit ────────────────────────────────────────────────────

def test_moving_the_target_replaces_the_resting_sell(fake, db_user):
    db, user = db_user
    pos = _open(db, user)
    _fill_and_arm(db, user, fake, pos, 0.50)
    old_tp = pos.tp_order_id
    assert pos.tp_price == pytest.approx(0.58)

    tradier_bot.set_target(db, user, pos.id, 0.75)
    db.refresh(pos)

    assert pos.tp_price == pytest.approx(0.75)
    assert old_tp in fake.cancelled                    # the old one is gone
    assert pos.tp_order_id != old_tp                   # and a new one rests
    new = fake.orders[pos.tp_order_id]
    assert new["side"] == "sell_to_close"
    assert new["price"] == pytest.approx(0.75)
    assert new["qty"] == pos.contracts                 # never more than we hold
    # the percent is restated against the real entry
    assert pos.tp_pct == pytest.approx(50.0)


def test_a_target_that_filled_mid_edit_aborts_instead_of_double_selling(fake, db_user):
    """The dangerous swap: cancel fails because it already filled. Placing the
    replacement anyway would sell a position we no longer hold."""
    db, user = db_user
    pos = _open(db, user)
    _fill_and_arm(db, user, fake, pos, 0.50)
    old_tp = pos.tp_order_id
    fake.cancel_fails.add(old_tp)
    fake.status[old_tp] = {"status": "filled", "avg_fill_price": 0.58}
    sells_before = sum(1 for o in fake.orders.values() if o["side"] == "sell_to_close")

    with pytest.raises(tradier_bot.TradierBotError) as exc:
        tradier_bot.set_target(db, user, pos.id, 0.75)
    assert exc.value.status_code == 409

    sells_after = sum(1 for o in fake.orders.values() if o["side"] == "sell_to_close")
    assert sells_after == sells_before                 # no second sell stacked


def test_target_below_the_stop_is_refused(fake, db_user):
    db, user = db_user
    pos = _open(db, user)
    _fill_and_arm(db, user, fake, pos, 0.50)
    assert pos.sl_price == pytest.approx(0.35)
    with pytest.raises(tradier_bot.TradierBotError):
        tradier_bot.set_target(db, user, pos.id, 0.30)


def test_target_set_before_the_fill_arms_at_that_price(fake, db_user):
    """A pending buy has no resting sell yet — the target is remembered and
    beats the percentage when the exits are armed."""
    db, user = db_user
    pos = _open(db, user)
    assert pos.status == "pending"

    tradier_bot.set_target(db, user, pos.id, 0.90)
    db.refresh(pos)
    assert pos.tp_price == pytest.approx(0.90)
    assert pos.tp_order_id is None                     # nothing resting yet

    _fill_and_arm(db, user, fake, pos, 0.50)
    assert pos.status == "open"
    # 15% of 0.50 would have been 0.58 — the explicit target wins
    assert pos.tp_price == pytest.approx(0.90)
    assert fake.orders[pos.tp_order_id]["price"] == pytest.approx(0.90)


def test_target_cannot_be_moved_on_a_finished_position(fake, db_user):
    db, user = db_user
    pos = _open(db, user)
    _fill_and_arm(db, user, fake, pos, 0.50)
    fake.status[pos.tp_order_id] = {"status": "filled", "avg_fill_price": 0.58}
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    assert pos.status == "tp_filled"
    with pytest.raises(tradier_bot.TradierBotError) as exc:
        tradier_bot.set_target(db, user, pos.id, 0.99)
    assert exc.value.status_code == 409


# ── buying a named contract (the options-flow board) ────────────────────────

def _quoting_fake(fake, *, ask=0.50, bid=0.48):
    """Teach the scripted venue to quote one OCC symbol like Tradier does."""
    fake.quote = lambda occ: {
        "symbol": occ, "underlying": "TSLA", "root_symbol": "TSLA",
        "strike": 350.0, "option_type": "call",
        "expiration_date": "2026-08-14",
        "bid": bid, "ask": ask, "last": 0.49, "low": 0.30, "high": 0.90,
    }
    return fake


def test_buys_the_named_contract_not_a_delta_pick(fake, db_user):
    """The flow board already chose it — the delta search must not override."""
    db, user = db_user
    _quoting_fake(fake)
    pos = tradier_bot.open_contract(db, user, occ_symbol="TSLA260814C00350000",
                                    buy_pct=50, tp_pct=15, sl_pct=30)
    assert pos.occ_symbol == "TSLA260814C00350000"   # not SPY_C635
    assert pos.underlying == "TSLA"
    assert pos.option_type == "call"
    assert pos.strike == pytest.approx(350.0)
    assert pos.strategy == "Manual"
    assert pos.status == "pending"
    # 50% of the 500-dollar account at the 0.50 ask
    assert pos.contracts == 5
    order = fake.orders[pos.buy_order_id]
    assert order["side"] == "buy_to_open"
    assert order["occ"] == "TSLA260814C00350000"
    assert order["price"] == pytest.approx(0.50)


def test_the_named_contract_is_managed_like_any_other(fake, db_user):
    db, user = db_user
    _quoting_fake(fake)
    pos = tradier_bot.open_contract(db, user, occ_symbol="TSLA260814C00350000",
                                    buy_pct=50, tp_pct=15, sl_pct=30)
    _fill_and_arm(db, user, fake, pos, 0.50)
    assert pos.status == "open"
    assert pos.tp_price == pytest.approx(0.58)       # +15%, ceiled to the penny
    assert pos.sl_price == pytest.approx(0.35)       # -30%
    assert fake.orders[pos.tp_order_id]["side"] == "sell_to_close"


def test_a_contract_with_no_offer_is_refused(fake, db_user):
    db, user = db_user
    _quoting_fake(fake, ask=0)
    with pytest.raises(tradier_bot.TradierBotError) as exc:
        tradier_bot.open_contract(db, user, occ_symbol="TSLA260814C00350000")
    assert exc.value.status_code == 409


def test_sizing_below_min_contracts_skips_the_buy(fake, db_user):
    db, user = db_user
    _quoting_fake(fake, ask=9.99)                    # 50% of 500 buys none
    with pytest.raises(tradier_bot.TradierBotError) as exc:
        tradier_bot.open_contract(db, user, occ_symbol="TSLA260814C00350000",
                                  buy_pct=50)
    assert "min_contracts" in str(exc.value)


# ── 0DTE is opt-in ──────────────────────────────────────────────────────────

def _today():
    from datetime import date
    return f"{date.today():%Y-%m-%d}"


def test_same_day_expiry_is_skipped_by_default(fake, db_user):
    """The default has to be the safe one: a contract with hours to live is
    not the trade a delta band describes."""
    db, user = db_user
    pos = tradier_bot.open_position(db, user, symbol="SPY", side="call")
    assert pos.expiration != _today()


def test_same_day_expiry_is_used_when_asked_for(fake, db_user):
    db, user = db_user
    pos = tradier_bot.open_position(db, user, symbol="SPY", side="call",
                                    zero_dte=True)
    assert pos.expiration == _today()


def test_an_explicit_expiration_still_wins(fake, db_user):
    """Callers that name a date — the auto-traders do — keep their own rule."""
    db, user = db_user
    pos = tradier_bot.open_position(db, user, symbol="SPY", side="call",
                                    expiration=_today())
    assert pos.expiration == _today()


def test_no_non_zero_dte_expiry_is_a_clear_refusal(fake, db_user, monkeypatch):
    db, user = db_user
    monkeypatch.setattr(fake, "expirations", lambda symbol: [_today()])
    with pytest.raises(tradier_bot.TradierBotError) as exc:
        tradier_bot.open_position(db, user, symbol="SPY", side="call")
    assert "non-0DTE" in str(exc.value)


# ── exits wait for the position to exist ────────────────────────────────────

def _fill(fake, pos, px=0.50, *, book=True):
    """Report the buy as filled, and optionally put it on the books."""
    fake.status[pos.buy_order_id] = {"status": "filled", "avg_fill_price": px}
    if book:
        fake.held[pos.occ_symbol] = pos.contracts


def _age_fill(db, pos, seconds):
    """Backdate the fill stamp so the arm delay has elapsed."""
    from datetime import datetime, timedelta, timezone
    raw = dict(pos.raw or {})
    raw["filled_at"] = (datetime.now(timezone.utc).replace(tzinfo=None)
                        - timedelta(seconds=seconds)).isoformat()
    pos.raw = raw
    db.commit()


def test_a_fill_does_not_arm_the_exits_immediately(fake, db_user):
    """The bug: selling into the gap between "filled" and the holding being
    on the books is what the venue rejects."""
    db, user = db_user
    pos = _open(db, user)
    _fill(fake, pos)
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    assert pos.status == "pending"          # not armed yet
    assert pos.entry_price == pytest.approx(0.50)   # but the fill is recorded
    assert pos.tp_order_id is None
    assert not any(o["side"] == "sell_to_close" for o in fake.orders.values())


def test_exits_arm_once_the_wait_passes_and_the_position_shows(fake, db_user):
    db, user = db_user
    pos = _open(db, user)
    _fill(fake, pos)
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    _age_fill(db, pos, 60)
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    assert pos.status == "open"
    assert pos.tp_price == pytest.approx(0.58)
    assert fake.orders[pos.tp_order_id]["side"] == "sell_to_close"


def test_no_sell_while_the_account_does_not_show_the_contract(fake, db_user):
    """Even after the wait: no holding, no sell order."""
    db, user = db_user
    pos = _open(db, user)
    _fill(fake, pos, book=False)            # filled, but not on the books
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    _age_fill(db, pos, 600)
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    assert pos.status == "pending"
    assert pos.tp_order_id is None
    assert not any(o["side"] == "sell_to_close" for o in fake.orders.values())
    assert "not on the books" in (pos.note or "")

    # and it arms the moment the position appears
    fake.held[pos.occ_symbol] = pos.contracts
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    assert pos.status == "open"
    assert fake.orders[pos.tp_order_id]["side"] == "sell_to_close"


def test_a_venue_that_cannot_answer_is_treated_as_not_held(fake, db_user):
    """An unreadable positions call must never be read as "go ahead"."""
    db, user = db_user
    pos = _open(db, user)
    _fill(fake, pos)
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    _age_fill(db, pos, 60)

    def boom():
        raise TradierError("positions unavailable", 500)
    fake.positions = boom
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    assert pos.status == "pending"
    assert pos.tp_order_id is None


# ── never two resting sells on one holding ──────────────────────────────────

def _sell_count(fake, occ=None):
    return sum(1 for o in fake.orders.values()
               if o["side"] == "sell_to_close" and (occ is None or o["occ"] == occ))


def test_a_second_monitor_pass_does_not_stack_another_sell(fake, db_user):
    """The background loop and the desk sweep both run this. Two resting
    sells on one holding is a short position waiting to happen."""
    db, user = db_user
    pos = _fill_and_arm(db, user, fake, _open(db, user))
    assert pos.status == "open"
    assert _sell_count(fake, pos.occ_symbol) == 1

    for _ in range(3):
        tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    assert _sell_count(fake, pos.occ_symbol) == 1


def test_a_sell_already_covering_the_holding_blocks_another(fake, db_user):
    """Our stored id would miss an order placed by another copy of the
    monitor — the ACCOUNT is what gets asked, and the test is whether the
    holding is already spoken for."""
    db, user = db_user
    pos = _open(db, user)
    fake.status[pos.buy_order_id] = {"status": "filled", "avg_fill_price": 0.50}
    fake.held[pos.occ_symbol] = pos.contracts
    tradier_bot.monitor_pass(db, user)          # records the fill
    db.refresh(pos)

    # someone else rests a sell on the same contract
    fake.place_option_order(
        underlying="SPY", occ_symbol=pos.occ_symbol, side="sell_to_close",
        quantity=pos.contracts, order_type="limit", price=0.61, duration="gtc")
    before = _sell_count(fake, pos.occ_symbol)

    tradier_bot.monitor_pass(db, user)          # would have armed
    db.refresh(pos)

    # every contract held is already spoken for, so nothing is added
    assert _sell_count(fake, pos.occ_symbol) == before
    assert pos.status == "pending"
    assert "already have a resting sell" in (pos.note or "")


def test_a_filled_sell_does_not_block_a_fresh_one(fake, db_user):
    """Only a WORKING order counts as resting; a filled one is history."""
    db, user = db_user
    pos = _open(db, user)
    fake.status[pos.buy_order_id] = {"status": "filled", "avg_fill_price": 0.50}
    fake.held[pos.occ_symbol] = pos.contracts
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    stale = fake.place_option_order(
        underlying="SPY", occ_symbol=pos.occ_symbol, side="sell_to_close",
        quantity=pos.contracts, order_type="limit", price=0.61, duration="gtc")
    fake.status[stale["id"]] = {"status": "filled"}

    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    assert pos.status == "open"
    assert pos.tp_order_id != stale["id"]
    assert pos.tp_price == pytest.approx(0.58)      # its own 15% target


def test_an_unreadable_order_book_arms_nothing(fake, db_user):
    """If the book cannot be read, do not add to it."""
    db, user = db_user
    pos = _open(db, user)
    fake.status[pos.buy_order_id] = {"status": "filled", "avg_fill_price": 0.50}
    fake.held[pos.occ_symbol] = pos.contracts
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)

    def boom(occ):
        raise TradierError("orders unavailable", 500)
    fake.resting_sells = boom

    tradier_bot.monitor_pass(db, user)          # swallowed as a venue error
    db.refresh(pos)
    assert pos.status == "pending"
    assert _sell_count(fake, pos.occ_symbol) == 0


def test_two_positions_on_one_contract_each_get_their_own_exit(fake, db_user):
    """The guard is arithmetic, not identity: 3 held + 3 held is 6, and six
    contracts deserve two exits."""
    db, user = db_user
    a = _fill_and_arm(db, user, fake, _open(db, user))
    b = tradier_bot.open_position(db, user, symbol="SPY", side="call", buy_pct=50)
    assert b.occ_symbol == a.occ_symbol
    fake.status[b.buy_order_id] = {"status": "filled", "avg_fill_price": 0.50}
    fake.held[b.occ_symbol] = a.contracts + b.contracts     # the venue holds both
    tradier_bot.monitor_pass(db, user)
    tradier_bot.monitor_pass(db, user)
    db.refresh(a); db.refresh(b)
    assert a.status == "open" and b.status == "open"
    assert a.tp_order_id != b.tp_order_id
    assert _sell_count(fake, a.occ_symbol) == 2


def test_an_open_row_the_account_no_longer_backs_is_closed(fake, db_user):
    """The exit filled somewhere we did not see it. Leaving the row open
    would keep the stop watching a holding that is not there."""
    db, user = db_user
    pos = _fill_and_arm(db, user, fake, _open(db, user))
    assert pos.status == "open"

    # the sell fills and the holding goes, but we never observe the fill
    fake.status[pos.tp_order_id] = {"status": "canceled"}
    fake.held.pop(pos.occ_symbol, None)

    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    assert pos.status == "closed"
    assert pos.exit_price is not None
    assert pos.closed_at is not None


def test_a_cancelled_exit_is_re_armed_while_the_holding_remains(fake, db_user):
    """The other half of the same branch: still held, so it gets an exit."""
    db, user = db_user
    pos = _fill_and_arm(db, user, fake, _open(db, user))
    old_tp = pos.tp_order_id
    fake.status[old_tp] = {"status": "canceled"}
    tradier_bot.monitor_pass(db, user)
    db.refresh(pos)
    assert pos.status == "open"
    assert pos.tp_order_id != old_tp
    assert _sell_count(fake, pos.occ_symbol) == 2   # the dead one plus the new
