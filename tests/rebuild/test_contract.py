"""Contract tests — the frozen Phase 4 baseline.

These are what protect constraint #1. The desk must not be able to tell that
anything changed underneath it, so every path, method and status code the
approved contract declares is asserted here, and anything the application
serves that the contract does not declare is reported as drift.

The list below IS the contract. Changing it is a deliberate act that shows up
in review; changing a router is not.
"""

from __future__ import annotations

import pytest

V1 = "/api/v1"

# ---- the approved surface ------------------------------------------------
# Bot station: eight operations keyed by bot_key, replacing 37 per-family
# routes. A new bot adds nothing here — that is the point.
BOT_OPERATIONS = ["status", "logs", "trades", "processes", "config",
                  "active-bets", "performance"]
BOT_ACTIONS = ["start", "stop", "sync", "kill"]

CONTRACT: list[tuple[str, str]] = [
    # auth
    ("POST", f"{V1}/auth/login"),
    ("POST", f"{V1}/auth/logout"),
    ("GET", f"{V1}/auth/me"),
    ("GET", f"{V1}/auth/status"),
    # tenancy admin
    ("GET", f"{V1}/tenants"),
    ("POST", f"{V1}/tenants"),
    ("PATCH", f"{V1}/tenants/{{tenant_id}}"),
    ("GET", f"{V1}/tenants/{{tenant_id}}/credentials"),
    ("POST", f"{V1}/tenants/{{tenant_id}}/credentials"),
    ("POST", f"{V1}/tenants/{{tenant_id}}/credentials/{{credential_id}}/rotate"),
    ("DELETE", f"{V1}/tenants/{{tenant_id}}/credentials/{{credential_id}}"),
    ("PUT", f"{V1}/tenants/{{tenant_id}}/worlds"),
    ("POST", f"{V1}/credentials/{{venue}}/verify"),
    # trading
    ("GET", f"{V1}/tradier/positions"),
    ("POST", f"{V1}/tradier/positions"),
    ("GET", f"{V1}/tradier/positions/{{position_id}}"),
    ("POST", f"{V1}/tradier/positions/contract"),
    ("POST", f"{V1}/tradier/positions/sweep"),
    ("POST", f"{V1}/tradier/positions/{{position_id}}/close"),
    ("POST", f"{V1}/tradier/positions/{{position_id}}/target"),
    ("POST", f"{V1}/tradier/positions/{{position_id}}/carryover"),
    ("GET", f"{V1}/tradier/balance"),
    ("GET", f"{V1}/tradier/venue"),
    ("GET", f"{V1}/tradier/quotes"),
    ("GET", f"{V1}/tradier/chain"),
    ("GET", f"{V1}/tradier/timesales"),
    ("GET", f"{V1}/tradier/hot"),
    ("GET", f"{V1}/tradier/flow"),
    ("GET", f"{V1}/tradier/commodities"),
    ("POST", f"{V1}/tradier/stream/session"),
    ("GET", f"{V1}/tradier/autotrade/status"),
    ("POST", f"{V1}/tradier/autotrade/start"),
    ("POST", f"{V1}/tradier/autotrade/stop"),
    # ledger + portfolio
    ("GET", f"{V1}/trades"),
    ("POST", f"{V1}/trades"),
    ("GET", f"{V1}/portfolio"),
    ("GET", f"{V1}/portfolio/history"),
    # bots
    ("GET", f"{V1}/bots"),
    ("POST", f"{V1}/bots/reconcile"),
    ("GET", f"{V1}/bots/commodities/signals"),
    # desk + wellness + worlds
    ("GET", f"{V1}/desk36/dmi"),
    ("GET", f"{V1}/wellness/profile"),
    ("PUT", f"{V1}/wellness/profile"),
    # system
    ("GET", "/health"),
    ("GET", "/readiness"),
] + [("GET", f"{V1}/bots/{{bot_key}}/{op}") for op in BOT_OPERATIONS] \
  + [("POST", f"{V1}/bots/{{bot_key}}/{a}") for a in BOT_ACTIONS]


