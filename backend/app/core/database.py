"""SQLAlchemy engine/session wiring for the local SQLite database."""

from __future__ import annotations

import logging
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _make_engine(url: str):
    is_sqlite = url.startswith("sqlite")
    engine = create_engine(
        url,
        # check_same_thread is a SQLite-only DBAPI flag
        connect_args={"check_same_thread": False} if is_sqlite else {},
        pool_pre_ping=True,
    )
    if not is_sqlite:
        return engine

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _record):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        # WAL keeps readers (dashboards) from blocking bot-driven writers.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    return engine


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables (idempotent). Called on app startup."""
    # Import models so they register on Base.metadata before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate(engine)


def _fix_india_signal_times(conn) -> int:
    """Re-derive india super_signals.logged_at from the wall-clock in ``raw``.

    Runs on every boot rather than once: it is a pure recompute, so rows that
    are already right land on the same value, and any row re-ingested by an
    older build gets corrected on the next start.
    """
    import json
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo

    from sqlalchemy import text

    ist = ZoneInfo("Asia/Kolkata")
    fixed = 0
    rows = conn.execute(
        text("SELECT id, raw, logged_at FROM super_signals WHERE category = 'india'")
    ).fetchall()
    for sid, raw, stored in rows:
        try:
            payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
            value = (payload.get("logged_at_cst") or "").strip()
        except (TypeError, ValueError):
            continue
        if not value:
            continue
        parsed = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                parsed = (
                    datetime.strptime(value, fmt)
                    .replace(tzinfo=ist)
                    .astimezone(timezone.utc)
                    .replace(tzinfo=None)
                )
                break
            except ValueError:
                continue
        if parsed is None:
            continue
        want = parsed.strftime("%Y-%m-%d %H:%M:%S.%f")
        if str(stored or "")[:19] == want[:19]:
            continue
        conn.execute(
            text("UPDATE super_signals SET logged_at = :ts WHERE id = :id"),
            {"ts": want, "id": sid},
        )
        fixed += 1
    if fixed:
        logging.getLogger("app.migrate").info(
            "corrected logged_at on %s india signal(s) (IST parsed as CST)", fixed
        )
    return fixed


def _backfill_btc15_modes(conn) -> int:
    """Classify unknown-mode btc15 trades from the run that produced them.

    A trade opened inside a run's [started_at, stopped_at] window was made by
    that run, and the run recorded whether it was paper or live. Only fills
        is_live IS NULL
    so a value the bot itself recorded is never overwritten, and rows with no
    matching run stay unknown rather than being guessed at.
    """
    from sqlalchemy import text

    rows = conn.execute(
        text(
            "SELECT id, user_id, opened_at FROM trades "
            "WHERE bot_key = 'btc15' AND is_live IS NULL AND opened_at IS NOT NULL"
        )
    ).fetchall()
    if not rows:
        return 0

    runs = conn.execute(
        text(
            "SELECT user_id, mode, started_at, stopped_at FROM bot_runs "
            "WHERE bot_key = 'btc15' AND started_at IS NOT NULL"
        )
    ).fetchall()
    if not runs:
        return 0

    fixed = 0
    for tid, user_id, opened in rows:
        for r_user, mode, started, stopped in runs:
            if r_user != user_id or not mode:
                continue
            # open-ended when the run is still going
            if str(opened) < str(started):
                continue
            if stopped and str(opened) > str(stopped):
                continue
            conn.execute(
                text("UPDATE trades SET is_live = :live, is_mock = :mock WHERE id = :id"),
                {"live": 1 if mode == "live" else 0,
                 "mock": 0 if mode == "live" else 1, "id": tid},
            )
            fixed += 1
            break
    if fixed:
        logging.getLogger("app.migrate").info(
            "classified %s btc15 trade(s) from their run's recorded mode", fixed
        )
    return fixed


def _relocate_user_roots(conn) -> int:
    """Point every user_root_folder at THIS project's customers folder.

    user_root_folder is stored as an absolute path, so a database that
    travels — a copy shipped to another machine, or just this folder moved
    or renamed — would otherwise keep reading credentials from wherever it
    was first set up. This migration is what makes the project relocatable.

    The rule is "inside this project wins", NOT "fix it only when it
    breaks". Checking whether the old path still resolves is not enough:
    ship a copy to a machine that happens to have the original layout — or
    simply run a copy alongside the original, which is what testing a
    deployment looks like — and the old path resolves perfectly while the
    copy quietly trades on another folder's tokens. So any stored root
    outside customers_root is corrected whenever a folder of the same name
    exists inside it, resolvable or not.

    Skipped entirely when allow_any_root is set, because then the operator
    has deliberately taken responsibility for pointing roots wherever they
    like and this would fight them.
    """
    from sqlalchemy import text

    from app.core import paths

    settings = get_settings()
    if settings.allow_any_root:
        return 0
    customers = settings.customers_root
    if not customers.is_dir():
        return 0
    try:
        customers_resolved = customers.resolve()
    except OSError:
        return 0

    log = logging.getLogger("app.migrate")
    fixed = 0
    rows = conn.execute(
        text("SELECT user_id, username, user_root_folder FROM users")
    ).fetchall()
    for user_id, username, root in rows:
        if not root:
            continue
        try:
            native = paths.normalize_root(root).resolve()
        except (ValueError, OSError):
            native = None
        if native is not None and (
            native == customers_resolved or customers_resolved in native.parents
        ):
            continue                          # already inside this project

        name = paths.canonical_str(root).rstrip("/").rsplit("/", 1)[-1]
        candidate = customers / name
        if not candidate.is_dir():
            log.warning(
                "user %s: credential folder %s is outside this project and no "
                "%s exists under %s - Tradier calls for this user will read "
                "that external folder, or fail",
                username, root, name, customers,
            )
            continue
        conn.execute(
            text("UPDATE users SET user_root_folder = :root WHERE user_id = :id"),
            {"root": paths.canonical_str(str(candidate)), "id": user_id},
        )
        log.info("user %s: credential folder repointed %s -> %s",
                 username, root, candidate)
        fixed += 1
    return fixed


def _migrate(bind) -> None:
    """Tiny additive migrations — create_all never alters existing tables.

    SQLite only: on Postgres, create_all already builds the current schema
    (there is no pre-existing legacy database to patch)."""
    from sqlalchemy import text

    if bind.dialect.name != "sqlite":
        return

    with bind.begin() as conn:
        cols = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(super_signals)")).fetchall()
        }
        if cols and "archived" not in cols:
            conn.execute(
                text(
                    "ALTER TABLE super_signals "
                    "ADD COLUMN archived BOOLEAN NOT NULL DEFAULT 0"
                )
            )

        # India signals were ingested with their IST wall-clock parsed as
        # Central, landing ~10.5h in the future and sorting above genuinely
        # newer US signals in the 24h A-book. Recompute logged_at from the
        # original string preserved in raw. Idempotent: rows already correct
        # recompute to the same value.
        scols = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(super_signals)")).fetchall()
        }
        if scols:
            _fix_india_signal_times(conn)

        _relocate_user_roots(conn)

        # btc15 rows written before the CSV carried a dry_run column have an
        # unknown mode, which hides them from BOTH the LIVE and PAPER ledgers.
        # The run that produced each one does know, so classify from bot_runs.
        if "is_live" in {
            row[1] for row in conn.execute(text("PRAGMA table_info(trades)")).fetchall()
        }:
            _backfill_btc15_modes(conn)

        # trades.is_live: real money or not, for the ledger's LIVE column.
        # NULLABLE on purpose - btc15 v2/v3/v4 write paper and live rows to the
        # same CSV with no distinguishing field, so their mode is genuinely
        # unknown. Backfill from is_mock everywhere it IS known, and leave
        # those rows NULL rather than mislabelling real trades as paper.
        tcols = {
            row[1] for row in conn.execute(text("PRAGMA table_info(trades)")).fetchall()
        }
        if tcols and "is_live" not in tcols:
            conn.execute(text("ALTER TABLE trades ADD COLUMN is_live BOOLEAN"))
            conn.execute(
                text(
                    "UPDATE trades SET is_live = NOT is_mock "
                    "WHERE NOT (bot_key = 'btc15' AND bot_version IN ('v2','v3','v4'))"
                )
            )
