"""Which stocks BreakoutRadar scans: live lists first, then the last saved live
copy, then the bundled snapshot -- and every answer says which it used.

The conftest makes every live fetch fail and points var/ at a scratch folder,
so each test says what the network does.
"""

from __future__ import annotations

import json

import pytest

from app.domains.trading.market import universes


def live(lists):
    def fetch(name):
        if name not in lists:
            raise ConnectionError("offline")
        return universes._valid(name, lists[name])
    return fetch


SP = [f"S{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(500)]
NDX = SP[:60] + [f"N{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(41)]


def test_offline_with_nothing_saved_uses_the_bundled_snapshot():
    us = universes.for_market("US")
    assert us["name"] == "S&P 500 + Nasdaq-100"
    assert us["lists"]["sp500"]["source"] == "snapshot"
    assert us["count"] > 480 and "AAPL" in us["symbols"] and "BRK.B" in us["symbols"]
    assert len(us["symbols"]) == len(set(us["symbols"]))       # the overlap counted once
    india = universes.for_market("INDIA")
    assert india["lists"]["nifty500"]["source"] == "snapshot"
    assert "RELIANCE" in india["symbols"] and "M&M" in india["symbols"]


def test_a_live_list_is_used_and_saved_for_the_next_offline_start(monkeypatch):
    monkeypatch.setattr(universes, "_fetch_live", live({"sp500": SP, "nasdaq100": NDX}))
    got = universes.for_market("US")
    assert got["lists"]["sp500"]["source"] == "live"
    assert got["count"] == 500 + 41

    universes.reset()
    monkeypatch.setattr(universes, "_fetch_live", live({}))
    again = universes.members("sp500")
    assert again["source"] == "saved" and again["symbols"] == SP


def test_a_short_saved_list_is_not_believed(monkeypatch):
    """A truncated copy on disk must not become a half-index scan."""
    saved = universes._saved_path("sp500")
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_text(json.dumps({"symbols": SP[:120], "source": "live", "as_of": "2026-01-01"}))
    monkeypatch.setattr(universes, "_fetch_live", live({}))
    assert universes.members("sp500")["source"] == "snapshot"


def test_a_failed_fetch_is_not_retried_on_every_scan(monkeypatch):
    asked = []

    def fetch(name):
        asked.append(name)
        raise ConnectionError("offline")

    monkeypatch.setattr(universes, "_fetch_live", fetch)
    universes.members("nifty500")
    universes.members("nifty500")
    assert asked == ["nifty500"]


@pytest.mark.parametrize("name,good,bad", [
    ("sp500", ["BRK.B", "AAPL", "BF.B"], ["", "TOOLONGX", "12AB", "aapl!"]),
    ("nifty500", ["M&M", "BAJAJ-AUTO", "3MINDIA"], ["", "RELIANCE.NS", "A B"]),
])
def test_symbols_are_checked_before_they_are_scanned(name, good, bad):
    assert universes._valid(name, good + bad) == good
