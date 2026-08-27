"""Read endpoints must mirror the bots' trade CSVs before answering.

The bug: the trades table is a mirror of CSVs the bots own, but it was only
refreshed by POST /sync-trades — a button click. A live tennis position sat
open for hours on 2026-07-29 while Active Bets showed nothing, because
nothing pulled the CSV in.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.services import ingest

CSV_HEADER = (
    "ts_epoch,ts,sport,ticker,name,side,situation,confidence,reason,context,"
    "model_wp,signal_bid,buy_price,fill_price,contracts,tp_price,stop_price,"
    "pv_entry,status,ts_close,pv_close,realized_pnl,pv_delta_pct\n"
)


def _row(ticker: str, status: str, epoch: float, pnl: str = "") -> str:
    closed = "2026-07-29 13:53:55 CST" if status == "CLOSED" else ""
    return (
        f"{epoch},2026-07-29 13:25:08 CST,tennis,{ticker},Someone,yes,F3,high,"
        f"reason,,,51,51,49,15,97,31,103.36,{status},{closed},110.41,{pnl},\n"
    )


@pytest.fixture
def user_with_csv(client, tmp_path):
    """A user whose folder holds a sports trade CSV with one open position."""
    root = tmp_path / "cust"
    (root / "trade_history").mkdir(parents=True)
    csv = root / "trade_history" / "trade_history_main.csv"
    csv.write_text(
        CSV_HEADER
        + _row("KXATP-OPEN-ONE", "OPEN", 1785349498.4)
        + _row("KXITF-CLOSED-A", "CLOSED", 1785350251.0, pnl="5.7"),
        encoding="utf-8",
    )
    u = client.post(
        "/api/v1/users",
        json={"username": "mirror", "user_root_folder": str(root)},
    ).json()
    ingest._last_sync.clear()   # a fresh user must not inherit another's TTL
    return u, csv


def test_active_bets_shows_an_open_position_without_a_manual_sync(client, user_with_csv):
    user, _ = user_with_csv
    r = client.get("/api/v1/bots/sports/active-bets", params={"user_id": user["user_id"]})
    assert r.status_code == 200, r.text
    tickers = [t["ticker"] for t in r.json()]
    assert "KXATP-OPEN-ONE" in tickers, "the open position never reached the mirror"


def test_trades_endpoint_picks_up_rows_written_after_the_first_read(client, user_with_csv):
    user, csv = user_with_csv
    first = client.get("/api/v1/bots/sports/trades", params={"user_id": user["user_id"]}).json()
    before = first["total"]

    with csv.open("a", encoding="utf-8") as fh:
        fh.write(_row("KXITF-NEW-LATER", "OPEN", 1785350999.0))

    ingest._last_sync.clear()  # simulate the TTL having elapsed
    after = client.get("/api/v1/bots/sports/trades", params={"user_id": user["user_id"]}).json()
    assert after["total"] == before + 1
    assert any(t["ticker"] == "KXITF-NEW-LATER" for t in after["items"])


def test_performance_reflects_the_csv_too(client, user_with_csv):
    user, _ = user_with_csv
    r = client.get("/api/v1/bots/sports/performance", params={"user_id": user["user_id"]})
    assert r.status_code == 200
    assert r.json()["trades"] >= 2


def test_ttl_prevents_reparsing_on_every_poll(client, user_with_csv, monkeypatch):
    user, _ = user_with_csv
    calls = []
    real = ingest.sync_trades
    monkeypatch.setattr(
        ingest, "sync_trades", lambda *a, **k: (calls.append(1), real(*a, **k))[1]
    )
    ingest._last_sync.clear()
    for _ in range(5):
        client.get("/api/v1/bots/sports/active-bets", params={"user_id": user["user_id"]})
    assert len(calls) == 1, f"TTL did not hold: {len(calls)} syncs for 5 polls"


def test_auto_sync_is_non_fatal_when_the_csv_is_unreadable(client, user_with_csv, monkeypatch):
    """A bad CSV must still serve whatever is already mirrored."""
    user, _ = user_with_csv
    client.get("/api/v1/bots/sports/active-bets", params={"user_id": user["user_id"]})

    def boom(*a, **k):
        raise OSError("file locked by the bot")

    monkeypatch.setattr(ingest, "sync_trades", boom)
    ingest._last_sync.clear()
    r = client.get("/api/v1/bots/sports/active-bets", params={"user_id": user["user_id"]})
    assert r.status_code == 200, "a CSV failure must not break the read"
    assert any(t["ticker"] == "KXATP-OPEN-ONE" for t in r.json())


def test_auto_sync_respects_the_kill_switch(client, user_with_csv, monkeypatch):
    from app.core.config import get_settings

    user, _ = user_with_csv
    settings = get_settings()
    monkeypatch.setattr(settings, "trades_auto_sync", False)
    ingest._last_sync.clear()
    r = client.get("/api/v1/bots/sports/active-bets", params={"user_id": user["user_id"]})
    assert r.status_code == 200
    assert r.json() == [], "auto-sync ran despite being disabled"


def test_unknown_user_does_not_error_the_read(client):
    r = client.get("/api/v1/bots/sports/active-bets", params={"user_id": "nope"})
    assert r.status_code == 200
    assert r.json() == []
