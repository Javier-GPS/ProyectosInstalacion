"""Add valid_combinations table.

Revision ID: 8a1f2e3b4c5d
Revises: 7c0e1b2a3d4f
Create Date: 2026-06-04 10:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8a1f2e3b4c5d"
down_revision: Union[str, Sequence[str], None] = "7c0e1b2a3d4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "valid_combinations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("gama_id", sa.Integer(), nullable=False),
        sa.Column("difusor_id", sa.Integer(), nullable=False),
        sa.Column("lente_id", sa.Integer(), nullable=False),
        sa.Column("led_type_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(["gama_id"], ["gamas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["difusor_id"], ["difusores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lente_id"], ["lentes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["led_type_id"], ["led_types.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "gama_id", "difusor_id", "lente_id", "led_type_id",
            name="uq_valid_combinations",
        ),
    )


def downgrade() -> None:
    op.drop_table("valid_combinations")
