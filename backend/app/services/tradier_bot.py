"""Tradier options executor: pick by delta, size by balance %, buy, then
manage the exit — resting TP sell on the venue, monitored SL that cancels
the TP before selling.

The trade the desk asked for (user 08/03):

    balance $500 · bid $0.50 · buy 50%  ->  $250 / ($0.50 x 100) = 5 contracts
    tp 15%  ->  resting sell at entry x 1.15
    sl 30%  ->  when the bid touches entry x 0.70, cancel the TP and sell

The x100 contract multiplier is the part the shorthand arithmetic usually
skips — sizing that forgot it would order 100x too many contracts.

buy_pct is a target, not a cap (user 08/15). Contracts are indivisible, so
the total is allowed to land within a tolerance band either side of the
budget — otherwise a contract priced just over it sizes to zero and the
delta band's own pick never trades. See size_contracts.

Multiple positions run concurrently; each is a row in tradier_positions and
the monitor sweeps them all. The TP order survives an API restart because it
rests on the venue; the SL survives because the rows do.
"""

from __future__ import annotations

import logging
import math
import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import User
from app.models.tradier import TradierPosition
from app.services import credentials
from app.services.tradier_client import TradierClient, TradierError

logger = logging.getLogger(__name__)

# Desk-wide defaults live in Settings (env: TBOT_TRADIER_*); these module
# aliases keep every existing call-site and API Field(default=...) working.
_S = get_settings()
DEFAULT_DELTA_MIN = _S.tradier_delta_min
DEFAULT_DELTA_MAX = _S.tradier_delta_max
DEFAULT_BUY_PCT = _S.tradier_buy_pct
DEFAULT_TOLERANCE_PCT = _S.tradier_size_tolerance_pct
DEFAULT_TP_PCT = _S.tradier_tp_pct
DEFAULT_SL_PCT = _S.tradier_sl_pct

ACTIVE_STATUSES = ("pending", "open")

# the desk's trading day, for deciding what counts as "today's expiration"
CST = ZoneInfo("America/Chicago")

# One monitor pass per user at a time. The background loop and the desk's
# sweep button both run it, and two passes over the same freshly-filled row
# race to arm it — the venue guard catches the duplicate order, but the
# cheaper fix is not to have two passes in flight at all.
_monitor_locks: dict[str, threading.Lock] = {}
_monitor_guard = threading.Lock()


def _monitor_lock(user_id: str) -> threading.Lock:
    with _monitor_guard:
        return _monitor_locks.setdefault(user_id, threading.Lock())


class TradierBotError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def client_for(user: User, *, live: bool = False) -> TradierClient:
    """Build a client for this user. SANDBOX unless LIVE is asked for.

    The default is deliberately the paper venue: every desk call that does not
    name an environment (quotes, chain preview, balance) lands on sandbox, so
    reaching the real account is always a deliberate act.

    TBOT_PAPER_ONLY=true refuses live outright rather than silently
    downgrading it — the same contract the Kalshi bots use, and an operator
    who asked for live money deserves to be told the server is locked.
    """
    if live and get_settings().paper_only:
        raise TradierBotError(
            "server is locked to paper (TBOT_PAPER_ONLY=true) — live Tradier "
            "orders are refused; unset it to trade the production account", 403
        )
    creds = credentials.load_tradier_credentials(
        user.user_root_folder, sandbox=not live
    )
    return TradierClient(creds)


# ── selection & sizing ──────────────────────────────────────────────────────

def delta_band(side: str, delta_min: float, delta_max: float) -> tuple[float, float]:
    """The SIGNED band a side actually trades in.

    A delta band is spoken as a magnitude — "0.25 to 0.45" — because that is
    how an operator thinks about moneyness. On the tape it is signed: a call's
    delta runs 0..+1 and a put's runs 0..-1. So the same spoken band means two
    different searches (user 08/17):

        SPY calls 0.25-0.45  ->  +0.25 .. +0.45
        SPY puts  0.25-0.45  ->  -0.45 .. -0.25

    Tradier signs them correctly — verified against the live chain, where 122
    of 211 SPY puts carry a negative delta and the rest are a flat 0.0000.
    Matching on |delta| got the right contracts by accident of magnitude while
    being unable to tell a correctly-signed put from a wrongly-signed one, and
    it recorded every put's entry delta as positive.
    """
    lo, hi = sorted((abs(delta_min), abs(delta_max)))
    return (lo, hi) if side == "call" else (-hi, -lo)


def smart_limit(bid: float, ask: float) -> float:
    """Mid-price when the spread is wide, ask when it is 1-2 cents."""
    spread = round(ask - bid, 2)
    if spread <= 0.02:
        return round(ask, 2)
    return math.ceil((bid + ask) / 2 * 100) / 100


