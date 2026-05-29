"""add raw courier data to pending events

Revision ID: q5r6s7t8u9v0
Revises: p4q5r6s7t8u9
Create Date: 2026-05-27 16:45:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "q5r6s7t8u9v0"
down_revision: Union[str, None] = "p4q5r6s7t8u9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _sqlite_has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    rows = bind.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def _add_column_if_missing(table_name: str, column_name: str, ddl: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        if not _sqlite_has_column(table_name, column_name):
            op.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")
        return
    op.execute(f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {ddl}")


def upgrade() -> None:
    bind = op.get_bind()
    json_type = "JSONB" if bind.dialect.name == "postgresql" else "JSON"
    bool_type = "BOOLEAN DEFAULT FALSE NOT NULL" if bind.dialect.name == "postgresql" else "BOOLEAN DEFAULT 0 NOT NULL"

    _add_column_if_missing("pending_events", "raw_order_data", json_type)
    _add_column_if_missing("pending_events", "portal_state", "VARCHAR(50)")
    _add_column_if_missing("pending_events", "is_confirmed", bool_type)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return
    op.execute("ALTER TABLE pending_events DROP COLUMN IF EXISTS is_confirmed")
    op.execute("ALTER TABLE pending_events DROP COLUMN IF EXISTS portal_state")
    op.execute("ALTER TABLE pending_events DROP COLUMN IF EXISTS raw_order_data")
