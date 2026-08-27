"""The HOT scan: Wilder DMI/ADX over the top 100, and the three gates.

The arithmetic is a port of the desk chart's adxCompute. These pin the port
against hand-worked values and against the chart's own conventions, because
the failure that matters is silent: a name ranked HOT here that shows no
matching marker on its own chart is worse than no scanner at all.
"""

from __future__ import annotations

import math

import pytest

from app.core.config import get_settings
from app.services import hot_scan


def _bars(closes, *, spread=1.0, time="2026-08-18T10:00:00"):
    """A bar per close, with a fixed high/low band around it."""
    return [{"time": time, "high": c + spread, "low": c - spread, "close": c}
            for c in closes]


# ── the universe ────────────────────────────────────────────────────────────

def test_the_universe_is_a_hundred_distinct_tickers():
    u = hot_scan.universe()
    assert len(u) == 100, f"asked for the top 100, got {len(u)}"
    assert len(set(u)) == 100, "duplicates would waste a call and double-count"
    assert all(t.isupper() and 1 <= len(t) <= 5 for t in u), u


# ── Wilder DMI/ADX ──────────────────────────────────────────────────────────

def test_wilder_smoothing_seeds_with_a_sum_then_decays():
    """Not a rolling mean — Wilder's own recurrence, which is what every
    charting package draws and therefore the only version whose numbers match
    the ones on screen."""
    src = [1.0] * 6
    out = hot_scan._wilder(src, 3)
    assert out[:2] == [None, None]
    assert out[2] == 3.0                       # seed: the sum of the first 3
    assert out[3] == pytest.approx(3.0)        # 3 - 3/3 + 1
    assert out[5] == pytest.approx(3.0)


def test_too_few_bars_is_none_not_a_guess():
    """ADX averages DX values that are themselves smoothed; on a short series
    the answer is mostly its own seed, so there is no honest number to give."""
    assert hot_scan.dmi(_bars([100 + i for i in range(20)])) is None
    assert hot_scan.dmi([]) is None


def test_a_clean_uptrend_is_all_plus_di():
    r = hot_scan.dmi(_bars([100 + i * 1.2 for i in range(60)]))
    assert r["minus_di"] == 0          # no down-move at all to answer it
    assert r["plus_di"] > 50
    assert r["adx"] > 90               # DX is 100 every bar, so ADX converges


def test_a_clean_downtrend_is_all_minus_di():
    r = hot_scan.dmi(_bars([200 - i * 1.2 for i in range(60)]))
    assert r["plus_di"] == 0
    assert r["minus_di"] > 50


# ── the gates ───────────────────────────────────────────────────────────────

def test_the_three_gates_as_the_desk_stated_them():
    s = get_settings()
    assert (s.tradier_hot_min_pdi, s.tradier_hot_di_ratio, s.tradier_hot_min_adx) \
        == (25.0, 2.0, 34.0)
    assert hot_scan.is_hot({"plus_di": 40, "minus_di": 15, "adx": 40})


def test_a_weak_plus_di_is_not_hot():
    # dominant and trending, but the up-move is small in its own right
    assert not hot_scan.is_hot({"plus_di": 24, "minus_di": 5, "adx": 45})


def test_leading_is_not_dominating():
    """+DI over -DI is a crossover, which happens constantly and reverses just
    as often. The gate is TWICE -DI: the buyers are not being answered."""
    assert not hot_scan.is_hot({"plus_di": 30, "minus_di": 16, "adx": 45})   # 1.88x
    assert hot_scan.is_hot({"plus_di": 32, "minus_di": 16, "adx": 45})       # 2.00x


def test_a_strong_one_sided_move_inside_a_range_is_not_hot():
    assert not hot_scan.is_hot({"plus_di": 50, "minus_di": 5, "adx": 34})    # not > 34
    assert hot_scan.is_hot({"plus_di": 50, "minus_di": 5, "adx": 34.01})


def test_chop_clears_nothing():
    r = hot_scan.dmi(_bars([100 + math.sin(i) for i in range(60)]))
    assert not hot_scan.is_hot(r)


def test_a_downtrend_is_never_hot():
    """HOT is a CALL shortlist; it is +DI that has to dominate."""
    r = hot_scan.dmi(_bars([200 - i * 1.2 for i in range(60)]))
    assert not hot_scan.is_hot(r)


# ── bar hygiene ─────────────────────────────────────────────────────────────

