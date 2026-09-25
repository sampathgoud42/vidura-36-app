"""The best_pairs auto-trade strategy: a live signal trades only on its pair.

A best pair is a signal type with a record on ONE ticker (the daily report's
"Best ticker + signal pairs", /super-signals/best-pairs), so what this holds:

* a new live signal buys only when its type AND its ticker are a picked pair,
  a CALL for a LONG and a PUT for a SHORT -- the pair's type on another ticker,
  or another type on the pair's ticker, never trades;
* arming refuses a pair that is malformed or no longer on the desk's list,
  and refuses outright when the desk cannot say what the list is;
* the pairs name their own tickers -- the form's ticker field plays no part;
* it shares super_signals' idempotency key, so a signal either strategy has
  acted on is never bought again by the other.

Every other rule (live only, open, fresh, in the window, one entry per ticker
per hour) is super_signals' own code and is held by its tests.
"""

from __future__ import annotations

from datetime import date, datetime
from datetime import time as dtime

import pytest

from app.domains.trading.execution import autotrade
from app.domains.trading.risk import clock
from app.services import super_signals as desk

V1 = "/api/v1/tradier"
LONG_KEY = "poc|poc_72h|medium|LONG"
SHORT_KEY = "reversion|vwap_band_fade||SHORT"
LISTED = [{"type_key": LONG_KEY, "ticker": "TSLA"}, {"type_key": SHORT_KEY, "ticker": "MU"}]


def _row(sid, *, key=LONG_KEY, ticker="TSLA", time="10:30", source="live", outcome="open"):
    agent, setup, grade, direction = key.split("|")
    return {"id": sid, "agent": agent, "setup": setup, "grade": grade,
            "direction": direction, "ticker": ticker, "time": time,
            "source": source, "outcome": outcome}


class Desk:
    """The signal desk's /api/session and /api/best-pairs, as the app sees them."""

    def __init__(self):
        self.rows: list[dict] = []
        self.pairs: list[dict] = list(LISTED)
        self.down: desk.Unavailable | None = None

    def get_json(self, path, params=None):
        if self.down is not None:
            raise self.down
        if path == "/api/best-pairs":
            return {"session": date.today().isoformat(), "total": len(self.pairs),
                    "count": len(self.pairs), "pairs": list(self.pairs)}
        assert path == "/api/session"
        return {"date": date.today().isoformat(), "signals": list(self.rows)}


@pytest.fixture()
def feed(monkeypatch) -> Desk:
    d = Desk()
    monkeypatch.setattr(desk, "get_json", d.get_json)
    return d


@pytest.fixture()
def at(monkeypatch):
    """Pin the desk clock to today, 10:32 CST (see test_autotrade_super_signals)."""
    now = datetime.combine(date.today(), dtime(10, 32), tzinfo=clock.DESK_TZ)
    monkeypatch.setattr(clock, "now", lambda: now)
    return now


def _watcher(op, *, strategy="best_pairs", pairs=((LONG_KEY, "TSLA"), (SHORT_KEY, "MU")),
             signals=(), tickers=None):
    pairs = set(pairs)
    return autotrade.Watcher(
        tenant_id=op.tenant_id, tickers=list(tickers or sorted({t for _, t in pairs})),
        strategy=strategy, live=False, buy_pct=20.0, tp_pct=15.0, sl_pct=30.0,
        tolerance_pct=25.0, min_contracts=1, delta_min=0.35, delta_max=0.65,
        armed_at=clock.now(), signals=list(signals), pairs=pairs,
        window_open="08:30", window_close="14:30")


def _positions(client, op):
    r = client.get(f"{V1}/positions", headers=op.headers)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _arm(client, op, **over):
    body = {"strategy": "best_pairs", "tickers": "SPY,QQQ,SPX", "live": False,
            "buy_pct": 20, "tp_pct": 15, "sl_pct": 30, "tolerance_pct": 25,
            "min_contracts": 1, "delta_min": 0.35, "delta_max": 0.65,
            "pairs": LISTED, "window_open": "08:30", "window_close": "14:30"}
    body.update(over)
    return client.post(f"{V1}/autotrade/start", json=body, headers=op.headers)


# ---- arming -----------------------------------------------------------------

def test_the_arm_form_is_offered_best_pairs(client, alice):
    st = client.get(f"{V1}/autotrade/status", headers=alice.headers).json()
    assert "best_pairs" in st["strategies"]
    assert st["defaults"]["strategies"] == st["strategies"]


