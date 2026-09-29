"""tools/ema_screener.py: the Best Bets screen in a terminal.

What this holds, with Tradier replaced by a fake HTTP session (no network):

* it asks Tradier exactly what the desk asks -- 15-minute bars, the regular
  session only, 40 days back -- with the Bearer header from CONFIG;
* it prints both strategy tables, and says which symbols it could not screen
  and why, instead of dropping them;
* a 429 is waited out, for as long as X-Ratelimit-Expiry says, and retried;
* a refused token stops the run (exit 3), and no token at all never calls out
  (exit 2);
* Tradier's null `series` and its one-bar-as-an-object quirk are both read.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tests.rebuild import synthetic

TOOL = Path(__file__).resolve().parents[2] / "tools" / "ema_screener.py"


@pytest.fixture()
def cli():
    spec = importlib.util.spec_from_file_location("ema_screener_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Resp:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}
        self.text = json.dumps(body) if body is not None else ""

    def json(self):
        return self._body


class FakeTradier:
    """Answers /markets/timesales from a script of responses per symbol."""

    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        queue = self.script.get(params["symbol"], [])
        return queue.pop(0) if queue else _Resp(body={"series": None})


def ok(bars):
    return _Resp(body={"series": {"data": bars}})


@pytest.fixture()
def fake(cli, monkeypatch):
    def install(script):
        tradier = FakeTradier(script)
        monkeypatch.setattr(cli.requests.Session, "get",
                            lambda self, url, params=None, timeout=None:
                            tradier.get(url, params, timeout))
        monkeypatch.setattr(cli.time, "sleep", lambda s: tradier.calls.append({"slept": s}))
        monkeypatch.setitem(cli.CONFIG["api"]["headers"], "Authorization", "Bearer test-token")
        return tradier
    return install


def test_no_token_never_calls_out(cli, monkeypatch, capsys):
    monkeypatch.setitem(cli.CONFIG["api"]["headers"], "Authorization", "Bearer <ACCESS_TOKEN>")
    assert cli.main(["--symbols", "AAPL", "--no-fundamentals"]) == 2
    assert "TRADIER_ACCESS_TOKEN" in capsys.readouterr().err


def test_it_asks_for_what_the_desk_asks_for(cli, fake):
    tradier = fake({"DIP": [ok(synthetic.crash_then(0.02))]})
    assert cli.main(["--symbols", "DIP", "--no-fundamentals", "--json"]) == 0
    call = next(c for c in tradier.calls if "url" in c)
    assert call["url"] == "https://api.tradier.com/v1/markets/timesales"
    assert call["params"]["interval"] == "15min"
    assert call["params"]["session_filter"] == "open"
    assert call["params"]["start"].endswith(" 00:00") and len(call["params"]["start"]) == 16


def test_both_tables_print_and_the_unscreenable_are_named(cli, fake, capsys):
    fake({"DIP": [ok(synthetic.crash_then(0.02))], "CROSS": [ok(synthetic.cross(1))],
          "NODATA": [_Resp(body={"series": None})]})
    assert cli.main(["--symbols", "DIP,CROSS,NODATA", "--no-fundamentals"]) == 0
    out = capsys.readouterr().out
    a, b = out.split("Strategy B")
    assert "Strategy A" in a and "| DIP" in a and "CROSS" not in a
    assert "| CROSS" in b and "1 candle ago" in b
    assert "Not screened (1):" in out and "NODATA" in out and "four-hour bars" in out
    assert "Est. days to catch" in a and " d / " in a


def test_a_429_is_waited_out_until_the_window_resets(cli, fake, monkeypatch):
    monkeypatch.setattr(cli.time, "time", lambda: 1000.0)
    limited = _Resp(429, {"fault": "quota"},
                    {"X-Ratelimit-Available": "0", "X-Ratelimit-Expiry": "1030000"})
    tradier = fake({"DIP": [limited, ok(synthetic.crash_then(0.02))]})
    assert cli.main(["--symbols", "DIP", "--no-fundamentals", "--json"]) == 0
    waits = [c["slept"] for c in tradier.calls if "slept" in c]
    assert any(w == pytest.approx(30.0) for w in waits), waits
    assert sum(1 for c in tradier.calls if "url" in c) == 2


def test_a_refused_token_stops_the_run(cli, fake, capsys):
    fake({"AAPL": [_Resp(401, {"fault": "invalid token"})]})
    assert cli.main(["--symbols", "AAPL,MSFT", "--no-fundamentals"]) == 3
    assert "refused the token" in capsys.readouterr().err


def test_one_bar_sent_as_an_object_is_still_a_bar(cli, fake):
    tradier = fake({})
    one = synthetic.flat(10.0, days=1)[0]
    client = cli.Tradier({**cli.CONFIG["api"], "headers": {"Authorization": "Bearer t"}})
    tradier.script["X"] = [_Resp(body={"series": {"data": one}})]
    assert client.timesales("X", interval="15min", start="2026-09-01",
                            session_filter="open") == [one]


def test_a_4xx_other_than_auth_is_not_retried(cli, fake, capsys):
    tradier = fake({"BAD": [_Resp(400, {"fault": "bad symbol"})]})
    assert cli.main(["--symbols", "BAD", "--no-fundamentals"]) == 0
    assert sum(1 for c in tradier.calls if "url" in c) == 1
    assert "HTTP 400" in capsys.readouterr().out