def _smart_sell(client, pos, bid: float, ask: float) -> dict:
    """Sell to close: limit at mid-price when spread > $0.02, else market."""
    spread = round(ask - bid, 2)
    if spread > 0.02 and bid > 0:
        limit_px = round((bid + ask) / 2, 2)
        return client.place_option_order(
            underlying=pos.underlying, occ_symbol=pos.occ_symbol,
            side="sell_to_close", quantity=pos.contracts,
            order_type="limit", price=limit_px,
        )
    return client.place_option_order(
        underlying=pos.underlying, occ_symbol=pos.occ_symbol,
        side="sell_to_close", quantity=pos.contracts,
        order_type="market",
    )


def pick_contract(chain: list[dict], side: str, delta_min: float,
                  delta_max: float) -> dict | None:
    """The option whose delta sits closest to the middle of its signed band.

    Requires a live two-sided quote — an option with no bid cannot be exited,
    so it must never be entered. Ties break toward the tighter spread.
    """
    lo, hi = delta_band(side, delta_min, delta_max)
    mid_target = (lo + hi) / 2.0
    best = None
    for opt in chain:
        if (opt.get("option_type") or "").lower() != side:
            continue
        greeks = opt.get("greeks") or {}
        delta = greeks.get("delta")
        if delta is None:
            continue
        d = float(delta)                    # signed, exactly as quoted
        if not (lo <= d <= hi):
            continue
        bid = float(opt.get("bid") or 0)
        ask = float(opt.get("ask") or 0)
        if bid <= 0 or ask <= 0:
            continue
        score = (abs(d - mid_target), ask - bid)
        if best is None or score < best[0]:
            best = (score, opt, d)
    if best is None:
        return None
    opt = dict(best[1])
    opt["_delta"] = best[2]                 # signed: negative for a put
    opt["_abs_delta"] = abs(best[2])
    return opt


def size_contracts(
    balance_usd: float,
    buy_pct: float,
    limit_price: float,
    *,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
    min_contracts: int = 1,
) -> tuple[int, dict]:
    """How many contracts to buy, and the arithmetic that says why.

    The budget is balance x buy_pct — a target, not a hard cap. Contracts are
    indivisible, so a strict floor() against that target misses the trade in
    both directions (user 08/15): on a $50 budget a $60 contract sizes to
    ZERO, even though it is the contract the delta band asked for, and a $30
    contract sizes to ONE, leaving $20 of the $50 parked.

    So the budget carries a tolerance band, +/- tolerance_pct around it, and
    the rule is: aim at the budget, accept any whole number of contracts
    whose total lands inside the band.

        floor((balance x pct) / (price x 100))  <- lots inside the budget
        under the band's floor -> one more lot, if it fits under the ceiling
        zero                   -> min_contracts, if it fits

    With $100, 50% and a 25% band the window is $37.50 - $62.50:

        0.60  ->  0 inside budget  ->  1 lot   ($60; before: no trade)
        0.62  ->  0 inside budget  ->  1 lot   ($62)
        0.38  ->  1 lot ($38, already inside the band)
        0.30  ->  1 lot = $30, under the floor  ->  2 lots ($60)
        0.05  -> 10 lots ($50, dead on the budget — unchanged by the band)

    The x100 is the option multiplier the desk's shorthand omits; without it
    this would order a hundred times the intended size.

    Returns (contracts, sizing); ``sizing`` carries the band, the per-lot
    cost and the resulting total so a caller can explain the number — or a
    refusal — without recomputing any of it.
    """
    least = max(1, int(min_contracts))
    cost = limit_price * 100.0
    budget = balance_usd * (buy_pct / 100.0)
    tol = max(0.0, tolerance_pct) / 100.0
    sizing = {
        "budget_usd": round(budget, 2),
        "band_low_usd": round(budget * (1 - tol), 2),
        "band_high_usd": round(budget * (1 + tol), 2),
        "tolerance_pct": tolerance_pct,
        "cost_per_contract_usd": round(cost, 2),
    }
    if cost <= 0:
        return 0, dict(sizing, total_usd=0.0)

    inside = math.floor(budget / cost)      # lots the budget alone pays for
    if inside <= 0:
        # One lot costs more than the entire budget. A lot is the smallest
        # trade there is, so the only question left is the ceiling.
        want = least
    elif inside * cost < sizing["band_low_usd"]:
        # Under-deployed. One more lot is the only count above the budget
        # that can still land under the ceiling, so it is the only candidate.
        want = inside + 1
    else:
        return inside, dict(sizing, total_usd=round(inside * cost, 2))

    total = want * cost
    if total > sizing["band_high_usd"]:
        # Nothing whole fits the band. Fall back to what the budget itself
        # buys — which is what the caller got before the band existed, and
        # is zero when even one lot is out of reach.
        return max(0, inside), dict(
            sizing,
            total_usd=round(max(0, inside) * cost, 2),
            over_ceiling_usd=round(total, 2),
        )
    return want, dict(sizing, total_usd=round(total, 2))


# ── open ────────────────────────────────────────────────────────────────────

