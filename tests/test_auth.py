"""The desk login — this project's own gate, so its own tests.

conftest turns the gate OFF for the whole suite (every mirrored test
predates it and calls the API bare). These tests turn it back on per case,
which is also a check worth having: the middleware reads the setting on
every request rather than capturing it at startup.
"""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.services import sessions as session_svc


@pytest.fixture
def gated(monkeypatch):
    """Login required, and a clean session/lockout store."""
    settings = get_settings()
    monkeypatch.setattr(settings, "login_required", True)
    monkeypatch.setattr(settings, "api_key", "")
    session_svc.revoke_all()
    session_svc._FAILURES.clear()
    yield settings
    session_svc.revoke_all()
    session_svc._FAILURES.clear()


@pytest.fixture
def operator(db_session, user_folder):
    """An operator whose folder carries the conftest .sam password.

    The row is inserted directly rather than through POST /users, because
    that endpoint is itself behind the gate these tests turn on — creating
    the user over HTTP would be refused by the thing under test.
    """
    from app.core import paths
    from app.models import User

    row = User(username="testuser", email="auth@example.com",
               user_root_folder=paths.canonical_str(str(user_folder)))
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return {"user": {"username": row.username, "user_id": row.user_id},
            "password": "test-pass-123", "folder": user_folder}


# --- the gate --------------------------------------------------------------

def test_api_is_closed_without_a_session(client, gated):
    r = client.get("/api/v1/users")
    assert r.status_code == 401
    assert r.json()["login_required"] is True


def test_login_and_status_stay_open(client, gated):
    # A browser must be able to fetch these before it has any credential,
    # or it can never render a login screen.
    assert client.get("/api/v1/auth/status").status_code == 200
    r = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "x"})
    assert r.status_code == 401          # reached the handler, not the guard


def test_health_and_docs_stay_open(client, gated):
    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 200


def test_preflight_is_never_refused(client, gated):
    # A CORS preflight carries no headers to check; refusing it breaks the
    # browser before the real request is ever sent.
    r = client.options(
        "/api/v1/users",
        headers={"Origin": "http://localhost:5199",
                 "Access-Control-Request-Method": "GET"},
    )
    assert r.status_code < 400


# --- signing in ------------------------------------------------------------

def test_correct_password_opens_the_api(client, gated, operator):
    r = client.post("/api/v1/auth/login",
                    json={"username": operator["user"]["username"],
                          "password": operator["password"]})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert len(token) > 20

    assert client.get("/api/v1/users",
                      headers={"X-API-Key": token}).status_code == 200


def test_username_is_case_insensitive(client, gated, operator):
    r = client.post("/api/v1/auth/login",
                    json={"username": operator["user"]["username"].upper(),
                          "password": operator["password"]})
    assert r.status_code == 200


def test_wrong_password_is_refused(client, gated, operator):
    r = client.post("/api/v1/auth/login",
                    json={"username": operator["user"]["username"],
                          "password": "not-it"})
    assert r.status_code == 401


def test_unknown_user_is_indistinguishable_from_a_bad_password(client, gated, operator):
    """The login screen must not confirm which operators exist."""
    bad_user = client.post("/api/v1/auth/login",
                           json={"username": "ghost", "password": "x"})
    bad_pass = client.post("/api/v1/auth/login",
                           json={"username": operator["user"]["username"],
                                 "password": "x"})
    assert bad_user.status_code == bad_pass.status_code == 401
    assert bad_user.json()["detail"] == bad_pass.json()["detail"]


def test_me_reports_the_session_but_never_the_token(client, gated, operator):
    token = client.post("/api/v1/auth/login",
                        json={"username": operator["user"]["username"],
                              "password": operator["password"]}).json()["token"]
    body = client.get("/api/v1/auth/me", headers={"X-API-Key": token}).json()
    assert body["username"] == operator["user"]["username"]
    assert "token" not in body


def test_logout_kills_the_token(client, gated, operator):
    token = client.post("/api/v1/auth/login",
                        json={"username": operator["user"]["username"],
                              "password": operator["password"]}).json()["token"]
    h = {"X-API-Key": token}
    assert client.post("/api/v1/auth/logout", headers=h).json()["logged_out"] is True
    assert client.get("/api/v1/users", headers=h).status_code == 401


def test_a_forged_token_is_refused(client, gated):
    assert client.get("/api/v1/users",
                      headers={"X-API-Key": "a" * 43}).status_code == 401


def test_an_expired_session_is_refused(client, gated, operator, monkeypatch):
    monkeypatch.setattr(get_settings(), "session_ttl_s", -1)
    token = client.post("/api/v1/auth/login",
                        json={"username": operator["user"]["username"],
                              "password": operator["password"]}).json()["token"]
    assert client.get("/api/v1/users",
                      headers={"X-API-Key": token}).status_code == 401


