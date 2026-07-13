"""
app/services/billing_service.py
────────────────────────────────
Razorpay billing integration (raw REST via httpx — no SDK dependency).

WHY RAZORPAY:
  No setup fee, no monthly fee — a per-transaction cut (~2%) deducted from
  payments you receive. Test Mode works immediately after signup with zero
  cost; KYC is only required to accept real money in Live Mode.

FEATURE FLAG:
  BILLING_ENABLED=false → all methods are graceful no-ops and the app runs
  normally with plans as plain DB flags.

CHECKOUT FLOW (differs from Stripe's redirect model):
  1. Backend creates a Subscription → returns subscription_id
  2. Frontend opens Razorpay Checkout (checkout.js modal) with that id
  3. User pays inside the modal
  4a. Webhook (public deployments): subscription.activated/charged → plan set
  4b. Sync endpoint (local dev — Razorpay can't reach localhost webhooks):
      frontend calls POST /billing/sync after the modal reports success;
      backend fetches the subscription from Razorpay and applies its status.

RAZORPAY SETUP (manual, one-time):
  1. Sign up at https://razorpay.com → Test Mode is on by default
  2. Settings → API Keys → Generate Test Key → RAZORPAY_KEY_ID / KEY_SECRET
  3. Subscriptions → Plans → create "Pro" and "Team" monthly plans →
     copy the plan_xxx ids into RAZORPAY_PLAN_PRO / RAZORPAY_PLAN_TEAM
  4. Set BILLING_ENABLED=true
  5. (When deployed publicly) Settings → Webhooks → add
     https://<your-domain>/api/webhooks/razorpay with events
     subscription.activated, subscription.charged, subscription.cancelled,
     subscription.halted → RAZORPAY_WEBHOOK_SECRET
"""
import hashlib
import hmac
import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

RAZORPAY_API = "https://api.razorpay.com/v1"

# ── Plan definitions ──────────────────────────────────────────────────────────

PLAN_LIMITS = {
    "free": {
        "resumes_per_month": 3,
        "cover_letters":     False,
        "api_access":        False,
        "label":             "Free",
        "price_monthly":     0,
    },
    "pro": {
        "resumes_per_month": -1,      # -1 = unlimited
        "cover_letters":     True,
        "api_access":        False,
        "label":             "Pro",
        "price_monthly":     19,
    },
    "team": {
        "resumes_per_month": -1,
        "cover_letters":     True,
        "api_access":        True,
        "label":             "Team",
        "price_monthly":     49,
    },
}


def get_plan_limits(plan: str) -> dict:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])


# ── Billing service ───────────────────────────────────────────────────────────

class BillingService:
    """Razorpay REST calls. All methods are graceful no-ops when disabled."""

    def is_enabled(self) -> bool:
        return settings.BILLING_ENABLED and bool(
            settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET
        )

    def _auth(self) -> tuple:
        # Razorpay uses HTTP Basic auth: key_id as user, key_secret as password
        return (settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)

    def _plan_id(self, plan: str) -> Optional[str]:
        return {
            "pro":  settings.RAZORPAY_PLAN_PRO,
            "team": settings.RAZORPAY_PLAN_TEAM,
        }.get(plan) or None

    # ── Subscriptions ─────────────────────────────────────────────────────────

    async def create_subscription(self, user_id: str, plan: str) -> Optional[Dict[str, Any]]:
        """
        Create a Razorpay Subscription for the plan.
        Returns {"subscription_id", "key_id"} for the frontend checkout modal,
        or None if billing is disabled / misconfigured.
        """
        if not self.is_enabled():
            logger.info("Billing disabled — skipping subscription creation")
            return None

        plan_id = self._plan_id(plan)
        if not plan_id:
            logger.error("Razorpay plan id not configured for plan=%s", plan)
            return None

        try:
            async with httpx.AsyncClient(auth=self._auth(), timeout=20) as client:
                r = await client.post(f"{RAZORPAY_API}/subscriptions", json={
                    "plan_id":         plan_id,
                    "total_count":     12,        # bill monthly for up to 12 cycles
                    "customer_notify": 1,
                    "notes":           {"user_id": user_id, "plan": plan},
                })
                r.raise_for_status()
                sub = r.json()
                logger.info("Created Razorpay subscription %s for user %s plan=%s",
                            sub.get("id"), user_id, plan)
                return {
                    "subscription_id": sub.get("id"),
                    "key_id":          settings.RAZORPAY_KEY_ID,
                }
        except httpx.HTTPStatusError as exc:
            logger.error("Razorpay subscription creation failed: %s — %s",
                         exc.response.status_code, exc.response.text[:300])
            return None
        except Exception as exc:
            logger.error("Razorpay subscription creation failed: %s", exc)
            return None

    async def fetch_subscription(self, subscription_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a subscription's current state from Razorpay."""
        if not self.is_enabled():
            return None
        try:
            async with httpx.AsyncClient(auth=self._auth(), timeout=20) as client:
                r = await client.get(f"{RAZORPAY_API}/subscriptions/{subscription_id}")
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            logger.error("Razorpay subscription fetch failed for %s: %s",
                         subscription_id, exc)
            return None

    async def cancel_subscription(self, subscription_id: str) -> bool:
        """Cancel at cycle end (user keeps access until the paid period ends)."""
        if not self.is_enabled():
            return False
        try:
            async with httpx.AsyncClient(auth=self._auth(), timeout=20) as client:
                r = await client.post(
                    f"{RAZORPAY_API}/subscriptions/{subscription_id}/cancel",
                    json={"cancel_at_cycle_end": 1},
                )
                r.raise_for_status()
                return True
        except Exception as exc:
            logger.error("Razorpay cancel failed for %s: %s", subscription_id, exc)
            return False

    # ── Webhook verification ──────────────────────────────────────────────────

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Razorpay signs webhooks with HMAC-SHA256 over the raw body using the
        webhook secret (X-Razorpay-Signature header). Plain hmac — no SDK.
        """
        if not settings.RAZORPAY_WEBHOOK_SECRET or not signature:
            return False
        expected = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)


# ── Singleton ─────────────────────────────────────────────────────────────────
billing_service = BillingService()
