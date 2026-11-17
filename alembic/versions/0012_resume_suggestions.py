"""resume_suggestions: per job description, the technical gaps and which were applied

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-17
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resume_suggestions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("jd_hash", sa.String(64), nullable=False),
        sa.Column("job_title", sa.String(300), nullable=True),
        sa.Column("items", JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_resume_suggestions_user_id", "resume_suggestions", ["user_id"])
    op.create_index("ix_resume_suggestions_user_jd", "resume_suggestions", ["user_id", "jd_hash"], unique=True)


def downgrade() -> None:
    op.drop_table("resume_suggestions")
