"""GEX live-fetch service — every test mocks the HTTP layer.

NEVER let these hit lab.flashalpha.com: the FREE plan allows 5 requests a
day and the desk depends on them.
"""

from __future__ import annotations

import json

import pytest

from app.core.config import get_settings
from app.services import gex as gex_svc

PAYLOAD = {
    "symbol": "SPY",
    "as_of": "2026-07-28T14:20:52.897Z",
    "price": {"last": 740.475},
    "volatility": {"atm_iv": 15.7},
    "options_flow": {"pc_ratio_volume": 0.354},
    "exposure": {
        "net_gex": -9178182877,
        "regime": "negative_gamma",
        "gamma_flip": 745.1068,
        "call_wall": 750,
        "put_wall": 740,
        "interpretation": {"gamma": "Dealers short gamma"},
    },
    "macro": {
        "vix": {"value": 18.72, "change_pct": 0.75},
        "vvix": {"value": 101.19},
        "skew": {"value": 147.28},
        "move": {"value": 76.81},
        "vix_term_structure": {"structure": "contango"},
        "fear_and_greed": {"score": 41},
    },
}


@pytest.fixture
def fake_api(monkeypatch, super_dir):
    """Key present, HTTP mocked, quota table empty."""
    monkeypatch.setattr(get_settings(), "flashalpha_api_key", "test-key")
    calls: list[str] = []

    def fake_fetch(ticker, key, timeout=30.0):
        calls.append(ticker)
        assert key == "test-key"
        return {**PAYLOAD, "symbol": ticker.upper()}

    monkeypatch.setattr(gex_svc, "fetch_summary", fake_fetch)
    return calls


def test_extract_matches_legacy_fields():
    out = gex_svc.extract(PAYLOAD)
    assert out["net_gex"] == -9178182877
    assert out["regime"] == "negative_gamma"
    assert out["gamma_flip"] == 745.11          # rounded like gex_daily.py
    assert out["price"] == 740.48
    assert out["call_wall"] == 750 and out["put_wall"] == 740
    assert out["gamma_note"] == "Dealers short gamma"
    assert set(out) == {
        "as_of", "price", "net_gex", "regime", "gamma_flip", "call_wall",
        "put_wall", "gamma_note", "atm_iv", "pc_ratio_volume",
    }


def test_refresh_stores_snapshot_and_meters_quota(client, fake_api, super_dir):
    resp = client.post("/api/v1/super/gex/refresh")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["calls_made"] == 2                # spy + qqq
    assert fake_api == ["spy", "qqq"]
    assert body["errors"] == {}
    assert body["gex"]["stale"] is False
    assert set(body["gex"]["tickers"]) == {"SPY", "QQQ"}
    assert body["gex"]["macro"]["fear_greed"] == 41
    assert body["quota"]["used_by_api"] == 2
    assert body["quota"]["remaining"] == get_settings().flashalpha_daily_cap - 2

    # served snapshot is the new one
    served = client.get("/api/v1/super/gex").json()
    assert served["tickers"]["SPY"]["net_gex"] == -9178182877

    # legacy file mirrored for the old stack
    on_disk = json.loads((super_dir / "gex_daily.json").read_text())
    assert on_disk["tickers"]["QQQ"]["regime"] == "negative_gamma"
    # raw payload archived per ticker
    assert (super_dir / "gex" / "2026-07-28_spy.json").is_file()


def test_quota_cap_blocks_further_calls(client, fake_api, monkeypatch):
    monkeypatch.setattr(get_settings(), "flashalpha_daily_cap", 3)
    assert client.post("/api/v1/super/gex/refresh").status_code == 200   # 2 used
    resp = client.post("/api/v1/super/gex/refresh")                      # needs 2, 1 left
    assert resp.status_code == 429
    assert "daily API calls remain" in resp.json()["detail"]
    assert len(fake_api) == 2, "no extra request may reach flashAlpha"

    # a single ticker still fits in the last slot
    resp = client.post("/api/v1/super/gex/refresh", params={"tickers": "spy"})
    assert resp.status_code == 200
    assert client.get("/api/v1/super/gex/quota").json()["remaining"] == 0


def test_failed_ticker_keeps_previous_data_and_marks_stale(client, fake_api, monkeypatch, super_dir):
    client.post("/api/v1/super/gex/refresh", params={"tickers": "spy"})   # good SPY

    def boom(ticker, key, timeout=30.0):
        raise gex_svc.GexError("HTTP 429 from flashAlpha")

    monkeypatch.setattr(gex_svc, "fetch_summary", boom)
    body = client.post("/api/v1/super/gex/refresh", params={"tickers": "qqq"}).json()
    assert body["gex"]["stale"] is True
    assert "qqq" in body["errors"]
    # SPY data survived the failed pass
    assert body["gex"]["tickers"]["SPY"]["net_gex"] == -9178182877
    # the failed request still counted against the budget
    assert body["quota"]["used_by_api"] == 2


def test_missing_key_is_a_clear_error(client, monkeypatch, super_dir):
    monkeypatch.setattr(get_settings(), "flashalpha_api_key", "")
    monkeypatch.setattr(gex_svc, "fetch_summary", lambda *a, **k: PAYLOAD)
    resp = client.post("/api/v1/super/gex/refresh")
    assert resp.status_code == 502
    assert "flashAlpha API key" in resp.json()["detail"]


def test_custom_lookup_does_not_touch_the_desk_snapshot(client, fake_api, super_dir):
    """persist=false: metered + archived, but SPY/QQQ view is untouched."""
    client.post("/api/v1/super/gex/refresh")          # seed the desk (spy+qqq)
    desk_before = client.get("/api/v1/super/gex").json()
    quota_before = client.get("/api/v1/super/gex/quota").json()["used_by_api"]

    body = client.post(
        "/api/v1/super/gex/refresh",
        params={"tickers": "nvda", "persist": "false"},
    ).json()

    # only the asked-for ticker comes back
    assert list(body["gex"]["tickers"]) == ["NVDA"]
    assert body["calls_made"] == 1
    # the budget was still charged
    assert body["quota"]["used_by_api"] == quota_before + 1
    # the desk snapshot is unchanged — no NVDA in the banner
    desk_after = client.get("/api/v1/super/gex").json()
    assert set(desk_after["tickers"]) == set(desk_before["tickers"]) == {"SPY", "QQQ"}
    assert desk_after["fetched_at"] == desk_before["fetched_at"]
    # ...but the raw payload was archived for history
    snaps = client.get("/api/v1/super/snapshots", params={"kind": "gex_raw_nvda"}).json()
    assert len(snaps) == 1


def test_custom_lookup_is_refused_when_budget_is_spent(client, fake_api, monkeypatch):
    monkeypatch.setattr(get_settings(), "flashalpha_daily_cap", 1)
    assert client.post(
        "/api/v1/super/gex/refresh", params={"tickers": "spy", "persist": "false"}
    ).status_code == 200
    resp = client.post(
        "/api/v1/super/gex/refresh", params={"tickers": "nvda", "persist": "false"}
    )
    assert resp.status_code == 429
    assert len(fake_api) == 1, "no request may reach flashAlpha past the cap"


def test_reload_is_free_and_never_fetches(client, fake_api, super_dir):
    client.post("/api/v1/super/sync")
    before = client.get("/api/v1/super/gex/quota").json()["used_by_api"]
    assert client.post("/api/v1/super/gex/reload").status_code == 200
    assert client.get("/api/v1/super/gex/quota").json()["used_by_api"] == before
    assert fake_api == []
