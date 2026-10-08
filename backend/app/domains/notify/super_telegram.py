"""New Super Signals, posted to an operator's Telegram channels.

Two channels on the same bot, each a feed of its own (CHANNELS): "vidura"
posts only the signals that are both ⭐⭐⭐ and 👍, "super" posts every one.
Each has its own chat, its own half-hourly tracker of today's signals it
posts, and its own HOT / SUPERHOT switches (superhot_telegram.py). The vidura
channel also gets, on the hour, every 👍 best-pair signal fired today --
whatever its stars -- and how each has done (sweep_best_pairs).

The signal desk serves today's session -- every signal its agents have
raised, each with a stable id. Every POLL_S this reads it once and, for each
feed that is on, posts the signals it has not posted before:

  * only signals timed AFTER the feed was switched on -- turning it on must
    not empty a session's backlog into the channel;
  * only today's session, and only the desk's live signals;
  * several at once go as one message (up to PER_MESSAGE), so a burst at a
    bar close is a handful of messages, inside Telegram's rate limits.

Each signal's first line says its side and how its pair has done, at a glance:

  * 🟢 a LONG (a call), 🔻 a SHORT (a put);
  * 👍 when its ticker + signal pair is one of the daily report's best pairs --
    the panel's own mark, keyed the same way (type_key::ticker);
  * ⭐⭐⭐ when that same pair won more than 66% of its decided trades over the
    previous 7 sessions AND its signal type's edge over the 30 sessions
    before is above 59 (else two), else ⭐⭐ over the previous 3, else ⭐ over the
    previous one. A win is the target before the stop; timeouts sit outside
    the rate, as they do on the panel.

On the super channel the marks never hold a signal back: when the desk's
lists cannot be read, the signal goes without them. The vidura channel posts
only what the marks pick, so it waits for them.

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
SIDE = {"LONG": "🟢", "SHORT": "🔻"}       # a call green, a put red
THUMBS = "👍"
STAR = "⭐"
STAR_WIN_PCT = 66                          # a pair's win rate must be ABOVE this
STAR_WINDOWS = ((7, 3), (3, 2), (1, 1))    # (sessions back, stars): the longest that clears it
STAR3_EDGE = 59.0                          # three stars also need the signal type's 30-session edge ABOVE this
PAIRS_TTL_S = 600                          # the best pairs change once a day, with the report
CHANNELS = ("vidura", "super")
CHANNEL_WHAT = {"vidura": "only the ⭐⭐⭐👍 signals", "super": "every Super Signal"}
LEGEND = ("🟢 long (call) · 🔻 short (put)\n"
          "👍 one of the best ticker + signal pairs\n"
          "⭐ the pair won more than 66% of its trades last session, "
          "⭐⭐ over the last 3 sessions (or 7) -- ⭐ and ⭐⭐ only when the signal "
          "type, across all tickers, also won more than 66% over the same sessions; "
          "⭐⭐⭐ over the last 7 when its signal type's 30-session edge is above 59")


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


def format_signal(signal: dict, *, best: bool = False, stars: int = 0) -> str:
    direction = str(signal.get("direction") or "").upper()
    head = f"{SIDE.get(direction, '•')} {signal.get('ticker', '?')} {direction} · {signal.get('agent', '')}"
    if best:
        head += f" {THUMBS}"
    if stars:
        head += f" {STAR * stars}"
    lines = [
        head,
        setup_text(signal),
        f"{_num(signal.get('price'))} → {_num(signal.get('target'))} · stop {_num(signal.get('stop'))}"
        + (f" · {int(signal['horizon_min'])}m" if signal.get("horizon_min") else ""),
        f"{signal.get('time', '')} CT" + (f" · {signal['context']}" if signal.get("context") else ""),
    ]
    return "\n".join(line for line in lines if line.strip())


def format_batch(signals: list[dict], marks: Marks | None = None) -> str:
    from app.platform import notify

    marks = marks or Marks()
    head = "Super signals" if len(signals) > 1 else "Super signal"
    text = head + "\n\n" + "\n\n".join(
        format_signal(s, best=marks.best(s), stars=marks.stars(s)) for s in signals)
    return text if len(text) <= notify.MAX_TEXT else text[:notify.MAX_TEXT - 1] + "…"


# ---- the marks: 👍 and ⭐ ----------------------------------------------------
def type_key(signal: dict) -> str:
    """A signal type as the desk keys it: agent|setup|grade|direction."""
    return (f'{signal.get("agent") or ""}|{signal.get("setup") or ""}|{signal.get("grade") or ""}'
            f'|{signal.get("direction") or ""}')


def pair_key(signal: dict) -> str:
    """A ticker + signal pair as the desk's best pairs key it: type_key::ticker,
    where type_key is agent|setup|grade|direction."""
    return f'{type_key(signal)}::{signal.get("ticker") or ""}'


def records_of(sessions: list[list[dict]]) -> dict[int, dict[str, tuple[int, int]]]:
    """Each pair's (wins, losses) over the last 1, 3 and 7 of `sessions`, the
    newest first -- and each signal type's across all tickers, keyed by its
    type_key (which, unlike a pair key, has no "::"). A target is a win and a
    stop a loss; nothing else counts."""
    out: dict[int, dict[str, tuple[int, int]]] = {}
    for back, _ in STAR_WINDOWS:
        tally: dict[str, tuple[int, int]] = {}
        for signals in sessions[:back]:
            for s in signals:
                outcome = s.get("outcome")
                if outcome not in ("target", "stop"):
                    continue
                for key in (pair_key(s), type_key(s)):
                    wins, losses = tally.get(key, (0, 0))
                    tally[key] = (wins + 1, losses) if outcome == "target" else (wins, losses + 1)
        out[back] = tally
    return out


def _won(wins: int, losses: int) -> bool:
    return bool(wins + losses) and 100 * wins / (wins + losses) > STAR_WIN_PCT


class Marks:
    """The best pairs, each pair's (wins, losses) per STAR_WINDOWS, and each
    signal type's edge over the 30 sessions before."""

    def __init__(self, pairs=(), records: dict[int, dict[str, tuple[int, int]]] | None = None,
                 edges: dict[str, float] | None = None):
        self.pairs = frozenset(pairs)
        self.records = records or {}
        self.edges = edges or {}

    def best(self, signal: dict) -> bool:
        return pair_key(signal) in self.pairs

    def edge(self, signal: dict) -> float | None:
        return self.edges.get(type_key(signal))

    def stars(self, signal: dict) -> int:
        return self.star_record(signal)[0]

    def star_record(self, signal: dict) -> tuple[int, int, int, int]:
        """(stars, wins, losses, sessions back) for the window that earned
        them -- or (0, 0, 0, 0). The panel shows the record as the reason.
        Three stars only on a 30-session edge above STAR3_EDGE; else two. One
        or two only when the signal type, across all tickers, also won more
        than STAR_WIN_PCT over the same sessions; else the next window down."""
        key = pair_key(signal)
        for back, count in STAR_WINDOWS:
            wins, losses = self.records.get(back, {}).get(key, (0, 0))
            if not _won(wins, losses):
                continue
            if count == 3 and not (self.edge(signal) or 0) > STAR3_EDGE:
                count = 2
            if count < 3 and not _won(*self.type_record(signal, back)):
                continue
            return count, wins, losses, back
        return 0, 0, 0, 0

    def type_record(self, signal: dict, back: int) -> tuple[int, int]:
        """The signal type's (wins, losses) across all tickers, `back` sessions."""
        return self.records.get(back, {}).get(type_key(signal), (0, 0))


