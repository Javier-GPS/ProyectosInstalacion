"""Repair Salvi maintenance-factor metadata after catalog imports.

Revision ID: 7e8f9a0b1c2
Revises: 6d7e8f9a0b1c
Create Date: 2026-07-13

Salvi LDT files contain raw (initial) photometry, so their maintenance
factor at source is 1.0.  The folder importer kept writing 0.85 after the
original data migration had run, which cancelled a user-selected MF of
0.85 in the luminance calculation.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "7e8f9a0b1c2"
down_revision: Union[str, Sequence[str], None] = "6d7e8f9a0b1c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE fotometrias
        SET mf_origen = 1.0
        WHERE manufacturer_id IN (
            SELECT id FROM manufacturers WHERE UPPER(name) = 'SALVI'
        )
        """
    )


def downgrade() -> None:
    # Data correction: restoring 0.85 would knowingly reintroduce the bug.
    pass
