"""Alembic environment.

Holds Alembic to the properties the brief wanted from Flyway: a clean
baseline, ordered versions, migrate-from-empty proven by a test, and adding a
world never editing an existing migration.

``render_as_batch`` is the SQLite-specific part. SQLite cannot ALTER most
things, so Alembic rebuilds the table instead — which only works when every
constraint has a name, which is why the naming convention is set on the
metadata itself rather than left to chance.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.platform.db.base import Base            # noqa: E402
from app.platform.db.engine import make_engine   # noqa: E402
from app.platform.db import registry             # noqa: E402

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import every model so the metadata is complete. One place does this, so a
# table cannot exist in the models and be missing from a migration.
registry.all_models()
target_metadata = Base.metadata


def _url() -> str:
    override = context.get_x_argument(as_dictionary=True).get("url")
    if override:
        return override
    from_ini = config.get_main_option("sqlalchemy.url")
    if from_ini:
        return from_ini
    from app.core.config import get_settings
    return get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection", None)
    if connectable is None:
        engine = make_engine(_url())
        with engine.connect() as connection:
            _run(connection)
        engine.dispose()
    else:
        _run(connectable)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
