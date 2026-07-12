"""
app/api/billing_routes.py
──────────────────────────
Stripe billing endpoints.

All endpoints return graceful responses when BILLING_ENABLED=false,
so you can deploy this code now without Stripe configured.

ENDPOINTS:
  GET  /api/billing/plans          — list plans + pricing (always available)
  GET  /api/billing/status         — current user's subscription status
  POST /api/billing/checkout       — create Stripe Checkout session
  POST /api/billing/portal         — create Stripe Customer Portal session
  POST /api/webhooks/stripe        — Stripe webhook handler (no auth)
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
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


# ── Schemas ───────────────────────────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: str           # "pro" or "team"
    success_path: str = "/dashboard?upgraded=true"
    cancel_path:  str = "/upgrade"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@billing_router.get("/billing/plans")
async def list_plans():
    """
    Return all available plans and their limits.
    Always available — no auth required.
    Used by the pricing page and upgrade modal.
    """
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
    """
    Return the current user's subscription status.
    Used by the dashboard to show plan info and usage.
    """
    from sqlalchemy import func
    from app.db.models import JobApplication

    # Count resumes this month
    now = datetime.now(timezone.utc)
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
        "has_payment_method":  bool(user.stripe_customer_id),
    }


@billing_router.post("/billing/checkout")
async def create_checkout(
    data: CheckoutRequest,
    user: User = Depends(get_current_user),
):
    """
    Create a Stripe Checkout session and return the URL to redirect to.

    When BILLING_ENABLED=false, returns a mock response explaining billing
    is not yet active — no error, just a helpful message.
    """
    if data.plan not in ("pro", "team"):
        raise HTTPException(status_code=422, detail="Plan must be 'pro' or 'team'")

    if not settings.BILLING_ENABLED:
        return {
            "checkout_url": None,
            "message": "Billing is not yet enabled. Contact support to upgrade.",
            "billing_enabled": False,
        }

    base_url = settings.FRONTEND_URL
    checkout_url = billing_service.create_checkout_session(
        user_id=str(user.id),
        user_email=user.email,
        plan=data.plan,
        success_url=f"{base_url}{data.success_path}",
        cancel_url=f"{base_url}{data.cancel_path}",
        stripe_customer_id=user.stripe_customer_id,
    )

    if not checkout_url:
        raise HTTPException(
            status_code=500,
            detail="Failed to create checkout session. Please try again.",
        )

    return {"checkout_url": checkout_url, "billing_enabled": True}


@billing_router.post("/billing/portal")
async def create_portal(
    user: User = Depends(get_current_user),
):
    """
    Create a Stripe Customer Portal session for managing subscriptions,
    payment methods, and invoices.
    """
    if not settings.BILLING_ENABLED:
        return {
            "portal_url": None,
            "message": "Billing is not yet enabled.",
            "billing_enabled": False,
        }

    if not user.stripe_customer_id:
        raise HTTPException(
            status_code=400,
            detail="No billing account found. Please subscribe first.",
        )

    portal_url = billing_service.create_portal_session(
        stripe_customer_id=user.stripe_customer_id,
        return_url=f"{settings.FRONTEND_URL}/dashboard",
    )

    if not portal_url:
        raise HTTPException(status_code=500, detail="Failed to create portal session.")

    return {"portal_url": portal_url, "billing_enabled": True}


# ── Stripe Webhook ────────────────────────────────────────────────────────────
# This endpoint has NO auth — Stripe calls it directly.
# Security is provided by the webhook signature verification.

@billing_router.post("/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    stripe_signature: str = Header(None, alias="stripe-signature"),
):
    """
    Handle Stripe webhook events.

    Events handled:
      checkout.session.completed    → activate subscription
      customer.subscription.updated → sync plan changes
      customer.subscription.deleted → downgrade to free
      invoice.payment_failed        → notify user
    """
    if not settings.BILLING_ENABLED:
        return {"status": "billing_disabled"}

    payload = await request.body()
    event = billing_service.construct_webhook_event(payload, stripe_signature)

    if not event:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event["type"]
    logger.info("Stripe webhook received: %s", event_type)

    try:
        if event_type == "checkout.session.completed":
            await _handle_checkout_completed(event["data"]["object"], db)

        elif event_type == "customer.subscription.updated":
            await _handle_subscription_updated(event["data"]["object"], db)

        elif event_type == "customer.subscription.deleted":
            await _handle_subscription_deleted(event["data"]["object"], db)

        elif event_type == "invoice.payment_failed":
            await _handle_payment_failed(event["data"]["object"], db)

    except Exception as exc:
        logger.error("Webhook handler error for %s: %s", event_type, exc, exc_info=True)
        # Return 200 anyway — Stripe will retry on 4xx/5xx

    return {"status": "ok"}


# ── Webhook handlers ──────────────────────────────────────────────────────────

async def _handle_checkout_completed(session: dict, db: AsyncSession):
    """User completed Stripe checkout → activate their subscription."""
    user_id = session.get("client_reference_id")
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    plan = session.get("metadata", {}).get("plan", "pro")

    if not user_id:
        logger.warning("checkout.session.completed missing client_reference_id")
        return

    from uuid import UUID
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning("checkout.session.completed: user %s not found", user_id)
        return

    user.plan = plan
    user.stripe_customer_id = customer_id
    user.stripe_subscription_id = subscription_id
    user.updated_at = datetime.utcnow()
    await db.commit()

    logger.info("Activated %s plan for user %s", plan, user_id)


async def _handle_subscription_updated(subscription: dict, db: AsyncSession):
    """Subscription changed (upgrade/downgrade) → sync plan."""
    customer_id = subscription.get("customer")
    status = subscription.get("status")

    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return

    if status == "active":
        # Determine plan from price ID
        items = subscription.get("items", {}).get("data", [])
        if items:
            price_id = items[0].get("price", {}).get("id")
            if price_id == settings.STRIPE_PRICE_TEAM:
                user.plan = "team"
            elif price_id == settings.STRIPE_PRICE_PRO:
                user.plan = "pro"
    elif status in ("canceled", "unpaid", "past_due"):
        user.plan = "free"

    user.updated_at = datetime.utcnow()
    await db.commit()
    logger.info("Updated plan to %s for user %s", user.plan, user.id)


async def _handle_subscription_deleted(subscription: dict, db: AsyncSession):
    """Subscription cancelled → downgrade to free."""
    customer_id = subscription.get("customer")

    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return

    user.plan = "free"
    user.stripe_subscription_id = None
    user.updated_at = datetime.utcnow()
    await db.commit()
    logger.info("Downgraded user %s to free plan (subscription cancelled)", user.id)


async def _handle_payment_failed(invoice: dict, db: AsyncSession):
    """Payment failed — log it. Could send email notification here."""
    customer_id = invoice.get("customer")
    amount = invoice.get("amount_due", 0) / 100

    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    if user:
        logger.warning(
            "Payment failed for user %s (email=%s) amount=$%.2f",
            user.id, user.email, amount,
        )
        # TODO Step 5: Send payment failed email via Resend
