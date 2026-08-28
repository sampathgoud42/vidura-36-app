"""Duplicate-free execution — the seven guards from Phase 3.

`open_position` today validates the side, the percentage, the sizing and the
contract pick, then places a real order with no check for an existing
position, no check for a working order, and no idempotency key. A double-tap,
or a mobile retry after the 60-second client timeout, buys twice with real
money.

Each test below names the guard it protects. They are ordered so that the
structural guarantees (1 and 2) come before the confirmations (4 and 5),
because that is the order in which they matter: a uniqueness constraint is a
guarantee, and check-then-act is a race.
"""

from __future__ import annotations

import uuid

import pytest

OPEN = "/api/v1/tradier/positions"
BUY_BODY = {"symbol": "SPY", "side": "call", "buy_pct": 10,
            "tp_pct": 15, "sl_pct": 30, "live": False}


def _buy(client, who, body=None, key=None):
    return client.post(
        OPEN,
        json=body or BUY_BODY,
        headers={**who.headers, "Idempotency-Key": key or uuid.uuid4().hex},
    )


# --------------------------------------------------------------------------
# Guard 1 — idempotency, enforced by a uniqueness constraint
# --------------------------------------------------------------------------

def test_the_same_idempotency_key_never_places_a_second_order(client, alice):
    """Given a buy submitted with key K,
    when the identical request is submitted again with key K,
    then the first order is returned and NO second order is placed.

    This is the double-tap. The second response must describe the first
    order, not a new one.
    """
    key = uuid.uuid4().hex
    first = _buy(client, alice, key=key)
    assert first.status_code in (200, 201), first.text

    second = _buy(client, alice, key=key)
    assert second.status_code in (200, 201, 409)
    assert second.json()["id"] == first.json()["id"], (
        "a repeated idempotency key produced a second position — "
        "the operator has just bought twice"
    )

    listing = client.get(OPEN, headers=alice.headers)
    rows = listing.json()
    rows = rows["items"] if isinstance(rows, dict) else rows
    assert len(rows) == 1


def test_a_retry_without_a_key_is_still_absorbed(client, alice):
    """Given a client that sends no idempotency key,
    when it submits the same buy twice in quick succession,
    then the server's own fingerprint absorbs the retry.

    Not every caller will be updated at once, and the operator's money must
    not depend on which client version they happen to be running.
    """
    first = client.post(OPEN, json=BUY_BODY, headers=alice.headers)
    second = client.post(OPEN, json=BUY_BODY, headers=alice.headers)
    assert first.status_code in (200, 201), first.text
    assert second.json().get("id") == first.json().get("id"), (
        "an unkeyed retry placed a second order"
    )


def test_idempotency_keys_do_not_collide_across_tenants(client, alice, bob):
    """Alice's key K and Bob's key K are different keys.

    The constraint is on (tenant, key). A global key space would let one
    operator's retry silently return another operator's order — a leak
    dressed as a safety feature.
    """
    key = "shared-" + uuid.uuid4().hex
    a = _buy(client, alice, key=key)
    b = _buy(client, bob, key=key)
    assert a.status_code in (200, 201) and b.status_code in (200, 201)
    assert a.json()["id"] != b.json()["id"]


def test_a_different_request_with_a_reused_key_is_refused(client, alice):
    """A key identifies one intent. Reusing it for a different order is a
    client bug, and answering it with the old result would hide that."""
    key = uuid.uuid4().hex
    _buy(client, alice, key=key)
    other = _buy(client, alice, body={**BUY_BODY, "symbol": "QQQ"}, key=key)
    assert other.status_code == 409


# --------------------------------------------------------------------------
# Guard 2 — a lease that holds across processes
# --------------------------------------------------------------------------

