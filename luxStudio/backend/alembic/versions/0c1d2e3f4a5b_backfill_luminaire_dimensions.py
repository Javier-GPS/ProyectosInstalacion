"""Backfill dimension FKs for existing luminaires.

Revision ID: 0c1d2e3f4a5b
Revises: 9b3c4d5e6f70
Create Date: 2026-06-04 10:15:00.000000

Para los LDTs ya presentes en la tabla ``luminaires`` (típicamente los
siete del repositorio de demo, pero también cualquier fila que se haya
cargado por la UI admin), esta migración:

1. Siembra las tablas ``gamas`` y ``lentes`` con los valores únicos de
   las columnas legadas ``type`` y ``optic_family``.
2. Siembra un difusor sentinela ``__LEGACY__`` y crea las
   ``valid_combinations`` correspondientes (sin ``led_type`` — los LDTs
   legacy no lo declaran; el importer del xlsx los rellenará más
   tarde con el valor real).
3. Rellena ``gama_id``, ``difusor_id`` y ``lente_id`` de cada
   ``Luminaire`` buscando el id de la dimensión correspondiente.
4. Rellena ``fotometria`` con el nombre de archivo sin extensión y
   ``photometric_path`` con el valor actual de ``ldt_path``.
5. Marca ``gama_id``, ``difusor_id`` y ``lente_id`` como NOT NULL.
   ``led_type_id`` queda NULL hasta que se complete el import del xlsx.
"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0c1d2e3f4a5b"
down_revision: Union[str, Sequence[str], None] = "9b3c4d5e6f70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LEGACY_DIFUSOR = "__LEGACY__"


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Sembrar gamas y lentes desde los valores únicos legacy.
    for (name,) in conn.exec_driver_sql(
        "SELECT DISTINCT type FROM luminaires WHERE type IS NOT NULL"
    ).fetchall():
        conn.exec_driver_sql(
            "INSERT OR IGNORE INTO gamas (name, created_at) VALUES (?, CURRENT_TIMESTAMP)",
            (name,),
        )
    for (name,) in conn.exec_driver_sql(
        "SELECT DISTINCT optic_family FROM luminaires WHERE optic_family IS NOT NULL"
    ).fetchall():
        conn.exec_driver_sql(
            "INSERT OR IGNORE INTO lentes (name, created_at) VALUES (?, CURRENT_TIMESTAMP)",
            (name,),
        )

    # Difusor sentinela para los legacy.
    conn.exec_driver_sql(
        "INSERT OR IGNORE INTO difusores (name, created_at) VALUES (?, CURRENT_TIMESTAMP)",
        (LEGACY_DIFUSOR,),
    )

    # 2. Crear las valid_combinations correspondientes. La combinación
    #    se forma con (gama, __LEGACY__, lente, led_type=NULL) por cada
    #    par (gama, lente) presente en luminaires.
    conn.exec_driver_sql(
        """
        INSERT OR IGNORE INTO valid_combinations
            (gama_id, difusor_id, lente_id, led_type_id, created_at)
        SELECT g.id,
               (SELECT id FROM difusores WHERE name = ?),
               l.id,
               NULL,
               CURRENT_TIMESTAMP
        FROM (SELECT DISTINCT type, optic_family FROM luminaires) AS src
        JOIN gamas g ON g.name = src.type
        JOIN lentes l ON l.name = src.optic_family
        """,
        (LEGACY_DIFUSOR,),
    )

    # 3. Rellenar las FKs de cada Luminaire.
    conn.exec_driver_sql(
        """
        UPDATE luminaires
        SET gama_id = (SELECT id FROM gamas WHERE gamas.name = luminaires.type)
        WHERE gama_id IS NULL
        """
    )
    conn.exec_driver_sql(
        """
        UPDATE luminaires
        SET lente_id = (SELECT id FROM lentes WHERE lentes.name = luminaires.optic_family)
        WHERE lente_id IS NULL
        """
    )
    conn.exec_driver_sql(
        """
        UPDATE luminaires
        SET difusor_id = (SELECT id FROM difusores WHERE name = ?)
        WHERE difusor_id IS NULL
        """,
        (LEGACY_DIFUSOR,),
    )

    # 4. Rellenar ``fotometria`` (filename stem) y ``photometric_path``.
    rows = conn.exec_driver_sql(
        "SELECT id, ldt_path FROM luminaires WHERE fotometria IS NULL"
    ).fetchall()
    for lum_id, ldt_path in rows:
        if not ldt_path:
            continue
        # ``Path`` (no PurePosixPath) porque el ``ldt_path`` puede contener
        # separadores ``\`` en Windows; queremos quedarnos solo con el
        # nombre de archivo sin extensión.
        stem = Path(ldt_path).stem
        conn.exec_driver_sql(
            "UPDATE luminaires SET fotometria = ?, photometric_path = ? WHERE id = ?",
            (stem, ldt_path, lum_id),
        )

    # 5. Marcar FKs como NOT NULL. ``led_type_id`` queda NULL a propósito.
    with op.batch_alter_table("luminaires") as batch_op:
        batch_op.alter_column("gama_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("difusor_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("lente_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("luminaires") as batch_op:
        batch_op.alter_column("lente_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("difusor_id", existing_type=sa.Integer(), nullable=True)
        batch_op.alter_column("gama_id", existing_type=sa.Integer(), nullable=True)
    conn = op.get_bind()
    conn.exec_driver_sql(
        "UPDATE luminaires SET gama_id = NULL, lente_id = NULL, difusor_id = NULL, "
        "fotometria = NULL, photometric_path = NULL"
    )
    conn.exec_driver_sql("DELETE FROM valid_combinations")
    conn.exec_driver_sql("DELETE FROM gamas")
    conn.exec_driver_sql("DELETE FROM lentes")
    conn.exec_driver_sql("DELETE FROM difusores WHERE name = ?", (LEGACY_DIFUSOR,))
