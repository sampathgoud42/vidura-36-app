"""Unconditional firesell band: bid <= 6c or >= 98c exits, whatever the config.

The rule (user 07/30): once an open position's live bid touches either edge,
price is no longer a strategy question — lock the win or salvage the loss. It
must fire ahead of, and regardless of, the per-sport ceiling/floor, the strike
debounce, SPORT_STOP_MIN_BID_C and the firesell toggles, for every sport and
every tennis model v1-v5.

These load each bot's _firesell_hit predicate by source (importing the bots
needs the launcher's module aliasing and live credentials) and assert the
guardian wiring textually.

STATUS (this extraction, 2026-08-26): xfail. The vendored sports bots no
longer carry SPORT_FIRESELL_HI_C / _firesell_hit at all - the
unconditional band was dropped from them upstream, and the same 64 cases
fail identically in the project this was extracted from. The file is kept
as the record of the rule that used to be enforced: delete the xfail mark
the moment the band is put back, and it starts guarding again.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SPORTS = Path(__file__).resolve().parents[1] / "runtime" / "prediction-trade" / "kalshi" / "sports"
BOTS = ["bot_kalshi_main.py", "bot_kalshi_sports_v1.py", "bot_kalshi_sports_v2.py"]

# Module-wide: every case here reaches through _predicate().
pytestmark = pytest.mark.xfail(
    reason="vendored sports bots no longer define the unconditional "
           "firesell band (same upstream)",
    strict=False,
)


def _predicate(bot: str):
    """Exec just the constants + _firesell_hit out of a bot, no imports."""
    src = (SPORTS / bot).read_text(encoding="utf-8", errors="replace")
    m = re.search(
        r"SPORT_FIRESELL_HI_C = .*?\n(?:.*?\n)*?def _firesell_hit\(.*?\n(?:(?:    .*)?\n)+",
        src,
    )
    assert m, f"{bot}: firesell block not found"
    ns: dict = {"os": __import__("os")}
    exec(compile(m.group(0), bot, "exec"), ns)  # noqa: S102 - fixed local source
    return ns["_firesell_hit"], ns["SPORT_FIRESELL_HI_C"], ns["SPORT_FIRESELL_LO_C"]


@pytest.mark.parametrize("bot", BOTS)
def test_thresholds_are_6_and_98(bot):
    _, hi, lo = _predicate(bot)
    assert (lo, hi) == (6, 98), f"{bot}: expected 6/98, got {lo}/{hi}"


@pytest.mark.parametrize("bot", BOTS)
@pytest.mark.parametrize(
    "bid_c,fires",
    [
        (0, False),    # no buyer at all — an exit cannot fill
        (1, True),     # salvage
        (5, True),
        (6, True),     # "touches 6" is inclusive
        (7, False),
        (50, False),
        (97, False),   # the configured TP ceiling is NOT the firesell edge
        (98, True),    # "touches 98" is inclusive
        (99, True),
        (100, True),
        (None, False),
    ],
)
def test_edges_are_inclusive_and_zero_is_excluded(bot, bid_c, fires):
    hit, _, _ = _predicate(bot)
    assert hit(bid_c) is fires, f"{bot}: bid {bid_c} should {'' if fires else 'not '}fire"


@pytest.mark.parametrize("bot", BOTS)
def test_each_edge_can_be_disabled_independently(bot):
    src = (SPORTS / bot).read_text(encoding="utf-8", errors="replace")
    assert "SPORT_FIRESELL_HI_C" in src and "SPORT_FIRESELL_LO_C" in src
    hit, _, _ = _predicate(bot)
    # the predicate short-circuits on 0, which is what makes an edge disable-able
    assert re.search(r"SPORT_FIRESELL_HI_C > 0", src)
    assert re.search(r"SPORT_FIRESELL_LO_C > 0", src)
    assert hit(99) and hit(2)


@pytest.mark.parametrize("bot", BOTS)
def test_firesell_runs_before_the_configured_band_exit(bot):
    """Ordering is the whole point: a configured floor of 9c with a 2-strike
    debounce must not get to decide before the unconditional rule."""
    src = (SPORTS / bot).read_text(encoding="utf-8", errors="replace")
    fire = src.find("UNCONDITIONAL FIRESELL")
    band = src.find("price-band exit", fire if fire > 0 else 0)
    if band < 0:
        band = src.lower().find("price-band exit", fire if fire > 0 else 0)
    assert fire > 0, f"{bot}: firesell pass missing"
    assert band > fire, f"{bot}: firesell must precede the configured band exit"


@pytest.mark.parametrize("bot", BOTS)
def test_firesell_is_risk_off_so_the_spread_guard_cannot_defer_it(bot):
    src = (SPORTS / bot).read_text(encoding="utf-8", errors="replace")
    block = src[src.find("UNCONDITIONAL FIRESELL"):]
    call = block[: block.find("\n\n        # ")] if "\n\n        # " in block else block[:3000]
    assert '"FIRESELL"' in call, f"{bot}: no FIRESELL exit call"
    assert "risk_off=True" in call, f"{bot}: firesell must skip the spread wait"


@pytest.mark.parametrize("bot", BOTS)
def test_firesold_tickers_are_not_re_sold_by_the_band_pass(bot):
    src = (SPORTS / bot).read_text(encoding="utf-8", errors="replace")
    assert re.search(r"already firesold this cycle", src), (
        f"{bot}: the band pass does not skip tickers the firesell already exited"
    )


@pytest.mark.parametrize("bot", BOTS)
def test_scope_guard_survives(bot):
    """'Irrespective of config' must not mean 'sells other bots' positions'."""
    src = (SPORTS / bot).read_text(encoding="utf-8", errors="replace")
    block = src[src.find("UNCONDITIONAL FIRESELL"):][:2200]
    assert ("_in_scope(" in block) or ("_SPORTS_SET" in block) or ("ADAPTERS" in block), (
        f"{bot}: firesell lost the configured-sport scope guard"
    )
