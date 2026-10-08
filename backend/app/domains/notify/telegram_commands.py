"""Commands typed into the operator's Super Signals channels (vidura, super).

    /hot        the HOT board on 5-minute bars, now -- while that channel's
                "post HOT boards" is ticked
    /superhot   the SUPERHOT list on 5-minute bars, now -- while that
                channel's "post SUPERHOT alerts" is ticked
    /dmi        asks for a ticker; the next one typed in the channel (META)
                gets +DI, -DI and ADX on 5m, 15m and 30m bars, each with its
                arrow against the bar before, and the side (UP / DOWN). /dmi
                META answers at once. In any channel whose feed is on.

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
COMMAND = re.compile(r"^/(hot|superhot|dmi)(?:@\w+)?(?:\s+([A-Za-z][A-Za-z0-9.\-]{0,9}))?\s*$",
                     re.IGNORECASE)
TICKER = re.compile(r"^\$?([A-Za-z][A-Za-z0-9.\-]{0,9})$")
DMI_INTERVALS = ("5min", "15min", "30min")
DMI_ASK_S = 300                             # how long a /dmi waits for its ticker
_asked: dict[str, float] = {}               # chat id -> when /dmi asked for a ticker

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


def _arrow(now, before) -> str:
    if now is None or before is None or now == before:
        return "→"
    return "↑" if now > before else "↓"


def _dmi_line(bars: list[dict], label: str) -> str:
    from app.domains.notify import superhot_telegram as sh
    from app.domains.trading.market import indicators

    now, before = indicators.dmi(bars), indicators.dmi(bars[:-1])
    if not now:
        return f"{label} · not enough bars yet"
    before = before or {}
    p, m, adx = now.get("plus_di"), now.get("minus_di"), now.get("adx")
    side = "call" if (p or 0) >= (m or 0) else "put"
    icon, word = sh.DIRECTION[side]
    return (f"{label} {icon} {word} · +DI {sh._fmt(p)} {_arrow(p, before.get('plus_di'))}"
            f" · −DI {sh._fmt(m)} {_arrow(m, before.get('minus_di'))}"
            f" · ADX {sh._fmt(adx)} {_arrow(adx, before.get('adx'))}")


def dmi_answer(symbol: str, cred, live: bool) -> str:
    """One ticker's DMI on 5m, 15m and 30m bars -- the desk's own reading
    (indicators.dmi, period 14), with each number's arrow against the bar
    before it."""
    from app.api_v2.routers import desk
    from app.domains.notify import superhot_telegram as sh
    from app.domains.trading.market import indicators

    symbol = symbol.upper()
    lines, last = [], None
    for iv in DMI_INTERVALS:
        label = sh.BAR_LABEL.get(iv, iv)
        try:
            native, factor = indicators.source_interval(iv)
            bars = indicators.aggregate(
                desk.venue_mod.timesales(symbol, cred=cred, interval=native,
                                         sandbox=not live, start=indicators.start_date(iv)),
                factor)
        except Exception as exc:                        # noqa: BLE001
            logger.info("telegram /dmi %s %s: %s", symbol, iv, type(exc).__name__)
            lines.append(f"{label} · no bars")
            continue
        if last is None:
            last = next((float(b["close"]) for b in reversed(bars)
                         if b.get("close") not in (None, "")), None)
        lines.append(_dmi_line(bars, label))
    stamp = datetime.now(sh.CT).strftime("%H:%M")
    head = f"📊 {symbol} DMI · {stamp} CT" + (f" · {last:,.2f}" if last is not None else "")
    if all(line.endswith("no bars") for line in lines):
        return f"{head}\nNo bars for {symbol} -- is it a ticker the venue knows?"
    return "\n".join([head, *lines])


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
            # Each command follows its own channel's switch: /hot only where
            # "post HOT boards" is ticked, /superhot only where "post SUPERHOT
            # alerts" is. With every box off the bot does not even listen.
            chats = {}
            for f in st._feeds(db, tid):
                allowed = {c for c, on in (("hot", f.post_hot),
                                           ("superhot", f.post_superhot),
                                           ("dmi", f.enabled)) if on}
                if f.chat_id and allowed:
                    chats[f.chat_id] = allowed
            if chats:
                token = st._token(db, tid, keyring)
                if token:
                    feeds.append((tid, token, chats))
    if not feeds:
        # Nothing to listen for: wait as long as a poll would have, rather
        # than asking the database again every second.
        time.sleep(LONG_POLL_S)
        return 0
    answered = 0
    for tenant_id, token, chats in feeds:
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
            typed = (post.get("text") or "").strip()
            chat_id = next((c for c in chats if _same_chat(post.get("chat") or {}, c)), None)
            if chat_id is None or now - float(post.get("date") or 0) > STALE_S:
                continue
            allowed = chats[chat_id]
            m = COMMAND.match(typed)
            # The ticker a /dmi asked for: the next bare symbol in that chat.
            t = TICKER.match(typed) if not m and "dmi" in allowed else None
            if t and now - _asked.get(chat_id, 0) <= DMI_ASK_S:
                command, symbol = "dmi", t.group(1)
            elif m:
                command, symbol = m.group(1).lower(), m.group(2)
            else:
                continue
            if command not in allowed:
                continue            # that post type is switched off: no reply
            if command == "dmi":
                _asked.pop(chat_id, None)
            try:
                if command == "dmi" and not symbol:
                    _asked[chat_id] = now
                    notify.send("telegram", text="📊 DMI -- which ticker? Reply with a symbol, e.g. META",
                                token=token, chat_id=chat_id)
                    answered += 1
                    continue
                with session_scope() as db:
                    cred, live = sh._credential(db, tenant_id, keyring)
                if cred is None:
                    text = "No Tradier credential is saved, so there is nothing to scan with."
                elif command == "dmi":
                    text = dmi_answer(symbol, cred, live)
                else:
                    text = answer(command, tenant_id, cred, live)
                notify.send("telegram", text=text, token=token, chat_id=chat_id)
                answered += 1
            except Exception as exc:                    # noqa: BLE001
                logger.warning("telegram /%s: %s: %s", command, type(exc).__name__, exc)
    return answered
