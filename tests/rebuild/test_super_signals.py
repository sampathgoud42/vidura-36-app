"""Super Signals: the desk reads the signal-agent project through its service.

What this holds:

* the proxy hands the service's answer through untouched, and forwards the
  session it was asked for;
* a report page comes back wrapped in JSON -- the desk's client refuses any
  other body -- with its HTML intact;
* a service that is down, slow or broken is reported as exactly that (503,
  504, 502), never as an empty board. "No signals today" and "the service is
  off" look identical on screen, which is how the research boards once
  rendered empty for weeks with no error anywhere (routers/research.py);
* a malformed date is refused here, before the service is asked at all,
  and so is a best-pairs minimum that is not a number in range.

No network: the service is replaced by a fake requests session.
"""

from __future__ import annotations

import pytest
import requests

from app.core.config import get_settings
from app.services import super_signals

V1 = "/api/v1/super-signals"

SESSION = {"date": "2026-09-24", "phase": "open",
           "totals": {"signals": 2, "target": 1, "stop": 0, "timeout": 0, "open": 1},
           "signals": [{"id": "gap|NFLX|open_drive|SHORT|2026-09-24 08:40", "ticker": "NFLX",
                        "direction": "SHORT", "outcome": "target"},
                       {"id": "poc|AMD|poc_250h|LONG|2026-09-24 09:10", "ticker": "AMD",
                        "direction": "LONG", "outcome": "open"}],
           "watchlist": [], "report": {"date": "2026-09-24", "available": False}}
REPORTS = {"latest": "2026-09-23",
           "reports": [{"date": "2026-09-23", "weekday": "Wed", "bytes": 792052}]}
RANK = {"date": "2026-09-24", "basis": "previous", "basis_date": "2026-09-23",
        "signals": [{"key": "poc|poc_48h|medium|SHORT", "rank": 4,
                     "verdict": {"level": "pos", "tag": "history agrees", "extra": 43}}],
        "excluded": [{"key": "levels|orb30_break||SHORT", "rank": 1,
                      "verdict": {"level": "neg", "tag": "history disagrees", "extra": 12}}]}
BEST = {"table": "best_ticker_signal_pairs", "session": "2026-09-24",
        "window": {"sessions": 30, "from": "2026-08-13", "to": "2026-09-24"},
        "filters": {"min_win_pct": None, "min_edge": None, "min_net_r": None},
        "total": 25, "count": 1,
        "pairs": [{"rank": 1, "signal": "poc · poc_72h [medium] · LONG", "ticker": "TSLA",
                   "type_key": "poc|poc_72h|medium|LONG", "edge": 70.1, "wins": 9, "losses": 1,
                   "timeouts": 1, "win_pct": 90.0, "net_r": 8.32,
                   "first_fired": "2026-08-13 08:45", "last_fired": "2026-09-21 14:15",
                   "fired_today": 0, "fired_yesterday": 0, "fired_past_week": 3,
                   "as_of": "2026-09-24", "updated_at": "2026-09-24 17:15:27"}]}
PAGE = "<!doctype html><title>Signal Desk 2026-09-23</title><main>report</main>"


class _Resp:
    def __init__(self, status: int = 200, body=None, text: str = ""):
        self.status_code = status
        self._body = body
        self.text = text
        self.reason = {200: "OK", 400: "Bad Request", 404: "Not Found"}.get(status, "Error")

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self):
        if self._body is None:
            raise ValueError("not JSON")
        return self._body


class FakeService:
    """Answers by path, records every call, or fails the way it is told to."""

    def __init__(self):
        self.calls: list[tuple[str, dict | None, float | None]] = []
        self.fail: Exception | None = None
        self.answers = {
            "/api/session": _Resp(body=SESSION),
            "/api/reports": _Resp(body=REPORTS),
            "/api/rank": _Resp(body=RANK),
            "/api/best-pairs": _Resp(body=BEST),
            "/reports/2026-09-23.html": _Resp(text=PAGE),
        }

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        if self.fail is not None:
            raise self.fail
        path = url.removeprefix(get_settings().super_signals_url.rstrip("/"))
        return self.answers.get(path, _Resp(404, {"detail": f"no such path: {path}"}))


@pytest.fixture()
def service(monkeypatch) -> FakeService:
    fake = FakeService()
    monkeypatch.setattr(super_signals, "_http", fake)
    return fake


def test_the_session_is_the_services_answer(client, alice, service):
    """Given the service answering for today,
    when an operator reads the session,
    then they get exactly that answer, and no date was imposed on the service."""
    r = client.get(f"{V1}/session", headers=alice.headers)
    assert r.status_code == 200
    assert r.json() == SESSION
    assert service.calls[0][1] is None


def test_a_requested_session_is_forwarded(client, alice, service):
    client.get(f"{V1}/session", params={"date": "2026-09-23"}, headers=alice.headers)
    assert service.calls[0][1] == {"date": "2026-09-23"}


