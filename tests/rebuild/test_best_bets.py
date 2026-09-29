"""Best Bets through the API: /tradier/best-bets, and the fundamentals it adds.

What this holds:

* the venue is asked for what the 4-hour screen needs -- 15-minute bars, the
  regular session only (which is what buys 40 days of them), from 40 days back;
* a sweep answers in the background: the first read says `refreshing` and
  carries no rows, and the rows arrive on a later read with A, then B, then
  the rest -- every symbol scanned, qualifying or not;
* market cap is re-marked at the screen's own price from the share count Yahoo
  implied, and industry rides along; neither can fail the screen;
* a rate-limited venue is waited out, and a refusing one becomes an
  unavailable row whose reason never repeats the venue's own text.
"""

from __future__ import annotations

import time
from datetime import timedelta

import pytest

from app.core.config import get_settings
from app.domains.trading.execution import venue
from app.domains.trading.market import best_bets, ema_screen, fundamentals
from app.services.tradier_client import TradierError
from tests.rebuild import synthetic

PATH = "/api/v1/tradier/best-bets"

SERIES = {
    "DIP": lambda: synthetic.crash_then(0.02),
    "CROSS": lambda: synthetic.cross(2),
    "FLAT": lambda: synthetic.flat(50.0),
}


@pytest.fixture()
def small_universe(monkeypatch):
    monkeypatch.setenv("TBOT_TRADIER_BEST_BETS_UNIVERSE", "DIP,CROSS,FLAT")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def bars_by_symbol(monkeypatch):
    calls: list[dict] = []

    def timesales(symbol, *, cred=None, interval="5min", start=None, sandbox=True,
                  session_filter=None):
        calls.append({"symbol": symbol, "interval": interval, "start": start,
                      "sandbox": sandbox, "session_filter": session_filter})
        return SERIES[symbol]() if symbol in SERIES else []

    monkeypatch.setattr(venue, "timesales", timesales)
    return calls


