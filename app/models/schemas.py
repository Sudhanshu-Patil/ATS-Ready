"""
Pydantic Schemas
-----------------
Request/response models and internal data structures.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, HttpUrl


# ─── JD Parsing ───────────────────────────────────────────────────────────────

class ParsedJD(BaseModel):
    """Structured output from AI JD analysis."""
    job_title: str
    company: Optional[str] = None
    location: Optional[str] = None
    job_type: Optional[str] = None
    seniority: Optional[str] = None
    industry: Optional[str] = None
    required_skills: List[str] = []
    preferred_skills: List[str] = []
    responsibilities: List[str] = []
    qualifications: List[str] = []
    keywords: List[str] = []
    raw_text: Optional[str] = None


# ─── ATS Scoring ──────────────────────────────────────────────────────────────

class ATSBreakdown(BaseModel):
    total_score: float
    keyword_score: float
    skills_score: float
    action_verb_score: float
    format_score: float
    matched_keywords: List[str] = []
    missing_keywords: List[str] = []
    matched_skills: List[str] = []
    missing_skills: List[str] = []
    suggestions: List[str] = []


# ─── API Request/Response ─────────────────────────────────────────────────────

class GenerateResumeRequest(BaseModel):
    jd_url: Optional[str] = None
    jd_text: Optional[str] = None
    emphasis: Optional[List[str]] = None  # keywords to emphasize


class GenerateResumeResponse(BaseModel):
    job_id: int
    job_title: str
    company: Optional[str] = None
    ats_score: float
    ats_breakdown: ATSBreakdown
    resume_path: str
    download_url: str
    skills_matched: List[str] = []
    skills_missing: List[str] = []
    message: str


# ─── Metabase Schemas ─────────────────────────────────────────────────────────

class SkillCreate(BaseModel):
    name: str
    category: str
    proficiency: str = "Intermediate"
    years_experience: float = 0.0
    keywords: List[str] = []
    is_primary: bool = True


class SkillOut(BaseModel):
    id: int
    name: str
    category: str
    proficiency: str
    years_experience: float
    is_primary: bool

    class Config:
        from_attributes = True


class BulletCreate(BaseModel):
    bullet: str
    keywords: List[str] = []


class ExperienceBulletCreate(BulletCreate):
    impact_score: float = 5.0


class ProjectCreate(BaseModel):
    title: str
    description: str
    short_description: Optional[str] = None
    tech_stack: List[str] = []
    impact: Optional[str] = None
    github_url: Optional[str] = None
    live_url: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_featured: bool = True
    bullets: List[BulletCreate] = []


class ProjectOut(BaseModel):
    id: int
    title: str
    tech_stack: List[str]
    is_featured: bool

    class Config:
        from_attributes = True


class WorkExperienceCreate(BaseModel):
    company: str
    role: str
    location: Optional[str] = None
    start_date: str
    end_date: Optional[str] = None
    is_current: bool = False
    description: Optional[str] = None
    tech_stack: List[str] = []
    bullets: List[ExperienceBulletCreate] = []


class WorkExperienceOut(BaseModel):
    id: int
    company: str
    role: str
    start_date: str
    end_date: Optional[str] = None
    is_current: bool

    class Config:
        from_attributes = True


class PersonalInfoUpdate(BaseModel):
    full_name: str
    email: str
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    professional_summary: Optional[str] = None


class JobApplicationOut(BaseModel):
    id: int
    job_title: Optional[str]
    company: Optional[str]
    ats_score: Optional[float]
    resume_path: Optional[str]

    class Config:
        from_attributes = True