@pytest.mark.parametrize("path", [f"{V1}/session?date=24-09-2026",
                                  f"{V1}/session?date=2026-09-24T00:00",
                                  f"{V1}/reports/not-a-date",
                                  f"{V1}/reports/2026-9-23"])
def test_a_malformed_date_never_reaches_the_service(client, alice, service, path):
    """Validated here: the service is not a place to discover bad input."""
    assert client.get(path, headers=alice.headers).status_code == 422
    assert service.calls == []


def test_the_ranking_is_passed_through_with_its_basis(client, alice, service):
    """The auto-trade form's list: the desk decides the ranking and which types
    history disagrees with; the proxy must not reorder, refilter or drop them."""
    r = client.get(f"{V1}/rank", params={"date": "2026-09-24"}, headers=alice.headers)
    assert r.status_code == 200
    assert r.json() == RANK
    assert service.calls[0][1] == {"date": "2026-09-24"}


def test_the_best_pairs_are_the_desks_list_untouched(client, alice, service):
    """Given no minimums,
    when an operator reads the best pairs,
    then they get the desk's whole list as it answered, and it was asked for no filter."""
    r = client.get(f"{V1}/best-pairs", headers=alice.headers)
    assert r.status_code == 200
    assert r.json() == BEST
    assert service.calls[0][1] is None


def test_the_minimums_are_forwarded_as_numbers(client, alice, service):
    """Only the minimums given go through, and as numbers: the desk filters."""
    client.get(f"{V1}/best-pairs", params={"min_win_pct": "80", "min_net_r": "-2.5"},
               headers=alice.headers)
    client.get(f"{V1}/best-pairs", params={"min_edge": 60, "min_win_pct": 100, "min_net_r": 5},
               headers=alice.headers)
    assert service.calls[0][1] == {"min_win_pct": 80.0, "min_net_r": -2.5}
    assert service.calls[1][1] == {"min_win_pct": 100.0, "min_edge": 60.0, "min_net_r": 5.0}


@pytest.mark.parametrize("query", ["min_win_pct=101", "min_win_pct=-1", "min_edge=100.5",
                                   "min_edge=abc", "min_net_r=nan", "min_net_r=inf",
                                   "min_net_r=1e9"])
def test_a_bad_minimum_never_reaches_the_service(client, alice, service, query):
    """A win rate or edge outside 0-100, or a net R that is not a real,
    sane number, is refused here: NaN would compare false and empty the list."""
    assert client.get(f"{V1}/best-pairs?{query}", headers=alice.headers).status_code == 422
    assert service.calls == []


def test_the_report_list_is_passed_through(client, alice, service):
    r = client.get(f"{V1}/reports", headers=alice.headers)
    assert r.status_code == 200
    assert r.json() == REPORTS


def test_a_report_page_comes_back_wrapped_in_json(client, alice, service):
    """Given a daily report on file,
    when an operator opens it,
    then the page arrives as a JSON string, byte for byte."""
    r = client.get(f"{V1}/reports/2026-09-23", headers=alice.headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {"date": "2026-09-23", "html": PAGE}


def test_a_missing_report_is_not_found_with_the_services_reason(client, alice, service):
    r = client.get(f"{V1}/reports/2026-01-02", headers=alice.headers)
    assert r.status_code == 404
    assert "2026-01-02" in r.json()["detail"]


@pytest.mark.parametrize("failure,status", [
    (requests.ConnectionError("refused"), 503),
    (requests.Timeout("slow"), 504),
])
def test_an_unreachable_service_is_never_an_empty_board(client, alice, service, failure, status):
    """Given the service down or hung,
    when an operator reads the session,
    then the answer is an error that says so -- not a 200 with no signals."""
    service.fail = failure
    r = client.get(f"{V1}/session", headers=alice.headers)
    assert r.status_code == status
    assert "super signals service" in r.json()["detail"]


def test_a_broken_service_is_a_bad_gateway(client, alice, service):
    service.answers["/api/session"] = _Resp(500, {"detail": "KeyError: 'date'"})
    r = client.get(f"{V1}/session", headers=alice.headers)
    assert r.status_code == 502
    assert "KeyError" in r.json()["detail"]


def test_the_service_is_always_asked_with_a_timeout(client, alice, service):
    """A hung service must not hold a request thread forever."""
    client.get(f"{V1}/session", headers=alice.headers)
    client.get(f"{V1}/reports", headers=alice.headers)
    client.get(f"{V1}/reports/2026-09-23", headers=alice.headers)
    assert [c[2] for c in service.calls] == [get_settings().super_signals_timeout_s] * 3


def test_every_operator_reads_the_same_desk(client, alice, bob, service):
    """Market data, not operator data: two operators see one set of signals."""
    a = client.get(f"{V1}/session", headers=alice.headers).json()
    b = client.get(f"{V1}/session", headers=bob.headers).json()
    assert a == b == SESSION
