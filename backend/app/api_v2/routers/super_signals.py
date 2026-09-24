"""Super Signals: the signal-agent desk, read through its own service.

The desk -- eight strategy agents on one 5m feed, a watchlist tracker, and a
daily report at 15:00 CST -- is a separate project with its own schedule. It
serves a read-only view of itself on loopback, and this router is the only
door into it: the sign-in stays in front, and this project still reads no file
outside its own folder (tools/check_self_contained.py).

Access matches /super: any signed-in operator may read -- a signal is a fact
about the market, the same for everybody on the desk -- and there is nothing
to write. The service itself has no sign-in and binds to loopback; proxying it
is what keeps the tunnel from exposing it.
"""

from __future__ import annotations

import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Path as PathParam

from app.api_v2 import deps
from app.core.config import get_settings
from app.tenancy.models import Tenant

router = APIRouter(prefix="/super-signals", tags=["super-signals"])

DATE = r"^\d{4}-\d{2}-\d{2}$"
OFFLINE = ("the super signals service is not answering -- it runs from the "
           "vidura-super-signals project (task Vidura_SignalAgents_API, or "
           "`python -m signal_agents.desk serve` there)")

# One pooled session, blind to proxy settings in the environment: the service
# is on loopback, and a machine-wide proxy would otherwise be asked to reach
# 127.0.0.1 on this process's behalf.
_http = requests.Session()
_http.trust_env = False


def _detail(r: requests.Response) -> str:
    try:
        return r.json().get("detail") or r.reason
    except ValueError:
        return r.reason


def _get(path: str, params: dict | None = None) -> requests.Response:
    s = get_settings()
    try:
        r = _http.get(s.super_signals_url.rstrip("/") + path, params=params,
                      timeout=s.super_signals_timeout_s)
    except requests.Timeout as exc:
        raise HTTPException(status_code=504,
                            detail="the super signals service did not answer in time") from exc
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail=OFFLINE) from exc
    if r.status_code in (400, 404):
        raise HTTPException(status_code=r.status_code, detail=_detail(r))
    if not r.ok:
        raise HTTPException(status_code=502,
                            detail=f"the super signals service answered {r.status_code}: {_detail(r)}")
    return r


@router.get("/session", operation_id="getSuperSignalsSession")
@deps.tenant_scoped
def session(date: str | None = Query(default=None, pattern=DATE),
            tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """One session's signals, the watchlist tracker's hits and desk health.

    No date is today on a trading day, otherwise the last session -- so a
    weekend visit shows Friday rather than an empty board."""
    return _get("/api/session", {"date": date} if date else None).json()


@router.get("/reports", operation_id="getSuperSignalsReports")
@deps.tenant_scoped
def reports(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """The daily reports on file, newest first."""
    return _get("/api/reports").json()


@router.get("/reports/{report_date}", operation_id="getSuperSignalsReport")
@deps.tenant_scoped
def report(report_date: str = PathParam(pattern=DATE),
           tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """One daily report page, wrapped in JSON.

    Wrapped rather than served as text/html: the desk's client treats any
    non-JSON answer as "backend not reachable", and the page is rendered from
    this string in a sandboxed frame -- so its scripts never run with the
    desk's origin or its session token."""
    return {"date": report_date, "html": _get(f"/reports/{report_date}.html").text}
