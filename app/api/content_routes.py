"""
app/api/content_routes.py
──────────────────────────
Cover letter and interview prep endpoints.

Same pattern as resume generation:
  POST → creates a pending row, enqueues an arq job, returns 202 + id
  GET  → list history / single item (status: pending|running|done|failed)

Generation runs in the arq worker (app/worker/tasks.py), so the user can leave
the page or open other tabs; progress is visible via GET /api/activity.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.activity_routes import ensure_capacity, ensure_profile
from app.api.dependencies import get_current_user
from app.api.plan_limits import check_cover_letter_access
from app.db.database import get_db
from app.db.models import CoverLetter, InterviewPrep, User
from app.services.queue import enqueue

content_router = APIRouter()
logger = logging.getLogger(__name__)

TONES = ("professional", "conversational", "enthusiastic")


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

def _check_jd(jd_text: str) -> None:
    if len(jd_text.strip()) < 100:
        raise HTTPException(status_code=422, detail="Job description too short (min 100 chars)")


async def _enqueue_or_fail(db: AsyncSession, row, function: str, **kwargs) -> None:
    """Enqueue; if the queue is unreachable, don't leave a row 'pending' forever."""
    try:
        await enqueue(function, **kwargs)
    except Exception:
        logger.exception("Could not enqueue %s", function)
        row.status, row.error = "failed", "The job queue is unavailable. Please try again."
        await db.commit()
        raise HTTPException(status_code=503, detail="The job queue is unavailable. Please try again.")


# ── Cover Letter endpoints ────────────────────────────────────────────────────

@content_router.post("/cover-letter", status_code=202)
async def generate_cover_letter(
    request: CoverLetterRequest,
    db: AsyncSession = Depends(get_db),
    # Pro/Team gate. No-op while BILLING_ENABLED=false.
    user: User = Depends(check_cover_letter_access),
):
    """
    Queue a personalized cover letter. Returns 202 immediately with an id;
    poll GET /api/activity (or GET /api/cover-letters/{id}) for the result.
    """
    _check_jd(request.jd_text)
    if request.tone not in TONES:
        raise HTTPException(status_code=422, detail="tone must be professional, conversational, or enthusiastic")
    await ensure_profile(db, user.id)
    await ensure_capacity(db, user.id)

    row = CoverLetter(
        user_id=user.id, jd_text=request.jd_text[:3000], body="",
        tone=request.tone, status="pending", created_at=datetime.utcnow(),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    await _enqueue_or_fail(
        db, row, "generate_cover_letter_task",
        letter_id=str(row.id), user_id=str(user.id), jd_text=request.jd_text,
        job_app_id=request.job_app_id, tone=request.tone,
    )
    logger.info("Queued cover letter %s for user %s", row.id, user.id)
    return {"id": str(row.id), "status": "pending"}


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
    return [
        {
            "id":         str(cl.id),
            "job_title":  cl.job_title,
            "company":    cl.company,
            "subject":    cl.subject,
            "word_count": cl.word_count,
            "tone":       cl.tone,
            "status":     cl.status,
            "error":      cl.error,
            "created_at": str(cl.created_at),
        }
        for cl in result.scalars().all()
    ]


async def _own_letter(db: AsyncSession, letter_id: str, user: User) -> CoverLetter:
    try:
        lid = uuid.UUID(letter_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Cover letter not found")
    cl = (await db.execute(
        select(CoverLetter).where(CoverLetter.id == lid, CoverLetter.user_id == user.id)
    )).scalar_one_or_none()
    if not cl:
        raise HTTPException(status_code=404, detail="Cover letter not found")
    return cl


@content_router.get("/cover-letters/{letter_id}")
async def get_cover_letter(
    letter_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get full cover letter content."""
    cl = await _own_letter(db, letter_id, user)
    return {
        "id":         str(cl.id),
        "job_title":  cl.job_title,
        "company":    cl.company,
        "subject":    cl.subject,
        "body":       cl.body,
        "word_count": cl.word_count,
        "highlights": cl.highlights,
        "tone":       cl.tone,
        "status":     cl.status,
        "error":      cl.error,
        "created_at": str(cl.created_at),
    }


@content_router.delete("/cover-letters/{letter_id}")
async def delete_cover_letter(
    letter_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await db.delete(await _own_letter(db, letter_id, user))
    await db.commit()
    return {"message": "Deleted"}


# ── Interview Prep endpoints ──────────────────────────────────────────────────

@content_router.post("/interview-prep", status_code=202)
async def generate_interview_prep(
    request: InterviewPrepRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Queue tailored interview questions and model answers (10 questions across
    behavioral, technical, situational and cultural categories, using the
    candidate's real experience). Returns 202 immediately with an id.
    """
    _check_jd(request.jd_text)
    await ensure_profile(db, user.id)
    await ensure_capacity(db, user.id)

    row = InterviewPrep(user_id=user.id, status="pending", created_at=datetime.utcnow())
    db.add(row)
    await db.commit()
    await db.refresh(row)

    await _enqueue_or_fail(
        db, row, "generate_interview_prep_task",
        prep_id=str(row.id), user_id=str(user.id), jd_text=request.jd_text,
        job_app_id=request.job_app_id,
    )
    logger.info("Queued interview prep %s for user %s", row.id, user.id)
    return {"id": str(row.id), "status": "pending"}


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
    return [
        {
            "id":             str(p.id),
            "job_title":      p.job_title,
            "company":        p.company,
            "question_count": len(p.questions or []),
            "status":         p.status,
            "error":          p.error,
            "created_at":     str(p.created_at),
        }
        for p in result.scalars().all()
    ]


async def _own_prep(db: AsyncSession, prep_id: str, user: User) -> InterviewPrep:
    try:
        pid = uuid.UUID(prep_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Interview prep not found")
    prep = (await db.execute(
        select(InterviewPrep).where(InterviewPrep.id == pid, InterviewPrep.user_id == user.id)
    )).scalar_one_or_none()
    if not prep:
        raise HTTPException(status_code=404, detail="Interview prep not found")
    return prep


@content_router.get("/interview-preps/{prep_id}")
async def get_interview_prep(
    prep_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get full interview prep content."""
    prep = await _own_prep(db, prep_id, user)
    return {
        "id":                  str(prep.id),
        "job_title":           prep.job_title,
        "company":             prep.company,
        "questions":           prep.questions,
        "quick_tips":          prep.quick_tips,
        "red_flags_to_avoid":  prep.red_flags_to_avoid,
        "questions_to_ask":    prep.questions_to_ask,
        "status":              prep.status,
        "error":               prep.error,
        "created_at":          str(prep.created_at),
    }


@content_router.delete("/interview-preps/{prep_id}")
async def delete_interview_prep(
    prep_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await db.delete(await _own_prep(db, prep_id, user))
    await db.commit()
    return {"message": "Deleted"}
