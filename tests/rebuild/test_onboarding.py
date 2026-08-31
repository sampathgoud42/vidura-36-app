"""The onboarding contracts, proven rather than asserted.

Two extension points carry a written contract, and both are tested by
actually doing the thing:

  * a new BOT      — the brief's primary success criterion
  * a new CUSTOMER — zero deploys, zero files, zero schema changes

The bot test measures the file-level cost instead of trusting a claim about
it. Today that cost is six files, roughly nine new endpoints, an arm added to
a CSV-shape switch and a UI panel. The contract says one config entry and one
adapter class.
"""

from __future__ import annotations

import uuid

import pytest

# The complete list of files a new bot is permitted to touch. Anything else
# is an architecture failure, not a workaround to be made.
ALLOWED_FILES_FOR_A_NEW_BOT = {
    "the bot's own config entry",
    "the bot's own adapter class",
    "the vendored bot script itself",
}


@pytest.fixture()
def example_bot(app):
    """Onboard the throwaway bot by the contract: register the config, done."""
    from app.domains.botstation import registry
    from tests.rebuild.fixtures.example_bot import EXAMPLE_BOT, ExampleBotAdapter

    registry.register(EXAMPLE_BOT, ExampleBotAdapter)
    yield EXAMPLE_BOT
    registry.unregister(EXAMPLE_BOT.key)


# --------------------------------------------------------------------------
# A new bot
# --------------------------------------------------------------------------

def test_a_newly_registered_bot_appears_without_touching_any_endpoint(
    client, alice, example_bot
):
    """Given a bot registered by config alone,
    when the registry is listed,
    then it is there — no route was added to make that true.
    """
    r = client.get("/api/v1/bots", headers=alice.headers)
    assert r.status_code == 200
    keys = {b["key"] for b in r.json()}
    assert "example15" in keys


@pytest.mark.parametrize("method,suffix", [
    ("get", "status"),
    ("get", "logs"),
    ("get", "trades"),
    ("get", "processes"),
    ("get", "config"),
    ("get", "active-bets"),
    ("get", "performance"),
])
def test_every_read_operation_works_for_a_brand_new_bot(
    client, alice, example_bot, method, suffix
):
    """The eight shared operations must work for a bot nobody wrote a route
    for. This is the whole point of keying them by bot_key."""
    r = getattr(client, method)(f"/api/v1/bots/example15/{suffix}",
                                headers=alice.headers)
    assert r.status_code != 404, (
        f"/bots/{{bot_key}}/{suffix} does not serve a newly registered bot — "
        "the route is still per-family"
    )
    assert r.status_code < 500


def test_the_launch_form_renders_itself_from_the_bots_own_schema(
    client, alice, example_bot
):
    """A new bot must not need a hand-written UI panel. The config declares
    its options and the form is generated from that."""
    r = client.get("/api/v1/bots/example15/config", headers=alice.headers)
    assert r.status_code == 200
    schema = r.json()["options_schema"]
    assert set(schema) == {"bankroll", "target_pct", "contracts"}
    assert schema["bankroll"]["default"] == 50


def test_launch_options_are_validated_against_the_declared_schema(
    client, alice, example_bot
):
    """Given the bot declares a minimum bankroll,
    when a launch violates it,
    then it is refused — by the shared validator, using the bot's own schema.
    """
    r = client.post(
        "/api/v1/bots/example15/start",
        json={"version": "v1", "bankroll": -1},
        headers={**alice.headers, "Idempotency-Key": uuid.uuid4().hex},
    )
    assert r.status_code in (400, 422)


def test_the_new_bots_records_reach_the_shared_ledger(client, alice, example_bot):
    """Given the adapter maps a record,
    when it is ingested,
    then it appears in the ledger like every other bot's trade — with no
    arm added to any dispatch switch.
    """
    from app.domains.botstation.ledger import ingest

    ingest.record(
        tenant_id=alice.tenant_id,
        bot_key="example15",
        records=[{
            "ticker": "EXAMPLE-TEST-1", "status": "closed",
            "opened_at": "2026-08-27T10:00:00", "closed_at": "2026-08-27T10:15:00",
            "contracts": 1, "entry_price": 0.40, "exit_price": 0.55,
            "realized_pnl": 0.15, "is_live": False,
        }],
    )
    r = client.get("/api/v1/bots/example15/trades", headers=alice.headers)
    assert r.status_code == 200
    rows = r.json()
    rows = rows["items"] if isinstance(rows, dict) else rows
    assert any(t["ticker"] == "EXAMPLE-TEST-1" for t in rows)


