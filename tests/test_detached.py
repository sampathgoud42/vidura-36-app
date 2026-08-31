"""Proof of full detachment: after one sync, every read endpoint keeps
serving from SQLite even when the 38trades source repo is gone from disk."""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.services import super_research as svc


def test_reads_survive_source_repo_removal(client, super_dir, monkeypatch, tmp_path: Path):
    # 1. With the repo present: one sync mirrors everything into the DB.
    assert client.post("/api/v1/super/sync").status_code == 200

    # 2. Point the API at a non-existent repo and drop every cache.
    monkeypatch.setattr(get_settings(), "source_repo", tmp_path / "gone")
    svc.invalidate_caches()

    # 3. Desk state still serves — config, feeds, worker rows, econ, gex.
    state = client.get("/api/v1/super/state").json()
    assert "error" not in state
    assert {c["key"] for c in state["categories"]} == {"etf", "crypto"}
    etf = next(c for c in state["categories"] if c["key"] == "etf")
    assert etf["tickers"][0]["rows"], "worker rows must come from the DB"
    assert all(isinstance(v, str) for v in state["aFeed"][0].values())
    assert state["aFeed"][0]["ticker"] == "GLD"
    assert state["econ"]["date"] == "2026-07-27"
    assert state["gex"]["tickers"]["SPY"]["regime"] == "negative_gamma"

    # archive semantics survive too
    assert len(client.get("/api/v1/super/state?all=1").json()["aFeed"]) == 3
    svc.invalidate_caches()
    assert len(client.get("/api/v1/super/state").json()["aFeed"]) == 2

    # 4. Dedicated endpoints too.
    assert client.get("/api/v1/super/gex").json()["macro"]["vix"] == 18.72
    assert client.get("/api/v1/super/econ").json()["high_impact"] is False
    cfg = client.get("/api/v1/super/config").json()
    assert cfg["_comment"] == "test"

    # 5. Config writes hit the DB mirror even without the file on disk.
    r = client.post("/api/v1/super/config", json={"enabled": {"spy": False}})
    assert r.json() == {"ok": True}
    cfg = client.get("/api/v1/super/config").json()
    assert cfg["categories"]["etf"]["tickers"][0]["enabled"] is False

    # 6. Signals history and snapshots (already DB-backed) still fine.
    assert client.get("/api/v1/super/signals").json()["total"] > 0
    assert client.get("/api/v1/super/snapshots", params={"kind": "gex"}).json()

    # 7. Execution paths degrade with clear errors instead of crashing.
    r = client.post("/api/v1/super/regenerate", params={"force": "true"})
    assert r.status_code == 500
    assert "source repo" in r.json()["detail"]
    r = client.post("/api/v1/super/econ/refresh")
    assert r.status_code == 503