def mark_session(session: dict) -> dict:
    """The session with each signal's marks attached, as the panel shows
    them: ``stars`` and ``star_record`` {wins, losses, sessions}. The same
    marks the channel posts, for any session -- a past one is marked against
    the sessions before IT. Never fails the read: unmarked on any error."""
    signals = session.get("signals") or []
    if not signals:
        return session
    marks = marks_for(session)
    for s in signals:
        count, wins, losses, back = marks.star_record(s)
        s["stars"] = count
        type_wins, type_losses = marks.type_record(s, back) if count else (0, 0)
        s["star_record"] = ({"wins": wins, "losses": losses, "sessions": back,
                             "type_wins": type_wins, "type_losses": type_losses,
                             "edge": marks.edge(s)} if count else None)
    return session


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


def _channel(channel: str | None) -> str:
    channel = (channel or "vidura").strip().lower()
    if channel not in CHANNELS:
        raise ValueError(f"no such channel: {channel} (one of {', '.join(CHANNELS)})")
    return channel


def _feed(db, tenant_id: str, channel: str = "vidura"):
    from app.domains.notify.models import TelegramFeed
    from app.platform.db.repository import TenantRepository

    return db.scalar(TenantRepository(db, tenant_id).query(TelegramFeed).where(
        TelegramFeed.channel == channel))


