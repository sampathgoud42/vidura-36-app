"""The super_signals auto-trade strategy: what fires an order, and what never does.

This strategy spends money with nobody watching, so the rules that say NO get
the most tests:

* only a LIVE signal of a picked type, on a picked ticker, inside the window,
  still open, and minutes old -- never a backfilled, resolved or stale one;
* everything already on the desk when the watcher arms is history, not a
  trigger, so arming can never fire a burst of entries;
* one entry per ticker per hour, but a refusal that bought nothing does not
  start that hour;
* one signal is one attempt, even across a second look at the same row;
* entries go through the manual BUY's own path (entry.open_managed), so the
  position is the same managed position with the same guards.

The watcher's tick is driven directly with a pinned clock and a fake desk, so
no test waits on a thread or on the market.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from datetime import time as dtime

import pytest

from app.domains.trading.execution import autotrade
from app.domains.trading.risk import clock
from app.services import super_signals as desk

V1 = "/api/v1/tradier"
PICK = "poc|poc_48h|medium|SHORT"
PICK_LONG = "flow|scalp_bias+near_level+adx_strong||LONG"


def _row(sid, *, key=PICK, ticker="SPY", time="10:30", source="live", outcome="open"):
    agent, setup, grade, direction = key.split("|")
    return {"id": sid, "agent": agent, "setup": setup, "grade": grade,
            "direction": direction, "ticker": ticker, "time": time,
            "source": source, "outcome": outcome}


class Desk:
    """The signal desk's /api/session, as the watcher sees it."""

    def __init__(self):
        self.rows: list[dict] = []
        self.date = date.today().isoformat()
        self.down: desk.Unavailable | None = None

    def get_json(self, path, params=None):
        assert path == "/api/session"
        if self.down is not None:
            raise self.down
        return {"date": self.date, "signals": list(self.rows)}


@pytest.fixture()
def feed(monkeypatch) -> Desk:
    d = Desk()
    monkeypatch.setattr(desk, "get_json", d.get_json)
    return d


@pytest.fixture()
def at(monkeypatch):
    """Pin the desk clock to today at a chosen CST time.

    TODAY, not a fixed date: validate_entry checks expiries against the real
    date, and the fake venue lists expiries from clock.today()."""
    holder = {"now": datetime.combine(date.today(), dtime(10, 32), tzinfo=clock.DESK_TZ)}
    monkeypatch.setattr(clock, "now", lambda: holder["now"])

    def set_time(hh, mm):
        holder["now"] = datetime.combine(date.today(), dtime(hh, mm), tzinfo=clock.DESK_TZ)
        return holder["now"]
    set_time.holder = holder
    return set_time


def _watcher(op, *, signals=(PICK,), tickers=("SPY", "QQQ"), zero_dte=False, **kw):
    return autotrade.Watcher(
        tenant_id=op.tenant_id, tickers=list(tickers), strategy="super_signals",
        live=False, buy_pct=kw.get("buy_pct", 20.0), tp_pct=15.0, sl_pct=30.0,
        tolerance_pct=25.0, min_contracts=kw.get("min_contracts", 1),
        delta_min=0.35, delta_max=0.65, armed_at=clock.now(),
        signals=list(signals), window_open="08:30", window_close="14:30",
        zero_dte=zero_dte)


def _positions(client, op):
    r = client.get(f"{V1}/positions", headers=op.headers)
    assert r.status_code == 200, r.text
    return r.json()["items"]


# ---- the rules, without a clock or a venue ---------------------------------

NOW = datetime(2026, 9, 24, 10, 32, tzinfo=clock.DESK_TZ)


def test_the_type_key_is_the_rank_endpoints_key():
    assert autotrade.type_key(_row("x")) == PICK
    assert autotrade.type_key(_row("x", key=PICK_LONG)) == PICK_LONG


@pytest.mark.parametrize("row,why", [
    (_row("a", source="catchup"), "not fired live"),
    (_row("b", source="backfill"), "not fired live"),
    (_row("c", outcome="target"), "already resolved"),
    (_row("d", time="08:25"), "outside"),
    (_row("e", time="14:30"), "outside"),
    (_row("f", time="10:20"), "min old"),
    (_row("g", time="nonsense"), "outside"),
])
def test_a_signal_that_is_not_live_open_fresh_and_in_window_is_refused(row, why):
    assert why in autotrade.refusal(row, now=NOW, window_open="08:30", window_close="14:30")


