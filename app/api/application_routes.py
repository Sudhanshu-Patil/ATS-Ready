"""Application tracker: every job the user is going after, with a dated timeline, follow-ups and back-questions."""
import asyncio
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.ai_agent import ai_agent
from app.api.dependencies import get_current_user
from app.api.rate_limit import per_user_limit
from app.config import settings
from app.db.database import get_db
from app.db.models import (APPLICATION_STATUSES, Application, ApplicationEvent, AssistantRequest, CoverLetter,
                           InterviewPrep, JobApplication, User)
from app.services import applications, credits, pricing
from app.services.usage import ensure_budget, mark_failed, record_usage, start_tally
from app.services.scraper import ScraperError, scraper_service, validate_public_url
from app.services.cache_service import cache_service
from app.services.metabase_service import metabase_service

application_router = APIRouter(tags=["Applications"])


def _iso(d: Optional[datetime]) -> Optional[str]:
    return d.isoformat() if d else None


def _dict(a: Application) -> dict:
    return {"id": str(a.id), "company": a.company, "role": a.role, "job_url": a.job_url, "status": a.status,
            "source": a.source, "applied_at": _iso(a.applied_at), "follow_up_at": _iso(a.follow_up_at),
            "notes": a.notes, "needs": a.needs or [], "created_at": _iso(a.created_at), "updated_at": _iso(a.updated_at),
            "has_jd": bool(a.jd_text), "unlock_level": a.unlock_level or "none"}


