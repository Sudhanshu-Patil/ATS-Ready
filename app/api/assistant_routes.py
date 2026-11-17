"""Application assistant: answers to the questions on an application form, plus the persona it learns from.

Refresh- and offline-safe by construction:
  * POST stores the request (and its application) BEFORE any AI work and is idempotent on client_request_id, so a
    retried submit after a dropped connection returns the same request instead of creating a second one;
  * answers are produced by the worker and read back by id, so a refresh or a closed tab loses nothing;
  * edits and approvals are separate small PATCH calls the client can retry safely.
"""
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.activity_routes import ensure_capacity, ensure_profile
from app.api.dependencies import get_current_user
from app.config import settings
from app.api.rate_limit import per_user_limit
from app.db.database import get_db
from app.db.models import AssistantRequest, User
from app.services import applications, assistant, credits, letter_limit, persona
from app.services.ats_score import term_in
from app.services.cache_service import cache_service
from app.services.metabase_service import metabase_service
from app.services.queue import enqueue

assistant_router = APIRouter(tags=["Assistant"])
logger = logging.getLogger(__name__)


class AssistantCreate(BaseModel):
    client_request_id: str = Field(min_length=8, max_length=64)   # made by the browser; makes retries safe
    questions: List[str] = Field(min_length=1, max_length=assistant.MAX_QUESTIONS)
    jd_text: Optional[str] = Field(default=None, max_length=50000)
    company: Optional[str] = Field(default=None, max_length=200)
    role: Optional[str] = Field(default=None, max_length=300)
    job_url: Optional[str] = Field(default=None, max_length=1000)
    limit: Optional[int] = None
    limit_unit: str = "words"
    track: bool = True                                           # False: just answer, do not record an application
    application_id: Optional[str] = None                         # keep working on a job already started


def _app_dict(app) -> Optional[dict]:
    if app is None:
        return None
    return {"id": str(app.id), "company": app.company, "role": app.role, "status": app.status, "needs": app.needs or [],
            "applied_at": app.applied_at.isoformat() if app.applied_at else None,
            "follow_up_at": app.follow_up_at.isoformat() if app.follow_up_at else None,
            "created_at": app.created_at.isoformat()}


def _req_dict(req: AssistantRequest, app=None, full: bool = True) -> dict:
    out = {"id": str(req.id), "status": req.status, "error": req.error, "company": req.company, "role": req.job_title,
           "application_id": str(req.application_id) if req.application_id else None,
           "has_jd": bool((req.jd_text or "").strip()), "created_at": req.created_at.isoformat(),
           "question_count": len(req.questions or []),
           "needs_input": sum(1 for q in req.questions or [] if q.get("status") == "needs_input")}
    if full:
        out["questions"] = req.questions
        out["application"] = _app_dict(app)
    return out


async def _own(db: AsyncSession, request_id: str, user: User) -> AssistantRequest:
    try:
        rid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Request not found")
    req = (await db.execute(select(AssistantRequest).where(
        AssistantRequest.id == rid, AssistantRequest.user_id == user.id))).scalar_one_or_none()
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return req


