"""The 15-minute price monitor: which markets exist, and where their ticks go.

Two things live here and nowhere else: the CATALOGUE of Kalshi's fifteen-minute
markets, and the ``monitor`` schema those ticks are written to.

WHAT A "SCHEMA" IS ON EACH DATABASE
This project runs on SQLite by default and on Postgres in the cloud, and the
word means different things to them. Rather than pick one and be wrong on the
other, the separation is real on both:

    Postgres   a genuine ``CREATE SCHEMA monitor``, tables inside it
    SQLite     a separate database FILE, var/monitor.db, which SQL attaches
               under exactly that name:

                   ATTACH 'var/monitor.db' AS monitor;
                   SELECT * FROM monitor."btc-15" ORDER BY id DESC LIMIT 20;

The separate file is not a workaround, it is the better shape. This table
takes a row every fifteen seconds per market, forever -- roughly 5,760 rows
per market per day, and fourteen markets is eighty thousand rows a day. That
does not belong in the same file as the tenants, the credentials and the
ledger, where every backup and every migration would carry it.

TABLE AND ID NAMING
The tables are named for the markets exactly as asked -- ``btc-15``,
``eth-15`` -- which contains a dash and therefore must be quoted in SQL. That
is a real ergonomic cost and it is deliberate: these names are what an
operator asked for and what the ids repeat, and a table silently renamed to
``btc_15`` is a table nobody finds.

    id          btc-15-00001, btc-15-00002, ...   text, primary key
    ticker      KXBTC15M-26SEP101215-15           the market being quoted
    timestamp   2026-09-10 11:15:07               CST, sortable
    yes_price   1-99, integer cents               NULL when nothing is bid
    no_price    1-99, integer cents               NULL when nothing is bid

WHY A MISSING BID IS NULL AND NOT 1
A bid of zero means nobody is buying, which is a real and interesting state
for a price monitor. Clamping it into the 1-99 band would record a price that
nobody offered, and nothing downstream could tell it apart from a genuine 1c
bid. Quotes that DO exist are rounded and clamped into 1-99 as asked.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

CST = ZoneInfo("America/Chicago")
SCHEMA = "monitor"


@dataclass(frozen=True)
class Market:
    """One fifteen-minute market: what we call it, and what Kalshi calls it."""

    key: str        # our name, the table name and the id prefix: "btc-15"
    series: str     # Kalshi's series ticker: "KXBTC15M"
    label: str      # for the launch form: "BTC"
    category: str   # crypto | commodities


# Every fifteen-minute market Kalshi lists that is a single yes/no on a price.
#
# Read off the exchange's own /series listing rather than typed from memory,
# which is how the mistake below was found: there is NO KXOIL15M. Oil's
# fifteen-minute series is KXWTI15M, and the desk's oil15 trading bot has been
# pointed at a series with zero markets at any status.
#
# KXCRYPTOLEAD15M and KXCRYPTOCOMP15M are deliberately absent. They list
# several markets per event ("which coin leads"), so "the current market for
# this series" -- which everything below assumes -- has no single answer for
# them.
#
# A series with no open market right now is still listed: several of these
# trade only in their underlying's session, and a quiet market is not a
# missing one. The bot waits rather than failing.
MARKETS: tuple[Market, ...] = (
    Market("btc-15", "KXBTC15M", "BTC", "crypto"),
    Market("eth-15", "KXETH15M", "ETH", "crypto"),
    Market("sol-15", "KXSOL15M", "SOL", "crypto"),
    Market("xrp-15", "KXXRP15M", "XRP", "crypto"),
    Market("doge-15", "KXDOGE15M", "DOGE", "crypto"),
    Market("bnb-15", "KXBNB15M", "BNB", "crypto"),
    Market("zec-15", "KXZEC15M", "ZEC", "crypto"),
    Market("near-15", "KXNEAR15M", "NEAR", "crypto"),
    Market("hype-15", "KXHYPE15M", "HYPE", "crypto"),
    Market("gold-15", "KXGOLD15M", "Gold", "commodities"),
    Market("silver-15", "KXSILVER15M", "Silver", "commodities"),
    Market("oil-15", "KXWTI15M", "WTI Oil", "commodities"),
    Market("copper-15", "KXCOPPER15M", "Copper", "commodities"),
    Market("natgas-15", "KXNATGAS15M", "Nat Gas", "commodities"),
)

BY_KEY = {m.key: m for m in MARKETS}
KEYS = tuple(m.key for m in MARKETS)

# What a launch monitors when the operator picks nothing.
DEFAULT_KEYS = ("btc-15",)

# How often each market is quoted, in seconds.
POLL_S = 15


def resolve(keys) -> list[Market]:
    """The markets named, in catalogue order, ignoring names we do not have.

    Order comes from the catalogue rather than from the request so two
    launches of the same set behave identically, and an unknown name is
    dropped with a warning rather than failing the launch -- a typo in one of
    fourteen checkboxes should not stop the other thirteen.
    """
    wanted = {str(k).strip().lower() for k in (keys or []) if str(k).strip()}
    unknown = wanted - set(BY_KEY)
    if unknown:
        logger.warning("monitor: no such market(s): %s", ", ".join(sorted(unknown)))
    chosen = [m for m in MARKETS if m.key in wanted]
    return chosen or [BY_KEY[k] for k in DEFAULT_KEYS]


# ---------------------------------------------------------------------------
# Prices.

def to_cents(dollars) -> int | None:
    """A Kalshi dollar quote as integer cents in 1-99, or None if unquoted.

    Kalshi sends these as decimal STRINGS ("0.8900"), so this parses rather
    than assuming a float. Anything unparseable is None for the same reason a
    zero bid is: an unknown price must not be stored as a number somebody
    could trade on.
    """
    if dollars in (None, ""):
        return None
    try:
        cents = round(float(dollars) * 100)
    except (TypeError, ValueError):
        return None
    if cents <= 0:
        return None                      # nobody is bidding
    return max(1, min(99, int(cents)))


def now_cst() -> str:
    """The tick's time, on the clock every schedule on this desk is written in."""
    return datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# The store.

