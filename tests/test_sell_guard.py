"""No bot may sell contracts it does not hold.

Kalshi's V2 book is single-sided and quoted from the YES leg, so "sell YES" is
an ASK. An ASK with no YES inventory does not get rejected - it OPENS A SHORT,
which on this venue reads as a NO position. A stale sell is therefore not a
no-op, it is a brand new trade in the opposite direction.

That happened live on 2026-08-27 (Britt Du Pree, sports/tennis): the 97c
take-profit filled at 1:43pm and flattened 25 YES bought at 57c - a clean
+$10.00. A second exit fired at 1:46pm, sold 25 YES the account no longer had,
and opened 25 NO. Closing that at 2:12pm cost $23.22 and left the round trip
at -$8.02.

The bots import the launcher's module aliasing and expect live credentials, so
these tests do what tests/test_kalshi_v2_endpoints.py does: lift the guard out
of the source and exercise it directly, against a fake client. That tests the
behaviour rather than the wiring, and the wiring is asserted separately at the
bottom.
"""

from __future__ import annotations

import ast
import asyncio
import re
from pathlib import Path

import pytest

def run(coro):
    """No pytest-asyncio in this project - drive it directly."""
    return asyncio.run(coro)


KALSHI = Path(__file__).resolve().parents[1] / "runtime" / "prediction-trade" / "kalshi"
BTC15 = KALSHI / "btc" / "btc15" / "v4_bot_kalshi_btc15.py"
BTC60 = KALSHI / "btc" / "btc60" / "bot_kalshi_btc60_fable5.py"


# ── harness ──────────────────────────────────────────────────────────────────

class FakeClient:
    """Stands in for KalshiClient. Never reached by the guard itself."""


def _load_guard(path: Path, position_for):
    """exec just `sellable_contracts` out of a bot, with its deps stubbed."""
    src = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    fn = next((n for n in tree.body
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "sellable_contracts"),
              None)
    assert fn is not None, f"{path.name}: sellable_contracts not found"

    import asyncio
    import sys as _sys

    ns = {
        "asyncio": asyncio,
        "sys": _sys,
        "position_for": position_for,
        "KalshiClient": FakeClient,
        # no real sleeping in tests
        "SELL_GUARD_RETRIES": 3,
        "SELL_GUARD_DELAY_S": 0.0,
        "_log": lambda *a, **k: None,
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), "exec"), ns)
    return ns["sellable_contracts"]


def _btc15_guard(position_for):
    return _load_guard(BTC15, position_for)


def _btc60_guard(position_for):
    return _load_guard(BTC60, position_for)


def _pos(contracts: int, side: str = "yes") -> dict:
    """A /portfolio/positions row as position_for returns it (btc15 shape)."""
    fp = contracts if side == "yes" else -contracts
    return {"contracts": abs(contracts), "position_fp": str(fp)}


# ── the incident: selling into a flat account ────────────────────────────────

def test_flat_account_sells_nothing_btc15():
    """The Britt Du Pree case. TP filled, position gone, second exit fires."""
    async def position_for(c, ticker):
        return None                       # flat - the TP already closed it

    guard = _btc15_guard(position_for)
    assert run(guard(FakeClient(), "KXTENNIS", "yes", 25, tag="TP")) == 0


def test_flat_account_sells_nothing_btc60():
    async def position_for(c, ticker):
        return 0, None

    guard = _btc60_guard(position_for)
    assert run(guard(FakeClient(), "KXBTCD", "yes", 1, "TP")) == 0


# ── clamping: never more than is held ────────────────────────────────────────

def test_partial_position_is_clamped_not_overshot():
    """A partial exit leaves 10 of 25. Selling the remembered 25 would short 15."""
    async def position_for(c, ticker):
        return _pos(10)

    guard = _btc15_guard(position_for)
    assert run(guard(FakeClient(), "KXTENNIS", "yes", 25, tag="EXIT")) == 10


def test_full_position_sells_in_full():
    async def position_for(c, ticker):
        return _pos(25)

    guard = _btc15_guard(position_for)
    assert run(guard(FakeClient(), "KXTENNIS", "yes", 25, tag="TP")) == 25


def test_holding_more_than_asked_still_sells_only_what_was_asked():
    """The guard is a ceiling, not a target - it must not enlarge an exit."""
    async def position_for(c, ticker):
        return _pos(100)

    guard = _btc15_guard(position_for)
    assert run(guard(FakeClient(), "KXTENNIS", "yes", 25, tag="EXIT")) == 25


# ── side: selling the other leg also opens a position ────────────────────────

def test_selling_the_wrong_leg_sells_nothing():
    """Holding NO and selling YES is not an exit, it is a second short."""
    async def position_for(c, ticker):
        return _pos(25, side="no")

    guard = _btc15_guard(position_for)
    assert run(guard(FakeClient(), "KXTENNIS", "yes", 25, tag="EXIT")) == 0


def test_selling_the_leg_actually_held_is_allowed():
    async def position_for(c, ticker):
        return _pos(25, side="no")

    guard = _btc15_guard(position_for)
    assert run(guard(FakeClient(), "KXTENNIS", "no", 25, tag="EXIT")) == 25


# ── fail safe ────────────────────────────────────────────────────────────────

