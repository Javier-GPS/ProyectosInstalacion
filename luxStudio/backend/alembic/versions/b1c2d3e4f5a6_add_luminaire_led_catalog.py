"""Add LED/PCB/Driver catalog and 4-tuple -> LED binding for power cap.

Revision ID: b1c2d3e4f5a6
Revises: 0c1d2e3f4a5b
Create Date: 2026-06-06 18:00:00.000000

Adds:
- ``leds``         — one row per LED catalog entry from
  ``Param_ Configura`` (LED block). Stores the maximum power the LED
  can support (``pmax_lum``) and the adjusted power ceiling
  (``pmax_ajustada``) that the configurator must enforce.
- ``pcbs``         — one row per PCB catalog entry. Stored for
  diagnostics / future use; not used to compute the luminaire power
  cap.
- ``drivers``      — one row per driver catalog entry. Same purpose as
  ``pcbs`` — diagnostics only.
- ``luminaire_leds`` — one row per 4-tuple
  ``(gama, difusor, lente, led_type)`` linked to the LED it ships with.
  The CCT is intentionally not modelled; when a 4-tuple has several
  build options, the seed keeps the highest-cap ``LED_REF`` (highest
  ``pmax_ajustada``) and logs a warning.

These tables back the hard power cap that the configurator must
apply: a 4-tuple selection is allowed to use at most the
``pmax_ajustada`` of its corresponding ``LED_REF``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "0c1d2e3f4a5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "leds",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("led_ref", sa.String(50), nullable=False, unique=True),
        sa.Column("led_desc_corta", sa.String(255), nullable=True),
        sa.Column("led_tipo", sa.String(100), nullable=True),
        sa.Column("pmax_lum", sa.Float(), nullable=True),
        sa.Column("i_max_led", sa.Float(), nullable=True),
        sa.Column("pmax_ajustada", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index("ix_leds_led_ref", "leds", ["led_ref"], unique=True)

    op.create_table(
        "pcbs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pcb_ref", sa.String(50), nullable=False, unique=True),
        sa.Column("pcb_no_drivers", sa.Integer(), nullable=True),
        sa.Column("pcb_v_nominal", sa.Float(), nullable=True),
        sa.Column("pcb_no_led", sa.Integer(), nullable=True),
        sa.Column("pcb_no_circuitos", sa.Integer(), nullable=True),
        sa.Column("pcb_imax_led", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index("ix_pcbs_pcb_ref", "pcbs", ["pcb_ref"], unique=True)

    op.create_table(
        "drivers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("dr_ref", sa.String(50), nullable=False, unique=True),
        sa.Column("dr_pot_max_driver", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
    )
    op.create_index("ix_drivers_dr_ref", "drivers", ["dr_ref"], unique=True)

    op.create_table(
        "luminaire_leds",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("gama_id", sa.Integer(), nullable=False),
        sa.Column("difusor_id", sa.Integer(), nullable=False),
        sa.Column("lente_id", sa.Integer(), nullable=False),
        sa.Column("led_type_id", sa.Integer(), nullable=True),
        sa.Column("led_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(["gama_id"], ["gamas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["difusor_id"], ["difusores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lente_id"], ["lentes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["led_type_id"], ["led_types.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["led_id"], ["leds.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "gama_id", "difusor_id", "lente_id", "led_type_id",
            name="uq_luminaire_leds_4tuple",
        ),
    )
    op.create_index(
        "ix_luminaire_leds_4tuple",
        "luminaire_leds",
        ["gama_id", "difusor_id", "lente_id", "led_type_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_luminaire_leds_4tuple", table_name="luminaire_leds")
    op.drop_table("luminaire_leds")
    op.drop_index("ix_drivers_dr_ref", table_name="drivers")
    op.drop_table("drivers")
    op.drop_index("ix_pcbs_pcb_ref", table_name="pcbs")
    op.drop_table("pcbs")
    op.drop_index("ix_leds_led_ref", table_name="leds")
    op.drop_table("leds")
