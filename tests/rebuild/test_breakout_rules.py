"""BreakoutRadar's eight rules, one at a time.

Each test builds a candle series that passes everything, breaks exactly one
rule, and asserts that rule -- and only that rule -- is the one reported. The
baseline: a climb from 80 to 100, twenty candles coiled in a 6% channel of
bodies, then a green candle closing ~6% above it on triple volume.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.domains.trading.market import breakout as br
from tests.rebuild.synthetic import breakout_scenario as scenario


def run(df, *, timeframe="1d", market="US", cap=5e9, params=None, daily=None):
    series = br.prepare("TEST", df, daily, timeframe=timeframe)
    return br.evaluate(series, params or br.Params(), timeframe=timeframe,
                       market=market, market_cap=cap)


def only_failed(result):
    return [k for k, v in result["rules"].items() if v is False]


def test_the_baseline_passes_all_eight():
    got = run(scenario())
    assert got["passed"] is True and got["failed"] == []
    assert all(got["rules"].values())
    assert got["breakout_age"] == 0
    assert got["consolidation_high"] == pytest.approx(104.0)
    assert got["consolidation_low"] == pytest.approx(99.0)
    assert got["range_pct"] == pytest.approx(100 * 5 / 99, abs=0.01)
    assert got["breakout_size_pct"] == pytest.approx(100 * 6.5 / 104, abs=0.01)
    assert got["rvol"] == pytest.approx(3.0)
    assert got["breakout_candle_timestamp"] == got["as_of"]


def test_1_a_loose_range_is_not_a_consolidation():
    loose = [(94 + (i % 2) * 11, 95 + (i % 2) * 12) for i in range(20)]  # bodies 94..107
    got = run(scenario(coil=loose, breakout=(107.5, 113.5)))
    assert only_failed(got) == ["consolidation"]
    assert got["range_pct"] == pytest.approx(100 * 13 / 94, abs=0.01)


def test_1_the_range_is_drawn_on_bodies_not_wicks():
    got = run(scenario(wick_spike=103.9 * 1.08))      # an 8% wick, bodies unchanged
    assert got["rules"]["consolidation"] is True


def test_2_a_close_just_over_the_top_is_not_a_breakout():
    got = run(scenario(breakout=(99.5, 105.0)))          # +0.96% over 104
    assert only_failed(got) == ["penetration"]


def test_3_a_small_body_fails_on_daily_but_not_hourly():
    candle = (106.0, 109.2)                              # +3.0% body, +5% over the top
    daily = run(scenario(breakout=candle))
    assert only_failed(daily) == ["body"]
    hourly = run(scenario(breakout=candle), timeframe="1h")
    assert hourly["rules"]["body"] is True


def test_3_a_red_candle_that_closes_above_the_range_is_a_fade():
    got = run(scenario(breakout=(118.0, 110.5)))
    assert "body" in only_failed(got)


def test_4_market_cap_floors_are_the_markets_own():
    assert only_failed(run(scenario(), cap=40e6)) == ["market_cap"]
    assert run(scenario(), cap=60e6)["passed"] is True
    assert only_failed(run(scenario(), market="INDIA", cap=2e7)) == ["market_cap"]   # Rs 2 crore
    assert run(scenario(), market="INDIA", cap=5e7)["passed"] is True                # Rs 5 crore


def test_4_an_unknown_cap_is_unverified_not_failed():
    got = run(scenario(), cap=None)
    assert got["rules"]["market_cap"] is None and got["passed"] is True


def test_5_thin_volume_is_not_conviction():
    assert only_failed(run(scenario(vol_x=1.2))) == ["rvol"]
    assert run(scenario(vol_x=40.0))["passed"] is True       # no upper cap


def test_6_an_illiquid_name_fails_on_average_daily_volume():
    got = run(scenario(base_vol=300_000))
    assert only_failed(got) == ["liquidity"]
    assert got["adv"] == pytest.approx(300_000)


def test_6_the_average_leaves_out_the_latest_session():
    """A breakout day's 3x volume must not lift its own liquidity test."""
    got = run(scenario(base_vol=450_000, vol_x=5.0))
    assert got["adv"] == pytest.approx(450_000)
    assert "liquidity" in only_failed(got)


def test_7_far_below_the_recent_high_is_not_near_a_high():
    got = run(scenario(wick_spike=130.0))
    assert only_failed(got) == ["near_high"]
    assert got["pct_from_high20"] < -10


def test_8_below_the_slow_ema_is_not_in_trend():
    falling = list(np.linspace(170, 101, 60))
    got = run(scenario(lead=falling))
    assert "trend" in only_failed(got)
    assert got["price"] < got["ema50"]


def test_a_breakout_two_candles_ago_that_holds_still_counts():
    got = run(scenario(after=[(110.6, 111.0), (111.0, 111.6)]))
    assert got["passed"] is True and got["breakout_age"] == 2


def test_a_breakout_that_fell_back_into_its_range_does_not():
    got = run(scenario(after=[(110.0, 106.0), (106.0, 103.0)]))
    assert got["passed"] is False and got["rules"]["penetration"] is False


def test_a_breakout_older_than_the_window_is_not_found():
    after = [(110.6, 111.0), (111.0, 111.4), (111.4, 111.8)]
    assert run(scenario(after=after))["passed"] is False
    wider = br.Params(breakout_within=4)
    got = run(scenario(after=after), params=wider)
    assert got["passed"] is True and got["breakout_age"] == 3


def test_thresholds_move_the_verdict():
    tight = br.Params(max_range_pct=4.0)
    assert only_failed(run(scenario(), params=tight)) == ["consolidation"]
    assert run(scenario(vol_x=1.2), params=br.Params(min_rvol=1.1))["passed"] is True


def test_too_few_candles_says_so():
    short = scenario().iloc[-30:]
    got = run(short)
    assert got["available"] is False and "50 EMA" in got["reason"]


def test_out_of_range_parameters_are_refused():
    with pytest.raises(ValueError):
        br.Params(min_rvol=-1)
    with pytest.raises(ValueError):
        br.Params(consolidation_bars=2)
    with pytest.raises(ValueError):
        br.Params(max_range_pct=float("nan"))


def test_the_chart_carries_the_overlay_and_aligned_emas():
    df = scenario()
    series = br.prepare("TEST", df, None, timeframe="1d")
    got = br.chart(series, br.Params(), timeframe="1d", market="US", market_cap=5e9, bars=40)
    assert len(got["candles"]) == len(got["ema20"]) == len(got["ema50"]) >= 40
    assert got["breakout_candle_timestamp"] == got["candles"][-1]["t"]
    assert got["consolidation_high"] == pytest.approx(104.0)
    times = [c["t"] for c in got["candles"]]
    assert got["consolidation_start"] in times and got["consolidation_end"] in times
    assert times.index(got["consolidation_end"]) == len(times) - 2


def test_the_resolved_thresholds_say_what_was_applied():
    p = br.Params()
    assert p.resolved("15m", "US")["min_body_pct"] == 2.5
    assert p.resolved("4h", "INDIA")["min_body_pct"] == 5.0
    assert p.resolved("1d", "INDIA")["min_market_cap"] == 3e7
    assert p.resolved("1d", "INDIA")["currency"] == "INR"
