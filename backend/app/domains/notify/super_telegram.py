"""New Super Signals, posted to an operator's Telegram chat.

The signal desk serves today's session -- every signal its agents have
raised, each with a stable id. Every POLL_S this reads it once and, for each
operator whose feed is on, posts the signals it has not posted before:

  * only signals timed AFTER the feed was switched on -- turning it on must
    not empty a session's backlog into the channel;
  * only today's session, and only the desk's live signals;
  * several at once go as one message (up to PER_MESSAGE), so a burst at a
    bar close is a handful of messages, inside Telegram's rate limits.

A signal is recorded as posted once Telegram has taken the message that
carried it, and never posted again. A message Telegram refuses leaves its
signals unposted and the reason on the feed, and they are tried again on the
next pass -- the reason says what to fix (the token, the chat, the bot's
rights in the channel).

The bot token is a credential (venue 'telegram') and goes out only in the
URL of the call to api.telegram.org: never in an answer, never in a log line.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select

logger = logging.getLogger(__name__)

POLL_S = 30
PER_MESSAGE = 8
SEND_GAP_S = 1.1          # Telegram: about one message a second per chat
KEEP_POSTS_DAYS = 14
VENUE = "telegram"
CT = ZoneInfo("America/Chicago")
ARROW = {"LONG": "🔺", "SHORT": "🔻"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _naive_utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


# ---- the message ------------------------------------------------------------
def _num(value) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{v:,.2f}" if abs(v) >= 10 else f"{v:.4f}"


def setup_text(signal: dict) -> str:
    """The setup as the panel writes it: "adx di cross + delta", "poc 250h
    [low]", "... ×2" when it has repeated."""
    text = str(signal.get("setup") or "").replace("_", " ").replace("+", " + ")
    if signal.get("grade"):
        text += f" [{signal['grade']}]"
    if int(signal.get("repeats") or 0) > 0:
        text += f" ×{int(signal['repeats']) + 1}"
    return text


def format_signal(signal: dict) -> str:
    direction = str(signal.get("direction") or "").upper()
    lines = [
        f"{ARROW.get(direction, '•')} {signal.get('ticker', '?')} {direction} · {signal.get('agent', '')}",
        setup_text(signal),
        f"{_num(signal.get('price'))} → {_num(signal.get('target'))} · stop {_num(signal.get('stop'))}"
        + (f" · {int(signal['horizon_min'])}m" if signal.get("horizon_min") else ""),
        f"{signal.get('time', '')} CT" + (f" · {signal['context']}" if signal.get("context") else ""),
    ]
    return "\n".join(line for line in lines if line.strip())


def format_batch(signals: list[dict]) -> str:
    from app.platform import notify

    head = "Super signals" if len(signals) > 1 else "Super signal"
    text = head + "\n\n" + "\n\n".join(format_signal(s) for s in signals)
    return text if len(text) <= notify.MAX_TEXT else text[:notify.MAX_TEXT - 1] + "…"