def test_extended_hours_bars_are_dropped_like_the_chart_drops_them():
    """A gap is a large true range, so overnight bars inflate ADX. The chart
    keeps 09:30-16:00; a scanner that did not would rank names HOT on
    overnight noise and show no marker on their charts."""
    rows = [
        {"time": "2026-08-18T04:15:00", "high": 1, "low": 1, "close": 1},
        {"time": "2026-08-18T09:29:00", "high": 1, "low": 1, "close": 1},
        {"time": "2026-08-18T09:30:00", "high": 1, "low": 1, "close": 1},
        {"time": "2026-08-18T12:00:00", "high": 1, "low": 1, "close": 1},
        {"time": "2026-08-18T16:00:00", "high": 1, "low": 1, "close": 1},
        {"time": "2026-08-18T18:45:00", "high": 1, "low": 1, "close": 1},
    ]
    kept = [r["time"][11:16] for r in hot_scan._regular_session(rows)]
    assert kept == ["09:30", "12:00", "16:00"]


def test_the_port_matches_the_chart_on_a_worked_series():
    """Pinned against the browser's adxCompute over the same 40 bars.

    Both implementations were run on this exact series; if the port ever
    drifts, this is what catches it before a HOT row and its chart disagree.
    """
    closes = [100 + 2 * math.sin(i / 3) + i * 0.35 for i in range(40)]
    r = hot_scan.dmi(_bars(closes, spread=0.6))
    assert r["plus_di"] == pytest.approx(36.8921, abs=1e-4)
    assert r["minus_di"] == pytest.approx(4.1768, abs=1e-4)
    assert r["adx"] == pytest.approx(69.4948, abs=1e-4)


# ── both directions ─────────────────────────────────────────────────────────

def test_the_gates_read_the_same_way_down_as_up():
    """DMI measures up-moves and down-moves identically, so a name whose -DI
    dominates is as tradable as one whose +DI does — the other way."""
    assert hot_scan.hot_side({"plus_di": 45, "minus_di": 10, "adx": 40}) == "call"
    assert hot_scan.hot_side({"plus_di": 10, "minus_di": 45, "adx": 40}) == "put"


def test_a_downtrend_inside_a_range_is_still_nothing():
    assert hot_scan.hot_side({"plus_di": 10, "minus_di": 45, "adx": 34}) is None


def test_a_weak_or_merely_leading_minus_di_is_not_a_put():
    assert hot_scan.hot_side({"plus_di": 5, "minus_di": 24, "adx": 40}) is None    # -DI < 25
    assert hot_scan.hot_side({"plus_di": 16, "minus_di": 30, "adx": 40}) is None   # 1.88x
    assert hot_scan.hot_side({"plus_di": 16, "minus_di": 32, "adx": 40}) == "put"  # 2.00x


def test_a_name_can_never_be_both_sides_at_once():
    """Each side demands its own DI be at least twice the other, and that pair
    of claims has no solution — so the buy direction is never ambiguous."""
    for pdi in range(0, 101, 5):
        for mdi in range(0, 101, 5):
            side = hot_scan.hot_side({"plus_di": pdi, "minus_di": mdi, "adx": 50})
            if side == "call":
                assert pdi >= mdi * 2 and pdi > 25
            elif side == "put":
                assert mdi >= pdi * 2 and mdi > 25


def test_is_hot_still_means_the_call_side():
    """The older helper keeps its meaning; a downtrend must not start
    reporting True to anything that still calls it."""
    assert hot_scan.is_hot({"plus_di": 45, "minus_di": 10, "adx": 40})
    assert not hot_scan.is_hot({"plus_di": 10, "minus_di": 45, "adx": 40})


# ── granularity ─────────────────────────────────────────────────────────────

def test_every_offered_interval_has_its_own_lookback():
    """A coarser bar needs a longer window to reach the same bar count.

    Measured against the live venue: 5min/5d gives 248 regular-session bars,
    15min/10d 166, 30min/20d 198, 1h/40d 197. Ask for 5 days of hourly and
    the ADX comes back built mostly from its own seed.
    """
    days = {iv: hot_scan.days_for(iv) for iv in hot_scan.INTERVALS}
    assert days == {"5min": 5, "15min": 10, "30min": 20, "1h": 40}
    # a coarser bar never gets a shorter window than a finer one
    assert sorted(days.values()) == list(days.values())


def test_the_desk_default_is_five_minute_bars():
    assert get_settings().tradier_hot_interval == "5min"
    assert hot_scan.INTERVALS[0] == "5min"


def test_an_unknown_interval_falls_back_rather_than_crashing():
    assert hot_scan.days_for("nonsense") == 5