def _feeds(db, tenant_id: str) -> list:
    """Every channel's feed this operator has, vidura first."""
    from app.domains.notify.models import TelegramFeed
    from app.platform.db.repository import TenantRepository

    rows = db.scalars(TenantRepository(db, tenant_id).query(TelegramFeed)).all()
    return sorted(rows, key=lambda f: CHANNELS.index(f.channel) if f.channel in CHANNELS else 99)


def post_key(channel: str, post: str) -> str:
    """What a channel records a post under. The vidura channel keeps the bare
    ids it has always used, so nothing it already posted goes out again."""
    return (post if channel == "vidura" else f"{channel}:{post}")[:255]


def wanted(channel: str, signal: dict, marks: Marks) -> bool:
    """Whether a channel posts this signal: super every one, vidura only the
    three-star best pairs."""
    return channel != "vidura" or (marks.stars(signal) == 3 and marks.best(signal))


def _stamp(moment):
    return moment.replace(tzinfo=timezone.utc).isoformat() if moment else None


def get_state(db, tenant_id: str, keyring, channel: str = "vidura") -> dict:
    """The feed as the panel shows it. Whether a token is saved, never what."""
    channel = _channel(channel)
    feed = _feed(db, tenant_id, channel)
    return {"channel": channel, "channels": list(CHANNELS), "what": CHANNEL_WHAT[channel],
            "token_saved": _token(db, tenant_id, keyring) is not None,
            "enabled": bool(feed and feed.enabled),
            "post_hot": bool(feed and feed.post_hot),
            "post_superhot": bool(feed and feed.post_superhot),
            "chat_id": feed.chat_id if feed else None,
            "chat_title": feed.chat_title if feed else None,
            "posted": feed.posted if feed else 0,
            "enabled_at": _stamp(feed.enabled_at) if feed else None,
            "last_post_at": _stamp(feed.last_post_at) if feed else None,
            "last_error": feed.last_error if feed else None}


def set_state(db, tenant, keyring, *, token: str | None = None,
              chat_id: str | None = None, chat_title: str | None = None,
              enabled: bool | None = None, post_hot: bool | None = None,
              post_superhot: bool | None = None, actor: str = "",
              channel: str = "vidura") -> dict:
    """Save the token (sealed, one for every channel), the channel's chat, and
    its switches -- whichever given. Switching on needs a token and a chat."""
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

    channel = _channel(channel)
    feed = _feed(db, tenant.id, channel)
    if feed is None:
        feed = TelegramFeed(channel=channel, enabled=False, posted=0)
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
    for name, value in (("post_hot", post_hot), ("post_superhot", post_superhot)):
        if value is None:
            continue
        if value and not (feed.chat_id and (token or _token(db, tenant.id, keyring))):
            raise ValueError("posting needs a saved bot token and a chat")
        setattr(feed, name, bool(value))
    db.commit()
    return get_state(db, tenant.id, keyring, channel)


# ---- Telegram ---------------------------------------------------------------
_SESSION = None
_SESSION_LOCK = __import__("threading").Lock()


def _session():
    """One kept-alive connection pool for every Telegram read. A fresh
    requests.get per call paid a full TLS handshake each time -- and on
    Windows that reloads the CA bundle -- which made the command poll the
    API's single largest CPU cost."""
    global _SESSION
    with _SESSION_LOCK:
        if _SESSION is None:
            import requests

            _SESSION = requests.Session()
        return _SESSION


def _get(url: str, params: dict, *, timeout: float = 10):
    """The one outbound read. The seam tests substitute."""
    return _session().get(url, params=params, timeout=timeout)


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


