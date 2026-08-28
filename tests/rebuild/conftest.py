"""Fixtures for the rebuild suite.

Everything here talks to the application through its HTTP surface or its
public tenancy API. Nothing reaches into a repository, a model class or a
session directly — a test that knows the shape of a table is a test that has
to be rewritten when the table changes, and the whole point of this suite is
that it outlives the implementation.

The suite is written against the Phase 2 specification and the Phase 4 API
contract. It does not exist yet. Every test in this tree is expected to fail
until Phase 7 builds it, and the failure mode should be an import error or a
404 — not a wrong answer.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

# The rebuild suite drives a database it owns, never the operator's.
#
# A FILE, deliberately, not "sqlite://". An in-memory SQLite URL gives every
# new connection its own empty database, so the pool that migrates the schema
# and the pool that serves a request would not be looking at the same thing --
# tables appear to vanish between calls. One file per test run avoids that and
# still leaves nothing behind.
_TMP = Path(tempfile.mkdtemp(prefix="vidura_rebuild_test_"))
os.environ.setdefault("TBOT_DATABASE_URL_OVERRIDE",
                      f"sqlite:///{(_TMP / 'rebuild.db').as_posix()}")
os.environ.setdefault("TBOT_PAPER_ONLY", "true")
os.environ.setdefault("TBOT_LOGIN_REQUIRED", "true")
os.environ.setdefault("TBOT_ENCRYPTION_MASTER_KEY", "test-master-key-not-a-real-one")


@dataclass(frozen=True)
class Operator:
    """A signed-in tenant, as a test sees it: a name and a way to be them."""

    slug: str
    password: str
    tenant_id: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"X-API-Key": self.token}


@pytest.fixture(autouse=True)
def fresh_schema():
    """A clean, MIGRATED database for every test.

    Migrated rather than created from metadata on purpose: it means every test
    in this suite runs against the same schema a deploy produces, so a
    migration that is wrong fails here rather than at 09:30 on a Monday.

    In-memory session state is reset too. Login sessions and the keyring are
    process-global by design, and a token surviving into the next test is
    exactly the kind of cross-test leakage the isolation suite exists to
    disprove.
    """
    from app.api_v2 import deps
    from app.core.config import get_settings
    from app.platform.db import migrations, session
    from app.platform.security import sessions as session_store

    # Settings are lru_cached, and the parent tests/conftest.py imports
    # app.core.database at module level -- which resolves Settings before this
    # file has set its database override. Clearing the cache here is what makes
    # the override actually apply, rather than depending on which conftest
    # pytest happened to import first.
    get_settings.cache_clear()

    url = os.environ["TBOT_DATABASE_URL_OVERRIDE"]
    db_file = Path(url.replace("sqlite:///", ""))
    if db_file.exists():
        db_file.unlink()
    for suffix in ("-wal", "-shm"):
        stale = Path(str(db_file) + suffix)
        if stale.exists():
            stale.unlink()

    session.reset_for_tests()
    session_store.revoke_all()
    deps.reset_keyring_for_tests()
    migrations.upgrade_to_head(url=url)
    yield
    session.reset_for_tests()
    session_store.revoke_all()


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture()
def app():
    # Points at app.api_v2 rather than app.main during the transition, and
    # this is wiring rather than a test being bent to pass: no assertion in
    # this suite changed, only where the application is assembled.
    #
    # The two cannot share a router table. The contract test asserts that
    # NOTHING is served which the Phase 4 contract does not declare, and every
    # legacy route fails that — so pointing this at app.main today would make
    # the contract suite red for a reason that has nothing to do with the
    # contract. app.main keeps serving the live desk until this app covers the
    # whole surface, at which point it becomes app.main and the legacy
    # routers are deleted in Phase 9.
    from app.api_v2.application import create_app

    return create_app()


@pytest.fixture()
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin(client) -> Operator:
    """The first operator, created by the documented bootstrap path.

    Bootstrapping is the one-time chicken-and-egg step: there is no admin to
    authorise creating the first admin. It is a runtime call, not a file and
    not a migration, so it does not violate the customer onboarding contract.
    """
    from app.tenancy import bootstrap

    slug = "admin-" + uuid.uuid4().hex[:8]
    password = "bootstrap-" + uuid.uuid4().hex
    tenant_id = bootstrap.create_first_admin(slug=slug, password=password)
    r = client.post("/api/v1/auth/login", json={"username": slug, "password": password})
    assert r.status_code == 200, r.text
    return Operator(slug=slug, password=password, tenant_id=tenant_id,
                    token=r.json()["token"])


def _make_operator(client, admin: Operator, slug: str) -> Operator:
    """Create a tenant entirely at runtime and sign in as them.

    This is the customer onboarding contract exercised as a fixture: three
    runtime writes, no file, no migration, no restart. If this ever needs
    more than the calls below, test_onboarding_tenant.py fails and says so.
    """
    password = "pw-" + uuid.uuid4().hex
    r = client.post(
        "/api/v1/tenants",
        json={"slug": slug, "display_name": slug.title(), "password": password},
        headers=admin.headers,
    )
    assert r.status_code == 201, r.text
    tenant_id = r.json()["tenant_id"]

    client.put(
        f"/api/v1/tenants/{tenant_id}/worlds",
        json={"worlds": {"tradier-platform": True, "36-trade-desk": True,
                         "bot-station": True},
              "default": "tradier-platform"},
        headers=admin.headers,
    ).raise_for_status()

    r = client.post("/api/v1/auth/login", json={"username": slug, "password": password})
    assert r.status_code == 200, r.text
    return Operator(slug=slug, password=password, tenant_id=tenant_id,
                    token=r.json()["token"])


@pytest.fixture()
def alice(client, admin) -> Operator:
    return _make_operator(client, admin, "alice-" + uuid.uuid4().hex[:8])


@pytest.fixture()
def bob(client, admin) -> Operator:
    return _make_operator(client, admin, "bob-" + uuid.uuid4().hex[:8])


@pytest.fixture()
def two_operators_with_lookalike_data(client, alice, bob):
    """Alice and Bob, each holding data that LOOKS like the other's.

    Deliberately overlapping: same symbol, same contract, same bot, same
    quantities. A leak that returned "a SPY call position" would otherwise
    look plausible in Alice's response. Only the ids differ, so any crossing
    of the boundary is unambiguous.
    """
    made = {}
    for who in (alice, bob):
        pos = client.post(
            "/api/v1/tradier/positions",
            json={"symbol": "SPY", "side": "call", "buy_pct": 10,
                  "tp_pct": 15, "sl_pct": 30, "live": False},
            headers={**who.headers, "Idempotency-Key": uuid.uuid4().hex},
        )
        assert pos.status_code in (200, 201), pos.text
        run = client.post(
            "/api/v1/bots/btc15/start",
            json={"version": "v2", "bankroll": 50, "target_pct": 25},
            headers={**who.headers, "Idempotency-Key": uuid.uuid4().hex},
        )
        made[who.slug] = {
            "position_id": pos.json()["id"],
            "run_id": run.json().get("run_id") if run.status_code < 300 else None,
        }
    return {"alice": alice, "bob": bob, "made": made}
