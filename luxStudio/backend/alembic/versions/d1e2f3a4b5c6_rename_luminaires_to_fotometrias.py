"""Rename luminaires → fotometrias, ldt_path → photometric_path

Revision ID: d1e2f3a4b5c6
Revises: 0c1d2e3f4a5b
Create Date: 2026-06-04
"""

from alembic import op
import sqlalchemy as sa


revision = "d1e2f3a4b5c6"
down_revision = "0c1d2e3f4a5b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Rename column ldt_path → photometric_path (do first, before table rename)
    op.execute("ALTER TABLE luminaires RENAME COLUMN ldt_path TO photometric_path")

    # 2. Rename table luminaires → fotometrias
    op.execute("ALTER TABLE luminaires RENAME TO fotometrias")


def downgrade() -> None:
    # 1. Rename table back
    op.execute("ALTER TABLE fotometrias RENAME TO luminaires")

    # 2. Rename column back
    op.execute("ALTER TABLE luminaires RENAME COLUMN photometric_path TO ldt_path")
