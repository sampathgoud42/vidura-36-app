"""telegram feed: switches for the HOT and SUPERHOT posts

The channel now carries more than new Super Signals: the half-hourly HOT
boards and the SUPERHOT alerts. Each gets its own switch on telegram_feed,
beside ``enabled`` (which stays the Super Signals one, with the tracker).

Existing feeds that were posting keep posting everything -- both switches are
backfilled from ``enabled`` -- so turning this on changes nothing until the
operator unticks something.

Revision ID: a7d3c5e9f2b8
Revises: e2c7a9d4b6f1
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'a7d3c5e9f2b8'
down_revision = 'e2c7a9d4b6f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('telegram_feed', schema=None) as batch_op:
        batch_op.add_column(sa.Column('post_hot', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        batch_op.add_column(sa.Column('post_superhot', sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
    op.execute("UPDATE telegram_feed SET post_hot = enabled, post_superhot = enabled")


def downgrade() -> None:
    with op.batch_alter_table('telegram_feed', schema=None) as batch_op:
        batch_op.drop_column('post_superhot')
        batch_op.drop_column('post_hot')
