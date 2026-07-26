"""Add eficiencia to difusores

Revision ID: c50ad46b421c
Revises: a7b8c9d0e1f2
Create Date: 2026-06-18 09:46:09.094011

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c50ad46b421c'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('difusores', sa.Column('eficiencia', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('difusores', 'eficiencia')
