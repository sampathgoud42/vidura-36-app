"""The parlay bot as the station launches it.

It is the sports engine's own script — same import graph, same trade-CSV
shape — but a separate process with a separate bankroll, ledger and pair of
CSVs. These cover the seams that creates: its knobs must land on PARLEY_*
rather than on the sports engine's, its paper mode must reach the exchange
in no way at all, and its rows must arrive in the ledger under their own bot
key instead of merging with the sports bot's.
"""

from __future__ import annotations

import textwrap
import time
from pathlib import Path

import pytest

from app.services import bot_manager, bot_registry
from app.services.bot_manager import BotStartOptions
from app.services.bot_registry import BotSpec, BotVersion

# Every knob the launch console can send, printed back by the stub below.
ECHOED = (
    "PARLEY_SPORTS_LIST", "PARLEY_CONTRACTS", "PARLEY_BANK",
    "PARLEY_STOP_LOSS_PCT", "PARLEY_MIN_PROB_C", "PARLEY_MIN_SET",
    "PARLEY_LEAD_SCOPE", "PARLEY_MIN_LEGS", "PARLEY_MAX_LEGS",
    "PARLEY_MAX_OPEN", "PARLEY_COOLDOWN_S", "PARLEY_SLIPPAGE_C",
    "PARLEY_MAX_PRICE_C", "PARLEY_TP_CEILING_C", "PARLEY_STOP_LOSS_C",
    "PARLEY_LIMIT_FALLBACK", "PARLEY_PAPER", "PARLEY_PAPER_CREATE_MARKET",
    "PARLEY_TRADE_CSV", "PARLEY_LEDGER", "MAIN_SPORTS_LIST", "DRY_RUN_MODE",
)