def test_concurrent_buys_for_one_contract_produce_one_position(client, alice):
    """Given several identical buys submitted at once,
    when they race,
    then exactly one position exists afterwards.

    Today's protection is an in-process threading lock, which two uvicorn
    workers do not share — and two have run at the same time on this machine
    before.
    """
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: _buy(client, alice), range(6)))

    created = [r for r in results if r.status_code in (200, 201)]
    ids = {r.json()["id"] for r in created}
    assert len(ids) == 1, f"{len(ids)} positions created by a concurrent burst"


def test_a_crashed_lease_holder_does_not_deadlock_the_contract(client, alice):
    """A lease must expire. A process that dies mid-order must not lock its
    contract out until someone notices."""
    from app.domains.trading.execution import leases

    leases.acquire(tenant_id=alice.tenant_id, resource="SPY_TEST", ttl_s=-1)
    assert leases.acquire(tenant_id=alice.tenant_id, resource="SPY_TEST", ttl_s=30)


# --------------------------------------------------------------------------
# Guards 3 and 4 — check our records, then check the venue
# --------------------------------------------------------------------------

def test_buying_a_contract_already_held_is_refused_by_default(client, alice):
    """Given the operator already holds an open position on a contract,
    when they buy it again without asking to add,
    then the request is refused and names the position they already have.

    "You already have this, here it is" is the answer; a second position is
    not.
    """
    first = _buy(client, alice)
    assert first.status_code in (200, 201)

    again = _buy(client, alice)  # fresh key, same contract
    assert again.status_code == 409
    assert str(first.json()["id"]) in again.text, (
        "the refusal did not tell the operator which position they already hold"
    )


def test_adding_to_a_position_is_possible_but_must_be_asked_for(client, alice):
    """The default answers no; the operator can still say yes deliberately."""
    _buy(client, alice)
    added = _buy(client, alice, body={**BUY_BODY, "allow_add": True})
    assert added.status_code in (200, 201)


def test_a_working_order_at_the_venue_blocks_a_second_one(client, alice, monkeypatch):
    """Our database can be wrong: an order can land while the write that
    records it fails. So the venue is asked too, exactly as the sell path
    already asks before resting a second sell.
    """
    from app.domains.trading.execution import venue

    monkeypatch.setattr(
        venue, "working_orders_for",
        lambda *a, **k: [{"id": "already-working", "side": "buy_to_open"}],
    )
    r = _buy(client, alice)
    assert r.status_code == 409
    assert "already-working" in r.text or "working order" in r.text.lower()


# --------------------------------------------------------------------------
# Guard 5 — settle, then confirm
# --------------------------------------------------------------------------

def test_an_unexpected_second_order_is_cancelled_and_flagged(client, alice, monkeypatch):
    """Given the post-placement check finds two working orders for one
    contract, when the settle step runs, then the extra is cancelled and the
    position is marked for review.

    This catches what the guards cannot see: an order placed by something
    outside this application.
    """
    from app.domains.trading.execution import venue

    cancelled = []
    monkeypatch.setattr(venue, "cancel_order",
                        lambda oid, **k: cancelled.append(oid))
    monkeypatch.setattr(
        venue, "working_orders_after_place",
        lambda *a, **k: [{"id": "ours"}, {"id": "stray"}],
    )
    r = _buy(client, alice)
    assert r.status_code in (200, 201)
    assert cancelled, "a duplicate working order was left resting at the venue"
    assert r.json().get("needs_review") is True


