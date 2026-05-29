"""add composite index on pending_events created_at

Revision ID: p4q5r6s7t8u9
Revises: o3p4q5r6s7t8
Create Date: 2026-05-27 10:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p4q5r6s7t8u9"
down_revision: Union[str, None] = "o3p4q5r6s7t8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # expiry_service ও cleanup_service created_at দিয়ে query করে —
    # composite index যোগ করলে full table scan এড়ানো যাবে।
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_pending_client_status_created "
            "ON pending_events (client_id, status, created_at);"
        )
    else:
        # SQLite (test environment)
        try:
            op.create_index(
                "ix_pending_client_status_created",
                "pending_events",
                ["client_id", "status", "created_at"],
                unique=False,
            )
        except Exception:
            pass  # Index may already exist


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_pending_client_status_created;")
    else:
        try:
            op.drop_index("ix_pending_client_status_created", table_name="pending_events")
        except Exception:
            pass