def open_position(
    db: Session,
    user: User,
    *,
    symbol: str,
    side: str,
    buy_pct: float = DEFAULT_BUY_PCT,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
    delta_min: float = DEFAULT_DELTA_MIN,
    delta_max: float = DEFAULT_DELTA_MAX,
    tp_pct: float = DEFAULT_TP_PCT,
    sl_pct: float = DEFAULT_SL_PCT,
    expiration: str | None = None,
    min_contracts: int = 1,
    strategy: str = "Manual",
    live: bool = False,
    zero_dte: bool = False,
    discount_pct: float = 0,
) -> TradierPosition:
    """Select, size and buy; the monitor takes over from there.

    ``live=False`` (the default) places the order on the SANDBOX venue with
    the sandbox token — a mock order against fake money.

    ``zero_dte=False`` (the default) skips today's expiration. A same-day
    contract with hours left is a different trade from the one a delta band
    describes, so it has to be asked for.
    """
    symbol = symbol.strip().upper()
    side = side.strip().lower()
    if side not in ("call", "put"):
        raise TradierBotError("side must be 'call' or 'put'")
    if not (0 < buy_pct <= 100):
        raise TradierBotError("buy_pct must be in (0, 100]")
    if not (0 <= tolerance_pct <= 100):
        raise TradierBotError("tolerance_pct must be in [0, 100] — 0 is the "
                              "old strict-budget behaviour")
    if not (0 < delta_min < delta_max <= 1):
        raise TradierBotError("need 0 < delta_min < delta_max <= 1")

    client = client_for(user, live=live)
    venue_sandbox = client.creds.sandbox
    try:
        bal = client.balances()
        buying_power = bal["option_buying_power"]
        if buying_power <= 0:
            raise TradierBotError(
                f"option buying power is ${buying_power:.2f} — nothing to size against", 409
            )

        if expiration is None:
            exps = client.expirations(symbol) or []
            if not zero_dte:
                today = f"{datetime.now(CST):%Y-%m-%d}"
                exps = [e for e in exps if str(e) > today]
            if not exps:
                raise TradierBotError(
                    f"no {'' if zero_dte else 'non-0DTE '}option expirations "
                    f"for {symbol}", 404)
            expiration = exps[0]        # nearest qualifying expiration

        chain = client.chain(symbol, expiration)
        opt = pick_contract(chain, side, delta_min, delta_max)
        if opt is None:
            # Name the SIGNED band that was searched. "no put with delta in
            # 0.25-0.45" reads like the band was wrong; "-0.45..-0.25" shows
            # the search was right for the side and the chain simply had
            # nothing there — and makes a vendor sign flip obvious on sight.
            lo, hi = delta_band(side, delta_min, delta_max)
            raise TradierBotError(
                f"no {side} on {symbol} {expiration} with delta in "
                f"{lo:+g}..{hi:+g} and a two-sided quote", 404
            )

        picked_delta = opt.get("_delta")
        logger.info(
            "pick_contract -> %s  delta=%s  strike=%s  bid=%s  ask=%s  exp=%s",
            opt.get("symbol"), picked_delta, opt.get("strike"),
            opt.get("bid"), opt.get("ask"), expiration,
        )

        market_price = smart_limit(float(opt.get("bid") or 0), float(opt["ask"]))
        if discount_pct > 0:
            limit_price = round(market_price * (1 - discount_pct / 100), 2)
        else:
            limit_price = market_price
        contracts, sizing = size_contracts(
            buying_power, buy_pct, limit_price,
            tolerance_pct=tolerance_pct, min_contracts=min_contracts,
        )
        if contracts < max(1, min_contracts):
            raise TradierBotError(
                f"sized {contracts} contract(s) — below min_contracts "
                f"{max(1, min_contracts)}: {buy_pct:g}% of ${buying_power:.2f} "
                f"is ${sizing['budget_usd']:.2f} (band ${sizing['band_low_usd']:.2f}"
                f"-${sizing['band_high_usd']:.2f} at +/-{tolerance_pct:g}%) "
                f"at ${limit_price:.2f} (${limit_price * 100:.2f}/contract) "
                f"for {opt['symbol']}"
                f" [delta={picked_delta}, range={delta_min:g}-{delta_max:g}]", 409
            )

        order = client.place_option_order(
            underlying=symbol, occ_symbol=opt["symbol"], side="buy_to_open",
            quantity=contracts, order_type="limit", price=limit_price,
        )
    finally:
        client.close()

    discount_label = f" ({discount_pct:g}% discount)" if discount_pct else ""
    pos = TradierPosition(
        user_id=user.user_id,
        sandbox=venue_sandbox,
        underlying=symbol,
        occ_symbol=opt["symbol"],
        option_type=side,
        strike=float(opt.get("strike") or 0),
        expiration=expiration,
        delta_at_entry=opt.get("_delta"),
        contracts=contracts,
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        buy_pct=buy_pct,
        buy_order_id=str(order["id"]),
        strategy=(strategy or "Manual")[:64],
        status="pending",
        note=(f"buy_to_open {contracts} @ {limit_price:.2f} limit{discount_label} "
              f"(${sizing['total_usd']:.2f} of a ${sizing['budget_usd']:.2f} "
              f"budget, +/-{tolerance_pct:g}%)"),
        raw={"buy_order": order, "picked": {
            "bid": opt.get("bid"), "ask": opt.get("ask"),
            "delta": opt.get("_delta"),
        }, "sizing": sizing,
            "discount_pct": discount_pct if discount_pct else None,
            "cancel_after_s": 900 if discount_pct else None},
    )
    db.add(pos)
    db.commit()
    db.refresh(pos)
    logger.info("tradier: opened #%s %s %s x%s (delta %.2f)",
                pos.id, pos.occ_symbol, side, contracts, pos.delta_at_entry or 0)
    return pos


