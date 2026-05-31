"""add refund_event_sent to courier_orders

Revision ID: w1x2y3z4a5b6
Revises: v0w1x2y3z4a5
Create Date: 2026-05-31 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "w1x2y3z4a5b6"
down_revision: Union[str, None] = "v0w1x2y3z4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        existing = {row[1] for row in bind.exec_driver_sql("PRAGMA table_info(courier_orders)").fetchall()}
        if "refund_event_sent" not in existing:
            op.add_column(
                "courier_orders",
                sa.Column("refund_event_sent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        return

    op.execute(
        "ALTER TABLE courier_orders "
        "ADD COLUMN IF NOT EXISTS refund_event_sent BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    op.execute("ALTER TABLE courier_orders DROP COLUMN IF EXISTS refund_event_sent")
