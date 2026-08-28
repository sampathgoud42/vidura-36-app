"""Trade ledger LIVE/PAPER classification and the live-by-default filter.

The ledger must default to real-money trades only — a paper run's P&L sitting
in the same table as live results is how a session gets misread. `mode=all`
opens it up for analysis.

Third state: btc15 v2/v3/v4 write paper AND live rows to one CSV with no
distinguishing field (BOT_CSV_PATH ignores DRY_RUN), so their mode is
genuinely unknown. Those are NULL, not False — calling them paper would hide
real trades, and calling them live would overstate real P&L. They surface
only under mode=all.
"""

from __future__ import annotations

import pytest


def _trade(**over) -> dict:
    body = {
        "bot_key": "sports",
        "ticker": "KXATP-TEST",
        "side": "yes",
        "action": "buy",
        "contracts": 5,
        "price_cents": 55,
        "status": "won",
        "pnl_usd": 3.0,
        "is_mock": False,
    }
    body.update(over)
    return body


@pytest.fixture
def ledger(client, user):
    uid = user["user_id"]
    client.post(f"/api/v1/users/{uid}/trades", json=_trade(ticker="LIVE-1", is_mock=False))
    client.post(f"/api/v1/users/{uid}/trades", json=_trade(ticker="LIVE-2", is_mock=False))
    client.post(f"/api/v1/users/{uid}/trades", json=_trade(ticker="PAPER-1", is_mock=True))
    return uid


def _tickers(page) -> set[str]:
    return {t["ticker"] for t in page["items"]}


def test_live_is_the_default(client, ledger):
    page = client.get("/api/v1/bots/sports/trades", params={"user_id": ledger}).json()
    assert _tickers(page) == {"LIVE-1", "LIVE-2"}
    assert page["total"] == 2


def test_paper_only(client, ledger):
    page = client.get(
        "/api/v1/bots/sports/trades", params={"user_id": ledger, "mode": "paper"}
    ).json()
    assert _tickers(page) == {"PAPER-1"}


def test_all_shows_everything(client, ledger):
    page = client.get(
        "/api/v1/bots/sports/trades", params={"user_id": ledger, "mode": "all"}
    ).json()
    assert _tickers(page) == {"LIVE-1", "LIVE-2", "PAPER-1"}


def test_is_live_is_exposed_on_every_row(client, ledger):
    page = client.get(
        "/api/v1/bots/sports/trades", params={"user_id": ledger, "mode": "all"}
    ).json()
    by_ticker = {t["ticker"]: t["is_live"] for t in page["items"]}
    assert by_ticker["LIVE-1"] is True
    assert by_ticker["PAPER-1"] is False


def test_recorded_trade_derives_is_live_from_is_mock(client, user):
    uid = user["user_id"]
    live = client.post(f"/api/v1/users/{uid}/trades", json=_trade(is_mock=False)).json()
    paper = client.post(f"/api/v1/users/{uid}/trades", json=_trade(is_mock=True)).json()
    assert live["is_live"] is True
    assert paper["is_live"] is False


def test_an_explicit_is_live_wins_over_the_derivation(client, user):
    uid = user["user_id"]
    t = client.post(
        f"/api/v1/users/{uid}/trades", json=_trade(is_mock=True, is_live=True)
    ).json()
    assert t["is_live"] is True


def test_unknown_mode_rows_are_hidden_from_live_and_paper(client, user, db_session):
    """A btc15 v2 row (mode unknown) must not be counted as either."""
    from app.models import Trade

    db_session.add(
        Trade(
            user_id=user["user_id"], bot_key="btc15", bot_version="v2",
            ticker="UNKNOWN-1", contracts=1, status="won", is_mock=True, is_live=None,
        )
    )
    db_session.commit()

    uid = user["user_id"]
    live = client.get("/api/v1/bots/btc/trades", params={"user_id": uid}).json()
    paper = client.get(
        "/api/v1/bots/btc/trades", params={"user_id": uid, "mode": "paper"}
    ).json()
    every = client.get(
        "/api/v1/bots/btc/trades", params={"user_id": uid, "mode": "all"}
    ).json()

    assert "UNKNOWN-1" not in _tickers(live), "unverified row leaked into the LIVE ledger"
    assert "UNKNOWN-1" not in _tickers(paper)
    assert "UNKNOWN-1" in _tickers(every), "unknown row is unreachable — data hidden entirely"


def test_btc_ledger_defaults_to_live_too(client, user):
    uid = user["user_id"]
    client.post(f"/api/v1/users/{uid}/trades", json=_trade(bot_key="btc15", ticker="B-LIVE", is_mock=False))
    client.post(f"/api/v1/users/{uid}/trades", json=_trade(bot_key="btc15", ticker="B-PAPER", is_mock=True))
    page = client.get("/api/v1/bots/btc/trades", params={"user_id": uid}).json()
    assert _tickers(page) == {"B-LIVE"}


def test_bad_mode_is_rejected(client, user):
    r = client.get(
        "/api/v1/bots/sports/trades", params={"user_id": user["user_id"], "mode": "nonsense"}
    )
    assert r.status_code == 422
