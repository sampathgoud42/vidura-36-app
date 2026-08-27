"""SPY 0DTE dealer gamma computed from getgamma.io's raw option chain.

The vendor returns per-contract gamma/OI/strike and computes the headline
numbers in its own dashboard, so this service does the maths. These tests
pin that maths — no network, hand-built chains with known answers.
"""

from __future__ import annotations

import pytest

from app.services import gex0dte


def _c(kind: str, strike: float, gamma: float, oi: float) -> dict:
    return {"contract_type": kind, "strike_price": strike,
            "open_interest": oi, "greeks": {"gamma": gamma}}


def _chain(contracts, spot=738.0) -> dict:
    return {"ticker": "SPY", "spotPrice": spot, "mode": "0dte",
            "timestamp": "2026-07-30T17:00:00Z", "marketStatus": "open",
            "marketOpen": True, "contracts": contracts}


# ---- the maths ------------------------------------------------------------

def test_net_gex_is_calls_minus_puts_in_dollar_gamma():
    spot = 100.0
    out = gex0dte.compute(_chain([_c("call", 100, 0.05, 1000),
                                  _c("put", 100, 0.02, 1000)], spot=spot))
    unit = 100 * spot * spot * 0.01          # multiplier x spot^2 x 1%
    assert out["net_gex"] == pytest.approx((0.05 - 0.02) * 1000 * unit)


def test_regime_follows_the_sign_of_net_gex():
    pos = gex0dte.compute(_chain([_c("call", 740, 0.05, 9000), _c("put", 730, 0.01, 100)]))
    neg = gex0dte.compute(_chain([_c("call", 740, 0.01, 100), _c("put", 730, 0.05, 9000)]))
    assert pos["regime"] == "POS" and pos["net_gex"] > 0
    assert neg["regime"] == "NEG" and neg["net_gex"] < 0


def test_walls_are_the_open_interest_peaks_per_side():
    out = gex0dte.compute(_chain([
        _c("call", 740, 0.05, 9000),   # most call OI
        _c("call", 744, 0.03, 3000),
        _c("put", 726, 0.02, 8000),    # most put OI
        _c("put", 733, 0.04, 4000),
    ]))
    assert out["call_wall"] == 740
    assert out["put_wall"] == 726


def test_the_put_wall_is_oi_not_the_gamma_peak():
    """Checked against getgamma 2026-07-30: it showed put wall 726, the max-OI
    strike, while the put GAMMA peak that day was 738. Ranking by exposure
    gave the wrong wall, so this pins the OI definition."""
    out = gex0dte.compute(_chain([
        _c("put", 726, 0.01, 20000),   # fat OI, thin gamma  -> the wall
        _c("put", 738, 0.09, 3000),    # thin OI, fat gamma
        _c("call", 740, 0.05, 9000),
    ]))
    assert out["put_wall"] == 726


def test_flip_is_interpolated_between_the_bracketing_strikes():
    """Cumulative gamma crosses zero between 730 and 740, not at a strike."""
    out = gex0dte.compute(_chain([
        _c("put", 730, 0.04, 1000),    # cumulative goes negative
        _c("call", 740, 0.08, 1000),   # and back positive
    ]))
    assert out["flip"] is not None
    assert 730 < out["flip"] < 740, out["flip"]


def test_flip_is_none_when_gamma_never_crosses_zero():
    out = gex0dte.compute(_chain([_c("call", 740, 0.05, 1000), _c("call", 744, 0.04, 1000)]))
    assert out["flip"] is None


def test_magnets_are_the_signed_net_extremes():
    """getgamma's +GEX / -GEX MAGNET: the single most positive and most
    negative net-gamma strikes, not the heaviest absolute ones near spot."""
    out = gex0dte.compute(_chain([
        _c("call", 740, 0.06, 9000),   # heaviest POSITIVE net -> +GEX magnet
        _c("call", 744, 0.01, 500),
        _c("put", 733, 0.05, 9000),    # heaviest NEGATIVE net -> -GEX magnet
        _c("put", 736, 0.01, 400),
    ], spot=738.0))
    assert out["magnet_hi"] == 740
    assert out["magnet_lo"] == 733


def test_call_and_put_gex_are_reported_separately():
    """The dashboard shows "Call: $X | Put: $Y" and total = call - put."""
    out = gex0dte.compute(_chain([_c("call", 740, 0.05, 1000), _c("put", 730, 0.02, 1000)]))
    assert out["call_gex"] > 0 and out["put_gex"] > 0
    assert out["net_gex"] == pytest.approx(out["call_gex"] - out["put_gex"])


