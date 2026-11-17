"""personal_info: preferred_locations and remote_ok (job search location preferences)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-17
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("personal_info", sa.Column("preferred_locations", JSONB(), nullable=True))
    op.add_column("personal_info", sa.Column("remote_ok", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("personal_info", "remote_ok")
    op.drop_column("personal_info", "preferred_locations")
