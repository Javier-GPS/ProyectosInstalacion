"""Add mf_origen column to fotometrias.

Revision ID: e1f2a3b4c5d6
Revises: c2d3e4f5a6b7
Create Date: 2026-06-13

The new column records the maintenance factor that was already baked into
the LDT candela values when the file was imported. The calculation engine
uses ``mf_efectivo = config.mf / fotometria.mf_origen`` to avoid
double-applying the depreciation.

All existing rows are backfilled to 0.85 (the historical default for this
catalog), so no calculation result changes for legacy LDTs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("fotometrias") as batch_op:
        batch_op.add_column(
            sa.Column(
                "mf_origen",
                sa.Float(),
                nullable=False,
                server_default="0.85",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("fotometrias") as batch_op:
        batch_op.drop_column("mf_origen")
