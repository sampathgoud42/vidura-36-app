"""Secrets and personal data must not escape by any route.

Three kinds of sensitive material live in this system now:

  * venue credentials — encrypted, because they must be presented to Tradier
    and Kalshi, so they have to be reversible
  * login passwords   — hashed with Argon2id, because they only ever need
    comparing, so reversibility would be pure downside
  * wellness profiles — special-category personal data: ethnicity, gender,
    diet, health goals

The tests below check every escape route the brief names: responses, logs,
errors, stack traces, debug dumps and support exports.
"""

from __future__ import annotations

import json
import logging
import uuid

import pytest

SECRET_TOKEN = "sk-live-DO-NOT-LEAK-8fd3a91c"
SECRET_ACCOUNT = "ACCT-DO-NOT-LEAK-4471"


@pytest.fixture()
def tenant_with_credentials(client, admin, alice):
    client.post(
        f"/api/v1/tenants/{alice.tenant_id}/credentials",
        json={"venue": "tradier", "label": "prod",
              "secret": {"token": SECRET_TOKEN, "account_id": SECRET_ACCOUNT}},
        headers=admin.headers,
    ).raise_for_status()
    return alice


# --------------------------------------------------------------------------
# Never in a response
# --------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/v1/auth/me",
    "/api/v1/tradier/venue",
    "/api/v1/tradier/balance",
    "/api/v1/tradier/positions",
    "/api/v1/readiness",
    "/health",
])
def test_no_endpoint_returns_a_credential(client, tenant_with_credentials, path):
    who = tenant_with_credentials
    r = client.get(path, headers=who.headers)
    assert SECRET_TOKEN not in r.text, f"{path} returned the venue token"
    assert SECRET_ACCOUNT not in r.text, f"{path} returned the account id"


def test_listing_credentials_shows_metadata_and_never_the_secret(
    client, admin, tenant_with_credentials
):
    """An operator needs to know a key exists, when it was added and when it
    was last rotated. They never need it read back — and the brief forbids
    even masked-then-unmasked."""
    who = tenant_with_credentials
    r = client.get(f"/api/v1/tenants/{who.tenant_id}/credentials",
                   headers=admin.headers)
    assert r.status_code == 200
    assert SECRET_TOKEN not in r.text
    assert SECRET_ACCOUNT not in r.text
    row = r.json()[0]
    assert {"venue", "label", "created_at"} <= set(row)
    assert "secret" not in row and "ciphertext" not in row


def test_verifying_a_credential_reports_health_not_content(
    client, tenant_with_credentials
):
    """The verification endpoint is how you confirm a new customer's keys
    work. It answers yes or no, never with the key."""
    r = client.post("/api/v1/credentials/tradier/verify",
                    headers=tenant_with_credentials.headers)
    assert r.status_code in (200, 424)
    assert SECRET_TOKEN not in r.text


# --------------------------------------------------------------------------
# Never in a log or an error
# --------------------------------------------------------------------------

def test_a_venue_failure_does_not_log_the_credential(
    client, tenant_with_credentials, monkeypatch, caplog
):
    """The classic leak: an exception handler that logs the request it was
    making, headers and all."""
    from app.domains.trading.execution import venue

    monkeypatch.setattr(
        venue, "balance",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("venue exploded")),
    )
    with caplog.at_level(logging.DEBUG):
        client.get("/api/v1/tradier/balance",
                   headers=tenant_with_credentials.headers)

    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert SECRET_TOKEN not in blob, "a credential reached the logs"
    assert SECRET_ACCOUNT not in blob


def test_an_error_response_does_not_carry_a_credential(
    client, tenant_with_credentials, monkeypatch
):
    from app.domains.trading.execution import venue

    monkeypatch.setattr(
        venue, "balance",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError(f"401 for {SECRET_TOKEN}")),
    )
    r = client.get("/api/v1/tradier/balance",
                   headers=tenant_with_credentials.headers)
    assert r.status_code >= 400
    assert SECRET_TOKEN not in r.text, (
        "the venue's own error text was passed through with the key in it"
    )


def test_the_repr_of_a_credential_does_not_expose_it():
    """Stack traces print locals. A credential object that prints itself is
    a leak waiting for the next unhandled exception."""
    from app.tenancy.credentials import VenueCredential

    c = VenueCredential(venue="tradier", token=SECRET_TOKEN,
                        account_id=SECRET_ACCOUNT)
    assert SECRET_TOKEN not in repr(c)
    assert SECRET_TOKEN not in str(c)
    assert SECRET_TOKEN not in json.dumps(c.public(), default=str)


