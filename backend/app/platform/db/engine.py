"""Engine construction, with the pragmas the design depends on.

Three of these are load-bearing rather than tuning:

  journal_mode=WAL   readers do not block the writer, and the single-writer
                     guarantee is what makes the execution lease a real mutex
  foreign_keys=ON    off by default in SQLite; without it a tenant_id can
                     reference a tenant that does not exist
  busy_timeout       a writer that arrives during another write waits instead
                     of failing, which the lease relies on

They are set on EVERY connection, not once at startup: the pool opens new
connections over the life of the process, and a connection without these is a
connection where the guarantees quietly do not hold.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, event


def make_engine(url: str, *, echo: bool = False) -> Engine:
    is_sqlite = url.startswith("sqlite")
    # SQLAlchemy's default pool is QueuePool(size=5, overflow=10) -- fifteen
    # connections, sized for Postgres where each one is a server process. On
    # SQLite a connection is a file handle, and fifteen is far too few: the
    # desk polls a dozen panels at once and several endpoints hold their
    # session across a venue call, so the pool was exhausted and every later
    # request blocked the full 30s timeout before failing. The API stayed
    # "alive" and answered nothing.
    #
    # Raised rather than removed. NullPool would open a connection per request
    # and lose the PRAGMA setup that runs on connect; a bigger QueuePool keeps
    # that and still bounds the count.
    pool_kwargs = ({"pool_size": 20, "max_overflow": 40, "pool_timeout": 10}
                   if is_sqlite else {})
    engine = create_engine(
        url,
        echo=echo,
        # SQLite-only DBAPI flag: FastAPI serves a request on a worker
        # thread, which is not the thread the connection was made on.
        connect_args={"check_same_thread": False} if is_sqlite else {},
        pool_pre_ping=True,
        **pool_kwargs,
    )
    if is_sqlite:
        _install_sqlite_pragmas(engine)
    return engine


def _install_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _record):  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            # Durability that survives a process crash without paying for a
            # full fsync on every commit. WAL makes this the documented
            # trade: a power loss can lose the last commits, a crash cannot.
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()
