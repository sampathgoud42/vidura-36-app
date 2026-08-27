"""The A/B super-signal options strategy's decision logic.

Pure functions only — no venue, no threads. What is asserted here is the
operator's rule: never buy a premium that is fading, and never enter a
same-day contract after the cutoff.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.auto_trade import (
    AB_SIDE,
    ab_decision,
    bid_trend,
    choose_expiration,
)

P = {
    "ab_observe_min_s": 300,
    "ab_observe_max_s": 600,
    "ab_stable_s": 150,
    "ab_max_wait_s": 1800,
    "ab_tol_pct": 2.0,
}


def obs(samples, started=0.0):
    """samples: [(ts, bid)] with ts in seconds from the observation start."""
    return {"samples": [(float(t), float(b)) for t, b in samples], "started": started}


# ── direction mapping ───────────────────────────────────────────────────────

def test_long_buys_calls_short_buys_puts():
    assert AB_SIDE["LONG"] == "call"
    assert AB_SIDE["SHORT"] == "put"


# ── trend classification ────────────────────────────────────────────────────

def test_rising_stable_and_falling():
    assert bid_trend([1.00, 1.02, 1.06], tol_pct=2.0) == "rising"
    assert bid_trend([1.00, 1.01, 1.00], tol_pct=2.0) == "stable"
    assert bid_trend([1.00, 0.97, 0.90], tol_pct=2.0) == "falling"
    assert bid_trend([1.00], tol_pct=2.0) == "unknown"
    assert bid_trend([], tol_pct=2.0) == "unknown"


def test_a_spike_given_back_is_falling_not_stable():
    """Ends where it started, but the move was handed back — that is a fade,
    and the naive first-vs-last test would call it stable and buy it."""
    assert bid_trend([1.00, 1.30, 1.01], tol_pct=2.0) == "falling"


def test_zero_and_none_samples_are_ignored():
    assert bid_trend([0, 1.00, 1.05], tol_pct=2.0) == "rising"
    assert bid_trend([None, None], tol_pct=2.0) == "unknown"


# ── the observe / wait / buy decision ───────────────────────────────────────

def test_waits_out_the_minimum_observation_even_when_rising():
    o = obs([(0, 1.00), (60, 1.20)])
    action, why = ab_decision(o, now_mono=120, p=P)
    assert action == "wait" and "observing" in why


def test_buys_a_rising_bid_once_the_window_is_up():
    o = obs([(0, 1.00), (150, 1.04), (300, 1.09)])
    action, _ = ab_decision(o, now_mono=310, p=P)
    assert action == "buy"


def test_buys_a_stable_bid_once_the_window_is_up():
    o = obs([(0, 1.00), (150, 1.005), (300, 0.995)])
    action, _ = ab_decision(o, now_mono=310, p=P)
    assert action == "buy"


def test_does_not_buy_a_fading_bid_in_phase_one():
    o = obs([(0, 1.00), (150, 0.95), (300, 0.88)])
    action, why = ab_decision(o, now_mono=310, p=P)
    assert action == "wait" and "falling" in why


def test_takes_it_when_the_trailing_window_steadies_after_a_fade():
    """The operator's rescue clause: it fell, then held for 2-3 minutes."""
    samples = [(0, 1.00), (200, 0.90), (400, 0.80)]
    samples += [(t, 0.80) for t in range(650, 810, 30)]   # flat trailing window
    action, why = ab_decision(obs(samples), now_mono=800, p=P)
    assert action == "buy" and "after fading" in why


def test_keeps_waiting_while_it_is_still_dropping_after_phase_one():
    samples = [(0, 1.00), (300, 0.90), (650, 0.80), (700, 0.74), (780, 0.68)]
    action, _ = ab_decision(obs(samples), now_mono=800, p=P)
    assert action == "wait"


def test_gives_up_once_max_wait_passes():
    samples = [(0, 1.00), (900, 0.60), (1750, 0.40), (1800, 0.30)]
    action, why = ab_decision(obs(samples), now_mono=1900, p=P)
    assert action == "skip" and "never steadied" in why


def test_no_samples_eventually_skips_rather_than_waiting_forever():
    action, _ = ab_decision(obs([(0, 1.00)]), now_mono=2000, p=P)
    assert action == "skip"


# ── expiration choice: 0DTE cutoff and the 0..6 day window ──────────────────

TODAY = date(2026, 8, 6)
EXPS = ["2026-08-06", "2026-08-07", "2026-08-13", "2026-09-18"]


def test_prefers_zero_dte_before_the_cutoff():
    exp, dte = choose_expiration(EXPS, TODAY, dte_max=6, allow_zero_dte=True)
    assert (exp, dte) == ("2026-08-06", 0)


