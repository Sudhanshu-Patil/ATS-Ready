"""interview_prep.jd_text, so failed runs can be retried

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-12
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("interview_prep", sa.Column("jd_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("interview_prep", "jd_text")
