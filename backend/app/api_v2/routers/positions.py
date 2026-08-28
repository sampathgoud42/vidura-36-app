"""Positions: the money-moving surface.

Every mutating route here is idempotent by construction. The attempt row is
written before the venue is called, so a repeat submit returns the FIRST
outcome instead of placing a second order — which is what a double-tap on BUY
now does.

There is no ``user_id`` anywhere. The operator comes from the session.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.api_v2 import deps
from app.domains.trading.execution import idempotency, leases, orders, selection
from app.domains.trading.execution import venue as venue_mod
from app.domains.trading.execution.orders import ExecutionRefused
from app.domains.trading.models import Position
from app.domains.trading.risk.validation import RiskRefused, validate_entry
from app.platform.security.envelope import Keyring
from app.tenancy import repository as tenants
from app.tenancy.models import Tenant

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tradier", tags=["trading"])


class OpenRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    side: str
    buy_pct: float = 50.0
    tp_pct: float = 15.0
    sl_pct: float = 30.0
    delta_min: float = 0.25
    delta_max: float = 0.50
    tolerance_pct: float = 25.0
    expiration: str | None = None
    zero_dte: bool = False
    live: bool = False
    strategy: str = "Manual"
    # Guard 3's deliberate override. The default answers no.
    allow_add: bool = False


def _serialise(pos: Position) -> dict:
    return {
        "id": pos.id,
        "underlying": pos.underlying,
        "occ_symbol": pos.occ_symbol,
        "option_type": pos.option_type,
        "strike": pos.strike,
        "expiration": pos.expiration,
        "contracts": pos.contracts,
        "delta_at_entry": pos.delta_at_entry,
        "entry_price": pos.entry_price,
        "tp_price": pos.tp_price,
        "sl_price": pos.sl_price,
        "tp_pct": pos.tp_pct,
        "sl_pct": pos.sl_pct,
        "buy_order_id": pos.buy_order_id,
        "tp_order_id": pos.tp_order_id,
        "stop_order_id": pos.stop_order_id,
        # Says out loud whether the stop survives this process dying.
        "stop_protection": pos.stop_protection,
        "status": pos.status,
        "strategy": pos.strategy,
        "venue": "sandbox" if pos.venue_sandbox else "live",
        "needs_review": pos.needs_review,
        "opened_at": pos.opened_at,
        "closed_at": pos.closed_at,
        "exit_price": pos.exit_price,
        "pnl_usd": pos.pnl_usd,
        "note": pos.note,
    }


def _credential(db: DbSession, tenant: Tenant, kr: Keyring, *, live: bool):
    venue_name = "tradier" if live else "tradier_sandbox"
    try:
        return tenants.load_credential(db, tenant.id, venue_name, kr)
    except Exception as exc:                            # noqa: BLE001
        # Never pass the venue's own text through: a 401 body can contain the
        # token that was rejected.
        raise HTTPException(
            status_code=424,
            detail=f"no usable {venue_name} credential for this operator",
        ) from exc


# ---- reads ----------------------------------------------------------------

@router.get("/positions", operation_id="listTradierPositions")
@deps.tenant_scoped
def list_positions(status: str | None = Query(default=None),
                   venue: str = Query(default="all"),
                   limit: int = Query(default=200, le=1000),
                   tenant: Tenant = Depends(deps.current_tenant),
                   db: DbSession = Depends(deps.get_db)) -> dict:
    stmt = select(Position).where(Position.tenant_id == tenant.id)
    if status:
        stmt = stmt.where(Position.status == status)
    if venue in ("sandbox", "live"):
        stmt = stmt.where(Position.venue_sandbox.is_(venue == "sandbox"))

    # Counted over the SAME predicate as the rows. A total computed without
    # the tenant filter is a leak that returns no rows.
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(db.scalars(
        stmt.order_by(Position.id.desc()).limit(limit)).all())
    return {"items": [_serialise(p) for p in rows], "total": total}


@router.get("/positions/{position_id}", operation_id="getTradierPosition")
@deps.tenant_scoped
def get_position(position_id: int,
                 tenant: Tenant = Depends(deps.current_tenant),
                 db: DbSession = Depends(deps.get_db)) -> dict:
    pos = db.get(Position, position_id)
    # 404 for another tenant's row, identical to one that does not exist. A
    # 403 would confirm it exists and turn an id into an oracle.
    if pos is None or pos.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Not found")
    return _serialise(pos)


# ---- the entry ------------------------------------------------------------

@router.post("/positions", operation_id="openTradierPosition")
@deps.tenant_scoped
def open_position(payload: OpenRequest,
                  idempotency_key: str | None = Header(default=None,
                                                       alias="Idempotency-Key"),
                  tenant: Tenant = Depends(deps.current_tenant),
                  db: DbSession = Depends(deps.get_db),
                  kr: Keyring = Depends(deps.keyring)) -> dict:
    body = payload.model_dump()
    body.pop("allow_add", None)     # not part of the request's identity

    # Guard 1, before anything else can happen twice.
    try:
        attempt = idempotency.begin(db, tenant_id=tenant.id, intent="open",
                                    payload=body, client_key=idempotency_key)
    except idempotency.DuplicateRequest as dup:
        db.commit()
        stored = idempotency.stored_result(dup.attempt)
        if stored:
            return stored
        raise HTTPException(
            status_code=409,
            detail="this request is already in flight; nothing was placed twice",
        ) from None
    except idempotency.KeyReused as exc:
        db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from None

    # Guard 6 first, and before the venue is reached at all. Validating
    # inside the order path meant a bad side surfaced as "no contract found"
    # and a zero size as "sized to zero" -- both true, neither the real fault.
    try:
        validate_entry(side=payload.side, buy_pct=payload.buy_pct,
                       tp_pct=payload.tp_pct, sl_pct=payload.sl_pct,
                       expiration=payload.expiration)
    except RiskRefused as exc:
        idempotency.fail(db, attempt, reason=str(exc))
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from None

    cred = _credential(db, tenant, kr, live=payload.live)
    sandbox = not payload.live

    try:
        chain, expiration = _load_chain(cred, payload, sandbox=sandbox)
        opt = selection.pick_contract(chain, payload.side,
                                      payload.delta_min, payload.delta_max)
        if opt is None:
            lo, hi = selection.delta_band(payload.side, payload.delta_min,
                                          payload.delta_max)
            raise ExecutionRefused(
                f"no {payload.side} on {payload.symbol} {expiration} with a "
                f"delta in {lo:+g}..{hi:+g} and a two-sided quote",
                status_code=404)

        limit_price = selection.smart_limit(float(opt.get("bid") or 0),
                                            float(opt["ask"]))
        buying_power = float(
            (venue_mod.balance(cred=cred, sandbox=sandbox) or {})
            .get("option_buying_power") or 0)
        sizing = selection.size_contracts(
            buying_power, payload.buy_pct, limit_price,
            tolerance_pct=payload.tolerance_pct)
        if sizing.contracts < 1:
            raise ExecutionRefused(f"sized to zero: {sizing.explain()}",
                                   status_code=409)

        pos = orders.open_position(
            db, tenant_id=tenant.id, cred=cred, symbol=payload.symbol,
            side=payload.side, occ_symbol=opt["symbol"],
            underlying=payload.symbol, strike=float(opt.get("strike") or 0),
            expiration=expiration, delta=opt.get("_delta"),
            contracts=sizing.contracts, limit_price=limit_price,
            buy_pct=payload.buy_pct, tolerance_pct=payload.tolerance_pct,
            tp_pct=payload.tp_pct, sl_pct=payload.sl_pct, sandbox=sandbox,
            strategy=payload.strategy, allow_add=payload.allow_add,
            zero_dte=payload.zero_dte,
        )
        result = _serialise(pos)
        idempotency.succeed(db, attempt, result=result, position_id=pos.id,
                            venue_order_id=pos.buy_order_id)
        db.commit()
        return result

    except (ExecutionRefused, RiskRefused, leases.LeaseUnavailable) as exc:
        # A refusal releases the key: the order did NOT go through, and
        # answering "duplicate" on the operator's retry would be a lie.
        idempotency.fail(db, attempt, reason=str(exc))
        db.commit()
        status_code = getattr(exc, "status_code", 409)
        raise HTTPException(status_code=status_code, detail=str(exc)) from None
    except HTTPException:
        idempotency.fail(db, attempt, reason="upstream refused")
        db.commit()
        raise
    except Exception as exc:                            # noqa: BLE001
        idempotency.fail(db, attempt, reason=str(exc))
        db.commit()
        logger.exception("open_position failed for tenant %s", tenant.id)
        raise HTTPException(status_code=502,
                            detail="the venue could not be reached") from None


def _load_chain(cred, payload: OpenRequest, *, sandbox: bool):
    """The chain to pick from, and the expiration it belongs to.

    Goes through the venue seam like every other broker call. It used to build
    its own client here, which meant substituting the venue substituted only
    half of the outbound calls -- the half that was easy to notice.
    """
    listed = venue_mod.expirations(payload.symbol, cred=cred, sandbox=sandbox)
    if not listed:
        raise ExecutionRefused(f"no listed expirations for {payload.symbol}",
                               status_code=404)
    expiration = payload.expiration or _choose_expiration(
        listed, zero_dte=payload.zero_dte)
    return venue_mod.option_chain(payload.symbol, expiration,
                                  cred=cred, sandbox=sandbox), expiration


def _choose_expiration(expirations: list[str], *, zero_dte: bool) -> str:
    """Nearest listed expiry, skipping today unless 0DTE was asked for.

    A same-day contract with hours left is a different trade from the one a
    delta band describes, so it has to be requested rather than fallen into.
    """
    from app.domains.trading.risk import clock

    today = clock.today().isoformat()
    for exp in sorted(expirations):
        if exp == today and not zero_dte:
            continue
        if exp >= today:
            return exp
    return sorted(expirations)[-1]


# ---- the exit -------------------------------------------------------------

@router.post("/positions/{position_id}/close", operation_id="closeTradierPosition")
@deps.tenant_scoped
def close_position(position_id: int,
                   force: bool = Query(default=False),
                   idempotency_key: str | None = Header(default=None,
                                                        alias="Idempotency-Key"),
                   tenant: Tenant = Depends(deps.current_tenant),
                   db: DbSession = Depends(deps.get_db),
                   kr: Keyring = Depends(deps.keyring)) -> dict:
    pos = db.get(Position, position_id)
    if pos is None or pos.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Not found")

    try:
        attempt = idempotency.begin(
            db, tenant_id=tenant.id, intent="close",
            payload={"position_id": position_id, "force": force},
            client_key=idempotency_key)
    except idempotency.DuplicateRequest as dup:
        db.commit()
        return idempotency.stored_result(dup.attempt) or _serialise(pos)
    except idempotency.KeyReused as exc:
        db.commit()
        raise HTTPException(status_code=409, detail=str(exc)) from None

    cred = _credential(db, tenant, kr, live=not pos.venue_sandbox)
    try:
        closed = orders.close_position(db, tenant_id=tenant.id, cred=cred,
                                       pos=pos, force=force)
        result = _serialise(closed)
        idempotency.succeed(db, attempt, result=result, position_id=closed.id)
        db.commit()
        return result
    except (ExecutionRefused, leases.LeaseUnavailable) as exc:
        idempotency.fail(db, attempt, reason=str(exc))
        db.commit()
        raise HTTPException(status_code=getattr(exc, "status_code", 409),
                            detail=str(exc)) from None
    except Exception as exc:                            # noqa: BLE001
        idempotency.fail(db, attempt, reason=str(exc))
        db.commit()
        logger.exception("close_position failed")
        raise HTTPException(status_code=502,
                            detail="the venue could not be reached") from None


# ---- credential health ----------------------------------------------------

credentials_router = APIRouter(prefix="/credentials", tags=["tenancy"])


@credentials_router.post("/{venue}/verify", operation_id="verifyCredential")
@deps.tenant_scoped
def verify_credential(venue: str,
                      tenant: Tenant = Depends(deps.current_tenant),
                      db: DbSession = Depends(deps.get_db),
                      kr: Keyring = Depends(deps.keyring)) -> dict:
    """Does this operator's credential work? Yes or no, never the credential.

    Load-bearing under runtime onboarding: it is how a new customer's keys are
    confirmed without anyone reading them back.
    """
    try:
        cred = tenants.load_credential(db, tenant.id, venue, kr)
    except Exception:                                   # noqa: BLE001
        raise HTTPException(status_code=424,
                            detail=f"no active {venue} credential") from None
    try:
        venue_mod.balance(cred=cred, sandbox=venue.endswith("sandbox"))
    except Exception as exc:                            # noqa: BLE001
        logger.info("credential verify failed for %s/%s", tenant.slug, venue)
        return {"venue": venue, "reachable": False,
                "detail": type(exc).__name__}
    return {"venue": venue, "reachable": True, **cred.public()}
