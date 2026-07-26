"""add_gama_pcbs_table

Revision ID: 393004ff84ac
Revises: 55211cce0b31
Create Date: 2026-06-17 23:35:58.719892

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '393004ff84ac'
down_revision: Union[str, Sequence[str], None] = '55211cce0b31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('gama_pcbs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('gama_id', sa.Integer(), nullable=False),
    sa.Column('pcb_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['gama_id'], ['gamas.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['pcb_id'], ['pcbs.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('gama_id', 'pcb_id', name='uq_gama_pcbs')
    )


def downgrade() -> None:
    op.drop_table('gama_pcbs')
