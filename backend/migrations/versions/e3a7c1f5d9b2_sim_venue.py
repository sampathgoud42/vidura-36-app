"""sim venue: the LONG-TERM (SIM) paper broker

An in-house simulated broker as a third venue beside Tradier's live account
and its sandbox (execution.sim). Three new tenant-owned tables -- the
account (cash, and whether it is the board's paper venue), its holdings and
its orders -- and ``position.simulated``, so a simulated position is never
confused with a sandbox one: both are paper (venue_sandbox), only this says
which paper.

Existing positions are all Tradier's, so the column defaults false.

Revision ID: e3a7c1f5d9b2
Revises: d8b2f6a1c4e9
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'e3a7c1f5d9b2'
down_revision = 'd8b2f6a1c4e9'
branch_labels = None
depends_on = None


def _owned(name: str, *columns, constraints=()):
    op.create_table(name,
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        *columns,
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'],
                                name=op.f(f'fk_{name}_tenant_id_tenant'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f(f'pk_{name}')),
        *constraints)
    with op.batch_alter_table(name, schema=None) as batch_op:
        batch_op.create_index(batch_op.f(f'ix_{name}_tenant_id'), ['tenant_id'], unique=False)


def upgrade() -> None:
    _owned('sim_account',
           sa.Column('label', sa.String(length=32), nullable=False),
           sa.Column('active', sa.Boolean(), nullable=False),
           sa.Column('cash', sa.Float(), nullable=False),
           sa.Column('seeded_equity', sa.Float(), nullable=True),
           sa.Column('seeded_at', sa.DateTime(), nullable=True),
           constraints=(sa.UniqueConstraint('tenant_id', name='one_sim_account_per_tenant'),))
    _owned('sim_holding',
           sa.Column('asset', sa.String(length=8), nullable=False),
           sa.Column('symbol', sa.String(length=32), nullable=False),
           sa.Column('underlying', sa.String(length=16), nullable=False),
           sa.Column('quantity', sa.Float(), nullable=False),
           sa.Column('avg_price', sa.Float(), nullable=False),
           sa.Column('opened_at', sa.DateTime(), nullable=True),
           constraints=(sa.UniqueConstraint('tenant_id', 'symbol',
                                            name='one_sim_holding_per_symbol'),))
    _owned('sim_order',
           sa.Column('asset', sa.String(length=8), nullable=False),
           sa.Column('symbol', sa.String(length=32), nullable=False),
           sa.Column('underlying', sa.String(length=16), nullable=False),
           sa.Column('side', sa.String(length=16), nullable=False),
           sa.Column('quantity', sa.Float(), nullable=False),
           sa.Column('order_type', sa.String(length=8), nullable=False),
           sa.Column('price', sa.Float(), nullable=True),
           sa.Column('stop_price', sa.Float(), nullable=True),
           sa.Column('duration', sa.String(length=4), nullable=False),
           sa.Column('status', sa.String(length=16), nullable=False),
           sa.Column('avg_fill_price', sa.Float(), nullable=True),
           sa.Column('exec_quantity', sa.Float(), nullable=False),
           sa.Column('realized', sa.Float(), nullable=True),
           sa.Column('reason', sa.String(length=255), nullable=True),
           sa.Column('filled_at', sa.DateTime(), nullable=True))
    with op.batch_alter_table('sim_order', schema=None) as batch_op:
        batch_op.create_index('ix_sim_order_tenant_status', ['tenant_id', 'status'], unique=False)
    with op.batch_alter_table('position', schema=None) as batch_op:
        batch_op.add_column(sa.Column('simulated', sa.Boolean(), nullable=False,
                                      server_default='0'))


def downgrade() -> None:
    with op.batch_alter_table('position', schema=None) as batch_op:
        batch_op.drop_column('simulated')
    with op.batch_alter_table('sim_order', schema=None) as batch_op:
        batch_op.drop_index('ix_sim_order_tenant_status')
    for name in ('sim_order', 'sim_holding', 'sim_account'):
        with op.batch_alter_table(name, schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(f'ix_{name}_tenant_id'))
        op.drop_table(name)
