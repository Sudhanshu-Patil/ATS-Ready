"""cover_letters.length_limit / limit_unit: the user's own word or character cap

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-17
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cover_letters", sa.Column("length_limit", sa.Integer(), nullable=True))
    op.add_column("cover_letters", sa.Column("limit_unit", sa.String(10), nullable=True))


def downgrade() -> None:
    op.drop_column("cover_letters", "limit_unit")
    op.drop_column("cover_letters", "length_limit")
