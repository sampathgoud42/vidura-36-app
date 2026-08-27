"""No bot may call a deprecated Kalshi V1 order endpoint.

Kalshi retired the V1 order paths: DELETE /portfolio/orders/{id} answers

    HTTP 410 {"error":{"code":"deprecated_v1_order_endpoint", ...}}

The bots swallow cancel failures (they log and continue), so a regression here
is silent and expensive: an unfilled order rests forever, holding capital and
skewing position checks. This scans the vendored runtime instead of trusting
review.

Verified against the docs 2026-07-29:
  create : POST   /portfolio/events/orders          (V2)
  cancel : DELETE /portfolio/events/orders/{id}     (V2)
  list   : GET    /portfolio/orders                 (current — NOT deprecated)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RUNTIME = Path(__file__).resolve().parents[1] / "runtime" / "prediction-trade" / "kalshi"

# DELETE/POST against the bare order collection is the V1 shape.
V1_ORDER_WRITE = re.compile(
    r'req\(\s*"(DELETE|POST)"\s*,\s*f?"(/portfolio/orders(?:/\{[^"]*\})?)"'
)

# GET /portfolio/orders is still current; only writes moved.
ALLOWED_GET = '/portfolio/orders'


def _py_files() -> list[Path]:
    return sorted(p for p in RUNTIME.rglob("*.py") if "__pycache__" not in p.parts)


def test_runtime_is_vendored():
    assert RUNTIME.is_dir(), f"vendored runtime missing at {RUNTIME}"
    assert _py_files(), "no bot sources found to scan"


def test_no_bot_writes_to_a_v1_order_endpoint():
    offenders: list[str] = []
    for path in _py_files():
        src = path.read_text(encoding="utf-8", errors="replace")
        for m in V1_ORDER_WRITE.finditer(src):
            line = src[: m.start()].count("\n") + 1
            offenders.append(f"{path.relative_to(RUNTIME)}:{line} -> {m.group(1)} {m.group(2)}")
    assert not offenders, (
        "deprecated V1 order endpoint(s) — Kalshi answers HTTP 410; "
        "use /portfolio/events/orders:\n  " + "\n  ".join(offenders)
    )


def test_cancels_use_the_v2_event_path():
    """At least one real cancel exists and every cancel uses the V2 path."""
    cancels = 0
    for path in _py_files():
        src = path.read_text(encoding="utf-8", errors="replace")
        cancels += len(re.findall(r'"DELETE"\s*,\s*f?"/portfolio/events/orders/', src))
    assert cancels >= 10, f"expected the migrated cancel sites, found {cancels}"


def test_listing_orders_is_still_allowed():
    """Guards over-correction: GET /portfolio/orders is current, and blanket
    -replacing it would break resting-order discovery."""
    gets = 0
    for path in _py_files():
        src = path.read_text(encoding="utf-8", errors="replace")
        gets += len(re.findall(r'"GET"\s*,\s*f?"' + re.escape(ALLOWED_GET) + r'"', src))
    assert gets >= 1, "resting-order listing disappeared"


@pytest.mark.parametrize(
    "bot",
    [
        "sports/bot_kalshi_main.py",
        "sports/bot_kalshi_sports_v1.py",
        "sports/bot_kalshi_sports_v2.py",
        "btc/btc15/v4_bot_kalshi_btc15.py",
        "btc/btc60/bot_kalshi_btc60_fable5.py",
        "btc/btc60/bot_kalshi_btc60_burst.py",
    ],
)
def test_each_trading_bot_is_clean(bot):
    path = RUNTIME / bot
    if not path.is_file():
        pytest.skip(f"{bot} not vendored")
    src = path.read_text(encoding="utf-8", errors="replace")
    assert not V1_ORDER_WRITE.search(src), f"{bot} still writes to a V1 order endpoint"
