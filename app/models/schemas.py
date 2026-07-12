"""
app/models/schemas.py
──────────────────────
Pydantic v2 request/response models.

CHANGES vs. original:
  - GenerateResumeResponse now returns a job_id + status (async pattern).
  - JobStatusResponse added for status polling.
  - HttpUrl used for jd_url (validates URL format before enqueuing).
  - All models use model_config instead of inner Config class (Pydantic v2).
"""
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, HttpUrl, field_validator

# ─────────────────────────────────────────────────────────────────────────────
# JD Parsing
# ─────────────────────────────────────────────────────────────────────────────

class ParsedJD(BaseModel):
    """Structured output from AI JD analysis (Stage 1)."""
    job_title:         str
    company:           Optional[str] = None
    location:          Optional[str] = None
    job_type:          Optional[str] = None
    seniority:         Optional[str] = None
    industry:          Optional[str] = None
    required_skills:   List[str] = []
    preferred_skills:  List[str] = []
    responsibilities:  List[str] = []
    qualifications:    List[str] = []
    keywords:          List[str] = []
    raw_text:          Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# ATS Scoring
# ─────────────────────────────────────────────────────────────────────────────

class ATSBreakdown(BaseModel):
    total_score:       float
    keyword_score:     float
    skills_score:      float
    action_verb_score: float
    format_score:      float
    matched_keywords:  List[str] = []
    missing_keywords:  List[str] = []
    matched_skills:    List[str] = []
    missing_skills:    List[str] = []
    suggestions:       List[str] = []


# ─────────────────────────────────────────────────────────────────────────────
# API: Generate Resume
# ─────────────────────────────────────────────────────────────────────────────

class GenerateResumeRequest(BaseModel):
    """
    POST /api/generate-resume

    Provide EITHER jd_url OR jd_text (not both, not neither).
    `emphasis` is an optional list of keywords the AI should prioritize.
    """
    jd_url:   Optional[str] = None   # validated as URL by the route
    jd_text:  Optional[str] = None
    emphasis: Optional[List[str]] = None

    @field_validator("jd_text")
    @classmethod
    def jd_text_not_too_short(cls, v):
        if v is not None and len(v.strip()) < 50:
            raise ValueError("jd_text must be at least 50 characters")
        if v is not None and len(v) > 50_000:
            raise ValueError("jd_text too long — max 50,000 characters")
        return v

    @field_validator("emphasis")
    @classmethod
    def limit_emphasis(cls, v):
        if v is None:
            return v
        if len(v) > 20:
            raise ValueError("Max 20 emphasis keywords")
        return [kw[:60] for kw in v]   # cap each keyword length


class GenerateResumeResponse(BaseModel):
    """
    Returned immediately (HTTP 202) after enqueueing the background job.
    The frontend should then poll GET /api/jobs/{job_id}/status.
    """
    job_id:  str
    status:  str = "pending"         # pending | running | done | failed
    message: str = ""


class JobStatusResponse(BaseModel):
    """
    Returned by GET /api/jobs/{job_id}/status.
    `result` is populated only when status == "done".
    """
    job_id: str
    status: str                      # pending | running | done | failed
    error:  Optional[str] = None     # present when status == "failed"
    result: Optional[Dict[str, Any]] = None   # full resume result


# ─────────────────────────────────────────────────────────────────────────────
# Metabase Schemas
# ─────────────────────────────────────────────────────────────────────────────

class SkillCreate(BaseModel):
    name:             str
    category:         str
    proficiency:      str = "Intermediate"
    years_experience: float = 0.0
    keywords:         List[str] = []
    is_primary:       bool = True


class SkillOut(BaseModel):
    model_config = model_config = {"from_attributes": True}

    id:               uuid.UUID
    name:             str
    category:         str
    proficiency:      str
    years_experience: float
    is_primary:       bool


class BulletCreate(BaseModel):
    bullet:   str
    keywords: List[str] = []


class ExperienceBulletCreate(BulletCreate):
    impact_score: float = 5.0


class ProjectCreate(BaseModel):
    title:             str
    description:       str
    short_description: Optional[str] = None
    tech_stack:        List[str] = []
    impact:            Optional[str] = None
    github_url:        Optional[str] = None
    live_url:          Optional[str] = None
    start_date:        Optional[str] = None
    end_date:          Optional[str] = None
    is_featured:       bool = True
    bullets:           List[BulletCreate] = []


class ProjectOut(BaseModel):
    model_config = {"from_attributes": True}

    id:          int
    title:       str
    tech_stack:  List[str]
    is_featured: bool


class WorkExperienceCreate(BaseModel):
    company:     str
    role:        str
    location:    Optional[str] = None
    start_date:  str
    end_date:    Optional[str] = None
    is_current:  bool = False
    description: Optional[str] = None
    tech_stack:  List[str] = []
    bullets:     List[ExperienceBulletCreate] = []


class WorkExperienceOut(BaseModel):
    model_config = {"from_attributes": True}

    id:         int
    company:    str
    role:       str
    start_date: str
    end_date:   Optional[str] = None
    is_current: bool


class PersonalInfoUpdate(BaseModel):
    full_name:            str
    email:                str
    phone:                Optional[str] = None
    location:             Optional[str] = None
    linkedin:             Optional[str] = None
    github:               Optional[str] = None
    portfolio:            Optional[str] = None
    professional_summary: Optional[str] = None


class JobApplicationOut(BaseModel):
    model_config = {"from_attributes": True}

    id:          int
    job_title:   Optional[str]
    company:     Optional[str]
    ats_score:   Optional[float]
    status:      str