def test_fetch_error_sells_nothing():
    """An unknown position is not an empty one - and it is not a sellable one."""
    async def position_for(c, ticker):
        raise RuntimeError("kalshi 503")

    guard = _btc15_guard(position_for)
    assert run(guard(FakeClient(), "KXTENNIS", "yes", 25, tag="EXIT")) == 0


def test_zero_request_never_reaches_the_venue():
    calls = []

    async def position_for(c, ticker):
        calls.append(ticker)
        return _pos(25)

    guard = _btc15_guard(position_for)
    assert run(guard(FakeClient(), "KXTENNIS", "yes", 0, tag="EXIT")) == 0
    assert calls == [], "a zero-count sell should not even cost a position fetch"


# ── the retry that keeps the opening take-profit working ─────────────────────

def test_position_visible_only_on_a_later_read_is_still_sellable():
    """A just-filled buy lags in /portfolio/positions. Without the retry the
    opening TP would race the fill and silently stop being placed."""
    reads = {"n": 0}

    async def position_for(c, ticker):
        reads["n"] += 1
        return _pos(25) if reads["n"] >= 2 else None

    guard = _btc15_guard(position_for)
    assert run(guard(FakeClient(), "KXTENNIS", "yes", 25, tag="TP")) == 25
    assert reads["n"] == 2


def test_retries_are_bounded():
    reads = {"n": 0}

    async def position_for(c, ticker):
        reads["n"] += 1
        return None

    guard = _btc15_guard(position_for)
    assert run(guard(FakeClient(), "KXTENNIS", "yes", 25, tag="TP")) == 0
    assert reads["n"] == 3, "should stop after SELL_GUARD_RETRIES reads"


# ── the wiring: the guard must sit between the caller and the POST ───────────

def _fn_source(path: Path, name: str) -> str:
    src = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"{path.name}: {name} not found")


@pytest.mark.parametrize("path,fn", [
    (BTC15, "place_tp_sell"),
    (BTC15, "_fire_sale"),
    (BTC60, "place_order"),
])
def test_every_sell_primitive_calls_the_guard(path, fn):
    body = _fn_source(path, fn)
    assert "sellable_contracts(" in body, (
        f"{path.name}:{fn} places an order without confirming the position")


@pytest.mark.parametrize("path,fn", [
    (BTC15, "place_tp_sell"),
    (BTC15, "_fire_sale"),
    (BTC60, "place_order"),
])
def test_the_guard_runs_before_the_order_is_built(path, fn):
    """_mk_order must not be reached with an unverified count: the clamped
    number has to be the one the body is built from."""
    body = _fn_source(path, fn)
    guard_at = body.index("sellable_contracts(")
    mk_at = body.index("_mk_order(")
    assert guard_at < mk_at, (
        f"{path.name}:{fn} builds the order before confirming the position — "
        f"the clamped count never reaches it")


def _sell_sites(path: Path):
    """(line, snippet) for every place a SELL order body is constructed."""
    src = path.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r'_mk_order\(\s*[^,()]+,\s*"sell"', src):
        yield src[: m.start()].count("\n") + 1, src


# Every bot file that can send an order. Scanned as a whole so a NEW sell
# added anywhere has to answer for itself.
ALL_BOTS = sorted(
    p for p in KALSHI.rglob("*.py")
    if "__pycache__" not in p.parts and '_mk_order(' in
    p.read_text(encoding="utf-8", errors="replace")
)

# How far above a sell the count must have been established. Generous enough
# for a log line and a comment, tight enough that an unrelated read 200 lines
# up does not count as confirmation.
LOOKBACK_LINES = 14

# Reading the live position and selling THAT number is the same invariant the
# guard enforces; the commodity bots and btc15 v5 were already written this
# way, and rewriting working exit logic to route through a new helper would be
# churn with real risk attached.
DERIVES_FROM_LIVE_POSITION = ("sellable_contracts(", "position_contracts(",
                              "position_for(")


def test_every_sell_site_confirms_the_position_first():
    """Not per-function: per SITE.

    An earlier version of this test asked whether the enclosing function
    mentioned the guard anywhere, and v4's run() is ~900 lines with five
    separate sell sites in it — guarding one made the other four pass
    vacuously. Three unguarded sells hid behind that for a full test run.
    """
    offenders = []
    for path in ALL_BOTS:
        for line, src in _sell_sites(path):
            lines = src.splitlines()
            window = "\n".join(lines[max(0, line - 1 - LOOKBACK_LINES): line])
            if not any(tok in window for tok in DERIVES_FROM_LIVE_POSITION):
                offenders.append(f"{path.relative_to(KALSHI)}:{line}")
    assert not offenders, (
        "sell order(s) built from a remembered count, with no live position "
        "read in the " + str(LOOKBACK_LINES) + " lines above. Selling a "
        "position that is already closed does not fail on Kalshi - it opens "
        "the opposite one:\n  " + "\n  ".join(offenders))


def test_the_scan_actually_finds_the_known_sell_sites():
    """A scan that silently matches nothing would pass forever."""
    found = {p.name: len(list(_sell_sites(p))) for p in ALL_BOTS}
    assert found.get("v4_bot_kalshi_btc15.py", 0) >= 5, found
    assert found.get("v2_bot_kalshi_gold15.py", 0) >= 1, found
    assert sum(found.values()) >= 12, found