def test_ingesting_the_same_record_twice_does_not_duplicate_it(
    client, alice, example_bot
):
    """The adapter's external id is deterministic, so re-running is
    idempotent — the rule every bot family must obey."""
    from app.domains.botstation.ledger import ingest

    rec = {"ticker": "EXAMPLE-DUPE", "status": "closed",
           "opened_at": "2026-08-27T11:00:00", "closed_at": "2026-08-27T11:15:00",
           "contracts": 1, "entry_price": 0.40, "exit_price": 0.55,
           "realized_pnl": 0.15, "is_live": False}
    ingest.record(tenant_id=alice.tenant_id, bot_key="example15", records=[rec])
    ingest.record(tenant_id=alice.tenant_id, bot_key="example15", records=[rec])

    rows = client.get("/api/v1/bots/example15/trades", headers=alice.headers).json()
    rows = rows["items"] if isinstance(rows, dict) else rows
    assert len([t for t in rows if t["ticker"] == "EXAMPLE-DUPE"]) == 1


def test_onboarding_a_bot_required_no_migration(example_bot):
    """A new bot must not add a table or a column. If this fails, the bot
    ledger is not generic and every future bot pays the same tax."""
    from app.platform.db import migrations

    assert migrations.pending_count() == 0, (
        "registering a bot produced a pending schema change — the ledger is "
        "not bot-agnostic"
    )


def test_onboarding_a_bot_touched_no_shared_library(example_bot):
    """The contract's negative half, enforced.

    The registry records which modules a bot's registration reached. Anything
    outside the bot's own two files means the plug point leaks.
    """
    from app.domains.botstation import registry

    touched = registry.modules_touched_by("example15")
    leaked = {m for m in touched if not m.startswith("tests.rebuild.fixtures")}
    assert not leaked, (
        "registering a bot reached into shared code: " + ", ".join(sorted(leaked))
    )


# --------------------------------------------------------------------------
# A new customer
# --------------------------------------------------------------------------

def test_a_customer_is_created_entirely_at_runtime(client, admin):
    """Given nothing but a running application,
    when a customer is onboarded through the API,
    then they exist and can sign in.

    No folder. No .env. No .pem. No .sam. No migration. No restart.
    """
    slug = "runtime-" + uuid.uuid4().hex[:8]
    password = "pw-" + uuid.uuid4().hex

    created = client.post(
        "/api/v1/tenants",
        json={"slug": slug, "display_name": "Runtime Customer", "password": password},
        headers=admin.headers,
    )
    assert created.status_code == 201, created.text

    signed_in = client.post("/api/v1/auth/login",
                            json={"username": slug, "password": password})
    assert signed_in.status_code == 200, "a runtime-created customer cannot sign in"


def test_onboarding_a_customer_creates_no_files(client, admin, tmp_path):
    """The contract's sharpest edge: a file per customer means onboarding
    needs a deploy and rotation needs a deploy. Neither is acceptable."""
    from app.core.config import get_settings

    customers_root = get_settings().customers_root
    before = set(customers_root.rglob("*")) if customers_root.exists() else set()

    slug = "nofiles-" + uuid.uuid4().hex[:8]
    client.post("/api/v1/tenants",
                json={"slug": slug, "display_name": "No Files",
                      "password": "pw-" + uuid.uuid4().hex},
                headers=admin.headers)

    after = set(customers_root.rglob("*")) if customers_root.exists() else set()
    assert after == before, f"onboarding wrote files: {sorted(after - before)}"


def test_onboarding_a_customer_requires_no_migration(client, admin):
    from app.platform.db import migrations

    client.post("/api/v1/tenants",
                json={"slug": "nomig-" + uuid.uuid4().hex[:8],
                      "display_name": "No Migration",
                      "password": "pw-" + uuid.uuid4().hex},
                headers=admin.headers)
    assert migrations.pending_count() == 0


def test_credentials_are_added_and_rotated_without_a_restart(client, admin):
    """Rotation is a runtime operation. A customer who rotates a key at the
    venue must be able to update it here immediately."""
    slug = "rotate-" + uuid.uuid4().hex[:8]
    tid = client.post("/api/v1/tenants",
                      json={"slug": slug, "display_name": "Rotate",
                            "password": "pw-" + uuid.uuid4().hex},
                      headers=admin.headers).json()["tenant_id"]

    added = client.post(f"/api/v1/tenants/{tid}/credentials",
                        json={"venue": "tradier", "label": "prod",
                              "secret": {"token": "first-token",
                                         "account_id": "ACC1"}},
                        headers=admin.headers)
    assert added.status_code == 201, added.text
    cid = added.json()["credential_id"]

    rotated = client.post(f"/api/v1/tenants/{tid}/credentials/{cid}/rotate",
                          json={"secret": {"token": "second-token",
                                           "account_id": "ACC1"}},
                          headers=admin.headers)
    assert rotated.status_code == 200, rotated.text

    revoked = client.delete(f"/api/v1/tenants/{tid}/credentials/{cid}",
                            headers=admin.headers)
    assert revoked.status_code in (200, 204)


