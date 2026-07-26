"""add project calculation settings

Revision ID: 6d7e8f9a0b1c
Revises: f2b156ef1546
Create Date: 2026-06-21 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "6d7e8f9a0b1c"
down_revision: Union[str, None] = "f2b156ef1546"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("t_amb_c", sa.Float(), nullable=False, server_default="25.0"))
    op.add_column("projects", sa.Column("i_op_ma", sa.Float(), nullable=True))
    op.add_column("projects", sa.Column("lm_w_min", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "lm_w_min")
    op.drop_column("projects", "i_op_ma")
    op.drop_column("projects", "t_amb_c")
