"""
app/api/billing_routes.py
──────────────────────────
Razorpay billing endpoints.

All endpoints return graceful responses when BILLING_ENABLED=false,
so this code deploys fine without Razorpay configured.

ENDPOINTS:
  GET  /api/billing/plans            — list plans + pricing (no auth)
  GET  /api/billing/status           — current user's subscription status
  POST /api/billing/checkout         — create subscription → frontend opens
                                       the Razorpay Checkout modal with it
  POST /api/billing/sync             — poll Razorpay for the subscription's
                                       state and apply it (dev fallback:
                                       Razorpay can't webhook localhost)
  POST /api/billing/cancel           — cancel at cycle end
  POST /api/webhooks/razorpay        — webhook handler (signature-verified)
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
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

# Razorpay subscription states that mean "paid and active"
_ACTIVE_STATES = {"active", "authenticated", "completed"}
_DEAD_STATES = {"cancelled", "halted", "expired"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str           # "pro" or "team"


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
    """
    Create a Razorpay Subscription. The frontend opens Razorpay Checkout
    (modal, not a redirect) with the returned subscription_id + key_id.
    """
    if data.plan not in ("pro", "team"):
        raise HTTPException(status_code=422, detail="Plan must be 'pro' or 'team'")

    if not settings.BILLING_ENABLED:
        return {
            "subscription_id": None,
            "message": "Billing is not yet enabled. Contact support to upgrade.",
            "billing_enabled": False,
        }

    result = await billing_service.create_subscription(str(user.id), data.plan)
    if not result:
        raise HTTPException(
            status_code=500,
            detail="Failed to create subscription. Please try again.",
        )

    # Remember the pending subscription so /billing/sync and the webhook can
    # both resolve it back to this user.
    user.payment_subscription_id = result["subscription_id"]
    user.updated_at = datetime.utcnow()
    await db.commit()

    return {
        "subscription_id": result["subscription_id"],
        "key_id":          result["key_id"],
        "plan":            data.plan,
        "user_email":      user.email,
        "user_name":       user.full_name or "",
        "billing_enabled": True,
    }


@billing_router.post("/billing/sync")
async def sync_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch the user's subscription state from Razorpay and apply it.

    This is the localhost-friendly alternative to webhooks (Razorpay cannot
    reach a dev machine): the frontend calls it right after the checkout
    modal reports success. Also useful as a manual "refresh my plan" action.
    """
    if not settings.BILLING_ENABLED:
        return {"plan": user.plan, "billing_enabled": False}

    if not user.payment_subscription_id:
        return {"plan": user.plan, "message": "No subscription on file"}

    sub = await billing_service.fetch_subscription(user.payment_subscription_id)
    if not sub:
        raise HTTPException(status_code=502, detail="Could not reach Razorpay")

    status = sub.get("status")
    plan = sub.get("notes", {}).get("plan", "pro")

    if status in _ACTIVE_STATES:
        user.plan = plan
    elif status in _DEAD_STATES:
        user.plan = "free"
        user.payment_subscription_id = None
    # pending/created states leave the plan untouched

    user.updated_at = datetime.utcnow()
    await db.commit()
    logger.info("Synced subscription %s (status=%s) → plan=%s for user %s",
                sub.get("id"), status, user.plan, user.id)
    return {"plan": user.plan, "subscription_status": status, "billing_enabled": True}


@billing_router.post("/billing/cancel")
async def cancel_subscription(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel at cycle end — access continues until the paid period expires."""
    if not settings.BILLING_ENABLED:
        return {"message": "Billing is not enabled.", "billing_enabled": False}

    if not user.payment_subscription_id:
        raise HTTPException(status_code=400, detail="No active subscription to cancel")

    ok = await billing_service.cancel_subscription(user.payment_subscription_id)
    if not ok:
        raise HTTPException(status_code=502, detail="Could not cancel subscription")

    return {"message": "Subscription will end at the current billing cycle.",
            "billing_enabled": True}


# ── Razorpay Webhook ──────────────────────────────────────────────────────────
# No auth — Razorpay calls it directly; security = HMAC signature verification.

@billing_router.post("/webhooks/razorpay", include_in_schema=False)
async def razorpay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_razorpay_signature: str = Header(None, alias="X-Razorpay-Signature"),
):
    """
    Events handled:
      subscription.activated / subscription.charged → set the paid plan
      subscription.cancelled / subscription.halted  → downgrade to free
    """
    if not settings.BILLING_ENABLED:
        return {"status": "billing_disabled"}

    payload = await request.body()
    if not billing_service.verify_webhook_signature(payload, x_razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event = await request.json()
    event_type = event.get("event", "")
    logger.info("Razorpay webhook received: %s", event_type)

    try:
        sub = (
            event.get("payload", {})
            .get("subscription", {})
            .get("entity", {})
        )
        subscription_id = sub.get("id")
        plan = sub.get("notes", {}).get("plan", "pro")

        if not subscription_id:
            return {"status": "ignored"}

        result = await db.execute(
            select(User).where(User.payment_subscription_id == subscription_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            # Fall back to the user_id we stored in subscription notes
            user_id = sub.get("notes", {}).get("user_id")
            if user_id:
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalar_one_or_none()
        if not user:
            logger.warning("Webhook %s: no user for subscription %s",
                           event_type, subscription_id)
            return {"status": "user_not_found"}

        if event_type in ("subscription.activated", "subscription.charged"):
            user.plan = plan
            user.payment_subscription_id = subscription_id
        elif event_type in ("subscription.cancelled", "subscription.halted"):
            user.plan = "free"
            user.payment_subscription_id = None

        user.updated_at = datetime.utcnow()
        await db.commit()
        logger.info("Webhook %s applied → plan=%s for user %s",
                    event_type, user.plan, user.id)

    except Exception as exc:
        logger.error("Webhook handler error for %s: %s", event_type, exc, exc_info=True)
        # Return 200 anyway — Razorpay retries on non-2xx and the sync
        # endpoint provides a recovery path.

    return {"status": "ok"}
