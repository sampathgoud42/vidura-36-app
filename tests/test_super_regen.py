from __future__ import annotations

from app.services import super_research as svc


def test_regenerate_spawns_backfill_once_per_category(client, monkeypatch, super_dir):
    spawned = []

    class FakeProc:
        pid = 5151

    monkeypatch.setattr(
        svc.subprocess, "Popen", lambda argv, **kw: (spawned.append(argv), FakeProc())[1]
    )
    resp = client.post("/api/v1/super/regenerate")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["launched"] == {"etf": 5151}  # crypto skipped: no enabled tickers
    assert body["skipped"] == {"crypto": "no enabled tickers"}
    assert "--once" in spawned[0] and "--backfill-today" in spawned[0]

    # second call within 24h: nothing launched, user must confirm
    resp = client.post("/api/v1/super/regenerate")
    body = resp.json()
    assert body.get("recent") is True
    assert body["launched"] == {}
    assert 0 <= body["hours_ago"] < 24

    # force launches despite the fresh stamp
    resp = client.post("/api/v1/super/regenerate", params={"force": "true"})
    assert resp.json().get("recent") is None
    assert resp.json()["launched"] == {"etf": 5151}

    resp = client.post(
        "/api/v1/super/regenerate", params={"categories": "crypto", "force": "true"}
    )
    assert resp.json()["launched"] == {}


def test_gex_reload_reads_file_and_snapshots(client, super_dir):
    resp = client.post("/api/v1/super/gex/reload")
    assert resp.status_code == 200
    body = resp.json()
    assert body["reloaded"] is True
    assert body["gex"]["tickers"]["SPY"]["regime"] == "negative_gamma"
    snaps = client.get("/api/v1/super/snapshots", params={"kind": "gex"}).json()
    assert len(snaps) == 1
