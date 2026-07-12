"""
app/api/plan_limits.py
───────────────────────
FastAPI dependencies for enforcing subscription plan limits.

FEATURE FLAG:
  When BILLING_ENABLED=false, all checks pass — everyone is treated as
  having unlimited access. Perfect for development and pre-billing launch.

USAGE IN ROUTES:
  from app.api.plan_limits import check_resume_limit

  @router.post("/generate-resume")
  async def generate_resume(
      request: GenerateResumeRequest,
      db: AsyncSession = Depends(get_db),
      user: User = Depends(check_resume_limit),   # ← enforces limit
  ):
      ...

HOW FREE TIER LIMITS WORK:
  We count JobApplication rows with status="done" in the current calendar
  month for the user. If count >= 3, we raise HTTP 402.
  The check runs before enqueuing to avoid wasting the job slot.
"""
import logging
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.config import settings
from app.db.database import get_db
from app.db.models import JobApplication, User
from app.services.billing_service import PLAN_LIMITS

logger = logging.getLogger(__name__)


async def check_resume_limit(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    """
    Enforce monthly resume generation limit for free plan users.

    Free plan: 3 resumes/month
    Pro/Team:  unlimited

    When BILLING_ENABLED=false, this dependency always passes.
    """
    if not settings.BILLING_ENABLED:
        return user

    limits = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["free"])
    monthly_limit = limits["resumes_per_month"]

    if monthly_limit == -1:
        # Unlimited plan — no check needed
        return user

    # Count completed resumes this calendar month
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(func.count(JobApplication.id)).where(
            JobApplication.user_id == user.id,
            JobApplication.status == "done",
            JobApplication.created_at >= month_start,
        )
    )
    count = result.scalar() or 0

    if count >= monthly_limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error":        "plan_limit_reached",
                "message":      f"You've used {count}/{monthly_limit} resumes this month.",
                "current_plan": user.plan,
                "upgrade_url":  f"{settings.FRONTEND_URL}/upgrade",
            },
        )

    logger.info(
        "Plan check passed: user=%s plan=%s resumes=%d/%d",
        user.id, user.plan, count, monthly_limit,
    )
    return user


async def check_cover_letter_access(
    user: User = Depends(get_current_user),
) -> User:
    """Enforce cover letter access — Pro and Team plans only."""
    if not settings.BILLING_ENABLED:
        return user

    limits = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["free"])
    if not limits["cover_letters"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error":        "feature_not_available",
                "message":      "Cover letters are a Pro feature.",
                "current_plan": user.plan,
                "upgrade_url":  f"{settings.FRONTEND_URL}/upgrade",
            },
        )
    return user


async def check_api_access(
    user: User = Depends(get_current_user),
) -> User:
    """Enforce API access — Team plan only."""
    if not settings.BILLING_ENABLED:
        return user

    limits = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["free"])
    if not limits["api_access"]:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error":        "feature_not_available",
                "message":      "API access is a Team plan feature.",
                "current_plan": user.plan,
                "upgrade_url":  f"{settings.FRONTEND_URL}/upgrade",
            },
        )
    return user