_engine = None
_lock = threading.Lock()
_ready: set[str] = set()


def _is_sqlite() -> bool:
    from app.core.config import get_settings
    return get_settings().is_sqlite


def engine():
    """The engine the monitor schema lives on. Built once, reused."""
    global _engine
    with _lock:
        if _engine is not None:
            return _engine
        from app.core.config import get_settings

        settings = get_settings()
        if settings.is_sqlite:
            path = settings.var_dir / "monitor.db"
            path.parent.mkdir(parents=True, exist_ok=True)
            # check_same_thread off: one writer task per market, each on its
            # own thread under asyncio's executor.
            _engine = create_engine(f"sqlite:///{path.as_posix()}",
                                    connect_args={"check_same_thread": False},
                                    future=True)
        else:
            _engine = create_engine(settings.database_url, future=True)
            with _engine.begin() as cx:
                cx.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
        return _engine


def _qualified(key: str) -> str:
    """How this table is written in SQL on this database.

    On SQLite the monitor IS its own file, so the table needs no prefix; on
    Postgres it is schema-qualified. Everything below goes through here so the
    difference is stated once.
    """
    return f'"{key}"' if _is_sqlite() else f'"{SCHEMA}"."{key}"'


def ensure_table(key: str) -> None:
    """Create this market's table if it is not there yet. Idempotent."""
    if key in _ready:
        return
    if key not in BY_KEY:
        raise KeyError(f"no such 15-minute market: {key!r}")
    table = _qualified(key)
    with engine().begin() as cx:
        cx.execute(text(f'''
            CREATE TABLE IF NOT EXISTS {table} (
                id         TEXT    NOT NULL PRIMARY KEY,
                ticker     TEXT    NOT NULL,
                "timestamp" TEXT   NOT NULL,
                yes_price  INTEGER,
                no_price   INTEGER
            )'''))
        # Reading this table means "the last N ticks", always.
        cx.execute(text(
            f'CREATE INDEX IF NOT EXISTS "ix_{key}_ts" ON {table} ("timestamp")'))
    _ready.add(key)


