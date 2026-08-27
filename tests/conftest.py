"""Shared fixtures: isolated temp SQLite DB + TestClient + fake user folder.

The database path env var must be set BEFORE any ``app.*`` import because
the engine binds at import time — hence the module-level bootstrap here.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="tradier_bot_test_"))
os.environ.setdefault("TBOT_DATABASE_PATH", str(_TMP / "test_app.db"))
os.environ.setdefault("TBOT_VAR_DIR", str(_TMP / "var"))
# Tests build user folders under pytest tmp paths, outside customers_root.
os.environ.setdefault("TBOT_ALLOW_ANY_ROOT", "true")
# Keep tests hermetic: no background loop ingesting the real super_research
# tree into the test database.
os.environ.setdefault("TBOT_SUPER_AUTO_SYNC", "false")
# The daily GEX job must NEVER run in a test: flashAlpha's free plan allows
# 5 requests/day and the desk depends on them.
os.environ.setdefault("TBOT_GEX_DAILY_ENABLED", "false")
os.environ.setdefault("TBOT_FLASHALPHA_API_KEY", "test-key-not-real")
# The earnings warm loop is keyless but still ~100 yfinance calls — tests must
# stay offline and fast, so the sweep is always monkeypatched instead.
os.environ.setdefault("TBOT_EARNINGS_ENABLED", "false")
# Hermetic: the Tradier SL monitor and the Kalshi reconcile loops must
# never run against test rows with real backoff timers.
os.environ.setdefault("TBOT_TRADIER_ENABLED", "false")
os.environ.setdefault("TBOT_RECONCILE_ENABLED", "false")
# The project .env on the extraction workstation carries a deliberate live
# unlock. Tests must never inherit it: every paper-only guard would read as
# unlocked and the suite would stop covering the guard at all.
os.environ.setdefault("TBOT_PAPER_ONLY", "true")
# The gate is exercised by tests/test_auth.py, which re-enables it
# per test. Everything else predates it and calls the API bare.
os.environ.setdefault("TBOT_LOGIN_REQUIRED", "false")

import pytest
from fastapi.testclient import TestClient

from app.core.database import Base, engine
from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db_session():
    """A plain session for exercising services without going through HTTP."""
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def clean_db():
    """Fresh tables for every test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def user_folder(tmp_path: Path) -> Path:
    """A realistic user root folder: .sam password, wellness profile,
    trade_history dir. (No real credentials — Kalshi tests are separate.)"""
    (tmp_path / ".sam").write_text("test-pass-123\n", encoding="utf-8")
    (tmp_path / "wellness-profile.json").write_text(
        '{"gender": "Male", "age": "30-35", "ethnicity": "Indian", '
        '"diet": "Non-Vegetarian", "style": "Both", "goals": ["Cholesterol"], '
        '"region": "Bangalore", "notifications": true}',
        encoding="utf-8",
    )
    (tmp_path / "trade_history").mkdir()
    (tmp_path / "logs").mkdir()
    return tmp_path


CENTRAL_HEADER = (
    "logged_at_cst,category,ticker,book,direction,signal,confluence,signal_price,"
    "entry_ref,target_price,stop_price,stop_deadline_cst,target_deadline_cst,"
    "acc_tp_before_sl_pct,acc_strict_pct,bar_time_cst,repeats,hot,engines,eng_hot,"
    "tfs,econ,outcome,outcome_at"
)
WORKER_HEADER = (
    "logged_at_cst,book,engine,tf,signal,direction,confluence,window,noise_k,"
    "vol_mult,acc_strict_pct,acc_tp_before_sl_pct,bt_trades,bar_time_cst,"
    "signal_price,entry_ref,target_price,stop_price,stop_deadline_cst,"
    "target_deadline_cst,vwap,y_poc,pivot,atr,volume,vol_vs_med20"
)


