"""
app/api/billing_routes.py
──────────────────────────
Credit packs. Razorpay takes INR (UPI, cards, netbanking); PayPal takes USD from buyers outside India.

  GET  /api/billing/catalog              — packs and what a credit buys (no auth)
  GET  /api/billing/status               — balance, referral link and stats, recent ledger
  POST /api/billing/checkout             — create an order {pack_id, provider}
  POST /api/billing/razorpay/verify      — the browser reports a finished Razorpay payment
  POST /api/billing/razorpay/webhook     — Razorpay tells us a payment was captured (no browser needed)
  POST /api/billing/sync                 — capture an approved PayPal order

Both gateways end in fulfil(), which credits a payment exactly once whichever path arrives first.
"""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.config import settings
from app.db.database import get_db
from app.db.models import CreditLedger, Payment, Referral, User
from app.services import credits, pricing, razorpay_service
from app.services.billing_service import billing_service

billing_router = APIRouter()
logger = logging.getLogger(__name__)


class CheckoutRequest(BaseModel):
    pack_id: str
    provider: Optional[str] = None            # "razorpay" | "paypal"; default: Razorpay when it is configured


class RazorpayVerify(BaseModel):
    order_id: str
    payment_id: str
    signature: str


class SyncRequest(BaseModel):
    order_id: str


async def fulfil(db: AsyncSession, payment: Payment, provider_payment_id: Optional[str]) -> bool:
    """Add the pack's credits for a paid order, once. Returns True if this call did it."""
    if payment.status == "paid":
        return False
    pack = pricing.PACKS[payment.pack_id]
    done = await credits.apply(db, payment.user_id, "job", pack["credits"], "purchase", f"payment:{payment.id}",
                               payment_id=payment.id)
    payment.status, payment.paid_at = "paid", datetime.utcnow()
    if provider_payment_id:
        payment.provider_payment_id = provider_payment_id
    await db.commit()
    logger.info("Payment %s (%s %s) credited %d job credits to user %s",
                payment.id, payment.provider, payment.pack_id, pack["credits"], payment.user_id)
    return done


@billing_router.get("/billing/catalog")
async def get_catalog():
    """Packs and what a credit includes. No auth: the pricing UI and landing page use it."""
    return {
        "billing_enabled": settings.BILLING_ENABLED,
        "razorpay": razorpay_service.is_enabled(),
        "paypal": billing_service.is_enabled(),
        **pricing.catalog(),
    }


