"""India signals carry IST, not Central — despite the column names.

Every engine writes wall-clock into columns named ``*_cst``, but the India
engine's clock is IST: a BANKNIFTY row carries stop_deadline_cst=15:30, which
is the NSE close, and its bar times sit inside 09:15-15:30 IST.

Parsing those as Central pushed each India signal ~10.5h into the future, so
the "past 24h, latest first" A-book showed an 01:15-CDT Indian bar ABOVE a
genuinely newer 09:00-CDT US one.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services import super_research as svc

IST = ZoneInfo("Asia/Kolkata")
CST = ZoneInfo("America/Chicago")


def test_india_maps_to_ist_everything_else_to_central():
    assert svc.signal_tz("india") is svc._IST
    for other in ("etf", "stock", "crypto", "", None, "INDIA_X"):
        assert svc.signal_tz(other) is svc._CST


def test_signal_tz_is_case_insensitive():
    assert svc.signal_tz("India") is svc._IST
    assert svc.signal_tz("  INDIA  ") is svc._IST


def test_india_wall_clock_parses_as_ist():
    got = svc._parse_cst("2026-07-30 11:45", "india")
    want = datetime(2026, 7, 30, 11, 45, tzinfo=IST).astimezone(timezone.utc).replace(tzinfo=None)
    assert got == want
    assert got == datetime(2026, 7, 30, 6, 15)      # 11:45 IST = 06:15 UTC


def test_us_wall_clock_still_parses_as_central():
    got = svc._parse_cst("2026-07-30 09:00", "etf")
    want = datetime(2026, 7, 30, 9, 0, tzinfo=CST).astimezone(timezone.utc).replace(tzinfo=None)
    assert got == want


def test_omitting_the_category_keeps_the_historical_behaviour():
    assert svc._parse_cst("2026-07-30 09:00") == svc._parse_cst("2026-07-30 09:00", "etf")


def test_the_reported_ordering_bug_is_gone():
    """The exact rows from the report: a BANKNIFTY 11:45 IST bar must sort
    BELOW an IWM 09:00 CDT bar, because it happened ~8h earlier."""
    banknifty = svc._parse_cst("2026-07-30 11:50:44", "india")
    iwm = svc._parse_cst("2026-07-30 09:15:52", "etf")
    assert banknifty < iwm, "India signal still sorts as newer than a later US signal"


def test_an_india_signal_is_the_middle_of_the_night_in_central():
    """Sanity-check the user's intuition: NSE hours are overnight in CST."""
    for hhmm in ("09:15", "11:45", "15:30"):
        utc = svc._parse_cst(f"2026-07-30 {hhmm}", "india")
        cst_hour = utc.replace(tzinfo=timezone.utc).astimezone(CST).hour
        assert cst_hour < 6 or cst_hour >= 22, f"{hhmm} IST -> {cst_hour}h CST"


def test_bad_input_still_returns_none():
    assert svc._parse_cst("not a timestamp", "india") is None
    assert svc._parse_cst("", "etf") is None


# ---- the backfill ---------------------------------------------------------

def test_migration_corrects_existing_india_rows(db_session):
    from sqlalchemy import text

    from app.core.database import _fix_india_signal_times
    from app.models.super_research import SuperSignal

    wrong = datetime(2026, 7, 30, 17, 0, 34)          # 11:50 parsed as Central
    right = datetime(2026, 7, 30, 6, 20, 34)          # 11:50 IST -> UTC
    db_session.add(
        SuperSignal(
            external_id="t1", book="A", category="india", ticker="BANKNIFTY",
            bar_time="2026-07-30 11:45", logged_at=wrong,
            raw={"logged_at_cst": "2026-07-30 11:50:34"},
        )
    )
    # a US row must be left alone
    us_at = datetime(2026, 7, 30, 14, 15, 52)
    db_session.add(
        SuperSignal(
            external_id="t2", book="A", category="etf", ticker="IWM",
            bar_time="2026-07-30 09:00", logged_at=us_at,
            raw={"logged_at_cst": "2026-07-30 09:15:52"},
        )
    )
    db_session.commit()

    with db_session.get_bind().begin() as conn:
        n = _fix_india_signal_times(conn)
    assert n == 1

    db_session.expire_all()
    india = db_session.scalar(select_one(SuperSignal, "t1"))
    etf = db_session.scalar(select_one(SuperSignal, "t2"))
    assert india.logged_at.replace(microsecond=0) == right
    assert etf.logged_at == us_at, "a non-India row was rewritten"

    # idempotent: a second pass changes nothing
    with db_session.get_bind().begin() as conn:
        assert _fix_india_signal_times(conn) == 0
    _ = text  # keep the import meaningful for readers


def select_one(model, external_id):
    from sqlalchemy import select

    return select(model).where(model.external_id == external_id)


def test_migration_skips_rows_without_a_usable_raw(db_session):
    from app.core.database import _fix_india_signal_times
    from app.models.super_research import SuperSignal

    keep = datetime(2026, 7, 30, 17, 0, 0)
    db_session.add(
        SuperSignal(external_id="t3", book="A", category="india", ticker="NIFTY",
                    logged_at=keep, raw={})
    )
    db_session.commit()
    with db_session.get_bind().begin() as conn:
        assert _fix_india_signal_times(conn) == 0
    db_session.expire_all()
    row = db_session.scalar(select_one(SuperSignal, "t3"))
    assert row.logged_at == keep
