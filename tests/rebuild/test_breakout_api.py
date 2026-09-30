"""BreakoutRadar through the API: /breakout/scan, /breakout/chart, the alert relay.

What this holds, with Yahoo, the index lists and Telegram/Discord all fakes:

* nothing is fetched until a scan is asked for, and then in the background:
  the answer says `refreshing` with progress, and the rows land on a later read;
* rows are exactly the tickers passing all eight rules; a ticker one rule short
  is a near miss that names the rule; the failure counts say which rule emptied
  the table;
* moving a threshold re-judges the cached scan and downloads nothing;
* India asks Yahoo for .NS listings and judges market cap in rupees;
* 4-hour candles are folded from hourly ones on the 09:30 open;
* the alert relay sends only to Telegram's host or a Discord webhook, never
  echoes a token -- not in an answer, not in a log -- and is rate limited.
"""

from __future__ import annotations

import logging
import time

import numpy as np
import pandas as pd
import pytest

from app.domains.trading.market import breakout_scan, fundamentals, universes, yahoo
from app.platform import notify
from tests.rebuild.synthetic import breakout_scenario

V1 = "/api/v1/breakout"
TOKEN = "123456789:" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
WEBHOOK = "https://discord.com/api/webhooks/123456789012/" + "w" * 40


def yahoo_like(frame: pd.DataFrame, zone: str) -> pd.DataFrame:
    out = frame.rename(columns=str.capitalize)
    out.index = pd.DatetimeIndex(out.index).tz_localize(zone)
    return out


def hourly(sessions: int = 150, zone_open=(9, 30), per_day: int = 7) -> pd.DataFrame:
    days = pd.bdate_range("2026-03-02", periods=sessions)
    idx, closes = [], []
    price = 50.0
    for day in days:
        for k in range(per_day):
            idx.append(day + pd.Timedelta(hours=zone_open[0] + k, minutes=zone_open[1]))
            price *= 1.0004
            closes.append(price)
    c = np.asarray(closes)
    return pd.DataFrame({"open": c * 0.999, "high": c * 1.002, "low": c * 0.997,
                         "close": c, "volume": np.full(len(c), 400_000.0)},
                        index=pd.DatetimeIndex(idx))


@pytest.fixture()
def market_data(monkeypatch):
    """Yahoo answering from a table of frames, and small universes."""
    frames = {
        ("BRKO", "1d"): yahoo_like(breakout_scenario(), "America/New_York"),
        ("NEAR", "1d"): yahoo_like(breakout_scenario(vol_x=1.2), "America/New_York"),
        ("DULL", "1d"): yahoo_like(breakout_scenario(breakout=(101.0, 101.5), vol_x=1.0),
                                   "America/New_York"),
        ("RELIANCE.NS", "1d"): yahoo_like(breakout_scenario(), "Asia/Kolkata"),
        ("TCS.NS", "1d"): yahoo_like(breakout_scenario(vol_x=1.1), "Asia/Kolkata"),
        ("HOURS", "1d"): yahoo_like(breakout_scenario(), "America/New_York"),
        ("HOURS", "60m"): yahoo_like(hourly(), "America/New_York"),
    }
    calls: list[tuple] = []

    def download(tickers, interval, period):
        calls.append((tuple(tickers), interval, period))
        parts = {t: frames[(t, interval)] for t in tickers if (t, interval) in frames}
        return pd.concat(parts, axis=1) if parts else pd.DataFrame()

    lists = {"US": ["BRKO", "NEAR", "DULL", "GONE"], "INDIA": ["RELIANCE", "TCS"]}
    monkeypatch.setattr(yahoo, "_download", download)
    monkeypatch.setattr(universes, "for_market", lambda market: {
        "name": "test list", "symbols": lists[market], "count": len(lists[market]),
        "lists": {"test": {"source": "snapshot", "as_of": "2025-09",
                           "count": len(lists[market])}}})
    monkeypatch.setattr(fundamentals, "_fetch_one", lambda sym: {
        "name": f"{sym} Ltd", "industry": "Testing", "market_cap": 8e9,
        "implied_shares": 8e7})
    return calls