def open_contract(
    db: Session,
    user: User,
    *,
    occ_symbol: str,
    buy_pct: float = DEFAULT_BUY_PCT,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
    tp_pct: float = DEFAULT_TP_PCT,
    sl_pct: float = DEFAULT_SL_PCT,
    min_contracts: int = 1,
    strategy: str = "Manual",
    live: bool = False,
    discount_pct: float = 0,
) -> TradierPosition:
    """Buy ONE named contract, sized and managed like any desk position.

    The delta search in ``open_position`` exists to CHOOSE a contract; here
    the operator already has one (a row on the flow board), so the only
    questions left are what it costs and how many fit inside buy_pct. It
    becomes an ordinary managed position: same TP resting on the venue, same
    monitored stop, same 'Manual' strategy tag.
    """
    occ = (occ_symbol or "").strip().upper()
    if not occ:
        raise TradierBotError("an option symbol is required")
    if not (0 < buy_pct <= 100):
        raise TradierBotError("buy_pct must be in (0, 100]")
    if not (0 <= tolerance_pct <= 100):
        raise TradierBotError("tolerance_pct must be in [0, 100] — 0 is the "
                              "old strict-budget behaviour")

    client = client_for(user, live=live)
    venue_sandbox = client.creds.sandbox
    try:
        bal = client.balances()
        buying_power = bal["option_buying_power"]
        if buying_power <= 0:
            raise TradierBotError(
                f"option buying power is ${buying_power:.2f} — nothing to size against", 409
            )
        q = client.quote(occ)
        underlying = (q.get("underlying") or q.get("root_symbol") or "").upper()
        bid = float(q.get("bid") or 0)
        ask = float(q.get("ask") or 0)
        if not underlying or ask <= 0:
            raise TradierBotError(
                f"{occ} has no tradeable offer right now (ask {ask})", 409)

        market_price = smart_limit(bid, ask)
        if discount_pct > 0:
            limit_price = round(market_price * (1 - discount_pct / 100), 2)
        else:
            limit_price = market_price
        contracts, sizing = size_contracts(
            buying_power, buy_pct, limit_price,
            tolerance_pct=tolerance_pct, min_contracts=min_contracts,
        )
        if contracts < max(1, min_contracts):
            raise TradierBotError(
                f"sized {contracts} contract(s) — below min_contracts "
                f"{max(1, min_contracts)}: {buy_pct:g}% of ${buying_power:.2f} "
                f"is ${sizing['budget_usd']:.2f} (band ${sizing['band_low_usd']:.2f}"
                f"-${sizing['band_high_usd']:.2f} at +/-{tolerance_pct:g}%) "
                f"at ${limit_price:.2f} (${limit_price * 100:.2f}/contract) "
                f"for {occ}", 409
            )
        order = client.place_option_order(
            underlying=underlying, occ_symbol=occ, side="buy_to_open",
            quantity=contracts, order_type="limit", price=limit_price,
        )
    finally:
        client.close()

    discount_label = f" ({discount_pct:g}% discount)" if discount_pct else ""
    pos = TradierPosition(
        user_id=user.user_id,
        sandbox=venue_sandbox,
        underlying=underlying,
        occ_symbol=occ,
        option_type=(q.get("option_type") or "").lower(),
        strike=float(q.get("strike") or 0),
        expiration=str(q.get("expiration_date") or ""),
        delta_at_entry=None,
        contracts=contracts,
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        buy_pct=buy_pct,
        buy_order_id=str(order["id"]),
        strategy=(strategy or "Manual")[:64],
        status="pending",
        note=(f"buy_to_open {contracts} @ {limit_price:.2f} limit{discount_label} "
              f"(${sizing['total_usd']:.2f} of a ${sizing['budget_usd']:.2f} "
              f"budget, +/-{tolerance_pct:g}%)"),
        raw={"buy_order": order, "picked": {
            "bid": q.get("bid"), "ask": q.get("ask"), "source": "options flow",
        }, "sizing": sizing,
            "discount_pct": discount_pct if discount_pct else None,
            "cancel_after_s": 900 if discount_pct else None},
    )
    db.add(pos)
    db.commit()
    db.refresh(pos)
    logger.info("tradier: opened #%s %s x%s from the flow board",
                pos.id, pos.occ_symbol, contracts)
    return pos


# ── monitor ─────────────────────────────────────────────────────────────────

