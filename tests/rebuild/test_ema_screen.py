"""The 4-hour EMA screen behind Best Bets.

What this holds:

* 4-hour bars are built on the 09:30 open -- two per full session, one on a
  half day -- by clock time, so a missing 15-minute bar thins a bucket rather
  than shifting every later one, and a daylight-saving change moves nothing;
* the EMA is the recursive one, masked until it has seen a full span;
* "days to catch" is the EMA's own recurrence solved, not gap / velocity: it
  agrees with a bar-by-bar simulation, and it is sooner than the flat-EMA sum;
* Strategy A needs the deep dip AND the turn; Strategy B needs a cross on one
  of the last three candles that still holds, and not an extended one.

Pure maths: no venue, no network, no database.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.domains.trading.market import ema_screen as es
from tests.rebuild.synthetic import bars, crash_then, path, sessions
from tests.rebuild.synthetic import cross as _cross


# ---- building the 4-hour bars ----------------------------------------------

def test_a_full_session_folds_into_two_bars_on_the_open():
    day = date(2026, 9, 28)
    four = es.four_hour(es.frame(bars([(day, [100.0] * 26)])))
    assert [t.strftime("%H:%M") for t in four.index] == ["09:30", "13:30"]
    assert list(four["n"]) == [16, 10]


def test_bars_outside_the_regular_session_are_not_folded_in():
    """A venue that ignores session_filter must still not move the 09:30 bar."""
    day = date(2026, 9, 28)
    early = bars([(day, [90.0] * 8)], open_at=(7, 30))       # 07:30-09:15
    late = bars([(day, [95.0] * 4)], open_at=(16, 0))        # 16:00-16:45
    regular = bars([(day, [100.0] * 26)])
    four = es.four_hour(es.frame(early + regular + late))
    assert len(four) == 2
    assert four["open"].iloc[0] == 100.0 and four["close"].iloc[-1] == 100.0


def test_the_extended_session_is_four_full_bars():
    day = date(2026, 9, 28)
    rows = bars([(day, [100.0] * 64)], open_at=(4, 0))        # 04:00-19:45
    four = es.four_hour(es.frame(rows, "extended"), "extended")
    assert [t.strftime("%H:%M") for t in four.index] == ["04:00", "08:00", "12:00", "16:00"]
    assert set(four["n"]) == {16}


def test_a_half_day_is_one_bar():
    day = date(2026, 11, 27)                                  # closes 13:00
    four = es.four_hour(es.frame(bars([(day, [100.0] * 14)])))
    assert len(four) == 1 and int(four["n"].iloc[0]) == 14


def test_a_missing_bar_thins_its_bucket_and_shifts_nothing():
    day = date(2026, 9, 28)
    rows = bars([(day, [100.0 + k for k in range(26)])])
    del rows[3]                                               # 10:15 never arrived
    four = es.four_hour(es.frame(rows))
    assert [t.strftime("%H:%M") for t in four.index] == ["09:30", "13:30"]
    assert list(four["n"]) == [15, 10]
    assert four["close"].iloc[0] == 115.0                     # 13:15's close, not 13:30's


def test_the_anchor_survives_a_daylight_saving_change():
    """Epoch-only rows are converted to Eastern wall clock, so the Monday after
    the clocks go back still opens at 09:30."""
    from zoneinfo import ZoneInfo

    eastern = ZoneInfo("America/New_York")
    rows = []
    for day in (date(2026, 10, 30), date(2026, 11, 2)):      # Fri EDT, Mon EST
        at = datetime(day.year, day.month, day.day, 9, 30, tzinfo=eastern)
        for k in range(26):
            rows.append({"timestamp": (at + timedelta(minutes=15 * k)).timestamp(),
                         "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1})
    four = es.four_hour(es.frame(rows))
    assert [t.strftime("%a %H:%M") for t in four.index] == [
        "Fri 09:30", "Fri 13:30", "Mon 09:30", "Mon 13:30"]


def test_missing_chunks_are_counted_not_hidden():
    """A session with an hour of 15-minute bars missing still folds into its
    two 4-hour bars, and the row says one of them was built thin."""
    rows = crash_then(0.02)
    whole = es.screen("X", rows)
    assert whole["thin_bars"] == 0
    day = rows[26 * 5]["time"][:10]                           # the sixth session
    holed = [r for r in rows if not (r["time"].startswith(day)
                                     and "10:00" <= r["time"][11:16] < "11:00")]
    assert len(holed) == len(rows) - 4
    thin = es.screen("X", holed)
    assert thin["thin_bars"] == 1 and thin["bars"] == whole["bars"]


def test_a_bar_with_no_close_is_dropped_not_zeroed():
    day = date(2026, 9, 28)
    rows = bars([(day, [100.0] * 26)])
    rows[5]["close"] = None
    rows[6]["close"] = ""
    frame = es.frame(rows)
    assert len(frame) == 24 and frame["close"].min() == 100.0


# ---- the EMA and the catch-up arithmetic ------------------------------------

def test_the_ema_is_recursive_and_masked_until_a_full_span():
    import pandas as pd

    closes = pd.Series([float(x) for x in range(1, 41)])
    out = es.ema(closes, 21)
    assert out.iloc[:20].isna().all() and out.iloc[20:].notna().all()
    alpha, want = 2 / 22, 1.0
    for x in closes.iloc[1:]:
        want = alpha * x + (1 - alpha) * want
    assert out.iloc[-1] == pytest.approx(want)


@pytest.mark.parametrize("gap,velocity", [(20.0, 1.0), (5.0, 0.25), (30.0, 3.0), (0.4, 0.05)])
def test_days_to_catch_is_the_emas_own_recurrence_solved(gap, velocity):
    """Price rises v a bar; the EMA moves alpha of the way toward it each bar.
    The closed form lands between the last bar with a gap and the first without."""
    alpha = 2 / 22
    g, steps = gap, 0
    while g > 0:
        g = (1 - alpha) * (g - velocity)
        steps += 1
    n = es.bars_to_catch(gap, velocity, alpha)
    assert steps - 1 < n <= steps
    # ...and the EMA closing from its side makes it sooner than gap / velocity
    assert n < gap / velocity


def test_no_catch_up_is_projected_for_a_price_that_is_not_rising():
    assert es.bars_to_catch(10.0, 0.0, 2 / 22) is None
    assert es.bars_to_catch(10.0, -0.5, 2 / 22) is None
    assert es.bars_to_catch(0.0, 1.0, 2 / 22) == 0.0


def test_the_velocity_is_a_fit_over_every_close():
    assert es.slope([10, 11, 12, 13, 14]) == pytest.approx(1.0)
    # one outsized last bar moves a fitted slope less than the two-endpoint
    # average delta, (14 - 10) / 4 = 1.0
    assert es.slope([10, 10, 10, 10, 14]) == pytest.approx(0.8)


# ---- the two setups ------------------------------------------------------------

def test_a_deep_dip_turning_back_up_is_strategy_a_with_a_catch_up_estimate():
    row = es.screen("DIP", crash_then(0.02))
    assert row["setup"] == "A"
    assert row["deepest_pct"] < -20 and row["distance_pct"] < 0
    assert row["distance_pct"] > row["deepest_pct"]
    assert row["velocity"] > 0 and row["days_to_catch"] > 0
    assert row["days_to_catch"] == pytest.approx(row["bars_to_catch"] / 2, abs=0.06)
    assert row["hours_to_catch"] == pytest.approx(row["days_to_catch"] * 6.5, abs=0.4)


def test_a_deep_dip_still_falling_is_not_strategy_a():
    row = es.screen("KNIFE", crash_then(-0.02))
    assert row["deepest_pct"] < -20
    assert row["setup"] is None
    assert row["days_to_catch"] is None


def test_a_shallow_dip_is_not_strategy_a():
    ds = sessions(28)
    rows = bars(path(ds, lambda i, k: 100 - (8 if i >= 20 else 0) + 0.01 * k))
    row = es.screen("SHALLOW", rows)
    assert row["deepest_pct"] > -20 and row["setup"] is None


@pytest.mark.parametrize("bars_ago", [1, 2, 3])
def test_a_cross_on_one_of_the_last_three_candles_is_strategy_b(bars_ago):
    row = es.screen("CROSS", _cross(bars_ago))
    assert row["cross_age"] == bars_ago
    assert row["setup"] == "B"
    assert 0 < row["distance_pct"] < 20


def test_a_cross_four_candles_ago_is_no_longer_fresh():
    row = es.screen("STALE", _cross(4))
    assert row["cross_age"] == 4 and row["setup"] is None


def test_a_cross_that_is_already_extended_is_not_strategy_b():
    row = es.screen("CHASE", _cross(1, jump=1.30))
    assert row["cross_age"] == 1 and row["distance_pct"] >= 20
    assert row["setup"] is None


def test_the_thresholds_are_the_rules_own():
    rows = crash_then(0.02)
    assert es.screen("X", rows, es.Rules(deep_pct=40))["setup"] is None
    assert es.screen("X", _cross(4), es.Rules(cross_within=4))["setup"] == "B"


def test_too_little_history_says_so_rather_than_guessing():
    ds = sessions(10)
    row = es.screen("NEW", bars(path(ds, lambda i, k: 100.0)))
    assert row["available"] is False and row["setup"] is None
    assert "26" in row["reason"] and "20" in row["reason"]


def test_the_newest_bar_says_whether_it_is_still_forming():
    rows = _cross(1)
    last_day = datetime.fromisoformat(rows[-1]["time"]).date()
    mid = datetime(last_day.year, last_day.month, last_day.day, 14, 0)
    after = datetime(last_day.year, last_day.month, last_day.day, 16, 5)
    assert es.screen("F", rows, as_of=mid)["forming"] is True
    assert es.screen("F", rows, as_of=after)["forming"] is False
    assert es.screen("F", rows)["forming"] is None


def test_the_tables_put_the_soonest_catch_and_the_freshest_cross_first():
    rows = [{"setup": "A", "days_to_catch": 9.0, "distance_pct": -5, "symbol": "a9"},
            {"setup": "A", "days_to_catch": None, "distance_pct": -2, "symbol": "an"},
            {"setup": "A", "days_to_catch": 2.5, "distance_pct": -9, "symbol": "a2"},
            {"setup": "B", "cross_age": 3, "distance_pct": 1, "symbol": "b3"},
            {"setup": "B", "cross_age": 1, "distance_pct": 4, "symbol": "b1"},
            {"setup": None, "symbol": "none"}]
    tables = es.by_setup(rows)
    assert [r["symbol"] for r in tables["A"]] == ["a2", "a9", "an"]
    assert [r["symbol"] for r in tables["B"]] == ["b1", "b3"]


def test_an_unknown_session_is_refused():
    with pytest.raises(ValueError):
        es.Rules(session="overnight")
