"""Rename stripe_* user columns to provider-neutral payment_* names

The billing integration moved from Stripe to Razorpay. Naming the columns
after the concept (payment provider's customer/subscription reference)
instead of the vendor means the next provider switch needs no migration.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-13
"""
from typing import Sequence, Union
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "stripe_customer_id", new_column_name="payment_customer_id")
    op.alter_column("users", "stripe_subscription_id", new_column_name="payment_subscription_id")


def downgrade() -> None:
    op.alter_column("users", "payment_customer_id", new_column_name="stripe_customer_id")
    op.alter_column("users", "payment_subscription_id", new_column_name="stripe_subscription_id")
