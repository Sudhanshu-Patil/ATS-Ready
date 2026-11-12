"""Admin analytics. Access is by email allowlist (ADMIN_EMAILS), verified-only."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.config import settings
from app.db.database import get_db
from app.db.models import CoverLetter, InterviewPrep, JobApplication, UsageEvent, User
from app.services.usage import tokens_today

admin_router = APIRouter(prefix="/admin", tags=["Admin"])


def is_admin(user: User) -> bool:
    allowed = {e.strip().lower() for e in settings.ADMIN_EMAILS.split(",") if e.strip()}
    return bool(user.is_verified and user.email.lower() in allowed)


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not is_admin(user):
        raise HTTPException(status_code=404, detail="Not found")      # do not reveal the page exists
    return user


async def _count(db, model, *where) -> int:
    return int((await db.execute(select(func.count(model.id)).where(*where))).scalar() or 0)


@admin_router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    now = datetime.utcnow()
    day, week = now - timedelta(days=1), now - timedelta(days=7)
    since30 = now - timedelta(days=30)

    users_total = await _count(db, User)
    plan_rows = (await db.execute(select(User.plan, func.count(User.id)).group_by(User.plan))).all()

    status_rows = (await db.execute(
        select(JobApplication.status, func.count(JobApplication.id)).group_by(JobApplication.status))).all()
    active_24h = int((await db.execute(
        select(func.count(func.distinct(UsageEvent.user_id))).where(UsageEvent.created_at >= day))).scalar() or 0)
    active_7d = int((await db.execute(
        select(func.count(func.distinct(UsageEvent.user_id))).where(UsageEvent.created_at >= week))).scalar() or 0)

    # Per-day series for the last 14 days.
    series_since = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=13)
    su_day = func.date_trunc("day", User.created_at)
    d_signups = {r[0].date().isoformat(): r[1] for r in (await db.execute(
        select(su_day, func.count(User.id)).where(User.created_at >= series_since).group_by(su_day))).all()}
    ue_day = func.date_trunc("day", UsageEvent.created_at)
    d_usage = {r[0].date().isoformat(): (r[1], r[2], r[3]) for r in (await db.execute(
        select(ue_day, func.count(UsageEvent.id),
               func.coalesce(func.sum(UsageEvent.tokens), 0), func.coalesce(func.sum(UsageEvent.ok.cast(Integer)), 0))
        .where(UsageEvent.created_at >= series_since).group_by(ue_day))).all()}
    daily = []
    for i in range(14):
        d = (series_since + timedelta(days=i)).date().isoformat()
        runs, tokens, oks = d_usage.get(d, (0, 0, 0))
        daily.append({"date": d, "signups": d_signups.get(d, 0), "runs": runs,
                      "tokens": int(tokens), "failed": int(runs - oks)})

    by_kind = [{"kind": k, "runs": r, "tokens": int(t), "avg_seconds": round((ms or 0) / 1000, 1),
                "failure_rate": round(1 - (ok or 0) / r, 3) if r else 0}
               for k, r, t, ms, ok in (await db.execute(
                   select(UsageEvent.kind, func.count(UsageEvent.id), func.coalesce(func.sum(UsageEvent.tokens), 0),
                          func.avg(UsageEvent.duration_ms), func.sum(UsageEvent.ok.cast(Integer)))
                   .where(UsageEvent.created_at >= since30).group_by(UsageEvent.kind))).all()]

    queue = {
        "pending": sum([await _count(db, m, m.status == "pending") for m in (JobApplication, CoverLetter, InterviewPrep)]),
        "running": sum([await _count(db, m, m.status == "running") for m in (JobApplication, CoverLetter, InterviewPrep)]),
    }
    return {
        "users": {"total": users_total, "active_24h": active_24h, "active_7d": active_7d,
                  "plans": {p: c for p, c in plan_rows}},
        "resumes_by_status": {s: c for s, c in status_rows},
        "queue": queue,
        "llm": {"tokens_today": await tokens_today(db), "daily_cap": settings.LLM_DAILY_TOKEN_CAP,
                "per_user_cap": settings.LLM_USER_DAILY_TOKEN_CAP, "by_kind_30d": by_kind},
        "daily": daily,
    }

