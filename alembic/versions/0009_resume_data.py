"""job_applications.resume_data: inputs of the generated resume, so a PDF can be rendered later

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-17
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("job_applications", sa.Column("resume_data", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("job_applications", "resume_data")
