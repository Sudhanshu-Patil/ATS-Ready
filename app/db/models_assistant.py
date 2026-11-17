"""Application tracking, the application-question assistant and the persona graph.

Re-exported from app.db.models so `from app.db.models import Application` works like every other model.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


def _now():
    return datetime.utcnow()


def _uuid():
    return uuid.uuid4()


APPLICATION_STATUSES = ("interested", "applied", "referral_requested", "interviewing", "offer", "rejected", "withdrawn")


class Application(Base):
    """One job the user is going after, however it started (resume, cover letter, referral, assistant, manual)."""
    __tablename__ = "applications"
    __table_args__ = (Index("ix_applications_user_jd", "user_id", "jd_hash"),)

    id           = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id      = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company      = Column(String(200), nullable=True)           # None until known (see `needs`)
    role         = Column(String(300), nullable=True)
    job_url      = Column(String(1000), nullable=True)
    jd_hash      = Column(String(64), nullable=True)
    jd_text      = Column(Text, nullable=True)                   # truncated copy, so questions can be answered later
    status       = Column(String(20), default="interested", nullable=False)
    source       = Column(String(30), nullable=True)             # what created it
    applied_at   = Column(DateTime, nullable=True)               # when the user applied (their date, editable)
    follow_up_at = Column(DateTime, nullable=True)
    notes        = Column(Text, nullable=True)
    needs        = Column(JSONB, nullable=False, default=list)   # fields still to ask the user: ["company", "role"]
    created_at   = Column(DateTime, default=_now, nullable=False)
    updated_at   = Column(DateTime, default=_now, onupdate=_now, nullable=False)


class ApplicationEvent(Base):
    """Timeline entry. occurred_at is when the USER did it (when they asked), not when a job finished."""
    __tablename__ = "application_events"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id        = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind           = Column(String(30), nullable=False)   # created|resume|cover_letter|referral_request|questions|status|note|follow_up
    summary        = Column(String(300), nullable=True)
    payload        = Column(JSONB, nullable=True)
    occurred_at    = Column(DateTime, default=_now, nullable=False)
    created_at     = Column(DateTime, default=_now, nullable=False)


class AssistantRequest(Base):
    """A batch of application questions. Stored before any work starts and filled in by the worker, so a refresh,
    a dropped connection or a closed tab never loses it; client_request_id makes a retried submit idempotent."""
    __tablename__ = "assistant_requests"
    __table_args__ = (Index("ix_assistant_requests_client", "user_id", "client_request_id", unique=True),)

    id                = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id           = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    application_id    = Column(UUID(as_uuid=True), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True, index=True)
    client_request_id = Column(String(64), nullable=False)
    jd_text           = Column(Text, nullable=True)
    company           = Column(String(200), nullable=True)
    job_title         = Column(String(300), nullable=True)
    # [{id, question, answer, status: pending|done|needs_input|skipped|failed, topic, limit, limit_unit,
    #   needs: {field, label, hint}, approved: bool}]
    questions         = Column(JSONB, nullable=False, default=list)
    status            = Column(String(20), default="pending", nullable=False)   # pending|running|done|failed
    error             = Column(Text, nullable=True)
    created_at        = Column(DateTime, default=_now, nullable=False)


class PersonaNode(Base):
    """What the assistant has learned about the user. kind: fact (notice period, salary...), story (an answer the
    user approved), skill, topic, target (roles/skills they keep applying for), style (how they write)."""
    __tablename__ = "persona_nodes"
    __table_args__ = (Index("ix_persona_nodes_user_kind_key", "user_id", "kind", "key", unique=True),)

    id         = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id    = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind       = Column(String(20), nullable=False)
    key        = Column(String(200), nullable=False)          # normalised identity within the kind
    label      = Column(String(300), nullable=False)
    data       = Column(JSONB, nullable=True)
    weight     = Column(Float, default=1.0, nullable=False)
    uses       = Column(Integer, default=0, nullable=False)
    source     = Column(String(20), nullable=True)            # user | approved_answer | application | system
    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)


class PersonaEdge(Base):
    __tablename__ = "persona_edges"
    __table_args__ = (Index("ix_persona_edges_unique", "src", "dst", "relation", unique=True),)

    id       = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id  = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    src      = Column(UUID(as_uuid=True), ForeignKey("persona_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    dst      = Column(UUID(as_uuid=True), ForeignKey("persona_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    relation = Column(String(30), nullable=False)             # about | mentions
    weight   = Column(Float, default=1.0, nullable=False)
