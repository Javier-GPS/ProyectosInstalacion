"""Reset mf_origen to 1.0 (raw LDTs).

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-06-13

The previous default ``mf_origen=0.85`` assumed Salvi LDTs had a 0.85
maintenance factor baked into the candela values. That assumption is
incorrect: integrating each LDT's intensity over the full sphere gives
LOR ≈ 1.000 for every Salvi file (CLAP, KRONOS, SIL families), confirming
the cd values are INITIAL output with no MF applied.

Effect of the bug: ``_effective_mf(config.mf=0.85, mf_origen=0.85) = 1.0``
caused the calculation engine to skip the user-supplied maintenance
factor entirely, overstating every illuminance and luminance by
~17.6 % (1 / 0.85 − 1).

This migration:
  1. Sets ``mf_origen = 1.0`` for every existing row.
  2. Changes the column default to 1.0 so future imports inherit the
     correct value.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE fotometrias SET mf_origen = 1.0")
    with op.batch_alter_table("fotometrias") as batch_op:
        batch_op.alter_column(
            "mf_origen",
            existing_type=sa.Float(),
            existing_nullable=False,
            server_default="1.0",
        )


def downgrade() -> None:
    op.execute("UPDATE fotometrias SET mf_origen = 0.85")
    with op.batch_alter_table("fotometrias") as batch_op:
        batch_op.alter_column(
            "mf_origen",
            existing_type=sa.Float(),
            existing_nullable=False,
            server_default="0.85",
        )
