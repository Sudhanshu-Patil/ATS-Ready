"""applications + timeline, assistant requests, persona graph

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _user():
    return sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


def _now(name):
    return sa.Column(name, sa.DateTime(), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "applications", sa.Column("id", UUID(as_uuid=True), primary_key=True), _user(),
        sa.Column("company", sa.String(200)), sa.Column("role", sa.String(300)), sa.Column("job_url", sa.String(1000)),
        sa.Column("jd_hash", sa.String(64)), sa.Column("jd_text", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="interested"),
        sa.Column("source", sa.String(30)), sa.Column("applied_at", sa.DateTime()),
        sa.Column("follow_up_at", sa.DateTime()), sa.Column("notes", sa.Text()),
        sa.Column("needs", JSONB(), nullable=False, server_default="[]"), _now("created_at"), _now("updated_at"))
    op.create_index("ix_applications_user_id", "applications", ["user_id"])
    op.create_index("ix_applications_user_jd", "applications", ["user_id", "jd_hash"])

    op.create_table(
        "application_events", sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("application_id", UUID(as_uuid=True), sa.ForeignKey("applications.id", ondelete="CASCADE"),
                  nullable=False),
        _user(), sa.Column("kind", sa.String(30), nullable=False), sa.Column("summary", sa.String(300)),
        sa.Column("payload", JSONB()), _now("occurred_at"), _now("created_at"))
    op.create_index("ix_application_events_application_id", "application_events", ["application_id"])
    op.create_index("ix_application_events_user_id", "application_events", ["user_id"])

    op.create_table(
        "assistant_requests", sa.Column("id", UUID(as_uuid=True), primary_key=True), _user(),
        sa.Column("application_id", UUID(as_uuid=True), sa.ForeignKey("applications.id", ondelete="SET NULL")),
        sa.Column("client_request_id", sa.String(64), nullable=False), sa.Column("jd_text", sa.Text()),
        sa.Column("company", sa.String(200)), sa.Column("job_title", sa.String(300)),
        sa.Column("questions", JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"), sa.Column("error", sa.Text()),
        _now("created_at"))
    op.create_index("ix_assistant_requests_user_id", "assistant_requests", ["user_id"])
    op.create_index("ix_assistant_requests_application_id", "assistant_requests", ["application_id"])
    op.create_index("ix_assistant_requests_client", "assistant_requests", ["user_id", "client_request_id"], unique=True)

    op.create_table(
        "persona_nodes", sa.Column("id", UUID(as_uuid=True), primary_key=True), _user(),
        sa.Column("kind", sa.String(20), nullable=False), sa.Column("key", sa.String(200), nullable=False),
        sa.Column("label", sa.String(300), nullable=False), sa.Column("data", JSONB()),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
        sa.Column("uses", sa.Integer(), nullable=False, server_default="0"), sa.Column("source", sa.String(20)),
        _now("created_at"), _now("updated_at"))
    op.create_index("ix_persona_nodes_user_id", "persona_nodes", ["user_id"])
    op.create_index("ix_persona_nodes_user_kind_key", "persona_nodes", ["user_id", "kind", "key"], unique=True)

    op.create_table(
        "persona_edges", sa.Column("id", UUID(as_uuid=True), primary_key=True), _user(),
        sa.Column("src", UUID(as_uuid=True), sa.ForeignKey("persona_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dst", UUID(as_uuid=True), sa.ForeignKey("persona_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation", sa.String(30), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1"))
    op.create_index("ix_persona_edges_user_id", "persona_edges", ["user_id"])
    op.create_index("ix_persona_edges_src", "persona_edges", ["src"])
    op.create_index("ix_persona_edges_dst", "persona_edges", ["dst"])
    op.create_index("ix_persona_edges_unique", "persona_edges", ["src", "dst", "relation"], unique=True)


def downgrade() -> None:
    for t in ("persona_edges", "persona_nodes", "assistant_requests", "application_events", "applications"):
        op.drop_table(t)
