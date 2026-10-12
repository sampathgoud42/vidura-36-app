"""combo15 auto: the 15M Combo, built and placed every quarter hour

Two tenant-owned tables, as the Luck schedule has: combo15_auto (the switch,
one row per operator) and combo15_auto_run (one row per slot, written before
the combo is built and unique per operator and slot, so a slot never runs
twice).

Revision ID: f4b8d2c6a1e7
Revises: e3a7c1f5d9b2
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'f4b8d2c6a1e7'
down_revision = 'e3a7c1f5d9b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('combo15_auto',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('enabled_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_combo15_auto_tenant_id_tenant'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_combo15_auto')),
    sa.UniqueConstraint('tenant_id', name='one_combo15_auto_per_tenant')
    )
    with op.batch_alter_table('combo15_auto', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_combo15_auto_tenant_id'), ['tenant_id'], unique=False)

    op.create_table('combo15_auto_run',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('slot', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('detail', sa.String(length=255), nullable=True),
    sa.Column('legs', sa.Integer(), nullable=True),
    sa.Column('chance_pct', sa.Float(), nullable=True),
    sa.Column('stake_usd', sa.Float(), nullable=True),
    sa.Column('cost_usd', sa.Float(), nullable=True),
    sa.Column('combo_ticker', sa.String(length=64), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("status in ('running','placed','skipped','failed','interrupted')", name=op.f('ck_combo15_auto_run_status_known')),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_combo15_auto_run_tenant_id_tenant'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_combo15_auto_run')),
    sa.UniqueConstraint('tenant_id', 'slot', name='one_combo15_run_per_slot')
    )
    with op.batch_alter_table('combo15_auto_run', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_combo15_auto_run_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_combo15_auto_run_tenant_slot', ['tenant_id', 'slot'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('combo15_auto_run', schema=None) as batch_op:
        batch_op.drop_index('ix_combo15_auto_run_tenant_slot')
        batch_op.drop_index(batch_op.f('ix_combo15_auto_run_tenant_id'))
    op.drop_table('combo15_auto_run')
    with op.batch_alter_table('combo15_auto', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_combo15_auto_tenant_id'))
    op.drop_table('combo15_auto')
