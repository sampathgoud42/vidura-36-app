"""telegram feed: one row per channel

An operator now posts to two channels on the same bot: "vidura" (only the
⭐⭐⭐👍 signals) and "super" (every Super Signal). Each is a telegram_feed
row of its own -- its chat, its switches, its tracker -- keyed by ``channel``.

The existing feed becomes the "vidura" channel; its posted signals keep
their ids, so nothing already posted there is posted again.

Revision ID: c9f4e2a7b1d3
Revises: b3e8d1f4a6c2
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'c9f4e2a7b1d3'
down_revision = 'b3e8d1f4a6c2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('telegram_feed', schema=None) as batch_op:
        batch_op.add_column(sa.Column('channel', sa.String(length=16), nullable=False,
                                      server_default='vidura'))
        batch_op.drop_constraint('one_feed_per_tenant', type_='unique')
        batch_op.create_unique_constraint('one_feed_per_channel', ['tenant_id', 'channel'])


def downgrade() -> None:
    op.execute("DELETE FROM telegram_feed WHERE channel <> 'vidura'")
    with op.batch_alter_table('telegram_feed', schema=None) as batch_op:
        batch_op.drop_constraint('one_feed_per_channel', type_='unique')
        batch_op.create_unique_constraint('one_feed_per_tenant', ['tenant_id'])
        batch_op.drop_column('channel')
