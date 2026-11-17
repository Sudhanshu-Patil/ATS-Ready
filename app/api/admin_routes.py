"""Admin analytics. Access is by email allowlist (ADMIN_EMAILS), verified-only."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.config import settings
from app.db.database import get_db
from app.db.models import (Application, CoverLetter, CreditLedger, InterviewPrep, JobApplication, Payment, Referral,
                           UsageEvent, User)
from app.services import pricing
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


async def _credit_stats(db: AsyncSession, since30: datetime, by_kind_tokens: int) -> dict:
    """Money in, credits out, and what a job really costs us (to tune pricing.JOB_CAPS and the pack prices)."""
    def paid(*where):
        return select(Payment.currency, func.count(Payment.id), func.coalesce(func.sum(Payment.amount_minor), 0)).where(
            Payment.status == "paid", *where).group_by(Payment.currency)

    revenue_total = {c: {"payments": n, "amount": int(a) / 100} for c, n, a in (await db.execute(paid())).all()}
    revenue_30d = {c: {"payments": n, "amount": int(a) / 100}
                   for c, n, a in (await db.execute(paid(Payment.paid_at >= since30))).all()}
    paying_users = int((await db.execute(select(func.count(func.distinct(Payment.user_id))).where(
        Payment.status == "paid"))).scalar() or 0)
    by_pack = [{"pack": p, "payments": n} for p, n in (await db.execute(
        select(Payment.pack_id, func.count(Payment.id)).where(Payment.status == "paid").group_by(Payment.pack_id))).all()]

    # ledger by reason: what was given for free, bought, earned, spent and returned
    ledger = {(r, k): int(d) for r, k, d in (await db.execute(
        select(CreditLedger.reason, CreditLedger.kind, func.sum(CreditLedger.delta)).group_by(
            CreditLedger.reason, CreditLedger.kind))).all()}
    sold = sum(v for (r, _), v in ledger.items() if r == "purchase")
    free = sum(v for (r, _), v in ledger.items() if r in ("signup", "referral"))
    unlocks_30d = int((await db.execute(select(func.count(CreditLedger.id)).where(
        CreditLedger.reason == "unlock", CreditLedger.created_at >= since30))).scalar() or 0)
    refunds_30d = int((await db.execute(select(func.count(CreditLedger.id)).where(
        CreditLedger.reason == "refund", CreditLedger.created_at >= since30))).scalar() or 0)
    outstanding_job = int((await db.execute(select(func.coalesce(func.sum(User.credits_job), 0)))).scalar() or 0)
    outstanding_resume = int((await db.execute(select(func.coalesce(func.sum(User.credits_resume), 0)))).scalar() or 0)
    unlocked_jobs = await _count(db, Application, Application.unlock_level != "none")
    refs = dict((await db.execute(select(Referral.status, func.count(Referral.id)).group_by(Referral.status))).all())

    return {
        "revenue_total": revenue_total, "revenue_30d": revenue_30d, "paying_users": paying_users, "by_pack": by_pack,
        "credits": {"sold": sold, "free_given": free, "outstanding_job": outstanding_job,
                    "outstanding_resume": outstanding_resume, "jobs_unlocked": unlocked_jobs},
        "last_30d": {"unlocks": unlocks_30d, "refunds": refunds_30d,
                     # model tokens per unlocked job: the number to compare with the ~2 rupee estimate behind the prices
                     "tokens_per_unlock": round(by_kind_tokens / unlocks_30d) if unlocks_30d else None},
        "referrals": {"rewarded": refs.get("rewarded", 0), "pending": refs.get("pending", 0), "void": refs.get("void", 0)},
        "pack_prices_inr": {p["id"]: p["inr"] / 100 for p in pricing.catalog()["packs"]},
    }


@admin_router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    now = datetime.utcnow()
    day, week = now - timedelta(days=1), now - timedelta(days=7)
    since30 = now - timedelta(days=30)

    users_total = await _count(db, User)

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
                  "verified": await _count(db, User, User.is_verified.is_(True))},
        "credits": await _credit_stats(db, since30, by_kind_tokens=sum(k["tokens"] for k in by_kind)),
        "resumes_by_status": {s: c for s, c in status_rows},
        "queue": queue,
        "llm": {"tokens_today": await tokens_today(db), "daily_cap": settings.LLM_DAILY_TOKEN_CAP,
                "per_user_cap": settings.LLM_USER_DAILY_TOKEN_CAP, "by_kind_30d": by_kind},
        "daily": daily,
    }

