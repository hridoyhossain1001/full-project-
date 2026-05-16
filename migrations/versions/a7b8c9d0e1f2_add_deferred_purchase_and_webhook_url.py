"""add deferred_purchase and webhook_url to clients

Revision ID: a7b8c9d0e1f2
Revises: 2346a5d9e53f
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = '6f95f5ca1ac2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('clients', sa.Column('deferred_purchase', sa.Boolean(), nullable=True, server_default=sa.text('false')))
    op.add_column('clients', sa.Column('webhook_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('clients', 'webhook_url')
    op.drop_column('clients', 'deferred_purchase')
