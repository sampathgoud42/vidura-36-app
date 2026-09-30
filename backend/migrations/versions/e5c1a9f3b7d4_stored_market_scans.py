"""stored market scans

Best Bets and BreakoutRadar keep their last scan per combination in tables
instead of only in memory: a sheet opens on the stored rows at once, stamped
with when they were scanned, and the day's first sign-in refreshes them all.

scan_run holds one row per combination -- (kind, combo) is unique -- and the
two row tables hold the results. A scan replaces its combination wholesale
(truncate and load), so nothing here is ever updated in place.

Three new tables and nothing else touched, so a downgrade is three drops.

Revision ID: e5c1a9f3b7d4
Revises: d4a7c2e9b815
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import sqlite

revision = 'e5c1a9f3b7d4'
down_revision = 'd4a7c2e9b815'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('scan_run',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('combo', sa.String(length=24), nullable=False),
    sa.Column('trade_date', sa.String(length=10), nullable=False),
    sa.Column('scanned_at', sa.DateTime(), nullable=False),
    sa.Column('took_s', sa.Float(), nullable=True),
    sa.Column('row_count', sa.Integer(), nullable=False),
    sa.Column('trigger', sa.String(length=16), nullable=False),
    sa.Column('meta', sqlite.JSON(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scan_run')),
    sa.UniqueConstraint('kind', 'combo', name='uq_scan_run_kind_combo')
    )
    op.create_table('scan_best_bets_row',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('venue', sa.String(length=8), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.Column('symbol', sa.String(length=16), nullable=False),
    sa.Column('setup', sa.String(length=1), nullable=True),
    sa.Column('available', sa.Boolean(), nullable=False),
    sa.Column('data', sqlite.JSON(), nullable=False),
    sa.Column('scanned_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scan_best_bets_row'))
    )
    with op.batch_alter_table('scan_best_bets_row', schema=None) as batch_op:
        batch_op.create_index('ix_scan_best_bets_row_venue_rank', ['venue', 'rank'], unique=False)

    op.create_table('scan_breakout_row',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('market', sa.String(length=8), nullable=False),
    sa.Column('timeframe', sa.String(length=4), nullable=False),
    sa.Column('section', sa.String(length=8), nullable=False),
    sa.Column('rank', sa.Integer(), nullable=False),
    sa.Column('ticker', sa.String(length=24), nullable=False),
    sa.Column('data', sqlite.JSON(), nullable=False),
    sa.Column('scanned_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_scan_breakout_row'))
    )
    with op.batch_alter_table('scan_breakout_row', schema=None) as batch_op:
        batch_op.create_index('ix_scan_breakout_row_combo',
                              ['market', 'timeframe', 'section', 'rank'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('scan_breakout_row', schema=None) as batch_op:
        batch_op.drop_index('ix_scan_breakout_row_combo')
    op.drop_table('scan_breakout_row')
    with op.batch_alter_table('scan_best_bets_row', schema=None) as batch_op:
        batch_op.drop_index('ix_scan_best_bets_row_venue_rank')
    op.drop_table('scan_best_bets_row')
    op.drop_table('scan_run')
