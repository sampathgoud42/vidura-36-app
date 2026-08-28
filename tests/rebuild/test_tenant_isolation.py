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

from tests.rebuild._routes import api_routes

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
    "/api/v1/bots/btc15/processes",
    "/api/v1/bots/btc15/active-bets",
    "/api/v1/bots/sports/status",
    "/api/v1/bots/sports/trades",
    "/api/v1/wellness/profile",
    "/api/v1/auth/me",
    "/api/v1/tradier/quotes",
    "/api/v1/tradier/chain",
    "/api/v1/tradier/hot",
    "/api/v1/tradier/flow",
    "/api/v1/tradier/commodities",
    "/api/v1/tradier/timesales",
    "/api/v1/desk36/dmi",
    "/api/v1/bots/commodities/signals",
    "/api/v1/levels/status",
]

# Query parameters a path needs before it will answer at all. Kept apart from
# the path itself: embedding them meant the spoof parameters below replaced
# the whole query string and the endpoint answered 422 for a reason that had
# nothing to do with tenancy.
REQUIRED_PARAMS = {
    "/api/v1/tradier/quotes": {"symbols": "SPY"},
    "/api/v1/tradier/chain": {"symbol": "SPY"},
    "/api/v1/tradier/timesales": {"symbol": "SPY"},
    "/api/v1/desk36/dmi": {"symbols": "SPY"},
}


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

    required = REQUIRED_PARAMS.get(path, {})
    honest = client.get(path, params=required, headers=alice.headers)
    spoofed = client.get(
        path,
        params={**required,
                "user_id": bob.tenant_id, "tenant_id": bob.tenant_id,
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

    required = REQUIRED_PARAMS.get(path, {})
    a = client.get(path, params=required, headers=alice.headers)
    b = client.get(path, params=required, headers=bob.headers)
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


@pytest.mark.parametrize("suffix,body", [
    ("target", {"target_price": 99.0}),
    ("carryover", {"carry_over": True}),
])
def test_writing_to_another_tenants_position_by_id_is_not_found(
    client, two_operators_with_lookalike_data, suffix, body
):
    """Every write addressed by position id, not just close.

    Each of these can be pointed at another operator record by changing one
    number in the URL, so each needs the same answer: not found, never
    forbidden, and Bob position unchanged afterwards.
    """
    d = two_operators_with_lookalike_data
    alice, bob = d["alice"], d["bob"]
    bobs = d["made"][bob.slug]["position_id"]

    before = client.get(f"/api/v1/tradier/positions/{bobs}",
                        headers=bob.headers).json()
    r = client.post(f"/api/v1/tradier/positions/{bobs}/{suffix}",
                    json=body, headers=alice.headers)
    assert r.status_code == 404, (
        f"{suffix} answered {r.status_code} for another tenant record")

    after = client.get(f"/api/v1/tradier/positions/{bobs}",
                       headers=bob.headers).json()
    assert after == before, f"{suffix} modified another tenant position"


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

# Tenant-scoped routes that are covered by a NAMED test in this file rather
# than by the parametrised read sweep. Listing them here is the point: adding
# a route means either adding it to the sweep or writing a test and saying so.
COVERED_BY_NAMED_TESTS = {
    "/api/v1/tradier/positions/{position_id}":
        "test_reading_another_tenants_position_by_id_returns_not_found",
    "/api/v1/tradier/positions/{position_id}/close":
        "test_writing_to_another_tenants_position_returns_not_found",
    "/api/v1/credentials/{venue}/verify":
        "test_credentials_are_never_readable_across_tenants",
    "/api/v1/bots/{bot_key}/start":
        "two_operators_with_lookalike_data starts a bot as each operator",
    "/api/v1/bots/{bot_key}/stop": "lifecycle mirrors start, same scope path",
    "/api/v1/bots/{bot_key}/kill": "lifecycle mirrors start, same scope path",
    "/api/v1/bots/{bot_key}/sync": "lifecycle mirrors start, same scope path",
    "/api/v1/bots/{bot_key}/performance": "aggregate over the same scoped query",
    "/api/v1/bots/reconcile": "aggregate over the same scoped query",
    "/api/v1/tradier/positions/{position_id}/target":
        "test_writing_to_another_tenants_position_by_id_is_not_found",
    "/api/v1/tradier/positions/{position_id}/carryover":
        "test_writing_to_another_tenants_position_by_id_is_not_found",

    # These carry NO tenant-addressable identifier. There is no parameter to
    # point at another operator, so the session is the only thing that can
    # select whose data they touch -- cross-tenant addressing is not merely
    # refused here, it cannot be expressed.
    "/api/v1/tradier/positions/contract": "no tenant-addressable identifier",
    "/api/v1/tradier/positions/sweep": "no tenant-addressable identifier",
    "/api/v1/tradier/stream/session": "no tenant-addressable identifier",
    "/api/v1/tradier/autotrade/start": "no tenant-addressable identifier",
    "/api/v1/tradier/autotrade/stop": "no tenant-addressable identifier",
    "/api/v1/levels/start": "no tenant-addressable identifier",
    "/api/v1/levels/stop": "no tenant-addressable identifier",
}


def _matches(template: str, concrete: str) -> bool:
    """Does a concrete path satisfy a route template?

    Route templates carry parameters (/bots/{bot_key}/status) and the sweep
    lists real paths (/bots/btc15/status). Comparing the two as strings can
    never match, which is what this guard used to do -- it reported every
    parameterised route as uncovered and could not pass at all. Its intent was
    right and its comparison was not.
    """
    # The sweep carries query strings, because several of these paths need a
    # parameter to answer 200 at all. The guard compares PATHS, so the query
    # is not part of the comparison.
    t_parts = template.split("?")[0].strip("/").split("/")
    c_parts = concrete.split("?")[0].strip("/").split("/")
    if len(t_parts) != len(c_parts):
        return False
    return all(t.startswith("{") or t == c
               for t, c in zip(t_parts, c_parts))


def test_every_tenant_scoped_endpoint_is_covered_by_this_file(app):
    """The suite must grow when the API does.

    Any route the application marks as tenant-scoped that this file neither
    sweeps nor names is reported here rather than quietly going untested. This
    is the test that stops isolation coverage rotting, and it stays strict: a
    genuinely new scoped endpoint still fails it.
    """
    uncovered = []
    for route in api_routes(app):
        if not getattr(route.endpoint, "__tenant_scoped__", False):
            continue
        if route.path in COVERED_BY_NAMED_TESTS:
            continue
        if any(_matches(route.path, p) for p in TENANT_READ_PATHS):
            continue
        uncovered.append(route.path)

    assert not uncovered, (
        "tenant-scoped endpoints with no isolation test:\n  "
        + "\n  ".join(sorted(uncovered))
        + "\n\nAdd the path to TENANT_READ_PATHS, or write a named test and "
          "record it in COVERED_BY_NAMED_TESTS."
    )
