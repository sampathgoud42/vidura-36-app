"""Send one message to Telegram or Discord for an operator, and store nothing.

The bot token, chat id and webhook live in the operator's own browser; each
alert carries them here and they are forgotten when the request ends. Relayed
rather than sent from the page because the desk talks to nothing but its own
API, and so an alert is one code path whichever world sends it.

Two rules make that safe to expose:

  * The destination is fixed. Telegram is always api.telegram.org; a Discord
    webhook must be a discord.com /api/webhooks/ URL. Anything else is refused
    before a socket opens, so this cannot be pointed at an internal address.
  * A secret never leaves in an answer or a log line. A Telegram token is part
    of its URL, and a requests exception prints the URL -- so failures are
    reported by channel and HTTP status only, never by the exception's text.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = re.compile(r"^\d{5,16}:[A-Za-z0-9_-]{30,64}$")
TELEGRAM_CHAT = re.compile(r"^(?:-?\d{1,20}|@[A-Za-z][A-Za-z0-9_]{4,31})$")
DISCORD_WEBHOOK = re.compile(
    r"^https://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/webhooks/\d{5,30}/[A-Za-z0-9_-]{20,100}$")
MAX_TEXT = 1900             # Discord's limit is 2000; Telegram's is 4096
TIMEOUT_S = 10


class NotifyError(ValueError):
    """A refusal whose message is safe to show: it never holds a secret.
    This one is the request's fault; `status` is what the API answers."""

    status = 422


class DeliveryFailed(NotifyError):
    """The request was fine; Telegram or Discord would not take it."""

    status = 502


def _post(url: str, body: dict):
    """The one outbound call. The seam tests substitute."""
    import requests

    return requests.post(url, json=body, timeout=TIMEOUT_S)


def send(channel: str, *, text: str, token: str | None = None, chat_id: str | None = None,
         webhook_url: str | None = None) -> dict:
    text = (text or "").strip()
    if not text:
        raise NotifyError("there is no message to send")
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT - 1] + "…"

    if channel == "telegram":
        if not TELEGRAM_TOKEN.match(token or ""):
            raise NotifyError("that is not a Telegram bot token (digits, a colon, then the key)")
        if not TELEGRAM_CHAT.match(chat_id or ""):
            raise NotifyError("that is not a Telegram chat id (a number, or @channel)")
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    elif channel == "discord":
        if not DISCORD_WEBHOOK.match(webhook_url or ""):
            raise NotifyError("that is not a Discord webhook URL "
                              "(https://discord.com/api/webhooks/...)")
        url = webhook_url
        body = {"content": text}
    else:
        raise NotifyError("channel must be telegram or discord")

    try:
        response = _post(url, body)
    except Exception:                                   # noqa: BLE001
        # Not the exception's text: for Telegram it contains the URL, and the
        # URL contains the token.
        logger.info("notify: %s could not be reached", channel)
        raise DeliveryFailed(f"{channel} could not be reached") from None
    if response.status_code >= 400:
        logger.info("notify: %s refused a message (HTTP %s)", channel, response.status_code)
        hints = {"telegram": {401: " -- check the bot token",
                              400: " -- check the chat id, and that the bot has been "
                                   "started or added to it",
                              403: " -- make the bot an admin of the chat, allowed "
                                   "to post"},
                 "discord": {401: " -- check the webhook", 404: " -- check the webhook"}}
        raise DeliveryFailed(f"{channel} refused the message (HTTP {response.status_code})"
                             f"{hints[channel].get(response.status_code, '')}")
    return {"sent": True, "channel": channel}
