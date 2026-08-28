"""The session factory, and the write-lock helper the lease depends on.

One engine per process, built lazily so importing a model does not open a
database — the old build bound its engine at import time, which is why its
test conftest had to set an environment variable before any ``app.*`` import.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.platform.db.engine import make_engine

_engine: Engine | None = None
_factory: sessionmaker | None = None
_bound_url: str | None = None


def _url() -> str:
    from app.core.config import get_settings
    return get_settings().database_url


def engine() -> Engine:
    """The process engine, rebuilt if the configured URL changed.

    The rebuild-on-change is what lets a test point at its own database
    without the import-order dance the old conftest needed.
    """
    global _engine, _factory, _bound_url
    url = _url()
    if _engine is None or url != _bound_url:
        if _engine is not None:
            _engine.dispose()
        _engine = make_engine(url)
        _factory = sessionmaker(bind=_engine, autoflush=False,
                                expire_on_commit=False)
        _bound_url = url
    return _engine


def session_factory() -> sessionmaker:
    engine()
    assert _factory is not None
    return _factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """A transaction that commits on success and rolls back on anything else."""
    db = session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def write_lock(db: Session) -> Iterator[Session]:
    """Take SQLite's write lock for the whole block.

    ``BEGIN IMMEDIATE`` acquires the write lock at the START of the
    transaction rather than at the first write. Without it, two processes can
    both begin, both read "no lease exists", and only collide when the second
    tries to write — by which point both have already decided to place an
    order. This is the difference between the lease being a mutex and being a
    suggestion.

    A no-op on any other dialect, where the same guarantee comes from
    SELECT ... FOR UPDATE instead.
    """
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise


def reset_for_tests() -> None:
    """Drop the cached engine so the next call rebinds to the current URL."""
    global _engine, _factory, _bound_url
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _factory = None
    _bound_url = None
