"""Replace integer PKs with UUID

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-22

Since we're in development with only seed data, the cleanest approach
is to drop all tables and recreate them with UUID primary keys.
Run `python scripts/seed_metabase.py` after applying this migration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop all in reverse dependency order (FKs first)
    op.drop_table("job_applications")
    op.drop_table("education")
    op.drop_table("experience_bullets")
    op.drop_table("work_experience")
    op.drop_table("project_bullets")
    op.drop_table("projects")
    op.drop_table("skills")
    op.drop_table("personal_info")
    op.drop_table("users")

    # Recreate with UUID PKs
    op.create_table(
        "users",
        sa.Column("id",                     postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("email",                  sa.String(255), nullable=False),
        sa.Column("full_name",              sa.String(200), nullable=True),
        sa.Column("hashed_password",        sa.String(255), nullable=True),
        sa.Column("google_id",              sa.String(100), nullable=True),
        sa.Column("github_id",              sa.String(100), nullable=True),
        sa.Column("is_active",              sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_verified",            sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("plan",                   sa.String(20), nullable=False, server_default="free"),
        sa.Column("stripe_customer_id",     sa.String(100), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(100), nullable=True),
        sa.Column("plan_expires_at",        sa.DateTime(), nullable=True),
        sa.Column("created_at",             sa.DateTime(), nullable=False),
        sa.Column("updated_at",             sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email",     "users", ["email"],     unique=True)
    op.create_index("ix_users_google_id", "users", ["google_id"], unique=True)
    op.create_index("ix_users_github_id", "users", ["github_id"], unique=True)

    op.create_table(
        "personal_info",
        sa.Column("id",                   postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id",              postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("full_name",            sa.String(200), nullable=False),
        sa.Column("email",                sa.String(200), nullable=False),
        sa.Column("phone",                sa.String(50), nullable=True),
        sa.Column("location",             sa.String(200), nullable=True),
        sa.Column("linkedin",             sa.String(500), nullable=True),
        sa.Column("github",               sa.String(500), nullable=True),
        sa.Column("portfolio",            sa.String(500), nullable=True),
        sa.Column("professional_summary", sa.Text(), nullable=True),
        sa.Column("updated_at",           sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "skills",
        sa.Column("id",               postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id",          postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name",             sa.String(100), nullable=False),
        sa.Column("category",         sa.String(50), nullable=False),
        sa.Column("proficiency",      sa.String(20), server_default="Intermediate"),
        sa.Column("years_experience", sa.Float(), server_default="0.0"),
        sa.Column("keywords",         postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
        sa.Column("is_primary",       sa.Boolean(), server_default="true"),
        sa.Column("created_at",       sa.DateTime(), nullable=False),
        sa.Column("updated_at",       sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_skills_user_id",   "skills", ["user_id"])
    op.create_index("ix_skills_user_name", "skills", ["user_id", "name"], unique=True)

    op.create_table(
        "projects",
        sa.Column("id",                postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id",           postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title",             sa.String(200), nullable=False),
        sa.Column("description",       sa.Text(), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("tech_stack",        postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
        sa.Column("impact",            sa.Text(), nullable=True),
        sa.Column("github_url",        sa.String(500), nullable=True),
        sa.Column("live_url",          sa.String(500), nullable=True),
        sa.Column("start_date",        sa.String(20), nullable=True),
        sa.Column("end_date",          sa.String(20), nullable=True),
        sa.Column("is_featured",       sa.Boolean(), server_default="true"),
        sa.Column("created_at",        sa.DateTime(), nullable=False),
        sa.Column("updated_at",        sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projects_user_id",       "projects", ["user_id"])
    op.create_index("ix_projects_user_featured", "projects", ["user_id", "is_featured"])

    op.create_table(
        "project_bullets",
        sa.Column("id",         postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bullet",     sa.Text(), nullable=False),
        sa.Column("keywords",   postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_bullets_project_id", "project_bullets", ["project_id"])

    op.create_table(
        "work_experience",
        sa.Column("id",          postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id",     postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company",     sa.String(200), nullable=False),
        sa.Column("role",        sa.String(200), nullable=False),
        sa.Column("location",    sa.String(100), nullable=True),
        sa.Column("start_date",  sa.String(20), nullable=False),
        sa.Column("end_date",    sa.String(20), nullable=True),
        sa.Column("is_current",  sa.Boolean(), server_default="false"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tech_stack",  postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
        sa.Column("created_at",  sa.DateTime(), nullable=False),
        sa.Column("updated_at",  sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_experience_user_id",      "work_experience", ["user_id"])
    op.create_index("ix_work_experience_user_current", "work_experience", ["user_id", "is_current"])

    op.create_table(
        "experience_bullets",
        sa.Column("id",            postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("experience_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bullet",        sa.Text(), nullable=False),
        sa.Column("keywords",      postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
        sa.Column("impact_score",  sa.Float(), server_default="5.0"),
        sa.ForeignKeyConstraint(["experience_id"], ["work_experience.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experience_bullets_experience_id", "experience_bullets", ["experience_id"])

    op.create_table(
        "education",
        sa.Column("id",                  postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id",             postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution",         sa.String(200), nullable=False),
        sa.Column("degree",              sa.String(200), nullable=False),
        sa.Column("field",               sa.String(200), nullable=False),
        sa.Column("start_year",          sa.Integer(), nullable=True),
        sa.Column("end_year",            sa.Integer(), nullable=True),
        sa.Column("gpa",                 sa.String(10), nullable=True),
        sa.Column("honors",              sa.String(200), nullable=True),
        sa.Column("relevant_coursework", postgresql.JSONB(astext_type=sa.Text()), server_default="[]"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_education_user_id", "education", ["user_id"])

    op.create_table(
        "job_applications",
        sa.Column("id",              postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id",         postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_title",       sa.String(300), nullable=True),
        sa.Column("company",         sa.String(200), nullable=True),
        sa.Column("jd_url",          sa.String(1000), nullable=True),
        sa.Column("jd_text",         sa.Text(), nullable=True),
        sa.Column("jd_parsed",       postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("resume_s3_key",   sa.String(500), nullable=True),
        sa.Column("resume_filename", sa.String(255), nullable=True),
        sa.Column("resume_path",     sa.String(500), nullable=True),
        sa.Column("ats_score",       sa.Float(), nullable=True),
        sa.Column("ats_breakdown",   postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("skills_matched",  postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("skills_missing",  postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("arq_job_id",      sa.String(100), nullable=True),
        sa.Column("status",          sa.String(20), server_default="pending"),
        sa.Column("error_message",   sa.Text(), nullable=True),
        sa.Column("created_at",      sa.DateTime(), nullable=False),
        sa.Column("updated_at",      sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_applications_user_id",      "job_applications", ["user_id"])
    op.create_index("ix_job_applications_user_created", "job_applications", ["user_id", "created_at"])
    op.create_index("ix_job_applications_arq_job_id",   "job_applications", ["arq_job_id"])


def downgrade() -> None:
    # Downgrade just drops back to integer PKs via migration 0001
    # Easiest: drop everything and let 0001 recreate
    op.drop_table("job_applications")
    op.drop_table("education")
    op.drop_table("experience_bullets")
    op.drop_table("work_experience")
    op.drop_table("project_bullets")
    op.drop_table("projects")
    op.drop_table("skills")
    op.drop_table("personal_info")
    op.drop_table("users")
