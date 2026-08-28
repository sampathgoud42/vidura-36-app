"""Account-wide halts are off; risk is per bot (user 07/30).

The Kalshi account is shared by the sports, BTC and perp bots, so a floor or
profit target on its JOINT portfolio value let one bot's drawdown stop the
others — and a small balance stopped everything. Each bot now carries its own
bankroll and its own target on that bankroll.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models import User
from app.services import bot_manager
from app.services.bot_registry import get_bot

RUNTIME = Path(__file__).resolve().parents[1] / "runtime" / "prediction-trade" / "kalshi"


def _env(tmp_path, bot_key="btc15", mode="paper", **opts):
    root = tmp_path / "u"
    (root / "trade_history").mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    user = User(user_id="u1", username="u", user_root_folder=str(root))
    spec = get_bot(bot_key)
    version = spec.versions[0]
    options = bot_manager.BotStartOptions(mode=mode, **opts)
    try:
        _argv, _cwd, env = bot_manager._launch_plan(spec, version, user, options)
    except bot_manager.BotManagerError as exc:
        pytest.skip(f"{bot_key} not launchable here: {exc}")
    return env


# ---- the floor ------------------------------------------------------------

@pytest.mark.parametrize("mode", ["paper", "live"])
@pytest.mark.parametrize("bot_key", ["btc15", "btc60", "sports"])
def test_portfolio_floor_is_zero_in_every_mode_for_every_bot(tmp_path, bot_key, mode):
    env = _env(tmp_path, bot_key=bot_key, mode=mode)
    assert env["DO_NOT_BUY_IF_PORTFOLIO_BELOW"] == "0"


def test_an_inherited_floor_cannot_re_arm_the_halt(tmp_path, monkeypatch):
    """setdefault would have let the operator's shell put the floor back."""
    monkeypatch.setenv("DO_NOT_BUY_IF_PORTFOLIO_BELOW", "100")
    env = _env(tmp_path, bot_key="btc15", mode="live")
    assert env["DO_NOT_BUY_IF_PORTFOLIO_BELOW"] == "0"


# ---- machine shutdown -----------------------------------------------------

@pytest.mark.parametrize("mode", ["paper", "live"])
def test_halt_never_powers_off_the_host(tmp_path, mode):
    assert _env(tmp_path, mode=mode)["HALT_MACHINE_SHUTDOWN"] == "FALSE"


def test_an_inherited_shutdown_flag_is_overridden(tmp_path, monkeypatch):
    monkeypatch.setenv("HALT_MACHINE_SHUTDOWN", "TRUE")
    assert _env(tmp_path)["HALT_MACHINE_SHUTDOWN"] == "FALSE"


# ---- env files ------------------------------------------------------------

def test_tracked_env_files_disable_the_account_wide_halts():
    env_file = RUNTIME / "sports" / "kaslhi_sports.env"
    text = env_file.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        bare = line.strip()
        if bare.startswith("#") or "=" not in bare:
            continue
        key, _, value = bare.partition("=")
        key, value = key.strip(), value.split("#")[0].strip()
        if key == "TARGET_PORTFOLIO_PCT":
            assert value == "0", f"account-PV target halt re-enabled: {bare}"
        if key == "DO_NOT_BUY_IF_PORTFOLIO_BELOW":
            assert value == "0", f"account-PV floor re-enabled: {bare}"
        if key == "HALT_MACHINE_SHUTDOWN":
            assert value.upper() == "FALSE", f"machine shutdown re-enabled: {bare}"


def test_btc60_floor_defaults_to_disabled():
    src = (RUNTIME / "btc" / "btc60" / "bot_kalshi_btc60_fable5.py").read_text(
        encoding="utf-8", errors="replace"
    )
    assert 'getenv("BTC60_MIN_BANKROLL", "0")' in src, "btc60 floor is not opt-in"
    assert "if MIN_PORTFOLIO_HALT > 0 and bank < MIN_PORTFOLIO_HALT:" in src, (
        "btc60 still halts on a bankroll floor unconditionally"
    )


# ---- per-bot bankroll + target -------------------------------------------