def send_test(db, tenant_id: str, keyring, channel: str = "vidura") -> dict:
    from app.platform import notify

    channel = _channel(channel)
    feed = _feed(db, tenant_id, channel)
    token = _token(db, tenant_id, keyring)
    if not token or not (feed and feed.chat_id):
        raise notify.NotifyError("save a bot token and a chat first")
    return notify.send("telegram", token=token, chat_id=feed.chat_id,
                       text=f"✅ Vidura Super Signals: this chat will get {CHANNEL_WHAT[channel]} "
                            "as the desk raises them, and a tracker of them every half hour."
                            "\n\n" + LEGEND)


# ---- the feed ---------------------------------------------------------------
def _desk(path: str, params: dict | None = None) -> dict:
    """The one read of the signal desk. The seam tests substitute."""
    from app.services import super_signals as desk

    return desk.get_json(path, params)


def _session() -> dict | None:
    try:
        return _desk("/api/session")
    except Exception as exc:                            # noqa: BLE001
        logger.info("super telegram: the signal desk did not answer (%s)",
                    type(exc).__name__)
        return None


_pairs_cache: list = [0.0, None]           # [monotonic time read, frozenset of pair keys]
_edges_cache: dict = {}                    # session date -> {type key: 30-session edge}
_records_cache: dict = {}                  # session date -> records_of(the sessions before it)
RECORDS_KEEP = 10


def _best_pairs(clock=time.monotonic) -> frozenset:
    """The report's best pairs, read again every PAIRS_TTL_S. Unreadable: the
    last list read (or none), and another try on the next pass."""
    read_at, pairs = _pairs_cache
    if pairs is not None and clock() - read_at < PAIRS_TTL_S:
        return pairs
    try:
        listed = _desk("/api/best-pairs").get("pairs") or []
    except Exception as exc:                            # noqa: BLE001
        logger.info("super telegram: the best pairs did not answer (%s)", type(exc).__name__)
        return pairs or frozenset()
    pairs = frozenset(f'{p["type_key"]}::{p.get("ticker") or ""}' for p in listed if p.get("type_key"))
    _pairs_cache[:] = [clock(), pairs]
    return pairs


def _records(session: dict) -> dict[int, dict[str, tuple[int, int]]]:
    """The pairs' records over the sessions before `session`, following the
    desk's previous-session links. Read once a day: those sessions are settled."""
    day = str(session.get("date") or "")
    if day in _records_cache:
        return _records_cache[day]
    deepest = max(back for back, _ in STAR_WINDOWS)
    chain: list[list[dict]] = []
    prev = (session.get("previous") or {}).get("date")
    try:
        while prev and len(chain) < deepest:
            past = _desk("/api/session", {"date": prev})
            chain.append(past.get("signals") or [])
            prev = (past.get("previous") or {}).get("date")
    except Exception as exc:                            # noqa: BLE001
        logger.info("super telegram: a past session did not answer (%s)", type(exc).__name__)
        return {}
    # A few days kept, not one: the panel reads past sessions while the feed
    # keeps reading today, and one slot would have them evict each other.
    while len(_records_cache) >= RECORDS_KEEP:
        _records_cache.pop(next(iter(_records_cache)))
    _records_cache[day] = records_of(chain)
    return _records_cache[day]


def _type_edges(session: dict) -> dict[str, float]:
    """Each signal type's edge over the 30 sessions before `session`, read
    once a day: those sessions are settled. Unreadable: none, and so no
    three stars, and another try on the next pass."""
    day = str(session.get("date") or "")
    if day in _edges_cache:
        return _edges_cache[day]
    try:
        edges = _desk("/api/type-edges", {"date": day} if day else None).get("edges") or {}
    except Exception as exc:                            # noqa: BLE001
        logger.info("super telegram: the type edges did not answer (%s)", type(exc).__name__)
        return {}
    while len(_edges_cache) >= RECORDS_KEEP:
        _edges_cache.pop(next(iter(_edges_cache)))
    _edges_cache[day] = {k: float(v) for k, v in edges.items() if v is not None}
    return _edges_cache[day]


