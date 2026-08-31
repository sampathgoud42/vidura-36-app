"""A stop must survive its watcher.

Phase 3 found that today the take-profit is a GTC order resting on Tradier
and the stop-loss is a threshold in a row watched by a Python loop inside the
API process. A crash, a deploy or an unhandled exception leaves live options
positions with unlimited downside and an armed profit-taker, and nothing
tells the operator.

Three layers were approved: a venue-resting stop that survives anything, the
monitored stop with no cold-start gap, and a heartbeat that makes a failed
watcher loud. These tests cover all three.
"""

from __future__ import annotations

import uuid

import pytest

OPEN = "/api/v1/tradier/positions"
BUY = {"symbol": "SPY", "side": "call", "buy_pct": 10,
       "tp_pct": 15, "sl_pct": 30, "live": False}


def _open_and_fill(client, who, monkeypatch):
    """Open a position and drive it to filled-and-armed."""
    from app.domains.trading.execution import venue
    from app.domains.trading.risk import monitor

    r = client.post(OPEN, json=BUY,
                    headers={**who.headers, "Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code in (200, 201), r.text
    pos_id = r.json()["id"]
    monkeypatch.setattr(venue, "order_status",
                        lambda *a, **k: {"status": "filled", "avg_fill_price": 1.00})
    monkeypatch.setattr(venue, "held_quantity", lambda *a, **k: 10)
    monitor.run_pass(tenant_id=who.tenant_id)   # records the fill
    monitor.run_pass(tenant_id=who.tenant_id)   # arms the exits
    return pos_id


def _force_monitored_stop(pos_id: int) -> None:
    """Put a position on the MONITORED stop path.

    Arming rests a stop at the venue, and with one resting the monitor
    deliberately stands aside. To test the monitored fallback -- the path that
    matters when the venue would not accept a stop -- the position has to be
    in the state that fallback exists for.
    """
    from sqlalchemy import select

    from app.domains.trading.models import Position
    from app.platform.db.session import session_scope

    with session_scope() as db:
        pos = db.scalars(select(Position).where(Position.id == pos_id)).one()
        pos.stop_protection = "monitored_only"
        pos.stop_order_id = None


# --------------------------------------------------------------------------
# Layer 1 — the stop rests on the venue
# --------------------------------------------------------------------------

def test_arming_a_position_rests_both_a_target_and_a_stop(client, alice, monkeypatch):
    """Given a filled position,
    when the exits are armed,
    then BOTH a take-profit and a stop are resting at the venue.

    This is the layer that closes the hole. Everything else shrinks the
    window; only an order the venue holds removes the dependency on this
    process being alive.
    """
    pos_id = _open_and_fill(client, alice, monkeypatch)
    pos = client.get(f"{OPEN}/{pos_id}", headers=alice.headers).json()

    assert pos["tp_order_id"], "no take-profit resting"
    assert pos["stop_order_id"], (
        "no stop resting at the venue — this position is unprotected the "
        "moment the API stops"
    )


def test_the_two_exit_legs_are_linked_so_one_fill_cancels_the_other(
    client, alice, monkeypatch
):
    """Given both legs rest,
    when the take-profit fills,
    then the stop is cancelled — not left resting against a holding that is
    already gone.

    An orphaned stop on a sold position is how an accidental short is
    opened.
    """
    from app.domains.trading.execution import venue
    from app.domains.trading.risk import monitor

    pos_id = _open_and_fill(client, alice, monkeypatch)
    cancelled = []
    monkeypatch.setattr(venue, "cancel_order", lambda oid, **k: cancelled.append(oid))
    monkeypatch.setattr(venue, "order_status",
                        lambda oid, **k: {"status": "filled", "avg_fill_price": 1.15}
                        if "tp" in str(oid) else {"status": "open"})
    monkeypatch.setattr(venue, "held_quantity", lambda *a, **k: 0)

    monitor.run_pass(tenant_id=alice.tenant_id)
    pos = client.get(f"{OPEN}/{pos_id}", headers=alice.headers).json()
    assert pos["status"] == "tp_filled"
    assert cancelled, "the stop was left resting after the target filled"


def test_a_venue_that_rejects_the_stop_does_not_leave_a_silent_gap(
    client, alice, monkeypatch
):
    """Given the venue refuses the stop leg,
    when arming completes,
    then the position is flagged as protected only by the monitored stop.

    Failing to rest a stop is acceptable; failing to rest one *quietly* is
    not.
    """
    from app.domains.trading.execution import venue

    monkeypatch.setattr(venue, "place_stop",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("rejected")))
    pos_id = _open_and_fill(client, alice, monkeypatch)
    pos = client.get(f"{OPEN}/{pos_id}", headers=alice.headers).json()

    assert pos["stop_order_id"] is None
    assert pos.get("stop_protection") == "monitored_only"
    assert "stop" in (pos.get("note") or "").lower()


# --------------------------------------------------------------------------
# Layer 2 — the monitored stop, with no cold-start gap
# --------------------------------------------------------------------------

def test_the_monitor_runs_a_pass_immediately_on_startup(app):
    """The current loop sleeps 15 seconds before its first pass, so every
    restart has a blind window while positions are live. The first pass must
    happen at startup, not after a nap."""
    from app.domains.trading.risk import monitor

    assert monitor.STARTUP_DELAY_S == 0, (
        f"the risk monitor waits {monitor.STARTUP_DELAY_S}s before its first "
        "pass — that is a blind window with live positions"
    )


def test_a_stop_threshold_survives_a_restart(client, alice, monkeypatch):
    """Given an armed position,
    when the application is rebuilt from the same database,
    then the stop threshold is still known and still watched.
    """
    pos_id = _open_and_fill(client, alice, monkeypatch)
    before = client.get(f"{OPEN}/{pos_id}", headers=alice.headers).json()

    # app.api_v2.application, not app.main. This built the OLD application,
    # which has a different auth model, so alice's session did not
    # authenticate and the "after" read was an error body rather than the
    # position -- the test was comparing two error payloads and calling it a
    # surviving stop.
    from fastapi.testclient import TestClient

    from app.api_v2.application import create_app

    with TestClient(create_app()) as fresh:
        after = fresh.get(f"{OPEN}/{pos_id}", headers=alice.headers).json()

    assert after["sl_price"] == before["sl_price"]
    assert after["status"] == before["status"]


def test_a_breached_stop_cancels_the_target_before_selling(client, alice, monkeypatch):
    """The monitored stop must not race the resting target."""
    from app.domains.trading.execution import venue
    from app.domains.trading.risk import monitor

    pos_id = _open_and_fill(client, alice, monkeypatch)

    # Two things had to be undone before this test could exercise what it
    # claims. _open_and_fill patches order_status to report EVERY order as
    # filled, so the target-filled branch fired first and returned -- the
    # observed ["cancel"] was the target being settled, never the stop. And
    # an armed position carries a venue-resting stop, where the monitored
    # path is deliberately skipped because the venue is faster than this
    # loop. So: stop reporting orders as filled, and put the position on the
    # monitored path this test is about.
    monkeypatch.setattr(venue, "order_status",
                        lambda *a, **k: {"status": "open"})
    _force_monitored_stop(pos_id)

    order = []
    monkeypatch.setattr(venue, "cancel_order", lambda oid, **k: order.append("cancel"))
    monkeypatch.setattr(venue, "sell_to_close", lambda **k: order.append("sell") or {"id": "x"})
    monkeypatch.setattr(venue, "bid_for", lambda *a, **k: 0.50)   # below a 30% stop

    monitor.run_pass(tenant_id=alice.tenant_id)
    assert order[:2] == ["cancel", "sell"], (
        "the monitored stop must cancel the resting target BEFORE selling; a "
        f"sell that races its own target double-sells the holding. Got {order}"
    )


# --------------------------------------------------------------------------
# Layer 3 — the watchdog
# --------------------------------------------------------------------------

def test_each_pass_records_a_heartbeat(client, alice, monkeypatch):
    from app.domains.trading.risk import heartbeat, monitor

    monitor.run_pass(tenant_id=alice.tenant_id)
    assert heartbeat.seconds_since_last_pass(alice.tenant_id) < 5


def test_a_failing_pass_does_not_record_a_healthy_heartbeat(
    client, alice, monkeypatch
):
    """A pass that threw is not a pass. Recording it as healthy would make
    the watchdog lie in exactly the situation it exists for."""
    from app.domains.trading.execution import venue
    from app.domains.trading.risk import heartbeat, monitor

    # held_quantity is only called while a position is still being armed; by
    # the time _open_and_fill returns, the armed path never reaches it, so
    # nothing threw and the pass was recorded healthy. order_status is on the
    # open path this position is actually on.
    _open_and_fill(client, alice, monkeypatch)
    monkeypatch.setattr(venue, "order_status",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("venue down")))
    with pytest.raises(Exception):
        monitor.run_pass(tenant_id=alice.tenant_id)

    assert heartbeat.consecutive_failures(alice.tenant_id) >= 1


def test_one_tenants_failure_does_not_stop_another_tenants_stop(
    client, alice, bob, monkeypatch
):
    """Given Alice's venue call fails,
    when the monitor sweeps,
    then Bob's positions are still checked.

    A shared loop that dies on one operator's bad credentials would silently
    disarm everyone else's stops.
    """
    from app.domains.trading.risk import monitor

    # Both operators need something AT RISK. sweep_all_tenants visits tenants
    # holding active positions -- correctly, since a tenant with nothing open
    # has no stop to watch -- and bob had none, so the sweep was right to skip
    # him and the assertion was asserting the wrong thing.
    _open_and_fill(client, alice, monkeypatch)
    _open_and_fill(client, bob, monkeypatch)

    swept = []
    original = monitor.run_pass

    def flaky(tenant_id, **kw):
        if tenant_id == alice.tenant_id:
            raise RuntimeError("alice's venue is down")
        swept.append(tenant_id)
        return original(tenant_id=tenant_id, **kw)

    monkeypatch.setattr(monitor, "run_pass", flaky)
    monitor.sweep_all_tenants()
    assert bob.tenant_id in swept
