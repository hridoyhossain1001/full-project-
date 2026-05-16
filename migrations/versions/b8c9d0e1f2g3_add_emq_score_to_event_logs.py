"""add emq_score to event_logs

Revision ID: b8c9d0e1f2g3
Revises: a7b8c9d0e1f2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2g3'
down_revision: Union[str, None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('event_logs', sa.Column('emq_score', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('event_logs', 'emq_score')
