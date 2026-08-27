"""The signal books sort newest-first by real instant, not by wall-clock text.

Reported from the A-book: an 11:45 IST BANKNIFTY bar sat between a 12:00 CST
and a 10:45 CST SPY bar, because the rows were sorted as STRINGS and
"11:45" > "10:45". In real time 11:45 IST is 01:15 CDT — older than both.

Display is unchanged: each row still shows its own engine's clock and label.
Only the ordering is normalised.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services import super_research as svc

IST = ZoneInfo("Asia/Kolkata")
CST = ZoneInfo("America/Chicago")


def _row(category, ticker, logged, bar):
    return {"category": category, "ticker": ticker,
            "logged_at_cst": logged, "bar_time_cst": bar}


def test_the_reported_ordering():
    """The exact rows from the screenshot, in the order they were shown."""
    shown = [
        _row("etf", "SPY", "2026-07-30 12:00:05", "2026-07-30 12:00"),
        _row("india", "BANKNIFTY", "2026-07-30 11:50:44", "2026-07-30 11:45"),
        _row("etf", "SPY", "2026-07-30 10:45:12", "2026-07-30 10:45"),
        _row("etf", "IWM", "2026-07-30 09:00:52", "2026-07-30 09:00"),
    ]
    shown.sort(key=svc.signal_sort_key, reverse=True)
    assert [r["ticker"] for r in shown] == ["SPY", "SPY", "IWM", "BANKNIFTY"], (
        "the IST row must fall to the bottom — 11:45 IST is 01:15 CDT"
    )


def test_ist_and_cst_are_compared_as_instants():
    ist_row = _row("india", "BANKNIFTY", "2026-07-30 11:45:00", "2026-07-30 11:45")
    cst_row = _row("etf", "SPY", "2026-07-30 09:00:00", "2026-07-30 09:00")
    assert svc.signal_sort_key(cst_row) > svc.signal_sort_key(ist_row)


def test_same_zone_rows_still_order_by_time():
    early = _row("etf", "SPY", "2026-07-30 09:00:00", "2026-07-30 09:00")
    late = _row("etf", "SPY", "2026-07-30 14:00:00", "2026-07-30 14:00")
    assert svc.signal_sort_key(late) > svc.signal_sort_key(early)


def test_key_matches_the_utc_instant():
    row = _row("india", "BANKNIFTY", "2026-07-30 11:45:00", "2026-07-30 11:45")
    want = (datetime(2026, 7, 30, 11, 45, tzinfo=IST)
            .astimezone(timezone.utc).replace(tzinfo=None))
    assert svc.signal_sort_key(row)[0] == want


def test_bar_time_is_the_tiebreak_when_logged_at_matches():
    same = "2026-07-30 12:00:00"
    older_bar = _row("etf", "SPY", same, "2026-07-30 11:00")
    newer_bar = _row("etf", "SPY", same, "2026-07-30 11:55")
    assert svc.signal_sort_key(newer_bar) > svc.signal_sort_key(older_bar)


def test_rows_missing_logged_at_fall_back_to_bar_time():
    row = _row("etf", "SPY", "", "2026-07-30 09:00")
    assert svc.signal_sort_key(row)[0] is not None
    assert svc.signal_sort_key(row)[0] == svc._parse_cst("2026-07-30 09:00", "etf")


def test_unparseable_rows_sink_instead_of_crashing():
    junk = _row("etf", "SPY", "not a time", "also not a time")
    good = _row("etf", "SPY", "2026-07-30 09:00:00", "2026-07-30 09:00")
    rows = [junk, good]
    rows.sort(key=svc.signal_sort_key, reverse=True)
    assert rows[0] is good, "a row with no usable timestamp must not sort to the top"


def test_a_missing_category_is_treated_as_central_time():
    """Unlabelled rows keep the historical assumption rather than shifting."""
    row = {"logged_at_cst": "2026-07-30 09:00:00", "bar_time_cst": "2026-07-30 09:00"}
    assert svc.signal_sort_key(row)[0] == svc._parse_cst("2026-07-30 09:00", "etf")


def test_ordering_is_stable_across_a_full_mixed_book():
    rows = [
        _row("india", "NIFTY", "2026-07-30 09:20:00", "2026-07-30 09:15"),    # 22:50 CDT prev day
        _row("etf", "SPY", "2026-07-30 08:35:00", "2026-07-30 08:30"),
        _row("india", "BANKNIFTY", "2026-07-30 15:25:00", "2026-07-30 15:20"),  # 04:55 CDT
        _row("stock", "TSLA", "2026-07-30 13:40:00", "2026-07-30 13:35"),
    ]
    rows.sort(key=svc.signal_sort_key, reverse=True)
    order = [r["ticker"] for r in rows]
    # CST afternoon > CST morning > IST close (04:55 CDT) > IST open (22:50 prev)
    assert order == ["TSLA", "SPY", "BANKNIFTY", "NIFTY"], order


def test_display_fields_are_never_rewritten():
    """Sorting must not touch the row — the UI shows the engine's own clock."""
    row = _row("india", "BANKNIFTY", "2026-07-30 11:50:44", "2026-07-30 11:45")
    before = dict(row)
    svc.signal_sort_key(row)
    assert row == before