def exit_prices(entry: float, tp_pct: float, sl_pct: float) -> tuple[float, float]:
    """(take-profit, stop) for an entry price.

    Ceil to the penny, not round(): round(0.575, 2) is 0.57 under banker's
    rounding — a TP that sells BELOW the promised percent. Ceiling errs
    protective on both sides: the TP never sells under its target, the SL
    never stops later than its floor.
    """
    def _ceil_penny(x: float) -> float:
        return math.ceil(x * 100 - 1e-6) / 100.0

    return (_ceil_penny(entry * (1 + tp_pct / 100.0)),
            _ceil_penny(entry * (1 - sl_pct / 100.0)))


def _target_override(pos: TradierPosition) -> float | None:
    """An explicit target the operator set, which outranks the percentage."""
    raw = pos.raw if isinstance(pos.raw, dict) else {}
    try:
        px = float((raw.get("tp_override") or {}).get("price"))
        return px if px > 0 else None
    except (TypeError, ValueError):
        return None


def _place_tp(client: TradierClient, pos: TradierPosition) -> None:
    """Entry filled -> arm the exits. TP rests on the venue (survives us);
    the SL threshold is stored and watched by the sweep.

    Never places a second sell. The background monitor and the desk's sweep
    both run this loop, in different threads and sessions, so two passes can
    reach the same freshly-filled row — and two resting sells on one holding
    is a short position waiting to happen. The ACCOUNT is asked what is
    already working rather than trusting our own stored id, which would miss
    an order placed by the other copy.
    """
    entry = pos.entry_price or 0
    pos.tp_price, pos.sl_price = exit_prices(entry, pos.tp_pct, pos.sl_pct)

    # Our own order, still working, is the plain duplicate case.
    if pos.tp_order_id:
        try:
            st = (client.order_status(pos.tp_order_id).get("status") or "").lower()
        except TradierError:
            raise
        if st in TradierClient.LIVE_ORDER_STATUSES:
            pos.status = "open"
            logger.info("tradier: #%s already has sell %s resting",
                        pos.id, pos.tp_order_id)
            return

    # Otherwise the test is arithmetic, not identity: several positions can
    # legitimately hold this contract, each with its own exit. What must
    # never happen is resting MORE sells than the account holds — that is a
    # short position by accident.
    resting = client.resting_sells(pos.occ_symbol)
    spoken_for = sum(abs(float(o.get("quantity") or 0)) for o in resting)
    held = _held_quantity(client, pos.occ_symbol)
    if spoken_for + pos.contracts > held:
        # Do not talk over a row that already HAS its exit. A pass that lost
        # the race to another one still lands here, and rewriting the note
        # would report "not armed" on a position that is armed.
        if not pos.tp_order_id:
            pos.note = (f"filled @ {entry:.2f}; exits not armed — {spoken_for:g} "
                        f"of {held:g} held already have a resting sell")
        logger.warning("tradier: #%s refused a TP — %s resting vs %s held on %s",
                       pos.id, spoken_for, held, pos.occ_symbol)
        return
    # A target set before the fill wins over the percentage — the operator
    # named a price, and the percentage was only ever a way to reach one.
    override = _target_override(pos)
    if override:
        pos.tp_price = override
        if entry:
            pos.tp_pct = round((override / entry - 1) * 100, 2)
    tp = client.place_option_order(
        underlying=pos.underlying, occ_symbol=pos.occ_symbol,
        side="sell_to_close", quantity=pos.contracts,
        order_type="limit", price=pos.tp_price, duration="gtc",
    )
    pos.tp_order_id = str(tp["id"])
    pos.status = "open"
    pos.note = (f"filled @ {entry:.2f}; TP {pos.tp_price:.2f} resting, "
                f"SL {pos.sl_price:.2f} monitored")


def _finalize(pos: TradierPosition, status: str, exit_price: float | None,
              note: str) -> None:
    pos.status = status
    pos.exit_price = exit_price
    if exit_price is not None and pos.entry_price is not None:
        pos.pnl_usd = round((exit_price - pos.entry_price) * 100 * pos.contracts, 2)
    pos.note = note
    pos.closed_at = _now()


def monitor_pass(db: Session, user: User) -> dict:
    """One sweep over this user's active positions.

    Called by the API's background loop AND by the desk's refresh, so passes
    are serialized per user: two of them over the same freshly-filled row
    both try to arm it, and while the venue guard refuses the duplicate
    order, the loser still writes its own conclusions over the winner's.
    A pass that finds one already running simply steps aside — the next tick
    is seconds away.
    """
    lock = _monitor_lock(user.user_id)
    if not lock.acquire(blocking=False):
        return {"checked": 0, "events": [], "busy": True}
    try:
        return _monitor_pass_locked(db, user)
    finally:
        lock.release()


