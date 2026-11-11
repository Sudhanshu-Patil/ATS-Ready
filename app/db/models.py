"""
app/db/models.py
─────────────────
SQLAlchemy ORM models — all primary keys and foreign keys are UUID.

WHY UUID?
  - No sequential ID leakage (users can't guess job_id=2 belongs to someone else)
  - Safe to generate on the client or worker before inserting
  - Works naturally in distributed/sharded systems
  - `gen_random_uuid()` server default means Postgres generates it if Python doesn't

UUID STORAGE:
  We use PostgreSQL's native UUID type (not VARCHAR).
  `as_uuid=True` means Python receives actual uuid.UUID objects, not strings.
  SQLAlchemy handles the conversion automatically.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship


from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.db.base import Base
import uuid

def _now(): return datetime.utcnow()
def _uuid(): return uuid.uuid4()

from app.db.base import Base


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _now():
    return datetime.utcnow()


def _uuid():
    return uuid.uuid4()


# ─────────────────────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id                     = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email                  = Column(String(255), unique=True, nullable=False, index=True)
    full_name              = Column(String(200), nullable=True)

    # auth
    hashed_password        = Column(String(255), nullable=True)
    google_id              = Column(String(100), unique=True, nullable=True)
    github_id              = Column(String(100), unique=True, nullable=True)
    is_active              = Column(Boolean, default=True, nullable=False)
    is_verified            = Column(Boolean, default=False, nullable=False)

    # subscription — provider-neutral names (currently PayPal order id):
    # payment_customer_id     = the provider's customer reference
    # payment_subscription_id = the active subscription reference
    plan                    = Column(String(20), default="free", nullable=False)
    payment_customer_id     = Column(String(100), nullable=True)
    payment_subscription_id = Column(String(100), nullable=True)
    plan_expires_at         = Column(DateTime, nullable=True)

    created_at             = Column(DateTime, default=_now, nullable=False)
    updated_at             = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    personal_info    = relationship("PersonalInfo",   back_populates="user", uselist=False, cascade="all, delete-orphan")
    skills           = relationship("Skill",          back_populates="user", cascade="all, delete-orphan")
    projects         = relationship("Project",        back_populates="user", cascade="all, delete-orphan")
    work_experience  = relationship("WorkExperience", back_populates="user", cascade="all, delete-orphan")
    education        = relationship("Education",      back_populates="user", cascade="all, delete-orphan")
    job_applications = relationship("JobApplication", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User id={self.id} email={self.email!r} plan={self.plan!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# Personal Info
# ─────────────────────────────────────────────────────────────────────────────

class PersonalInfo(Base):
    __tablename__ = "personal_info"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id      = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    full_name    = Column(String(200), nullable=False)
    email        = Column(String(200), nullable=False)
    phone        = Column(String(50), nullable=True)
    location     = Column(String(200), nullable=True)
    linkedin     = Column(String(500), nullable=True)
    github       = Column(String(500), nullable=True)
    portfolio    = Column(String(500), nullable=True)
    professional_summary = Column(Text, nullable=True)
    updated_at   = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    user = relationship("User", back_populates="personal_info")


# ─────────────────────────────────────────────────────────────────────────────
# Skills
# ─────────────────────────────────────────────────────────────────────────────

class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = (
        Index("ix_skills_user_name", "user_id", "name", unique=True),
    )

    id               = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id          = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    name             = Column(String(100), nullable=False)
    category         = Column(String(50), nullable=False)
    proficiency      = Column(String(20), default="Intermediate")
    years_experience = Column(Float, default=0.0)
    keywords         = Column(JSONB, default=list)
    is_primary       = Column(Boolean, default=True)
    created_at       = Column(DateTime, default=_now, nullable=False)
    updated_at       = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    user = relationship("User", back_populates="skills")


# ─────────────────────────────────────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_user_featured", "user_id", "is_featured"),
    )

    id                = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id           = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    title             = Column(String(200), nullable=False)
    description       = Column(Text, nullable=False)
    short_description = Column(Text, nullable=True)
    tech_stack        = Column(JSONB, default=list)
    impact            = Column(Text, nullable=True)
    github_url        = Column(String(500), nullable=True)
    live_url          = Column(String(500), nullable=True)
    start_date        = Column(String(20), nullable=True)
    end_date          = Column(String(20), nullable=True)
    is_featured       = Column(Boolean, default=True)
    created_at        = Column(DateTime, default=_now, nullable=False)
    updated_at        = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    user    = relationship("User", back_populates="projects")
    bullets = relationship("ProjectBullet", back_populates="project", cascade="all, delete-orphan", lazy="selectin")


class ProjectBullet(Base):
    __tablename__ = "project_bullets"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    bullet     = Column(Text, nullable=False)
    keywords   = Column(JSONB, default=list)

    project = relationship("Project", back_populates="bullets")


# ─────────────────────────────────────────────────────────────────────────────
# Work Experience
# ─────────────────────────────────────────────────────────────────────────────

class WorkExperience(Base):
    __tablename__ = "work_experience"
    __table_args__ = (
        Index("ix_work_user_current", "user_id", "is_current"),
    )

    id          = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    company     = Column(String(200), nullable=False)
    role        = Column(String(200), nullable=False)
    location    = Column(String(100), nullable=True)
    start_date  = Column(String(20), nullable=False)
    end_date    = Column(String(20), nullable=True)
    is_current  = Column(Boolean, default=False)
    description = Column(Text, nullable=True)
    tech_stack  = Column(JSONB, default=list)
    created_at  = Column(DateTime, default=_now, nullable=False)
    updated_at  = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    user    = relationship("User", back_populates="work_experience")
    bullets = relationship("ExperienceBullet", back_populates="experience", cascade="all, delete-orphan", lazy="selectin")


class ExperienceBullet(Base):
    __tablename__ = "experience_bullets"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    experience_id = Column(UUID(as_uuid=True), ForeignKey("work_experience.id", ondelete="CASCADE"), nullable=False, index=True)
    bullet        = Column(Text, nullable=False)
    keywords      = Column(JSONB, default=list)
    impact_score  = Column(Float, default=5.0)

    experience = relationship("WorkExperience", back_populates="bullets")


# ─────────────────────────────────────────────────────────────────────────────
# Education
# ─────────────────────────────────────────────────────────────────────────────

class Education(Base):
    __tablename__ = "education"

    id                  = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id             = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    institution         = Column(String(200), nullable=False)
    degree              = Column(String(200), nullable=False)
    field               = Column(String(200), nullable=False)
    start_year          = Column(Integer, nullable=True)
    end_year            = Column(Integer, nullable=True)
    gpa                 = Column(String(10), nullable=True)
    honors              = Column(String(200), nullable=True)
    relevant_coursework = Column(JSONB, default=list)

    user = relationship("User", back_populates="education")


# ─────────────────────────────────────────────────────────────────────────────
# Job Applications
# ─────────────────────────────────────────────────────────────────────────────

class JobApplication(Base):
    __tablename__ = "job_applications"
    __table_args__ = (
        Index("ix_jobapp_user_created", "user_id", "created_at"),
    )

    id              = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id         = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    job_title       = Column(String(300), nullable=True)
    company         = Column(String(200), nullable=True)
    jd_url          = Column(String(1000), nullable=True)
    jd_text         = Column(Text, nullable=True)
    jd_parsed       = Column(JSONB, nullable=True)

    resume_s3_key   = Column(String(500), nullable=True)
    resume_filename = Column(String(255), nullable=True)
    resume_path     = Column(String(500), nullable=True)   # legacy

    ats_score       = Column(Float, nullable=True)
    ats_breakdown   = Column(JSONB, nullable=True)
    skills_matched  = Column(JSONB, nullable=True)
    skills_missing  = Column(JSONB, nullable=True)

    arq_job_id      = Column(String(100), nullable=True, index=True)
    status          = Column(String(20), default="pending")
    error_message   = Column(Text, nullable=True)

    created_at      = Column(DateTime, default=_now, nullable=False)
    updated_at      = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    user = relationship("User", back_populates="job_applications")


class CoverLetter(Base):
    __tablename__ = "cover_letters"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id     = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_app_id  = Column(UUID(as_uuid=True), ForeignKey("job_applications.id", ondelete="SET NULL"), nullable=True, index=True)

    job_title   = Column(String(300), nullable=True)
    company     = Column(String(200), nullable=True)
    jd_text     = Column(Text(), nullable=True)

    subject     = Column(String(500), nullable=True)
    body        = Column(Text(), nullable=False)
    word_count  = Column(Integer(), nullable=True)
    highlights  = Column(JSONB, default=list)
    tone        = Column(String(30), default="professional")

    created_at  = Column(DateTime, default=_now, nullable=False)

    user        = relationship("User", backref="cover_letters")


class InterviewPrep(Base):
    __tablename__ = "interview_prep"

    id                 = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id            = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_app_id         = Column(UUID(as_uuid=True), ForeignKey("job_applications.id", ondelete="SET NULL"), nullable=True, index=True)

    job_title          = Column(String(300), nullable=True)
    company            = Column(String(200), nullable=True)

    questions          = Column(JSONB, default=list)
    quick_tips         = Column(JSONB, default=list)
    red_flags_to_avoid = Column(JSONB, default=list)
    questions_to_ask   = Column(JSONB, default=list)

    created_at         = Column(DateTime, default=_now, nullable=False)

    user               = relationship("User", backref="interview_preps")
