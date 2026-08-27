"""Upcoming-earnings sweep: grouping, session derivation, caching, windowing.

Every test monkeypatches the yfinance layer — the suite must never make ~100
network calls, and must not depend on whichever companies happen to report
this week.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import earnings as svc


def _evt(ticker: str, when: datetime, session: str) -> dict:
    return {
        "ticker": ticker,
        "when_utc": when.astimezone(timezone.utc).isoformat(),
        "when_ct": when.astimezone(svc.CT).strftime("%Y-%m-%d %H:%M"),
        "date": when.astimezone(svc.ET).strftime("%Y-%m-%d"),
        "session": session,
        "eps_estimate": 1.23,
    }


@pytest.fixture
def fake_sweep(monkeypatch):
    """Two prints today post-close, one tomorrow pre-open."""
    now = datetime.now(svc.ET)
    today_post = now.replace(hour=16, minute=0, second=0, microsecond=0)
    if today_post < now:
        today_post += timedelta(days=1)
    tomo_pre = today_post + timedelta(days=1)
    tomo_pre = tomo_pre.replace(hour=7, minute=0)

    calls: list[int] = []

    def fake_fetch(hours=48, universe=svc.EARNINGS_UNIVERSE):
        calls.append(hours)
        events = [
            _evt("MSFT", today_post, "post"),
            _evt("AAPL", today_post, "post"),
            _evt("NVDA", tomo_pre, "pre"),
        ]
        days: dict = {}
        for e in events:
            days.setdefault(e["date"], {}).setdefault(e["session"], []).append(e["ticker"])
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_hours": hours,
            "universe_size": 100,
            "count": len(events),
            "events": events,
            "days": [{"date": d, "sessions": days[d]} for d in sorted(days)],
            "note": svc.summarize(days),
        }

    monkeypatch.setattr(svc, "fetch_upcoming", fake_fetch)
    return calls


# ---- session derivation ---------------------------------------------------

@pytest.mark.parametrize(
    "hour,minute,expected",
    [(6, 0, "pre"), (8, 30, "pre"), (9, 29, "pre"), (9, 30, "during"),
     (12, 0, "during"), (15, 59, "during"), (16, 0, "post"), (20, 0, "post")],
)
def test_session_boundaries(hour, minute, expected):
    ts = datetime(2026, 7, 29, hour, minute, tzinfo=svc.ET)
    assert svc._session_of(ts) == expected


def test_session_uses_eastern_not_local():
    # 16:00 ET is 'post' even when expressed as a UTC instant
    ts = datetime(2026, 7, 29, 20, 0, tzinfo=timezone.utc)  # = 16:00 EDT
    assert svc._session_of(ts) == "post"


# ---- desk summary ---------------------------------------------------------

def test_summary_reads_like_the_desk_line():
    days = {"2026-07-29": {"post": ["MSFT", "AAPL"]}, "2026-07-30": {"pre": ["NVDA"]}}
    assert svc.summarize(days) == "07/29 Post: MSFT, AAPL · 07/30 Pre: NVDA"


def test_summary_truncates_long_lists():
    days = {"2026-07-29": {"post": [f"T{i}" for i in range(10)]}}
    note = svc.summarize(days, max_per_session=3)
    assert note == "07/29 Post: T0, T1, T2 +7"


def test_summary_orders_pre_before_post_within_a_day():
    days = {"2026-07-29": {"post": ["B"], "pre": ["A"]}}
    assert svc.summarize(days).index("Pre") < svc.summarize(days).index("Post")


# ---- caching --------------------------------------------------------------

def test_first_read_sweeps_and_persists(client, db_session, fake_sweep):
    out = svc.get_earnings(db_session, hours=24)
    assert out["cached"] is False
    assert len(fake_sweep) == 1
    assert out["count"] >= 1

    # second read is served from the DB — no second sweep
    again = svc.get_earnings(db_session, hours=24)
    assert again["cached"] is True
    assert len(fake_sweep) == 1


def test_force_refresh_bypasses_the_cache(db_session, fake_sweep):
    svc.get_earnings(db_session, hours=24)
    svc.get_earnings(db_session, hours=24, force=True)
    assert len(fake_sweep) == 2


def test_stale_cache_is_refetched(db_session, fake_sweep, monkeypatch):
    svc.get_earnings(db_session, hours=24)
    # age the stored payload past the staleness window
    monkeypatch.setattr(svc, "_payload_age_h", lambda payload: svc._STALE_HOURS + 1)
    svc.get_earnings(db_session, hours=24)
    assert len(fake_sweep) == 2


def test_a_24h_ask_is_served_from_the_48h_sweep(db_session, fake_sweep):
    """The stored sweep is always >= 48h so narrower asks never re-fetch."""
    svc.get_earnings(db_session, hours=48)
    out = svc.get_earnings(db_session, hours=24)
    assert out["cached"] is True
    assert out["window_hours"] == 24
    assert len(fake_sweep) == 1


def test_window_narrowing_drops_events_beyond_the_horizon(db_session, fake_sweep):
    wide = svc.get_earnings(db_session, hours=48)
    narrow = svc.get_earnings(db_session, hours=2)
    assert narrow["count"] <= wide["count"]
    for e in narrow["events"]:
        when = datetime.fromisoformat(e["when_utc"])
        assert when <= datetime.now(timezone.utc) + timedelta(hours=2)


# ---- endpoint -------------------------------------------------------------

def test_endpoint_returns_grouped_days(client, fake_sweep):
    r = client.get("/api/v1/super/earnings", params={"hours": 48})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["universe_size"] == 100
    assert body["days"], "expected at least one grouped day"
    first = body["days"][0]
    assert set(first) == {"date", "sessions"}
    assert "Post:" in body["note"] or "Pre:" in body["note"]


def test_endpoint_rejects_an_absurd_window(client, fake_sweep):
    assert client.get("/api/v1/super/earnings", params={"hours": 0}).status_code == 422
    assert client.get("/api/v1/super/earnings", params={"hours": 999}).status_code == 422


def test_endpoint_reports_upstream_failure_as_502(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("yfinance is down")

    monkeypatch.setattr(svc, "get_earnings", boom)
    r = client.get("/api/v1/super/earnings")
    assert r.status_code == 502
    assert "yfinance is down" in r.json()["detail"]


def test_a_broken_ticker_does_not_sink_the_sweep(monkeypatch):
    """One bad symbol must not lose the other 99."""
    class Boom:
        def get_earnings_dates(self, limit=8):
            raise RuntimeError("delisted")

    import sys
    import types

    fake_yf = types.ModuleType("yfinance")
    fake_yf.Ticker = lambda t: Boom()
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    now = datetime.now(timezone.utc)
    assert svc._one("NOPE", now, now + timedelta(hours=48)) == []
