"""Application tracking: one record per job the user goes after, however it started.

Every feature that touches a job (resume, cover letter, referral request, assistant answers, manual entry) calls
track(). Rules:

  * Company and role are taken from the job description when there is one, otherwise ONLY from what the user's own
    text literally says ("Why do you want to work at Stripe?"). They are never guessed.
  * When the company is missing or unclear ("Confidential", "our client") the application is still created, marked
    needs=["company"], and the UI asks the user right away (and keeps asking until answered, across refreshes).
  * The same job reached from different features is one application: matched by job description, then by
    company + role, then by link.
  * Every event keeps the date the USER did it (occurred_at), so the timeline shows when they asked.
  * Follow-ups: once an application is marked applied, a follow-up date is set (default +7 days). A job the user
    only asked questions about is nudged ("did you apply?") instead, so nothing is assumed.
"""
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import APPLICATION_STATUSES, Application, ApplicationEvent, AssistantRequest
from app.services.suggestion_store import jd_hash

FOLLOW_UP_DAYS = 7
ASK_IF_APPLIED_AFTER_DAYS = 3
# a status never moves backwards by itself (asking for a cover letter must not undo "interviewing")
_RANK = {s: i for i, s in enumerate(("interested", "referral_requested", "applied", "interviewing", "offer"))}
_FINAL = {"rejected", "withdrawn"}

_UNCLEAR = {"confidential", "our client", "a client", "client", "the company", "company", "this company", "stealth",
            "stealth startup", "undisclosed", "n/a", "na", "tbd", "unknown", "a leading company", "leading company",
            "hiring", "startup", "a startup", "anonymous", "not disclosed", "various", "multiple"}
_NOT_NAMES = {"you", "us", "our", "this", "the", "we", "your", "my", "me", "i", "it", "that", "there", "what",
              "how", "why", "please", "describe", "tell", "explain", "when", "where", "which", "who", "do", "are",
              "have", "can", "would", "could", "should", "if", "in", "on", "at", "a", "an", "to", "for", "and"}


