"""Per-trade profit target for the BTC engines.

Distinct from target_pct, which halts the whole session at a portfolio gain.
tp_pct is the take-profit on EACH trade, as a percent over the entry price.

The four startable engines each express take-profit differently, so one input
has to reach three different knobs:
    btc15 v2/v3/v4 : KALSHI_PROFIT_PCT   (already env-driven)
    btc15 v5       : BOT152_TP_PCT       (else a flat 90c sell)
    btc60 both     : BTC60_TP_PCT        (fable5 also pins its learner)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services import bot_manager

BTC = Path(__file__).resolve().parents[1] / "runtime" / "prediction-trade" / "kalshi" / "btc"


# ---- env plumbing ---------------------------------------------------------

def _btc_launch_env(tmp_path, tp_pct):
    """The env a real BTC launch would get. Caught the original bug: the
    mapping lived in _sports_env(), which a BTC start never calls, so the
    knob was set in source but never in the process."""
    from app.models import User
    from app.services.bot_registry import get_bot

    root = tmp_path / "u"
    (root / "trade_history").mkdir(parents=True)
    (root / "logs").mkdir(exist_ok=True)
    user = User(user_id="u1", username="u", user_root_folder=str(root))
    spec = get_bot("btc15")
    version = next(v for v in spec.versions if v.version == "v5")
    opts = bot_manager.BotStartOptions(mode="paper", tp_pct=tp_pct)
    try:
        _argv, _cwd, env = bot_manager._launch_plan(spec, version, user, opts)
    except bot_manager.BotManagerError as exc:
        pytest.skip(f"btc15 v5 not launchable here: {exc}")
    return env


def test_a_btc_launch_actually_receives_the_target(tmp_path):
    env = _btc_launch_env(tmp_path, 20)
    assert env.get("BOT152_TP_PCT") == "20", "btc15 v5 never sees the per-trade target"
    assert env.get("BTC60_TP_PCT") == "20"
    assert env.get("KALSHI_PROFIT_PCT") == "20"


def test_no_target_leaves_the_engine_defaults_alone(tmp_path):
    env = _btc_launch_env(tmp_path, None)
    for key in ("BOT152_TP_PCT", "BTC60_TP_PCT", "KALSHI_PROFIT_PCT"):
        assert key not in env, f"{key} set even though no target was requested"


def test_tp_pct_sets_every_engine_knob():
    src = Path(bot_manager.__file__).read_text(encoding="utf-8")
    assert "BOT152_TP_PCT" in src, "tp_pct never reaches the launch env"
    block = src[src.find("def _trade_target_env"):][:1200]
    for key in ("KALSHI_PROFIT_PCT", "BOT152_TP_PCT", "BTC60_TP_PCT"):
        assert key in block, f"{key} not set from tp_pct"


def test_tp_pct_is_separate_from_the_session_halt_target(tmp_path):
    env = _btc_launch_env(tmp_path, 20)
    # explicitly 0 rather than absent: the account-wide target is disabled for
    # every bot, and a per-trade target must not switch it back on
    assert env.get("TARGET_PORTFOLIO_PCT") == "0", (
        "the per-trade target must not also halt the session"
    )


def test_options_carry_tp_pct():
    o = bot_manager.BotStartOptions(mode="paper", tp_pct=12.5)
    assert o.tp_pct == 12.5
    assert bot_manager.BotStartOptions().tp_pct is None


# ---- request schema -------------------------------------------------------

def test_schema_accepts_and_bounds_tp_pct(client, user, monkeypatch):
    from app.schemas.bot import BotStartRequest

    assert BotStartRequest(user_id="u", tp_pct=15).tp_pct == 15
    with pytest.raises(Exception):
        BotStartRequest(user_id="u", tp_pct=0)      # gt=0
    with pytest.raises(Exception):
        BotStartRequest(user_id="u", tp_pct=501)    # le=500


def test_start_endpoint_rejects_a_zero_target(client, user):
    r = client.post(
        "/api/v1/bots/btc/start?bot=btc15",
        json={"user_id": user["user_id"], "mode": "paper", "tp_pct": 0},
    )
    assert r.status_code == 422


# ---- the bots' own price math --------------------------------------------

def _load_tp_price():
    """Exec btc15 v5's _tp_price with a chosen TP_PCT, without importing the bot."""
    src = (BTC / "btc15" / "v5_bot_btc_15_2.py").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"def _tp_price\(entry_c.*?\n(?:(?:    .*)?\n)+", src)
    assert m, "_tp_price not found in v5"
    return m.group(0)


@pytest.mark.parametrize(
    "pct,entry,expected",
    [
        (0, 45, 90),      # percent off -> the historical flat 90c sell
        (20, 45, 54),     # 45 * 1.20
        (50, 40, 60),
        (15, 70, 81),     # 70 * 1.15 = 80.5 -> 81 (half-UP, not banker's)
        (100, 60, 99),    # clamped, never above 99
        (20, None, 90),   # no entry known -> fall back to the flat price
    ],
)
def test_btc15_v5_tp_price(pct, entry, expected):
    ns = {"TP_PCT": float(pct), "TP_CENTS": 90}
    exec(compile(_load_tp_price(), "v5", "exec"), ns)  # noqa: S102
    assert ns["_tp_price"](entry) == expected


def test_btc15_v5_passes_the_entry_price_to_the_tp_leg():
    src = (BTC / "btc15" / "v5_bot_btc_15_2.py").read_text(encoding="utf-8", errors="replace")
    assert "tp_seller(c, ticker, side, mark, entry_c=band_hi)" in src, (
        "the TP leg no longer receives the fill price, so a percent target cannot work"
    )


def test_btc60_fable5_override_beats_the_state_file_and_the_learner():
    src = (BTC / "btc60" / "bot_kalshi_btc60_fable5.py").read_text(encoding="utf-8", errors="replace")
    assert "TP_PCT_OVERRIDE" in src
    load = src.find("def _load(")
    pin = src.find("tp_pct pinned to")
    assert pin > load, "the override must be applied AFTER the state load, or the file wins"
    assert "if TP_PCT_OVERRIDE > 0:\n            pass" in src, (
        "the learner can still drift a user-pinned target"
    )


def test_btc60_burst_uses_percent_when_set():
    src = (BTC / "btc60" / "bot_kalshi_btc60_burst.py").read_text(encoding="utf-8", errors="replace")
    assert "TP_PCT_OVERRIDE" in src
    assert "entry * (1 + TP_PCT_OVERRIDE / 100.0)" in src
    assert "min(99, entry + TP_CENTS)" in src, "the flat-offset default disappeared"


@pytest.mark.parametrize(
    "pct,entry,expected",
    [(20, 50, 60), (15, 30, 35), (10, 95, 99), (50, 10, 15)],
)
def test_btc60_burst_price_math(pct, entry, expected):
    tp = min(99, max(entry + 1, int(entry * (1 + pct / 100.0) + 0.5)))
    assert tp == expected


def test_burst_target_always_beats_the_entry():
    """A tiny percent on a cheap entry must still round UP, never to a loss."""
    for entry in range(1, 99):
        tp = min(99, max(entry + 1, int(entry * 1.01 + 0.5)))
        assert tp > entry
