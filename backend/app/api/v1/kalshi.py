from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_user_or_404
from app.core.database import get_db
from app.models import User
from app.schemas.kalshi import KalshiClientState
from app.services import credentials as creds_svc
from app.services.kalshi_client import KalshiApiError, KalshiAuthError, KalshiClient

router = APIRouter(prefix="/users/{user_id}", tags=["kalshi"])

# Portfolio value is signed-request-per-call against Kalshi. The desk polls it
# every 5 minutes, but several open tabs (or a reload loop) would multiply
# that, so serve repeats from a short cache.
_PV_TTL_S = 30.0
_pv_cache: dict[str, tuple[float, dict]] = {}
_pv_lock = Lock()


def _pv_cache_get(user_id: str) -> dict | None:
    with _pv_lock:
        hit = _pv_cache.get(user_id)
        if hit and monotonic() - hit[0] < _PV_TTL_S:
            return {**hit[1], "cached": True}
    return None


def _pv_cache_put(user_id: str, payload: dict) -> None:
    with _pv_lock:
        _pv_cache[user_id] = (monotonic(), payload)


class KalshiClientRequest(BaseModel):
    # Optional passphrase for password-protected PEM files.
    pem_password: str | None = None


@router.post(
    "/kalshi-client",
    operation_id="getKalshiClient",
    response_model=KalshiClientState,
)
def get_kalshi_client(
    payload: KalshiClientRequest | None = None,
    user: User = Depends(get_user_or_404),
) -> KalshiClientState:
    """Read credentials from the user's root folder, authenticate against
    Kalshi (read-only balance + exchange status), and return connection state.
    Never places orders."""
    try:
        creds = creds_svc.load_kalshi_credentials(user.user_root_folder)
    except creds_svc.CredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY, detail=str(exc))

    pem_password = payload.pem_password if payload else None
    try:
        client = KalshiClient(
            creds.api_key_id,
            creds.private_key_path,
            creds.base_uri,
            pem_password=pem_password,
        )
    except KalshiAuthError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    checked_at = datetime.now(timezone.utc)
    try:
        balance = client.balance_cents()
        exchange = client.exchange_status()
        return KalshiClientState(
            user_id=user.user_id,
            environment="prod" if "external-api" in creds.base_uri else "custom",
            api_key_id_masked=creds.api_key_id_masked,
            authenticated=True,
            balance_cents=balance,
            exchange_active=exchange.get("exchange_active"),
            trading_active=exchange.get("trading_active"),
            checked_at=checked_at,
            detail=f"credentials from {creds.env_file.name}; dry_run={creds.dry_run}",
        )
    except KalshiApiError as exc:
        if exc.status_code in (401, 403):
            return KalshiClientState(
                user_id=user.user_id,
                environment="prod" if "external-api" in creds.base_uri else "custom",
                api_key_id_masked=creds.api_key_id_masked,
                authenticated=False,
                checked_at=checked_at,
                detail=f"Kalshi rejected credentials: HTTP {exc.status_code}",
            )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    except Exception as exc:  # network failures
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Kalshi unreachable: {exc}")
    finally:
        client.close()


def _record_daily_pv(db, user_id: str, pv: dict) -> None:
    """Upsert TODAY's (CST) portfolio value into daily_snapshots (kind 'pv').

    Every fresh Kalshi fetch overwrites the day's row, so each date holds the
    LAST value seen that day — the daily pixel graph reads this series. One
    row per calendar day, account-wide (the Kalshi account is shared).
    """
    from zoneinfo import ZoneInfo

    from sqlalchemy import select as sa_select

    from app.models import DailySnapshot

    today = datetime.now(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")
    payload = {
        "total_usd": round((pv.get("cash_usd") or 0) + (pv.get("positions_usd") or 0), 2),
        "cash_usd": pv.get("cash_usd"),
        "positions_usd": pv.get("positions_usd"),
        "user_id": user_id,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    row = db.scalar(sa_select(DailySnapshot).where(
        DailySnapshot.kind == "pv", DailySnapshot.snapshot_date == today))
    if row is None:
        db.add(DailySnapshot(kind="pv", snapshot_date=today, payload=payload,
                             source_file="kalshi_portfolio",
                             fetched_at=datetime.now(timezone.utc).replace(tzinfo=None)))
    else:
        row.payload = payload
        row.fetched_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()


@router.get("/portfolio", operation_id="getPortfolioValue")
def get_portfolio_value(user: User = Depends(get_user_or_404),
                        db=Depends(get_db)) -> dict:
    """Live portfolio value: settled cash + mark-to-market on open positions.

    Read-only, and the same figure the bots print as [TARGET-PV], so the desk
    and the bot logs agree. Cached briefly so a polling UI cannot turn into a
    request per viewer per second against Kalshi. Every FRESH fetch also
    files today's value into daily_snapshots for the PV progress graph.
    """
    cached = _pv_cache_get(user.user_id)
    if cached is not None:
        return cached

    try:
        creds = creds_svc.load_kalshi_credentials(user.user_root_folder)
    except creds_svc.CredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_424_FAILED_DEPENDENCY, detail=str(exc))
    try:
        client = KalshiClient(creds.api_key_id, creds.private_key_path, creds.base_uri)
    except KalshiAuthError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    try:
        pv = client.portfolio()
    except KalshiApiError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Kalshi unreachable: {exc}"
        )
    finally:
        client.close()

    out = {**pv, "fetched_at": datetime.now(timezone.utc).isoformat(), "cached": False}
    _pv_cache_put(user.user_id, out)
    try:
        _record_daily_pv(db, user.user_id, pv)   # the graph's daily capture
    except Exception:  # noqa: BLE001 — recording must never sink the read
        db.rollback()
    return out


@router.get("/portfolio/history", operation_id="getPortfolioHistory")
def get_portfolio_history(days: int = 366,
                          user: User = Depends(get_user_or_404),
                          db=Depends(get_db)) -> dict:
    """Daily portfolio values (kind 'pv' snapshots), oldest first.

    One row per CST calendar day, written by every fresh /portfolio fetch —
    feeds the desk's pixel progress graph.
    """
    from sqlalchemy import select as sa_select

    from app.models import DailySnapshot

    rows = db.scalars(
        sa_select(DailySnapshot).where(DailySnapshot.kind == "pv")
        .order_by(DailySnapshot.snapshot_date.desc()).limit(max(1, min(days, 3660)))
    ).all()
    items = [{
        "date": r.snapshot_date,
        "total_usd": (r.payload or {}).get("total_usd"),
        "cash_usd": (r.payload or {}).get("cash_usd"),
        "positions_usd": (r.payload or {}).get("positions_usd"),
        "seeded": bool((r.payload or {}).get("seeded")),
    } for r in reversed(rows)]
    return {"total": len(items), "items": items}


class PasswordCheck(BaseModel):
    password: str


@router.post("/verify-password", operation_id="verifyUserPassword")
def verify_password(payload: PasswordCheck, user: User = Depends(get_user_or_404)) -> dict:
    """Timing-safe check against the folder's .sam password file (legacy
    wellness/sports app login contract)."""
    ok = creds_svc.verify_password(user.user_root_folder, payload.password)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return {"user_id": user.user_id, "verified": True}
