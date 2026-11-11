"""
app/api/billing_routes.py
──────────────────────────
PayPal billing endpoints.

All endpoints return graceful responses when BILLING_ENABLED=false,
so this code deploys fine without PayPal configured.

ENDPOINTS:
  GET  /api/billing/plans     — list plans + pricing (no auth)
  GET  /api/billing/status    — current user's plan + usage
  POST /api/billing/checkout  — create PayPal order → frontend redirects to approve_url
  POST /api/billing/sync      — capture the approved order and apply the plan
  POST /api/billing/cancel    — drop back to the free plan
"""
import logging
from datetime import datetime

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.config import settings
from app.db.database import get_db
from app.db.models import User
from app.services.billing_service import PLAN_LIMITS, billing_service

billing_router = APIRouter()
logger = logging.getLogger(__name__)

PLAN_DAYS = 30  # each payment buys 30 days


# ── Schemas ───────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str           # "pro" or "team"


class SyncRequest(BaseModel):
    order_id: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@billing_router.get("/billing/plans")
async def list_plans():
    """All available plans and their limits. No auth — used by pricing UI."""
    return {
        "billing_enabled": settings.BILLING_ENABLED,
        "plans": [
            {
                "id":                 plan_id,
                "label":              info["label"],
                "price_monthly":      info["price_monthly"],
                "resumes_per_month":  info["resumes_per_month"],
                "cover_letters":      info["cover_letters"],
                "api_access":         info["api_access"],
            }
            for plan_id, info in PLAN_LIMITS.items()
        ],
    }


@billing_router.get("/billing/status")
async def billing_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Current user's subscription status + this month's usage."""
    from sqlalchemy import func
    from app.db.models import JobApplication

    # Naive UTC on purpose — created_at is a naive TIMESTAMP column; asyncpg
    # rejects tz-aware parameters against it (see plan_limits.py).
    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(JobApplication.id)).where(
            JobApplication.user_id == user.id,
            JobApplication.status == "done",
            JobApplication.created_at >= month_start,
        )
    )
    resumes_this_month = result.scalar() or 0

    limits = PLAN_LIMITS.get(user.plan, PLAN_LIMITS["free"])

    return {
        "plan":                user.plan,
        "plan_label":          limits["label"],
        "billing_enabled":     settings.BILLING_ENABLED,
        "resumes_this_month":  resumes_this_month,
        "resumes_limit":       limits["resumes_per_month"],  # -1 = unlimited
        "cover_letters":       limits["cover_letters"],
        "api_access":          limits["api_access"],
        "plan_expires_at":     str(user.plan_expires_at) if user.plan_expires_at else None,
        "has_subscription":    bool(user.payment_subscription_id),
    }


@billing_router.post("/billing/checkout")
async def create_checkout(
    data: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a PayPal order; the frontend redirects the browser to approve_url."""
    if data.plan not in ("pro", "team"):
        raise HTTPException(status_code=422, detail="Plan must be 'pro' or 'team'")

    if not settings.BILLING_ENABLED:
        return {
            "order_id": None,
            "message": "Billing is not yet enabled. Contact support to upgrade.",
            "billing_enabled": False,
        }

    result = await billing_service.create_order(
        str(user.id), data.plan, f"{settings.FRONTEND_URL}/settings?section=plan"
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to start checkout. Please try again.")

    # Remember the pending order: /billing/sync only captures this exact id,
    # so a user can't redeem someone else's order.
    user.payment_subscription_id = result["order_id"]
    user.updated_at = datetime.utcnow()
    await db.commit()

    return {**result, "plan": data.plan, "billing_enabled": True}


@billing_router.post("/billing/sync")
async def sync_subscription(
    data: SyncRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Capture the order PayPal just approved and grant the plan for 30 days."""
    if not settings.BILLING_ENABLED:
        return {"plan": user.plan, "billing_enabled": False}

    if data.order_id != user.payment_subscription_id:
        raise HTTPException(status_code=400, detail="Unknown order")

    order = await billing_service.capture_order(data.order_id)
    if not order:
        raise HTTPException(status_code=502, detail="Could not capture PayPal payment")

    status = order.get("status")
    unit = (order.get("purchase_units") or [{}])[0]
    capture = (unit.get("payments", {}).get("captures") or [{}])[0]
    if status == "COMPLETED" and capture.get("status") == "COMPLETED":
        owner, _, plan = capture.get("custom_id", "").partition(":")
        if owner != str(user.id) or plan not in ("pro", "team"):
            raise HTTPException(status_code=400, detail="Order does not belong to this user")
        user.plan = plan
        user.plan_expires_at = datetime.utcnow() + timedelta(days=PLAN_DAYS)
        user.payment_subscription_id = None  # order consumed
        user.updated_at = datetime.utcnow()
        await db.commit()
        logger.info("PayPal order %s captured → plan=%s for user %s", data.order_id, plan, user.id)

    return {"plan": user.plan, "order_status": status, "billing_enabled": True}


@billing_router.post("/billing/cancel")
async def cancel_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Payments are one-time, so cancelling just returns the user to free."""
    if not settings.BILLING_ENABLED:
        return {"message": "Billing is not enabled.", "billing_enabled": False}

    user.plan = "free"
    user.plan_expires_at = None
    user.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "Plan cancelled.", "billing_enabled": True}
