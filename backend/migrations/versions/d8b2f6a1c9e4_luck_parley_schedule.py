"""luck parley schedule

The Luck parley can be scheduled: a ticket built and placed in the background
at 9:00 and 18:00 Chicago time every day, while the operator has it switched
on. luck_schedule holds each operator's switch and the ticket's settings;
luck_run holds one row per slot, written before the ticket is built, unique
per (tenant, slot) so a slot can never be run twice.

Two new tenant-owned tables, nothing else touched; a downgrade drops them.

Revision ID: d8b2f6a1c9e4
Revises: c6d9e2a4f7b1
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'd8b2f6a1c9e4'
down_revision = 'c6d9e2a4f7b1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('luck_run',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('slot', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('detail', sa.String(length=255), nullable=True),
    sa.Column('legs', sa.Integer(), nullable=True),
    sa.Column('cost_usd', sa.Float(), nullable=True),
    sa.Column('combo_ticker', sa.String(length=64), nullable=True),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("status in ('running','placed','skipped','failed','interrupted')", name=op.f('ck_luck_run_status_known')),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_luck_run_tenant_id_tenant'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_luck_run')),
    sa.UniqueConstraint('tenant_id', 'slot', name='one_run_per_slot')
    )
    with op.batch_alter_table('luck_run', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_luck_run_tenant_id'), ['tenant_id'], unique=False)
        batch_op.create_index('ix_luck_run_tenant_slot', ['tenant_id', 'slot'], unique=False)

    op.create_table('luck_schedule',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('enabled_at', sa.DateTime(), nullable=True),
    sa.Column('config_json', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_luck_schedule_tenant_id_tenant'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_luck_schedule')),
    sa.UniqueConstraint('tenant_id', name='one_schedule_per_tenant')
    )
    with op.batch_alter_table('luck_schedule', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_luck_schedule_tenant_id'), ['tenant_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('luck_schedule', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_luck_schedule_tenant_id'))

    op.drop_table('luck_schedule')
    with op.batch_alter_table('luck_run', schema=None) as batch_op:
        batch_op.drop_index('ix_luck_run_tenant_slot')
        batch_op.drop_index(batch_op.f('ix_luck_run_tenant_id'))

    op.drop_table('luck_run')
