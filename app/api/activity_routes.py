"""
app/api/activity_routes.py
──────────────────────────
One view of everything a user has running in the background (resumes, cover
letters, interview prep), plus the per-user cap on concurrent requests.

The server is the source of truth, so a reload, another page, or another
browser tab all see the same queue.
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import CoverLetter, InterviewPrep, JobApplication, PersonalInfo, User

from app.services.usage import ensure_budget  # noqa: E402

activity_router = APIRouter()

ACTIVE = ("pending", "running")
MAX_ACTIVE_PER_USER = 3
RECENT_WINDOW = timedelta(minutes=15)

# kind -> (model, error column)
KINDS = {
    "resume":         (JobApplication, "error_message"),
    "cover_letter":   (CoverLetter, "error"),
    "interview_prep": (InterviewPrep, "error"),
}


async def count_active(db: AsyncSession, user_id) -> int:
    total = 0
    for model, _ in KINDS.values():
        total += (await db.execute(
            select(func.count(model.id)).where(model.user_id == user_id, model.status.in_(ACTIVE))
        )).scalar() or 0
    return total


async def ensure_capacity(db: AsyncSession, user_id) -> None:
    """Free-tier AI quota is shared by everyone: cap one user's parallel work
    and refuse new work once the daily token budget is spent."""
    await ensure_budget(db, user_id)
    if await count_active(db, user_id) >= MAX_ACTIVE_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=f"You already have {MAX_ACTIVE_PER_USER} requests in progress. "
                   "Wait for one to finish, then try again.",
        )


async def ensure_profile(db: AsyncSession, user_id) -> None:
    exists = (await db.execute(
        select(PersonalInfo.id).where(PersonalInfo.user_id == user_id)
    )).first()
    if not exists:
        raise HTTPException(
            status_code=400,
            detail="Profile incomplete — fill in Personal Info in Metabase first.",
        )


def _item(kind: str, row, error_col: str) -> dict:
    return {
        "kind":       kind,
        "id":         str(row.id),
        "title":      row.job_title,
        "company":    row.company,
        "status":     row.status,
        "error":      getattr(row, error_col) if row.status == "failed" else None,
        "created_at": str(row.created_at),
    }


@activity_router.get("/activity")
async def get_activity(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """{active: [...oldest first], recent: [...finished in the last 15 min]}."""
    since = datetime.utcnow() - RECENT_WINDOW
    active, recent = [], []
    for kind, (model, error_col) in KINDS.items():
        rows = (await db.execute(
            select(model).where(
                model.user_id == user.id,
                or_(model.status.in_(ACTIVE), model.created_at >= since),
            ).order_by(model.created_at)
        )).scalars().all()
        for row in rows:
            (active if row.status in ACTIVE else recent).append(_item(kind, row, error_col))
    active.sort(key=lambda i: i["created_at"])
    recent.sort(key=lambda i: i["created_at"], reverse=True)
    for pos, item in enumerate(active, 1):
        item["position"] = pos
    return {"active": active, "recent": recent}
