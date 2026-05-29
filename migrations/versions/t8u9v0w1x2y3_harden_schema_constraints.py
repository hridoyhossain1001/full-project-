"""harden schema constraints

Revision ID: t8u9v0w1x2y3
Revises: s7t8u9v0w1x2
Create Date: 2026-05-29 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "t8u9v0w1x2y3"
down_revision: Union[str, None] = "s7t8u9v0w1x2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CLIENT_DEFAULTS = {
    "is_active": "true",
    "rate_limit": "5000",
    "daily_quota": "100000",
    "deferred_purchase": "false",
    "monthly_limit": "50000",
}


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(idx["name"] == index_name for idx in inspector.get_indexes(table_name))


def _constraint_exists(bind, table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(bind)
    constraints = inspector.get_unique_constraints(table_name)
    constraints += inspector.get_foreign_keys(table_name)
    return any(constraint.get("name") == constraint_name for constraint in constraints)


def _postgres_constraint_exists(bind, constraint_name: str) -> bool:
    return bool(
        bind.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
            {"name": constraint_name},
        ).scalar()
    )


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_courier_orders_courier_status "
            "ON courier_orders (courier_status)"
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_client_users_client_email "
            "ON client_users (client_id, email)"
        )
        return

    for column_name, default_sql in CLIENT_DEFAULTS.items():
        existing_type = sa.Boolean() if default_sql in {"true", "false"} else sa.Integer()
        op.execute(f"UPDATE clients SET {column_name} = {default_sql} WHERE {column_name} IS NULL")
        op.alter_column(
            "clients",
            column_name,
            existing_type=existing_type,
            nullable=False,
            server_default=sa.text(default_sql),
        )
        op.alter_column("clients", column_name, existing_type=existing_type, server_default=None)

    if _index_exists(bind, "client_users", "ix_client_users_email"):
        op.drop_index("ix_client_users_email", table_name="client_users")
    if _postgres_constraint_exists(bind, "client_users_email_key"):
        op.drop_constraint("client_users_email_key", "client_users", type_="unique")
    if not _constraint_exists(bind, "client_users", "uq_client_users_client_email"):
        op.create_unique_constraint(
            "uq_client_users_client_email",
            "client_users",
            ["client_id", "email"],
        )
    if not _index_exists(bind, "client_users", "ix_client_users_email"):
        op.create_index("ix_client_users_email", "client_users", ["email"], unique=False)

    op.execute("ALTER TABLE client_sessions DROP CONSTRAINT IF EXISTS client_sessions_client_id_fkey")
    op.execute("ALTER TABLE client_sessions DROP CONSTRAINT IF EXISTS client_sessions_user_id_fkey")
    op.create_foreign_key(
        "client_sessions_client_id_fkey",
        "client_sessions",
        "clients",
        ["client_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "client_sessions_user_id_fkey",
        "client_sessions",
        "client_users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    if not _index_exists(bind, "courier_orders", "ix_courier_orders_courier_status"):
        op.create_index(
            "ix_courier_orders_courier_status",
            "courier_orders",
            ["courier_status"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        op.execute("DROP INDEX IF EXISTS ix_courier_orders_courier_status")
        op.execute("DROP INDEX IF EXISTS uq_client_users_client_email")
        return

    if _index_exists(bind, "courier_orders", "ix_courier_orders_courier_status"):
        op.drop_index("ix_courier_orders_courier_status", table_name="courier_orders")

    op.execute("ALTER TABLE client_sessions DROP CONSTRAINT IF EXISTS client_sessions_client_id_fkey")
    op.execute("ALTER TABLE client_sessions DROP CONSTRAINT IF EXISTS client_sessions_user_id_fkey")
    op.create_foreign_key(
        "client_sessions_client_id_fkey",
        "client_sessions",
        "clients",
        ["client_id"],
        ["id"],
    )
    op.create_foreign_key(
        "client_sessions_user_id_fkey",
        "client_sessions",
        "client_users",
        ["user_id"],
        ["id"],
    )

    if _constraint_exists(bind, "client_users", "uq_client_users_client_email"):
        op.drop_constraint("uq_client_users_client_email", "client_users", type_="unique")
    if _index_exists(bind, "client_users", "ix_client_users_email"):
        op.drop_index("ix_client_users_email", table_name="client_users")
    op.create_index("ix_client_users_email", "client_users", ["email"], unique=True)
    op.create_unique_constraint("client_users_email_key", "client_users", ["email"])

    for column_name, default_sql in CLIENT_DEFAULTS.items():
        op.alter_column(
            "clients",
            column_name,
            existing_type=sa.Boolean() if default_sql in {"true", "false"} else sa.Integer(),
            nullable=True,
        )
