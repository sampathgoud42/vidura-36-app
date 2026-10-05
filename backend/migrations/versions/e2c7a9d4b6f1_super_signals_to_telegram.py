"""super signals to telegram

New Super Signals can be posted to an operator's Telegram chat by a bot of
theirs. Two new tenant-owned tables: telegram_feed (the chat, the switch,
when it was switched on, the last error) and telegram_post (one row per
posted signal, unique per operator, so a signal is posted once).

The bot token is a credential like every other key the desk holds, so the
tenant_credential CHECK learns the venue 'telegram'. Hand-written for that
part -- autogenerate does not diff CHECK constraints -- and a table recreate,
because SQLite cannot ALTER one (as in c6d9e2a4f7b1). Batch mode copies every
row and keeps the indexes, the unique key and the foreign key.

Revision ID: e2c7a9d4b6f1
Revises: d8b2f6a1c9e4
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'e2c7a9d4b6f1'
down_revision = 'd8b2f6a1c9e4'
branch_labels = None
depends_on = None

OLD_VENUES = "venue in ('tradier','tradier_sandbox','kalshi')"
NEW_VENUES = "venue in ('tradier','tradier_sandbox','kalshi','telegram')"


def upgrade() -> None:
    with op.batch_alter_table('tenant_credential', schema=None) as batch_op:
        # The BARE name: the naming convention adds ck_tenant_credential_.
        batch_op.drop_constraint('venue_known', type_='check')
        batch_op.create_check_constraint('venue_known', NEW_VENUES)

    op.create_table('telegram_feed',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('enabled_at', sa.DateTime(), nullable=True),
    sa.Column('chat_id', sa.String(length=64), nullable=True),
    sa.Column('chat_title', sa.String(length=128), nullable=True),
    sa.Column('posted', sa.Integer(), nullable=False),
    sa.Column('last_post_at', sa.DateTime(), nullable=True),
    sa.Column('last_error', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_telegram_feed_tenant_id_tenant'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_telegram_feed')),
    sa.UniqueConstraint('tenant_id', name='one_feed_per_tenant')
    )
    with op.batch_alter_table('telegram_feed', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_telegram_feed_tenant_id'), ['tenant_id'], unique=False)

    op.create_table('telegram_post',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tenant_id', sa.String(length=36), nullable=False),
    sa.Column('signal_id', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], name=op.f('fk_telegram_post_tenant_id_tenant'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_telegram_post')),
    sa.UniqueConstraint('tenant_id', 'signal_id', name='one_post_per_signal')
    )
    with op.batch_alter_table('telegram_post', schema=None) as batch_op:
        batch_op.create_index('ix_telegram_post_tenant_created', ['tenant_id', 'created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_telegram_post_tenant_id'), ['tenant_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('telegram_post', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_telegram_post_tenant_id'))
        batch_op.drop_index('ix_telegram_post_tenant_created')

    op.drop_table('telegram_post')
    with op.batch_alter_table('telegram_feed', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_telegram_feed_tenant_id'))

    op.drop_table('telegram_feed')

    # The narrower CHECK cannot hold a Telegram bot token: those go with the
    # feature they served.
    op.execute("delete from tenant_credential where venue='telegram'")
    with op.batch_alter_table('tenant_credential', schema=None) as batch_op:
        batch_op.drop_constraint('venue_known', type_='check')
        batch_op.create_check_constraint('venue_known', OLD_VENUES)
