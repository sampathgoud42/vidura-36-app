"""Commands typed into the operator's Super Signals channel.

    /hot        the HOT board on 5-minute bars, now
    /superhot   the SUPERHOT list on 5-minute bars, now

The bot reads its updates every few seconds (getUpdates; no webhook, so
nothing has to reach this machine from outside) and answers in the same
channel, in the same format as the scheduled posts.

WHO CAN ASK
Only the feed's own chat is answered -- a channel, where only its admins can
post. A command from any other chat, a DM to the bot included, is ignored:
answering runs a scan through the operator's Tradier credential, and that is
not something a stranger who finds the bot should be able to start.

NOT TWICE
A command older than STALE_S is skipped, so the updates Telegram has kept
while the server was down are not all answered at once after a restart.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime

from sqlalchemy import select

logger = logging.getLogger(__name__)

POLL_S = 5
STALE_S = 120
INTERVAL = "5min"
COMMAND = re.compile(r"^/(hot|superhot)(?:@\w+)?\s*$", re.IGNORECASE)

_offsets: dict[str, int] = {}               # token -> next update id to ask for


def _updates(token: str, offset: int | None) -> list[dict]:
    from app.domains.notify import super_telegram as st

    params = {"allowed_updates": '["channel_post","message"]', "timeout": 0}
    if offset is not None:
        params["offset"] = offset
    r = st._get(f"https://api.telegram.org/bot{token}/getUpdates", params)
    if r.status_code >= 400:
        raise RuntimeError(f"getUpdates answered HTTP {r.status_code}")
    return (r.json() or {}).get("result") or []


def _same_chat(chat: dict, chat_id: str) -> bool:
    want = (chat_id or "").strip().lower()
    return want in {str(chat.get("id")).lower(),
                    f"@{(chat.get('username') or '').lower()}"}


def answer(command: str, tenant_id: str, cred, live: bool) -> str:
    from app.domains.notify import superhot_telegram as sh

    board = sh._board(tenant_id, cred, live, INTERVAL)
    stamp = datetime.now(sh.CT).strftime("%H:%M")
    if command == "hot":
        return sh.format_hot(board, INTERVAL, stamp)
    listed = sh.superhot_rows(board)
    if not listed:
        return f"{sh.HEAD} · 5m bars · {stamp} CT\nNothing clears the SUPERHOT gates right now."
    return sh.format_rows(listed, INTERVAL).replace(
        "5m bars", f"5m bars · {stamp} CT · {len(listed)} name{'s' if len(listed) != 1 else ''}", 1)


def sweep_all_tenants() -> int:
    """One pass: read each feed's bot updates, answer its channel's commands."""
    from app.api_v2 import deps
    from app.domains.notify import super_telegram as st
    from app.domains.notify import superhot_telegram as sh
    from app.platform import notify
    from app.platform.db.session import session_scope
    from app.tenancy.models import Tenant

    keyring = deps.keyring()
    with session_scope() as db:
        feeds = []
        for tid in db.scalars(select(Tenant.id)).all():
            f = st._feed(db, tid)
            if f is not None and f.enabled and f.chat_id:
                token = st._token(db, tid, keyring)
                if token:
                    feeds.append((tid, f.chat_id, token))
    answered = 0
    for tenant_id, chat_id, token in feeds:
        try:
            updates = _updates(token, _offsets.get(token))
        except Exception as exc:                        # noqa: BLE001
            logger.info("telegram commands: %s", exc)
            continue
        if not updates:
            continue
        _offsets[token] = max(u["update_id"] for u in updates) + 1
        now = time.time()
        for u in updates:
            post = u.get("channel_post") or u.get("message") or {}
            m = COMMAND.match((post.get("text") or "").strip())
            if not m or not _same_chat(post.get("chat") or {}, chat_id):
                continue
            if now - float(post.get("date") or 0) > STALE_S:
                continue
            try:
                with session_scope() as db:
                    cred, live = sh._credential(db, tenant_id, keyring)
                text = (answer(m.group(1).lower(), tenant_id, cred, live) if cred is not None
                        else "No Tradier credential is saved, so there is nothing to scan with.")
                notify.send("telegram", text=text, token=token, chat_id=chat_id)
                answered += 1
            except Exception as exc:                    # noqa: BLE001
                logger.warning("telegram /%s: %s: %s", m.group(1), type(exc).__name__, exc)
    return answered
