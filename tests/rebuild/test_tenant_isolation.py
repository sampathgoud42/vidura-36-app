"""Tenant isolation — the highest-priority category in this suite.

Phase 1 found five ways one operator could reach another's data, and the
worst of them needed nothing more than a query string. These tests exist so
that none of the five can come back, and so that a sixth is caught the first
time someone writes it.

The rule every test here enforces: THE SESSION DECIDES WHO YOU ARE. A request
cannot name a tenant, cannot select one, and cannot widen to all of them.

Two operators, Alice and Bob, hold deliberately look-alike data — same
symbol, same contract, same bot, same sizes. If a response ever crosses the
boundary it is unambiguous, because only the ids differ.
"""

from __future__ import annotations

import uuid

import pytest

# Every read path a signed-in operator can reach that returns tenant data.
# A new tenant-scoped endpoint that is not in this list is a gap in the
# suite, and test_every_scoped_endpoint_is_covered says so out loud.
TENANT_READ_PATHS = [
    "/api/v1/tradier/positions",
    "/api/v1/tradier/balance",
    "/api/v1/tradier/venue",
    "/api/v1/tradier/autotrade/status",
    "/api/v1/trades",
    "/api/v1/portfolio",
    "/api/v1/portfolio/history",
    "/api/v1/bots/btc15/status",
    "/api/v1/bots/btc15/trades",
    "/api/v1/bots/btc15/logs",
    "/api/v1/bots/btc15/active-bets",
    "/api/v1/bots/sports/status",
    "/api/v1/bots/sports/trades",
    "/api/v1/wellness/profile",
    "/api/v1/auth/me",
]


# --------------------------------------------------------------------------
# The parameter that must no longer exist
# --------------------------------------------------------------------------

@pytest.mark.parametrize("path", TENANT_READ_PATHS)
def test_naming_another_tenant_is_ignored_not_honoured(
    client, two_operators_with_lookalike_data, path
):
    """Given Alice is signed in and passes Bob's tenant id as a parameter,
    when she calls any tenant-scoped read,
    then she gets HER data — the parameter is not a tenant selector.

    This is the Phase 1 finding that needed no crafted request: `?operator=`
    and `?user_id=` chose whose account you acted as. Passing them now must
    be inert, not authoritative.
    """
    alice = two_operators_with_lookalike_data["alice"]
    bob = two_operators_with_lookalike_data["bob"]

    honest = client.get(path, headers=alice.headers)
    spoofed = client.get(
        path,
        params={"user_id": bob.tenant_id, "tenant_id": bob.tenant_id,
                "operator": bob.slug},
        headers=alice.headers,
    )

    assert spoofed.status_code == honest.status_code
    assert spoofed.json() == honest.json(), (
        f"{path} changed its answer when handed another tenant's id — "
        "the request is still choosing the tenant"
    )


@pytest.mark.parametrize("path", TENANT_READ_PATHS)
def test_no_tenant_data_leaks_between_operators(
    client, two_operators_with_lookalike_data, path
):
    """Given two operators with look-alike data,
    when each reads the same path,
    then no identifier belonging to one appears in the other's response.
    """
    alice = two_operators_with_lookalike_data["alice"]
    bob = two_operators_with_lookalike_data["bob"]

    a = client.get(path, headers=alice.headers)
    b = client.get(path, headers=bob.headers)
    if a.status_code >= 400 or b.status_code >= 400:
        pytest.skip(f"{path} unavailable in this environment")

    assert bob.tenant_id not in a.text, f"{path} leaked Bob's tenant id to Alice"
    assert bob.slug not in a.text, f"{path} leaked Bob's name to Alice"
    assert alice.tenant_id not in b.text, f"{path} leaked Alice's tenant id to Bob"
    assert alice.slug not in b.text, f"{path} leaked Alice's name to Bob"


# --------------------------------------------------------------------------
# ID guessing: not-found, never forbidden
# --------------------------------------------------------------------------

def test_reading_another_tenants_position_by_id_returns_not_found(
    client, two_operators_with_lookalike_data
):
    """Given Bob owns position P,
    when Alice requests P by its exact id,
    then the answer is 404 — never 403.

    403 confirms the record exists, which turns an id into an oracle. The
    only honest answer to "may I see something that is not mine" is that it
    is not there.
    """
    d = two_operators_with_lookalike_data
    alice, bob = d["alice"], d["bob"]
    bobs_position = d["made"][bob.slug]["position_id"]

    r = client.get(f"/api/v1/tradier/positions/{bobs_position}", headers=alice.headers)
    assert r.status_code == 404, (
        f"expected 404 for another tenant's record, got {r.status_code} — "
        "403 tells the caller the record exists"
    )


