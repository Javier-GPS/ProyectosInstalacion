"""Merge heads: 4-tuple -> LED catalog and luminaires -> fotometrias rename.

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6, d1e2f3a4b5c6
Create Date: 2026-06-06 18:10:00.000000

Empty merge migration to bring the two heads together so a single
``alembic upgrade head`` runs both branches.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = ("b1c2d3e4f5a6", "d1e2f3a4b5c6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
