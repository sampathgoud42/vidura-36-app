"""combo15 auto result: WON / LOST for each placed auto-bot combo

One tenant-owned table, combo15_auto_result: one row per placed
combo15_auto_run, written once the combo market resolves, with Kalshi's
settlement cost, payout, fees and P&L.

Revision ID: a7d3e9b1c5f2
Revises: f4b8d2c6a1e7
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'a7d3e9b1c5f2'
down_revision = 'f4b8d2c6a1e7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('combo15_auto_result',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('run_id', sa.Integer(), nullable=False),
    sa.Column('slot', sa.String(length=16), nullable=False),
    sa.Column('combo_ticker', sa.String(length=64), nullable=False),
    sa.Column('result', sa.String(length=8), nullable=False),
    sa.Column('cost_usd', sa.Float(), nullable=True),
    sa.Column('payout_usd', sa.Float(), nullable=True),
    sa.Column('fees_usd', sa.Float(), nullable=True),
    sa.Column('pnl_usd', sa.Float(), nullable=True),
    sa.Column('settled_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("result in ('won','lost','void')", name=op.f('ck_combo15_auto_result_result_known')),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_combo15_auto_result_tenant_id_tenant'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['run_id'], ['combo15_auto_run.id'], name=op.f('fk_combo15_auto_result_run_id_combo15_auto_run'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_combo15_auto_result')),
    sa.UniqueConstraint('run_id', name='one_combo15_result_per_run')
    )
    with op.batch_alter_table('combo15_auto_result', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_combo15_auto_result_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_combo15_auto_result_tenant_slot', ['tenant_id', 'slot'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('combo15_auto_result', schema=None) as batch_op:
        batch_op.drop_index('ix_combo15_auto_result_tenant_slot')
        batch_op.drop_index(batch_op.f('ix_combo15_auto_result_tenant_id'))
    op.drop_table('combo15_auto_result')
