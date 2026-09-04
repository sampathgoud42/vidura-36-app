"""Trade history as the EXCHANGE has it: open positions and settled markets.

The ledger answers "what did our bots think they did". This answers "what did
the account actually do", and the two are not the same read. A bot records a
trade when it enters and never learns how it ended; the exchange knows every
fill, every settlement and the fees on both, and it is the only side of that
pair that can be wrong about nothing.

P&L HERE IS NOT revenue minus cost. Most settled rows on this account carry
BOTH sides -- 950 of 1635 at the time of writing -- because closing a position
is recorded as acquiring the opposite token rather than as a sale, and a
matched yes/no pair auto-redeems for $1. Subtracting both costs from the
settlement revenue therefore books the exit as a total loss: one real row came
out at -$73.85 that way against a true -$12.58. The pair term is what makes it
right, and it is the same arithmetic ``services.reconcile`` already documents:

    pnl = revenue/100                      # what settlement paid
        + 1.00 x min(yes_count, no_count)  # pairs that redeemed on their own
        - yes_cost - no_cost - fees        # everything the account paid

Open positions are shown at cost, and marked in aggregate rather than one by
one: Kalshi values the whole book in /portfolio/balance, while a per-ticker
mark would be one request each and would read zero on every combined market
that nobody quotes -- a fake loss on a position that is doing fine.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# How far back the settled list reaches. The feed is cursor-paged and the
# client follows up to ten pages, so this is a ceiling on the read rather than
# a promise about the account's whole life.
DEFAULT_LIMIT = 500


def _num(row: dict, key: str) -> float:
    try:
        return float(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def settled_pnl(row: dict) -> float:
    """What one settled market actually made, fees included.

    See the module docstring for why the pair term is not optional.
    """
    pairs = min(_num(row, "yes_count_fp"), _num(row, "no_count_fp"))
    return (_num(row, "revenue") / 100.0
            + pairs
            - _num(row, "yes_total_cost_dollars")
            - _num(row, "no_total_cost_dollars")
            - _num(row, "fee_cost"))


def _title(ticker: str) -> str:
    """A readable name for a market we only know by ticker.

    Kalshi's combined-market tickers carry no words at all, so this is the
    shape of the bet rather than its subject: enough to tell a parlay from a
    single market in a list, and the full ticker is on the row anyway.
    """
    if "MVE" in ticker or "CROSSCATEGORY" in ticker:
        return "parlay"
    return ticker.split("-", 1)[0].removeprefix("KX").lower() or ticker


def trade_history(cred, *, limit: int = DEFAULT_LIMIT) -> dict:
    """Every open position and every settled market, with the P&L of both.

    Best-effort in the same way the portfolio panel is: a venue hiccup returns
    what could be read rather than failing the request, because a desk that
    blanks on a timeout teaches its operator to distrust the numbers that ARE
    there.
    """
    from app.domains.botstation import venue as kalshi

    out: dict = {"available": True, "venue": "kalshi",
                 "open": [], "history": [], "detail": ""}

    try:
        positions = kalshi.positions(cred, limit=500)
    except Exception:                                   # noqa: BLE001
        return {**out, "available": False,
                "detail": "Kalshi could not be reached"}

    for row in positions:
        contracts = abs(_num(row, "position_fp"))
        if contracts <= 0:
            # Flat. The row is history, and history comes from settlements
            # below where the payout is known.
            continue
        ticker = str(row.get("ticker") or "")
        out["open"].append({
            "ticker": ticker,
            "title": _title(ticker),
            "status": "OPEN",
            "contracts": round(contracts, 2),
            "cost_usd": round(_num(row, "total_traded_dollars"), 4),
            "fees_usd": round(_num(row, "fees_paid_dollars"), 4),
            "pnl_usd": None,
            "at": row.get("last_updated_ts") or "",
        })

    try:
        settlements = kalshi.settlements(cred, limit=limit)
    except Exception:                                   # noqa: BLE001
        settlements = []
        out["detail"] = "settlement history could not be read"

    for row in settlements:
        ticker = str(row.get("ticker") or "")
        pnl = settled_pnl(row)
        cost = (_num(row, "yes_total_cost_dollars")
                + _num(row, "no_total_cost_dollars"))
        out["history"].append({
            "ticker": ticker,
            "title": _title(ticker),
            # WON and LOST off the money, not off market_result. The result
            # says which side the market resolved to; this account can hold
            # either side, and on a closed-out position it holds both.
            "status": "WON" if pnl > 0 else "LOST" if pnl < 0 else "FLAT",
            "result": row.get("market_result") or "",
            "contracts": round(max(_num(row, "yes_count_fp"),
                                   _num(row, "no_count_fp")), 2),
            "cost_usd": round(cost, 4),
            "revenue_usd": round(_num(row, "revenue") / 100.0
                                 + min(_num(row, "yes_count_fp"),
                                       _num(row, "no_count_fp")), 4),
            "fees_usd": round(_num(row, "fee_cost"), 4),
            "pnl_usd": round(pnl, 4),
            "at": row.get("settled_time") or "",
        })

    out["history"].sort(key=lambda r: r["at"], reverse=True)
    out["open"].sort(key=lambda r: r["at"], reverse=True)

    # The mark for open positions, from the exchange rather than from us.
    mark = None
    cash = None
    try:
        pv = kalshi.portfolio(cred)
        mark, cash = pv.get("positions_usd"), pv.get("cash_usd")
    except Exception:                                   # noqa: BLE001
        logger.info("kalshi portfolio unavailable for the history panel")

    open_cost = sum(r["cost_usd"] for r in out["open"])
    open_fees = sum(r["fees_usd"] for r in out["open"])
    realized = sum(r["pnl_usd"] for r in out["history"])
    # Unrealized only when the exchange gave us a mark. None is not zero: a
    # missing mark means unknown, and showing "$0.00 unrealized" against 24
    # open positions is the kind of number an operator acts on.
    unrealized = (None if mark is None
                  else round(mark - open_cost - open_fees, 2))

    out["pnl"] = {
        "realized_usd": round(realized, 2),
        "unrealized_usd": unrealized,
        "total_usd": (round(realized, 2) if unrealized is None
                      else round(realized + unrealized, 2)),
        "open_cost_usd": round(open_cost, 2),
        "open_fees_usd": round(open_fees, 2),
        "open_mark_usd": mark,
        "cash_usd": cash,
        "open_count": len(out["open"]),
        "settled_count": len(out["history"]),
        "wins": sum(1 for r in out["history"] if r["status"] == "WON"),
        "losses": sum(1 for r in out["history"] if r["status"] == "LOST"),
        "fees_usd": round(open_fees
                          + sum(r["fees_usd"] for r in out["history"]), 2),
    }
    return out