def settled(client, headers, params, timeout_s: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while True:
        r = client.get(f"{V1}/scan", params=params, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        if not body["refreshing"] or time.monotonic() > deadline:
            return body
        time.sleep(0.05)


def run_scan(client, headers, **params) -> dict:
    params = {"market": "US", "timeframe": "1d", **params}
    first = client.get(f"{V1}/scan", params={**params, "refresh": "true"}, headers=headers)
    assert first.status_code == 200, first.text
    return settled(client, headers, params)


# ---- the scan ----------------------------------------------------------------

def test_nothing_is_fetched_until_a_scan_is_asked_for(client, alice, market_data):
    body = client.get(f"{V1}/scan", headers=alice.headers).json()
    assert body["rows"] == [] and body["refreshing"] is False and body["at"] is None
    assert "run one" in body["note"]
    assert market_data == []


def test_a_scan_runs_behind_the_answer_and_lands(client, alice, market_data):
    first = client.get(f"{V1}/scan", params={"refresh": "true"}, headers=alice.headers).json()
    assert first["refreshing"] is True and first["progress"] is not None
    body = settled(client, alice.headers, {})
    assert body["refreshing"] is False and body["at"] is not None
    assert [r["ticker"] for r in body["rows"]] == ["BRKO"]
    row = body["rows"][0]
    assert all(row["rules"].values())
    assert row["market_cap"] == pytest.approx(8e7 * row["price"])
    for column in ("price", "change_pct", "breakout_size_pct", "rvol", "range_pct", "market_cap"):
        assert row[column] is not None
    assert body["scanned"] == 3 and body["unavailable"] == 1           # GONE had no data
    assert body["universe"]["name"] == "test list"


def test_a_near_miss_names_the_rule_it_missed(client, alice, market_data):
    body = run_scan(client, alice.headers)
    near = {r["ticker"]: r["failed"] for r in body["near_misses"]}
    assert near["NEAR"] == ["rvol"]
    assert body["failures"]["rvol"] >= 1
    assert set(body["failures"]) == {"consolidation", "penetration", "body", "market_cap",
                                     "rvol", "liquidity", "near_high", "trend"}


def test_moving_a_threshold_rejudges_without_downloading(client, alice, market_data):
    run_scan(client, alice.headers)
    downloads = len(market_data)
    strict = client.get(f"{V1}/scan", params={"min_rvol": 5}, headers=alice.headers).json()
    assert strict["rows"] == []
    assert {r["ticker"]: r["failed"] for r in strict["near_misses"]}["BRKO"] == ["rvol"]
    loose = client.get(f"{V1}/scan", params={"min_rvol": 1.1}, headers=alice.headers).json()
    assert {r["ticker"] for r in loose["rows"]} == {"BRKO", "NEAR"}
    assert loose["params"]["min_rvol"] == 1.1
    assert len(market_data) == downloads


def test_the_market_cap_floor_is_applied_once_the_cap_is_known(client, alice, market_data,
                                                              monkeypatch):
    monkeypatch.setattr(fundamentals, "_fetch_one", lambda sym: {"market_cap": 3e7,
                                                                  "implied_shares": None})
    body = run_scan(client, alice.headers)
    assert body["rows"] == []
    assert {r["ticker"]: r["failed"] for r in body["near_misses"]}["BRKO"] == ["market_cap"]


def test_india_scans_nse_listings_and_judges_the_cap_in_rupees(client, alice, market_data):
    body = run_scan(client, alice.headers, market="INDIA")
    asked = {t for tickers, _, _ in market_data for t in tickers}
    assert asked == {"RELIANCE.NS", "TCS.NS"}
    assert [r["ticker"] for r in body["rows"]] == ["RELIANCE"]
    assert body["params"]["min_market_cap"] == 3e7 and body["params"]["currency"] == "INR"


def test_the_body_floor_follows_the_timeframe(client, alice, market_data):
    daily = client.get(f"{V1}/scan", params={"timeframe": "1d"}, headers=alice.headers).json()
    fast = client.get(f"{V1}/scan", params={"timeframe": "15m"}, headers=alice.headers).json()
    assert daily["params"]["min_body_pct"] == 5.0 and fast["params"]["min_body_pct"] == 2.5


@pytest.mark.parametrize("params", [{"market": "EU"}, {"timeframe": "2h"},
                                    {"min_rvol": -1}, {"consolidation_bars": 2},
                                    {"max_range_pct": 0}])
def test_nonsense_is_refused_before_anything_runs(client, alice, market_data, params):
    r = client.get(f"{V1}/scan", params={**params, "refresh": "true"}, headers=alice.headers)
    assert r.status_code == 422
    assert market_data == []


# ---- the chart ---------------------------------------------------------------

def test_the_chart_carries_candles_emas_and_the_breakout(client, alice, market_data):
    run_scan(client, alice.headers)
    r = client.get(f"{V1}/chart/BRKO", params={"market": "US", "timeframe": "1d"},
                   headers=alice.headers)
    assert r.status_code == 200, r.text
    chart = r.json()
    assert len(chart["candles"]) == len(chart["ema20"]) == len(chart["ema50"])
    assert chart["breakout_candle_timestamp"] == chart["candles"][-1]["t"]
    assert chart["consolidation_high"] == pytest.approx(104.0)
    assert chart["consolidation_low"] == pytest.approx(99.0)
    assert chart["verdict"]["passed"] is True and chart["industry"] == "Testing"


def test_a_ticker_outside_the_scan_is_fetched_on_its_own(client, alice, market_data):
    r = client.get(f"{V1}/chart/RELIANCE.NS", params={"market": "INDIA", "timeframe": "1d"},
                   headers=alice.headers)
    assert r.status_code == 200, r.text
    assert r.json()["ticker"] == "RELIANCE"
    assert market_data == [(("RELIANCE.NS",), "1d", "1y")]


def test_four_hour_candles_are_folded_from_hourly_on_the_open(client, alice, market_data):
    r = client.get(f"{V1}/chart/HOURS", params={"market": "US", "timeframe": "4h"},
                   headers=alice.headers)
    assert r.status_code == 200, r.text
    assert (("HOURS",), "60m", "180d") in market_data
    times = {c["t"][11:] for c in r.json()["candles"]}
    assert times == {"09:30", "13:30"}


def test_an_unknown_ticker_is_not_found(client, alice, market_data):
    r = client.get(f"{V1}/chart/ZZZZ", headers=alice.headers)
    assert r.status_code == 404


def test_a_yahoo_outage_on_a_chart_is_an_outage_not_a_missing_ticker(client, alice,
                                                                     monkeypatch):
    def down(tickers, interval, period):
        raise ConnectionError("Yahoo is down")

    monkeypatch.setattr(yahoo, "_download", down)
    r = client.get(f"{V1}/chart/AAPL", headers=alice.headers)
    assert r.status_code == 502 and "Yahoo" in r.json()["detail"]


def test_market_caps_wait_for_at_most_a_bounded_few(client, alice, market_data, monkeypatch):
    """A drawer slid to nothing makes every name a contender. Only the first
    SYNC_CAPS caps are looked up before answering; the rest are warmed behind
    it and show as unverified meanwhile."""
    many = [f"T{i:03d}" for i in range(40)]
    frame = yahoo_like(breakout_scenario(), "America/New_York")

    def download(tickers, interval, period):
        return pd.concat({t: frame for t in tickers}, axis=1)

    looked: list[str] = []
    warmed: list[str] = []

    def lookup(symbols, workers=6):
        looked.extend(symbols)
        return {s: {"market_cap": 9e9, "implied_shares": None} for s in symbols}

    monkeypatch.setattr(yahoo, "_download", download)
    monkeypatch.setattr(universes, "for_market", lambda market: {
        "name": "many", "symbols": many, "count": len(many), "lists": {}})
    monkeypatch.setattr(breakout_scan.fundamentals, "lookup", lookup)
    monkeypatch.setattr(breakout_scan.fundamentals, "warm", lambda symbols: warmed.extend(symbols))
    run_scan(client, alice.headers)            # the sweep itself warms the 40 it passes
    looked.clear()                             # ...and the polls while it ran judged too
    warmed.clear()
    fundamentals.reset()
    body = client.get(f"{V1}/scan", params={"min_rvol": 0.5}, headers=alice.headers).json()
    assert len(looked) == breakout_scan.SYNC_CAPS
    assert len(warmed) == 40 - breakout_scan.SYNC_CAPS
    assert len(body["rows"]) == 40
    unverified = [r for r in body["rows"] if r["rules"]["market_cap"] is None]
    assert len(unverified) == 40 - breakout_scan.SYNC_CAPS


# ---- the alert relay -----------------------------------------------------------

class _Answer:
    def __init__(self, status: int):
        self.status_code = status


@pytest.fixture()
def posted(monkeypatch):
    sent: list[tuple[str, dict]] = []
    status = {"code": 200}

    def post(url, body):
        sent.append((url, body))
        return _Answer(status["code"])

    monkeypatch.setattr(notify, "_post", post)
    return sent, status


def alert(client, headers, **body):
    return client.post(f"{V1}/alerts/send", json=body, headers=headers)


def test_a_telegram_alert_goes_to_telegram_and_the_answer_holds_no_token(client, alice, posted):
    sent, _ = posted
    r = alert(client, alice.headers, channel="telegram", token=TOKEN,
              chat_id="-1001234567890", text="BRKO broke out")
    assert r.status_code == 200 and r.json() == {"sent": True, "channel": "telegram"}
    url, body = sent[0]
    assert url == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    assert body["chat_id"] == "-1001234567890" and body["text"] == "BRKO broke out"
    assert TOKEN not in r.text


def test_a_discord_alert_goes_only_to_a_discord_webhook(client, alice, posted):
    sent, _ = posted
    ok = alert(client, alice.headers, channel="discord", webhook_url=WEBHOOK, text="hi")
    assert ok.status_code == 200 and sent == [(WEBHOOK, {"content": "hi"})]
    for elsewhere in ("https://169.254.169.254/api/webhooks/1/abc",
                      "http://discord.com/api/webhooks/123456/" + "w" * 30,
                      "https://discord.com.evil.io/api/webhooks/123456/" + "w" * 30,
                      "https://discord.com/api/users/@me"):
        r = alert(client, alice.headers, channel="discord", webhook_url=elsewhere, text="hi")
        assert r.status_code == 422, elsewhere
    assert len(sent) == 1


@pytest.mark.parametrize("body", [{}, {"channel": "sms", "text": "x"},
                                  {"channel": "telegram", "token": "nope", "chat_id": "1",
                                   "text": "x"},
                                  {"channel": "telegram", "token": TOKEN, "chat_id": "; drop",
                                   "text": "x"},
                                  {"channel": "telegram", "token": TOKEN, "chat_id": "1",
                                   "text": "   "}])
def test_a_malformed_alert_is_refused_without_calling_out(client, alice, posted, body):
    sent, _ = posted
    r = alert(client, alice.headers, **body)
    assert r.status_code == 422 and sent == []
    assert TOKEN not in r.text


def test_a_refused_alert_says_why_without_the_token(client, alice, posted, caplog):
    _, status = posted
    status["code"] = 401
    with caplog.at_level(logging.DEBUG):
        r = alert(client, alice.headers, channel="telegram", token=TOKEN, chat_id="42",
                  text="x")
    assert r.status_code == 502 and "check the bot token" in r.json()["detail"]
    assert TOKEN not in r.text and TOKEN not in caplog.text


def test_an_unreachable_channel_never_repeats_the_url(client, alice, monkeypatch, caplog):
    def boom(url, body):
        raise ConnectionError(f"Max retries exceeded with url: {url}")

    monkeypatch.setattr(notify, "_post", boom)
    with caplog.at_level(logging.DEBUG):
        r = alert(client, alice.headers, channel="telegram", token=TOKEN, chat_id="42",
                  text="x")
    assert r.status_code == 502 and r.json()["detail"] == "telegram could not be reached"
    assert TOKEN not in r.text and TOKEN not in caplog.text


def test_alerts_are_rate_limited_per_operator(client, alice, bob, posted):
    for _ in range(20):
        assert alert(client, alice.headers, channel="discord", webhook_url=WEBHOOK,
                     text="x").status_code == 200
    assert alert(client, alice.headers, channel="discord", webhook_url=WEBHOOK,
                 text="x").status_code == 429
    assert alert(client, bob.headers, channel="discord", webhook_url=WEBHOOK,
                 text="x").status_code == 200


@pytest.mark.parametrize("method,path", [("GET", f"{V1}/scan"), ("GET", f"{V1}/chart/SPY"),
                                         ("POST", f"{V1}/alerts/send")])
def test_every_route_needs_a_session(client, method, path):
    r = client.request(method, path)
    assert r.status_code == 401 and r.json().get("login_required") is True
