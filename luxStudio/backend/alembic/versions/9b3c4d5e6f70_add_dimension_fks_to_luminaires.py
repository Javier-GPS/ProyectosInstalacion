"""Add dimension FKs, fotometria and photometric_path columns to luminaires.

Revision ID: 9b3c4d5e6f70
Revises: 8a1f2e3b4c5d
Create Date: 2026-06-04 10:10:00.000000

Las nuevas columnas son todas NULL al principio. La migración siguiente
realiza el backfill desde las columnas legadas ``type`` y ``optic_family``
y desde el nombre de archivo del LDT, y deja ``gama_id``, ``difusor_id``,
``lente_id`` como NOT NULL. ``led_type_id`` y ``fotometria`` permanecen
NULL para los LDTs legacy (los nuevos LDTs importados desde el xlsx
tendrán estos campos rellenos).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b3c4d5e6f70"
down_revision: Union[str, Sequence[str], None] = "8a1f2e3b4c5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nuevas columnas — todas NULL inicialmente.
    with op.batch_alter_table("luminaires") as batch_op:
        batch_op.add_column(sa.Column("gama_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("difusor_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("lente_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("led_type_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("fotometria", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("photometric_path", sa.String(length=255), nullable=True))
        batch_op.create_foreign_key(
            "fk_luminaires_gama_id", "gamas", ["gama_id"], ["id"], ondelete="RESTRICT"
        )
        batch_op.create_foreign_key(
            "fk_luminaires_difusor_id", "difusores", ["difusor_id"], ["id"], ondelete="RESTRICT"
        )
        batch_op.create_foreign_key(
            "fk_luminaires_lente_id", "lentes", ["lente_id"], ["id"], ondelete="RESTRICT"
        )
        batch_op.create_foreign_key(
            "fk_luminaires_led_type_id", "led_types", ["led_type_id"], ["id"], ondelete="RESTRICT"
        )
        batch_op.create_unique_constraint("uq_luminaires_fotometria", ["fotometria"])


def downgrade() -> None:
    with op.batch_alter_table("luminaires") as batch_op:
        batch_op.drop_constraint("uq_luminaires_fotometria", type_="unique")
        batch_op.drop_constraint("fk_luminaires_led_type_id", type_="foreignkey")
        batch_op.drop_constraint("fk_luminaires_lente_id", type_="foreignkey")
        batch_op.drop_constraint("fk_luminaires_difusor_id", type_="foreignkey")
        batch_op.drop_constraint("fk_luminaires_gama_id", type_="foreignkey")
        batch_op.drop_column("photometric_path")
        batch_op.drop_column("fotometria")
        batch_op.drop_column("led_type_id")
        batch_op.drop_column("lente_id")
        batch_op.drop_column("difusor_id")
        batch_op.drop_column("gama_id")