# ---- robustness -----------------------------------------------------------

@pytest.mark.parametrize("bad", [
    {}, {"contracts": []}, {"contracts": [_c("call", 1, 1, 1)]},          # no spot
    {"spotPrice": 738.0}, {"spotPrice": 738.0, "contracts": []},
])
def test_unusable_payloads_raise_rather_than_return_nonsense(bad):
    with pytest.raises(gex0dte.GammaError):
        gex0dte.compute(bad)


def test_contracts_without_gamma_or_oi_are_skipped():
    out = gex0dte.compute(_chain([
        _c("call", 740, 0.05, 9000),
        {"contract_type": "call", "strike_price": 741, "open_interest": 100},   # no greeks
        _c("call", 742, 0.05, 0),                                               # no OI
        {"contract_type": "warrant", "strike_price": 743, "open_interest": 10,
         "greeks": {"gamma": 0.5}},                                             # not an option side
    ]))
    assert out["strikes"] == 1
    assert out["call_wall"] == 740


def test_a_chain_of_only_junk_raises():
    with pytest.raises(gex0dte.GammaError):
        gex0dte.compute(_chain([_c("call", 740, 0.05, 0)]))


# ---- the desk line --------------------------------------------------------

@pytest.mark.parametrize("value,text", [
    (-12_560_000_000, "-$12.56B"), (980_400_000, "$980.40M"),
    (12_300, "$12.30K"), (-450, "-$450"), (None, "—"),
])
def test_gex_shorthand(value, text):
    assert gex0dte.fmt_gex(value) == text


def test_summary_line_matches_the_desk_format():
    line = gex0dte.summary_line("SPY", "NEG", -12_560_000_000, 743.09, 740, 730, 744, 733)
    assert line == ("SPY NEG · net -$12.56B · flip 743.09 · call wall 740 · "
                    "put wall 730 · magnets 744-733")


def test_compute_emits_that_line():
    out = gex0dte.compute(_chain([_c("call", 740, 0.05, 9000), _c("put", 730, 0.04, 8000)]))
    assert out["note"].startswith("SPY ")
    assert "call wall 740" in out["note"] and "put wall 730" in out["note"]


# ---- transport ------------------------------------------------------------

def test_the_fetch_sends_no_credentials(monkeypatch):
    """The vendor endpoint needs none — verified against a session JWT, the
    gamma_fp cookie, and no cookies at all, which all answer identically. So
    none are sent: nothing to store, leak, or expire."""
    seen = {}

    def spy(*a, **k):
        seen.update(k)
        raise RuntimeError("stop here")

    monkeypatch.setattr("requests.get", spy)
    with pytest.raises(gex0dte.GammaError):
        gex0dte.fetch_live()
    assert "cookies" not in seen, "a credential was sent to a credential-free endpoint"


def test_a_bot_check_page_is_reported_as_such(monkeypatch):
    """The vendor answers server-side calls with HTTP 429 + HTML. That must
    surface as a clear message, never as a parse crash."""
    class Resp:
        status_code = 429
        headers = {"content-type": "text/html; charset=utf-8"}
        text = "<!DOCTYPE html><title>Vercel Security Checkpoint</title>"

    monkeypatch.setattr("requests.get", lambda *a, **k: Resp())
    with pytest.raises(gex0dte.GammaError, match="bot-check page"):
        gex0dte.fetch_live()


# ---- endpoints ------------------------------------------------------------

def test_refresh_accepts_a_browser_captured_payload_and_stores_it(client):
    chain = _chain([_c("call", 740, 0.05, 9000), _c("put", 730, 0.04, 8000)])
    r = client.post("/api/v1/super/gex0dte/refresh", json={"payload": chain})
    assert r.status_code == 200, r.text
    assert r.json()["call_wall"] == 740

    stored = client.get("/api/v1/super/gex0dte")
    assert stored.status_code == 200
    assert stored.json()["note"] == r.json()["note"]
    assert stored.json()["fetched_at"]


def test_reading_before_any_refresh_is_404_not_500(client):
    r = client.get("/api/v1/super/gex0dte")
    assert r.status_code == 404


def test_a_malformed_payload_is_422(client):
    r = client.post("/api/v1/super/gex0dte/refresh", json={"payload": {"contracts": []}})
    assert r.status_code == 422


def test_refresh_without_a_payload_tries_the_vendor_and_reports_the_block(client):
    r = client.post("/api/v1/super/gex0dte/refresh", json={})
    assert r.status_code == 502
