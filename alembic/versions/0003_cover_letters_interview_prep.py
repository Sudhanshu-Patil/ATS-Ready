"""Add cover_letters and interview_prep tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-23
"""
from typing import Sequence, Union
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── cover_letters ─────────────────────────────────────────────────────────
    op.create_table(
        "cover_letters",
        sa.Column("id",              postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id",         postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_app_id",      postgresql.UUID(as_uuid=True), nullable=True),  # optional link to a resume job

        # Job info (denormalised for easy display)
        sa.Column("job_title",       sa.String(300), nullable=True),
        sa.Column("company",         sa.String(200), nullable=True),
        sa.Column("jd_text",         sa.Text(), nullable=True),

        # AI output
        sa.Column("subject",         sa.String(500), nullable=True),
        sa.Column("body",            sa.Text(), nullable=False),
        sa.Column("word_count",      sa.Integer(), nullable=True),
        sa.Column("highlights",      postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
        sa.Column("tone",            sa.String(30), server_default="professional"),

        sa.Column("created_at",      sa.DateTime(), nullable=False),

        sa.ForeignKeyConstraint(["user_id"],    ["users.id"],            ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_app_id"], ["job_applications.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cover_letters_user_id",    "cover_letters", ["user_id"])
    op.create_index("ix_cover_letters_job_app_id", "cover_letters", ["job_app_id"])

    # ── interview_prep ────────────────────────────────────────────────────────
    op.create_table(
        "interview_prep",
        sa.Column("id",                  postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id",             postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_app_id",          postgresql.UUID(as_uuid=True), nullable=True),

        sa.Column("job_title",           sa.String(300), nullable=True),
        sa.Column("company",             sa.String(200), nullable=True),

        # Full AI output stored as JSONB
        sa.Column("questions",           postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
        sa.Column("quick_tips",          postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
        sa.Column("red_flags_to_avoid",  postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
        sa.Column("questions_to_ask",    postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),

        sa.Column("created_at",          sa.DateTime(), nullable=False),

        sa.ForeignKeyConstraint(["user_id"],    ["users.id"],            ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_app_id"], ["job_applications.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_interview_prep_user_id",    "interview_prep", ["user_id"])
    op.create_index("ix_interview_prep_job_app_id", "interview_prep", ["job_app_id"])


def downgrade() -> None:
    op.drop_table("interview_prep")
    op.drop_table("cover_letters")
