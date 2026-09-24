"""Super Signals: the signal-agent desk, read through its own service.

The desk -- eight strategy agents on one 5m feed, a watchlist tracker, and a
daily report at 15:00 CST -- is a separate project with its own schedule. It
serves a read-only view of itself on loopback, and this router is the only
door into it: the sign-in stays in front, and this project still reads no file
outside its own folder (tools/check_self_contained.py). The HTTP client is
shared with the super_signals auto-trade strategy (app.services.super_signals).

Access matches /super: any signed-in operator may read -- a signal is a fact
about the market, the same for everybody on the desk -- and there is nothing
to write. The service itself has no sign-in and binds to loopback; proxying it
is what keeps the tunnel from exposing it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Path as PathParam

from app.api_v2 import deps
from app.services import super_signals as desk
from app.tenancy.models import Tenant

router = APIRouter(prefix="/super-signals", tags=["super-signals"])

DATE = r"^\d{4}-\d{2}-\d{2}$"


def _relay(fn, *args):
    try:
        return fn(*args)
    except desk.Unavailable as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from None


@router.get("/session", operation_id="getSuperSignalsSession")
@deps.tenant_scoped
def session(date: str | None = Query(default=None, pattern=DATE),
            tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """One session's signals, the watchlist tracker's hits and desk health.

    No date is today on a trading day, otherwise the last session -- so a
    weekend visit shows Friday rather than an empty board."""
    return _relay(desk.get_json, "/api/session", {"date": date} if date else None)


@router.get("/rank", operation_id="getSuperSignalsRank")
@deps.tenant_scoped
def rank(date: str | None = Query(default=None, pattern=DATE),
         tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """Signal types ranked by the daily report's edge score for one session --
    the previous one when it has none ranked yet -- with types whose longest
    window disagrees held apart. What the super_signals auto-trade form lists."""
    return _relay(desk.get_json, "/api/rank", {"date": date} if date else None)


@router.get("/best-pairs", operation_id="getSuperSignalsBestPairs")
@deps.tenant_scoped
def best_pairs(min_win_pct: float | None = Query(default=None, ge=0, le=100),
               min_edge: float | None = Query(default=None, ge=0, le=100),
               min_net_r: float | None = Query(default=None, ge=-1000, le=1000),
               tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """The daily report's best ticker + signal pairs over the last 30 sessions,
    best first, each with how often it fired today, yesterday and over the past
    week -- the desk's best_ticker_signal_pairs table, rewritten after every
    report. Each minimum is optional and inclusive: win % (wins over wins +
    losses), edge score (50 = breakeven), net R. The bounds also turn away NaN
    and infinity, so the desk is only ever asked with a real number."""
    mins = {"min_win_pct": min_win_pct, "min_edge": min_edge, "min_net_r": min_net_r}
    return _relay(desk.get_json, "/api/best-pairs",
                  {k: v for k, v in mins.items() if v is not None} or None)


@router.get("/reports", operation_id="getSuperSignalsReports")
@deps.tenant_scoped
def reports(tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """The daily reports on file, newest first."""
    return _relay(desk.get_json, "/api/reports")


@router.get("/reports/{report_date}", operation_id="getSuperSignalsReport")
@deps.tenant_scoped
def report(report_date: str = PathParam(pattern=DATE),
           tenant: Tenant = Depends(deps.current_tenant)) -> dict:
    """One daily report page, wrapped in JSON.

    Wrapped rather than served as text/html: the desk's client treats any
    non-JSON answer as "backend not reachable", and the page is rendered from
    this string in a sandboxed frame -- so its scripts never run with the
    desk's origin or its session token."""
    return {"date": report_date,
            "html": _relay(desk.get, f"/reports/{report_date}.html").text}
