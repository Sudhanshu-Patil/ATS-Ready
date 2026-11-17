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
import asyncio
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.ai_agent import ai_agent
from app.api.activity_routes import ensure_capacity, ensure_profile
from app.api.rate_limit import per_user_limit
from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import CoverLetter, InterviewPrep, User
from app.services import applications, credits, job_access, letter_limit
from app.services.cache_service import cache_service
from app.services.content_service import ProfileIncomplete, friendly_error
from app.services.metabase_service import metabase_service
from app.services.queue import enqueue
from app.services.usage import ensure_budget, mark_failed, record_usage, start_tally

content_router = APIRouter()
logger = logging.getLogger(__name__)

TONES = ("professional", "conversational", "enthusiastic")


# ── Request schemas ───────────────────────────────────────────────────────────

class CoverLetterRequest(BaseModel):
    jd_text:    str
    job_app_id: Optional[str] = None   # link to an existing resume job
    tone:       str = "professional"   # professional | conversational | enthusiastic
    limit:      Optional[int] = None   # the user's own cap, if the application has one
    limit_unit: str = "words"          # words | chars
    company:    Optional[str] = Field(default=None, max_length=200)   # when the posting does not name it

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


async def _enqueue_or_fail(db: AsyncSession, row, function: str, kind: Optional[str] = None, **kwargs) -> None:
    """Enqueue; if the queue is unreachable, don't leave a row 'pending' forever (and give the job's use back)."""
    try:
        await enqueue(function, **kwargs)
    except Exception:
        logger.exception("Could not enqueue %s", function)
        row.status, row.error = "failed", "The job queue is unavailable. Please try again."
        if kind:
            await credits.release(db, getattr(row, "application_id", None), kind)
        await db.commit()
        raise HTTPException(status_code=503, detail="The job queue is unavailable. Please try again.")


# ── Cover Letter endpoints ────────────────────────────────────────────────────

@content_router.post("/cover-letter", status_code=202,
                     dependencies=[Depends(per_user_limit("content", 10))])
