"""Stray-process detection and the kill option.

The dangerous case: a bot the API never started (orphan from a previous
instance, the legacy scheduler, a manual launch) is invisible to the DB
check, so a start would silently double-run against one Kalshi account.
"""

from __future__ import annotations

import textwrap
import time
from pathlib import Path

import pytest

from app.services import bot_manager, bot_registry
from app.services.bot_registry import BotSpec, BotVersion


@pytest.fixture
def fake_btc15(tmp_path: Path, monkeypatch):
    script = tmp_path / "fake_stray_bot.py"
    script.write_text(
        textwrap.dedent(
            """
            import time
            print("FAKE-BOT up", flush=True)
            time.sleep(120)
            """
        ),
        encoding="utf-8",
    )
    spec = BotSpec(
        key="btc15",
        name="fake btc15",
        category="btc",
        cadence="15m",
        versions=(BotVersion("v2", script.name, default=True),),
        launch_style="cwd_customer",
    )
    monkeypatch.setitem(bot_registry.BOTS, "btc15", spec)
    monkeypatch.setattr(bot_registry, "script_path", lambda s, v: tmp_path / v.rel_script)
    monkeypatch.setattr(bot_manager, "script_path", bot_registry.script_path)
    return script


def _spawn_stray(script: Path):
    """A copy of the bot the API knows nothing about."""
    import subprocess
    import sys

    return subprocess.Popen([sys.executable, str(script)], stdout=subprocess.DEVNULL)


def test_processes_endpoint_sees_untracked_copy(client, fake_btc15):
    stray = _spawn_stray(fake_btc15)
    try:
        time.sleep(1.5)
        body = client.get("/api/v1/bots/btc/processes", params={"bot": "btc15"}).json()
        assert body["count"] >= 1
        assert any(p["pid"] == stray.pid for p in body["processes"])
        assert body["processes"][0]["script"] == fake_btc15.name
    finally:
        stray.kill()


def test_start_refuses_while_an_untracked_copy_runs(client, user, fake_btc15):
    stray = _spawn_stray(fake_btc15)
    try:
        time.sleep(1.5)
        resp = client.post(
            "/api/v1/bots/btc/start?bot=btc15",
            json={"user_id": user["user_id"], "mode": "paper"},
        )
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert "outside this API" in detail
        assert str(stray.pid) in detail
    finally:
        stray.kill()


def test_kill_existing_takes_over(client, user, fake_btc15):
    stray = _spawn_stray(fake_btc15)
    time.sleep(1.5)
    resp = client.post(
        "/api/v1/bots/btc/start?bot=btc15",
        json={"user_id": user["user_id"], "mode": "paper", "kill_existing": True},
    )
    assert resp.status_code == 201, resp.text
    run = resp.json()
    assert run["status"] == "running"
    assert run["pid"] != stray.pid

    time.sleep(1)
    assert stray.poll() is not None, "the stray copy must be gone"

    client.post("/api/v1/bots/btc/stop?bot=btc15", json={"user_id": user["user_id"]})


def test_kill_endpoint_clears_everything_and_updates_runs(client, user, fake_btc15):
    resp = client.post(
        "/api/v1/bots/btc/start?bot=btc15",
        json={"user_id": user["user_id"], "mode": "paper"},
    )
    assert resp.status_code == 201
    ours = resp.json()["pid"]
    stray = _spawn_stray(fake_btc15)
    time.sleep(1.5)

    body = client.post("/api/v1/bots/btc/kill", params={"bot": "btc15"}).json()
    assert set(body["killed"]) >= {ours, stray.pid}

    # the DB row for our run is no longer 'running'
    status = client.get("/api/v1/bots/btc/status", params={"user_id": user["user_id"]}).json()
    btc15 = next(s for s in status if s["bot_key"] == "btc15")
    assert btc15["running"] is False
    assert stray.poll() is not None


def test_kill_specific_pid_only(client, user, fake_btc15):
    a = _spawn_stray(fake_btc15)
    b = _spawn_stray(fake_btc15)
    try:
        time.sleep(1.5)
        body = client.post(
            "/api/v1/bots/btc/kill", params={"bot": "btc15", "pids": str(a.pid)}
        ).json()
        # the target dies with its children (the venv launcher re-execs a real
        # interpreter, so more than one pid can come back) — what matters is
        # that ONLY the requested tree went down
        assert a.pid in body["killed"]
        assert b.pid not in body["killed"]
        time.sleep(0.5)
        assert a.poll() is not None
        assert b.poll() is None, "the other copy must be untouched"
    finally:
        a.kill()
        b.kill()
