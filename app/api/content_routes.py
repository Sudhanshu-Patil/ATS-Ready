"""
app/api/content_routes.py
──────────────────────────
Cover letter and interview prep endpoints.

Both follow the same pattern as resume generation:
  POST → triggers AI generation → returns result + saves to DB
  GET  → list history
  GET /{id} → single item

Generation is synchronous (not ARQ) because:
  - Cover letters: ~5-10s, acceptable to wait
  - Interview prep: ~10-15s, acceptable to wait
  - Both are user-initiated single actions, not bulk operations

If latency becomes an issue, these can be moved to ARQ later.
"""
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.api.plan_limits import check_cover_letter_access
from app.db.database import get_db
from app.db.models import CoverLetter, InterviewPrep, JobApplication, User
from app.services.metabase_service import metabase_service
from app.services.cache_service import cache_service
from app.agents.ai_agent import ai_agent
from app.models.schemas import ParsedJD

content_router = APIRouter()
logger = logging.getLogger(__name__)


# ── Request schemas ───────────────────────────────────────────────────────────

class CoverLetterRequest(BaseModel):
    jd_text:    str
    job_app_id: Optional[str] = None   # link to an existing resume job
    tone:       str = "professional"   # professional | conversational | enthusiastic

    class Config:
        json_schema_extra = {
            "example": {
                "jd_text": "We are looking for a Senior Python Engineer...",
                "tone": "professional",
            }
        }


class InterviewPrepRequest(BaseModel):
    jd_text:    str
    job_app_id: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "jd_text": "We are looking for a Senior Python Engineer...",
            }
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_profile_and_jd(
    jd_text: str,
    user: User,
    db: AsyncSession,
    job_app_id: Optional[str] = None,
):
    """
    Shared setup: fetch candidate profile + parse JD.
    If job_app_id is provided, reuse already-parsed JD data.
    """
    # Get candidate profile (with cache)
    cached = await cache_service.get_profile(str(user.id))
    if cached:
        profile = cached
    else:
        profile = await metabase_service.get_full_profile_async(db, user.id)
        await cache_service.set_profile(str(user.id), profile)

    if not profile.get("personal"):
        raise HTTPException(
            status_code=400,
            detail="Profile incomplete — fill in Personal Info in Metabase first."
        )

    # Try to reuse parsed JD from existing job application
    parsed_jd = None
    job_app = None

    if job_app_id:
        try:
            result = await db.execute(
                select(JobApplication).where(
                    JobApplication.id == uuid.UUID(job_app_id),
                    JobApplication.user_id == user.id,
                )
            )
            job_app = result.scalar_one_or_none()
            if job_app and job_app.jd_parsed:
                parsed_jd = ParsedJD(**job_app.jd_parsed)
                logger.info("Reusing parsed JD from job_app %s", job_app_id)
        except Exception:
            pass

    # Parse JD fresh if not reused
    if not parsed_jd:
        cached_parse = await cache_service.get_parsed_jd(jd_text)
        if cached_parse:
            parsed_jd = ParsedJD(**cached_parse)
        else:
            parsed_jd = ai_agent.parse_jd(jd_text)
            await cache_service.set_parsed_jd(jd_text, parsed_jd.model_dump())

    # Get tailored resume content for context
    # (Either from existing job_app or generate fresh)
    tailored = {}
    if job_app and job_app.ats_breakdown:
        # Use the stored tailored content if available
        tailored = job_app.jd_parsed or {}
    else:
        tailored = ai_agent.tailor_resume(parsed_jd, profile, None)

    return profile, parsed_jd, tailored, job_app


# ── Cover Letter endpoints ────────────────────────────────────────────────────

@content_router.post("/cover-letter")
async def generate_cover_letter(
    request: CoverLetterRequest,
    db: AsyncSession = Depends(get_db),
    # Pro/Team gate — was silently unenforced (the dependency existed but was
    # never wired here), letting free users generate cover letters.
    # No-op while BILLING_ENABLED=false.
    user: User = Depends(check_cover_letter_access),
):
    """
    Generate a personalized cover letter.

    Provide the job description text. Optionally link to an existing
    resume job (job_app_id) to reuse the already-parsed JD.

    Takes ~5-10 seconds. Returns the full cover letter immediately.
    """
    if len(request.jd_text.strip()) < 100:
        raise HTTPException(status_code=422, detail="Job description too short (min 100 chars)")

    if request.tone not in ("professional", "conversational", "enthusiastic"):
        raise HTTPException(status_code=422, detail="tone must be professional, conversational, or enthusiastic")

    logger.info("Generating cover letter for user %s", user.id)

    profile, parsed_jd, tailored, job_app = await _get_profile_and_jd(
        request.jd_text, user, db, request.job_app_id
    )

    # Generate cover letter
    result = ai_agent.generate_cover_letter(parsed_jd, profile, tailored, request.tone)

    # Save to DB
    cover_letter = CoverLetter(
        user_id    = user.id,
        job_app_id = job_app.id if job_app else None,
        job_title  = parsed_jd.job_title,
        company    = parsed_jd.company,
        jd_text    = request.jd_text[:3000],
        subject    = result.get("subject"),
        body       = result.get("body", ""),
        word_count = result.get("word_count"),
        highlights = result.get("highlights", []),
        tone       = request.tone,
        created_at = datetime.utcnow(),
    )
    db.add(cover_letter)
    await db.commit()
    await db.refresh(cover_letter)

    return {
        "id":         str(cover_letter.id),
        "job_title":  parsed_jd.job_title,
        "company":    parsed_jd.company,
        "subject":    result.get("subject"),
        "body":       result.get("body"),
        "word_count": result.get("word_count"),
        "highlights": result.get("highlights", []),
        "tone":       request.tone,
        "created_at": str(cover_letter.created_at),
    }


