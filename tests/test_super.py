from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.services import super_research as svc

# super_dir fixture + CSV headers live in conftest.py (shared with
# test_super_regen.py)


def test_state_shape_matches_vite_contract(client, super_dir):
    resp = client.get("/api/v1/super/state")
    assert resp.status_code == 200
    state = resp.json()
    assert state["abookOnTop"] is True
    assert {c["key"] for c in state["categories"]} == {"etf", "crypto"}

    etf = next(c for c in state["categories"] if c["key"] == "etf")
    assert etf["session"] == "rth"
    assert etf["live"] is False and etf["pid"] is None
    spy = etf["tickers"][0]
    assert spy["enabled"] is True and spy["live"] is False
    # worker rows: newest first, ALL STRING values
    assert spy["rows"][0]["logged_at_cst"] == "2026-07-27 10:35:26"
    assert spy["rows"][0]["signal_price"] == "738.50"
    assert isinstance(spy["rows"][0]["volume"], str)

    crypto = next(c for c in state["categories"] if c["key"] == "crypto")
    assert crypto["tickers"][0]["rows"] == []  # disabled -> no rows

    # abook: only book A rows from enabled tickers, with src/cat added
    assert all(r["book"] == "A" for r in state["abook"])
    assert state["abook"][0]["src"] == "SPY" and state["abook"][0]["cat"] == "etf"

    # central feeds sorted desc, strings preserved
    assert state["aFeed"][0]["ticker"] == "GLD"
    assert state["aFeed"][0]["eng_hot"] == "4"
    assert state["aFeed"][0]["hot"] == ""
    assert state["bFeed"][0]["book"] == "B"

    # econ + gex verbatim
    assert state["econ"]["date"] == "2026-07-27"
    assert state["gex"]["tickers"]["SPY"]["regime"] == "negative_gamma"


def test_state_all_merges_archive(client, super_dir):
    base = client.get("/api/v1/super/state").json()
    assert len(base["aFeed"]) == 2
    full = client.get("/api/v1/super/state?all=1").json()
    assert len(full["aFeed"]) == 3
    assert any(r["eng_hot"] == "5" for r in full["aFeed"])  # legacy archive row


def test_state_config_unreadable_error_shape(client, super_dir):
    (super_dir / "super_research.config").write_text("{not json")
    state = client.get("/api/v1/super/state").json()
    assert set(state) == {"error"}
    assert state["error"].startswith("config unreadable:")


def test_config_toggle_roundtrip(client, super_dir):
    resp = client.post("/api/v1/super/config", json={"enabled": {"spy": False, "btc": True}})
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    cfg = client.get("/api/v1/super/config").json()
    tickers = {
        t["id"]: t["enabled"]
        for c in cfg["categories"].values()
        for t in c["tickers"]
    }
    assert tickers == {"spy": False, "btc": True}
    # preserved untouched keys
    assert cfg["_comment"] == "test"
    # state reflects it: spy disabled -> no rows
    state = client.get("/api/v1/super/state").json()
    etf = next(c for c in state["categories"] if c["key"] == "etf")
    assert etf["tickers"][0]["rows"] == []


def test_compat_aliases_match_v1(client, super_dir):
    v1 = client.get("/api/v1/super/state").json()
    compat = client.get("/api/super/state").json()
    assert compat == v1
    resp = client.post("/api/super/config", json={"enabled": {"spy": True}})
    assert resp.json() == {"ok": True}


def test_gex_and_econ_endpoints(client, super_dir):
    gex = client.get("/api/v1/super/gex").json()
    assert gex["tickers"]["SPY"]["net_gex"] == -9178182877
    econ = client.get("/api/v1/super/econ").json()
    assert econ["high_impact"] is False

    # Detached serving: deleting the source file does NOT lose the data —
    # the DB snapshot keeps answering.
    (super_dir / "gex_daily.json").unlink()
    resp = client.get("/api/v1/super/gex")
    assert resp.status_code == 200
    assert resp.json()["tickers"]["SPY"]["net_gex"] == -9178182877