@pytest.mark.parametrize("over,why", [
    ({"pairs": []}, "pick at least one best pair"),
    ({"pairs": [{"type_key": "not a key", "ticker": "TSLA"}]}, "not a signal type"),
    ({"pairs": [{"type_key": LONG_KEY, "ticker": "$$$"}]}, "plain symbol"),
    ({"pairs": [{"type_key": LONG_KEY, "ticker": "NVDA"}]}, "no longer on the best-pairs list"),
    ({"window_open": "14:30", "window_close": "08:30"}, "start before end"),
    ({"sl_pct": 100}, "stop"),
])
def test_arming_refuses_a_pair_it_cannot_trade(client, alice, feed, over, why):
    r = _arm(client, alice, **over)
    assert r.status_code == 409, r.text
    assert why in r.json()["detail"]


def test_a_desk_that_cannot_say_what_the_pairs_are_refuses_the_arm(client, alice, feed):
    feed.down = desk.Unavailable(503, "the super signals service is not answering")
    r = _arm(client, alice)
    assert r.status_code == 409
    assert "cannot confirm the best pairs" in r.json()["detail"]


def test_the_pairs_name_the_tickers_and_the_form_field_plays_no_part(client, alice, feed, at):
    r = _arm(client, alice, tickers="SPY")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] is True and body["strategy"] == "best_pairs"
    assert body["tickers"] == "MU,TSLA"
    assert body["pairs"] == sorted(LISTED, key=lambda p: (p["type_key"], p["ticker"]))
    stopped = client.post(f"{V1}/autotrade/stop", headers=alice.headers).json()
    assert stopped["active"] is False


# ---- the tick: what actually trades ------------------------------------------

def test_a_live_signal_on_a_pair_buys_in_its_direction(client, alice, feed, at):
    w = _watcher(alice)
    day = autotrade._super_tick(w, clock.now(), None)      # empty baseline
    feed.rows = [_row("tsla-long", key=LONG_KEY, ticker="TSLA"),
                 _row("mu-short", key=SHORT_KEY, ticker="MU")]
    autotrade._super_tick(w, clock.now(), day)

    got = {p["underlying"]: p for p in _positions(client, alice)}
    assert set(got) == {"TSLA", "MU"}
    assert got["TSLA"]["option_type"] == "call" and got["MU"]["option_type"] == "put"
    assert {p["strategy"] for p in got.values()} == {"Auto/best_pairs"}
    assert w.placed == 2


def test_a_pairs_type_elsewhere_or_another_type_on_its_ticker_never_trades(client, alice, feed, at):
    w = _watcher(alice)
    day = autotrade._super_tick(w, clock.now(), None)
    feed.rows = [_row("right-type-wrong-ticker", key=LONG_KEY, ticker="MU"),
                 _row("wrong-type-right-ticker", key=SHORT_KEY, ticker="TSLA"),
                 _row("on-no-pair", key=LONG_KEY, ticker="SPY")]
    autotrade._super_tick(w, clock.now(), day)
    assert _positions(client, alice) == []


def test_the_backlog_at_arm_time_is_history_not_triggers(client, alice, feed, at):
    feed.rows = [_row("already", key=LONG_KEY, ticker="TSLA")]
    w = _watcher(alice)
    day = autotrade._super_tick(w, clock.now(), None)
    autotrade._super_tick(w, clock.now(), day)
    assert _positions(client, alice) == []


def test_a_signal_super_signals_bought_is_not_bought_again(client, alice, feed, at):
    """One signal, one attempt, whichever strategy armed first -- a switch from
    super_signals to best_pairs mid-session cannot double a position."""
    sup = _watcher(alice, strategy="super_signals", signals=(LONG_KEY,), tickers=("TSLA",))
    best = _watcher(alice)
    d1 = autotrade._super_tick(sup, clock.now(), None)
    d2 = autotrade._super_tick(best, clock.now(), None)
    feed.rows = [_row("both-want-it", key=LONG_KEY, ticker="TSLA")]
    autotrade._super_tick(sup, clock.now(), d1)
    autotrade._super_tick(best, clock.now(), d2)
    [pos] = _positions(client, alice)
    assert pos["strategy"] == "Auto/super_signals"
    assert any("already acted on" in e["message"] for e in best.events)