def test_a_live_open_fresh_signal_in_the_window_is_accepted():
    assert autotrade.refusal(_row("ok", time="10:30"), now=NOW,
                             window_open="08:30", window_close="14:30") is None


def test_the_same_ticker_waits_out_its_cooldown():
    recent = NOW - timedelta(minutes=20)
    why = autotrade.refusal(_row("x"), now=NOW, window_open="08:30", window_close="14:30",
                            last_entry=recent)
    assert "cooldown" in why
    long_ago = NOW - timedelta(minutes=61)
    assert autotrade.refusal(_row("x"), now=NOW, window_open="08:30", window_close="14:30",
                             last_entry=long_ago) is None


# ---- arming -----------------------------------------------------------------

def _arm(client, op, **over):
    body = {"strategy": "super_signals", "tickers": "SPY,QQQ,SPX", "live": False,
            "buy_pct": 20, "tp_pct": 15, "sl_pct": 30, "tolerance_pct": 25,
            "min_contracts": 1, "delta_min": 0.35, "delta_max": 0.65,
            "signals": [PICK], "window_open": "08:30", "window_close": "14:30"}
    body.update(over)
    return client.post(f"{V1}/autotrade/start", json=body, headers=op.headers)


@pytest.mark.parametrize("over,why", [
    ({"signals": []}, "pick at least one signal type"),
    ({"signals": ["not a key"]}, "not a signal type"),
    ({"window_open": "14:30", "window_close": "08:30"}, "start before end"),
    ({"window_open": "8:30"}, "HH:MM"),
    ({"tickers": "SPY,$$$"}, "plain symbols"),
    ({"sl_pct": 100}, "stop"),
    ({"strategy": "hot_tickers"}, "unknown strategy"),
])
def test_arming_refuses_what_it_cannot_trade(client, alice, over, why):
    r = _arm(client, alice, **over)
    assert r.status_code == 409, r.text
    assert why in r.json()["detail"]


def test_status_offers_the_strategies_and_the_forms_defaults(client, alice):
    """Without these the 36 Trades sheet never rendered the form, and neither
    desk could show an armed watcher or reach its disarm button."""
    st = client.get(f"{V1}/autotrade/status", headers=alice.headers).json()
    assert st["active"] is False
    assert "super_signals" in st["strategies"]
    assert st["defaults"]["strategies"] == st["strategies"]
    assert st["defaults"]["tickers"] == "SPY,QQQ,SPX"


def test_arm_shows_armed_then_disarms(client, alice, feed, at):
    r = _arm(client, alice)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] is True and body["strategy"] == "super_signals"
    assert body["signals"] == [PICK] and body["window"] == "08:30-14:30"
    assert client.get(f"{V1}/autotrade/status", headers=alice.headers).json()["active"] is True
    assert _arm(client, alice).status_code == 409          # never two at once
    stopped = client.post(f"{V1}/autotrade/stop", headers=alice.headers).json()
    assert stopped["active"] is False and "defaults" in stopped


# ---- the tick: what actually trades ------------------------------------------

def test_the_backlog_at_arm_time_is_history_not_triggers(client, alice, feed, at):
    feed.rows = [_row("already-1", time="10:25"), _row("already-2", time="10:30")]
    w = _watcher(alice)
    day = autotrade._super_tick(w, clock.now(), None)
    assert day == date.today().isoformat()
    assert w.seen_ids == {"already-1", "already-2"}
    assert _positions(client, alice) == []
    autotrade._super_tick(w, clock.now(), day)             # still nothing to do
    assert _positions(client, alice) == []


def test_a_new_live_short_opens_one_managed_put(client, alice, feed, at):
    w = _watcher(alice)
    day = autotrade._super_tick(w, clock.now(), None)      # empty baseline
    feed.rows = [_row("sig-1", time="10:30")]
    autotrade._super_tick(w, clock.now(), day)

    [pos] = _positions(client, alice)
    assert pos["strategy"] == "Auto/super_signals"
    assert pos["option_type"] == "put" and pos["underlying"] == "SPY"
    assert pos["venue"] == "sandbox"
    assert w.placed == 1 and w.trades[0]["signal"] == PICK

    autotrade._super_tick(w, clock.now(), day)             # same row again
    assert len(_positions(client, alice)) == 1