@content_router.get("/cover-letters")
async def list_cover_letters(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all cover letters for the current user."""
    result = await db.execute(
        select(CoverLetter)
        .where(CoverLetter.user_id == user.id)
        .order_by(CoverLetter.created_at.desc())
    )
    letters = result.scalars().all()
    return [
        {
            "id":         str(cl.id),
            "job_title":  cl.job_title,
            "company":    cl.company,
            "subject":    cl.subject,
            "word_count": cl.word_count,
            "tone":       cl.tone,
            "created_at": str(cl.created_at),
        }
        for cl in letters
    ]


@content_router.get("/cover-letters/{letter_id}")
async def get_cover_letter(
    letter_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get full cover letter content."""
    result = await db.execute(
        select(CoverLetter).where(
            CoverLetter.id == uuid.UUID(letter_id),
            CoverLetter.user_id == user.id,
        )
    )
    cl = result.scalar_one_or_none()
    if not cl:
        raise HTTPException(status_code=404, detail="Cover letter not found")
    return {
        "id":         str(cl.id),
        "job_title":  cl.job_title,
        "company":    cl.company,
        "subject":    cl.subject,
        "body":       cl.body,
        "word_count": cl.word_count,
        "highlights": cl.highlights,
        "tone":       cl.tone,
        "created_at": str(cl.created_at),
    }


@content_router.delete("/cover-letters/{letter_id}")
async def delete_cover_letter(
    letter_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CoverLetter).where(
            CoverLetter.id == uuid.UUID(letter_id),
            CoverLetter.user_id == user.id,
        )
    )
    cl = result.scalar_one_or_none()
    if not cl:
        raise HTTPException(status_code=404, detail="Cover letter not found")
    await db.delete(cl)
    await db.commit()
    return {"message": "Deleted"}


# ── Interview Prep endpoints ──────────────────────────────────────────────────

@content_router.post("/interview-prep")
async def generate_interview_prep(
    request: InterviewPrepRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Generate tailored interview questions and model answers.

    Returns 10 questions across behavioral, technical, situational,
    and cultural categories — all using the candidate's real experience.

    Takes ~10-15 seconds. Returns the full prep kit immediately.
    """
    if len(request.jd_text.strip()) < 100:
        raise HTTPException(status_code=422, detail="Job description too short (min 100 chars)")

    logger.info("Generating interview prep for user %s", user.id)

    profile, parsed_jd, tailored, job_app = await _get_profile_and_jd(
        request.jd_text, user, db, request.job_app_id
    )

    # Generate interview prep
    result = ai_agent.generate_interview_prep(parsed_jd, profile, tailored)

    # Save to DB
    prep = InterviewPrep(
        user_id            = user.id,
        job_app_id         = job_app.id if job_app else None,
        job_title          = parsed_jd.job_title,
        company            = parsed_jd.company,
        questions          = result.get("questions", []),
        quick_tips         = result.get("quick_tips", []),
        red_flags_to_avoid = result.get("red_flags_to_avoid", []),
        questions_to_ask   = result.get("questions_to_ask", []),
        created_at         = datetime.utcnow(),
    )
    db.add(prep)
    await db.commit()
    await db.refresh(prep)

    return {
        "id":                  str(prep.id),
        "job_title":           parsed_jd.job_title,
        "company":             parsed_jd.company,
        "questions":           result.get("questions", []),
        "quick_tips":          result.get("quick_tips", []),
        "red_flags_to_avoid":  result.get("red_flags_to_avoid", []),
        "questions_to_ask":    result.get("questions_to_ask", []),
        "created_at":          str(prep.created_at),
    }


@content_router.get("/interview-preps")
async def list_interview_preps(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all interview prep sessions."""
    result = await db.execute(
        select(InterviewPrep)
        .where(InterviewPrep.user_id == user.id)
        .order_by(InterviewPrep.created_at.desc())
    )
    preps = result.scalars().all()
    return [
        {
            "id":            str(p.id),
            "job_title":     p.job_title,
            "company":       p.company,
            "question_count": len(p.questions or []),
            "created_at":    str(p.created_at),
        }
        for p in preps
    ]


@content_router.get("/interview-preps/{prep_id}")
async def get_interview_prep(
    prep_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get full interview prep content."""
    result = await db.execute(
        select(InterviewPrep).where(
            InterviewPrep.id == uuid.UUID(prep_id),
            InterviewPrep.user_id == user.id,
        )
    )
    prep = result.scalar_one_or_none()
    if not prep:
        raise HTTPException(status_code=404, detail="Interview prep not found")
    return {
        "id":                  str(prep.id),
        "job_title":           prep.job_title,
        "company":             prep.company,
        "questions":           prep.questions,
        "quick_tips":          prep.quick_tips,
        "red_flags_to_avoid":  prep.red_flags_to_avoid,
        "questions_to_ask":    prep.questions_to_ask,
        "created_at":          str(prep.created_at),
    }


@content_router.delete("/interview-preps/{prep_id}")
async def delete_interview_prep(
    prep_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(InterviewPrep).where(
            InterviewPrep.id == uuid.UUID(prep_id),
            InterviewPrep.user_id == user.id,
        )
    )
    prep = result.scalar_one_or_none()
    if not prep:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(prep)
    await db.commit()
    return {"message": "Deleted"}
