"""Commands typed into the operator's Super Signals channel.

    /hot        the HOT board on 5-minute bars, now -- while "post HOT
                boards" is ticked
    /superhot   the SUPERHOT list on 5-minute bars, now -- while "post
                SUPERHOT alerts" is ticked

The bot LONG-POLLS its updates (getUpdates with a timeout: Telegram holds
the request open until a message arrives or LONG_POLL_S passes; no webhook,
so nothing has to reach this machine from outside) and answers in the same
channel, in the same format as the scheduled posts. A command is answered
as it arrives, on one kept-alive connection -- polling every five seconds
with a fresh connection each time cost more CPU than anything else the API
did.

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

# The loop re-enters at once: the wait happens at Telegram, in the request.
POLL_S = 1
LONG_POLL_S = 20
STALE_S = 120
INTERVAL = "5min"
COMMAND = re.compile(r"^/(hot|superhot)(?:@\w+)?\s*$", re.IGNORECASE)

_offsets: dict[str, int] = {}               # token -> next update id to ask for


def _updates(token: str, offset: int | None, *, wait_s: int = 0) -> list[dict]:
    from app.domains.notify import super_telegram as st

    params = {"allowed_updates": '["channel_post","message"]', "timeout": wait_s}
    if offset is not None:
        params["offset"] = offset
    r = st._get(f"https://api.telegram.org/bot{token}/getUpdates", params,
                timeout=wait_s + 10)
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
            # Each command follows its own switch: /hot only while "post HOT
            # boards" is ticked, /superhot only while "post SUPERHOT alerts"
            # is. With both off the bot does not even listen.
            allowed = {c for c, on in (("hot", f and f.post_hot),
                                       ("superhot", f and f.post_superhot)) if on}
            if f is not None and f.chat_id and allowed:
                token = st._token(db, tid, keyring)
                if token:
                    feeds.append((tid, f.chat_id, token, allowed))
    if not feeds:
        # Nothing to listen for: wait as long as a poll would have, rather
        # than asking the database again every second.
        time.sleep(LONG_POLL_S)
        return 0
    answered = 0
    for tenant_id, chat_id, token, allowed in feeds:
        try:
            # One feed (the usual case) waits at Telegram; several take turns
            # with a short wait each, so one quiet channel cannot hold up the rest.
            updates = _updates(token, _offsets.get(token),
                               wait_s=LONG_POLL_S if len(feeds) == 1 else 2)
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
            if m.group(1).lower() not in allowed:
                continue            # that post type is switched off: no reply
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
