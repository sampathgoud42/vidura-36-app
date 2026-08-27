from __future__ import annotations

import textwrap
import time
from pathlib import Path

import pytest

from app.services import bot_registry
from app.services.bot_registry import BotSpec, BotVersion


@pytest.fixture
def fake_btc15(tmp_path: Path, monkeypatch) -> Path:
    """Swap the btc15 registry entry for a harmless long-running script so
    the full start/status/logs/stop lifecycle runs without a real bot."""
    script = tmp_path / "fake_bot.py"
    script.write_text(
        textwrap.dedent(
            """
            import os, sys, time
            print("FAKE-BOT started", flush=True)
            print("DRY_RUN_MODE=" + os.environ.get("DRY_RUN_MODE", ""), flush=True)
            print("HALT_MACHINE_SHUTDOWN=" + os.environ.get("HALT_MACHINE_SHUTDOWN", ""), flush=True)
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
    # script_path joins settings.source_repo / rel_script -> point repo at tmp.
    monkeypatch.setattr(
        bot_registry, "script_path", lambda s, v: tmp_path / v.rel_script
    )
    import app.services.bot_manager as bm

    monkeypatch.setattr(bm, "script_path", bot_registry.script_path)
    return script


def test_bot_registry_lists_all_bots(client):
    resp = client.get("/api/v1/bots")
    assert resp.status_code == 200
    bots = {b["key"]: b for b in resp.json()}
    assert set(bots) == {"btc15", "btc60", "sports", "parley",
                         "gold15", "silver15", "oil15"}
    assert any(v["version"] == "v2" for v in bots["btc15"]["versions"])
    assert any(v["version"] == "fable5" for v in bots["btc60"]["versions"])
    # the parlay script must be VENDORED, not merely registered — a registry
    # entry pointing at nothing reports "exists": false and 503s on start
    assert all(v["exists"] for v in bots["parley"]["versions"]), bots["parley"]


def test_btc_lifecycle_start_status_logs_stop(client, user, fake_btc15):
    # start
    resp = client.post(
        "/api/v1/bots/btc/start?bot=btc15",
        json={"user_id": user["user_id"], "mode": "paper"},
    )
    assert resp.status_code == 201, resp.text
    run = resp.json()
    assert run["status"] == "running"
    assert run["pid"]

    # duplicate start rejected
    resp = client.post(
        "/api/v1/bots/btc/start?bot=btc15",
        json={"user_id": user["user_id"], "mode": "paper"},
    )
    assert resp.status_code == 409

    # status shows running
    resp = client.get("/api/v1/bots/btc/status", params={"user_id": user["user_id"]})
    assert resp.status_code == 200
    by_key = {s["bot_key"]: s for s in resp.json()}
    assert by_key["btc15"]["running"] is True

    # logs captured (paper flags forced)
    time.sleep(1.5)
    resp = client.get(
        "/api/v1/bots/btc/logs",
        params={"bot": "btc15", "user_id": user["user_id"]},
    )
    assert resp.status_code == 200
    text = "\n".join(resp.json()["lines"])
    assert "FAKE-BOT started" in text
    assert "DRY_RUN_MODE=TRUE" in text
    assert "HALT_MACHINE_SHUTDOWN=FALSE" in text

    # stop
    resp = client.post(
        "/api/v1/bots/btc/stop?bot=btc15", json={"user_id": user["user_id"]}
    )
    assert resp.status_code == 200
    assert resp.json()[0]["status"] == "stopped"

    # status shows not running
    resp = client.get("/api/v1/bots/btc/status", params={"user_id": user["user_id"]})
    by_key = {s["bot_key"]: s for s in resp.json()}
    assert by_key["btc15"]["running"] is False


def test_stop_without_running_bot_404(client, user):
    resp = client.post(
        "/api/v1/bots/btc/stop?bot=btc60", json={"user_id": user["user_id"]}
    )
    assert resp.status_code == 404


def test_live_mode_rejected_when_paper_only(client, user, fake_btc15):
    resp = client.post(
        "/api/v1/bots/btc/start?bot=btc15",
        json={"user_id": user["user_id"], "mode": "live"},
    )
    # Pydantic pattern rejects it at validation (422); belt-and-braces 403 in
    # the manager if the schema ever loosens.
    assert resp.status_code in (403, 422)


def test_sports_config_exposes_no_secrets(client):
    resp = client.get("/api/v1/bots/sports/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["paper_only_server"] is True
    joined = " ".join(body["config"].keys()).upper()
    assert "KEY" not in joined
    assert "SECRET" not in joined
