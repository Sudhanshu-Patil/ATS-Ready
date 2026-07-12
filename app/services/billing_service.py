"""
app/services/billing_service.py
────────────────────────────────
Stripe billing integration.

FEATURE FLAG:
  Set BILLING_ENABLED=false in .env to disable all billing logic.
  The app runs normally — everyone gets treated as "pro" plan.
  Set BILLING_ENABLED=true when you're ready to charge users.

PLANS:
  free  — 3 resumes/month, no cover letters
  pro   — $19/mo, unlimited resumes + cover letters
  team  — $49/mo, pro + API access + 5 seats

STRIPE SETUP (when ready):
  1. Create account at https://stripe.com
  2. Dashboard → Products → Create product "ATS-Ready Pro" ($19/mo)
  3. Dashboard → Products → Create product "ATS-Ready Team" ($49/mo)
  4. Copy the Price IDs (price_xxx) into .env
  5. Set STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET from dashboard
  6. Set BILLING_ENABLED=true
"""
import logging
from datetime import datetime
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

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
    """
    Wraps Stripe API calls.  All methods are no-ops when BILLING_ENABLED=false.
    """

    def _get_stripe(self):
        """Return the stripe module, configured with the secret key."""
        if not settings.BILLING_ENABLED:
            return None
        try:
            import stripe
            stripe.api_key = settings.STRIPE_SECRET_KEY
            return stripe
        except ImportError:
            logger.error("stripe package not installed — run: pip install stripe")
            return None

    def is_enabled(self) -> bool:
        return settings.BILLING_ENABLED and bool(settings.STRIPE_SECRET_KEY)

    # ── Checkout ──────────────────────────────────────────────────────────────

    def create_checkout_session(
        self,
        user_id: str,
        user_email: str,
        plan: str,          # "pro" or "team"
        success_url: str,
        cancel_url: str,
        stripe_customer_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Create a Stripe Checkout session.
        Returns the checkout URL to redirect the user to, or None if billing is off.
        """
        if not self.is_enabled():
            logger.info("Billing disabled — skipping checkout session creation")
            return None

        stripe = self._get_stripe()
        if not stripe:
            return None

        price_id = (
            settings.STRIPE_PRICE_PRO
            if plan == "pro"
            else settings.STRIPE_PRICE_TEAM
        )

        if not price_id:
            logger.error("Stripe price ID not configured for plan=%s", plan)
            return None

        params = {
            "mode":               "subscription",
            "line_items":         [{"price": price_id, "quantity": 1}],
            "success_url":        success_url,
            "cancel_url":         cancel_url,
            "client_reference_id": user_id,
            "metadata":           {"user_id": user_id, "plan": plan},
            "subscription_data":  {"metadata": {"user_id": user_id}},
        }

        if stripe_customer_id:
            params["customer"] = stripe_customer_id
        else:
            params["customer_email"] = user_email

        try:
            session = stripe.checkout.Session.create(**params)
            logger.info("Created checkout session %s for user %s plan=%s",
                       session.id, user_id, plan)
            return session.url
        except Exception as exc:
            logger.error("Stripe checkout session creation failed: %s", exc)
            return None

    # ── Customer Portal ───────────────────────────────────────────────────────

    def create_portal_session(
        self,
        stripe_customer_id: str,
        return_url: str,
    ) -> Optional[str]:
        """
        Create a Stripe Customer Portal session for managing subscriptions.
        Returns the portal URL, or None if billing is disabled.
        """
        if not self.is_enabled():
            return None

        stripe = self._get_stripe()
        if not stripe:
            return None

        try:
            session = stripe.billing_portal.Session.create(
                customer=stripe_customer_id,
                return_url=return_url,
            )
            return session.url
        except Exception as exc:
            logger.error("Stripe portal session creation failed: %s", exc)
            return None

    # ── Webhook processing ────────────────────────────────────────────────────

    def construct_webhook_event(self, payload: bytes, sig_header: str):
        """Verify and parse a Stripe webhook event."""
        if not self.is_enabled():
            return None

        stripe = self._get_stripe()
        if not stripe:
            return None

        try:
            return stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except stripe.error.SignatureVerificationError as exc:
            logger.warning("Stripe webhook signature invalid: %s", exc)
            return None
        except Exception as exc:
            logger.error("Stripe webhook construction failed: %s", exc)
            return None


# ── Singleton ─────────────────────────────────────────────────────────────────
billing_service = BillingService()
