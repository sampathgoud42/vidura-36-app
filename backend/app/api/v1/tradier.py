"""Tradier Platform endpoints: balance, chain preview, managed positions.

The bot here is an EXECUTOR, not a signal engine: the operator says
"SPY call, 50% of the account, delta 0.25-0.50" and the service picks the
contract, sizes it, buys, rests the TP on the venue and monitors the SL.
Multiple positions run side by side.

Environment follows the desk's paper gate: TBOT_PAPER_ONLY=true pins every
client to Tradier's SANDBOX venue (its own token, its own account), so paper
cannot reach live money by construction.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.cloud import require_local_runtime
from app.core.database import get_db
from app.models import User
from app.models.tradier import TradierPosition
from app.services import credentials as creds_svc
from app.services import tradier_bot
from app.services.tradier_client import TradierError

router = APIRouter(prefix="/tradier", tags=["tradier"])

logger = logging.getLogger(__name__)

CST = ZoneInfo("America/Chicago")


def _user_or_404(db: Session, user_id: str) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return user


def _translated(exc: Exception) -> HTTPException:
    if isinstance(exc, tradier_bot.TradierBotError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    if isinstance(exc, creds_svc.CredentialsError):
        return HTTPException(status_code=424, detail=str(exc))
    if isinstance(exc, TradierError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/venue", operation_id="getTradierVenue")
def venue(user_id: str = Query(...), db: Session = Depends(get_db)) -> dict:
    """Which venues this operator can reach, for the desk's LIVE toggle.

    Reports configuration only — no order can be placed from here, and the
    tokens themselves never leave the server.
    """
    user = _user_or_404(db, user_id)
    from app.core.config import get_settings

    out = {"paper_only_server": get_settings().paper_only,
           "sandbox": None, "live": None}
    for key, is_live in (("sandbox", False), ("live", True)):
        try:
            creds = creds_svc.load_tradier_credentials(
                user.user_root_folder, sandbox=not is_live)
            out[key] = {"configured": True, "base_url": creds.base_url,
                        "account_id": creds.account_id}
        except Exception as exc:                      # noqa: BLE001
            out[key] = {"configured": False, "reason": str(exc)}
    if out["live"]["configured"] and get_settings().paper_only:
        out["live"]["reason"] = "server locked to paper (TBOT_PAPER_ONLY)"
    return out


@router.get("/balance", operation_id="getTradierBalance")
def balance(user_id: str = Query(...),
            live: bool = Query(default=False,
                               description="true reads the PRODUCTION account"),
            db: Session = Depends(get_db)) -> dict:
    """Account equity and option buying power — the sizing base."""
    from sqlalchemy import func as sa_func

    from app.core.config import get_settings

    user = _user_or_404(db, user_id)
    try:
        client = tradier_bot.client_for(user, live=live)
    except Exception as exc:                          # noqa: BLE001
        raise _translated(exc) from exc
    try:
        bal = client.balances()
    except TradierError as exc:
        raise _translated(exc) from exc
    finally:
        client.close()

    s = get_settings()
    fee = s.tradier_fee_per_contract
    today = f"{datetime.now(CST):%Y-%m-%d}"
    is_sandbox = not live

    bought = db.scalar(
        select(sa_func.coalesce(sa_func.sum(TradierPosition.contracts), 0))
        .where(TradierPosition.user_id == user_id,
               TradierPosition.sandbox == is_sandbox,
               sa_func.date(TradierPosition.opened_at) == today)
    ) or 0
    sold = db.scalar(
        select(sa_func.coalesce(sa_func.sum(TradierPosition.contracts), 0))
        .where(TradierPosition.user_id == user_id,
               TradierPosition.sandbox == is_sandbox,
               sa_func.date(TradierPosition.closed_at) == today)
    ) or 0

    fees_today = round((bought + sold) * fee, 2)
    bal["fees_today"] = fees_today
    bal["day_pl_net"] = round(bal["day_pl"] - fees_today, 2)
    return bal


# The desk's ticker rail, in the operator's fixed display order.
DESK_TICKERS = ("SPX,SPY,QQQ,VIX,IWM,GLD,AAPL,TSLA,NVDA,MSFT,AMZN,MU,SNDK,"
                "AVGO,META,GOOGL,LLY,JPM,ORCL,IBM,ONDS,IONQ,QBTS")

# One shared quotes cache: the rail polls every 15s per browser tab, Tradier
# rate-limits per token — 10s TTL keeps N tabs at one upstream call per tick.
_QUOTES_CACHE: dict[str, tuple[float, dict]] = {}
_QUOTES_TTL = 10.0


def _tradier_quote_out(q: dict) -> dict:
    def f(key):
        v = q.get(key)
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return None
    return {
        "symbol": (q.get("symbol") or "").upper(),
        "price": f("last"),
        "prev_close": f("prevclose"),
        "change": f("change"),
        "change_pct": f("change_percentage"),
        "source": "tradier",
    }


# The index strip, in the order the desk reads it (user 08/18).
#
# Tradier quotes SPX and VIX as indices directly, but has no symbol for the Dow
# itself (DJI is unmatched) — DIA, the SPDR Dow ETF, is the tradable proxy,
# labelled DOW so the strip reads the way an operator expects.
#
# BTC is not a Tradier instrument at all: the market socket carries equities
# and indices, so nothing here can make it tick. It rides along as a polled
# quote instead — real BTC-USD from the keyless quotes service, not an ETF
# wearing bitcoin's name — and is flagged so the browser knows to refresh it
# itself rather than wait for a tick that will never come.
STREAM_SYMBOLS = [
    {"label": "QQQ", "symbol": "QQQ"},
    {"label": "SPY", "symbol": "SPY"},
    {"label": "SPX", "symbol": "SPX"},
    {"label": "VIX", "symbol": "VIX"},
    {"label": "DOW", "symbol": "DIA"},
    {"label": "BTC", "symbol": "BTC", "stream": False},
]

STREAMED = [s for s in STREAM_SYMBOLS if s.get("stream", True)]
POLLED = [s for s in STREAM_SYMBOLS if not s.get("stream", True)]


def _polled_seed(entry: dict) -> dict:
    """A strip entry Tradier cannot stream, priced from the quotes service."""
    from app.services import quotes as quotes_svc

    out = {**entry}
    try:
        q = quotes_svc.quote_for(entry["symbol"])
        out.update({"price": q.get("price"), "prev_close": q.get("prev_close"),
                    "change_pct": q.get("change_pct"), "source": "quotes"})
    except Exception as exc:                          # noqa: BLE001
        # A strip entry is not worth failing the whole session over — it
        # simply shows a dash until the browser's own poll fills it.
        logger.info("strip quote for %s unavailable: %s", entry["symbol"], exc)
    return out


@router.post("/stream/session", operation_id="createTradierStreamSession")
def stream_session(user_id: str = Query(...), db: Session = Depends(get_db)) -> dict:
    """Short-lived credential for Tradier's market WebSocket, plus a seed snapshot.

    Streaming is PRODUCTION-ONLY — the sandbox token is rejected with
    "Required scope(s): scope-stream", so this always uses the live keys. That
    is safe and deliberate: a market session can only read quotes, never place
    an order, and paper trading against real prices is the point.

    The account token never reaches the browser. What is returned is Tradier's
    session id, which is market-data-only and must be connected within five
    minutes; the page reconnects by asking for a fresh one.
    """
    require_local_runtime("Opening a Tradier market stream")
    user = _user_or_404(db, user_id)
    try:
        client = tradier_bot.client_for(user, live=True)
    except Exception as exc:                          # noqa: BLE001
        raise _translated(exc) from exc
    try:
        data = client.market_session()
        # Seeded in STREAM_SYMBOLS order — the strip renders in the order it
        # is handed, so this list is the single place that order is decided.
        seed = []
        try:
            by_symbol = {(q.get("symbol") or "").upper(): q
                         for q in client.quotes([s["symbol"] for s in STREAMED])}
        except TradierError:
            by_symbol = {}
        for s in STREAM_SYMBOLS:
            if s.get("stream", True):
                q = by_symbol.get(s["symbol"])
                seed.append({**s, **(_tradier_quote_out(q) if q else {}),
                             "symbol": s["symbol"], "label": s["label"]})
            else:
                seed.append(_polled_seed(s))
        return {
            "sessionid": data.get("sessionid"),
            "url": data.get("url"),
            "ws_url": "wss://ws.tradier.com/v1/markets/events",
            # only what the socket should be asked to subscribe to
            "symbols": STREAMED,
            "polled": [s["symbol"] for s in POLLED],
            "seed": seed,
            "venue": "live",
        }
    except TradierError as exc:
        raise _translated(exc) from exc
    finally:
        client.close()


# symbol|interval|venue -> (monotonic, payload). Two charts polling at once
# must not become two upstream calls per tick.
_BARS_CACHE: dict[str, tuple[float, dict]] = {}
_BARS_TTL = 25.0


@router.get("/timesales", operation_id="getTradierTimesales")
def timesales(
    user_id: str = Query(...),
    symbol: str = Query(..., max_length=12),
    interval: str = Query(default="1min", pattern="^(1min|5min|15min)$"),
    days: int = Query(default=1, ge=1, le=30,
                      description="sessions of history; >1 is warmup for "
                                  "indicators, not extra chart"),
    live: bool = Query(default=False,
                       description="true reads bars from the PRODUCTION venue"),
    db: Session = Depends(get_db),
) -> dict:
    """Intraday bars and the prior close the day is measured against.

    Seeds the desk's charts: a WebSocket only produces from the moment it
    connects, so without this the chart would start blank every reload.

    ``days`` exists for indicators rather than for the picture. ADX(14) needs
    roughly 28 bars before it means anything, and a 15-minute session only
    yields ~26 — so the caller asks for earlier sessions to warm the maths up
    and still draws only the latest day.
    """
    import time as _t
    from datetime import timedelta as _td

    sym = symbol.strip().upper()
    key = f"{sym}|{interval}|{days}|{'live' if live else 'sbx'}"
    hit = _BARS_CACHE.get(key)
    if hit and _t.monotonic() - hit[0] < _BARS_TTL:
        return hit[1]

    user = _user_or_404(db, user_id)
    try:
        client = tradier_bot.client_for(user, live=live)
    except Exception as exc:                          # noqa: BLE001
        raise _translated(exc) from exc
    try:
        # calendar days back, generous enough to cover weekends and holidays
        start = None
        if days > 1:
            back = datetime.now(CST).date() - _td(days=days * 2 + 3)
            start = f"{back:%Y-%m-%d} 00:00"
        raw = client.timesales(sym, interval=interval, start=start)
        bars = []
        for b in raw:
            try:
                bars.append({
                    "t": int(b.get("timestamp") or 0),
                    "time": b.get("time"),
                    "o": float(b.get("open") or 0),
                    "h": float(b.get("high") or 0),
                    "l": float(b.get("low") or 0),
                    "c": float(b.get("close") or b.get("price") or 0),
                    "v": float(b.get("volume") or 0),
                })
            except (TypeError, ValueError):
                continue
        prev_close = None
        try:
            q = (client.quotes([sym]) or [{}])[0]
            prev_close = float(q.get("prevclose")) if q.get("prevclose") else None
        except (TradierError, TypeError, ValueError, IndexError):
            prev_close = None
        out = {"symbol": sym, "interval": interval, "bars": bars,
               "prev_close": prev_close, "venue": "live" if live else "sandbox"}
        _BARS_CACHE[key] = (_t.monotonic(), out)
        return out
    except TradierError as exc:
        raise _translated(exc) from exc
    finally:
        client.close()


@router.get("/hot", operation_id="getTradierHotScan")
def hot_scan(
    user_id: str = Query(...),
    live: bool = Query(default=False,
                       description="true reads bars from the PRODUCTION venue"),
    interval: str | None = Query(
        default=None, pattern="^(5min|15min|30min|1h)$",
        description="bar size the DMI is computed on. All four are served "
                    "natively by Tradier — none is resampled — and each "
                    "carries its own lookback so every choice lands on a "
                    "comparable number of bars.",
        examples=["5min"]),
    refresh: bool = Query(default=False, description="force a sweep now"),
    db: Session = Depends(get_db),
) -> dict:
    """Top-100 names in a strong one-sided uptrend, by Wilder DMI/ADX.

    The gates: +DI above 25, +DI at least twice -DI, ADX above 34. The middle
    one is the point — a +DI/-DI crossover happens constantly and reverses
    just as often, while TWICE -DI says the buyers are not being answered.

    Returns the last good snapshot immediately and refreshes in the background
    when stale; a 100-name bar sweep must never sit in front of the render.
    """
    from app.services import hot_scan as hot_svc

    user = _user_or_404(db, user_id)
    try:
        return hot_svc.snapshot(user, live=live, interval=interval, force=refresh)
    except Exception as exc:                          # noqa: BLE001
        raise _translated(exc) from exc


@router.get("/flow", operation_id="getTradierOptionsFlow")
def options_flow(
    user_id: str = Query(...),
    live: bool = Query(default=False,
                       description="true reads chains from the PRODUCTION venue"),
    refresh: bool = Query(default=False, description="force a sweep now"),
    db: Session = Depends(get_db),
) -> dict:
    """Top option contracts by volume across the large-cap universe.

    Returns the last good snapshot immediately and refreshes in the
    background when it is stale — a 50-name chain sweep takes seconds and
    must never sit in front of the desk's render.
    """
    from app.services import options_flow as flow_svc

    user = _user_or_404(db, user_id)
    try:
        return flow_svc.snapshot(user, live=live, force=refresh)
    except Exception as exc:                          # noqa: BLE001
        raise _translated(exc) from exc


@router.get("/quotes", operation_id="getTradierQuotes")
def desk_quotes(
    user_id: str = Query(...),
    symbols: str = Query(default=DESK_TICKERS, max_length=500),
    live: bool = Query(default=False,
                       description="true quotes from the PRODUCTION venue"),
    db: Session = Depends(get_db),
) -> dict:
    """Live prices for the desk's ticker rail, in the requested order.

    Tradier batch quotes first (one request for the whole rail); any symbol
    Tradier does not return — indices on the sandbox, or the whole set when
    the account has no Tradier keys yet — is filled from a one-call yfinance
    batch, so the rail renders before the operator ever adds keys.
    """
    from app.services import quotes as quotes_svc

    syms, seen = [], set()
    for s in symbols.split(","):
        s = s.strip().upper()
        if s and s not in seen:
            seen.add(s)
            syms.append(s)
    if not syms:
        raise HTTPException(status_code=400, detail="no symbols given")

    cache_key = f"{user_id}:{'live' if live else 'sbx'}:{','.join(syms)}"
    import time as _t
    hit = _QUOTES_CACHE.get(cache_key)
    if hit and _t.monotonic() - hit[0] < _QUOTES_TTL:
        return hit[1]

    user = _user_or_404(db, user_id)
    found: dict[str, dict] = {}
    sources = set()
    try:
        client = tradier_bot.client_for(user, live=live)
        try:
            for q in client.quotes(syms):
                out = _tradier_quote_out(q)
                if out["symbol"] and out["price"] is not None:
                    found[out["symbol"]] = out
                    sources.add("tradier")
        finally:
            client.close()
    except Exception:  # noqa: BLE001 — no keys / venue down: yfinance covers
        pass

    missing = [s for s in syms if s not in found]
    if missing:
        try:
            for q in quotes_svc.batch_quotes(missing):
                if q.get("price") is not None:
                    found[q["symbol"]] = q
                    sources.add("yfinance")
        except Exception:  # noqa: BLE001 — a dead rail beats a 502 desk
            pass

    result = {
        "source": "+".join(sorted(sources)) or "none",
        "quotes": [found.get(s, {"symbol": s, "price": None, "prev_close": None,
                                 "change": None, "change_pct": None,
                                 "source": "none"}) for s in syms],
    }
    _QUOTES_CACHE[cache_key] = (_t.monotonic(), result)
    return result


@router.get("/chain", operation_id="previewTradierChain")
def chain_preview(
    user_id: str = Query(...),
    symbol: str = Query(..., max_length=12),
    side: str = Query(default="call", pattern="^(call|put)$"),
    delta_min: float = Query(default=tradier_bot.DEFAULT_DELTA_MIN, gt=0, lt=1),
    delta_max: float = Query(default=tradier_bot.DEFAULT_DELTA_MAX, gt=0, le=1),
    expiration: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    expiries: int = Query(default=1, ge=1, le=6,
                          description="how many expirations to try before "
                                      "giving up on the delta band"),
    zero_dte: bool = Query(default=False,
                           description="include today's expiration; off by "
                                       "default, so same-day contracts are "
                                       "only ever traded deliberately"),
    live: bool = Query(default=False,
                       description="true prices from the PRODUCTION venue"),
    db: Session = Depends(get_db),
) -> dict:
    """What WOULD be traded: the delta-band candidates and the pick.

    Exists so the desk can show the contract before any money moves — an
    executor that only reveals its choice after the fill is not operable.
    """
    user = _user_or_404(db, user_id)
    try:
        client = tradier_bot.client_for(user, live=live)
    except Exception as exc:                          # noqa: BLE001
        raise _translated(exc) from exc
    try:
        sym = symbol.upper()
        if expiration:
            candidates = [expiration]
        else:
            exps = client.expirations(sym) or []
            if not zero_dte:
                # Same-day contracts are excluded unless asked for: their
                # deltas are barely a position size, and an entry that has
                # hours to live is a different trade from the one the delta
                # band describes.
                today = f"{datetime.now(CST):%Y-%m-%d}"
                exps = [e for e in exps if str(e) > today]
            candidates = exps[:expiries]
        if not candidates:
            raise HTTPException(
                status_code=404,
                detail=(f"no {'' if zero_dte else 'non-0DTE '}expirations "
                        f"for {symbol}"))

        # Walk out until the band has something. The nearest expiry is often
        # 0DTE, whose deltas sit near 0 or 1 — a mid-band request against it
        # comes back empty most of the afternoon.
        # The preview must search the same SIGNED band the buy will, or it
        # shows a shortlist the executor would not have picked from.
        lo, hi = tradier_bot.delta_band(side, delta_min, delta_max)
        tried: list[str] = []
        for exp in candidates:
            raw = client.chain(sym, exp)
            band = []
            for o in raw:
                g = o.get("greeks") or {}
                d = g.get("delta")
                if d is None or (o.get("option_type") or "").lower() != side:
                    continue
                if lo <= float(d) <= hi:
                    band.append({
                        "occ_symbol": o.get("symbol"), "strike": o.get("strike"),
                        "bid": o.get("bid"), "ask": o.get("ask"),
                        # signed, as quoted — a put reads -0.30
                        "delta": round(float(d), 4),
                        "volume": o.get("volume"),
                        "open_interest": o.get("open_interest"),
                    })
            tried.append(exp)
            pick = tradier_bot.pick_contract(raw, side, delta_min, delta_max)
            if band or pick or exp == candidates[-1]:
                return {
                    "symbol": sym, "expiration": exp, "side": side,
                    # deepest-in-the-money first for both sides: sorting on
                    # the signed value would stand the put list on its head
                    "band": sorted(band, key=lambda x: abs(x["delta"]), reverse=True),
                    "pick": (pick or {}).get("symbol"),
                    "delta_band": [lo, hi],
                    "tried": tried,
                }
    except TradierError as exc:
        raise _translated(exc) from exc
    finally:
        client.close()


class OpenRequest(BaseModel):
    user_id: str
    symbol: str = Field(..., max_length=12, examples=["SPY"])
    side: str = Field(..., pattern="^(call|put)$")
    buy_pct: float = Field(default=tradier_bot.DEFAULT_BUY_PCT, gt=0, le=100,
                           description="% of option buying power to spend")
    tolerance_pct: float = Field(
        default=tradier_bot.DEFAULT_TOLERANCE_PCT, ge=0, le=100,
        description="how far either side of the buy_pct budget the total may "
                    "land. Contracts are indivisible, so the budget is a "
                    "target: at 50% of $100 with +/-25% the window is "
                    "$37.50-$62.50, which buys one contract at 0.60 (a strict "
                    "budget buys none) and two at 0.30 (a strict budget buys "
                    "one and parks $20). 0 restores the strict behaviour.",
        examples=[25],
    )
    delta_min: float = Field(default=tradier_bot.DEFAULT_DELTA_MIN, gt=0, lt=1)
    delta_max: float = Field(default=tradier_bot.DEFAULT_DELTA_MAX, gt=0, le=1)
    tp_pct: float = Field(default=tradier_bot.DEFAULT_TP_PCT, gt=0, le=500,
                          description="sell when the premium is this % above entry")
    sl_pct: float = Field(default=tradier_bot.DEFAULT_SL_PCT, gt=0, lt=100,
                          description="cancel the TP and sell when the bid is this % below entry")
    expiration: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$",
                                   description="YYYY-MM-DD; omit for the nearest listed")
    zero_dte: bool = Field(default=False,
                           description="allow today's expiration; off by "
                                       "default, so 0DTE is deliberate")
    discount_pct: float = Field(default=0, ge=0, le=50,
                                description="limit-price discount: 0 = market "
                                            "(smart_limit), 5/10/20 = that % below")
    live: bool = Field(default=False,
                       description="false (default) places a MOCK order on the "
                                   "Tradier sandbox; true spends real money on "
                                   "the production account")


@router.post("/positions", operation_id="openTradierPosition")
def open_position(payload: OpenRequest, db: Session = Depends(get_db)) -> dict:
    """Pick by delta, size by balance %, buy, then manage TP/SL.

    Sandbox unless ``live`` is explicitly true — the desk's LIVE toggle is the
    only thing that routes an order to the production account.
    """
    require_local_runtime("Placing a Tradier order")
    user = _user_or_404(db, payload.user_id)
    try:
        pos = tradier_bot.open_position(
            db, user,
            symbol=payload.symbol, side=payload.side, buy_pct=payload.buy_pct,
            tolerance_pct=payload.tolerance_pct,
            delta_min=payload.delta_min, delta_max=payload.delta_max,
            tp_pct=payload.tp_pct, sl_pct=payload.sl_pct,
            expiration=payload.expiration, live=payload.live,
            zero_dte=payload.zero_dte,
            discount_pct=payload.discount_pct,
        )
    except Exception as exc:                          # noqa: BLE001
        raise _translated(exc) from exc
    return _pos_out(pos)


class ContractRequest(BaseModel):
    """Buy one named contract — the flow board already chose it."""

    user_id: str
    occ_symbol: str = Field(..., max_length=32, examples=["TSLA260814C00350000"])
    buy_pct: float = Field(default=tradier_bot.DEFAULT_BUY_PCT, gt=0, le=100)
    tolerance_pct: float = Field(
        default=tradier_bot.DEFAULT_TOLERANCE_PCT, ge=0, le=100,
        description="how far either side of the buy_pct budget the total may land",
    )
    tp_pct: float = Field(default=tradier_bot.DEFAULT_TP_PCT, gt=0, le=500)
    sl_pct: float = Field(default=tradier_bot.DEFAULT_SL_PCT, gt=0, lt=100)
    discount_pct: float = Field(default=0, ge=0, le=50,
                                description="limit-price discount: 0 = market "
                                            "(smart_limit), 5/10/20 = that % below")
    live: bool = Field(default=False,
                       description="false (default) buys on the Tradier sandbox")


@router.post("/positions/contract", operation_id="openTradierContract")
def open_contract(payload: ContractRequest, db: Session = Depends(get_db)) -> dict:
    """Buy a specific option contract as a managed position.

    Same sizing, TP and SL as a hand-placed trade — the only difference is
    that the contract came from the flow board instead of the delta search.
    """
    require_local_runtime("Placing a Tradier order")
    user = _user_or_404(db, payload.user_id)
    try:
        pos = tradier_bot.open_contract(
            db, user, occ_symbol=payload.occ_symbol, buy_pct=payload.buy_pct,
            tolerance_pct=payload.tolerance_pct,
            tp_pct=payload.tp_pct, sl_pct=payload.sl_pct, live=payload.live,
            discount_pct=payload.discount_pct,
        )
    except Exception as exc:                          # noqa: BLE001
        raise _translated(exc) from exc
    return _pos_out(pos)


class TargetRequest(BaseModel):
    user_id: str
    target_price: float = Field(..., gt=0, le=10_000,
                                description="new take-profit price for this contract")


@router.post("/positions/{position_id}/target", operation_id="setTradierTarget")
def set_target(position_id: int, payload: TargetRequest,
               db: Session = Depends(get_db)) -> dict:
    """Move a live position's take-profit to an explicit price.

    Replaces the resting sell on the venue so the exit still happens without
    the desk running. Refuses if the old take-profit filled mid-edit, rather
    than stacking a second sell on a position that is already closing.
    """
    require_local_runtime("Moving a Tradier take-profit")
    user = _user_or_404(db, payload.user_id)
    try:
        pos = tradier_bot.set_target(db, user, position_id, payload.target_price)
    except Exception as exc:                          # noqa: BLE001
        raise _translated(exc) from exc
    return _pos_out(pos)


@router.get("/positions", operation_id="listTradierPositions")
def list_positions(
    user_id: str = Query(...),
    status: str = Query(default="all",
                        pattern="^(all|active|pending|open|tp_filled|sl_sold|closed|failed)$"),
    venue: str = Query(default="all", pattern="^(all|live|sandbox)$",
                       description="filter by the venue the position was opened on"),
    marks: bool = Query(default=False,
                        description="attach live bid + unrealized P&L for active rows"),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    user = _user_or_404(db, user_id)
    stmt = select(TradierPosition).where(TradierPosition.user_id == user_id)
    if status == "active":
        stmt = stmt.where(TradierPosition.status.in_(tradier_bot.ACTIVE_STATUSES))
    elif status != "all":
        stmt = stmt.where(TradierPosition.status == status)
    if venue == "live":
        stmt = stmt.where(TradierPosition.sandbox.is_(False))
    elif venue == "sandbox":
        stmt = stmt.where(TradierPosition.sandbox.is_(True))
    rows = list(db.scalars(
        stmt.order_by(TradierPosition.opened_at.desc()).limit(limit)
    ).all())
    quotes: dict[str, dict] = {}
    if marks and rows:
        quotes = tradier_bot.live_quotes(user, rows)

    def mark_for(p: TradierPosition) -> dict | None:
        # Keyed by contract, and two rows can hold the SAME contract — so a
        # settled row must not borrow the open row's quote and report a live
        # P&L next to its realized one.
        if p.status not in tradier_bot.ACTIVE_STATUSES:
            return None
        return quotes.get(p.occ_symbol)

    return {"total": len(rows),
            "items": [_pos_out(p, mark_for(p)) for p in rows]}


@router.post("/positions/sweep", operation_id="sweepTradierPositions")
def sweep(user_id: str = Query(...), db: Session = Depends(get_db)) -> dict:
    """Run one monitor pass now — the same sweep the background loop runs.

    The desk calls this on refresh so what it renders is the venue's current
    truth, not the state as of the last 10-second tick.
    """
    require_local_runtime("Sweeping Tradier positions")
    user = _user_or_404(db, user_id)
    try:
        return tradier_bot.monitor_pass(db, user)
    except Exception as exc:                          # noqa: BLE001
        raise _translated(exc) from exc


@router.post("/positions/{position_id}/close", operation_id="closeTradierPosition")
def close_position(position_id: int, user_id: str = Query(...),
                   force: bool = Query(
                       default=False,
                       description="sandbox only: stop tracking a pending row "
                                   "whose cancel the venue refuses"),
                   db: Session = Depends(get_db)) -> dict:
    """Manual exit: cancel resting orders, sell at market."""
    require_local_runtime("Closing a Tradier position")
    user = _user_or_404(db, user_id)
    try:
        return _pos_out(tradier_bot.close_position(db, user, position_id,
                                                   force=force))
    except Exception as exc:                          # noqa: BLE001
        raise _translated(exc) from exc


# ── auto-trade: opening-range level-cross watcher ───────────────────────────

class AutoTradeStart(BaseModel):
    """Omitted fields fall back to Settings (env: TBOT_TRADIER_*)."""

    user_id: str
    strategy: str | None = Field(default=None, examples=["10min_intraday_move"])
    tickers: str | None = Field(default=None, max_length=120,
                                description="comma-separated, e.g. SPY,QQQ,SPX")
    window_open: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$",
                                    description="HH:MM CST")
    window_close: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$",
                                     description="HH:MM CST")
    buy_pct: float | None = Field(default=None, gt=0, le=100)
    tolerance_pct: float | None = Field(
        default=None, ge=0, le=100,
        description="how far either side of the buy_pct budget a total may "
                    "land; 0 makes the budget a hard cap")
    tp_pct: float | None = Field(default=None, gt=0, le=500)
    sl_pct: float | None = Field(default=None, gt=0, lt=100)
    delta_min: float | None = Field(default=None, gt=0, lt=1)
    delta_max: float | None = Field(default=None, gt=0, le=1)
    min_contracts: int | None = Field(default=None, ge=1, le=1000)
    # --- ab_signal_options only ---
    books: str | None = Field(default=None, examples=["A,B"],
                              description="which super-signal books to act on")
    dte_max: int | None = Field(default=None, ge=0, le=30,
                                description="furthest expiration to consider, in days")
    zero_dte_cutoff: str | None = Field(
        default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$",
        description="CST time after which same-day expirations are not entered",
        examples=["13:00"])
    cooldown_min: int | None = Field(
        default=None, ge=0, le=1440,
        description="minutes this strategy must wait before re-entering the "
                    "same ticker (0 disables)",
        examples=[60])
    live: bool = Field(default=False,
                       description="false (default) arms the watcher on the "
                                   "SANDBOX venue; true trades real money")


@router.post("/autotrade/start", operation_id="startTradierAutoTrade")
def autotrade_start(payload: AutoTradeStart, db: Session = Depends(get_db)) -> dict:
    """Arm the opening-range auto-trader for this user.

    Watches the configured tickers' level crosses stamped inside the CST
    window; a new above_10min_high (CALL) / below_10min_low (PUT) must still
    hold after the confirmation delay, then the desk's normal managed 0DTE
    position is opened — TP rests on the venue, SL is the monitor loop.
    Sizing below min_contracts skips the trade.
    """
    from app.services import auto_trade

    require_local_runtime("Arming the auto-trader")
    _user_or_404(db, payload.user_id)
    try:
        return auto_trade.start(
            payload.user_id,
            strategy=payload.strategy, tickers=payload.tickers,
            window_open=payload.window_open, window_close=payload.window_close,
            buy_pct=payload.buy_pct, tolerance_pct=payload.tolerance_pct,
            tp_pct=payload.tp_pct, sl_pct=payload.sl_pct,
            delta_min=payload.delta_min, delta_max=payload.delta_max,
            min_contracts=payload.min_contracts, live=payload.live,
            books=payload.books, dte_max=payload.dte_max,
            zero_dte_cutoff=payload.zero_dte_cutoff,
            cooldown_min=payload.cooldown_min,
        )
    except auto_trade.AutoTradeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/autotrade/stop", operation_id="stopTradierAutoTrade")
def autotrade_stop(user_id: str = Query(...)) -> dict:
    from app.services import auto_trade

    require_local_runtime("Stopping the auto-trader")
    return auto_trade.stop(user_id)


@router.get("/autotrade/status", operation_id="getTradierAutoTradeStatus")
def autotrade_status(user_id: str = Query(...)) -> dict:
    from app.services import auto_trade

    return auto_trade.status(user_id)


def _limit_price(p: TradierPosition) -> float | None:
    """The limit the buy was placed at — the ask when the contract was picked."""
    raw = p.raw if isinstance(p.raw, dict) else {}
    try:
        return float((raw.get("picked") or {}).get("ask"))
    except (TypeError, ValueError):
        return None


def _pos_out(p: TradierPosition, quote: dict | None = None) -> dict:
    # TP/SL are percentages OF THE FILL, so they cannot be final until the
    # buy fills. While it is still working, show what they would be at the
    # limit price and mark them provisional — blank cells read as "stale"
    # when the truth is "this order has not filled yet".
    tp_price, sl_price = p.tp_price, p.sl_price
    provisional = False
    if p.status == "pending" and p.entry_price is None and tp_price is None:
        limit = _limit_price(p)
        if limit:
            tp_price, sl_price = tradier_bot.exit_prices(limit, p.tp_pct, p.sl_pct)
            provisional = True

    # Unrealized mark and P&L for a position that is still running. Priced on
    # the BID: that is what closing it right now would actually pay.
    live_bid = live_pnl = None
    if quote is not None:
        try:
            live_bid = float(quote.get("bid")) if quote.get("bid") is not None else None
        except (TypeError, ValueError):
            live_bid = None
        if live_bid is not None and p.entry_price and p.contracts:
            live_pnl = round((live_bid - p.entry_price) * 100 * p.contracts, 2)
    return {
        "id": p.id, "status": p.status, "sandbox": p.sandbox,
        "live_bid": live_bid, "live_pnl_usd": live_pnl,
        "strategy": p.strategy or "Manual",
        "underlying": p.underlying, "occ_symbol": p.occ_symbol,
        "option_type": p.option_type, "strike": p.strike,
        "expiration": p.expiration, "delta_at_entry": p.delta_at_entry,
        "contracts": p.contracts, "entry_price": p.entry_price,
        "tp_price": tp_price, "sl_price": sl_price,
        "exits_provisional": provisional,
        "limit_price": _limit_price(p) if p.entry_price is None else None,
        "tp_pct": p.tp_pct, "sl_pct": p.sl_pct, "buy_pct": p.buy_pct,
        # what the size actually came to, so the desk can show why it is
        # that many contracts rather than the round number buy_pct implies
        "sizing": (p.raw or {}).get("sizing"),
        "exit_price": p.exit_price, "pnl_usd": p.pnl_usd,
        "note": p.note,
        "opened_at": p.opened_at.isoformat() if p.opened_at else None,
        "closed_at": p.closed_at.isoformat() if p.closed_at else None,
    }
