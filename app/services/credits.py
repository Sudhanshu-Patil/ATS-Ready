"""Credits: the ledger, unlocking a job, the per-job caps, refunds, signup grants and referrals.

Rules that keep this safe:
  * Every balance change goes through apply() under a row lock on the user, with a unique idempotency key. A double
    click, a retried request or a replayed webhook cannot charge or grant twice.
  * A job is paid for once (Application.unlock_level) and the server uses ITS stored job description afterwards, so one
    credit cannot be spread over different job descriptions.
  * Each kind of generation has a per-job cap (pricing.JOB_CAPS). A run that fails gives its use back, and if nothing
    for the job ever succeeded the credit itself is returned.
  * BILLING_ENABLED=false (dev, CI, e2e) skips all of it.
"""
import logging
import secrets
import uuid
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import Application, CreditLedger, Referral, User
from app.services import pricing

logger = logging.getLogger(__name__)

DISPOSABLE_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com", "temp-mail.org", "yopmail.com",
    "trashmail.com", "sharklasers.com", "getnada.com", "dispostable.com", "maildrop.cc", "throwawaymail.com",
}


class InsufficientCredits(Exception):
    pass


# ── Who is who ───────────────────────────────────────────────────────────────

def canonical_email(email: str) -> str:
    """Gmail ignores dots and +tags, so a+1@gmail.com and a.@gmail.com are one person for the signup grant."""
    local, _, domain = (email or "").strip().lower().partition("@")
    if domain in ("gmail.com", "googlemail.com"):
        local = local.split("+")[0].replace(".", "")
        domain = "gmail.com"
    else:
        local = local.split("+")[0]
    return f"{local}@{domain}"


def new_referral_code() -> str:
    return secrets.token_urlsafe(6).replace("-", "x").replace("_", "y")[:8].lower()


# ── The ledger ───────────────────────────────────────────────────────────────

async def _lock(db: AsyncSession, user_id) -> User:
    # populate_existing: after waiting for the lock, read the committed values, not a copy loaded earlier.
    # Flush first: the session does not autoflush, and populate_existing would drop unflushed changes.
    await db.flush()
    return (await db.execute(select(User).where(User.id == user_id).with_for_update()
                             .execution_options(populate_existing=True))).scalar_one()


async def _lock_app(db: AsyncSession, application_id) -> Optional[Application]:
    await db.flush()
    return (await db.execute(select(Application).where(Application.id == application_id).with_for_update()
                             .execution_options(populate_existing=True))).scalar_one_or_none()


async def apply(db: AsyncSession, user_id, kind: str, delta: int, reason: str, key: str, *,
                application_id=None, payment_id=None) -> bool:
    """Change a balance once. Returns False if this key was already applied (nothing changes).
    Raises InsufficientCredits if the balance would go below zero. Does not commit."""
    user = await _lock(db, user_id)
    if (await db.execute(select(CreditLedger.id).where(CreditLedger.idempotency_key == key))).first():
        return False
    field = "credits_job" if kind == "job" else "credits_resume"
    balance = getattr(user, field) + delta
    if balance < 0:
        raise InsufficientCredits(kind)
    setattr(user, field, balance)
    db.add(CreditLedger(user_id=user_id, kind=kind, delta=delta, reason=reason, application_id=application_id,
                        payment_id=payment_id, idempotency_key=key, balance_after=balance))
    await db.flush()
    return True


def balances(user: User) -> dict:
    return {"job": user.credits_job, "resume": user.credits_resume}


# ── Signup grant and referrals ───────────────────────────────────────────────

async def ensure_codes(db: AsyncSession, user: User) -> None:
    if not user.email_canonical:
        user.email_canonical = canonical_email(user.email)
    while not user.referral_code:
        code = new_referral_code()
        if not (await db.execute(select(User.id).where(User.referral_code == code))).first():
            user.referral_code = code


async def grant_signup(db: AsyncSession, user: User) -> bool:
    """Free starter credits, once per person, only for a verified email. Safe to call on every sign-in."""
    verified = user.is_verified or settings.GRANT_WITHOUT_VERIFICATION
    if user.signup_granted or not verified or not settings.BILLING_ENABLED:
        return False
    await ensure_codes(db, user)
    user.signup_granted = True                         # decided now, whatever the outcome below
    await db.flush()
    domain = user.email.rsplit("@", 1)[-1].lower()
    same_person = (await db.execute(select(User.id).where(
        User.email_canonical == user.email_canonical, User.id != user.id, User.signup_granted.is_(True)))).first()
    if domain in DISPOSABLE_DOMAINS or same_person:
        logger.info("Signup grant withheld for user %s (disposable or duplicate address)", user.id)
        await db.commit()
        return False
    await apply(db, user.id, "job", pricing.SIGNUP_JOB_CREDITS, "signup", f"signup:{user.id}:job")
    await apply(db, user.id, "resume", pricing.SIGNUP_RESUME_CREDITS, "signup", f"signup:{user.id}:resume")
    await db.commit()
    return True


