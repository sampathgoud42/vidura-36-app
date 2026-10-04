"""signal trades can be bought unwatched

A RISKY-BUY from the Bot Station's signal form is bought whatever its bid and
watched by nothing -- no take-profit, no stop-loss -- and is recorded with
the status 'unwatched'. The previous revision's CHECK does not know it.

Hand-written, because autogenerate does not diff CHECK constraints, and a
table recreate, because SQLite cannot ALTER one (the same shape as
b1c4d7e90a22). Batch mode rebuilds from the model's metadata, so the indexes,
the unique key and the foreign key survive.

Revision ID: c6d9e2a4f7b1
Revises: a3f8d2c6e1b7
"""
from __future__ import annotations

from alembic import op

revision = 'c6d9e2a4f7b1'
down_revision = 'a3f8d2c6e1b7'
branch_labels = None
depends_on = None

OLD = "status in ('watching','tp','sl','expired','closed','unfilled')"
NEW = ("status in ('watching','tp','sl','expired','closed','unfilled',"
       "'unwatched')")


def upgrade() -> None:
    with op.batch_alter_table('signal_trade', schema=None) as batch_op:
        # The BARE name: the naming convention adds the ck_signal_trade_
        # prefix itself.
        batch_op.drop_constraint('status_known', type_='check')
        batch_op.create_check_constraint('status_known', NEW)


def downgrade() -> None:
    # An unwatched row has no closer word under the narrower constraint than
    # 'expired': bought, held, and left to settle.
    op.execute("update signal_trade set status='expired' "
               "where status='unwatched'")
    with op.batch_alter_table('signal_trade', schema=None) as batch_op:
        batch_op.drop_constraint('status_known', type_='check')
        batch_op.create_check_constraint('status_known', OLD)