def _monitor_pass_locked(db: Session, user: User) -> dict:
    rows = list(db.scalars(
        select(TradierPosition).where(
            TradierPosition.user_id == user.user_id,
            TradierPosition.status.in_(ACTIVE_STATUSES),
        )
    ).all())
    if not rows:
        return {"checked": 0, "events": []}

    # One client per VENUE, chosen by each row's own sandbox flag. Sweeping a
    # live position against sandbox would find no such order id and finalize
    # a real, still-open position as failed.
    events: list[str] = []
    clients: dict[bool, TradierClient] = {}
    try:
        for pos in rows:
            want_live = not pos.sandbox
            try:
                client = clients.get(want_live)
                if client is None:
                    client = clients[want_live] = client_for(user, live=want_live)
                _monitor_one(client, pos, events)
            except TradierError as exc:
                # transient venue trouble must not kill the sweep for the
                # other positions; this row is retried next pass
                events.append(f"#{pos.id}: venue error, retrying ({exc})")
            except (TradierBotError, credentials.CredentialsError) as exc:
                # e.g. a live row while the server is paper-locked: leave it
                # untouched rather than mislabel it from the wrong venue
                events.append(f"#{pos.id}: skipped ({exc})")
        db.commit()
    finally:
        for client in clients.values():
            client.close()
    return {"checked": len(rows), "events": events}


def _seconds_since(pos: TradierPosition) -> float | None:
    """Seconds since the buy filled, or None if that was never stamped."""
    raw = pos.raw if isinstance(pos.raw, dict) else {}
    stamp = raw.get("filled_at")
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None
    return (_now() - when).total_seconds()


def _held_quantity(client: TradierClient, occ_symbol: str) -> float:
    """How many of this contract the ACCOUNT says it holds (0 if none)."""
    try:
        for p in client.positions():
            if (p.get("symbol") or "").upper() == (occ_symbol or "").upper():
                return abs(float(p.get("quantity") or 0))
    except (TradierError, TypeError, ValueError):
        return 0.0        # unknown is treated as not-yet: never sell blind
    return 0.0