async def link_referral(db: AsyncSession, user: User, code: Optional[str]) -> None:
    """Record who invited this user (at registration). Ignored if the code is unknown or it is the user themself."""
    code = (code or "").strip().lower()
    if not code or user.referred_by_id:
        return
    referrer = (await db.execute(select(User).where(User.referral_code == code))).scalar_one_or_none()
    if referrer is None or referrer.id == user.id or referrer.email_canonical == (user.email_canonical or canonical_email(user.email)):
        return
    user.referred_by_id = referrer.id
    db.add(Referral(referrer_id=referrer.id, referee_id=user.id, status="pending"))


async def reward_referral(db: AsyncSession, referee: User) -> None:
    """The invited person verified their email and started a job: the inviter gets a job credit (capped)."""
    if not referee.referred_by_id or not (referee.is_verified or settings.GRANT_WITHOUT_VERIFICATION):
        return
    ref = (await db.execute(select(Referral).where(
        Referral.referee_id == referee.id, Referral.status == "pending").with_for_update())).scalar_one_or_none()
    if ref is None:
        return
    done = (await db.execute(select(func.count(Referral.id)).where(
        Referral.referrer_id == ref.referrer_id, Referral.status == "rewarded"))).scalar() or 0
    if done >= pricing.REFERRAL_REWARD_CAP:
        ref.status = "void"
        return
    await apply(db, ref.referrer_id, "job", pricing.REFERRAL_JOB_CREDITS, "referral", f"referral:{referee.id}")
    ref.status, ref.rewarded_at = "rewarded", datetime.utcnow()


# ── Unlocking a job ──────────────────────────────────────────────────────────

def _no_credits(user: User, kind: str) -> HTTPException:
    what = "this resume" if kind == "resume" else "this job"
    return HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail={
        "error": "no_credits", "kind": kind,
        "message": f"You need a credit to unlock {what}.",
        "credits": balances(user)})


async def ensure_unlocked(db: AsyncSession, user: User, app: Application, kind: str, amount: int = 1) -> None:
    """Spend a credit if this job is not yet unlocked far enough for `kind`, then count the use against the job's
    cap. Raises 402 no_credits or 429 (job limit). The caller commits."""
    if not settings.BILLING_ENABLED:
        return
    app = await _lock_app(db, app.id)
    user = await _lock(db, user.id)
    usage = dict(app.usage or {})
    cap = pricing.JOB_CAPS[kind]
    if usage.get(kind, 0) + amount > cap:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail={
            "error": "job_limit", "kind": kind,
            "message": f"This job has used all {cap} {pricing.LABELS[kind]} it includes. Start a new job for more."})

    need = pricing.REQUIRED_LEVEL[kind]
    level = app.unlock_level or "none"
    covered = level == "full" or (level == "resume" and need == "resume")
    if not covered:
        paid = list(usage.get("_paid", []))
        n = int(usage.get("_unlocks", 0)) + 1
        key = f"unlock:{app.id}:{n}"
        try:
            if need == "resume" and user.credits_resume > 0:
                await apply(db, user.id, "resume", -1, "unlock", key, application_id=app.id)
                new_level, spent = "resume", "resume"
            elif user.credits_job > 0:
                await apply(db, user.id, "job", -1, "unlock", key, application_id=app.id)
                new_level, spent = "full", "job"
            else:
                raise _no_credits(user, need)
        except InsufficientCredits:
            raise _no_credits(user, need)
        app.unlock_level, app.unlocked_at = new_level, datetime.utcnow()
        usage["_unlocks"], usage["_paid"] = n, paid + [spent]
        await reward_referral(db, user)
    usage[kind] = usage.get(kind, 0) + amount
    app.usage = usage


async def release(db: AsyncSession, application_id, kind: str, amount: int = 1) -> None:
    """A run failed: give its use back, and the credit too if nothing for this job has ever worked."""
    if not settings.BILLING_ENABLED or not application_id:
        return
    app = await _lock_app(db, application_id)
    if app is None:
        return
    usage = dict(app.usage or {})
    usage[kind] = max(0, usage.get(kind, 0) - amount)
    if not usage.get("_done") and usage.get("_paid"):
        for spent in usage["_paid"]:
            await apply(db, app.user_id, spent, 1, "refund", f"refund:{app.id}:{usage.get('_unlocks', 0)}:{spent}",
                        application_id=app.id)
        usage["_paid"] = []
        app.unlock_level, app.unlocked_at = "none", None
    app.usage = usage


async def succeeded(db: AsyncSession, application_id) -> None:
    """Something for this job was produced: its credit is now spent for good."""
    if not settings.BILLING_ENABLED or not application_id:
        return
    app = await _lock_app(db, application_id)
    if app is not None:
        usage = dict(app.usage or {})
        usage["_done"] = usage.get("_done", 0) + 1
        app.usage = usage


def parse_uuid(value) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None

