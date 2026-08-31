from __future__ import annotations

import pytest

from app.services import quotes


def test_pivot_math():
    # H=110 L=90 C=100 -> P=100, R1=110, S1=90, R2=120, S2=80, R3=130, S3=70
    p = quotes._pivots(110, 90, 100)
    assert p == {"P": 100.0, "R1": 110.0, "R2": 120.0, "R3": 130.0, "S1": 90.0, "S2": 80.0, "S3": 70.0}


def test_symbol_mapping():
    assert quotes.SYMBOL_MAP["BTC"] == ("BTC-USD", "BTCUSD")
    assert quotes.SYMBOL_MAP["NIFTY"][0] == "^NSEI"


def test_quote_endpoint_serves_and_caches(client, monkeypatch):
    calls = []

    def fake_fetch(ticker):
        calls.append(ticker)
        return {
            "ticker": ticker,
            "yf_symbol": ticker,
            "tv_symbol": ticker,
            "tv_url": quotes.TV_CHART_BASE + ticker,
            "price": 500.25,
            "prev_close": 495.0,
            "change": 5.25,
            "change_pct": 1.06,
            "currency": "USD",
            "prior_session": {"date": "2026-07-27", "open": 490.0, "high": 505.0, "low": 488.0, "close": 495.0},
            "pivots": quotes._pivots(505.0, 488.0, 495.0),
            "fetched_at": "2026-07-28T08:00:00+00:00",
        }

    monkeypatch.setattr(quotes, "_fetch", fake_fetch)
    quotes._CACHE.clear()

    r = client.get("/api/v1/super/quote/QQQ")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["price"] == 500.25
    assert body["tv_url"].endswith("?symbol=QQQ")
    assert body["pivots"]["P"] == pytest.approx((505 + 488 + 495) / 3, abs=0.01)

    client.get("/api/v1/super/quote/QQQ")
    assert calls == ["QQQ"]  # second hit served from cache


def test_quote_endpoint_error_shape(client, monkeypatch):
    def boom(ticker):
        raise quotes.QuoteError("no market data for XX")

    monkeypatch.setattr(quotes, "_fetch", boom)
    quotes._CACHE.clear()
    r = client.get("/api/v1/super/quote/XX")
    assert r.status_code == 502
    assert "no market data" in r.json()["detail"]