def _settled(client, headers, params=None, timeout_s: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while True:
        r = client.get(PATH, params=params or {}, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        if not body["refreshing"] or time.monotonic() > deadline:
            return body
        time.sleep(0.05)


def test_the_first_read_starts_a_sweep_and_says_so(client, alice, small_universe,
                                                   bars_by_symbol):
    first = client.get(PATH, headers=alice.headers).json()
    assert first["kind"] == "best_bets"
    assert first["refreshing"] is True and first["rows"] == []
    assert first["meta"]["scanned"] == 3


def test_the_venue_is_asked_for_forty_days_of_regular_session_15_minute_bars(
        client, alice, small_universe, bars_by_symbol):
    _settled(client, alice.headers)
    assert {c["symbol"] for c in bars_by_symbol} == {"DIP", "CROSS", "FLAT"}
    want_start = (ema_screen.now_eastern() - timedelta(days=40)).strftime("%Y-%m-%d 00:00")
    for call in bars_by_symbol:
        assert call["interval"] == "15min"
        assert call["session_filter"] == "open"
        assert call["start"] == want_start
        assert call["sandbox"] is True


def test_every_symbol_comes_back_with_its_setup_a_first(client, alice, small_universe,
                                                        bars_by_symbol):
    body = _settled(client, alice.headers)
    assert [r["symbol"] for r in body["rows"]] == ["DIP", "CROSS", "FLAT"]
    setups = {r["symbol"]: r["setup"] for r in body["rows"]}
    assert setups == {"DIP": "A", "CROSS": "B", "FLAT": None}
    assert body["meta"]["matched"] == {"A": 1, "B": 1}
    assert body["meta"]["timeframe"]["bar"] == "4h"
    assert body["meta"]["timeframe"]["anchor"] == "09:30 ET"
    dip = body["rows"][0]
    assert dip["days_to_catch"] > 0 and dip["distance_pct"] < 0 and dip["gap"] < 0


def test_market_cap_is_re_marked_at_the_screens_price(client, alice, small_universe,
                                                      bars_by_symbol, monkeypatch):
    """Yahoo said $1B at $100: 10M implied shares. The screen's price is the
    DIP's, so the cap shown is 10M x that price -- not the stale $1B."""
    monkeypatch.setattr(fundamentals, "_fetch_one", lambda sym: {
        "name": f"{sym} Inc", "industry": "Software—Infrastructure", "sector": "Technology",
        "market_cap": 1e9, "implied_shares": 1e7})
    body = _settled(client, alice.headers)
    dip = next(r for r in body["rows"] if r["symbol"] == "DIP")
    assert dip["market_cap"] == pytest.approx(1e7 * dip["price"])
    assert dip["industry"] == "Software—Infrastructure"
    assert body["meta"]["fundamentals"] == {"source": "yfinance", "answered": 3}


def test_yahoo_failing_costs_the_columns_not_the_screen(client, alice, small_universe,
                                                       bars_by_symbol, monkeypatch):
    def down(symbol):
        raise RuntimeError("Too Many Requests")

    monkeypatch.setattr(fundamentals, "_fetch_one", down)
    body = _settled(client, alice.headers)
    assert {r["setup"] for r in body["rows"]} == {"A", "B", None}
    assert all(r["market_cap"] is None and r["industry"] is None for r in body["rows"])


def test_a_rate_limited_venue_is_waited_out(client, alice, small_universe, monkeypatch):
    monkeypatch.setattr(best_bets, "BACKOFF_S", 0.0)
    refused = {"DIP": 2}

    def timesales(symbol, **kw):
        if refused.get(symbol):
            refused[symbol] -= 1
            raise TradierError("Tradier HTTP 429: quota exceeded", 429)
        return SERIES[symbol]()

    monkeypatch.setattr(venue, "timesales", timesales)
    body = _settled(client, alice.headers)
    dip = next(r for r in body["rows"] if r["symbol"] == "DIP")
    assert dip["available"] is True and dip["setup"] == "A"


def test_a_refusing_venue_is_a_row_that_says_so_without_the_venues_text(
        client, alice, small_universe, monkeypatch):
    def timesales(symbol, **kw):
        if symbol == "CROSS":
            raise TradierError("Tradier HTTP 401: invalid token fake-token-secret", 401)
        return SERIES[symbol]()

    monkeypatch.setattr(venue, "timesales", timesales)
    r = client.get(PATH, headers=alice.headers)
    body = _settled(client, alice.headers)
    cross = next(row for row in body["rows"] if row["symbol"] == "CROSS")
    assert cross["available"] is False and cross["setup"] is None
    assert cross["reason"] == "the venue refused the request"
    assert "fake-token" not in r.text and "fake-token" not in str(body)
    assert body["rows"][-1]["symbol"] == "CROSS"          # the unreadable sort last


def test_one_unreadable_series_costs_its_row_not_the_sweep(client, alice, small_universe,
                                                          monkeypatch):
    real = ema_screen.screen

    def screen(symbol, bars, rules=None, **kw):
        if symbol == "FLAT":
            raise ValueError("SVD did not converge")
        return real(symbol, bars, rules, **kw)

    monkeypatch.setattr(ema_screen, "screen", screen)
    monkeypatch.setattr(venue, "timesales", lambda symbol, **kw: SERIES[symbol]())
    body = _settled(client, alice.headers)
    flat = next(r for r in body["rows"] if r["symbol"] == "FLAT")
    assert flat["available"] is False and flat["reason"] == "the venue's bars could not be read"
    assert body["meta"]["matched"] == {"A": 1, "B": 1}


def test_refresh_starts_a_new_sweep_on_a_fresh_snapshot(client, alice, small_universe,
                                                        bars_by_symbol):
    _settled(client, alice.headers)
    asked = len(bars_by_symbol)
    again = client.get(PATH, params={"refresh": "true"}, headers=alice.headers).json()
    assert again["refreshing"] is True and again["rows"]    # the old rows still shown
    _settled(client, alice.headers)
    assert len(bars_by_symbol) == 2 * asked


def test_a_fresh_snapshot_is_served_without_asking_the_venue(client, alice, small_universe,
                                                             bars_by_symbol):
    _settled(client, alice.headers)
    asked = len(bars_by_symbol)
    body = client.get(PATH, headers=alice.headers).json()
    assert body["refreshing"] is False and len(bars_by_symbol) == asked
    assert body["age_s"] is not None


def test_an_operator_with_no_live_credential_is_told_so(client, alice, small_universe):
    r = client.get(PATH, params={"live": "true"}, headers=alice.headers)
    assert r.status_code == 424


def test_an_anonymous_caller_is_refused(client):
    r = client.get(PATH)
    assert r.status_code == 401 and r.json().get("login_required") is True


# ---- fundamentals, directly ---------------------------------------------------

def test_fundamentals_are_cached_and_a_miss_is_not_retried_at_once(monkeypatch):
    asked: list[str] = []

    def fetch(sym):
        asked.append(sym)
        return None if sym == "GONE" else {"industry": "Banks", "market_cap": 5e9,
                                           "implied_shares": 5e7}

    monkeypatch.setattr(fundamentals, "_fetch_one", fetch)
    first = fundamentals.lookup(["JPM", "GONE", "jpm"])
    second = fundamentals.lookup(["JPM", "GONE"])
    assert first == second == {"JPM": {"industry": "Banks", "market_cap": 5e9,
                                       "implied_shares": 5e7}, "GONE": {}}
    assert sorted(asked) == ["GONE", "JPM"]


def test_yahoo_symbols_follow_yahoos_spelling():
    assert fundamentals.yahoo_symbol("brk.b") == "BRK-B"
    assert fundamentals.yahoo_symbol("RELIANCE.NS") == "RELIANCE.NS"
    assert fundamentals.yahoo_symbol("SPX") == "^GSPC"


def test_a_cap_without_a_share_count_falls_back_to_the_fetched_cap():
    assert fundamentals.market_cap({"market_cap": 2e9}, 10.0) == 2e9
    assert fundamentals.market_cap({"market_cap": 2e9, "implied_shares": 1e8}, 30.0) == 3e9
    assert fundamentals.market_cap({}, 30.0) is None
