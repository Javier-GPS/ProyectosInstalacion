"""add_pcb_descripcion

Revision ID: 55211cce0b31
Revises: 73512dafeddc
Create Date: 2026-06-17 19:40:53.623303

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '55211cce0b31'
down_revision: Union[str, Sequence[str], None] = '73512dafeddc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pcbs', sa.Column('pcb_descripcion', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('pcbs', 'pcb_descripcion')