def norm(text: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def is_unclear_company(name: Optional[str]) -> bool:
    n = norm(name)
    return not n or n in _UNCLEAR or len(n) < 2 or n in _NOT_NAMES


# ── What the user's own text literally says ───────────────────────────────────

_NAME = r"([A-Z][\w&.\-]*(?:\s+(?:[A-Z][\w&.\-]*|&|of|and))*)"
_COMPANY_PATTERNS = [
    re.compile(r"\b(?:work(?:ing)?|career|job|role|position|opening)s?\s+(?:at|for|with)\s+" + _NAME),
    re.compile(r"\b(?:join(?:ing)?|apply(?:ing)?\s+(?:to|at|for))\s+" + _NAME),
    re.compile(r"\b(?:interested\s+in|excited\s+(?:about|by)|attracted\s+to)\s+" + _NAME + r"(?:\W|$)"),
    re.compile(r"\bwhy\s+(?:do\s+you\s+want\s+to\s+(?:work\s+(?:at|for)\s+)?)?" + _NAME + r"\s*\?"),
    re.compile(r"\bat\s+" + _NAME + r"\b(?=[\s,.?!]|$)"),
]
_ROLE = re.compile(r"\b(?:for|as|to)\s+(?:the\s+|a\s+|an\s+)?((?:(?:Senior|Junior|Lead|Staff|Principal|Associate)\s+)?"
                   r"[A-Z][\w/+\-]*(?:\s+[A-Z][\w/+\-]*){0,4})\s+(?:role|position|opening|job|internship)\b")


def _clean_name(raw: str) -> Optional[str]:
    name = re.sub(r"\s+(?:and|of|&)$", "", raw.strip(" .,;:?!")).strip()
    words = name.split()
    while words and norm(words[0]) in _NOT_NAMES:
        words.pop(0)
    name = " ".join(words)
    return None if is_unclear_company(name) else name


def extract_hints(text: str) -> Dict[str, Optional[str]]:
    """Company and role only when the text literally names them; otherwise None. Never a guess."""
    company = role = None
    for pat in _COMPANY_PATTERNS:
        for m in pat.finditer(text or ""):
            candidate = _clean_name(m.group(1))
            if candidate:
                company = candidate
                break
        if company:
            break
    m = _ROLE.search(text or "")
    if m:
        r = m.group(1).strip()
        if norm(r) not in _NOT_NAMES and norm(r) != norm(company):
            role = r
    return {"company": company, "role": role}


# ── Create / find / enrich ───────────────────────────────────────────────────

def _needs(app: Application) -> List[str]:
    out = []
    if is_unclear_company(app.company):
        out.append("company")
    if not (app.role or "").strip():
        out.append("role")
    return out


async def _find(db: AsyncSession, user_id: UUID, jd_text: Optional[str], company: Optional[str],
                role: Optional[str], job_url: Optional[str]) -> Optional[Application]:
    q = select(Application).where(Application.user_id == user_id).order_by(Application.created_at.desc())
    if jd_text and len(jd_text.strip()) >= 100:
        hit = (await db.execute(q.where(Application.jd_hash == jd_hash(jd_text)).limit(1))).scalar_one_or_none()
        if hit:
            return hit
    if job_url:
        hit = (await db.execute(q.where(Application.job_url == job_url[:1000]).limit(1))).scalar_one_or_none()
        if hit:
            return hit
    if not is_unclear_company(company):
        for app in (await db.execute(q.limit(200))).scalars().all():
            if norm(app.company) == norm(company) and (not role or not app.role or norm(app.role) == norm(role)):
                return app
    return None


async def add_event(db: AsyncSession, app: Application, kind: str, summary: str,
                    occurred_at: Optional[datetime] = None, payload: Optional[Dict[str, Any]] = None) -> None:
    db.add(ApplicationEvent(application_id=app.id, user_id=app.user_id, kind=kind, summary=summary[:300],
                            payload=payload, occurred_at=occurred_at or datetime.utcnow()))


def _advance(app: Application, status: Optional[str]) -> None:
    if status in _RANK and app.status in _RANK and _RANK[status] > _RANK[app.status]:
        app.status = status


async def track(db: AsyncSession, user_id: UUID, *, source: str, kind: str, summary: str,
                jd_text: Optional[str] = None, company: Optional[str] = None, role: Optional[str] = None,
                job_url: Optional[str] = None, status: Optional[str] = None, occurred_at: Optional[datetime] = None,
                payload: Optional[Dict[str, Any]] = None, application_id: Optional[UUID] = None) -> Application:
    """Attach an event to the right application, creating it if this job is new. Returns the application."""
    app = await db.get(Application, application_id) if application_id else None
    if app is not None and app.user_id != user_id:
        app = None
    if app is None:
        app = await _find(db, user_id, jd_text, company, role, job_url)
    created = app is None
    if created:
        app = Application(user_id=user_id, source=source, status="interested", needs=[])
        db.add(app)
    # fill gaps only: values the user set or confirmed are never overwritten by a later guess
    if is_unclear_company(app.company) and not is_unclear_company(company):
        app.company = (company or "").strip()[:200]
    if not (app.role or "").strip() and (role or "").strip():
        app.role = role.strip()[:300]
    if not app.job_url and job_url:
        app.job_url = job_url[:1000]
    if jd_text and len(jd_text.strip()) >= 100 and not app.jd_hash:
        app.jd_hash, app.jd_text = jd_hash(jd_text), jd_text.strip()[:8000]
    _advance(app, status)
    app.needs = _needs(app)
    await db.flush()
    if created:
        await add_event(db, app, "created", f"Started from {source.replace('_', ' ')}", occurred_at)
    await add_event(db, app, kind, summary, occurred_at, payload)
    return app


# ── The user answers a back-question or edits the record ─────────────────────

def _schedule_follow_up(app: Application) -> None:
    if app.status == "applied" and app.applied_at and not app.follow_up_at:
        app.follow_up_at = app.applied_at + timedelta(days=FOLLOW_UP_DAYS)


async def update_application(db: AsyncSession, app: Application, *, company: Optional[str] = None,
                             role: Optional[str] = None, job_url: Optional[str] = None,
                             status: Optional[str] = None, applied_at: Optional[datetime] = None,
                             follow_up_at: Optional[datetime] = None, notes: Optional[str] = None,
                             clear_follow_up: bool = False) -> Application:
    """Apply the user's edits. Returns the surviving application: if the corrected company + role match another
    application, the two are merged (events and assistant requests move over) so one job never appears twice."""
    if company is not None:
        app.company = company.strip()[:200] or None
    if role is not None:
        app.role = role.strip()[:300] or None
    if job_url is not None:
        app.job_url = job_url.strip()[:1000] or None
    if notes is not None:
        app.notes = notes[:4000]
    if status is not None:
        if status not in APPLICATION_STATUSES:
            raise ValueError(f"status must be one of {', '.join(APPLICATION_STATUSES)}")
        if status != app.status:
            await add_event(db, app, "status", f"Marked {status.replace('_', ' ')}", applied_at or datetime.utcnow())
        app.status = status
        if status == "applied" and not app.applied_at:
            app.applied_at = applied_at or datetime.utcnow()
    if applied_at is not None:
        app.applied_at = applied_at
        app.follow_up_at = None                    # the date moved: recompute below
    if follow_up_at is not None:
        app.follow_up_at = follow_up_at
    if clear_follow_up:
        app.follow_up_at = None
    _schedule_follow_up(app)
    app.needs = _needs(app)
    await db.flush()
    return await _merge_duplicate(db, app)


async def _merge_duplicate(db: AsyncSession, app: Application) -> Application:
    if is_unclear_company(app.company):
        return app
    others = (await db.execute(select(Application).where(
        Application.user_id == app.user_id, Application.id != app.id))).scalars().all()
    twin = next((o for o in others if norm(o.company) == norm(app.company)
                 and (not o.role or not app.role or norm(o.role) == norm(app.role))), None)
    if twin is None:
        return app
    keep, drop = (twin, app) if twin.created_at <= app.created_at else (app, twin)
    for field in ("role", "job_url", "jd_hash", "jd_text", "applied_at", "follow_up_at", "notes"):
        if not getattr(keep, field) and getattr(drop, field):
            setattr(keep, field, getattr(drop, field))
    if _RANK.get(drop.status, -1) > _RANK.get(keep.status, -1) or drop.status in _FINAL:
        keep.status = drop.status
    await db.execute(update(ApplicationEvent).where(ApplicationEvent.application_id == drop.id)
                     .values(application_id=keep.id))
    await db.execute(update(AssistantRequest).where(AssistantRequest.application_id == drop.id)
                     .values(application_id=keep.id))
    await db.delete(drop)
    keep.needs = _needs(keep)
    await db.flush()
    return keep


# ── What needs the user's attention ──────────────────────────────────────────

async def attention(db: AsyncSession, user_id: UUID, now: Optional[datetime] = None) -> Dict[str, List[Application]]:
    """needs: missing company/role. due: follow-up date reached. ask_applied: questions were answered a few days
    ago but the user never said whether they applied."""
    now = now or datetime.utcnow()
    apps = (await db.execute(select(Application).where(
        Application.user_id == user_id, Application.status.notin_(tuple(_FINAL) + ("offer",))
    ).order_by(Application.created_at))).scalars().all()
    stale_before = now - timedelta(days=ASK_IF_APPLIED_AFTER_DAYS)
    return {
        "needs": [a for a in apps if a.needs],
        "due": [a for a in apps if a.follow_up_at and a.follow_up_at <= now and a.status in ("applied", "referral_requested")],
        "ask_applied": [a for a in apps if a.status == "interested" and not a.needs and a.created_at <= stale_before
                        and not a.applied_at],
    }
