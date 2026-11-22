"""Admin analytics. Access is by email allowlist (ADMIN_EMAILS), verified-only."""
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
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


def _day_key(d) -> str:
    return d.date().isoformat()


@admin_router.get("/stats")
async def stats(days: int = Query(30, ge=7, le=90), db: AsyncSession = Depends(get_db),
                _: User = Depends(require_admin)):
    """Everything on the admin page for the last `days` days (7 to 90)."""
    now = datetime.utcnow()
    day, week = now - timedelta(days=1), now - timedelta(days=7)
    since = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    dates = [_day_key(since + timedelta(days=i)) for i in range(days)]

    users_total = await _count(db, User)
    status_rows = (await db.execute(
        select(JobApplication.status, func.count(JobApplication.id)).group_by(JobApplication.status))).all()
    active_24h = int((await db.execute(
        select(func.count(func.distinct(UsageEvent.user_id))).where(UsageEvent.created_at >= day))).scalar() or 0)
    active_7d = int((await db.execute(
        select(func.count(func.distinct(UsageEvent.user_id))).where(UsageEvent.created_at >= week))).scalar() or 0)

    # ── per-day series ────────────────────────────────────────────────────────
    def per_day(col, *cols, where=(), group=None):
        g = func.date_trunc("day", col)
        return select(g, *cols).where(col >= since, *where).group_by(g, *(group or []))

    signups = {_day_key(r[0]): r[1] for r in (await db.execute(per_day(User.created_at, func.count(User.id)))).all()}
    verified_signups = {_day_key(r[0]): r[1] for r in (await db.execute(
        per_day(User.created_at, func.count(User.id), where=(User.is_verified.is_(True),)))).all()}
    usage_day = {_day_key(r[0]): r[1:] for r in (await db.execute(per_day(
        UsageEvent.created_at, func.count(UsageEvent.id), func.coalesce(func.sum(UsageEvent.tokens), 0),
        func.coalesce(func.sum(UsageEvent.ok.cast(Integer)), 0), func.count(func.distinct(UsageEvent.user_id))))).all()}
    tokens_kind_day: dict = {}
    for d, kind, tokens in (await db.execute(per_day(
            UsageEvent.created_at, UsageEvent.kind, func.coalesce(func.sum(UsageEvent.tokens), 0),
            group=[UsageEvent.kind]))).all():
        tokens_kind_day.setdefault(_day_key(d), {})[kind] = int(tokens)
    revenue_day: dict = {}
    for d, cur, amount in (await db.execute(per_day(
            Payment.paid_at, Payment.currency, func.coalesce(func.sum(Payment.amount_minor), 0),
            where=(Payment.status == "paid",), group=[Payment.currency]))).all():
        revenue_day.setdefault(_day_key(d), {})[cur] = int(amount) / 100
    ledger_day: dict = {}
    for d, reason, n, total in (await db.execute(per_day(
            CreditLedger.created_at, CreditLedger.reason, func.count(CreditLedger.id), func.sum(CreditLedger.delta),
            group=[CreditLedger.reason]))).all():
        ledger_day.setdefault(_day_key(d), {})[reason] = (n, int(total))

    kinds = sorted({k for v in tokens_kind_day.values() for k in v})
    daily = []
    for d in dates:
        runs, tokens, oks, actives = usage_day.get(d, (0, 0, 0, 0))
        led = ledger_day.get(d, {})
        daily.append({
            "date": d, "signups": signups.get(d, 0), "verified_signups": verified_signups.get(d, 0),
            "runs": runs, "tokens": int(tokens), "failed": int(runs - oks), "active_users": actives,
            "revenue_inr": revenue_day.get(d, {}).get("INR", 0), "revenue_usd": revenue_day.get(d, {}).get("USD", 0),
            "unlocks": led.get("unlock", (0, 0))[0], "refunds": led.get("refund", (0, 0))[0],
            "credits_bought": led.get("purchase", (0, 0))[1],
            "credits_free": led.get("signup", (0, 0))[1] + led.get("referral", (0, 0))[1],
            "tokens_by_kind": tokens_kind_day.get(d, {}),
        })

    # ── by kind, latency, and when people use it ──────────────────────────────
    by_kind = [{"kind": k, "runs": r, "tokens": int(t), "avg_seconds": round((ms or 0) / 1000, 1),
                "p95_seconds": round((p95 or 0) / 1000, 1), "failure_rate": round(1 - (ok or 0) / r, 3) if r else 0,
                "tokens_per_run": round(int(t) / r) if r else 0}
               for k, r, t, ms, p95, ok in (await db.execute(
                   select(UsageEvent.kind, func.count(UsageEvent.id), func.coalesce(func.sum(UsageEvent.tokens), 0),
                          func.avg(UsageEvent.duration_ms),
                          func.percentile_cont(0.95).within_group(UsageEvent.duration_ms),
                          func.sum(UsageEvent.ok.cast(Integer)))
                   .where(UsageEvent.created_at >= since).group_by(UsageEvent.kind))).all()]
    heat = [[0] * 24 for _ in range(7)]                       # weekday (Mon=0) x hour, UTC
    for dow, hour, n in (await db.execute(
            select(func.extract("isodow", UsageEvent.created_at), func.extract("hour", UsageEvent.created_at),
                   func.count(UsageEvent.id)).where(UsageEvent.created_at >= since)
            .group_by(func.extract("isodow", UsageEvent.created_at), func.extract("hour", UsageEvent.created_at)))).all():
        heat[int(dow) - 1][int(hour)] = n

    # ── the path from sign-up to paying ──────────────────────────────────────
    async def distinct_users(model, *where):
        return int((await db.execute(select(func.count(func.distinct(model.user_id))).where(*where))).scalar() or 0)
    funnel = [
        {"step": "Signed up", "users": users_total},
        {"step": "Verified email", "users": await _count(db, User, User.is_verified.is_(True))},
        {"step": "Started a job", "users": await distinct_users(Application)},
        {"step": "Unlocked a job", "users": await distinct_users(Application, Application.unlock_level != "none")},
        {"step": "Paid", "users": await distinct_users(Payment, Payment.status == "paid")},
    ]

    credit_block = await _credit_stats(db, since, by_kind_tokens=sum(k["tokens"] for k in by_kind))
    tokens_window = sum(d["tokens"] for d in daily)
    rev_inr = sum(d["revenue_inr"] for d in daily)
    est_cost = round(tokens_window / 1000 * settings.LLM_COST_INR_PER_1K_TOKENS, 2)
    queue = {
        "pending": sum([await _count(db, m, m.status == "pending") for m in (JobApplication, CoverLetter, InterviewPrep)]),
        "running": sum([await _count(db, m, m.status == "running") for m in (JobApplication, CoverLetter, InterviewPrep)]),
    }
    return {
        "days": days,
        "users": {"total": users_total, "active_24h": active_24h, "active_7d": active_7d,
                  "verified": funnel[1]["users"]},
        "credits": credit_block,
        "funnel": funnel,
        "money": {"revenue_inr": rev_inr, "revenue_usd": sum(d["revenue_usd"] for d in daily),
                  "est_ai_cost_inr": est_cost, "cost_per_1k_tokens_inr": settings.LLM_COST_INR_PER_1K_TOKENS,
                  "margin_inr": round(rev_inr - est_cost, 2)},
        "resumes_by_status": {s_: c for s_, c in status_rows},
        "queue": queue,
        "llm": {"tokens_today": await tokens_today(db), "daily_cap": settings.LLM_DAILY_TOKEN_CAP,
                "per_user_cap": settings.LLM_USER_DAILY_TOKEN_CAP, "by_kind": by_kind, "kinds": kinds},
        "heatmap": heat,
        "daily": daily,
    }


class GrantIn(BaseModel):
    email: EmailStr
    job: int = Field(0, ge=0, le=1000)
    resume: int = Field(0, ge=0, le=1000)


@admin_router.post("/credits/grant")
async def grant_credits(body: GrantIn, db: AsyncSession = Depends(get_db), admin: User = Depends(require_admin)):
    """Add credits to an account (yours or anyone's). Recorded in the ledger as reason 'admin', one row per grant."""
    from app.services import credits

    if not (body.job or body.resume):
        raise HTTPException(status_code=422, detail="Give at least one credit")
    user = (await db.execute(select(User).where(func.lower(User.email) == body.email.lower()))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="No account with that email")
    for kind, n in (("job", body.job), ("resume", body.resume)):
        if n:
            await credits.apply(db, user.id, kind, n, "admin", f"admin:{uuid.uuid4()}")
    await db.commit()
    await db.refresh(user)
    return {"email": user.email, **credits.balances(user)}
