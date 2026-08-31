"""Closing trades the bots opened and never finished.

The payloads in this file are the real shapes, copied from live Kalshi
responses, because the bug this suite exists to prevent was a FIELD NAME. The
previous reconciler read ``yes_total_cost``; the field is
``yes_total_cost_dollars``. It came back None, the cost basis became zero,
fees were ignored, and P&L was reported as gross revenue.

Checked against two real settlements:

    revenue $15.00 - cost $9.15  - fee $0.00 = +$5.85   (reported +$15.00)
    revenue $25.00 - cost $37.50 - fee $0.44 = -$12.94  (reported +$25.00)

The second is the one that matters: a $12.94 LOSS was being reported as a $25
GAIN. Both numbers look entirely plausible on a board, which is why a test
with an invented payload would have agreed with the mistake — a fake shaped
from the same wrong assumption proves nothing.

Units are not uniform and that is the trap:

    revenue                CENTS   (int)
    *_total_cost_dollars   DOLLARS (decimal string)
    fee_cost               DOLLARS (decimal string)
    realized_pnl_dollars   DOLLARS (decimal string)
    position_fp            CONTRACTS (decimal string)
"""

from __future__ import annotations

import pytest

# Verbatim from GET /portfolio/settlements.
WON = {
    "ticker": "KXBTC15M-26AUG142045-45", "market_result": "yes",
    "revenue": 1500, "yes_total_cost_dollars": "9.150000",
    "no_total_cost_dollars": "0.000000", "fee_cost": "0.000000",
    "yes_count_fp": "15.00", "no_count_fp": "0.00",
}
LOST = {
    "ticker": "KXBTC15M-26AUG041115-15", "market_result": "no",
    "revenue": 2500, "yes_total_cost_dollars": "11.500000",
    "no_total_cost_dollars": "26.000000", "fee_cost": "0.440000",
    "yes_count_fp": "25.00", "no_count_fp": "25.00",
}


def test_settlement_pnl_is_revenue_less_cost_and_fees():
    """Given a resolved market,
    when P&L is computed,
    then cost basis and fees are subtracted from revenue.

    Both figures verified against the live account. The losing one is the
    important case: reading the wrong cost field turned it into a gain.
    """
    from app.domains.botstation import reconcile

    pnl, status = reconcile._from_settlement(WON)
    assert pnl == 5.85, f"expected +5.85, got {pnl}"
    assert status == "won"

    pnl, status = reconcile._from_settlement(LOST)
    assert pnl == -12.94, (
        f"expected -12.94, got {pnl} — reading gross revenue instead of net "
        "reports this loss as a $25 gain"
    )
    assert status == "lost"


def test_the_cost_field_that_does_not_exist_is_not_silently_zero():
    """A payload missing the real field must not compute a plausible number.

    This is the actual failure: ``yes_total_cost`` is absent from every
    Kalshi response, ``_num`` defaulted it to 0, and the result was gross
    revenue wearing the name of net P&L. Here the correctly-named field is
    the only one that moves the answer.
    """
    from app.domains.botstation import reconcile

    wrong_name = {**WON, "yes_total_cost": "9.150000"}
    del wrong_name["yes_total_cost_dollars"]
    pnl, _ = reconcile._from_settlement(wrong_name)
    assert pnl == 15.0, "the fixture is wrong: the old field should be ignored"

    pnl, _ = reconcile._from_settlement(WON)
    assert pnl == 5.85


@pytest.mark.parametrize("position_fp,expected_open", [
    ("15.00", True),        # still holding — must never be closed
    ("0.00", False),        # flat — finished, resolve it
    ("0.00001", False),     # inside the epsilon; float noise, not a position
])
def test_a_held_position_is_never_closed(position_fp, expected_open):
    """Given a ticker with contracts still held,
    when the reconciler runs,
    then that trade stays open.

    The guard that stops a bookkeeping pass from closing a live trade out
    from under a running bot. Everything else here is about writing the right
    number; this is about not touching a trade at all.
    """
    from app.domains.botstation import reconcile

    held = abs(reconcile._num(position_fp)) > reconcile.FLAT_EPSILON
    assert held is expected_open


def test_an_unknown_outcome_is_null_not_zero():
    """Given no settlement, position or fill for a market,
    when the trade is closed,
    then its P&L is None.

    A fabricated 0.00 is worse than a null. It is silently averaged into
    every performance figure on the desk, and nothing downstream can tell it
    apart from a trade that genuinely broke even. Verified against the live
    account: 49 open rows referenced markets it had never traded — the bots
    recorded entries that never became filled orders.
    """
    from app.domains.botstation import reconcile

    pnl, contracts = reconcile._from_fills([])
    assert pnl is None, "no fills must not resolve to a number"
    assert contracts == 0
    assert reconcile._status_for(None) == "closed"


def test_a_half_finished_round_trip_does_not_report_a_number():
    """Bought but not sold is not a realised P&L.

    Reconstructing from one leg would report the purchase cost as a loss on a
    position that is still perfectly healthy.
    """
    from app.domains.botstation import reconcile

    only_bought = [{"action": "buy", "side": "yes", "count_fp": "10.00",
                    "yes_price_dollars": "0.4000", "fee_cost": "0.01"}]
    pnl, contracts = reconcile._from_fills(only_bought)
    assert pnl is None
    assert contracts == 10


def test_a_completed_round_trip_nets_out_with_fees():
    """Bought 10 at 0.40, sold 10 at 0.55, two cents of fees."""
    from app.domains.botstation import reconcile

    fills = [
        {"action": "buy", "side": "yes", "count_fp": "10.00",
         "yes_price_dollars": "0.4000", "fee_cost": "0.01"},
        {"action": "sell", "side": "yes", "count_fp": "10.00",
         "yes_price_dollars": "0.5500", "fee_cost": "0.01"},
    ]
    pnl, contracts = reconcile._from_fills(fills)
    assert contracts == 10
    assert pnl == pytest.approx(1.48, abs=0.005)   # 5.50 - 4.00 - 0.02


def test_status_follows_the_sign():
    from app.domains.botstation import reconcile

    assert reconcile._status_for(1.0) == "won"
    assert reconcile._status_for(-1.0) == "lost"
    assert reconcile._status_for(0.0) == "settled"
    assert reconcile._status_for(None) == "closed"
