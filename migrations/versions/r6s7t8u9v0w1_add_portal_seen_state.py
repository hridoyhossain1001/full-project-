"""add portal seen state

Revision ID: r6s7t8u9v0w1
Revises: q5r6s7t8u9v0
Create Date: 2026-05-28 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "r6s7t8u9v0w1"
down_revision: Union[str, None] = "q5r6s7t8u9v0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _sqlite_has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        if not _sqlite_has_column("clients", "portal_seen_state"):
            op.execute("ALTER TABLE clients ADD COLUMN portal_seen_state JSON")
        return
    op.execute("ALTER TABLE clients ADD COLUMN IF NOT EXISTS portal_seen_state JSONB")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    op.execute("ALTER TABLE clients DROP COLUMN IF EXISTS portal_seen_state")