def _monitor_one(client: TradierClient, pos: TradierPosition,
                 events: list[str]) -> None:
    if pos.status == "pending":
        # Two steps, not one. A buy that reports "filled" is not yet a
        # position: the holding lands on the books a beat later, and a
        # sell_to_close into that gap is what the venue rejects. So the fill
        # is recorded first, and the exits are armed on a later pass once the
        # wait has elapsed AND the account actually shows the contract.
        if pos.entry_price is None:
            order = client.order_status(pos.buy_order_id)
            st = (order.get("status") or "").lower()
            if st == "filled":
                pos.entry_price = float(order.get("avg_fill_price") or 0)
                raw = dict(pos.raw or {})
                raw["filled_at"] = _now().isoformat()
                pos.raw = raw
                delay = get_settings().tradier_arm_delay_s
                pos.note = (f"filled @ {pos.entry_price:.2f}; confirming the "
                            f"position before arming exits ({delay}s)")
                events.append(f"#{pos.id} filled @ {pos.entry_price:.2f}; "
                              f"confirming the position")
            elif st in ("canceled", "rejected", "expired"):
                _finalize(pos, "failed", None, f"buy {st}; nothing at risk")
                events.append(f"#{pos.id} buy {st}")
            else:
                raw = pos.raw if isinstance(pos.raw, dict) else {}
                cancel_after = raw.get("cancel_after_s")
                if cancel_after and pos.opened_at:
                    age = (_now() - pos.opened_at).total_seconds()
                    if age >= cancel_after:
                        try:
                            client.cancel_order(pos.buy_order_id)
                        except TradierError:
                            pass
                        _finalize(pos, "failed", None,
                                  f"buy cancelled — unfilled after "
                                  f"{int(age)}s (discount order)")
                        events.append(
                            f"#{pos.id} discount order timed out after "
                            f"{int(age)}s — cancelled")
            return

        # filled, waiting to arm
        delay = get_settings().tradier_arm_delay_s
        waited = _seconds_since(pos)
        if waited is not None and waited < delay:
            return
        held = _held_quantity(client, pos.occ_symbol)
        if held <= 0:
            # Not on the books yet. Say so once, then keep checking — the
            # contract IS owned, so giving up would leave it unmanaged.
            if "not on the books" not in (pos.note or ""):
                pos.note = (f"filled @ {pos.entry_price:.2f}; position not on "
                            f"the books yet — exits not armed")
                events.append(f"#{pos.id} filled but the position is not on "
                              f"the books yet; holding off on the exits")
            return
        _place_tp(client, pos)
        events.append(f"#{pos.id} position confirmed ({held:g}); exits armed "
                      f"— TP {pos.tp_price:.2f}, SL {pos.sl_price:.2f}")
        return

    # open: TP filled? then SL?
    if pos.tp_order_id:
        tp = client.order_status(pos.tp_order_id)
        st = (tp.get("status") or "").lower()
        if st == "filled":
            _finalize(pos, "tp_filled",
                      float(tp.get("avg_fill_price") or pos.tp_price or 0),
                      "TP filled")
            events.append(f"#{pos.id} TP filled @ {pos.exit_price:.2f}")
            return
        if st in ("canceled", "rejected", "expired"):
            # The order is gone. Before re-arming, ask whether the POSITION
            # is gone too: a sell that filled without us seeing it looks
            # exactly like this, and re-arming would rest a sell against a
            # holding that no longer exists — the rejection loop this whole
            # change exists to end.
            if _held_quantity(client, pos.occ_symbol) <= 0:
                exit_px = None
                try:
                    exit_px = float(tp.get("avg_fill_price") or 0) or None
                except (TypeError, ValueError):
                    exit_px = None
                if exit_px is None:
                    exit_px = pos.tp_price
                _finalize(pos, "closed", exit_px,
                          f"exit order {st} and the account holds none — "
                          f"closed at the last known exit price")
                events.append(f"#{pos.id} exit {st} and nothing held; "
                              f"marked closed")
                return
            # still holding it — re-arm rather than leave it with no exit
            _place_tp(client, pos)
            events.append(f"#{pos.id} TP was {st}; re-armed")
            return

    # An open row the account no longer backs is finished, however it ended:
    # the exit filled somewhere we did not observe, or it was closed by hand.
    # Leaving it "open" would keep the stop monitoring a holding that is not
    # there, and eventually try to sell it.
    if not client.resting_sells(pos.occ_symbol) \
            and _held_quantity(client, pos.occ_symbol) <= 0:
        quote = client.quote(pos.occ_symbol)
        exit_px = float(quote.get("bid") or 0) or pos.tp_price
        _finalize(pos, "closed", exit_px,
                  "no holding and no resting exit — closed against the "
                  "last quote")
        events.append(f"#{pos.id} no longer held and nothing resting; "
                      f"marked closed")
        return

    quote = client.quote(pos.occ_symbol)
    bid = float(quote.get("bid") or 0)
    ask = float(quote.get("ask") or 0)
    if pos.sl_price is not None and 0 < bid <= pos.sl_price:
        # ORDER MATTERS: cancel the TP first. Selling while the TP still
        # rests would stack two sells for one position and the second fill
        # would open a naked short.
        if pos.tp_order_id:
            try:
                client.cancel_order(pos.tp_order_id)
            except TradierError as exc:
                # if the TP filled in this exact window, that IS the exit
                tp = client.order_status(pos.tp_order_id)
                if (tp.get("status") or "").lower() == "filled":
                    _finalize(pos, "tp_filled",
                              float(tp.get("avg_fill_price") or 0),
                              "TP filled during SL race")
                    events.append(f"#{pos.id} TP won the race")
                    return
                raise exc
        sell = _smart_sell(client, pos, bid, ask)
        pos.close_order_id = str(sell["id"])
        _finalize(pos, "sl_sold", bid,
                  f"SL: bid {bid:.2f} <= {pos.sl_price:.2f}; TP cancelled, sold")
        events.append(f"#{pos.id} SL hit @ {bid:.2f}")
        return

    # 2:50 PM CST auto-close: if TP hasn't hit by now, close the position
    now_cst = datetime.now(CST)
    if f"{now_cst:%H:%M}" >= "14:50":
        if pos.tp_order_id:
            try:
                client.cancel_order(pos.tp_order_id)
            except TradierError as exc:
                tp = client.order_status(pos.tp_order_id)
                if (tp.get("status") or "").lower() == "filled":
                    _finalize(pos, "tp_filled",
                              float(tp.get("avg_fill_price") or 0),
                              "TP filled during EOD close race")
                    events.append(f"#{pos.id} TP filled just before EOD close")
                    return
                raise exc
        sell = _smart_sell(client, pos, bid, ask)
        pos.close_order_id = str(sell["id"])
        exit_px = smart_limit(bid, ask) if (ask - bid) > 0.02 else bid
        _finalize(pos, "closed", exit_px,
                  f"EOD close @ 14:50 CST: bid {bid:.2f}, ask {ask:.2f}")
        events.append(f"#{pos.id} EOD auto-close @ 14:50 CST, bid {bid:.2f}")


def live_quotes(user: User, rows) -> dict[str, dict]:
    """``{occ_symbol: {bid, ask, last}}`` for the still-active rows.

    One batch request per venue, and none at all when nothing is active —
    the desk polls this every few seconds and Tradier rate-limits per token.
    Quote trouble is swallowed: a stale mark must never break the table.
    """
    by_venue: dict[bool, set[str]] = {}
    for p in rows:
        if p.status in ACTIVE_STATUSES and p.occ_symbol:
            by_venue.setdefault(not p.sandbox, set()).add(p.occ_symbol)
    out: dict[str, dict] = {}
    for want_live, syms in by_venue.items():
        try:
            client = client_for(user, live=want_live)
        except Exception:                         # noqa: BLE001 - venue not usable
            continue
        try:
            for q in client.quotes(sorted(syms)):
                sym = q.get("symbol")
                if sym:
                    out[sym] = {"bid": q.get("bid"), "ask": q.get("ask"),
                                "last": q.get("last")}
        except TradierError:
            pass
        finally:
            client.close()
    return out


