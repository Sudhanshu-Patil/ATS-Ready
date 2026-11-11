"""
app/services/billing_service.py
────────────────────────────────
PayPal billing (Orders v2 REST via httpx — no SDK dependency).

Each upgrade is a one-time 30-day payment (no recurring subscription), which
keeps the sandbox demo to zero dashboard setup beyond an app's credentials.

FEATURE FLAG:
  BILLING_ENABLED=false → all methods are graceful no-ops.

CHECKOUT FLOW (redirect):
  1. Backend creates an Order → returns order_id + approve_url
  2. Frontend redirects the browser to approve_url (PayPal sandbox login)
  3. PayPal redirects back to /settings?token=<order_id>
  4. Frontend calls POST /billing/sync → backend captures the order and
     applies the plan.

PAYPAL SETUP (one-time):
  1. https://developer.paypal.com → Apps & Credentials → Sandbox → Create App
  2. Copy Client ID / Secret → PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET
  3. Pay with a sandbox *personal* test account (Testing Tools → Sandbox Accounts)
  4. Set BILLING_ENABLED=true
"""
import logging
from typing import Any, Dict, Optional

import httpx

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
    """PayPal REST calls. All methods are graceful no-ops when disabled."""

    def is_enabled(self) -> bool:
        return settings.BILLING_ENABLED and bool(
            settings.PAYPAL_CLIENT_ID and settings.PAYPAL_CLIENT_SECRET
        )

    async def _token(self, client: httpx.AsyncClient) -> str:
        r = await client.post(
            f"{settings.PAYPAL_API}/v1/oauth2/token",
            auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
        )
        r.raise_for_status()
        return r.json()["access_token"]

    async def create_order(self, user_id: str, plan: str, return_url: str) -> Optional[Dict[str, Any]]:
        """Returns {"order_id", "approve_url"}, or None if disabled / failed."""
        if not self.is_enabled():
            logger.info("Billing disabled — skipping order creation")
            return None
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                token = await self._token(client)
                r = await client.post(
                    f"{settings.PAYPAL_API}/v2/checkout/orders",
                    headers={"Authorization": f"Bearer {token}"},
                    json={
                        "intent": "CAPTURE",
                        "purchase_units": [{
                            "custom_id": f"{user_id}:{plan}",
                            "description": f"ATS-Ready {plan} plan (30 days)",
                            "amount": {
                                "currency_code": "USD",
                                "value": f"{PLAN_LIMITS[plan]['price_monthly']:.2f}",
                            },
                        }],
                        "payment_source": {"paypal": {"experience_context": {
                            "return_url": return_url,
                            "cancel_url": return_url,
                            "user_action": "PAY_NOW",
                        }}},
                    },
                )
                r.raise_for_status()
                order = r.json()
                approve = next((l["href"] for l in order["links"]
                                if l["rel"] in ("payer-action", "approve")), None)
                if not approve:
                    return None
                return {"order_id": order["id"], "approve_url": approve}
        except Exception as exc:
            logger.error("PayPal order creation failed: %s", exc)
            return None

    async def capture_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Capture an approved order. Returns the PayPal order JSON or None."""
        if not self.is_enabled():
            return None
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                token = await self._token(client)
                r = await client.post(
                    f"{settings.PAYPAL_API}/v2/checkout/orders/{order_id}/capture",
                    headers={"Authorization": f"Bearer {token}",
                             "Content-Type": "application/json"},
                )
                r.raise_for_status()
                return r.json()
        except Exception as exc:
            logger.error("PayPal capture failed for %s: %s", order_id, exc)
            return None


# ── Singleton ─────────────────────────────────────────────────────────────────
billing_service = BillingService()