def marks_for(session: dict) -> Marks:
    """Never holds a signal back: anything amiss, and it goes without marks."""
    try:
        return Marks(_best_pairs(), _records(session), _type_edges(session))
    except Exception as exc:                            # noqa: BLE001
        logger.warning("super telegram: no marks this pass (%s)", type(exc).__name__)
        return Marks()


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
        targets = [(tid, f.channel) for tid in db.scalars(select(Tenant.id)).all()
                   for f in _feeds(db, tid) if f.enabled]
    if not targets:
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
    marks = None                               # read once a pass, and only with something to post
    for tenant_id, channel in targets:
        try:
            with session_scope() as db:
                repo = TenantRepository(db, tenant_id)
                feed = _feed(db, tenant_id, channel)
                if feed is None or not feed.enabled or not feed.chat_id:
                    continue
                since = feed.enabled_at or _naive_utc(now)
                ids = [post_key(channel, s["id"]) for s in live]
                posted = {row.signal_id for row in db.scalars(
                    repo.query(TelegramPost).where(TelegramPost.signal_id.in_(ids))).all()}
                fresh = [s for s in live if post_key(channel, s["id"]) not in posted
                         and (_signal_at(date, s) or since) >= since]
                if fresh and channel == "vidura":
                    if marks is None:
                        marks = marks_for(session)
                    fresh = [s for s in fresh if wanted(channel, s, marks)]
                if not fresh:
                    continue
                token = _token(db, tenant_id, keyring)
                if not token:
                    feed.last_error = "no bot token saved"
                    continue
                fresh.sort(key=lambda s: (s.get("time") or "", s["id"]))
                if marks is None:
                    marks = marks_for(session)
                for start in range(0, len(fresh), PER_MESSAGE):
                    batch = fresh[start:start + PER_MESSAGE]
                    try:
                        notify.send("telegram", text=format_batch(batch, marks),
                                    token=token, chat_id=feed.chat_id)
                    except notify.NotifyError as exc:
                        feed.last_error = str(exc)[:255]
                        break
                    for signal in batch:
                        repo.add(TelegramPost(signal_id=post_key(channel, signal["id"])))
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
            logger.warning("super telegram for one operator's %s channel: %s",
                           channel, type(exc).__name__)
    return sent


# ---- the tracker: today's signals, every half hour -------------------------
# Each channel re-posts the signals it posts each half hour (the HOT slots,
# 09:00-15:00 CT) with where each one stands now, newest first -- the vidura
# channel its ⭐⭐⭐👍 signals, the super channel every one of today's:
#
#   ⭐⭐⭐👍 TRACKER · 12:30 CT · 4 signals · 1 TP · 1 SL · 0 TIMEOUT · 2 OPEN
#   🟢 GOOGL LONG · levels · 12:15 · 345.86 → 347.24 / 344.48 · 🟡 OPEN
#
# One TelegramPost per channel and slot (post_key of "tracker:<date>:<HH:MM>"),
# as the HOT posts. A long list goes as up to TRACK_PAGES messages. A channel
# with nothing of its own today yet gets no tracker at all -- not an empty one.
TRACK_STATUS = {"open": "🟡 OPEN", "target": "✅ TP-hit", "stop": "❌ SL-hit",
                "timeout": "⏱️ TIMEOUT"}
TRACK_HEAD = f"{STAR * 3}{THUMBS} TRACKER"
TRACK_HEADS = {"vidura": TRACK_HEAD, "super": "📋 SUPER SIGNALS TRACKER"}
TRACK_EMPTY = {"vidura": "No signal today is both three-star and a best pair yet.",
               "super": "No signal yet today."}
TRACK_PAGES = 4


def tracked(session: dict, marks: Marks, channel: str = "vidura") -> list[dict]:
    """Today's live signals the channel posts, newest first."""
    out = [s for s in session.get("signals") or []
           if str(s.get("source") or "live") == "live" and wanted(channel, s, marks)]
    out.sort(key=lambda s: (s.get("time") or "", s.get("id") or ""), reverse=True)
    return out


def _track_line(s: dict) -> str:
    direction = str(s.get("direction") or "").upper()
    status = TRACK_STATUS.get(s.get("outcome"), str(s.get("outcome") or "?").upper())
    if s.get("outcome") != "open" and s.get("exit_time"):
        status += f" {s['exit_time']}"
    if s.get("r") is not None:
        status += f" ({float(s['r']):+.2f}R)"
    # The setup too: several setups often fire on one bar, and without it
    # their lines read as the same signal posted twice.
    return (f"{SIDE.get(direction, '•')} {s.get('ticker', '?')} {direction} · "
            f"{s.get('agent', '')} {setup_text(s)} · {s.get('time', '')} · {_num(s.get('price'))} → "
            f"{_num(s.get('target'))} / {_num(s.get('stop'))} · {status}")