@pytest.mark.parametrize("bot_key", ["btc15", "btc60"])
def test_bank_and_target_reach_a_btc_launch(tmp_path, bot_key):
    env = _env(tmp_path, bot_key=bot_key, bank=250, target_pct=40)
    assert env["BTC_BANKROLL"] == "250"
    assert env["BTC15_TARGET_PCT"] == "40"
    assert env["BTC60_TARGET_PCT"] == "40"


@pytest.mark.parametrize("bot_key", ["btc15", "btc60", "sports"])
def test_account_wide_target_is_off_unless_sports_asks(tmp_path, bot_key):
    """A TARGET_PORTFOLIO_PCT inherited from the shell must not score a bot
    against the shared account."""
    env = _env(tmp_path, bot_key=bot_key, bank=250, target_pct=40)
    if bot_key == "sports":
        return  # sports still maps target_pct onto its own bank logic
    assert env["TARGET_PORTFOLIO_PCT"] == "0"


def test_btc15_target_is_measured_on_its_own_bankroll():
    src = (RUNTIME / "btc" / "btc15" / "v4_bot_kalshi_btc15.py").read_text(
        encoding="utf-8", errors="replace"
    )
    assert "class Bankroll" in src, "btc15 has no bankroll ledger"
    assert "self.start * (1 + BTC15_TARGET_PCT / 100.0)" in src
    assert "if BANKROLL.target_reached():" in src, "the target never gates new orders"
    assert "BANKROLL.settle(pnl)" in src, "the ledger never moves on realized P&L"


def test_btc15_floor_defaults_to_disabled():
    src = (RUNTIME / "btc" / "btc15" / "v4_bot_kalshi_btc15.py").read_text(
        encoding="utf-8", errors="replace"
    )
    assert 'getenv("DO_NOT_BUY_IF_PORTFOLIO_BELOW", "0")' in src
    assert "if DO_NOT_BUY_IF_PORTFOLIO_BELOW > 0 and pv < DO_NOT_BUY_IF_PORTFOLIO_BELOW:" in src


def test_btc15_bankroll_is_fresh_every_start():
    # Contract changed 08/03: EVERY start resets the ledger to the typed
    # seed. The old resume-when-seed-unchanged path must stay gone, or a
    # previous session's balance decides when the new session's target/SL
    # fire.
    src = (RUNTIME / "btc" / "btc15" / "v4_bot_kalshi_btc15.py").read_text(
        encoding="utf-8", errors="replace"
    )
    assert 'float(d.get("start", 0)) == self.start' not in src, (
        "the resume-on-same-seed path is back - sessions would inherit "
        "the previous ledger"
    )
    assert "self.balance = self.start" in src, "the fresh reset is missing"


def test_nothing_is_set_when_no_bankroll_is_given(tmp_path):
    env = _env(tmp_path, bot_key="btc60")
    assert "BTC_BANKROLL" not in env
    assert "BTC60_TARGET_PCT" not in env


def test_btc60_target_is_measured_on_its_own_bankroll():
    src = (RUNTIME / "btc" / "btc60" / "bot_kalshi_btc60_fable5.py").read_text(
        encoding="utf-8", errors="replace"
    )
    assert "def target_reached" in src
    assert "self.start_bankroll * (1 + BTC_TARGET_PCT / 100.0)" in src, (
        "target is not computed from this bot's own bankroll"
    )
    assert "if learner.target_reached():" in src, "the target never gates new entries"


def test_btc60_learner_is_fresh_every_start():
    # Contract changed 08/03: the learner no longer restores tp/sl/pv/
    # bid_lo/bankroll from its state file - every session starts at the
    # seed and the defaults (or the operator's pins).
    src = (RUNTIME / "btc" / "btc60" / "bot_kalshi_btc60_fable5.py").read_text(
        encoding="utf-8", errors="replace"
    )
    assert 'self.tp_pct = float(d.get("tp_pct"' not in src, (
        "the learner resumes tp_pct from the state file again"
    )
    assert 'self.bankroll = float(d.get("bankroll"' not in src, (
        "the learner resumes the bankroll from the state file again"
    )
    assert "fresh session resets to seed/defaults" in src


def test_bank_is_rejected_when_not_positive():
    from app.schemas.bot import BotStartRequest

    assert BotStartRequest(user_id="u", bank=250).bank == 250
    with pytest.raises(Exception):
        BotStartRequest(user_id="u", bank=0)
    with pytest.raises(Exception):
        BotStartRequest(user_id="u", bank=-5)