async def _own(db: AsyncSession, application_id: str, user: User) -> Application:
    try:
        aid = uuid.UUID(application_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Application not found")
    a = (await db.execute(select(Application).where(
        Application.id == aid, Application.user_id == user.id))).scalar_one_or_none()
    if a is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return a


def _when(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        raise HTTPException(status_code=422, detail="Dates must look like 2026-11-18")
    if d > datetime.utcnow() + timedelta(days=1):
        raise HTTPException(status_code=422, detail="That date is in the future")
    return d


class ApplicationIn(BaseModel):
    company: Optional[str] = Field(default=None, max_length=200)
    role: Optional[str] = Field(default=None, max_length=300)
    job_url: Optional[str] = Field(default=None, max_length=1000)
    jd_text: Optional[str] = Field(default=None, max_length=50000)      # a posting to start a job from
    status: Optional[str] = None
    applied_at: Optional[str] = None            # the date the user applied (their own date)
    follow_up_at: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=4000)
    clear_follow_up: bool = False


@application_router.get("/applications")
async def list_applications(status: Optional[str] = None, db: AsyncSession = Depends(get_db),
                            user: User = Depends(get_current_user)):
    q = select(Application).where(Application.user_id == user.id).order_by(Application.updated_at.desc())
    if status:
        q = q.where(Application.status == status)
    rows = (await db.execute(q.limit(500))).scalars().all()
    return {"items": [_dict(a) for a in rows], "statuses": list(APPLICATION_STATUSES)}


@application_router.get("/applications/attention")
async def get_attention(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """What needs the user: missing company/role (the back-question popup), follow-ups due, and jobs they asked about
    but never said whether they applied to. Server-side, so it survives refreshes and works on any device."""
    att = await applications.attention(db, user.id)
    letters = (await db.execute(select(CoverLetter).where(
        CoverLetter.user_id == user.id, CoverLetter.status == "needs_input").order_by(CoverLetter.created_at))).scalars().all()
    out = {k: [_dict(a) for a in v] for k, v in att.items()}
    out["letters"] = [{"id": str(c.id), "job_title": c.job_title, "created_at": _iso(c.created_at)} for c in letters]
    return out | {"count": sum(len(v) for v in out.values())}


@application_router.post("/applications", status_code=201)
async def create_application(data: ApplicationIn, db: AsyncSession = Depends(get_db),
                             user: User = Depends(get_current_user)):
    text = (data.jd_text or "").strip()
    if not text and data.job_url and data.job_url.lower().startswith(("http://", "https://")):
        try:                                    # a posting link: read it once now, so no tool asks for it again
            await validate_public_url(data.job_url)
            text, _ = await scraper_service.scrape(data.job_url)
        except ScraperError as exc:
            if not (data.company or data.role):
                raise HTTPException(status_code=422, detail=f"{exc} Paste the job description instead.")
            text = ""
    if text and len(text) < 100:
        raise HTTPException(status_code=422, detail="The job description is too short (min 100 characters)")
    if not (text or data.company or data.role):
        raise HTTPException(status_code=422, detail="Paste the job description, or add a company or a role")
    hints = applications.extract_hints(text[:600]) if text else {"company": None, "role": None}
    started = await applications.get_or_create(db, user.id, source="manual", jd_text=text or None,
                                               job_url=data.job_url) if text else None
    app = await applications.track(db, user.id, source="manual", kind="note", summary="Added by you",
                                   company=data.company or hints["company"], role=data.role or hints["role"],
                                   job_url=data.job_url, jd_text=text or None,
                                   application_id=started.id if started else None)
    app = await applications.update_application(
        db, app, status=data.status, applied_at=_when(data.applied_at), follow_up_at=_when(data.follow_up_at),
        notes=data.notes)
    await db.commit()
    return _dict(app)


@application_router.get("/applications/{application_id}")
async def get_application(application_id: str, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    a = await _own(db, application_id, user)
    events = (await db.execute(select(ApplicationEvent).where(ApplicationEvent.application_id == a.id)
                               .order_by(ApplicationEvent.occurred_at.desc()))).scalars().all()
    reqs = (await db.execute(select(AssistantRequest.id).where(AssistantRequest.application_id == a.id))).scalars().all()
    resumes = (await db.execute(select(JobApplication).where(JobApplication.application_id == a.id)
                                .order_by(JobApplication.created_at.desc()))).scalars().all()
    letters = (await db.execute(select(CoverLetter).where(CoverLetter.application_id == a.id)
                                .order_by(CoverLetter.created_at.desc()))).scalars().all()
    preps = (await db.execute(select(InterviewPrep).where(InterviewPrep.application_id == a.id)
                              .order_by(InterviewPrep.created_at.desc()))).scalars().all()
    usage = {k: v for k, v in (a.usage or {}).items() if not k.startswith("_")}
    return {**_dict(a), "assistant_requests": [str(r) for r in reqs],
            "jd_text": a.jd_text, "usage": usage, "caps": pricing.JOB_CAPS if settings.BILLING_ENABLED else {},
            "artifacts": {
                "resumes": [{"id": str(r.id), "status": r.status, "ats_score": r.ats_score, "created_at": _iso(r.created_at),
                             "download_url": f"/api/download/{r.id}" if r.resume_s3_key else None,
                             "pdf_url": f"/api/download/{r.id}?format=pdf" if r.resume_data else None} for r in resumes],
                "cover_letters": [{"id": str(c.id), "status": c.status, "word_count": c.word_count,
                                   "created_at": _iso(c.created_at)} for c in letters],
                "interview_preps": [{"id": str(p.id), "status": p.status, "created_at": _iso(p.created_at)} for p in preps],
            },
            "events": [{"id": str(e.id), "kind": e.kind, "summary": e.summary, "occurred_at": _iso(e.occurred_at)}
                       for e in events]}


@application_router.patch("/applications/{application_id}")
async def update_application(application_id: str, data: ApplicationIn, db: AsyncSession = Depends(get_db),
                             user: User = Depends(get_current_user)):
    """Edit a record, or answer a back-question (company/role). Returns the surviving record: if the corrected
    company and role match another application, they are merged into one."""
    a = await _own(db, application_id, user)
    try:
        a = await applications.update_application(
            db, a, company=data.company, role=data.role, job_url=data.job_url, status=data.status,
            applied_at=_when(data.applied_at), follow_up_at=_when(data.follow_up_at), notes=data.notes,
            clear_follow_up=data.clear_follow_up)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await db.commit()
    return _dict(a)


@application_router.delete("/applications/{application_id}")
async def delete_application(application_id: str, db: AsyncSession = Depends(get_db),
                             user: User = Depends(get_current_user)):
    await db.delete(await _own(db, application_id, user))
    await db.commit()
    return {"message": "Deleted"}


@application_router.post("/applications/{application_id}/follow-up-draft",
                         dependencies=[Depends(per_user_limit("content", 10))])
async def follow_up_draft(application_id: str, db: AsyncSession = Depends(get_db),
                          user: User = Depends(get_current_user)):
    """A short follow-up message for this application, from what we know about it. Facts only."""
    a = await _own(db, application_id, user)
    await credits.ensure_unlocked(db, user, a, "follow_up")
    await db.commit()                                  # the use is counted before the model runs
    profile = (await cache_service.get_profile(str(user.id)) or await metabase_service.get_full_profile_async(db, user.id))
    name = ((profile.get("personal") or {}).get("full_name") or "").strip()
    since = a.applied_at or a.created_at
    days = max((datetime.utcnow() - since).days, 0)
    if settings.LLM_FAKE:
        text = f"Hi, I applied for the {a.role or 'role'} {days} days ago and wanted to follow up. Thank you. {name}"
    else:
        prompt = (f"Write a short, polite follow-up email (60-90 words) from a job candidate.\nCandidate: {name}\n"
                  f"Company: {a.company or 'the company'}\nRole: {a.role or 'the role'}\n"
                  f"They applied {days} days ago.\nStatus: {a.status}\n"
                  "Rules: do not invent anything about the candidate or the company; no numbers other than the "
                  "days above; ask about next steps; sign with the candidate's name.\n"
                  'Return JSON: {"subject": "...", "body": "..."}')
        import json
        await ensure_budget(db, user.id)
        tally, started, ok = start_tally(), time.monotonic(), False
        try:
            raw = await asyncio.to_thread(ai_agent._call, "You write brief, honest job follow-up emails. JSON only.", prompt, 500)
            data = json.loads(raw)
            ok = True
        except Exception:
            mark_failed()
            await credits.release(db, a.id, "follow_up")
            await db.commit()
            raise
        finally:
            await record_usage(user.id, "follow_up", tally, started, ok and not tally["failed"])
        text = f"Subject: {data.get('subject', '')}\n\n{data.get('body', '')}"
    await applications.add_event(db, a, "follow_up", "Drafted a follow-up message")
    await credits.succeeded(db, a.id)
    await db.commit()
    return {"draft": text}
