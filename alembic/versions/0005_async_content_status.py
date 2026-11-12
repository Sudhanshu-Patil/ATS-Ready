"""Add status/error to cover_letters and interview_prep

Cover letters and interview prep now run in the arq worker (like resumes), so
rows exist before the content does. Existing rows are complete: 'done'.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-12
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("cover_letters", "interview_prep")


def upgrade() -> None:
    for t in TABLES:
        op.add_column(t, sa.Column("status", sa.String(20), nullable=False, server_default="done"))
        op.add_column(t, sa.Column("error", sa.Text(), nullable=True))


def downgrade() -> None:
    for t in TABLES:
        op.drop_column(t, "error")
        op.drop_column(t, "status")