async def generate_cover_letter(
    request: CoverLetterRequest,
    db: AsyncSession = Depends(get_db),
    # Pro/Team gate. No-op while BILLING_ENABLED=false.
    user: User = Depends(get_current_user),
):
    """
    Queue a personalized cover letter. Returns 202 immediately with an id;
    poll GET /api/activity (or GET /api/cover-letters/{id}) for the result.
    """
    _check_jd(request.jd_text)
    if request.tone not in TONES:
        raise HTTPException(status_code=422, detail="tone must be professional, conversational, or enthusiastic")
    if request.limit is not None:
        try:
            letter_limit.validate(request.limit_unit, request.limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    await ensure_profile(db, user.id)
    await ensure_capacity(db, user.id)
    job = await job_access.gate(db, user, "cover_letter", source="cover_letter", jd_text=request.jd_text)

    row = CoverLetter(
        user_id=user.id, application_id=job.id, jd_text=request.jd_text[:3000], body="",
        tone=request.tone, status="pending", created_at=datetime.utcnow(),
        length_limit=request.limit, limit_unit=request.limit_unit if request.limit else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    await _enqueue_or_fail(
        db, row, "generate_cover_letter_task", kind="cover_letter", application_id=str(job.id),
        letter_id=str(row.id), user_id=str(user.id), jd_text=request.jd_text,
        job_app_id=request.job_app_id, tone=request.tone,
        limit=request.limit, limit_unit=request.limit_unit if request.limit else None,
        company=(request.company or "").strip() or None,
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
            "length_limit": cl.length_limit,
            "limit_unit":  cl.limit_unit,
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
        "length_limit": cl.length_limit,
        "limit_unit":  cl.limit_unit,
        "status":     cl.status,
        "error":      cl.error,
        "created_at": str(cl.created_at),
    }


@content_router.post("/cover-letters/{letter_id}/retry", status_code=202,
                     dependencies=[Depends(per_user_limit("content", 10))])
async def retry_cover_letter(
    letter_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Re-run a failed cover letter with the job description saved on it."""
    cl = await _own_letter(db, letter_id, user)
    if cl.status != "failed" or not cl.jd_text:
        raise HTTPException(status_code=409, detail="Only failed cover letters with a saved job description can be retried")
    await ensure_capacity(db, user.id)
    job = await job_access.gate(db, user, "cover_letter", source="cover_letter", jd_text=cl.jd_text,
                                application_id=cl.application_id)
    cl.application_id = job.id
    cl.status, cl.error = "pending", None
    await db.commit()
    await _enqueue_or_fail(db, cl, "generate_cover_letter_task", kind="cover_letter", application_id=str(job.id),
                           letter_id=str(cl.id), user_id=str(user.id),
                           jd_text=job_access.stored_jd(job, cl.jd_text), job_app_id=None,
                           tone=cl.tone or "professional", limit=cl.length_limit, limit_unit=cl.limit_unit)
    return {"id": str(cl.id), "status": "pending"}


class CompanyAnswer(BaseModel):
    company: Optional[str] = Field(default=None, max_length=200)
    skip: bool = False                  # "write it without naming the company"


@content_router.post("/cover-letters/{letter_id}/company", status_code=202,
                     dependencies=[Depends(per_user_limit("content", 10))])
async def answer_company(
    letter_id: str,
    data: CompanyAnswer,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The user's answer to "which company is this letter for?". Resumes the waiting letter."""
    cl = await _own_letter(db, letter_id, user)
    company = (data.company or "").strip()
    if cl.status != "needs_input":
        raise HTTPException(status_code=409, detail="This cover letter is not waiting for a company name")
    if not company and not data.skip:
        raise HTTPException(status_code=422, detail="Enter the company name, or choose to skip it")
    await ensure_capacity(db, user.id)
    cl.status, cl.error = "pending", None
    await db.commit()
    await _enqueue_or_fail(db, cl, "generate_cover_letter_task", letter_id=str(cl.id), user_id=str(user.id),
                           jd_text=cl.jd_text, job_app_id=None, tone=cl.tone or "professional",
                           limit=cl.length_limit, limit_unit=cl.limit_unit,
                           company=company or None, company_skipped=not company,
                           application_id=str(cl.application_id) if cl.application_id else None)
    return {"id": str(cl.id), "status": "pending"}


class CoverLetterEdit(BaseModel):
    subject: Optional[str] = Field(default=None, max_length=500)
    body: str = Field(min_length=1, max_length=20000)


@content_router.patch("/cover-letters/{letter_id}")
async def edit_cover_letter(
    letter_id: str,
    data: CoverLetterEdit,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Save the user's edits. Downloads and copies then use this text."""
    cl = await _own_letter(db, letter_id, user)
    if cl.status != "done":
        raise HTTPException(status_code=409, detail="Only finished cover letters can be edited")
    cl.body = data.body.strip()
    if data.subject is not None:
        cl.subject = data.subject.strip()
    cl.word_count = len(cl.body.split())
    await db.commit()
    return {"id": str(cl.id), "subject": cl.subject, "body": cl.body, "word_count": cl.word_count}


def _safe_name(*parts: Optional[str]) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", "_".join(p for p in parts if p)).strip("_")[:60] or "cover_letter"


@content_router.get("/cover-letters/{letter_id}/download")
async def download_cover_letter(
    letter_id: str,
    format: str = "docx",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """The saved (possibly edited) letter as DOCX or PDF."""
    from app.services.documents import cover_letter_docx, cover_letter_pdf
    if format not in ("docx", "pdf"):
        raise HTTPException(status_code=422, detail="format must be docx or pdf")
    cl = await _own_letter(db, letter_id, user)
    if cl.status != "done":
        raise HTTPException(status_code=409, detail="This cover letter is not ready yet")
    if format == "pdf":
        data = await asyncio.to_thread(cover_letter_pdf, cl.subject or "", cl.body)
        media = "application/pdf"
    else:
        data = await asyncio.to_thread(cover_letter_docx, cl.subject or "", cl.body)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    name = f"cover_letter_{_safe_name(cl.company, cl.job_title)}.{format}"
    return Response(data, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}"'})


# ── LinkedIn referral request ─────────────────────────────────────────────────

class ReferralRequest(BaseModel):
    person_name: str = Field(default="", max_length=120)
    jd_text:     str = Field(default="", max_length=20000)
    job_url:     str = Field(default="", max_length=1000)


async def _track_referral(db: AsyncSession, user: User, request, application_id=None) -> None:
    """A referral request is a step in an application: put it on that job's timeline, dated now. The company
    comes from the posting's cached analysis or its own text; if neither names it, the app asks the user."""
    try:
        jd = request.jd_text.strip()
        cached = await cache_service.get_parsed_jd(jd)
        company, role = (cached or {}).get("company"), (cached or {}).get("job_title")
        if applications.is_unclear_company(company):
            hints = applications.extract_hints(jd[:600])
            company, role = hints["company"], role or hints["role"]
        person = request.person_name.strip()
        await applications.track(
            db, user.id, source="referral", kind="referral_request",
            summary="Drafted a referral request" + (f" to {person}" if person else ""), jd_text=jd,
            company=company, role=role, job_url=request.job_url.strip() or None, status="referral_requested",
            payload={"person": person} if person else None, application_id=application_id)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("Application tracking failed for referral (non-fatal)", exc_info=True)


@content_router.post("/referral-message",
                     dependencies=[Depends(per_user_limit("content", 10))])
async def referral_message(
    request: ReferralRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),     # outreach is part of the Pro writing tools
):
    """Draft a LinkedIn referral ask. One small LLM call, answered directly (not queued)."""
    if len(request.jd_text.strip()) < 100:
        raise HTTPException(status_code=422, detail="Paste the job description (min 100 characters)")
    await ensure_budget(db, user.id)
    job = await job_access.gate(db, user, "referral", source="referral", jd_text=request.jd_text,
                                jd_url=request.job_url.strip() or None)
    await db.commit()                                  # the use is counted before the model runs

    profile = await cache_service.get_profile(str(user.id))
    if not profile:
        profile = await metabase_service.get_full_profile_async(db, user.id)
        await cache_service.set_profile(str(user.id), profile)
    if not profile.get("personal"):
        raise HTTPException(status_code=400, detail=str(ProfileIncomplete(
            "Profile incomplete — fill in Personal Info in Metabase first.")))

    tally, started, ok = start_tally(), time.monotonic(), False
    try:
        result = await asyncio.wait_for(asyncio.to_thread(
            ai_agent.generate_referral_message, request.person_name.strip(), request.jd_text.strip(),
            request.job_url.strip(), profile), timeout=70)
        ok = True
        await credits.succeeded(db, job.id)
        await _track_referral(db, user, request, job.id)
        return result
    except asyncio.TimeoutError:
        mark_failed()
        await credits.release(db, job.id, "referral")
        await db.commit()
        raise HTTPException(status_code=503, detail="The AI service is busy right now. Please try again in a minute.")
    except Exception as exc:
        mark_failed()
        await credits.release(db, job.id, "referral")
        await db.commit()
        logger.exception("Referral message failed")
        raise HTTPException(status_code=503, detail=friendly_error(exc))
    finally:
        await record_usage(user.id, "referral", tally, started, ok and not tally["failed"])


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

@content_router.post("/interview-prep", status_code=202,
                     dependencies=[Depends(per_user_limit("content", 10))])
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
    job = await job_access.gate(db, user, "interview_prep", source="interview_prep", jd_text=request.jd_text)

    row = InterviewPrep(user_id=user.id, application_id=job.id, jd_text=request.jd_text[:3000], status="pending",
                        created_at=datetime.utcnow())
    db.add(row)
    await db.commit()
    await db.refresh(row)

    await _enqueue_or_fail(
        db, row, "generate_interview_prep_task", kind="interview_prep", application_id=str(job.id),
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


@content_router.post("/interview-preps/{prep_id}/retry", status_code=202,
                     dependencies=[Depends(per_user_limit("content", 10))])
async def retry_interview_prep(
    prep_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Re-run a failed interview prep with the job description saved on it."""
    prep = await _own_prep(db, prep_id, user)
    if prep.status != "failed" or not prep.jd_text:
        raise HTTPException(status_code=409, detail="Only failed sessions with a saved job description can be retried")
    await ensure_capacity(db, user.id)
    job = await job_access.gate(db, user, "interview_prep", source="interview_prep", jd_text=prep.jd_text,
                                application_id=prep.application_id)
    prep.application_id = job.id
    prep.status, prep.error = "pending", None
    await db.commit()
    await _enqueue_or_fail(db, prep, "generate_interview_prep_task", kind="interview_prep",
                           application_id=str(job.id), prep_id=str(prep.id), user_id=str(user.id),
                           jd_text=job_access.stored_jd(job, prep.jd_text), job_app_id=None)
    return {"id": str(prep.id), "status": "pending"}


@content_router.delete("/interview-preps/{prep_id}")
async def delete_interview_prep(
    prep_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await db.delete(await _own_prep(db, prep_id, user))
    await db.commit()
    return {"message": "Deleted"}
