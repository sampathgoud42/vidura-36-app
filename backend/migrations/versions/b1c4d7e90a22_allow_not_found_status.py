"""allow the not_found trade status

Hand-written, because alembic's autogenerate does not diff CHECK constraints:
the previous revision added `resolve_attempts` and silently left the old
constraint in place, so the column arrived and the value it exists to hold
would have been rejected at runtime.

SQLite cannot ALTER a constraint, so this is a table recreate. Batch mode
rebuilds from the model's metadata, which is why the indexes, the unique key
and the foreign key survive -- anything the model did not declare would not.

Revision ID: b1c4d7e90a22
Revises: 09adb10cc3da
"""
from __future__ import annotations

from alembic import op

revision = 'b1c4d7e90a22'
down_revision = '09adb10cc3da'
branch_labels = None
depends_on = None

OLD = "status in ('open','closed','cancelled','won','lost','settled')"
NEW = ("status in ('open','closed','cancelled','won','lost','settled',"
       "'not_found')")


def upgrade() -> None:
    with op.batch_alter_table('bot_trade', schema=None) as batch_op:
        # The BARE name: the naming convention adds the ck_bot_trade_
        # prefix itself, and passing the prefixed one asks for
        # ck_bot_trade_ck_bot_trade_status_known.
        batch_op.drop_constraint('status_known', type_='check')
        batch_op.create_check_constraint('status_known', NEW)


def downgrade() -> None:
    # Rows already marked not_found would violate the narrower constraint, so
    # they are put back to the honest predecessor: closed, with no P&L.
    op.execute("update bot_trade set status='closed' "
               "where status='not_found'")
    with op.batch_alter_table('bot_trade', schema=None) as batch_op:
        # The BARE name: the naming convention adds the ck_bot_trade_
        # prefix itself, and passing the prefixed one asks for
        # ck_bot_trade_ck_bot_trade_status_known.
        batch_op.drop_constraint('status_known', type_='check')
        batch_op.create_check_constraint('status_known', OLD)
