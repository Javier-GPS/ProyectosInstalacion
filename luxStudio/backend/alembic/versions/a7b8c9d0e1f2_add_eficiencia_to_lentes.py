"""Add eficiencia column to lentes table.

Revision ID: a7b8c9d0e1f2
Revises: 393004ff84ac
Create Date: 2026-06-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "393004ff84ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lentes", sa.Column("eficiencia", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("lentes", "eficiencia")
