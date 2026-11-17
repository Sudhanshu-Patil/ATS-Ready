"""credits, payments, referrals; jobs know what they have paid for

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("credits_job", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("credits_resume", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("referral_code", sa.String(16), nullable=True))
    op.add_column("users", sa.Column("referred_by_id", UUID(as_uuid=True),
                                     sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
    op.add_column("users", sa.Column("email_canonical", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("signup_granted", sa.Boolean(), nullable=False, server_default="false"))
    op.create_index("ix_users_referral_code", "users", ["referral_code"], unique=True)
    op.create_index("ix_users_email_canonical", "users", ["email_canonical"])

    op.add_column("applications", sa.Column("unlock_level", sa.String(10), nullable=False, server_default="none"))
    op.add_column("applications", sa.Column("unlocked_at", sa.DateTime(), nullable=True))
    op.add_column("applications", sa.Column("usage", JSONB(), nullable=False, server_default="{}"))
    for table in ("job_applications", "cover_letters", "interview_prep"):
        op.add_column(table, sa.Column("application_id", UUID(as_uuid=True),
                                       sa.ForeignKey("applications.id", ondelete="SET NULL"), nullable=True))
        op.create_index(f"ix_{table}_application_id", table, ["application_id"])

    op.create_table(
        "credit_ledger", sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False), sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(20), nullable=False),
        sa.Column("application_id", UUID(as_uuid=True), sa.ForeignKey("applications.id", ondelete="SET NULL")),
        sa.Column("payment_id", UUID(as_uuid=True)),
        sa.Column("idempotency_key", sa.String(120), nullable=False, unique=True),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_credit_ledger_user_id", "credit_ledger", ["user_id"])

    op.create_table(
        "payments", sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(12), nullable=False),
        sa.Column("provider_order_id", sa.String(100), nullable=False, unique=True),
        sa.Column("provider_payment_id", sa.String(100), unique=True),
        sa.Column("pack_id", sa.String(20), nullable=False), sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="created"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("paid_at", sa.DateTime()))
    op.create_index("ix_payments_user_id", "payments", ["user_id"])

    op.create_table(
        "referrals", sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("referrer_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("referee_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("rewarded_at", sa.DateTime()))
    op.create_index("ix_referrals_referrer_id", "referrals", ["referrer_id"])

    # Existing accounts get a canonical email now; their signup grant is given on first sign-in
    # (credits.grant_signup), so nothing is credited here.
    op.execute("UPDATE users SET email_canonical = lower(email) WHERE email_canonical IS NULL")


def downgrade() -> None:
    op.drop_table("referrals")
    op.drop_table("payments")
    op.drop_table("credit_ledger")
    for table in ("job_applications", "cover_letters", "interview_prep"):
        op.drop_index(f"ix_{table}_application_id", table_name=table)
        op.drop_column(table, "application_id")
    for col in ("usage", "unlocked_at", "unlock_level"):
        op.drop_column("applications", col)
    op.drop_index("ix_users_email_canonical", table_name="users")
    op.drop_index("ix_users_referral_code", table_name="users")
    for col in ("signup_granted", "email_canonical", "referred_by_id", "referral_code", "credits_resume", "credits_job"):
        op.drop_column("users", col)
