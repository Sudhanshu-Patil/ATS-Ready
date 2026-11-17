"""The one place a generation request is tied to a job and, when billing is on, to a credit.

Every route that spends model tokens for a user calls gate(): it finds (or starts) the job this request is about,
makes sure the job is unlocked far enough for the kind of work, counts the use against the job's cap, and returns the
job. The job is found only by its job description (or link), never by what the client claims, so a credit cannot be
stretched over different postings. Nothing here commits: the route does, together with its own row.
"""
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Application, User
from app.services import applications, credits


async def job_for(db: AsyncSession, user_id, *, source: str, jd_text: Optional[str] = None,
                  jd_url: Optional[str] = None, application_id=None) -> Application:
    """The job a request is about. A row that already has one keeps it (retries); otherwise by JD or link."""
    app = None
    if application_id:
        app = await db.get(Application, application_id)
        if app is not None and app.user_id != user_id:
            app = None
    if app is None:
        app = await applications.get_or_create(db, user_id, source=source, jd_text=jd_text, job_url=jd_url)
    return app


async def gate(db: AsyncSession, user: User, kind: str, *, source: str, jd_text: Optional[str] = None,
               jd_url: Optional[str] = None, application_id=None, amount: int = 1) -> Application:
    app = await job_for(db, user.id, source=source, jd_text=jd_text, jd_url=jd_url, application_id=application_id)
    await credits.ensure_unlocked(db, user, app, kind, amount)
    return app


def stored_jd(app: Application, fallback: Optional[str]) -> Optional[str]:
    """The job description to generate from: the job's own once it has one (read-only after unlock)."""
    return (app.jd_text or "").strip() or fallback


def as_uuid(value) -> Optional[uuid.UUID]:
    return credits.parse_uuid(value)
