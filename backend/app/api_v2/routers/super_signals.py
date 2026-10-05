"""Super Signals: the signal-agent desk, read through its own service.

The desk -- eight strategy agents on one 5m feed, a watchlist tracker, and a
daily report at 15:00 CST -- is a separate project with its own schedule. It
serves a view of itself on loopback, and an on/off switch, and this router is
the only door into it: the sign-in stays in front, and this project still
reads no file outside its own folder (tools/check_self_contained.py). The HTTP
client is shared with the super_signals auto-trade strategy
(app.services.super_signals).

Access matches /super: any signed-in operator may read -- a signal is a fact
about the market, the same for everybody on the desk -- and only an admin may
start or stop the desk, as only an admin turns the /super engine on and off:
there is one desk, and it serves every operator. The service itself has no
sign-in and binds to loopback; proxying it is what keeps the tunnel from
exposing it.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import Path as PathParam
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DbSession

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
    weekend visit shows Friday rather than an empty board.

    Each signal carries the channel's marks: ``stars`` (1-3, the pair's win
    rate above 66% over the last 1, 3 or 7 sessions before this one) and the
    ``star_record`` that earned them."""
    from app.domains.notify import super_telegram

    data = _relay(desk.get_json, "/api/session", {"date": date} if date else None)
    try:
        return super_telegram.mark_session(data)
    except Exception:                                   # noqa: BLE001
        return data


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


@router.post("/desk/start", status_code=202, operation_id="startSuperSignalsDesk")
def desk_start(tenant: Tenant = Depends(deps.require_admin)) -> dict:
    """Start the desk, as its 08:15 task does: for a morning the task missed,
    or after a stop. Started late, it catches up from the open, so today's
    signals so far appear at once. 409 when it is already running or today is
    not a trading day."""
    return _relay(desk.post_json, "/api/desk/start")


@router.post("/desk/stop", status_code=202, operation_id="stopSuperSignalsDesk")
def desk_stop(tenant: Tenant = Depends(deps.require_admin)) -> dict:
    """End the desk's day early, gracefully: the agents finish their cycle,
    the desk reconciles and writes the day's report, and no new signal comes
    in until it is started again. Positions are not the desk's -- nothing is
    closed. 409 when it is not running."""
    return _relay(desk.post_json, "/api/desk/stop")


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


# ---- new signals to Telegram ------------------------------------------------
# Each operator's own: their bot, their chat, their switch. The token is sealed
# like every other key and never comes back out -- an answer says only whether
# one is saved.
class TelegramFeedRequest(BaseModel):
    token: str | None = Field(default=None, max_length=128)
    chat_id: str | None = Field(default=None, max_length=64)
    chat_title: str | None = Field(default=None, max_length=128)
    enabled: bool | None = None


class TelegramChatsRequest(BaseModel):
    # A token typed into the form but not saved yet; omitted, the saved one.
    token: str | None = Field(default=None, max_length=128)


def _telegram(fn, *args, **kwargs):
    from app.platform import notify

    try:
        return fn(*args, **kwargs)
    except notify.NotifyError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("/telegram", operation_id="getSuperSignalsTelegram")
@deps.tenant_scoped
def telegram_get(tenant: Tenant = Depends(deps.current_tenant),
                 db: DbSession = Depends(deps.get_db),
                 kr=Depends(deps.keyring)) -> dict:
    """Where this operator's new signals go: the chat, the switch, the last
    post and the last error, and whether a bot token is saved."""
    from app.domains.notify import super_telegram

    return super_telegram.get_state(db, tenant.id, kr)


@router.put("/telegram", operation_id="setSuperSignalsTelegram")
@deps.tenant_scoped
def telegram_set(payload: TelegramFeedRequest,
                 tenant: Tenant = Depends(deps.current_tenant),
                 db: DbSession = Depends(deps.get_db),
                 kr=Depends(deps.keyring)) -> dict:
    """Save the bot token, the chat and the switch -- any of them. Switching
    on needs a token and a chat, and posts only signals raised from then."""
    from app.domains.notify import super_telegram

    return _telegram(super_telegram.set_state, db, tenant, kr,
                     token=payload.token, chat_id=payload.chat_id,
                     chat_title=payload.chat_title, enabled=payload.enabled,
                     actor=tenant.slug)


@router.post("/telegram/chats", operation_id="listSuperSignalsTelegramChats")
@deps.tenant_scoped
def telegram_chats(payload: TelegramChatsRequest,
                   tenant: Tenant = Depends(deps.current_tenant),
                   db: DbSession = Depends(deps.get_db),
                   kr=Depends(deps.keyring)) -> dict:
    """The chats the bot can see -- how to find a private channel's id once
    the bot is an admin there."""
    from app.domains.notify import super_telegram

    token = (payload.token or "").strip() or super_telegram._token(db, tenant.id, kr)
    if not token:
        raise HTTPException(status_code=422, detail="paste the bot token first")
    return {"chats": _telegram(super_telegram.chats, token)}


@router.post("/telegram/test", operation_id="testSuperSignalsTelegram")
@deps.tenant_scoped
def telegram_test(tenant: Tenant = Depends(deps.current_tenant),
                  db: DbSession = Depends(deps.get_db),
                  kr=Depends(deps.keyring)) -> dict:
    """One test message to the saved chat."""
    from app.domains.notify import super_telegram

    return _telegram(super_telegram.send_test, db, tenant.id, kr)