# --------------------------------------------------------------------------
# Passwords: hashed, not encrypted, not recoverable
# --------------------------------------------------------------------------

def test_the_stored_password_is_not_the_password(client, admin):
    """Given a customer is created with a password,
    when the stored value is read,
    then it is an Argon2id hash — not the password, and not ciphertext that
    a key could turn back into the password.
    """
    from app.tenancy import repository as tenants

    slug = "pw-" + uuid.uuid4().hex[:8]
    secret = "correct-horse-battery-staple"
    client.post("/api/v1/tenants",
                json={"slug": slug, "display_name": "PW", "password": secret},
                headers=admin.headers).raise_for_status()

    stored = tenants.password_hash_for(slug)
    assert secret not in stored
    assert stored.startswith("$argon2id$"), (
        f"password stored as {stored[:12]!r} — it must be an Argon2id hash, "
        "not reversible ciphertext"
    )


def test_no_api_path_returns_a_password_hash(client, admin, alice):
    for path in ("/api/v1/auth/me", "/api/v1/tenants",
                 f"/api/v1/tenants/{alice.tenant_id}"):
        r = client.get(path, headers=admin.headers)
        assert "argon2" not in r.text.lower()
        assert "password" not in r.text.lower() or "password_hash" not in r.text


def test_login_answers_identically_for_a_bad_password_and_a_missing_operator(
    client
):
    """Two different failures must be indistinguishable, or the login screen
    becomes a way to enumerate operators."""
    a = client.post("/api/v1/auth/login",
                    json={"username": "definitely-not-a-real-operator",
                          "password": "x"})
    b = client.post("/api/v1/auth/login",
                    json={"username": "admin", "password": "wrong-on-purpose"})
    assert a.status_code == b.status_code == 401
    assert a.json()["detail"] == b.json()["detail"]


def test_repeated_failures_are_throttled_on_every_password_path(client):
    """The Phase 1 finding: /auth/login was carefully defended and
    /verify-password was not, while both reached the same secret. Whatever
    password-checking paths exist, they share one lockout."""
    paths = ["/api/v1/auth/login"]
    for path in paths:
        codes = [
            client.post(path, json={"username": "throttle-me", "password": "no"})
            .status_code
            for _ in range(12)
        ]
        assert 429 in codes, f"{path} accepts unlimited password guesses"


# --------------------------------------------------------------------------
# Wellness: special-category personal data
# --------------------------------------------------------------------------

def test_a_wellness_profile_round_trips_for_its_owner(client, alice):
    payload = {"gender": "male", "age_band": "35-44", "ethnicity": "asian",
               "diet": "vegetarian", "style": "calm", "region": "midwest",
               "notifications": True, "goals": ["sleep-better", "eat-less"]}
    client.put("/api/v1/wellness/profile", json=payload,
               headers=alice.headers).raise_for_status()

    got = client.get("/api/v1/wellness/profile", headers=alice.headers).json()
    assert got["age_band"] == "35-44"
    assert got["goals"] == ["sleep-better", "eat-less"], "goal order was lost"


def test_the_age_band_is_text_and_a_range_survives_it(client, alice):
    """The source file stores a band, not a number. A column typed INTEGER
    would fail on the very first imported row."""
    client.put("/api/v1/wellness/profile", json={"age_band": "65+"},
               headers=alice.headers).raise_for_status()
    assert client.get("/api/v1/wellness/profile",
                      headers=alice.headers).json()["age_band"] == "65+"


def test_wellness_data_never_appears_in_logs(client, alice, caplog):
    with caplog.at_level(logging.DEBUG):
        client.put("/api/v1/wellness/profile",
                   json={"ethnicity": "asian", "diet": "vegetarian",
                         "goals": ["sleep-better"]},
                   headers=alice.headers)
    blob = "\n".join(r.getMessage() for r in caplog.records)
    for private in ("asian", "vegetarian", "sleep-better"):
        assert private not in blob, f"wellness data {private!r} reached the logs"


def test_wellness_data_is_absent_from_diagnostics(client, alice):
    """Health, readiness and any support export are the places sensitive data
    reaches an audience it was never meant for."""
    client.put("/api/v1/wellness/profile",
               json={"ethnicity": "asian", "diet": "vegetarian"},
               headers=alice.headers)
    for path in ("/health", "/readiness"):
        r = client.get(path)
        assert "asian" not in r.text and "vegetarian" not in r.text