def set_target(db: Session, user: User, position_id: int,
               target_price: float) -> TradierPosition:
    """Move a live position's take-profit to an explicit price.

    For an OPEN position the resting sell is replaced on the venue, so the
    exit still happens without us. The dangerous part is the swap: if the old
    order filled between our cancel and our replace we would be selling a
    position we no longer hold, so the old order's status is re-read after
    the cancel and a filled one aborts the edit — the monitor then finalizes
    it normally.

    For a PENDING position there is no resting order yet; the target is
    recorded and armed at fill instead.
    """
    pos = db.get(TradierPosition, position_id)
    if pos is None or pos.user_id != user.user_id:
        raise TradierBotError(f"position {position_id} not found", 404)
    if pos.status not in ACTIVE_STATUSES:
        raise TradierBotError(
            f"position {position_id} is {pos.status} — only a live position "
            "has a target to move", 409)
    try:
        target = round(float(target_price), 2)
    except (TypeError, ValueError) as exc:
        raise TradierBotError("target must be a price") from exc
    if target <= 0:
        raise TradierBotError("target must be greater than zero")
    if pos.sl_price and target <= pos.sl_price:
        raise TradierBotError(
            f"target {target:.2f} is at or below the stop {pos.sl_price:.2f} — "
            "the position would be stopped out before it could ever reach it", 409)

    client = client_for(user, live=not pos.sandbox)
    try:
        if pos.status == "open" and pos.tp_order_id:
            try:
                client.cancel_order(pos.tp_order_id)
            except TradierError:
                pass                      # already gone; the status check rules
            st = (client.order_status(pos.tp_order_id).get("status") or "").lower()
            if st == "filled":
                raise TradierBotError(
                    "the take-profit filled while the target was being moved — "
                    "the position is already closing", 409)
            order = client.place_option_order(
                underlying=pos.underlying, occ_symbol=pos.occ_symbol,
                side="sell_to_close", quantity=pos.contracts,
                order_type="limit", price=target, duration="gtc",
            )
            pos.tp_order_id = str(order["id"])
            pos.note = (f"target moved to {target:.2f}"
                        + (f" (entry {pos.entry_price:.2f})" if pos.entry_price else ""))
        else:
            pos.note = f"target {target:.2f} set; arms when the buy fills"
    finally:
        client.close()

    pos.tp_price = target
    if pos.entry_price:
        pos.tp_pct = round((target / pos.entry_price - 1) * 100, 2)
    raw = dict(pos.raw or {})
    raw["tp_override"] = {"price": target, "at": _now().isoformat()}
    pos.raw = raw
    db.commit()
    db.refresh(pos)
    return pos


def close_position(db: Session, user: User, position_id: int,
                   force: bool = False) -> TradierPosition:
    """Manual close from the desk: cancel whatever rests, sell at market.

    ``force`` only applies to a PENDING row on the SANDBOX whose cancel the
    venue refuses: the row stops being tracked so the desk can be cleared.
    It is deliberately not available on the live account — abandoning a real
    working order would leave a position nobody is watching.
    """
    pos = db.get(TradierPosition, position_id)
    if pos is None or pos.user_id != user.user_id:
        raise TradierBotError(f"position {position_id} not found", 404)
    if pos.status not in ACTIVE_STATUSES:
        raise TradierBotError(f"position {position_id} is {pos.status}", 409)

    # Close on the venue the position was opened on, never the desk's default.
    client = client_for(user, live=not pos.sandbox)
    try:
        if pos.status == "pending" and pos.buy_order_id:
            try:
                client.cancel_order(pos.buy_order_id)
            except TradierError as exc:
                # A cancel can fail because the order is already gone — or
                # because the venue itself is unwell (Tradier's sandbox 500s
                # on DELETE while happily serving the same order on GET).
                # Ask what the order actually IS before deciding.
                try:
                    st = (client.order_status(pos.buy_order_id).get("status")
                          or "").lower()
                except TradierError:
                    st = ""
                if st in ("canceled", "cancelled", "expired", "rejected"):
                    pass                  # already dead; fall through and close
                elif st == "filled":
                    raise TradierBotError(
                        "the buy filled while it was being cancelled — refresh "
                        "and close the position instead", 409) from exc
                elif force and pos.sandbox:
                    _finalize(pos, "failed", None,
                              f"stopped tracking: venue would not cancel "
                              f"({str(exc)[:80]}); order may still rest on the "
                              f"sandbox")
                    db.commit()
                    return pos
                else:
                    raise TradierBotError(
                        f"the venue refused to cancel this order and it is "
                        f"still {st or 'working'} — the position is untouched. "
                        f"({exc})", 502) from exc
            _finalize(pos, "failed", None, "buy cancelled from the desk")
        else:
            if pos.tp_order_id:
                try:
                    client.cancel_order(pos.tp_order_id)
                except TradierError:
                    pass                      # already gone is fine here
            quote = client.quote(pos.occ_symbol)
            bid = float(quote.get("bid") or 0)
            ask = float(quote.get("ask") or 0)
            sell = _smart_sell(client, pos, bid, ask)
            pos.close_order_id = str(sell["id"])
            exit_px = smart_limit(bid, ask) if (ask - bid) > 0.02 else bid
            _finalize(pos, "closed", exit_px or None,
                      "closed from the desk")
        db.commit()
        db.refresh(pos)
    finally:
        client.close()
    return pos
