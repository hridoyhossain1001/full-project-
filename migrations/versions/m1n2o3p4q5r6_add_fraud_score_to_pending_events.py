"""add fraud score to pending events

Revision ID: m1n2o3p4q5r6
Revises: 7b6820fcccf6
Create Date: 2026-05-24 21:35:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m1n2o3p4q5r6"
down_revision: Union[str, None] = "7b6820fcccf6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns to pending_events table
    op.add_column(
        "pending_events",
        sa.Column("fraud_score", sa.Integer(), nullable=True)
    )
    op.add_column(
        "pending_events",
        sa.Column("fraud_details", sa.JSON(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("pending_events", "fraud_details")
    op.drop_column("pending_events", "fraud_score")
