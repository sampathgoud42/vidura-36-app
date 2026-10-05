"""SUPERHOT on Telegram: a ticker that joins the desk's SUPERHOT list is
posted to the operator's Super Signals channel, with its DMI direction.

Same bot token, same chat, same on/off switch as the Super Signals feed
(super_telegram.py) -- an operator who turned that on gets these too.

    🔥 SUPERHOT · 5m bars
    🟢 NVDA DMI UP · ADX 42.1 · +DI 35.2 / −DI 12.0 · 182.40

WHEN
Every five minutes through the desk's day (08:30-15:00 CT, weekdays), with
no page open. The list is the panel's: the HOT board's names on the desk's
default bar (tradier_hot_interval) whose period-9 DMI clears the SUPERHOT
gates. UP is a call-side reading (+DI over −DI), DOWN a put-side one.

ONCE
A ticker is posted the first time it appears on a side each day, recorded as
a TelegramPost ("superhot:<date>:<symbol>:<side>") exactly as a signal is, so
a restart does not post it again. A name that drops off and comes back the
same day stays quiet; one that flips from UP to DOWN is news and is posted.
The first pass of a day posts whatever is already on the list -- each of
those names is new that day.

The sweep reuses the panel's snapshot when it is fresh, and leaves its own
for the panel when it is not, so the two never scan the same bars twice.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

logger = logging.getLogger(__name__)

POLL_S = 300
CT = ZoneInfo("America/Chicago")
OPEN, CLOSE = (8, 30), (15, 0)
DIRECTION = {"call": ("🟢", "UP"), "put": ("🔻", "DOWN")}
HEAD = "🔥 SUPERHOT"


def desk_open(now: datetime) -> bool:
    ct = now.astimezone(CT)
    return ct.weekday() < 5 and OPEN <= (ct.hour, ct.minute) < CLOSE


def _fmt(v, nd=1) -> str:
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "—"


def post_id(day: str, row: dict) -> str:
    return f"superhot:{day}:{row['symbol']}:{row['sh_side']}"


def format_rows(rows: list[dict], interval: str) -> str:
    lines = [f"{HEAD} · {interval.replace('min', 'm')} bars"]
    for r in rows:
        icon, word = DIRECTION.get(r["sh_side"], ("•", str(r["sh_side"]).upper()))
        last = r.get("last")
        lines.append(
            f"{icon} {r['symbol']} DMI {word} · ADX {_fmt(r.get('sh_adx'))}"
            f" · +DI {_fmt(r.get('sh_plus_di'))} / −DI {_fmt(r.get('sh_minus_di'))}"
            + (f" · {float(last):,.2f}" if last not in (None, "") else ""))
    return "\n".join(lines)


def superhot_rows(rows: list[dict]) -> list[dict]:
    """The SUPERHOT list from the HOT board's rows, as the panel builds it."""
    out = [{**r, **r["sh"]} for r in rows if r.get("sh") and r["sh"].get("sh_side")]
    out.sort(key=lambda r: (r.get("adx") or 0), reverse=True)
    return out


def _credential(db, tenant_id: str, keyring):
    """The live Tradier credential, else the sandbox one -- the bars are the
    same either way. Returns (cred, live) or (None, None)."""
    from app.tenancy import repository as tenants

    for venue, live in (("tradier", True), ("tradier_sandbox", False)):
        try:
            return tenants.load_credential(db, tenant_id, venue, keyring), live
        except Exception:                               # noqa: BLE001
            continue
    return None, None


def _board(tenant_id: str, cred, live: bool, interval: str) -> list[dict]:
    """The HOT board's rows: the panel's snapshot when fresh, else a scan,
    left in the panel's cache for its next poll."""
    from app.api_v2.routers import desk
    from app.core.config import get_settings

    key = (tenant_id, bool(live), interval)
    with desk._HOT_LOCK:
        held = desk._HOT.get(key)
        if held and held.get("at") and time.time() - held["at"] < desk.HOT_TTL_S:
            return list(held["rows"])
    settings = get_settings()
    universe = [s.strip().upper() for s in settings.tradier_hot_universe.split(",")
                if s.strip()]
    rows = desk._scan(cred, universe, interval, sandbox=not live, gate=True)
    with desk._HOT_LOCK:
        current = desk._HOT.get(key)
        if not (current and current.get("refreshing")):
            desk._HOT[key] = {"rows": rows, "at": time.time(), "refreshing": False}
    return rows


def sweep_all_tenants(now: datetime | None = None) -> int:
    """One pass: post every feed-on operator's new SUPERHOT names."""
    from app.api_v2 import deps
    from app.core.config import get_settings
    from app.domains.notify import super_telegram as st
    from app.domains.notify.models import TelegramFeed, TelegramPost
    from app.platform import notify
    from app.platform.db.repository import TenantRepository
    from app.platform.db.session import session_scope
    from app.tenancy.models import Tenant

    now = now or datetime.now(timezone.utc)
    if not desk_open(now):
        return 0
    with session_scope() as db:
        tenant_ids = [tid for tid in db.scalars(select(Tenant.id)).all()
                      if (f := st._feed(db, tid)) is not None and f.enabled]
    if not tenant_ids:
        return 0
    keyring = deps.keyring()
    interval = get_settings().tradier_hot_interval
    day = now.astimezone(CT).date().isoformat()
    sent = 0
    for tenant_id in tenant_ids:
        try:
            with session_scope() as db:
                cred, live = _credential(db, tenant_id, keyring)
            if cred is None:
                continue
            listed = superhot_rows(_board(tenant_id, cred, live, interval))
            if not listed:
                continue
            with session_scope() as db:
                repo = TenantRepository(db, tenant_id)
                feed = db.scalar(repo.query(TelegramFeed))
                if feed is None or not feed.enabled or not feed.chat_id:
                    continue
                ids = {post_id(day, r): r for r in listed}
                posted = {p.signal_id for p in db.scalars(
                    repo.query(TelegramPost).where(TelegramPost.signal_id.in_(list(ids)))).all()}
                fresh = [r for pid, r in ids.items() if pid not in posted]
                if not fresh:
                    continue
                token = st._token(db, tenant_id, keyring)
                if not token:
                    feed.last_error = "no bot token saved"
                    continue
                try:
                    notify.send("telegram", text=format_rows(fresh, interval),
                                token=token, chat_id=feed.chat_id)
                except notify.NotifyError as exc:
                    feed.last_error = str(exc)[:255]
                    continue
                for r in fresh:
                    repo.add(TelegramPost(signal_id=post_id(day, r)[:255]))
                feed.posted = (feed.posted or 0) + len(fresh)
                feed.last_post_at = st._naive_utc(datetime.now(timezone.utc))
                feed.last_error = None
                sent += len(fresh)
        except Exception as exc:                        # noqa: BLE001
            logger.warning("superhot telegram for one operator: %s: %s",
                           type(exc).__name__, exc)
    return sent