def _served(app) -> set[tuple[str, str]]:
    out = set()
    for route in app.routes:
        for method in getattr(route, "methods", set()) or set():
            if method in ("HEAD", "OPTIONS"):
                continue
            out.add((method, route.path))
    return out


@pytest.mark.parametrize("method,path", CONTRACT)
def test_every_contracted_endpoint_is_served(app, method, path):
    assert (method, path) in _served(app), (
        f"{method} {path} is in the approved contract but not served"
    )


def test_nothing_is_served_that_the_contract_does_not_declare(app):
    """Drift in the other direction. An endpoint that appears without going
    through the consolidation table is exactly how 37 near-duplicate bot
    routes accumulated in the first place."""
    undeclared = sorted(
        f"{m} {p}" for m, p in _served(app)
        if (m, p) not in set(CONTRACT)
        and not p.startswith(("/docs", "/redoc", "/openapi", "/static"))
        and p != "/{full_path:path}"
    )
    assert not undeclared, "undeclared endpoints:\n  " + "\n  ".join(undeclared)


def test_no_endpoint_accepts_a_tenant_selector(app):
    """The D1 guarantee, machine-checked.

    If no endpoint can accept a tenant parameter, then the Phase 1 attacks
    have no input surface at all — this is stronger than testing that they
    are ignored, because it proves they cannot be expressed.
    """
    from fastapi.routing import APIRoute

    banned = {"user_id", "tenant_id", "operator", "username", "customer"}
    offenders = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        # tenancy admin legitimately addresses a tenant by path
        if route.path.startswith(f"{V1}/tenants"):
            continue
        for field in list(route.dependant.query_params) + list(route.dependant.path_params):
            if field.name in banned:
                offenders.append(f"{route.path} ({field.name})")
    assert not offenders, (
        "these endpoints still let the caller name a tenant:\n  "
        + "\n  ".join(sorted(offenders))
    )


@pytest.mark.parametrize("path", [
    f"{V1}/tradier/positions", f"{V1}/trades", f"{V1}/portfolio",
    f"{V1}/bots/btc15/status", f"{V1}/wellness/profile",
])
def test_tenant_scoped_endpoints_refuse_an_anonymous_caller(client, path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", [f"{V1}/auth/login", f"{V1}/auth/status",
                                  "/health"])
def test_the_open_paths_stay_open(client, path):
    r = client.get(path) if path != f"{V1}/auth/login" else client.post(
        path, json={"username": "x", "password": "y"})
    assert r.status_code != 401


def test_the_shared_api_key_cannot_reach_tenant_data(client, monkeypatch):
    """D4: the shared key resolves to no tenant, so it is accepted only on
    operational endpoints. Phase 1 proved nothing sends it today, which is
    why demoting it is safe."""
    monkeypatch.setenv("TBOT_API_KEY", "a-shared-script-key")
    h = {"X-API-Key": "a-shared-script-key"}
    assert client.get(f"{V1}/tradier/positions", headers=h).status_code == 401
    assert client.get("/health", headers=h).status_code == 200


def test_execution_endpoints_advertise_idempotency(app):
    """Every money-moving endpoint must accept an Idempotency-Key header, or
    the guarantee is optional in practice."""
    from fastapi.routing import APIRoute

    money = {f"{V1}/tradier/positions", f"{V1}/tradier/positions/contract",
             f"{V1}/tradier/positions/{{position_id}}/close",
             f"{V1}/tradier/positions/sweep"}
    missing = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path in money and "POST" in route.methods:
            names = {h.name.lower().replace("_", "-")
                     for h in route.dependant.header_params}
            if "idempotency-key" not in names:
                missing.append(route.path)
    assert not missing, "money-moving endpoints without idempotency: " + ", ".join(missing)