def test_sync_and_query_signals(client, super_dir):
    resp = client.post("/api/v1/super/sync")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["signals"]["inserted"] == 4  # 2 A + 1 B + 1 archive A
    assert body["workers"]["inserted"] == 2  # spy worker CSV rows
    assert body["snapshots"]["upserted"] == 3  # gex + econ + gex_raw_spy

    page = client.get("/api/v1/super/signals", params={"book": "a"}).json()
    assert page["total"] == 4  # 3 central A + 1 worker A row
    assert page["items"][0]["ticker"] == "GLD"
    assert page["items"][0]["grade"] == "4"
    assert page["items"][0]["raw"]["outcome"] == "stop"

    hot = client.get("/api/v1/super/signals", params={"grade_min": 4}).json()
    assert hot["total"] == 2  # eng_hot 4 + legacy 5; ungraded worker rows excluded

    # idempotent across every source
    again = client.post("/api/v1/super/sync").json()
    assert again["signals"]["inserted"] == 0
    assert again["workers"]["inserted"] == 0

    snaps = client.get("/api/v1/super/snapshots", params={"kind": "gex"}).json()
    assert len(snaps) == 1 and snaps[0]["snapshot_date"] == "2026-07-27"


def test_worker_rows_persisted_with_identity(client, super_dir):
    client.post("/api/v1/super/sync")
    page = client.get("/api/v1/super/signals", params={"ticker": "SPY"}).json()
    assert page["total"] == 3  # 1 central ledger row + 2 worker rows
    worker_rows = [i for i in page["items"] if i["raw"].get("engine")]
    assert {i["raw"]["engine"] for i in worker_rows} == {"4h", "1h"}
    assert all(i["category"] == "etf" and i["grade"] is None for i in worker_rows)

    # appending a new worker row is picked up incrementally (force pass)
    csv_path = super_dir / "spy_research" / "spy_intraday_signals.csv"
    with csv_path.open("a") as fh:
        fh.write(
            "2026-07-27 11:35:26,A,2h,5m,new_sig,LONG,1,am_0845_1130,0.0,0.8,75.0,"
            "80.0,4,2026-07-27 11:30,739.00,739.00,740.85,737.15,13:35,13:35,742.05,"
            "738.0,739.96,1.003,702388,1.30\n"
        )
    body = client.post("/api/v1/super/sync").json()
    assert body["workers"]["inserted"] == 1


def test_sync_status_endpoint(client, super_dir):
    status = client.get("/api/v1/super/sync/status").json()
    # background loop is disabled in tests; the shape is what matters
    assert status["enabled"] is False
    assert set(status) >= {"runs", "errors", "last_run_at", "last_result"}


def test_supervisor_start_stop_logic_mocked(client, super_dir, monkeypatch):
    spawned = []

    class FakeProc:
        pid = 4242

        def poll(self):
            return None

    def fake_popen(argv, **kwargs):
        spawned.append(argv)
        return FakeProc()

    monkeypatch.setattr(svc.subprocess, "Popen", fake_popen)
    resp = client.post("/api/v1/super/on")
    assert resp.status_code == 200
    body = resp.json()
    # etf has an enabled ticker -> started; crypto has none enabled -> skipped
    assert body["started"] == ["etf"]
    assert body["already"] == []
    assert body["sequence"] == ["etf"]
    assert "--category" in spawned[0] and "etf" in spawned[0]

    # now etf is live via our child handle -> 'already'
    resp = client.post("/api/v1/super/on")
    assert resp.json()["already"] == ["etf"]

    state = client.get("/api/v1/super/state").json()
    etf = next(c for c in state["categories"] if c["key"] == "etf")
    assert etf["live"] is True and etf["pid"] == 4242
