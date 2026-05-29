"""add shopify shared secret

Revision ID: u9v0w1x2y3z4
Revises: t8u9v0w1x2y3
Create Date: 2026-05-29 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "u9v0w1x2y3z4"
down_revision: Union[str, None] = "t8u9v0w1x2y3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        existing = {row[1] for row in bind.exec_driver_sql("PRAGMA table_info(clients)").fetchall()}
        if "shopify_shared_secret" not in existing:
            op.add_column("clients", sa.Column("shopify_shared_secret", sa.String(), nullable=True))
        return

    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS shopify_shared_secret VARCHAR")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    op.execute("ALTER TABLE clients DROP COLUMN IF EXISTS shopify_shared_secret")
