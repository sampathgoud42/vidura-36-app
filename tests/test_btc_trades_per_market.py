"""One trade per market is the BTC default (user 07/30).

Re-entering the same market doubles exposure to a single BTC move that has
already gone against the first entry. For btc15 the market is the 15-minute
event; for btc60 it is the hourly one — the engines spell the cap differently
but MAX_TRADES_PER_MARKET is the one name that sets them all.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BTC = Path(__file__).resolve().parents[1] / "runtime" / "prediction-trade" / "kalshi" / "btc"

ENGINES = [
    ("btc15/v4_bot_kalshi_btc15.py", "MAX_TRADES_PER_MARKET"),
    ("btc60/bot_kalshi_btc60_fable5.py", "MAX_TRADES_PER_HOUR"),
    ("btc60/bot_kalshi_btc60_burst.py", "MAX_TRADES_PER_HOUR"),
]


def _assignment(rel: str, name: str) -> str:
    src = (BTC / rel).read_text(encoding="utf-8", errors="replace")
    m = re.search(rf"^{name}\s*=\s*(.+)$", src, re.M)
    assert m, f"{rel}: {name} not found"
    return m.group(1)


@pytest.mark.parametrize("rel,name", ENGINES)
def test_default_is_one_trade_per_market(rel, name):
    line = _assignment(rel, name)
    assert '"MAX_TRADES_PER_MARKET", "1"' in line, (
        f"{rel}: {name} does not default to 1 — got {line.strip()}"
    )


@pytest.mark.parametrize("rel,name", ENGINES)
def test_the_cap_stays_overridable(rel, name):
    """A default, not a hard-code: MAX_TRADES_PER_MARKET must still be read."""
    assert "getenv" in _assignment(rel, name)


@pytest.mark.parametrize("rel,name", ENGINES)
def test_every_engine_reads_the_same_env_name(rel, name):
    assert "MAX_TRADES_PER_MARKET" in _assignment(rel, name), (
        f"{rel} uses a different knob, so one setting cannot cover the BTC world"
    )


def test_v2_and_v3_inherit_the_cap_rather_than_redefining_it():
    """They import from v1 (aliased to v4), so the default lands once."""
    for rel in ("btc15/v2_bot_kalshi_btc15.py", "btc15/v3_bot_kalshi_btc15.py"):
        src = (BTC / rel).read_text(encoding="utf-8", errors="replace")
        assert re.search(r"^MAX_TRADES_PER_MARKET\s*=\s*v1\.MAX_TRADES_PER_MARKET", src, re.M), (
            f"{rel} no longer inherits the cap — its default could drift"
        )


def test_v5_is_already_one_per_market():
    """v5 has no counter: it records each traded ticker and skips it after."""
    src = (BTC / "btc15" / "v5_bot_btc_15_2.py").read_text(encoding="utf-8", errors="replace")
    assert 'if ticker in st["traded"]' in src, (
        "v5 lost its per-market guard, so it could re-enter the same market"
    )


@pytest.mark.parametrize("rel,name", ENGINES)
def test_the_loop_actually_honours_the_cap(rel, name):
    src = (BTC / rel).read_text(encoding="utf-8", errors="replace")
    assert re.search(rf"{name}\s*\+\s*1|<\s*{name}|>=\s*{name}", src), (
        f"{rel}: {name} is defined but never bounds the trade loop"
    )
