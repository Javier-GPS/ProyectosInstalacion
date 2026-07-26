"""Add CRI to luminaires

Revision ID: 9b2e7a6d4c11
Revises: 70fdb4b2b3e6
Create Date: 2026-06-01 22:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9b2e7a6d4c11"
down_revision: Union[str, Sequence[str], None] = "70fdb4b2b3e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "luminaires",
        sa.Column("cri", sa.Integer(), nullable=False, server_default="70"),
    )
    op.execute("UPDATE luminaires SET cri = 70 WHERE cri IS NULL")


def downgrade() -> None:
    op.drop_column("luminaires", "cri")
