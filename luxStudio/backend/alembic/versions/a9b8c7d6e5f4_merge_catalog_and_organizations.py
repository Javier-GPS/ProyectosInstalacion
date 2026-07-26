"""Merge the catalog repair and organizations migration branches."""

from typing import Sequence, Union


revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, Sequence[str], None] = ("7e8f9a0b1c2", "9a8b7c6d5e4f")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