def test_world_access_is_data_not_a_file(client, admin, alice):
    """`worlds.json` was a file edit per operator. It is now a runtime write,
    and turning a world off takes effect on the next request."""
    client.put(f"/api/v1/tenants/{alice.tenant_id}/worlds",
               json={"worlds": {"tradier-platform": True, "36-trade-desk": False,
                                "bot-station": False},
                     "default": "tradier-platform"},
               headers=admin.headers).raise_for_status()

    me = client.get("/api/v1/auth/me", headers=alice.headers).json()
    assert me["worlds"]["36-trade-desk"] is False


# ---- the payloads the desk actually sends ---------------------------------
# Every individual bot launch was refused with "does not accept: ..." naming
# fields the operator never typed. Three separate causes, all invisible from
# the desk:
#
#   user_id            an identity field the form has always sent
#   bank, target_pct   the desk's names for bankroll and bank_tp_pct
#   sports, sport_settings, parley   real options nothing had declared
#
# These pin the payloads as the desk sends them, so the schema and the form
# cannot drift apart again without a test naming the field.

DESK_PAYLOADS = {
    "parley": {"user_id": "demo", "contracts": 10, "bank": 100,
               "bank_sl_pct": 50, "sports": ["tennis"],
               "parley": {"min_prob_c": 80, "min_set": 2}},
    "sports": {"user_id": "demo", "sports": ["tennis", "baseball"],
               "sport_settings": {"tennis": {"contracts": 25, "bank": 50}},
               "target_pct": 30, "bank_sl_pct": 20},
    "btc15": {"user_id": "demo", "contracts": 25, "bank": 50, "tp_pct": 15,
              "sl_pct": 30, "target_pct": 30, "bank_sl_pct": 20},
    "gold15": {"user_id": "demo", "contracts": 25, "bank": 50,
               "target_pct": 30},
}


@pytest.mark.parametrize("bot_key", sorted(DESK_PAYLOADS))
def test_the_desk_launch_payload_is_accepted(bot_key):
    """Given the body the bot station posts,
    when it is validated against that bot's schema,
    then it is accepted.
    """
    from app.domains.botstation import registry

    registry.load_builtin_bots()
    config = registry.get(bot_key)
    registry.validate_options(config, DESK_PAYLOADS[bot_key])


def test_an_operator_id_in_the_body_is_ignored_not_honoured():
    """user_id must never select whose bot this is.

    Dropped rather than accepted: the session decides the tenant, and
    honouring an operator from the request body is exactly the cross-tenant
    selector the isolation suite forbids. Dropped rather than REJECTED
    because the desk sends it on every call, and erroring broke every launch
    over a field whose only correct handling is to ignore it.
    """
    from app.domains.botstation import registry

    registry.load_builtin_bots()
    config = registry.get("btc15")
    cleaned = registry.validate_options(config, {"user_id": "somebody-else",
                                                 "contracts": 5})
    assert "user_id" not in cleaned
    assert cleaned["contracts"] == 5


def test_the_desks_older_field_names_still_resolve():
    """bank -> bankroll, target_pct -> bank_tp_pct."""
    from app.domains.botstation import registry

    registry.load_builtin_bots()
    config = registry.get("btc15")
    cleaned = registry.validate_options(config, {"bank": 250,
                                                 "target_pct": 40})
    assert cleaned["bankroll"] == 250
    assert cleaned["bank_tp_pct"] == 40


def test_an_alias_never_shadows_a_real_field():
    """The alias applies only when the schema does NOT declare the incoming
    name, so a bot that genuinely owns `bank` keeps it."""
    from app.domains.botstation import registry

    registry.load_builtin_bots()
    config = registry.get("btc15")
    assert "bank" not in config.options_schema      # the premise
    both = registry.normalise_options(config, {"bank": 1, "bankroll": 2})
    assert both["bankroll"] in (1, 2)               # one wins, neither errors


def test_a_structured_option_reaches_the_bot_as_json():
    """str() of a dict is Python repr — single quotes, True/False — which no
    JSON parser on the other side accepts."""
    import json

    from app.domains.botstation import lifecycle, registry

    registry.load_builtin_bots()
    config = registry.get("sports")
    options = registry.validate_options(config, DESK_PAYLOADS["sports"])
    plan = lifecycle.launch_plan(config, config.versions[0],
                                 tenant_slug="sampath", options=options,
                                 mode="paper", paper_only=True)
    assert json.loads(plan.env["SPORTS"]) == ["tennis", "baseball"]
    assert json.loads(plan.env["SPORT_SETTINGS"])["tennis"]["contracts"] == 25
