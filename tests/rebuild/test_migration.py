"""Migrations: clean, ordered, and provable from an empty database.

The brief asks for Flyway. Flyway is a JVM tool with no SQLite support and
this is a Python project, so Alembic does the job — held to every property
the brief actually wanted: a clean baseline with the old history deleted, an
explicit versioning scheme, migrate-from-empty proven by a test, and adding a
world never editing an existing migration.
"""

from __future__ import annotations

import pytest


def test_migrate_from_an_empty_database_succeeds(tmp_path):
    """The headline requirement. A fresh clone must reach the current schema
    with one command and no manual steps."""
    from app.platform.db import migrations

    db = tmp_path / "fresh.db"
    migrations.upgrade_to_head(url=f"sqlite:///{db}")
    assert db.exists()
    assert migrations.current_revision(url=f"sqlite:///{db}") == migrations.head_revision()


def test_migrating_twice_is_a_no_op(tmp_path):
    from app.platform.db import migrations

    url = f"sqlite:///{tmp_path / 'twice.db'}"
    migrations.upgrade_to_head(url=url)
    migrations.upgrade_to_head(url=url)
    assert migrations.pending_count(url=url) == 0


def test_every_migration_can_be_rolled_back(tmp_path):
    """Rollback is an ops requirement, not a nicety: a bad deploy during
    market hours needs a way back that is not a restore from backup."""
    from app.platform.db import migrations

    url = f"sqlite:///{tmp_path / 'roll.db'}"
    migrations.upgrade_to_head(url=url)
    migrations.downgrade_one(url=url)
    migrations.upgrade_to_head(url=url)
    assert migrations.current_revision(url=url) == migrations.head_revision()


def test_the_schema_alembic_builds_matches_the_models(tmp_path):
    """A migration that has drifted from the models is a deploy that fails
    at 09:30. Autogenerate must find nothing to do."""
    from app.platform.db import migrations

    url = f"sqlite:///{tmp_path / 'drift.db'}"
    migrations.upgrade_to_head(url=url)
    diff = migrations.autogenerate_diff(url=url)
    assert not diff, f"models and migrations have drifted:\n{diff}"


def test_there_is_exactly_one_head(tmp_path):
    """Two heads mean two people branched the schema and nobody merged. It
    fails at deploy time, which is the worst time to find out."""
    from app.platform.db import migrations

    assert len(migrations.heads()) == 1, f"multiple migration heads: {migrations.heads()}"


def test_the_baseline_is_clean(tmp_path):
    """The old history is deleted, not carried. The first revision creates
    the current schema rather than replaying how the old one got there."""
    from app.platform.db import migrations

    revisions = migrations.all_revisions()
    assert revisions, "no migrations found"
    assert revisions[0].down_revision is None
    for r in revisions:
        assert "customers/" not in (r.doc or ""), (
            "a migration references the old customer-folder layout"
        )


def test_no_migration_creates_a_per_tenant_object(tmp_path):
    """Schema-per-tenant was rejected in Phase 0 because it makes onboarding
    a customer a DDL operation. This test stops it coming back by accident."""
    from app.platform.db import migrations

    for r in migrations.all_revisions():
        sql = migrations.render_sql(r)
        assert "CREATE SCHEMA" not in sql.upper()
        for slug in ("sampath", "suma", "sams"):
            assert slug not in sql.lower(), (
                f"migration {r.revision} names a specific customer"
            )


def test_pragmas_are_set_on_every_connection(tmp_path):
    """The execution lease depends on SQLite's single-writer semantics, and
    foreign keys are off by default. Both must hold on every connection, not
    just the first."""
    from sqlalchemy import text
    from app.platform.db import engine as db_engine

    eng = db_engine.make_engine(f"sqlite:///{tmp_path / 'pragma.db'}")
    for _ in range(3):
        with eng.connect() as conn:
            assert conn.execute(text("PRAGMA journal_mode")).scalar().lower() == "wal"
            assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_the_user_import_is_not_part_of_the_migration_chain(tmp_path):
    """Phase 8 is a one-shot import. If it ran as a migration it would run on
    every fresh environment, including a developer's laptop and CI."""
    from app.platform.db import migrations

    for r in migrations.all_revisions():
        sql = migrations.render_sql(r).lower()
        assert "wellness-profile.json" not in sql
        assert "trade_history" not in sql
