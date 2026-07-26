"""add organizations and organization_tramos

Revision ID: 9a8b7c6d5e4f
Revises: f2b156ef1546
Create Date: 2026-07-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a8b7c6d5e4f'
down_revision: Union[str, Sequence[str], None] = 'f2b156ef1546'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('organizations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_organizations_user_id'), 'organizations', ['user_id'], unique=False)

    op.create_table('organization_tramos',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organization_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('config_json', sa.Text(), nullable=True),
        sa.Column('config_sha256', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_organization_tramos_organization_id'), 'organization_tramos', ['organization_id'], unique=False)
    op.create_index(op.f('ix_organization_tramos_config_sha256'), 'organization_tramos', ['config_sha256'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_organization_tramos_config_sha256'), table_name='organization_tramos')
    op.drop_index(op.f('ix_organization_tramos_organization_id'), table_name='organization_tramos')
    op.drop_table('organization_tramos')
    op.drop_index(op.f('ix_organizations_user_id'), table_name='organizations')
    op.drop_table('organizations')
