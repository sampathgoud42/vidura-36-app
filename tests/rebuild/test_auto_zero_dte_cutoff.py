"""The auto-trader never buys a same-day contract from 11:50 CST on.

A person may buy 0DTE until 13:00; an unattended trader stops at 11:50. Two
layers hold it: the watcher picks the next expiry from 11:50 (held in
test_autotrade_super_signals), and -- because a decision made at 11:49:59 can
reach the order at 11:50:01 -- the order itself refuses a same-day contract
for any entry labelled Auto/ from 11:50 on, whichever strategy placed it. A
person's cutoff is unchanged.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from datetime import time as dtime

import pytest

from app.domains.trading.execution import orders
from app.domains.trading.risk import clock
from app.domains.trading.risk.validation import RiskRefused

OPEN = "/api/v1/tradier/positions"
BUY_BODY = {"symbol": "SPY", "side": "call", "buy_pct": 10,
            "tp_pct": 15, "sl_pct": 30, "live": False}


@pytest.fixture()
def at(monkeypatch):
    """Pin the desk clock to today at a CST time."""
    def set_time(hh, mm, ss=0):
        moment = datetime.combine(date.today(), dtime(hh, mm, ss), tzinfo=clock.DESK_TZ)
        monkeypatch.setattr(clock, "now", lambda: moment)
        return moment
    return set_time


def test_the_auto_traders_cutoff_is_earlier_than_a_persons():
    assert clock.AUTO_ZERO_DTE_CUTOFF == dtime(11, 50) < clock.ZERO_DTE_CUTOFF


@pytest.mark.parametrize("hh,mm,ss,past", [(11, 49, 59, False), (11, 50, 0, True),
                                           (12, 30, 0, True)])
def test_the_boundary_is_1150_sharp(hh, mm, ss, past):
    moment = datetime.combine(date.today(), dtime(hh, mm, ss), tzinfo=clock.DESK_TZ)
    assert clock.past_auto_zero_dte_cutoff(moment) is past


def _automated_order(strategy: str, expiration: str):
    """The cutoff is among the order's first guards, so an order it refuses
    never reaches the database or the venue -- neither is needed here."""
    return orders.open_position(
        None, tenant_id="t", cred=None, symbol="SPY", side="call",
        occ_symbol=f"SPY{expiration.replace('-', '')[2:]}C00450000", underlying="SPY",
        strike=450.0, expiration=expiration, delta=0.4, contracts=1, limit_price=1.0,
        buy_pct=10, tolerance_pct=25, tp_pct=15, sl_pct=30, sandbox=True,
        strategy=strategy)


@pytest.mark.parametrize("strategy", ["Auto/super_signals", "Auto/best_pairs",
                                      "Auto/10min_intraday_move"])
@pytest.mark.parametrize("hh,mm", [(11, 50), (12, 45)])
def test_an_automated_same_day_order_is_refused_from_1150(at, strategy, hh, mm):
    """Whichever strategy placed it, and even if the watcher decided a moment
    before the cutoff: the order is where the rule is kept."""
    at(hh, mm)
    with pytest.raises(RiskRefused, match="11:50 CST by the auto-trader"):
        _automated_order(strategy, date.today().isoformat())


@pytest.mark.parametrize("hh,mm,ok", [(11, 55, True), (12, 59, True), (13, 5, False)])
def test_a_persons_same_day_buy_keeps_the_1300_cutoff(client, alice, at, hh, mm, ok):
    at(hh, mm)
    r = client.post(OPEN, json={**BUY_BODY, "zero_dte": True},
                    headers={**alice.headers, "Idempotency-Key": uuid.uuid4().hex})
    if ok:
        assert r.status_code == 200, r.text
        assert r.json()["expiration"] == date.today().isoformat()
    else:
        assert r.status_code in (400, 409, 422)
        assert "13:00" in r.json()["detail"]