def test_a_long_buys_a_call(client, alice, feed, at):
    w = _watcher(alice, signals=(PICK_LONG,))
    day = autotrade._super_tick(w, clock.now(), None)
    feed.rows = [_row("sig-long", key=PICK_LONG, ticker="QQQ", time="10:30")]
    autotrade._super_tick(w, clock.now(), day)
    [pos] = _positions(client, alice)
    assert pos["option_type"] == "call" and pos["underlying"] == "QQQ"


def test_types_and_tickers_not_picked_never_trade(client, alice, feed, at):
    w = _watcher(alice)
    day = autotrade._super_tick(w, clock.now(), None)
    feed.rows = [_row("other-type", key=PICK_LONG, time="10:30"),
                 _row("other-ticker", ticker="NVDA", time="10:30")]
    autotrade._super_tick(w, clock.now(), day)
    assert _positions(client, alice) == []


def test_one_ticker_is_entered_once_per_hour(client, alice, feed, at):
    w = _watcher(alice)
    day = autotrade._super_tick(w, clock.now(), None)
    feed.rows = [_row("first", time="10:30")]
    autotrade._super_tick(w, clock.now(), day)
    at(10, 37)
    feed.rows.append(_row("second", time="10:35"))
    autotrade._super_tick(w, clock.now(), day)
    assert len(_positions(client, alice)) == 1
    assert any("cooldown" in e["message"] for e in w.events)


def test_a_refused_entry_does_not_start_the_cooldown(client, alice, feed, at, fake_venue):
    """Nothing was bought, so nothing should lock the ticker out for an hour."""
    fake_venue.account_for_slug(alice.slug).option_buying_power = 0.0
    w = _watcher(alice)
    day = autotrade._super_tick(w, clock.now(), None)
    feed.rows = [_row("unaffordable", time="10:30")]
    autotrade._super_tick(w, clock.now(), day)
    assert _positions(client, alice) == []
    assert "SPY" not in w.last_entry
    assert any("sized to zero" in e["message"] for e in w.events)

    fake_venue.account_for_slug(alice.slug).option_buying_power = 10_000.0
    at(10, 37)
    feed.rows.append(_row("affordable", time="10:35"))
    autotrade._super_tick(w, clock.now(), day)
    assert len(_positions(client, alice)) == 1


def test_a_signal_already_acted_on_is_never_bought_twice(client, alice, feed, at):
    """The idempotency key is the signal id: a second watcher -- a re-arm after
    a restart, say -- that somehow judged the same row cannot buy it again."""
    first, second = _watcher(alice), _watcher(alice)
    d1 = autotrade._super_tick(first, clock.now(), None)
    d2 = autotrade._super_tick(second, clock.now(), None)
    feed.rows = [_row("shared", time="10:30")]
    autotrade._super_tick(first, clock.now(), d1)
    autotrade._super_tick(second, clock.now(), d2)
    assert len(_positions(client, alice)) == 1
    assert any("already acted on" in e["message"] for e in second.events)


@pytest.mark.parametrize("hh,mm,same_day", [(10, 32, True), (13, 5, False)])
def test_zero_dte_is_bought_only_before_the_cutoff(client, alice, feed, at, hh, mm, same_day):
    at(hh, mm)
    w = _watcher(alice, zero_dte=True)
    day = autotrade._super_tick(w, clock.now(), None)
    feed.rows = [_row("odte", time=f"{hh:02d}:{mm - 2:02d}")]
    autotrade._super_tick(w, clock.now(), day)
    [pos] = _positions(client, alice)
    assert (pos["expiration"] == date.today().isoformat()) is same_day


def test_a_desk_outage_is_said_once_and_trades_nothing(client, alice, feed, at):
    feed.down = desk.Unavailable(503, "the super signals service is not answering")
    w = _watcher(alice)
    autotrade._super_tick(w, clock.now(), None)
    autotrade._super_tick(w, clock.now(), None)
    lines = [e for e in w.events if "unavailable" in e["message"]]
    assert len(lines) == 1 and w.feed.startswith("unavailable")
    assert _positions(client, alice) == []


def test_a_desk_serving_another_day_trades_nothing(client, alice, feed, at):
    feed.date = (date.today() - timedelta(days=1)).isoformat()
    feed.rows = [_row("yesterday", time="10:30")]
    w = _watcher(alice)
    autotrade._super_tick(w, clock.now(), None)
    autotrade._super_tick(w, clock.now(), None)
    assert _positions(client, alice) == []
    assert "not today" in w.feed