def next_id(cx, key: str) -> str:
    """The next id for this table: btc-15-00001, btc-15-00002, ...

    Derived from the row count inside the caller's transaction rather than
    held in memory, so a restarted bot continues the sequence instead of
    colliding with it. Five digits is a floor, not a ceiling -- row 100000
    simply gets a longer id rather than wrapping onto row 1.
    """
    n = cx.execute(text(f"SELECT COUNT(*) FROM {_qualified(key)}")).scalar() or 0
    return f"{key}-{n + 1:05d}"


def record(key: str, *, ticker: str, yes_price: int | None,
           no_price: int | None, at: str | None = None) -> str | None:
    """One tick. Returns the id written, or None if it could not be.

    Never raises. A monitor that dies because the disk hiccuped stops
    monitoring, which is worse than a gap in a chart -- the caller logs and
    carries on to the next fifteen seconds.
    """
    ensure_table(key)
    stamp = at or now_cst()
    table = _qualified(key)
    for attempt in range(3):
        try:
            with engine().begin() as cx:
                row_id = next_id(cx, key)
                cx.execute(text(
                    f'INSERT INTO {table} (id, ticker, "timestamp", '
                    f'yes_price, no_price) '
                    f'VALUES (:id, :ticker, :ts, :yes, :no)'),
                    {"id": row_id, "ticker": ticker, "ts": stamp,
                     "yes": yes_price, "no": no_price})
            return row_id
        except Exception as exc:                        # noqa: BLE001
            # A primary-key clash means somebody else inserted between the
            # count and the insert -- two monitors on one market. Recount and
            # try again rather than dropping the tick.
            if attempt == 2:
                logger.warning("monitor %s: tick not written: %s: %s",
                               key, type(exc).__name__, exc)
                return None
    return None


def latest(key: str, limit: int = 50) -> list[dict]:
    """The most recent ticks for one market, newest first."""
    if key not in BY_KEY:
        return []
    ensure_table(key)
    with engine().begin() as cx:
        rows = cx.execute(text(
            f'SELECT id, ticker, "timestamp", yes_price, no_price '
            f'FROM {_qualified(key)} ORDER BY id DESC LIMIT :n'),
            {"n": int(limit)}).mappings().all()
    return [dict(r) for r in rows]


def summary() -> list[dict]:
    """One line per market that has ever been recorded, for the desk.

    Markets with no table yet are reported with a zero count rather than
    omitted: "nothing has monitored ETH" and "ETH is not a market" are
    different answers.
    """
    out = []
    for market in MARKETS:
        row = {"key": market.key, "label": market.label,
               "series": market.series, "category": market.category,
               "rows": 0, "last_at": None, "ticker": None,
               "yes_price": None, "no_price": None}
        try:
            with engine().begin() as cx:
                exists = cx.execute(text(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n"
                    if _is_sqlite() else
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema=:s AND table_name=:n"),
                    ({"n": market.key} if _is_sqlite()
                     else {"s": SCHEMA, "n": market.key})).first()
                if exists:
                    table = _qualified(market.key)
                    row["rows"] = cx.execute(text(
                        f"SELECT COUNT(*) FROM {table}")).scalar() or 0
                    last = cx.execute(text(
                        f'SELECT ticker, "timestamp", yes_price, no_price '
                        f'FROM {table} ORDER BY id DESC LIMIT 1')).mappings().first()
                    if last:
                        row.update({"last_at": last["timestamp"],
                                    "ticker": last["ticker"],
                                    "yes_price": last["yes_price"],
                                    "no_price": last["no_price"]})
        except Exception as exc:                        # noqa: BLE001
            logger.info("monitor summary %s: %s", market.key,
                        type(exc).__name__)
        out.append(row)
    return out