def test_rolls_past_zero_dte_after_the_cutoff():
    exp, dte = choose_expiration(EXPS, TODAY, dte_max=6, allow_zero_dte=False)
    assert (exp, dte) == ("2026-08-07", 1)


def test_never_reaches_beyond_the_dte_window():
    # only the 43-day expiry is left once the near ones are gone
    exp, dte = choose_expiration(["2026-09-18"], TODAY, dte_max=6,
                                 allow_zero_dte=True)
    assert exp is None and dte is None


def test_ignores_expired_and_unparseable_dates():
    exp, dte = choose_expiration(
        ["2026-08-01", "not-a-date", None, "2026-08-11"], TODAY,
        dte_max=6, allow_zero_dte=True)
    assert (exp, dte) == ("2026-08-11", 5)


@pytest.mark.parametrize("dte_max,expected", [(0, "2026-08-06"), (1, "2026-08-06")])
def test_dte_max_zero_still_allows_same_day(dte_max, expected):
    exp, _ = choose_expiration(EXPS, TODAY, dte_max=dte_max, allow_zero_dte=True)
    assert exp == expected


# ── per-ticker cooldown ─────────────────────────────────────────────────────

def _watcher(user_id, *, cooldown_s=3600, strategy="ab_signal_options"):
    return {"user_id": user_id, "events": [],
            "params": {"ab_cooldown_s": cooldown_s, "strategy": strategy}}


def _place_row(db, user_id, ticker, *, minutes_ago, strategy="ab_signal_options",
               status="open"):
    from datetime import datetime, timedelta, timezone

    from app.models.tradier import TradierPosition

    row = TradierPosition(
        user_id=user_id, sandbox=True, underlying=ticker,
        occ_symbol=f"{ticker}_TEST", option_type="call", strike=1.0,
        expiration="2026-08-13", contracts=1, tp_pct=15, sl_pct=30, buy_pct=1,
        buy_order_id="1", strategy=strategy, status=status,
        opened_at=(datetime.now(timezone.utc).replace(tzinfo=None)
                   - timedelta(minutes=minutes_ago)),
    )
    db.add(row)
    db.commit()
    return row


def test_no_cooldown_when_the_ticker_is_untouched(db_session, user):
    from app.services.auto_trade import _ab_cooldown_left
    assert _ab_cooldown_left(_watcher(user["user_id"]), "SPY") == 0


def test_recent_entry_blocks_the_same_ticker(db_session, user):
    from app.services.auto_trade import _ab_cooldown_left

    db = db_session
    _place_row(db, user["user_id"], "SPY", minutes_ago=10)
    left = _ab_cooldown_left(_watcher(user["user_id"]), "SPY")
    assert 49 * 60 <= left <= 50 * 60          # ~50 minutes of the hour remain


def test_an_hour_later_the_ticker_is_free(db_session, user):
    from app.services.auto_trade import _ab_cooldown_left

    db = db_session
    _place_row(db, user["user_id"], "SPY", minutes_ago=61)
    assert _ab_cooldown_left(_watcher(user["user_id"]), "SPY") == 0


def test_cooldown_is_per_ticker(db_session, user):
    from app.services.auto_trade import _ab_cooldown_left

    db = db_session
    _place_row(db, user["user_id"], "SPY", minutes_ago=5)
    w = _watcher(user["user_id"])
    assert _ab_cooldown_left(w, "SPY") > 0
    assert _ab_cooldown_left(w, "QQQ") == 0


def test_other_strategies_do_not_trigger_it(db_session, user):
    """The rule is scoped to this strategy — a manual buy must not lock the
    ticker out of the auto-trader for an hour."""
    from app.services.auto_trade import _ab_cooldown_left

    db = db_session
    _place_row(db, user["user_id"], "SPY", minutes_ago=5, strategy="Manual")
    assert _ab_cooldown_left(_watcher(user["user_id"]), "SPY") == 0


def test_a_rejected_buy_does_not_lock_the_ticker(db_session, user):
    from app.services.auto_trade import _ab_cooldown_left

    db = db_session
    _place_row(db, user["user_id"], "SPY", minutes_ago=5, status="failed")
    assert _ab_cooldown_left(_watcher(user["user_id"]), "SPY") == 0


def test_zero_disables_the_cooldown(db_session, user):
    from app.services.auto_trade import _ab_cooldown_left

    db = db_session
    _place_row(db, user["user_id"], "SPY", minutes_ago=1)
    assert _ab_cooldown_left(_watcher(user["user_id"], cooldown_s=0), "SPY") == 0
