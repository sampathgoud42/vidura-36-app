"""signal trades on fifteen-minute markets

A DMI signal on the Bot Station (CALL or PUT) can be bought by hand on the
asset's Kalshi fifteen-minute market. Each such trade is one row, and the row
is the watch: the background loop reads every 'watching' row on each pass to
apply its take-profit and stop-loss, so a trade outlives a restart.

One new tenant-owned table, nothing else touched; a downgrade drops it.

Revision ID: a3f8d2c6e1b7
Revises: e5c1a9f3b7d4
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'a3f8d2c6e1b7'
down_revision = 'e5c1a9f3b7d4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('signal_trade',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('request_id', sa.String(length=64), nullable=False),
    sa.Column('asset', sa.String(length=16), nullable=False),
    sa.Column('series', sa.String(length=24), nullable=False),
    sa.Column('ticker', sa.String(length=64), nullable=False),
    sa.Column('signal', sa.String(length=4), nullable=False),
    sa.Column('confirmed', sa.Boolean(), nullable=False),
    sa.Column('side', sa.String(length=3), nullable=False),
    sa.Column('contracts', sa.Float(), nullable=False),
    sa.Column('filled', sa.Float(), nullable=False),
    sa.Column('entry_c', sa.Float(), nullable=True),
    sa.Column('tp_c', sa.Float(), nullable=True),
    sa.Column('sl_c', sa.Float(), nullable=True),
    sa.Column('close_at', sa.DateTime(), nullable=False),
    sa.Column('order_id', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('exited', sa.Float(), nullable=False),
    sa.Column('exit_c', sa.Float(), nullable=True),
    sa.Column('note', sa.String(length=255), nullable=True),
    sa.Column('closed_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("side in ('yes','no')", name=op.f('ck_signal_trade_side_known')),
    sa.CheckConstraint("signal in ('call','put')", name=op.f('ck_signal_trade_signal_known')),
    sa.CheckConstraint("status in ('watching','tp','sl','expired','closed','unfilled')", name=op.f('ck_signal_trade_status_known')),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_signal_trade_tenant_id_tenant'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_signal_trade')),
    sa.UniqueConstraint('tenant_id', 'request_id', name='tenant_request')
    )
    with op.batch_alter_table('signal_trade', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_signal_trade_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_signal_trade_tenant_status', ['tenant_id', 'status'], unique=False)



def downgrade() -> None:
    with op.batch_alter_table('signal_trade', schema=None) as batch_op:
        batch_op.drop_index('ix_signal_trade_tenant_status')
        batch_op.drop_index(batch_op.f('ix_signal_trade_tenant_id'))

    op.drop_table('signal_trade')
