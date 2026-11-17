"""Razorpay (INR; UPI, cards, netbanking) over plain httpx, no SDK.

Flow: the backend creates an order (amount in paise) -> the browser opens Razorpay Checkout with that order id ->
on success the browser sends order_id, payment_id and signature to /billing/razorpay/verify -> we check the HMAC and
add the credits. A webhook (payment.captured / order.paid) does the same if the browser never came back. Both paths
use the same idempotent fulfilment, so whichever arrives first wins and the other changes nothing.

Setup: dashboard.razorpay.com -> Settings -> API keys (test mode first), and Webhooks -> add
https://<your-host>/api/billing/razorpay/webhook with the events payment.captured and order.paid and a secret.
"""
import hashlib
import hmac
import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

API = "https://api.razorpay.com/v1"


def is_enabled() -> bool:
    return settings.BILLING_ENABLED and bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


async def create_order(amount_paise: int, receipt: str, notes: Dict[str, str]) -> Optional[Dict[str, Any]]:
    if not is_enabled():
        return None
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(f"{API}/orders", auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
                                  json={"amount": amount_paise, "currency": "INR", "receipt": receipt[:40], "notes": notes})
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        logger.error("Razorpay order creation failed: %s", exc)
        return None


def _hmac(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_payment_signature(order_id: str, payment_id: str, signature: str) -> bool:
    if not (settings.RAZORPAY_KEY_SECRET and order_id and payment_id and signature):
        return False
    expected = _hmac(settings.RAZORPAY_KEY_SECRET, f"{order_id}|{payment_id}".encode())
    return hmac.compare_digest(expected, signature)


def verify_webhook(body: bytes, signature: str) -> bool:
    if not (settings.RAZORPAY_WEBHOOK_SECRET and signature):
        return False
    return hmac.compare_digest(_hmac(settings.RAZORPAY_WEBHOOK_SECRET, body), signature)