@billing_router.get("/billing/status")
async def billing_status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Balance, the referral link, how referrals are going, and the latest ledger entries."""
    await credits.ensure_codes(db, user)
    await credits.grant_signup(db, user)              # existing accounts get their starter credits on first visit
    await db.commit()
    rewarded = (await db.execute(select(func.count(Referral.id)).where(
        Referral.referrer_id == user.id, Referral.status == "rewarded"))).scalar() or 0
    pending = (await db.execute(select(func.count(Referral.id)).where(
        Referral.referrer_id == user.id, Referral.status == "pending"))).scalar() or 0
    ledger = (await db.execute(select(CreditLedger).where(CreditLedger.user_id == user.id)
                               .order_by(CreditLedger.created_at.desc()).limit(25))).scalars().all()
    return {
        "billing_enabled": settings.BILLING_ENABLED,
        "credits": credits.balances(user),
        "is_verified": user.is_verified,
        "referral_code": user.referral_code,
        "referral_link": f"{settings.FRONTEND_URL}/register?ref={user.referral_code}",
        "referrals": {"rewarded": rewarded, "pending": pending, "cap": pricing.REFERRAL_REWARD_CAP,
                      "reward": pricing.REFERRAL_JOB_CREDITS},
        "ledger": [{"id": str(r.id), "kind": r.kind, "delta": r.delta, "reason": r.reason,
                    "balance_after": r.balance_after, "created_at": r.created_at.isoformat()} for r in ledger],
    }


@billing_router.post("/billing/checkout")
async def create_checkout(data: CheckoutRequest, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    pack = pricing.PACKS.get(data.pack_id)
    if pack is None:
        raise HTTPException(status_code=422, detail="Unknown pack")
    if not settings.BILLING_ENABLED:
        return {"billing_enabled": False, "message": "Payments are not enabled yet."}

    provider = data.provider or ("razorpay" if razorpay_service.is_enabled() else "paypal")
    if provider == "razorpay":
        if not razorpay_service.is_enabled():
            raise HTTPException(status_code=503, detail="Payments are not available right now.")
        order = await razorpay_service.create_order(pack["inr"], f"u{str(user.id)[:8]}-{data.pack_id}",
                                                    {"user_id": str(user.id), "pack_id": data.pack_id})
        if not order:
            raise HTTPException(status_code=502, detail="Could not start the payment. Please try again.")
        db.add(Payment(user_id=user.id, provider="razorpay", provider_order_id=order["id"], pack_id=data.pack_id,
                       amount_minor=pack["inr"], currency="INR"))
        await db.commit()
        return {"billing_enabled": True, "provider": "razorpay", "order_id": order["id"], "amount": pack["inr"],
                "currency": "INR", "key_id": settings.RAZORPAY_KEY_ID, "pack": data.pack_id}

    if provider == "paypal":
        if not billing_service.is_enabled():
            raise HTTPException(status_code=503, detail="Payments are not available right now.")
        if not pack["usd"]:
            raise HTTPException(status_code=422, detail="This pack is sold in rupees only.")
        result = await billing_service.create_order(
            str(user.id), f"ATS-Ready {pack['label']}: {pack['credits']} credits", pack["usd"],
            f"{settings.FRONTEND_URL}/settings?section=billing")
        if not result:
            raise HTTPException(status_code=502, detail="Could not start the payment. Please try again.")
        db.add(Payment(user_id=user.id, provider="paypal", provider_order_id=result["order_id"],
                       pack_id=data.pack_id, amount_minor=pack["usd"], currency="USD"))
        await db.commit()
        return {"billing_enabled": True, "provider": "paypal", **result, "pack": data.pack_id}

    raise HTTPException(status_code=422, detail="provider must be razorpay or paypal")


async def _own_payment(db: AsyncSession, order_id: str, user: User) -> Payment:
    payment = (await db.execute(select(Payment).where(
        Payment.provider_order_id == order_id, Payment.user_id == user.id))).scalar_one_or_none()
    if payment is None:
        raise HTTPException(status_code=400, detail="Unknown order")
    return payment


@billing_router.post("/billing/razorpay/verify")
async def razorpay_verify(data: RazorpayVerify, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    payment = await _own_payment(db, data.order_id, user)
    if payment.provider != "razorpay" or not razorpay_service.verify_payment_signature(
            data.order_id, data.payment_id, data.signature):
        raise HTTPException(status_code=400, detail="Payment could not be verified")
    await fulfil(db, payment, data.payment_id)
    await db.refresh(user)
    return {"credits": credits.balances(user), "status": payment.status}


@billing_router.post("/billing/razorpay/webhook")
async def razorpay_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Server-to-server: credits the payment even if the buyer closed the tab. Authenticated by the signature."""
    body = await request.body()
    if not razorpay_service.verify_webhook(body, request.headers.get("x-razorpay-signature", "")):
        raise HTTPException(status_code=400, detail="Bad signature")
    try:
        event = json.loads(body)
        entity = event["payload"]["payment"]["entity"]
    except (ValueError, KeyError, TypeError):
        return {"ok": True}                               # an event we do not act on
    if event.get("event") not in ("payment.captured", "order.paid"):
        return {"ok": True}
    payment = (await db.execute(select(Payment).where(
        Payment.provider_order_id == entity.get("order_id"), Payment.provider == "razorpay"))).scalar_one_or_none()
    if payment is not None and entity.get("amount") == payment.amount_minor and entity.get("currency") == "INR":
        await fulfil(db, payment, entity.get("id"))
    return {"ok": True}


@billing_router.post("/billing/sync")
async def sync_paypal(data: SyncRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Capture the PayPal order the buyer just approved and add the credits."""
    if not settings.BILLING_ENABLED:
        return {"billing_enabled": False}
    payment = await _own_payment(db, data.order_id, user)
    if payment.status == "paid":
        return {"credits": credits.balances(user), "status": "paid"}
    order = await billing_service.capture_order(data.order_id)
    if not order:
        raise HTTPException(status_code=502, detail="Could not capture the PayPal payment")
    unit = (order.get("purchase_units") or [{}])[0]
    capture = (unit.get("payments", {}).get("captures") or [{}])[0]
    if order.get("status") == "COMPLETED" and capture.get("status") == "COMPLETED":
        if capture.get("custom_id") != str(user.id):
            raise HTTPException(status_code=400, detail="Order does not belong to this user")
        await fulfil(db, payment, capture.get("id"))
        await db.refresh(user)
    return {"credits": credits.balances(user), "status": payment.status, "order_status": order.get("status")}