def _signal_at(date: str, signal: dict) -> datetime | None:
    """A signal's time as a moment: the session date and its CT clock time."""
    try:
        local = datetime.strptime(f"{date} {signal.get('time', '')}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    return _naive_utc(local.replace(tzinfo=CT))


# ---- the operator's settings -----------------------------------------------
def _token(db, tenant_id: str, keyring) -> str | None:
    from app.tenancy import repository as tenants

    try:
        return tenants.load_credential(db, tenant_id, VENUE, keyring).token or None
    except Exception:                                   # noqa: BLE001
        return None


def _feed(db, tenant_id: str):
    from app.domains.notify.models import TelegramFeed
    from app.platform.db.repository import TenantRepository

    return db.scalar(TenantRepository(db, tenant_id).query(TelegramFeed))


def _stamp(moment):
    return moment.replace(tzinfo=timezone.utc).isoformat() if moment else None


def get_state(db, tenant_id: str, keyring) -> dict:
    """The feed as the panel shows it. Whether a token is saved, never what."""
    feed = _feed(db, tenant_id)
    return {"token_saved": _token(db, tenant_id, keyring) is not None,
            "enabled": bool(feed and feed.enabled),
            "chat_id": feed.chat_id if feed else None,
            "chat_title": feed.chat_title if feed else None,
            "posted": feed.posted if feed else 0,
            "enabled_at": _stamp(feed.enabled_at) if feed else None,
            "last_post_at": _stamp(feed.last_post_at) if feed else None,
            "last_error": feed.last_error if feed else None}


def set_state(db, tenant, keyring, *, token: str | None = None,
              chat_id: str | None = None, chat_title: str | None = None,
              enabled: bool | None = None, actor: str = "") -> dict:
    """Save the token (sealed), the chat, and the switch -- whichever given.
    Switching on needs both a token and a chat."""
    from app.domains.notify.models import TelegramFeed
    from app.platform import notify
    from app.platform.db.repository import TenantRepository
    from app.tenancy import repository as tenants
    from app.tenancy.models import TenantCredential

    if token is not None:
        token = token.strip()
        if not notify.TELEGRAM_TOKEN.match(token):
            raise ValueError("that is not a Telegram bot token (digits, a colon, then the key)")
        row = db.scalar(select(TenantCredential).where(
            TenantCredential.tenant_id == tenant.id, TenantCredential.venue == VENUE,
            TenantCredential.label == "default", TenantCredential.revoked_at.is_(None)))
        if row is None:
            tenants.store_credential(db, tenant, venue=VENUE, label="default",
                                     secret={"token": token}, keyring=keyring, actor=actor)
        else:
            tenants.rotate_credential(db, row, secret={"token": token},
                                      keyring=keyring, actor=actor)
    if chat_id is not None and chat_id.strip() and not notify.TELEGRAM_CHAT.match(chat_id.strip()):
        raise ValueError("that is not a Telegram chat id (a number like -100..., or @channel)")

    feed = _feed(db, tenant.id)
    if feed is None:
        feed = TelegramFeed(enabled=False, posted=0)
        TenantRepository(db, tenant.id).add(feed)
    if chat_id is not None:
        if (chat_id.strip() or None) != feed.chat_id:
            feed.chat_title = None
        feed.chat_id = chat_id.strip() or None
    if chat_title is not None:
        feed.chat_title = chat_title.strip()[:128] or None
    if enabled is not None:
        if enabled and not (feed.chat_id and (token or _token(db, tenant.id, keyring))):
            raise ValueError("posting needs a saved bot token and a chat")
        if enabled and not feed.enabled:
            feed.enabled_at = _naive_utc(_now())
            feed.last_error = None
        feed.enabled = bool(enabled)
    db.commit()
    return get_state(db, tenant.id, keyring)


# ---- Telegram ---------------------------------------------------------------
def _get(url: str, params: dict):
    """The one outbound read. The seam tests substitute."""
    import requests

    return requests.get(url, params=params, timeout=10)


def chats(token: str) -> list[dict]:
    """The chats this bot has been added to or written in lately -- where to
    find a private channel's id, which an invite link does not give.

    Telegram keeps a bot's updates for a day; a channel shows up once the bot
    has been made an admin there, or once anything is posted in it after."""
    from app.platform import notify

    if not notify.TELEGRAM_TOKEN.match(token or ""):
        raise notify.NotifyError("that is not a Telegram bot token (digits, a colon, then the key)")
    try:
        response = _get(f"https://api.telegram.org/bot{token}/getUpdates",
                        {"allowed_updates": '["my_chat_member","channel_post","message"]'})
    except Exception:                                   # noqa: BLE001
        raise notify.DeliveryFailed("Telegram could not be reached") from None
    if response.status_code == 401:
        raise notify.DeliveryFailed("Telegram refused the token (HTTP 401) -- check it")
    if response.status_code == 409:
        raise notify.DeliveryFailed("this bot has a webhook set, so Telegram will not list its "
                                    "chats here -- enter the chat id by hand")
    if response.status_code >= 400:
        raise notify.DeliveryFailed(f"Telegram answered HTTP {response.status_code}")
    found: dict[str, dict] = {}
    for update in (response.json() or {}).get("result") or []:
        for key in ("my_chat_member", "channel_post", "edited_channel_post", "message"):
            chat = (update.get(key) or {}).get("chat")
            if not chat or chat.get("id") is None:
                continue
            found[str(chat["id"])] = {
                "id": str(chat["id"]), "type": chat.get("type") or "",
                "title": (chat.get("title") or chat.get("username")
                          or chat.get("first_name") or str(chat["id"]))}
    return sorted(found.values(), key=lambda c: (c["type"] != "channel", c["title"].lower()))


def send_test(db, tenant_id: str, keyring) -> dict:
    from app.platform import notify

    feed = _feed(db, tenant_id)
    token = _token(db, tenant_id, keyring)
    if not token or not (feed and feed.chat_id):
        raise notify.NotifyError("save a bot token and a chat first")
    return notify.send("telegram", token=token, chat_id=feed.chat_id,
                       text="✅ Vidura Super Signals: this chat will get new signals as "
                            "the desk raises them.")


# ---- the feed ---------------------------------------------------------------
def _session() -> dict | None:
    from app.services import super_signals as desk

    try:
        return desk.get_json("/api/session")
    except Exception as exc:                            # noqa: BLE001
        logger.info("super telegram: the signal desk did not answer (%s)",
                    type(exc).__name__)
        return None


def sweep_all_tenants(now: datetime | None = None, sleep=time.sleep) -> int:
    """One pass: post every operator's new signals. Returns how many."""
    from app.api_v2 import deps
    from app.domains.notify.models import TelegramFeed, TelegramPost
    from app.platform import notify
    from app.platform.db.repository import TenantRepository
    from app.platform.db.session import session_scope
    from app.tenancy.models import Tenant

    now = now or _now()
    with session_scope() as db:
        tenant_ids = [tid for tid in db.scalars(select(Tenant.id)).all()
                      if (f := _feed(db, tid)) is not None and f.enabled]
    if not tenant_ids:
        return 0
    session = _session()
    if not session or not session.get("is_today"):
        return 0
    date = str(session.get("date") or "")
    live = [s for s in session.get("signals") or []
            if s.get("id") and str(s.get("source") or "live") == "live"]
    if not live:
        return 0
    keyring = deps.keyring()
    sent = 0
    for tenant_id in tenant_ids:
        try:
            with session_scope() as db:
                repo = TenantRepository(db, tenant_id)
                feed = db.scalar(repo.query(TelegramFeed))
                if feed is None or not feed.enabled or not feed.chat_id:
                    continue
                since = feed.enabled_at or _naive_utc(now)
                ids = [s["id"] for s in live]
                posted = {row.signal_id for row in db.scalars(
                    repo.query(TelegramPost).where(TelegramPost.signal_id.in_(ids))).all()}
                fresh = [s for s in live if s["id"] not in posted
                         and (_signal_at(date, s) or since) >= since]
                if not fresh:
                    continue
                token = _token(db, tenant_id, keyring)
                if not token:
                    feed.last_error = "no bot token saved"
                    continue
                fresh.sort(key=lambda s: (s.get("time") or "", s["id"]))
                for start in range(0, len(fresh), PER_MESSAGE):
                    batch = fresh[start:start + PER_MESSAGE]
                    try:
                        notify.send("telegram", text=format_batch(batch),
                                    token=token, chat_id=feed.chat_id)
                    except notify.NotifyError as exc:
                        feed.last_error = str(exc)[:255]
                        break
                    for signal in batch:
                        repo.add(TelegramPost(signal_id=signal["id"][:255]))
                    feed.posted = (feed.posted or 0) + len(batch)
                    feed.last_post_at = _naive_utc(_now())
                    feed.last_error = None
                    sent += len(batch)
                    db.commit()
                    if start + PER_MESSAGE < len(fresh):
                        sleep(SEND_GAP_S)
                cutoff = _naive_utc(now) - timedelta(days=KEEP_POSTS_DAYS)
                for old in db.scalars(repo.query(TelegramPost).where(
                        TelegramPost.created_at < cutoff)).all():
                    db.delete(old)
        except Exception as exc:                        # noqa: BLE001
            logger.warning("super telegram for one operator: %s", type(exc).__name__)
    return sent
