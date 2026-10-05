"""position rollover: what was held over the close

Positions bought on a 7+ day expiry (Near Expiry off) are opened marked to
carry, and at the close each one still open -- neither its target nor its
stop hit -- is recorded here: one row per position per session, with the
closing bid, the unrealised P&L and whether both exits were still resting.
A new tenant-owned table; nothing existing changes.

Revision ID: b3e8d1f4a6c2
Revises: a7d3c5e9f2b8
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'b3e8d1f4a6c2'
down_revision = 'a7d3c5e9f2b8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('position_rollover',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('position_id', sa.Integer(), nullable=False),
    sa.Column('rolled_on', sa.String(length=10), nullable=False),
    sa.Column('venue_sandbox', sa.Boolean(), nullable=False),
    sa.Column('underlying', sa.String(length=16), nullable=False),
    sa.Column('occ_symbol', sa.String(length=32), nullable=False),
    sa.Column('option_type', sa.String(length=4), nullable=False),
    sa.Column('strike', sa.Float(), nullable=False),
    sa.Column('expiration', sa.String(length=10), nullable=False),
    sa.Column('days_left', sa.Integer(), nullable=False),
    sa.Column('contracts', sa.Integer(), nullable=False),
    sa.Column('entry_price', sa.Float(), nullable=True),
    sa.Column('close_bid', sa.Float(), nullable=True),
    sa.Column('unrealised_usd', sa.Float(), nullable=True),
    sa.Column('tp_price', sa.Float(), nullable=True),
    sa.Column('sl_price', sa.Float(), nullable=True),
    sa.Column('tp_order_id', sa.String(length=64), nullable=True),
    sa.Column('stop_order_id', sa.String(length=64), nullable=True),
    sa.Column('tp_status', sa.String(length=24), nullable=True),
    sa.Column('stop_status', sa.String(length=24), nullable=True),
    sa.Column('stop_protection', sa.String(length=16), nullable=False),
    sa.Column('strategy', sa.String(length=64), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_position_rollover_tenant_id_tenant'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['position_id'], ['position.id'], name=op.f('fk_position_rollover_position_id_position'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_position_rollover')),
    sa.UniqueConstraint('tenant_id', 'position_id', 'rolled_on', name='one_roll_per_session')
    )
    with op.batch_alter_table('position_rollover', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_position_rollover_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_position_rollover_tenant_day', ['tenant_id', 'rolled_on'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('position_rollover', schema=None) as batch_op:
        batch_op.drop_index('ix_position_rollover_tenant_day')
        batch_op.drop_index(batch_op.f('ix_position_rollover_tenant_id'))
    op.drop_table('position_rollover')
