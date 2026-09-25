"""The managed-positions list, as the desks ask for it.

Both desks filter with the words on their chips -- "active", "all", "tp_filled",
"sl_sold", "closed" -- and ask for marks. Taken literally, "all" and "active"
matched no status at all, so every managed position, auto-trade entries
included, disappeared from both boards while the account showed the money in
them. What this holds:

* each chip word selects what it says, and exact statuses still work;
* marks=true prices every working position at the current bid -- the MARK and
  P&L columns -- and a venue that cannot quote leaves them empty rather than
  failing the list.
"""

from __future__ import annotations

import uuid

import pytest

from app.domains.trading.execution import venue
from app.domains.trading.models import Position
from app.platform.db.session import session_scope

OPEN = "/api/v1/tradier/positions"
BUY = {"symbol": "SPY", "side": "call", "buy_pct": 10, "tp_pct": 15, "sl_pct": 30, "live": False}


def _open(client, op, symbol):
    r = client.post(OPEN, json={**BUY, "symbol": symbol},
                    headers={**op.headers, "Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 200, r.text
    return r.json()


def _set_status(pid, status, **fields):
    with session_scope() as db:
        pos = db.get(Position, pid)
        pos.status = status
        for k, v in fields.items():
            setattr(pos, k, v)


def _list(client, op, **params):
    r = client.get(OPEN, params=params, headers=op.headers)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture()
def book(client, alice):
    """One working, one stopped out, one closed."""
    working, stopped, closed = (_open(client, alice, s) for s in ("SPY", "QQQ", "IWM"))
    _set_status(working["id"], "open", entry_price=1.10)    # filled, as the monitor records it
    _set_status(stopped["id"], "sl_filled")
    _set_status(closed["id"], "closed")
    return {"working": working, "stopped": stopped, "closed": closed}


@pytest.mark.parametrize("word,expect", [
    ("all", {"working", "stopped", "closed"}),
    ("active", {"working"}),
    ("sl_sold", {"stopped"}),
    ("sl_filled", {"stopped"}),
    ("closed", {"closed"}),
    ("tp_filled", set()),
])
def test_each_filter_word_selects_what_it_says(client, alice, book, word, expect):
    page = _list(client, alice, status=word, venue="all")
    got = {name for name, pos in book.items() if pos["id"] in {p["id"] for p in page["items"]}}
    assert got == expect
    assert page["total"] == len(expect)


def test_no_status_is_every_position(client, alice, book):
    assert _list(client, alice)["total"] == 3


def test_marks_price_working_positions_at_the_bid(client, alice, book, monkeypatch):
    working = book["working"]
    asked = []

    def quotes(symbols, *, cred, sandbox=True):
        asked.append(list(symbols))
        return [{"symbol": s, "bid": 1.30} for s in symbols]
    monkeypatch.setattr(venue, "quotes", quotes)

    items = {p["id"]: p for p in _list(client, alice, status="all", marks="true")["items"]}
    assert asked == [[working["occ_symbol"]]]           # one call, working positions only
    row = items[working["id"]]
    assert row["live_bid"] == 1.30
    assert row["live_pnl_usd"] == round((1.30 - row["entry_price"]) * row["contracts"] * 100, 2)
    assert "live_bid" not in items[book["closed"]["id"]]


def test_a_venue_that_cannot_quote_leaves_the_marks_empty(client, alice, book, monkeypatch):
    def down(*a, **k):
        raise ConnectionError("venue unreachable")
    monkeypatch.setattr(venue, "quotes", down)
    page = _list(client, alice, status="active", marks="true")
    assert [p["id"] for p in page["items"]] == [book["working"]["id"]]
    assert "live_bid" not in page["items"][0]
