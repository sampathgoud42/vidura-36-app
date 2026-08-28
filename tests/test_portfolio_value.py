"""Live portfolio value for the sports desk.

PV must match what the bots print as [TARGET-PV] — settled cash PLUS the
mark-to-market value of open positions — so the desk and the bot logs never
disagree. Kalshi returns both in cents on /portfolio/balance.

Never hits the network: the Kalshi client is stubbed.
"""

from __future__ import annotations

import pytest

from app.api.v1 import kalshi as kalshi_api
from app.services.kalshi_client import KalshiApiError, KalshiClient


@pytest.fixture(autouse=True)
def clear_pv_cache():
    kalshi_api._pv_cache.clear()
    yield
    kalshi_api._pv_cache.clear()


@pytest.fixture
def kalshi_user(client, tmp_path):
    """A user whose folder carries usable-looking Kalshi credentials."""
    root = tmp_path / "cust"
    root.mkdir()
    (root / ".env").write_text(
        "KALSHI_API_KEY_ID=test-key\n"
        "KALSHI_PRIVATE_KEY=k.pem\n"
        "BASE_URI=https://external-api.kalshi.com/trade-api/v2\n",
        encoding="utf-8",
    )
    (root / "k.pem").write_text("not-a-real-key", encoding="utf-8")
    return client.post(
        "/api/v1/users", json={"username": "pv", "user_root_folder": str(root)}
    ).json()


def _stub(monkeypatch, payload=None, raises=None, calls=None):
    class Stub:
        def __init__(self, *a, **k):
            pass

        def portfolio(self):
            if calls is not None:
                calls.append(1)
            if raises:
                raise raises
            return payload

        def close(self):
            pass

    monkeypatch.setattr(kalshi_api, "KalshiClient", Stub)


# ---- the PV definition ----------------------------------------------------

def test_total_is_cash_plus_open_positions(monkeypatch, client, kalshi_user):
    _stub(monkeypatch, {"cash_usd": 40.0, "positions_usd": 62.72, "total_usd": 102.72})
    r = client.get(f"/api/v1/users/{kalshi_user['user_id']}/portfolio")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["total_usd"] == 102.72
    assert b["cash_usd"] == 40.0 and b["positions_usd"] == 62.72
    assert b["fetched_at"] and b["cached"] is False


def test_client_wrapper_converts_cents_and_sums(monkeypatch):
    """The wrapper itself, against Kalshi's raw cents payload."""
    c = KalshiClient.__new__(KalshiClient)
    monkeypatch.setattr(
        KalshiClient,
        "request",
        lambda self, *a, **k: {"balance": 4000, "portfolio_value": 6272},
    )
    assert c.portfolio() == {
        "cash_usd": 40.0,
        "positions_usd": 62.72,
        "total_usd": 102.72,
    }


def test_zero_positions_is_just_cash(monkeypatch):
    c = KalshiClient.__new__(KalshiClient)
    monkeypatch.setattr(
        KalshiClient, "request", lambda self, *a, **k: {"balance": 120, "portfolio_value": 0}
    )
    assert c.portfolio()["total_usd"] == 1.2


def test_missing_fields_do_not_explode(monkeypatch):
    c = KalshiClient.__new__(KalshiClient)
    monkeypatch.setattr(KalshiClient, "request", lambda self, *a, **k: {})
    assert c.portfolio() == {"cash_usd": 0.0, "positions_usd": 0.0, "total_usd": 0.0}


# ---- caching --------------------------------------------------------------

def test_repeat_calls_are_served_from_cache(monkeypatch, client, kalshi_user):
    calls: list = []
    _stub(monkeypatch, {"cash_usd": 1.0, "positions_usd": 2.0, "total_usd": 3.0}, calls=calls)
    uid = kalshi_user["user_id"]
    first = client.get(f"/api/v1/users/{uid}/portfolio").json()
    second = client.get(f"/api/v1/users/{uid}/portfolio").json()
    assert len(calls) == 1, "second read hit Kalshi instead of the cache"
    assert first["cached"] is False and second["cached"] is True
    assert second["total_usd"] == first["total_usd"]


def test_cache_is_per_user(monkeypatch, client, kalshi_user, tmp_path):
    calls: list = []
    _stub(monkeypatch, {"cash_usd": 1.0, "positions_usd": 0.0, "total_usd": 1.0}, calls=calls)
    other_root = tmp_path / "other"
    other_root.mkdir()
    (other_root / ".env").write_text(
        "KALSHI_API_KEY_ID=k2\nKALSHI_PRIVATE_KEY=k.pem\nBASE_URI=https://x/trade-api/v2\n",
        encoding="utf-8",
    )
    (other_root / "k.pem").write_text("x", encoding="utf-8")
    other = client.post(
        "/api/v1/users", json={"username": "pv2", "user_root_folder": str(other_root)}
    ).json()

    client.get(f"/api/v1/users/{kalshi_user['user_id']}/portfolio")
    client.get(f"/api/v1/users/{other['user_id']}/portfolio")
    assert len(calls) == 2, "one user's PV was served to another"


# ---- failure modes --------------------------------------------------------

def test_upstream_failure_is_502_not_500(monkeypatch, client, kalshi_user):
    _stub(monkeypatch, raises=KalshiApiError(500, "kalshi exploded"))
    r = client.get(f"/api/v1/users/{kalshi_user['user_id']}/portfolio")
    assert r.status_code == 502


def test_network_failure_is_502(monkeypatch, client, kalshi_user):
    _stub(monkeypatch, raises=ConnectionError("dns"))
    r = client.get(f"/api/v1/users/{kalshi_user['user_id']}/portfolio")
    assert r.status_code == 502
    assert "unreachable" in r.json()["detail"].lower()


def test_missing_credentials_is_424(client, tmp_path):
    root = tmp_path / "bare"
    root.mkdir()
    u = client.post(
        "/api/v1/users", json={"username": "nocreds", "user_root_folder": str(root)}
    ).json()
    r = client.get(f"/api/v1/users/{u['user_id']}/portfolio")
    assert r.status_code == 424


def test_unknown_user_is_404(client):
    assert client.get("/api/v1/users/nope/portfolio").status_code == 404


def test_a_failed_fetch_is_not_cached(monkeypatch, client, kalshi_user):
    """A 502 must not poison the cache for the next 30 seconds."""
    calls: list = []
    _stub(monkeypatch, raises=ConnectionError("blip"), calls=calls)
    uid = kalshi_user["user_id"]
    assert client.get(f"/api/v1/users/{uid}/portfolio").status_code == 502
    _stub(monkeypatch, {"cash_usd": 5.0, "positions_usd": 0.0, "total_usd": 5.0}, calls=calls)
    r = client.get(f"/api/v1/users/{uid}/portfolio")
    assert r.status_code == 200 and r.json()["total_usd"] == 5.0
