"""add event_id to event_logs

Revision ID: f125ee6894bf
Revises: 
Create Date: 2026-05-05 17:53:58.071757
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f125ee6894bf'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('event_logs', sa.Column('event_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_event_logs_event_id'), 'event_logs', ['event_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_event_logs_event_id'), table_name='event_logs')
    op.drop_column('event_logs', 'event_id')
