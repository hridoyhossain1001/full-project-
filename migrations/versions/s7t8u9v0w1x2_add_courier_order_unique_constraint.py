"""add courier order unique constraint

Revision ID: s7t8u9v0w1x2
Revises: r6s7t8u9v0w1
Create Date: 2026-05-29 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "s7t8u9v0w1x2"
down_revision: Union[str, None] = "r6s7t8u9v0w1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite cannot add a named unique constraint to an existing table
        # without table rebuild; tests/new DBs already get it from create_all.
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_courier_orders_client_order "
            "ON courier_orders (client_id, order_id)"
        )
        return

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_courier_orders_client_order'
            ) THEN
                ALTER TABLE courier_orders
                ADD CONSTRAINT uq_courier_orders_client_order UNIQUE (client_id, order_id);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP INDEX IF EXISTS uq_courier_orders_client_order")
        return

    op.execute(
        "ALTER TABLE courier_orders "
        "DROP CONSTRAINT IF EXISTS uq_courier_orders_client_order"
    )