@pytest.fixture
def super_dir(tmp_path: Path, monkeypatch) -> Path:
    """A realistic fake super_research tree; settings.source_repo points at
    its parent so settings.super_dir resolves here."""
    import json

    from app.core.config import get_settings
    from app.services import super_research as svc

    repo = tmp_path / "repo"
    sdir = repo / "super_research"
    (sdir / "archive").mkdir(parents=True)
    (sdir / "spy_research").mkdir()
    (sdir / "gex").mkdir()

    config = {
        "_comment": "test",
        "abookOnTop": True,
        "categories": {
            "etf": {
                "label": "ETF",
                "bot": "super_signal_bot.py",
                "session": "rth",
                "tickers": [
                    {
                        "id": "spy",
                        "label": "SPY",
                        "path": "spy_research",
                        "csv": "spy_intraday_signals.csv",
                        "img": "live-spy.webp",
                        "rules": "TP ±0.25%",
                        "enabled": True,
                    }
                ],
            },
            "crypto": {
                "label": "Crypto",
                "bot": "super_signal_bot.py",
                "session": "24x7",
                "tickers": [
                    {
                        "id": "btc",
                        "label": "BTC",
                        "path": "btc_research",
                        "csv": "btc_intraday_signals.csv",
                        "img": "live-btc.webp",
                        "rules": "24x7",
                        "enabled": False,
                    }
                ],
            },
        },
    }
    (sdir / "super_research.config").write_text(json.dumps(config, indent=2))
    (sdir / "super_signal_bot.py").write_text("# test stub\n")

    (sdir / "a_signals.csv").write_text(
        f"{CENTRAL_HEADER}\n"
        "2026-07-27 12:30:12,etf,GLD,A,SHORT,vwap_loss,2,373.92,373.92,372.99,374.85,"
        "14:35,14:35,100.0,66.7,2026-07-27 12:00,2,,30m+1h+2h+4h,4,5m+30m,,stop,14:20\n"
        "2026-07-27 09:35:26,etf,SPY,A,LONG,poc_bounce,1,737.97,737.97,739.81,736.13,"
        "13:35,13:35,90.0,80.0,2026-07-27 09:30,1,1,1h+2h,2,5m,,target,10:05\n"
    )
    (sdir / "b_signals.csv").write_text(
        f"{CENTRAL_HEADER}\n"
        "2026-07-27 13:56:09,etf,QQQ,B,LONG,adi_up,1,681.05,681.05,682.76,679.35,"
        "14:35,14:35,87.5,87.5,2026-07-27 13:50,1,,1h+2h+4h,3,5m,,target,14:05\n"
    )
    (sdir / "archive" / "a_signals.csv").write_text(
        f"{CENTRAL_HEADER}\n"
        "2026-07-20 13:00:28,etf,GLD,A,SHORT,vwap_loss,1,367.91,367.91,366.81,369.01,"
        "14:35,14:35,100.0,71.4,2026-07-20 12:10,2,,30m+1h+2h+3h+4h,5,5m+30m,,timeout,14:35\n"
    )
    (sdir / "spy_research" / "spy_intraday_signals.csv").write_text(
        f"{WORKER_HEADER}\n"
        "2026-07-27 09:35:26,A,4h,5m,poc_reject_dn,SHORT,1,am_0845_1130,0.0,0.8,100.0,"
        "100.0,6,2026-07-27 09:30,737.97,737.97,736.13,739.81,13:35,13:35,742.05,"
        "738.0,739.96,1.003,902388,1.57\n"
        "2026-07-27 10:35:26,B,1h,15m,vwap_reclaim,LONG,2,am_0845_1130,0.0,0.8,80.0,"
        "90.0,10,2026-07-27 10:30,738.50,738.50,740.35,736.65,13:35,13:35,742.05,"
        "738.0,739.96,1.003,802388,1.40\n"
    )
    (sdir / "gex_daily.json").write_text(
        json.dumps(
            {
                "fetched_at": "2026-07-27 09:20:57",
                "stale": False,
                "tickers": {
                    "SPY": {
                        "as_of": "2026-07-27T14:20:52.897Z",
                        "price": 740.48,
                        "net_gex": -9178182877,
                        "regime": "negative_gamma",
                        "gamma_flip": 745.11,
                        "call_wall": 750,
                        "put_wall": 740,
                        "gamma_note": "Dealers short gamma",
                        "atm_iv": 15.7,
                        "pc_ratio_volume": 0.354,
                    }
                },
                "macro": {"vix": 18.72, "fear_greed": 41},
            }
        )
    )
    (sdir / "econ_today.json").write_text(
        json.dumps(
            {
                "date": "2026-07-27",
                "events": [],
                "yields": {"10y": 4.651, "d10y_bp": -2.8},
                "note": "",
                "high_impact": False,
            }
        )
    )
    (sdir / "gex" / "2026-07-27_spy.json").write_text(json.dumps({"symbol": "SPY"}))

    settings = get_settings()
    monkeypatch.setattr(settings, "source_repo", repo)
    # Never scan or touch real machine processes from tests.
    monkeypatch.setattr(svc, "_scan_running", lambda force=False: {})
    svc._CHILDREN.clear()
    svc.invalidate_caches()  # state/scan TTL caches must not leak across tests
    return sdir


@pytest.fixture
def user(client: TestClient, user_folder: Path) -> dict:
    resp = client.post(
        "/api/v1/users",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "user_root_folder": str(user_folder),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
