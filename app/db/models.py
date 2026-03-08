"""
SQLite Metabase — stores your personal skills, projects, experience.
Think of it as your personal knowledge base that the AI agent queries.
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float,
    DateTime, Boolean, JSON, ForeignKey
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from app.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ─── ORM Models ────────────────────────────────────────────────────────────────

class Skill(Base):
    """A technical or soft skill you possess."""
    __tablename__ = "skills"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)       # e.g., "Python"
    category = Column(String(50), nullable=False)                  # e.g., "Programming Language"
    proficiency = Column(String(20), default="Intermediate")       # Beginner/Intermediate/Expert
    years_experience = Column(Float, default=0.0)
    keywords = Column(JSON, default=list)                          # aliases: ["py", "python3"]
    is_primary = Column(Boolean, default=True)                     # highlight in resume?
    created_at = Column(DateTime, default=datetime.utcnow)


class Project(Base):
    """A project you've built or contributed to."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)                     # full description
    short_description = Column(Text, nullable=True)                # 1-liner for resume
    tech_stack = Column(JSON, default=list)                        # ["Python", "FastAPI", "PostgreSQL"]
    impact = Column(Text, nullable=True)                           # quantified results
    github_url = Column(String(500), nullable=True)
    live_url = Column(String(500), nullable=True)
    start_date = Column(String(20), nullable=True)
    end_date = Column(String(20), nullable=True)
    is_featured = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # bullet points for resume
    bullets = relationship("ProjectBullet", back_populates="project", cascade="all, delete")


class ProjectBullet(Base):
    """Individual bullet points for a project (resume line items)."""
    __tablename__ = "project_bullets"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"))
    bullet = Column(Text, nullable=False)
    keywords = Column(JSON, default=list)   # keywords this bullet covers
    project = relationship("Project", back_populates="bullets")


class WorkExperience(Base):
    """Your work history."""
    __tablename__ = "work_experience"

    id = Column(Integer, primary_key=True, index=True)
    company = Column(String(200), nullable=False)
    role = Column(String(200), nullable=False)
    location = Column(String(100), nullable=True)
    start_date = Column(String(20), nullable=False)
    end_date = Column(String(20), nullable=True)          # None = current
    is_current = Column(Boolean, default=False)
    description = Column(Text, nullable=True)
    tech_stack = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)

    bullets = relationship("ExperienceBullet", back_populates="experience", cascade="all, delete")


class ExperienceBullet(Base):
    """Individual bullet points for a work experience role."""
    __tablename__ = "experience_bullets"

    id = Column(Integer, primary_key=True, index=True)
    experience_id = Column(Integer, ForeignKey("work_experience.id"))
    bullet = Column(Text, nullable=False)
    keywords = Column(JSON, default=list)
    impact_score = Column(Float, default=5.0)   # 1-10, higher = more impactful
    experience = relationship("WorkExperience", back_populates="bullets")


class Education(Base):
    """Your educational background."""
    __tablename__ = "education"

    id = Column(Integer, primary_key=True, index=True)
    institution = Column(String(200), nullable=False)
    degree = Column(String(200), nullable=False)
    field = Column(String(200), nullable=False)
    start_year = Column(Integer, nullable=True)
    end_year = Column(Integer, nullable=True)
    gpa = Column(String(10), nullable=True)
    honors = Column(String(200), nullable=True)
    relevant_coursework = Column(JSON, default=list)


class PersonalInfo(Base):
    """Your personal/contact information."""
    __tablename__ = "personal_info"

    id = Column(Integer, primary_key=True)
    full_name = Column(String(200), nullable=False)
    email = Column(String(200), nullable=False)
    phone = Column(String(50), nullable=True)
    location = Column(String(200), nullable=True)
    linkedin = Column(String(500), nullable=True)
    github = Column(String(500), nullable=True)
    portfolio = Column(String(500), nullable=True)
    professional_summary = Column(Text, nullable=True)   # base summary, AI will tailor
    updated_at = Column(DateTime, default=datetime.utcnow)


class JobApplication(Base):
    """Tracks generated resumes and their ATS scores."""
    __tablename__ = "job_applications"

    id = Column(Integer, primary_key=True, index=True)
    job_title = Column(String(300), nullable=True)
    company = Column(String(200), nullable=True)
    jd_url = Column(String(1000), nullable=True)
    jd_text = Column(Text, nullable=True)
    jd_parsed = Column(JSON, nullable=True)          # structured JD from AI
    resume_path = Column(String(500), nullable=True)  # path to generated .docx
    ats_score = Column(Float, nullable=True)
    ats_breakdown = Column(JSON, nullable=True)
    skills_matched = Column(JSON, nullable=True)
    skills_missing = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# ─── DB helpers ────────────────────────────────────────────────────────────────

def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
