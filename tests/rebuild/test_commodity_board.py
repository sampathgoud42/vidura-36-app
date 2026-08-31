"""The commodity board must emit the keys the panel reads.

This exists because the board rendered as a row of dashes with no error
anywhere. The data was real and the endpoint answered 200; the SHAPE had
changed. The rebuild emitted `bot_key` / `adx` / `side`, and the panel reads
`bot` / `m1_adx` / `m2_adx` / `signal`, so every lookup returned undefined and
React dutifully rendered the fallback for each one: no label, "—", "1m —",
"2m —", "mixed".

Nothing caught it. The contract test checks that PATHS are served, the
isolation tests check who may call them, and both pass while a handler
returns a correctly-shaped-looking object with entirely the wrong keys. A 200
carrying the wrong field names is indistinguishable from a quiet market, and
the operator has no way to tell.

So the check is against the frontend itself: the keys the component reads off
a row are extracted from the JSX, and the server has to emit all of them. It
cannot drift, because both halves come from the code rather than from a list
someone remembers to update.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PANEL = ROOT / "frontend/src/sites/botstation/BotStationSite.jsx"


def _keys_the_panel_reads() -> set[str]:
    """Every `r.<key>` inside the CommoditiesStrip component."""
    source = PANEL.read_text(encoding="utf-8")
    start = source.index("function CommoditiesStrip()")
    end = source.index("\nfunction ", start + 1)
    body = source[start:end]
    # r.foo and r.foo?.bar — the optional chain is still a read of `foo`.
    return set(re.findall(r"\br\.([a-zA-Z_][a-zA-Z0-9_]*)", body))


def test_the_panel_reads_keys_this_module_can_produce():
    """Given the keys the commodities panel reads off a row,
    when a row is built from bars,
    then every one of those keys is present.

    `error` is excluded: it is the panel's own branch for a failed row and is
    deliberately absent from a good one.
    """
    from app.domains.trading.market import board, commodities

    proxy = commodities.Proxy(bot_key="gold15", symbol="GLD", label="Gold")
    # Enough synthetic bars to clear the DMI minimum, with a real trend so the
    # indicator returns a side rather than None.
    bars = [{"time": f"2026-08-27 09:{m:02d}", "open": 100 + m,
             "high": 101 + m, "low": 99 + m, "close": 100.5 + m}
            for m in range(60)]
    row = board.row_from_bars(proxy.bot_key, proxy.label, proxy.symbol,
                              bars, "tradier")

    wanted = _keys_the_panel_reads() - {"error"}
    missing = sorted(wanted - set(row))
    assert not missing, (
        "the commodities panel reads keys the board does not emit: "
        + ", ".join(missing)
        + "\n\nA missing key is not an error anywhere -- the panel renders its "
          "fallback ('—', 'mixed') and the board looks like a flat market."
    )


def test_a_signal_needs_both_timeframes_to_agree():
    """Given 1m and 2m disagree,
    when the row is built,
    then there is no signal.

    Reported as disagreement rather than resolved in favour of the faster
    timeframe. Showing two timeframes exists precisely because either can be
    wrong, so collapsing them into one answer discards the reason they are
    both on screen.
    """
    from app.domains.trading.market import board, commodities

    proxy = commodities.Proxy(bot_key="gold15", symbol="GLD", label="Gold")
    bars = [{"time": f"2026-08-27 09:{m:02d}", "open": 100 + m,
             "high": 101 + m, "low": 99 + m, "close": 100.5 + m}
            for m in range(60)]
    row = board.row_from_bars(proxy.bot_key, proxy.label, proxy.symbol,
                              bars, "tradier")

    if row["m1_side"] and row["m1_side"] == row["m2_side"]:
        assert row["signal"] == row["m1_side"]
    else:
        assert row["signal"] is None


def test_the_source_follows_the_clock(monkeypatch):
    """Given the session window,
    when the board is built,
    then Tradier answers inside it and API Ninjas outside it.

    The rule the operator asked for, pinned. It had been Tradier in session
    and the yfinance futures engine outside, so the spot API was configured,
    keyed, and never called once.
    """
    from app.domains.trading.market import commodities

    called: list[str] = []

    monkeypatch.setattr(commodities, "proxies_from_registry",
                        lambda: [commodities.Proxy("gold15", "GLD", "Gold")])
    monkeypatch.setattr(commodities, "_bars_from_tradier",
                        lambda *a, **k: called.append("tradier") or [])
    monkeypatch.setattr(commodities, "_bars_from_api_ninjas",
                        lambda *a, **k: called.append("api_ninjas") or [])
    monkeypatch.setattr(commodities, "_bars_from_futures", lambda *a, **k: [])

    monkeypatch.setattr(commodities.clock, "is_regular_session",
                        lambda at=None: True)
    commodities.snapshot(cred=object(), force=True)
    assert called == ["tradier"], f"in session the board used {called}"

    called.clear()
    monkeypatch.setattr(commodities.clock, "is_regular_session",
                        lambda at=None: False)
    commodities.snapshot(cred=object(), force=True)
    assert called == ["api_ninjas"], f"outside the session the board used {called}"


def test_an_unanswerable_row_says_why(monkeypatch):
    """Given no source could produce bars,
    when the row is rendered,
    then it carries a reason rather than nulls.

    "Monthly quota exceeded" and "warming up, 6 of 29 bars" need different
    actions from the operator, and both look identical as a blank row.
    """
    from datetime import datetime

    from app.domains.trading.market import commodities

    monkeypatch.setattr(commodities, "proxies_from_registry",
                        lambda: [commodities.Proxy("gold15", "GLD", "Gold")])
    monkeypatch.setattr(commodities, "_bars_from_api_ninjas", lambda *a, **k: [])
    monkeypatch.setattr(commodities, "_bars_from_futures", lambda *a, **k: [])

    # A Saturday: outside the session, so the spot source is the one asked.
    snap = commodities.snapshot(cred=None, force=True,
                                at=datetime(2026, 8, 29, 22, 0))
    row = snap["rows"][0]
    assert row["bot"] == "gold15"
    assert row.get("error"), "an empty row must carry a reason, not just nulls"


# ---- ordering and the crypto board ----------------------------------------

def test_the_commodity_board_reads_gold_silver_oil():
    """Order comes from each bot's own config, not from the registry.

    The registry is sorted by KEY, which put oil between gold and silver — an
    ordering that means nothing to anyone reading the board. Declaring it per
    bot means a fourth commodity chooses its slot without touching the board.
    """
    from app.domains.botstation import registry
    from app.domains.trading.market import commodities

    registry.load_builtin_bots()
    assert [p.bot_key for p in commodities.proxies_from_registry()] == [
        "gold15", "silver15", "oil15"]


def test_a_bot_declaring_no_order_sorts_last_not_first():
    """A missing board_order must not jump the queue."""
    from app.domains.trading.market import commodities

    order = {"gold15": 1, "silver15": 2, "oil15": 3}
    keys = sorted(["zzz", "gold15", "oil15"],
                  key=lambda k: (order.get(k, 999), k))
    assert keys[-1] == "zzz"


def test_coinbase_candles_are_reversed_into_oldest_first():
    """Coinbase sends NEWEST first; every indicator here assumes oldest first.

    Feeding the list through unreversed computes DMI on a series running
    backwards through time — a plausible number with the trend inverted, and
    nothing downstream could detect it.
    """
    import httpx

    from app.domains.trading.market import crypto

    newest_first = [
        [1787981700, 1.0, 2.0, 1.5, 1.8, 10.0],
        [1787981640, 0.9, 1.9, 1.4, 1.5, 11.0],
        [1787981580, 0.8, 1.8, 1.3, 1.4, 12.0],
    ]

    class _Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return newest_first

    original = httpx.get
    httpx.get = lambda *a, **k: _Response()
    try:
        bars = crypto._bars_from_coinbase("BTC-USD")
    finally:
        httpx.get = original

    assert [b["time"] for b in bars] == [1787981580, 1787981640, 1787981700]
    assert bars[-1]["close"] == 1.8      # the newest candle is last


def test_both_boards_emit_the_same_row_shape():
    """The panels share one component, so a field only one board sends would
    render as a dash on the other with no error anywhere."""
    from app.domains.trading.market import board

    bars = [{"time": m, "open": 100 + m, "high": 101 + m,
             "low": 99 + m, "close": 100.5 + m} for m in range(60)]
    commodity = board.row_from_bars("gold15", "Gold", "GLD", bars, "tradier")
    crypto_row = board.row_from_bars("btc", "BTC", "BTC-USD", bars, "coinbase")
    assert set(commodity) == set(crypto_row)


def test_the_crypto_board_lists_all_eight_coins():
    """BTC, ETH, SOL, DOGE, XRP, BNB, ZEC, HYPE — all against USD.

    The quote pair matters and is not interchangeable: ZEC-USDC is a
    different book at a different price entirely (~$53 against ~$800), so a
    pair chosen carelessly shows a real number for the wrong asset.
    """
    from app.domains.trading.market import crypto

    assert [c.key for c in crypto.COINS] == [
        "btc", "eth", "sol", "doge", "xrp", "bnb", "zec", "hype"]
    assert all(c.product.endswith("-USD") for c in crypto.COINS)


def test_both_boards_carry_four_timeframes():
    from app.domains.trading.market import board

    assert board.TIMEFRAMES == {"m1": 1, "m2": 2, "m5": 5, "m10": 10}

    bars = [{"time": f"2026-08-29 {9 + m // 60:02d}:{m % 60:02d}",
             "open": 100 + m, "high": 101 + m, "low": 99 + m,
             "close": 100.5 + m} for m in range(400)]
    row = board.row_from_bars("btc", "BTC", "BTC-USD", bars, "coinbase")
    for key in ("m1", "m2", "m5", "m10"):
        assert row[f"{key}_adx"] is not None, f"{key} did not compute"
    assert row["bars_10m"] >= 29


def test_a_gap_does_not_discard_the_whole_series():
    """Only the FORMING bar is dropped when short, not every short bucket.

    A thinly traded market publishes no candle for a minute with no trades,
    so most of its buckets are short. Discarding them all took BNB from ~106
    five-minute bars to 15 — below what an ADX needs, so the column went
    blank with nothing anywhere saying why.
    """
    from app.domains.trading.market import indicators

    # 60 minutes of clock time with every third minute missing.
    gappy = [{"time": f"2026-08-29 10:{m:02d}", "open": 1, "high": 2,
              "low": 1, "close": 1.5} for m in range(60) if m % 3]
    folded = indicators.aggregate(gappy, 5)
    # 12 five-minute windows exist; the last is the forming one.
    assert len(folded) >= 11, (
        f"only {len(folded)} buckets survived a gappy feed — interior "
        "buckets missing a minute are still the right time window")


def test_the_forming_bar_is_still_dropped():
    """The rule it was meant to be: a short bucket at the right-hand edge is
    the bar still filling, and keeping it makes the newest reading flicker."""
    from app.domains.trading.market import indicators

    # Two full 5-minute windows, then a third with only one minute in it.
    bars = [{"time": f"2026-08-29 10:{m:02d}", "open": 1, "high": 2,
             "low": 1, "close": 1.5} for m in range(11)]
    assert len(indicators.aggregate(bars, 5)) == 2
