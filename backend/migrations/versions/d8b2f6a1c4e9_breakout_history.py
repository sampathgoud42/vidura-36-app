"""breakout history: every BreakoutRadar breakout of the last 30 days

The stored scan is truncate-and-load, so a rescan used to forget every ticker
that no longer passes. scan_breakout_history keeps one row per market,
timeframe and ticker that passed in the last 30 days: when it first did, when
its latest breakout candle first showed (popped_at -- the table's order), how
many distinct breakouts it has had (hits), and its latest row.

One new table and nothing else touched, so a downgrade is one drop.

Revision ID: d8b2f6a1c4e9
Revises: c9f4e2a7b1d3
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import sqlite

revision = 'd8b2f6a1c4e9'
down_revision = 'c9f4e2a7b1d3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('scan_breakout_history',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('market', sa.String(length=8), nullable=False),
    sa.Column('timeframe', sa.String(length=4), nullable=False),
    sa.Column('ticker', sa.String(length=24), nullable=False),
    sa.Column('first_seen', sa.DateTime(), nullable=False),
    sa.Column('popped_at', sa.DateTime(), nullable=False),
    sa.Column('last_seen', sa.DateTime(), nullable=False),
    sa.Column('breakout_at', sa.String(length=40), nullable=True),
    sa.Column('hits', sa.Integer(), nullable=False),
    sa.Column('data', sqlite.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scan_breakout_history')),
    sa.UniqueConstraint('market', 'timeframe', 'ticker', name='one_history_per_ticker')
    )
    with op.batch_alter_table('scan_breakout_history', schema=None) as batch_op:
        batch_op.create_index('ix_scan_breakout_history_combo',
                              ['market', 'timeframe', 'popped_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('scan_breakout_history', schema=None) as batch_op:
        batch_op.drop_index('ix_scan_breakout_history_combo')
    op.drop_table('scan_breakout_history')