# --- brute force -----------------------------------------------------------

def test_repeated_failures_lock_the_account(client, gated, operator):
    """verify_password already burns a second per failure; the lockout is
    what stops an attacker simply waiting that out."""
    name = operator["user"]["username"]
    for _ in range(session_svc._LOCK_AFTER):
        client.post("/api/v1/auth/login", json={"username": name, "password": "x"})

    r = client.post("/api/v1/auth/login",
                    json={"username": name, "password": operator["password"]})
    assert r.status_code == 429, "the right password must not bypass the lockout"

    session_svc.clear_failures(name)
    assert client.post("/api/v1/auth/login",
                       json={"username": name,
                             "password": operator["password"]}).status_code == 200


def test_a_good_login_clears_the_failure_count(client, gated, operator):
    name = operator["user"]["username"]
    for _ in range(session_svc._LOCK_AFTER - 1):
        client.post("/api/v1/auth/login", json={"username": name, "password": "x"})
    assert client.post("/api/v1/auth/login",
                       json={"username": name,
                             "password": operator["password"]}).status_code == 200
    assert session_svc.lockout_remaining(name) == 0


# --- the shared key still works for scripts --------------------------------

def test_the_shared_key_is_accepted_instead_of_a_session(client, gated, monkeypatch):
    monkeypatch.setattr(get_settings(), "api_key", "script-key")
    assert client.get("/api/v1/users",
                      headers={"X-API-Key": "script-key"}).status_code == 200
    assert client.get("/api/v1/users",
                      headers={"X-API-Key": "wrong"}).status_code == 401


def test_gate_off_means_open(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "login_required", False)
    monkeypatch.setattr(get_settings(), "api_key", "")
    assert client.get("/api/v1/users").status_code == 200


# --- the scoped GEX push token --------------------------------------------
# A bookmarklet running on getgamma.io carries this token. If it ever opened
# more than the two ingest paths, a leak from someone else's page would reach
# a live trading API.

PUSH_REFRESH = "/api/v1/super/gex0dte/refresh"
PUSH_BEAT = "/api/v1/super/gex0dte/heartbeat"

MIN_PAYLOAD = {
    "ticker": "SPY", "spotPrice": 769.0, "mode": "0dte",
    "timestamp": "2026-08-19T15:00:00Z",
    "marketStatus": "open", "marketOpen": True,
    "contracts": [
        {"contract_type": "call", "strike_price": 770.0,
         "open_interest": 21000, "greeks": {"gamma": 0.045}},
        {"contract_type": "put", "strike_price": 770.0,
         "open_interest": 15500, "greeks": {"gamma": 0.041}},
    ],
}


@pytest.fixture
def push_token(gated, monkeypatch):
    monkeypatch.setattr(get_settings(), "gex_push_token", "push-token-xyz")
    return "push-token-xyz"


def test_push_token_opens_the_ingest_paths(client, push_token):
    h = {"X-API-Key": push_token}
    assert client.post(PUSH_REFRESH, json={"payload": MIN_PAYLOAD},
                       headers=h).status_code == 200
    assert client.post(PUSH_BEAT, headers=h, json={
        "session": "abc", "seq": 1, "ok": True, "reason": "",
        "wall": 1787000000000, "mono": 12}).status_code == 200


@pytest.mark.parametrize("path", [
    "/api/v1/users",
    "/api/v1/super/signals",
    "/api/v1/tradier/positions",
    "/api/v1/levels/status",
])
def test_push_token_opens_nothing_else(client, push_token, path):
    """The whole reason this token exists instead of TBOT_API_KEY."""
    assert client.get(path, headers={"X-API-Key": push_token}).status_code == 401


def test_the_ingest_paths_still_need_a_credential(client, push_token):
    assert client.post(PUSH_REFRESH, json={"payload": MIN_PAYLOAD}).status_code == 401
    assert client.post(PUSH_REFRESH, json={"payload": MIN_PAYLOAD},
                       headers={"X-API-Key": "wrong"}).status_code == 401


def test_an_unset_push_token_grants_nothing(client, gated, monkeypatch):
    """Empty must not mean 'any token works', nor 'no token works'."""
    monkeypatch.setattr(get_settings(), "gex_push_token", "")
    assert client.post(PUSH_REFRESH, json={"payload": MIN_PAYLOAD},
                       headers={"X-API-Key": ""}).status_code == 401


def test_a_session_can_still_push(client, gated, operator):
    """The desk's own refresh button must keep working."""
    token = client.post("/api/v1/auth/login",
                        json={"username": operator["user"]["username"],
                              "password": operator["password"]}).json()["token"]
    assert client.post(PUSH_REFRESH, json={"payload": MIN_PAYLOAD},
                       headers={"X-API-Key": token}).status_code == 200
