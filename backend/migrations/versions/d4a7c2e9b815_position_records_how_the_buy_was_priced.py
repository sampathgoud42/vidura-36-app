"""position records how the buy was priced

The ticket offers three ways to buy -- smart, market, or a limit at the mark
less a discount -- and a discounted limit that has not filled in fifteen
minutes is withdrawn. The position keeps what was sent (order_type,
limit_price, discount_pct) and when an unfilled limit is withdrawn
(buy_expires_at), so the monitor can do it and the desks can show it.

Four nullable columns, so every row placed before this reads as it always
did: no order type recorded, no limit shown, never withdrawn.

Revision ID: d4a7c2e9b815
Revises: b1c4d7e90a22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = 'd4a7c2e9b815'
down_revision = 'b1c4d7e90a22'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('position', schema=None) as batch_op:
        batch_op.add_column(sa.Column('order_type', sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column('limit_price', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('discount_pct', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('buy_expires_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('position', schema=None) as batch_op:
        batch_op.drop_column('buy_expires_at')
        batch_op.drop_column('discount_pct')
        batch_op.drop_column('limit_price')
        batch_op.drop_column('order_type')
