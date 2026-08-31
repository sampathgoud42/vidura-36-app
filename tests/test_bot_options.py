from __future__ import annotations

import textwrap
import time
from pathlib import Path

import pytest

from app.schemas.bot import SportSettings
from app.services import bot_manager, bot_registry
from app.services.bot_manager import BotStartOptions
from app.services.bot_registry import BotSpec, BotVersion


@pytest.fixture
def fake_sports_bot(tmp_path: Path, monkeypatch) -> Path:
    """Sports spec pointing at a stub that prints its env knobs then sleeps."""
    script = tmp_path / "fake_sports.py"
    script.write_text(
        textwrap.dedent(
            """
            import os, time
            for k in ("MAIN_SPORTS_LIST", "TENNIS_CONTRACTS", "TENNIS_BANK",
                      "TENNIS_MODEL", "BASEBALL_CONTRACTS", "BASEBALL_BANK",
                      "TARGET_PORTFOLIO_PCT", "MAIN_PAPER", "DRY_RUN_MODE"):
                print(f"{k}={os.environ.get(k, '')}", flush=True)
            time.sleep(120)
            """
        ),
        encoding="utf-8",
    )
    spec = BotSpec(
        key="sports",
        name="fake sports",
        category="sports",
        cadence="live",
        versions=(BotVersion("main", script.name, default=True),),
        launch_style="argv_customer",
    )
    monkeypatch.setitem(bot_registry.BOTS, "sports", spec)
    monkeypatch.setattr(bot_registry, "script_path", lambda s, v: tmp_path / v.rel_script)
    monkeypatch.setattr(bot_manager, "script_path", bot_registry.script_path)
    return script


def test_live_mode_locked_on_paper_only_server(client, user, fake_sports_bot):
    resp = client.post(
        "/api/v1/bots/sports/start",
        json={"user_id": user["user_id"], "mode": "live"},
    )
    assert resp.status_code == 403
    assert "TBOT_PAPER_ONLY" in resp.json()["detail"]


def test_sports_options_reach_bot_env(client, user, fake_sports_bot):
    resp = client.post(
        "/api/v1/bots/sports/start",
        json={
            "user_id": user["user_id"],
            "mode": "paper",
            "sports": ["tennis", "baseball"],
            "sport_settings": {
                "tennis": {"contracts": 25, "bank": 300, "model": "v3"},
                "baseball": {"contracts": 10, "bank": 150.5},
            },
            "target_pct": 12.5,
        },
    )
    assert resp.status_code == 201, resp.text
    run = resp.json()
    assert run["mode"] == "paper"
    assert run["extra"]["sports"] == ["tennis", "baseball"]
    assert run["extra"]["target_pct"] == 12.5

    time.sleep(1.5)
    logs = client.get(
        "/api/v1/bots/sports/logs", params={"user_id": user["user_id"]}
    ).json()
    text = "\n".join(logs["lines"])
    assert "MAIN_SPORTS_LIST=tennis,baseball" in text
    assert "TENNIS_CONTRACTS=25" in text
    assert "TENNIS_BANK=300" in text
    assert "TENNIS_MODEL=v3" in text
    assert "BASEBALL_CONTRACTS=10" in text
    assert "BASEBALL_BANK=150.5" in text
    assert "TARGET_PORTFOLIO_PCT=12.5" in text
    assert "MAIN_PAPER=TRUE" in text  # default stays paper
    assert "DRY_RUN_MODE=TRUE" in text

    client.post("/api/v1/bots/sports/stop", json={"user_id": user["user_id"]})


def test_unknown_sport_rejected(client, user, fake_sports_bot):
    resp = client.post(
        "/api/v1/bots/sports/start",
        json={"user_id": user["user_id"], "sports": ["cricket"]},
    )
    assert resp.status_code == 422
    assert "cricket" in resp.json()["detail"]


def test_live_env_flags_when_unlocked(monkeypatch):
    """Unit check: live mode flips every paper flag off (no process spawned)."""
    env = bot_manager._base_env("live")
    assert env["DRY_RUN_MODE"] == "FALSE"
    assert env["BOT152_DRY_RUN"] == "FALSE"
    assert env["MAIN_PAPER"] == "FALSE"
    assert env["HALT_MACHINE_SHUTDOWN"] == "FALSE"  # never allowed regardless

    env = bot_manager._base_env("paper")
    assert env["DRY_RUN_MODE"] == "TRUE"
    assert env["MAIN_PAPER"] == "TRUE"


def test_sports_env_mapping_unit():
    env: dict[str, str] = {}
    bot_manager._sports_env(
        env,
        BotStartOptions(
            sports=["tennis"],
            sport_settings={"tennis": SportSettings(contracts=20, bank=0)},
            target_pct=8,
        ),
    )
    assert env["MAIN_SPORTS_LIST"] == "tennis"
    assert env["SPORTS_LIST"] == "tennis"
    assert env["TENNIS_CONTRACTS"] == "20"
    assert env["TENNIS_BANK"] == "0"  # 0 = unlimited, must be passed through
    assert env["TARGET_PORTFOLIO_PCT"] == "8"