# --------------------------------------------------------------------------
# Guard 6 — validation refuses, never clamps
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad,why", [
    ({"sl_pct": 0}, "a zero stop is not a stop"),
    ({"sl_pct": 100}, "a 100% stop prices the exit at zero"),
    ({"sl_pct": -5}, "a negative stop is below the strike floor"),
    ({"tp_pct": 0}, "a take-profit at entry is not a target"),
    ({"tp_pct": -10}, "a take-profit below entry inverts the trade"),
    ({"buy_pct": 0}, "zero size is not an order"),
    ({"buy_pct": 101}, "over 100% of buying power"),
    ({"side": "sideways"}, "not a side"),
    ({"expiration": "2020-01-01"}, "already expired"),
])
def test_invalid_risk_parameters_are_refused_with_the_arithmetic(
    client, alice, bad, why
):
    """Nothing is silently clamped to a legal value. A clamped stop is a stop
    the operator did not choose, and they would never know."""
    r = _buy(client, alice, body={**BUY_BODY, **bad})
    assert r.status_code in (400, 422), f"{bad} was accepted — {why}"
    assert r.json()["detail"], "a refusal must explain itself"


def test_the_zero_dte_cutoff_is_re_checked_at_the_order(client, alice, monkeypatch):
    """Given a request that was inside the cutoff when it arrived,
    when the cutoff passes before the order is placed,
    then the order is refused rather than slipping through.

    Checked twice on purpose: once so an observation that cannot finish in
    time never starts, and again at the moment of the order.
    """
    from app.domains.trading.risk import clock

    monkeypatch.setattr(clock, "past_zero_dte_cutoff", lambda: True)
    r = _buy(client, alice, body={**BUY_BODY, "zero_dte": True})
    assert r.status_code in (400, 409, 422)


# --------------------------------------------------------------------------
# Guard 7 — no entry while the stop cannot be watched
# --------------------------------------------------------------------------

def test_entries_are_refused_when_the_risk_monitor_is_stale(
    client, alice, monkeypatch
):
    """Given the risk monitor has not completed a pass recently,
    when an entry is attempted,
    then it is refused.

    Opening a position whose stop-loss nobody is watching is worse than not
    trading. This is the guard that would have made Phase 3's alarm visible
    instead of silent.
    """
    from app.domains.trading.risk import heartbeat

    monkeypatch.setattr(heartbeat, "seconds_since_last_pass",
                        lambda tenant_id: 3600)
    r = _buy(client, alice)
    assert r.status_code == 503
    assert "stop" in r.text.lower() or "monitor" in r.text.lower()


def test_readiness_reports_the_heartbeat_age(client, alice):
    """The same signal must be visible to ops, not only to the order path."""
    r = client.get("/readiness")
    assert r.status_code == 200
    assert "risk_monitor" in r.json()


# --------------------------------------------------------------------------
# The exit path keeps the behaviour that already works
# --------------------------------------------------------------------------

def test_closing_cancels_the_resting_take_profit_before_selling(
    client, alice, monkeypatch
):
    """A sell that races its own take-profit double-sells the holding."""
    from app.domains.trading.execution import venue

    calls = []
    monkeypatch.setattr(venue, "cancel_order", lambda oid, **k: calls.append(("cancel", oid)))
    monkeypatch.setattr(venue, "sell_to_close", lambda **k: calls.append(("sell", k)) or {"id": "s1"})

    pos = _buy(client, alice).json()
    client.post(f"{OPEN}/{pos['id']}/close",
                headers={**alice.headers, "Idempotency-Key": uuid.uuid4().hex})

    kinds = [c[0] for c in calls]
    assert kinds.index("cancel") < kinds.index("sell"), (
        "the take-profit was still resting when the close order went in"
    )


def test_never_rests_more_sells_than_the_account_holds(client, alice, monkeypatch):
    """Resting more sells than the account holds is a short position by
    accident. This rule already exists and must survive the rebuild."""
    from app.domains.trading.execution import venue

    monkeypatch.setattr(venue, "held_quantity", lambda *a, **k: 1)
    monkeypatch.setattr(venue, "resting_sells",
                        lambda *a, **k: [{"quantity": 1}])
    placed = []
    monkeypatch.setattr(venue, "place_sell", lambda **k: placed.append(k))

    from app.domains.trading.risk import monitor
    monitor.run_pass(tenant_id=alice.tenant_id)
    assert not placed, "a second sell was rested against a single held contract"
