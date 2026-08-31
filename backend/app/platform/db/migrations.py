"""Programmatic access to the migration chain.

Exists so the tests, the health endpoint and the ops runbook all ask the same
questions the same way, rather than each shelling out to alembic and parsing
its output.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.platform.db.engine import make_engine

PROJECT_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"


def _config(url: str | None = None) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location",
                        str(PROJECT_ROOT / "backend" / "migrations"))
    if url:
        cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _resolved_url(url: str | None) -> str:
    if url:
        return url
    from app.core.config import get_settings
    return get_settings().database_url


def _scripts(url: str | None = None) -> ScriptDirectory:
    return ScriptDirectory.from_config(_config(url))


# ---- moving ---------------------------------------------------------------

def upgrade_to_head(url: str | None = None) -> None:
    command.upgrade(_config(_resolved_url(url)), "head")


def downgrade_one(url: str | None = None) -> None:
    command.downgrade(_config(_resolved_url(url)), "-1")


# ---- asking ---------------------------------------------------------------

def head_revision(url: str | None = None) -> str | None:
    return _scripts(url).get_current_head()


def heads(url: str | None = None) -> list[str]:
    """More than one means two people branched the schema and nobody merged.
    It fails at deploy time, which is the worst time to find out."""
    return list(_scripts(url).get_heads())


def current_revision(url: str | None = None) -> str | None:
    engine = make_engine(_resolved_url(url))
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()


def pending_count(url: str | None = None) -> int:
    """How many revisions this database has not applied.

    Used by the onboarding tests: registering a bot or creating a customer
    must never produce a pending schema change.
    """
    current = current_revision(url)
    scripts = _scripts(url)
    head = scripts.get_current_head()
    if current == head:
        return 0
    return len(list(scripts.iterate_revisions(head, current)))


@dataclass(frozen=True)
class RevisionInfo:
    revision: str
    down_revision: str | None
    doc: str | None
    path: str


def all_revisions(url: str | None = None) -> list[RevisionInfo]:
    """Oldest first, so ``[0]`` is the baseline."""
    scripts = _scripts(url)
    out = [
        RevisionInfo(revision=r.revision, down_revision=r.down_revision,
                     doc=r.doc, path=r.path)
        for r in scripts.walk_revisions()
    ]
    return list(reversed(out))


def render_sql(revision: RevisionInfo) -> str:
    """The revision's own source.

    The tests read this to assert that no migration names a customer or
    creates a per-tenant object — cheaper and more honest than executing it
    against a scratch database to find out.
    """
    return Path(revision.path).read_text(encoding="utf-8")


def autogenerate_diff(url: str | None = None) -> list:
    """What autogenerate would still write.

    Non-empty means the models and the migrations have drifted, which is a
    deploy that fails at 09:30 rather than in CI.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext as MC

    from app.platform.db import registry
    from app.platform.db.base import Base

    registry.all_models()
    engine = make_engine(_resolved_url(url))
    try:
        with engine.connect() as conn:
            ctx = MC.configure(conn, opts={"compare_type": True,
                                           "render_as_batch": True})
            return compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()