def test_writing_to_another_tenants_position_returns_not_found(
    client, two_operators_with_lookalike_data
):
    """Given Bob owns position P,
    when Alice tries to close it,
    then the answer is 404 and Bob's position is untouched.

    The write path matters more than the read path: this one spends money.
    """
    d = two_operators_with_lookalike_data
    alice, bob = d["alice"], d["bob"]
    bobs_position = d["made"][bob.slug]["position_id"]

    r = client.post(
        f"/api/v1/tradier/positions/{bobs_position}/close",
        headers={**alice.headers, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert r.status_code == 404

    still_there = client.get(f"/api/v1/tradier/positions/{bobs_position}",
                             headers=bob.headers)
    assert still_there.status_code == 200
    assert still_there.json()["status"] != "closed"


def test_error_messages_do_not_confirm_existence(
    client, two_operators_with_lookalike_data
):
    """A real id belonging to someone else and an id belonging to nobody must
    produce the same answer, byte for byte. A difference is an oracle."""
    d = two_operators_with_lookalike_data
    alice, bob = d["alice"], d["bob"]
    real_but_not_hers = d["made"][bob.slug]["position_id"]
    pure_fiction = 987654321

    a = client.get(f"/api/v1/tradier/positions/{real_but_not_hers}",
                   headers=alice.headers)
    b = client.get(f"/api/v1/tradier/positions/{pure_fiction}",
                   headers=alice.headers)

    assert a.status_code == b.status_code
    assert a.json() == b.json(), (
        "a real record and an imaginary one answered differently — "
        "the difference is enough to enumerate other tenants' ids"
    )


# --------------------------------------------------------------------------
# Aggregates, counts and list envelopes
# --------------------------------------------------------------------------

def test_counts_and_totals_only_span_the_callers_tenant(
    client, two_operators_with_lookalike_data
):
    """Given both operators hold one position each,
    when Alice reads the list envelope,
    then the total counts hers and not the pair.

    Aggregates leak without returning a single row, which is why the brief
    calls them out separately.
    """
    alice = two_operators_with_lookalike_data["alice"]
    r = client.get("/api/v1/tradier/positions", headers=alice.headers)
    assert r.status_code == 200
    body = r.json()
    rows = body["items"] if isinstance(body, dict) else body
    if isinstance(body, dict) and "total" in body:
        assert body["total"] == len(rows), (
            "the total does not match the rows returned — it was computed "
            "over more tenants than the caller's"
        )
    assert len(rows) == 1


def test_trade_ledger_aggregates_are_scoped(client, two_operators_with_lookalike_data):
    alice = two_operators_with_lookalike_data["alice"]
    bob = two_operators_with_lookalike_data["bob"]
    a = client.get("/api/v1/trades", params={"mode": "all"}, headers=alice.headers)
    b = client.get("/api/v1/trades", params={"mode": "all"}, headers=bob.headers)
    if a.status_code != 200 or b.status_code != 200:
        pytest.skip("ledger unavailable in this environment")
    assert bob.tenant_id not in a.text
    assert alice.tenant_id not in b.text


# --------------------------------------------------------------------------
# Bot station and wellness, the two places it is easy to forget
# --------------------------------------------------------------------------

def test_bot_logs_are_not_readable_across_tenants(
    client, two_operators_with_lookalike_data
):
    """Bot logs are files on disk keyed by operator. A path built from a
    parameter rather than the session is the classic traversal here."""
    d = two_operators_with_lookalike_data
    alice, bob = d["alice"], d["bob"]

    r = client.get("/api/v1/bots/btc15/logs", headers=alice.headers)
    if r.status_code != 200:
        pytest.skip("bot logs unavailable in this environment")
    assert bob.slug not in r.text, "Alice can read log lines from Bob's bot"


def test_wellness_profile_is_private_to_its_operator(client, alice, bob):
    """Given Bob records a wellness profile,
    when Alice reads the wellness endpoint,
    then she sees her own (empty) profile and nothing of Bob's.

    Ethnicity, gender, diet and health goals are special-category personal
    data. A leak here is a privacy incident, not a financial one.
    """
    saved = client.put(
        "/api/v1/wellness/profile",
        json={"gender": "male", "age_band": "35-44", "ethnicity": "asian",
              "diet": "vegetarian", "style": "calm", "region": "midwest",
              "notifications": True, "goals": ["sleep-better", "eat-less"]},
        headers=bob.headers,
    )
    assert saved.status_code in (200, 201), saved.text

    mine = client.get("/api/v1/wellness/profile", headers=alice.headers)
    assert mine.status_code in (200, 404)
    if mine.status_code == 200:
        for private in ("vegetarian", "sleep-better", "midwest", "asian"):
            assert private not in mine.text, (
                "Alice can read Bob's wellness profile"
            )


def test_credentials_are_never_readable_across_tenants(client, admin, alice, bob):
    """Bob's venue keys must not appear anywhere Alice can reach — not in a
    list, not masked, not in a verification response."""
    client.post(
        f"/api/v1/tenants/{bob.tenant_id}/credentials",
        json={"venue": "tradier", "label": "prod",
              "secret": {"token": "bobs-secret-token-value",
                         "account_id": "BOB123"}},
        headers=admin.headers,
    )
    for path in ("/api/v1/auth/me", "/api/v1/tradier/venue", "/api/v1/tradier/balance"):
        r = client.get(path, headers=alice.headers)
        assert "bobs-secret-token-value" not in r.text
        assert "BOB123" not in r.text


# --------------------------------------------------------------------------
# Coverage guard
# --------------------------------------------------------------------------

def test_every_tenant_scoped_endpoint_is_covered_by_this_file(app):
    """The suite must grow when the API does.

    Any route the application marks as tenant-scoped and that this file does
    not exercise is reported here rather than quietly going untested. This is
    the test that stops isolation coverage rotting.
    """
    declared = set()
    for route in app.routes:
        scoped = getattr(getattr(route, "endpoint", None), "__tenant_scoped__", False)
        if scoped:
            declared.add(route.path)

    uncovered = sorted(declared - set(TENANT_READ_PATHS))
    assert not uncovered, (
        "tenant-scoped endpoints with no isolation test:\n  "
        + "\n  ".join(uncovered)
    )