@pytest.fixture
def fake_parley_bot(tmp_path: Path, monkeypatch) -> Path:
    script = tmp_path / "fake_parley.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import os, time
            for k in {ECHOED!r}:
                print(f"{{k}}={{os.environ.get(k, '')}}", flush=True)
            time.sleep(120)
            """
        ),
        encoding="utf-8",
    )
    spec = BotSpec(
        key="parley",
        name="fake parley",
        category="sports",
        cadence="live-match",
        versions=(BotVersion("v1", script.name, default=True),),
        launch_style="argv_customer",
    )
    monkeypatch.setitem(bot_registry.BOTS, "parley", spec)
    monkeypatch.setattr(bot_registry, "script_path", lambda s, v: tmp_path / v.rel_script)
    monkeypatch.setattr(bot_manager, "script_path", bot_registry.script_path)
    yield script
    # Reap the stub unconditionally. start_bot refuses to launch while ANY
    # copy of a bot runs — including one this API never started — so a stub
    # left behind by a failing test turns every later test in this file into
    # a 409 and hides the real failure behind a cascade.
    for proc in bot_manager.find_bot_processes("parley"):
        try:
            bot_manager.psutil.Process(proc["pid"]).kill()
        except Exception:                                          # noqa: BLE001
            pass


def _tail(client, user) -> str:
    time.sleep(1.5)
    logs = client.get("/api/v1/bots/parley/logs", params={"user_id": user["user_id"]}).json()
    return "\n".join(logs["lines"])


# --- launch --------------------------------------------------------------

def test_parley_options_reach_bot_env(client, user, fake_parley_bot):
    resp = client.post(
        "/api/v1/bots/parley/start",
        json={
            "user_id": user["user_id"],
            "mode": "paper",
            "sports": ["tennis"],
            "contracts": 8,
            "bank": 250,
            "bank_sl_pct": 40,
            "parley": {
                "min_prob_c": 85, "min_set": 3, "lead_scope": "off",
                "min_legs": 3, "max_legs": 4, "max_open": 2,
                "cooldown_min": 20, "slippage_c": 2, "max_price_c": 90,
                "tp_ceiling_c": 96, "stop_loss_c": 25, "limit_fallback": True,
            },
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["extra"]["parley"]["min_prob_c"] == 85

    text = _tail(client, user)
    assert "PARLEY_SPORTS_LIST=tennis" in text
    assert "PARLEY_CONTRACTS=8" in text
    assert "PARLEY_BANK=250" in text
    assert "PARLEY_STOP_LOSS_PCT=40" in text
    assert "PARLEY_MIN_PROB_C=85" in text
    assert "PARLEY_MIN_SET=3" in text
    assert "PARLEY_LEAD_SCOPE=off" in text
    assert "PARLEY_MIN_LEGS=3" in text
    assert "PARLEY_MAX_LEGS=4" in text
    assert "PARLEY_MAX_OPEN=2" in text
    assert "PARLEY_COOLDOWN_S=1200" in text     # minutes on the wire, seconds here
    assert "PARLEY_SLIPPAGE_C=2" in text
    assert "PARLEY_MAX_PRICE_C=90" in text
    assert "PARLEY_TP_CEILING_C=96" in text
    assert "PARLEY_STOP_LOSS_C=25" in text
    assert "PARLEY_LIMIT_FALLBACK=TRUE" in text
    # the sports engine's own selection knob must stay untouched: this bot
    # shares that engine's process image, and setting it would re-point the
    # engine's config from underneath the parlay logic
    assert "MAIN_SPORTS_LIST=\n" in text + "\n"

    client.post("/api/v1/bots/parley/stop", json={"user_id": user["user_id"]})


def test_paper_run_touches_the_exchange_in_no_way(client, user, fake_parley_bot):
    """Paper must be paper: no order, and no combined-market creation either.

    Creating the combo is a POST — the bot's own default does it so paper can
    price against a real book, but Kalshi caps creations at 5000/week and a
    fresh combo has an empty book anyway.
    """
    resp = client.post(
        "/api/v1/bots/parley/start",
        json={"user_id": user["user_id"], "mode": "paper"},
    )
    assert resp.status_code == 201, resp.text
    text = _tail(client, user)
    assert "PARLEY_PAPER=TRUE" in text
    assert "PARLEY_PAPER_CREATE_MARKET=FALSE" in text
    assert "DRY_RUN_MODE=TRUE" in text
    client.post("/api/v1/bots/parley/stop", json={"user_id": user["user_id"]})


def test_paper_and_live_never_share_a_ledger(client, user, fake_parley_bot):
    resp = client.post(
        "/api/v1/bots/parley/start",
        json={"user_id": user["user_id"], "mode": "paper"},
    )
    assert resp.status_code == 201, resp.text
    text = _tail(client, user)
    assert "paper_parley.csv" in text
    assert "parley_ledger_paper.json" in text
    assert "trade_history_parley.csv" not in text
    client.post("/api/v1/bots/parley/stop", json={"user_id": user["user_id"]})


def test_live_mode_locked_on_paper_only_server(client, user, fake_parley_bot, monkeypatch):
    # The lock is pinned on rather than inherited: this machine's .env has
    # TBOT_PAPER_ONLY=false, and a test that only passes on a locked server
    # is a test that silently stops checking anything here.
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "paper_only", True)
    resp = client.post(
        "/api/v1/bots/parley/start",
        json={"user_id": user["user_id"], "mode": "live"},
    )
    assert resp.status_code == 403
    assert "TBOT_PAPER_ONLY" in resp.json()["detail"]


def test_only_tennis_legs_are_accepted(client, user, fake_parley_bot):
    resp = client.post(
        "/api/v1/bots/parley/start",
        json={"user_id": user["user_id"], "sports": ["baseball"]},
    )
    assert resp.status_code == 422
    assert "baseball" in resp.json()["detail"]


# --- unit: the env mapping itself ----------------------------------------

def test_parley_env_mapping_unit():
    env: dict[str, str] = {}
    bot_manager._parley_env(
        env,
        BotStartOptions(
            sports=["tennis"], contracts=10, bank=0, bank_sl_pct=50,
            parley={"min_prob_c": 80, "cooldown_min": 0.5, "limit_fallback": False},
        ),
    )
    assert env["PARLEY_BANK"] == "0"          # 0 = unlimited, must pass through
    assert env["PARLEY_CONTRACTS"] == "10"
    assert env["PARLEY_STOP_LOSS_PCT"] == "50"
    assert env["PARLEY_MIN_PROB_C"] == "80"
    assert env["PARLEY_COOLDOWN_S"] == "30"
    assert env["PARLEY_LIMIT_FALLBACK"] == "FALSE"
    # nothing the caller left alone may be invented — an unset knob has to
    # fall through to the engine's own default
    assert "PARLEY_MIN_SET" not in env
    assert "PARLEY_TP_CEILING_C" not in env


def test_sports_knobs_never_leak_into_a_parley_launch():
    env: dict[str, str] = {}
    bot_manager._parley_env(env, BotStartOptions(sports=["tennis"], contracts=10))
    assert "MAIN_SPORTS_LIST" not in env
    assert "TENNIS_CONTRACTS" not in env
    assert "SPORT_CONTRACTS" not in env


def test_paper_base_env_holds_both_parlay_brakes():
    paper = bot_manager._base_env("paper")
    assert paper["PARLEY_PAPER"] == "TRUE"
    assert paper["PARLEY_PAPER_CREATE_MARKET"] == "FALSE"
    live = bot_manager._base_env("live")
    assert live["PARLEY_PAPER"] == "FALSE"


# --- the vendored script -------------------------------------------------

def test_script_is_vendored_and_imports_the_sports_engine():
    from app.core.config import get_settings

    script = get_settings().source_repo / "prediction-trade/kalshi/sports/bot_kalshi_parley.py"
    assert script.is_file(), f"parlay bot not vendored at {script}"
    src = script.read_text(encoding="utf-8", errors="replace")
    # it inherits the engine's plumbing rather than re-implementing it; if
    # these move, the vendored sports files it leans on have to move with it
    for dep in ("import bot_kalshi_main as eng",
                "import bot_kalshi_sports_v1 as tv1",
                "from sport_adapters import create_adapter"):
        assert dep in src, f"missing dependency line: {dep}"
    for sibling in ("bot_kalshi_main.py", "bot_kalshi_sports_v1.py", "sport_adapters"):
        assert (script.parent / sibling).exists(), f"{sibling} not vendored beside it"


# --- ledger --------------------------------------------------------------

def test_parley_csv_ingests_under_its_own_bot_key(client, user, tmp_path):
    """Its rows carry the sports CSV shape. They must not merge with the
    sports bot's: one key space would let two ledgers collide on a shared
    timestamp, and the desk would file a parlay under SPORTS."""
    from app.core.database import SessionLocal
    from app.models import User
    from app.services import ingest

    root = Path(user["user_root_folder"])
    trade_dir = root / "trade_history"
    trade_dir.mkdir(parents=True, exist_ok=True)
    header = ("ts_epoch,ts,sport,ticker,name,side,situation,confidence,reason,"
              "context,model_wp,signal_bid,buy_price,fill_price,contracts,"
              "tp_price,stop_price,pv_entry,status,ts_close,realized_pnl\n")
    (trade_dir / "trade_history_parley.csv").write_text(
        header
        + "1755200000,2026-08-14 10:00:00,parley,KXPARLEY-A,2-leg parlay,yes,"
          "2 live legs,high,legs,ctx,0.64,66,68,67,10,97,47,500,CLOSED,"
          "2026-08-14 11:00:00,12.5\n",
        encoding="utf-8",
    )
    # same ts_epoch as the parlay row, different ledger — the collision case
    (trade_dir / "trade_history_main.csv").write_text(
        header
        + "1755200000,2026-08-14 10:00:00,tennis,KXATP-B,Player,yes,live,high,r,"
          "c,0.7,70,71,70,5,97,50,500,OPEN,,\n",
        encoding="utf-8",
    )

    db = SessionLocal()
    try:
        u = db.get(User, user["user_id"])
        assert ingest.sync_trades(db, u, "parley")["inserted"] == 1
        assert ingest.sync_trades(db, u, "sports")["inserted"] == 1
    finally:
        db.close()

    rows = client.get("/api/v1/bots/parley/trades",
                      params={"user_id": user["user_id"], "mode": "all"}).json()
    assert rows["total"] == 1
    row = rows["items"][0]
    assert row["bot_key"] == "parley"
    assert row["ticker"] == "KXPARLEY-A"
    assert row["pnl_usd"] == 12.5

    sports = client.get("/api/v1/bots/sports/trades",
                        params={"user_id": user["user_id"], "mode": "all"}).json()
    assert [r["ticker"] for r in sports["items"]] == ["KXATP-B"]


def test_paper_rows_stay_out_of_the_live_view(client, user):
    from app.core.database import SessionLocal
    from app.models import User
    from app.services import ingest

    trade_dir = Path(user["user_root_folder"]) / "trade_history"
    trade_dir.mkdir(parents=True, exist_ok=True)
    (trade_dir / "paper_parley.csv").write_text(
        "ts_epoch,ts,ticker,name,fill_price,contracts,status,realized_pnl\n"
        "1755300000,2026-08-14 12:00:00,KXPARLEY-P,3-leg parlay,55,10,OPEN,\n",
        encoding="utf-8",
    )
    db = SessionLocal()
    try:
        ingest.sync_trades(db, db.get(User, user["user_id"]), "parley")
    finally:
        db.close()

    live = client.get("/api/v1/bots/parley/trades",
                      params={"user_id": user["user_id"], "mode": "live"}).json()
    assert live["total"] == 0
    paper = client.get("/api/v1/bots/parley/trades",
                       params={"user_id": user["user_id"], "mode": "paper"}).json()
    assert [r["ticker"] for r in paper["items"]] == ["KXPARLEY-P"]