def tracker_pages(signals: list[dict], slot: str, channel: str = "vidura",
                  pages: int = TRACK_PAGES) -> list[str]:
    """The tracker as messages: the head on the first, as many lines as fit
    on each, at most `pages` of them, the last saying how many did not fit."""
    from app.platform import notify

    count = {k: sum(1 for s in signals if s.get("outcome") == k) for k in TRACK_STATUS}
    head = (f"{TRACK_HEADS.get(channel, TRACK_HEAD)} · {slot} CT · "
            f"{len(signals)} signal{'s' if len(signals) != 1 else ''}"
            f" · {count['target']} TP · {count['stop']} SL · {count['timeout']} TIMEOUT"
            f" · {count['open']} OPEN")
    if not signals:
        return [head + "\n" + TRACK_EMPTY.get(channel, TRACK_EMPTY["super"])]
    lines = [_track_line(s) for s in signals]
    out, text = [], head
    for i, line in enumerate(lines):
        more = f"\n… and {len(lines) - i} more"
        last = len(out) == pages - 1
        if len(text) + 1 + len(line) + (len(more) if last else 0) > notify.MAX_TEXT:
            if last:
                out.append(text + more)
                return out
            out.append(text)
            text = line
            continue
        text += "\n" + line
    out.append(text)
    return out


def format_tracker(signals: list[dict], slot: str) -> str:
    """The vidura channel's tracker, in one message."""
    return tracker_pages(signals, slot, "vidura", pages=1)[0]


def sweep_tracker(now: datetime | None = None) -> int:
    """Post the tracker for the half-hour slot due now, once per channel."""
    from app.api_v2 import deps
    from app.domains.notify import superhot_telegram as sh
    from app.domains.notify.models import TelegramPost
    from app.platform import notify
    from app.platform.db.repository import TenantRepository
    from app.platform.db.session import session_scope
    from app.tenancy.models import Tenant

    now = now or _now()
    slot = sh.hot_slot(now)
    if slot is None:
        return 0
    day = now.astimezone(CT).date().isoformat()
    post = f"tracker:{day}:{slot}"
    with session_scope() as db:
        due = []
        for tid in db.scalars(select(Tenant.id)).all():
            for f in _feeds(db, tid):
                if not f.enabled or not f.chat_id:
                    continue
                if db.scalar(TenantRepository(db, tid).query(TelegramPost).where(
                        TelegramPost.signal_id == post_key(f.channel, post))) is None:
                    due.append((tid, f.channel))
    if not due:
        return 0
    session = _session()
    if not session or not session.get("is_today"):
        return 0
    marks = marks_for(session)
    texts = {}
    for channel in {c for _, c in due}:
        signals = tracked(session, marks, channel)
        if signals:
            texts[channel] = tracker_pages(signals, slot, channel)
    keyring = deps.keyring()
    sent = 0
    for tenant_id, channel in due:
        if channel not in texts:
            continue
        try:
            with session_scope() as db:
                repo = TenantRepository(db, tenant_id)
                feed = _feed(db, tenant_id, channel)
                token = _token(db, tenant_id, keyring)
                if feed is None or not token:
                    continue
                try:
                    for i, text in enumerate(texts[channel]):
                        if i:
                            time.sleep(SEND_GAP_S)
                        notify.send("telegram", text=text, token=token, chat_id=feed.chat_id)
                except notify.NotifyError as exc:
                    feed.last_error = str(exc)[:255]
                    continue
                repo.add(TelegramPost(signal_id=post_key(channel, post)))
                feed.posted = (feed.posted or 0) + 1
                feed.last_post_at = _naive_utc(_now())
                feed.last_error = None
                sent += 1
        except Exception as exc:                        # noqa: BLE001
            logger.warning("super telegram tracker for one operator's %s channel: %s",
                           channel, type(exc).__name__)
    return sent


