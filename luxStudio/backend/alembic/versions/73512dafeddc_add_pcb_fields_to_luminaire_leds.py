"""add_pcb_fields_to_luminaire_leds

Revision ID: 73512dafeddc
Revises: f2a3b4c5d6e7
Create Date: 2026-06-17 19:03:09.396759
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '73512dafeddc'
down_revision: Union[str, Sequence[str], None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('luminaire_leds', sa.Column('n_pcbs', sa.Integer(), nullable=True))
    op.add_column('luminaire_leds', sa.Column('n_leds_per_pcb', sa.Integer(), nullable=True))
    op.add_column('luminaire_leds', sa.Column('pcb_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('luminaire_leds', 'pcb_id')
    op.drop_column('luminaire_leds', 'n_leds_per_pcb')
    op.drop_column('luminaire_leds', 'n_pcbs')
