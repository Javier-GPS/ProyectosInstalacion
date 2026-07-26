"""Add LUXEON 5050 model fields to leds + ts_coefficients table.

Adds to ``leds``:
- ``family`` (str): LUXEON 5050 family key (HE_PLUS_6V, HE_6V, …)
- ``flux_ref_lm`` (float): typical luminous flux at the family reference
  current, Tj=25 °C, from the datasheet Table 1a.
- ``cct`` (int): nominal correlated colour temperature, Kelvin.
- ``cri`` (int): minimum CRI.
- ``part_number`` (str, nullable): Lumileds partNumber (kept for
  traceability even though the application does not need it for the
  flux lookup).
- ``same_drive_flux_lm`` (float, nullable): flux at the same-drive
  current from the datasheet.
- ``technology`` (str, nullable): standard / HE Plus / Crisp Color / …

Adds ``ts_coefficients`` table to map ``(gama, difusor) -> coef_led
(°C/W)`` so the thermal model can compute ``Tsp`` per luminaire.

Revision ID: d3e4f5a6b7c8
Revises: c50ad46b421c
Create Date: 2026-06-18 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c50ad46b421c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leds", sa.Column("family", sa.String(length=40), nullable=True))
    op.add_column("leds", sa.Column("flux_ref_lm", sa.Float(), nullable=True))
    op.add_column("leds", sa.Column("cct", sa.Integer(), nullable=True))
    op.add_column("leds", sa.Column("cri", sa.Integer(), nullable=True))
    op.add_column("leds", sa.Column("part_number", sa.String(length=40), nullable=True))
    op.add_column("leds", sa.Column("same_drive_flux_lm", sa.Float(), nullable=True))
    op.add_column("leds", sa.Column("technology", sa.String(length=60), nullable=True))
    op.create_index("ix_leds_family", "leds", ["family"])

    op.create_table(
        "ts_coefficients",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "gama_id",
            sa.Integer(),
            sa.ForeignKey("gamas.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "difusor_id",
            sa.Integer(),
            sa.ForeignKey("difusores.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("coef_led_c_per_w", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.UniqueConstraint("gama_id", "difusor_id", name="uq_ts_coefficients_pair"),
    )


def downgrade() -> None:
    op.drop_table("ts_coefficients")
    op.drop_index("ix_leds_family", table_name="leds")
    op.drop_column("leds", "technology")
    op.drop_column("leds", "same_drive_flux_lm")
    op.drop_column("leds", "part_number")
    op.drop_column("leds", "cri")
    op.drop_column("leds", "cct")
    op.drop_column("leds", "flux_ref_lm")
    op.drop_column("leds", "family")
