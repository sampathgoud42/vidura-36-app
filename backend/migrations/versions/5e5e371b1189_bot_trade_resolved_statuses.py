"""bot_trade resolved statuses

Revision ID: 5e5e371b1189
Revises: affed5ed5671
Created: 2026-08-28 16:22:51.933591
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '5e5e371b1189'
down_revision = 'affed5ed5671'
branch_labels = None
depends_on = None


# The table as it must END UP. Spelled out rather than reflected, because
# SQLite batch mode reflects the OLD check constraint straight back and the
# recreate becomes a no-op -- which looks like it worked.
# The same convention the application metadata uses. Inlined rather than
# imported: a migration that reads live application config is a migration that
# changes meaning when that config does. Without it, the constraint in this
# table is registered as "status_known" while batch mode looks for the
# expanded "ck_bot_trade_status_known", and the drop fails.
_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _bot_trade(check: str) -> sa.Table:
    return sa.Table(
        "bot_trade", sa.MetaData(naming_convention=_CONVENTION),
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("bot_key", sa.String(32), nullable=False),
        sa.Column("bot_version", sa.String(16)),
        sa.Column("run_id", sa.Integer),
        sa.Column("external_id", sa.String(256), nullable=False),
        sa.Column("ticker", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("opened_at", sa.DateTime),
        sa.Column("closed_at", sa.DateTime),
        sa.Column("contracts", sa.Integer),
        sa.Column("entry_price", sa.Float),
        sa.Column("exit_price", sa.Float),
        sa.Column("realized_pnl", sa.Float),
        sa.Column("is_live", sa.Boolean),
        sa.Column("reconciled_at", sa.DateTime),
        sa.Column("fee_checked_at", sa.DateTime),
        sa.Column("raw", sa.Text),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], ondelete="CASCADE",
            name="tenant_id_tenant"),
        sa.UniqueConstraint("tenant_id", "bot_key", "external_id",
                            name="tenant_bot_external"),
        sa.CheckConstraint(check, name="status_known"),
        # The indexes have to be here too. A batch recreate rebuilds the table
        # from THIS definition, so anything omitted is silently dropped -- the
        # first version of this migration lost both of them, and the only
        # symptom would have been the ledger getting slower.
        sa.Index("ix_bot_trade_tenant_id", "tenant_id"),
        sa.Index("ix_bot_trade_tenant_bot_opened",
                 "tenant_id", "bot_key", "opened_at"),
    )


NARROW = "status in ('open','closed','cancelled')"
RESOLVED = "status in ('open','closed','cancelled','won','lost','settled')"


def upgrade() -> None:
    """Widen bot_trade.status to the vocabulary the data actually uses.

    WRITTEN BY HAND. Alembic's autogenerate does not compare CHECK
    constraints: it produced an empty migration, advanced the revision, and
    reported zero drift, because it cannot see this change in either
    direction. Anything touching a CHECK has to be written out, and anything
    relying on autogenerate to catch a CHECK drift will not.

    The ledger holds 244 won, 118 lost and 5 settled. A Kalshi contract
    RESOLVES; it does not merely close. Collapsing those into "closed" would
    throw away the win/loss record, which is most of what a prediction-market
    ledger is for.
    """
    with op.batch_alter_table("bot_trade", copy_from=_bot_trade(NARROW),
                              recreate="always") as batch:
        # Short name: the metadata naming convention expands it. Passing the
        # expanded form gets it expanded a second time.
        batch.drop_constraint("status_known", type_="check")
        batch.create_check_constraint("status_known", RESOLVED)


def downgrade() -> None:
    """Back to the narrow set.

    Rows holding won/lost/settled would violate it, so they are mapped to
    'closed' first. That is lossy, and saying so is better than a downgrade
    that pretends to be clean.
    """
    op.execute("UPDATE bot_trade SET status='closed' "
               "WHERE status IN ('won','lost','settled')")
    with op.batch_alter_table("bot_trade", copy_from=_bot_trade(RESOLVED),
                              recreate="always") as batch:
        # Short name: the metadata naming convention expands it. Passing the
        # expanded form gets it expanded a second time.
        batch.drop_constraint("status_known", type_="check")
        batch.create_check_constraint("status_known", NARROW)