# ---- the best pairs, on the hour: vidura's other report ---------------------
# Every best-pair (👍) signal fired today, whatever its stars, and where each
# stands -- posted to the vidura channel at the top of each hour, 09:00-15:00
# CT, with the day's tally and net R:
#
#   👍 BEST PAIRS TODAY · 11:00 CT · 6 signals · 2 TP · 1 SL · 0 TIMEOUT · 3 OPEN · +1.00R
#   🟢 TSLA LONG · flow · 10:40 · 241.10 → 243.00 / 240.20 · 🟡 OPEN ⭐⭐
#
# One TelegramPost per hour ("bestpairs:<date>:<HH:00>"); none while no best
# pair has fired today.
BEST_HEAD = f"{THUMBS} BEST PAIRS TODAY"


def best_today(session: dict, marks: Marks) -> list[dict]:
    """Today's live signals on a best pair, newest first."""
    out = [s for s in session.get("signals") or []
           if str(s.get("source") or "live") == "live" and marks.best(s)]
    out.sort(key=lambda s: (s.get("time") or "", s.get("id") or ""), reverse=True)
    return out


def best_pages(signals: list[dict], slot: str, marks: Marks) -> list[str]:
    from app.platform import notify

    count = {k: sum(1 for s in signals if s.get("outcome") == k) for k in TRACK_STATUS}
    net = sum(float(s["r"]) for s in signals
              if s.get("r") is not None and s.get("outcome") in ("target", "stop", "timeout"))
    head = (f"{BEST_HEAD} · {slot} CT · {len(signals)} signal{'s' if len(signals) != 1 else ''}"
            f" · {count['target']} TP · {count['stop']} SL · {count['timeout']} TIMEOUT"
            f" · {count['open']} OPEN · {net:+.2f}R")
    if not signals:
        return [head + "\nNo best-pair signal has fired today yet."]
    lines = [_track_line(s) + (f" {STAR * n}" if (n := marks.stars(s)) else "") for s in signals]
    out, text = [], head
    for i, line in enumerate(lines):
        last = len(out) == TRACK_PAGES - 1
        more = f"\n… and {len(lines) - i} more"
        if len(text) + 1 + len(line) + (len(more) if last else 0) > notify.MAX_TEXT:
            if last:
                out.append(text + more)
                return out
            out.append(text)
            text = line
            continue
        text += "\n" + line
    out.append(text)
    return out


def sweep_best_pairs(now: datetime | None = None) -> int:
    """Post the hour's best-pairs report to each vidura channel that is on."""
    from app.api_v2 import deps
    from app.domains.notify import superhot_telegram as sh
    from app.domains.notify.models import TelegramPost
    from app.platform import notify
    from app.platform.db.repository import TenantRepository
    from app.platform.db.session import session_scope
    from app.tenancy.models import Tenant

    now = now or _now()
    slot = sh.hot_slot(now)
    if slot is None or not slot.endswith(":00"):
        return 0
    day = now.astimezone(CT).date().isoformat()
    post = post_key("vidura", f"bestpairs:{day}:{slot}")
    with session_scope() as db:
        due = [tid for tid in db.scalars(select(Tenant.id)).all()
               if (f := _feed(db, tid, "vidura")) is not None and f.enabled and f.chat_id
               and db.scalar(TenantRepository(db, tid).query(TelegramPost).where(
                   TelegramPost.signal_id == post)) is None]
    if not due:
        return 0
    session = _session()
    if not session or not session.get("is_today"):
        return 0
    marks = marks_for(session)
    picked = best_today(session, marks)
    if not picked:
        return 0
    texts = best_pages(picked, slot, marks)
    keyring = deps.keyring()
    sent = 0
    for tenant_id in due:
        try:
            with session_scope() as db:
                repo = TenantRepository(db, tenant_id)
                feed = _feed(db, tenant_id, "vidura")
                token = _token(db, tenant_id, keyring)
                if feed is None or not token:
                    continue
                try:
                    for i, text in enumerate(texts):
                        if i:
                            time.sleep(SEND_GAP_S)
                        notify.send("telegram", text=text, token=token, chat_id=feed.chat_id)
                except notify.NotifyError as exc:
                    feed.last_error = str(exc)[:255]
                    continue
                repo.add(TelegramPost(signal_id=post))
                feed.posted = (feed.posted or 0) + 1
                feed.last_post_at = _naive_utc(_now())
                feed.last_error = None
                sent += 1
        except Exception as exc:                        # noqa: BLE001
            logger.warning("super telegram best pairs for one operator: %s", type(exc).__name__)
    return sent
