"""A query without a tenant must fail, not widen.

Phase 1's third finding was `if user_id:` — a missing scope meant "all
tenants" instead of "refuse". That is one keystroke away from returning
every operator's ledger, and roughly twenty endpoints declared the parameter
optional.

These tests are about the data layer itself rather than the HTTP surface,
because the guarantee has to hold for code paths that never see a request:
background loops, the reconciler, the ingest pass. They are the one place in
this suite that touches an internal seam, and deliberately so — the brief
asks for a structural guarantee, and a structural guarantee has to be tested
where the structure is.
"""

from __future__ import annotations

import pytest


def test_repository_refuses_to_build_a_query_without_a_tenant():
    """Given a repository constructed with no tenant context,
    when any read is attempted,
    then it raises — it must never fall back to every tenant.
    """
    from app.platform.db.repository import TenantScopeMissing, TenantRepository

    repo = TenantRepository(session=None, tenant_id=None)
    with pytest.raises(TenantScopeMissing):
        repo.query()


def test_repository_refuses_an_empty_string_tenant():
    """The falsy-value trap that caused the original bug.

    `if user_id:` treated "" and None identically and silently widened. An
    empty tenant is not a tenant, and it must fail exactly as None does
    rather than being quietly accepted as a real scope.
    """
    from app.platform.db.repository import TenantScopeMissing, TenantRepository

    for empty in ("", "   ", None):
        repo = TenantRepository(session=None, tenant_id=empty)
        with pytest.raises(TenantScopeMissing):
            repo.query()


def test_every_tenant_owned_model_is_reachable_only_through_the_scoped_repository():
    """No model that carries a tenant may be queried by a bare session.

    This is what makes the guarantee structural instead of a convention: if
    a future handler imports a model and writes `select(Position)` directly,
    this test names the model and fails.
    """
    from app.platform.db import registry

    unguarded = [m.__name__ for m in registry.tenant_owned_models()
                 if not registry.is_scope_enforced(m)]
    assert not unguarded, (
        "these tenant-owned models can be queried without a tenant scope: "
        + ", ".join(unguarded)
    )


# Market data, identical for every operator, and the ONLY kind of table
# allowed to be read without a tenant scope. Each name here is a decision
# someone has to defend, which is why the test asserts the exact set:
#
#   Signal              a desk signal: an observation about the market.
#   ResearchSignal      the super-research engines' ledger. Same category.
#   DailySnapshot       GEX walls and the econ calendar for a date.
#   Gex0dteHour         SPY net gamma per trading hour.
#   PusherHeartbeat     liveness of the browser pusher that FEEDS Gex0dteHour.
#                       Not market data itself, but telemetry ABOUT a
#                       market-data feed, and it has no operator either -- the
#                       pusher is one browser tab for the whole desk.
#
# A gamma wall is the same number for every operator. Copying it per tenant
# would mean N identical rows and N identical vendor calls for one fact.
_MARKET_DATA = {"Signal", "ResearchSignal", "DailySnapshot", "Gex0dteHour",
                "PusherHeartbeat"}


def test_market_data_is_the_only_documented_exception():
    """Only market data may be read unscoped, and only by name.

    The exemption is explicit and enumerated rather than implied, so adding a
    sixth one is a visible decision instead of an accident. A new table that
    simply forgets its tenant_id fails here by name.
    """
    from app.platform.db import registry

    exempt = {m.__name__ for m in registry.unscoped_models()}
    assert exempt == _MARKET_DATA, (
        f"unexpected unscoped models: {exempt - _MARKET_DATA} — every table "
        "except market data must be tenant-scoped"
    )


def test_a_background_pass_cannot_run_without_choosing_a_tenant():
    """The risk monitor iterates tenants. It must ask for each one by name,
    not sweep the table — a sweep is how one tenant's failure becomes
    everyone's, and how an unscoped write reaches the wrong account.
    """
    from app.domains.trading.risk import monitor

    with pytest.raises(TypeError):
        monitor.run_pass()  # no tenant argument: must not be callable