@assistant_router.post("/assistant/requests", status_code=202, dependencies=[Depends(per_user_limit("content", 10))])
async def create_request(
    data: AssistantCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Queue answers. Works with a job description, or with questions alone."""
    existing = (await db.execute(select(AssistantRequest).where(
        AssistantRequest.user_id == user.id, AssistantRequest.client_request_id == data.client_request_id))).scalar_one_or_none()
    if existing is not None:                                     # a retried submit: same request, no duplicate
        app = await db.get(applications.Application, existing.application_id) if existing.application_id else None
        return _req_dict(existing, app)

    if data.limit is not None:
        try:
            letter_limit.validate(data.limit_unit, data.limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    questions = assistant.prepare_questions(data.questions, data.limit, data.limit_unit)
    if not questions:
        raise HTTPException(status_code=422, detail="Add at least one question")
    await ensure_profile(db, user.id)
    await ensure_capacity(db, user.id)

    jd_text = (data.jd_text or "").strip() or None
    # Company/role: what the user typed, else only what their own text literally says. Never a guess.
    hints = applications.extract_hints(" ".join(q["question"] for q in questions))
    company = (data.company or "").strip() or hints["company"]
    role = (data.role or "").strip() or hints["role"]

    app = None
    given = credits.parse_uuid(data.application_id) if data.application_id else None
    if given:
        app = await db.get(applications.Application, given)
        if app is None or app.user_id != user.id:
            raise HTTPException(status_code=404, detail="Job not found")
    elif data.track or settings.BILLING_ENABLED:          # with credits, every answer belongs to a job
        app = await applications.track(
            db, user.id, source="assistant", kind="questions",
            summary=f"Asked for answers to {len(questions)} application question{'s' if len(questions) != 1 else ''}",
            jd_text=jd_text, company=company, role=role, job_url=data.job_url,
            payload={"questions": [q["question"][:120] for q in questions][:20]})
    if app is not None:
        await credits.ensure_unlocked(db, user, app, "answers", len(questions))
    req = AssistantRequest(user_id=user.id, application_id=app.id if app else None,
                           client_request_id=data.client_request_id, jd_text=jd_text,
                           company=app.company if app else company, job_title=app.role if app else role,
                           questions=questions, status="pending")
    db.add(req)
    await db.commit()
    await db.refresh(req)
    try:
        await enqueue("generate_assistant_answers_task", request_id=str(req.id), user_id=str(user.id), only=None)
    except Exception:
        logger.exception("Could not enqueue assistant request %s", req.id)
        req.status, req.error = "failed", "The job queue is unavailable. Please try again."
        await credits.release(db, req.application_id, "answers", len(questions))
        await db.commit()
        raise HTTPException(status_code=503, detail="The job queue is unavailable. Please try again.")
    return _req_dict(req, app)


@assistant_router.get("/assistant/requests")
async def list_requests(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    rows = (await db.execute(select(AssistantRequest).where(AssistantRequest.user_id == user.id)
                             .order_by(AssistantRequest.created_at.desc()).limit(100))).scalars().all()
    return [_req_dict(r, full=False) for r in rows]


@assistant_router.get("/assistant/requests/{request_id}")
async def get_request(request_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    req = await _own(db, request_id, user)
    app = await db.get(applications.Application, req.application_id) if req.application_id else None
    return _req_dict(req, app)


class AnswerEdit(BaseModel):
    answer: Optional[str] = Field(default=None, max_length=6000)
    approved: Optional[bool] = None            # the user copied it or said it is good: learn from it


@assistant_router.patch("/assistant/requests/{request_id}/questions/{qid}")
async def edit_answer(request_id: str, qid: int, data: AnswerEdit, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """Save the user's edit, and learn from it when they approve it."""
    req = await _own(db, request_id, user)
    items = [dict(q) for q in req.questions]
    q = next((x for x in items if x["id"] == qid), None)
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found")
    if data.answer is not None:
        q["answer"] = data.answer.strip()
    if data.approved and q.get("answer") and q["status"] == "done":
        q["approved"] = True
        profile = (await cache_service.get_profile(str(user.id))
                   or await metabase_service.get_full_profile_async(db, user.id))
        mentioned = [s["name"] for s in profile.get("skills", []) if s.get("name") and term_in(s["name"], _n(q["answer"]))]
        await persona.record_story(db, user.id, q.get("topic") or "other", q["question"], q["answer"], mentioned)
    req.questions = items
    await db.commit()
    return q


def _n(text: str) -> str:
    from app.services.ats_score import _norm
    return _norm(text)


class FactIn(BaseModel):
    field: str
    value: str = Field(min_length=1, max_length=300)


@assistant_router.post("/assistant/requests/{request_id}/facts", status_code=202)
async def supply_fact(request_id: str, data: FactIn, db: AsyncSession = Depends(get_db),
                      user: User = Depends(get_current_user)):
    """The user answered a back-question (e.g. their notice period). Remember it, then answer the questions that
    were waiting for it."""
    if data.field not in persona.FACT_FIELDS:
        raise HTTPException(status_code=422, detail="Unknown field")
    req = await _own(db, request_id, user)
    await persona.set_fact(db, user.id, data.field, data.value)
    waiting = [q["id"] for q in req.questions if q.get("status") == "needs_input" and (q.get("needs") or {}).get("field") == data.field]
    if not waiting:                                   # nothing was waiting for this fact: no model run
        await db.commit()
        return {"id": str(req.id), "waiting": []}
    items = [dict(q) | ({"status": "pending", "needs": None} if q["id"] in waiting else {}) for q in req.questions]
    req.questions, req.status = items, "pending"
    await db.commit()
    await enqueue("generate_assistant_answers_task", request_id=str(req.id), user_id=str(user.id), only=waiting)
    return {"id": str(req.id), "waiting": waiting}


@assistant_router.delete("/assistant/requests/{request_id}")
async def delete_request(request_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await db.delete(await _own(db, request_id, user))
    await db.commit()
    return {"message": "Deleted"}


# ── What the assistant knows about you ───────────────────────────────────────

@assistant_router.get("/persona")
async def get_persona(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return {**await persona.overview(db, user.id), "fields": {k: {"label": v["label"], "hint": v["hint"]}
                                                              for k, v in persona.FACT_FIELDS.items()}}


@assistant_router.put("/persona/facts/{field}")
async def put_fact(field: str, data: FactIn, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    if field not in persona.FACT_FIELDS or field != data.field:
        raise HTTPException(status_code=422, detail="Unknown field")
    await persona.set_fact(db, user.id, field, data.value)
    await db.commit()
    return {"field": field, "value": data.value.strip()}


@assistant_router.delete("/persona/nodes/{node_id}")
async def forget_node(node_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        nid = uuid.UUID(node_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    if not await persona.forget(db, user.id, nid):
        raise HTTPException(status_code=404, detail="Not found")
    await db.commit()
    return {"message": "Forgotten"}


@assistant_router.delete("/persona")
async def forget_everything(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    n = await persona.forget_all(db, user.id)
    await db.commit()
    return {"forgotten": n}
