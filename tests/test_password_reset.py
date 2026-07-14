"""
Password reset + email verification flows, and Razorpay webhook signature.
"""
import hashlib
import hmac

from app.config import settings
from app.services.auth_service import (
    create_email_verify_token,
    create_reset_token,
)
from app.services.billing_service import billing_service
from tests.conftest import unique_email
from tests.test_auth import PASSWORD, bearer, login, register


# ── Forgot password ───────────────────────────────────────────────────────────

async def test_forgot_password_identical_response_for_unknown_email(client):
    """Anti-enumeration: same 200 whether or not the account exists."""
    known = unique_email()
    await register(client, known)

    r_known = await client.post("/api/auth/forgot-password", json={"email": known})
    r_unknown = await client.post(
        "/api/auth/forgot-password", json={"email": f"nobody-{known}"}
    )
    assert r_known.status_code == r_unknown.status_code == 200
    assert r_known.json() == r_unknown.json()


# ── Reset password ────────────────────────────────────────────────────────────

async def test_reset_password_full_flow_and_single_use(client):
    email = unique_email()
    reg = await register(client, email)
    user_id = reg.json()["user_id"]

    # Mint the token the email link would carry (fingerprint of current hash)
    me = await client.get("/api/auth/me", headers=bearer(reg))
    assert me.status_code == 200
    # fetch current hash via a fresh login → we don't expose hashes; instead
    # build the token exactly as forgot-password does, from the DB
    from sqlalchemy import select
    from app.db.database import AsyncSessionLocal
    from app.db.models import User

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        token = create_reset_token(user.id, user.hashed_password)

    # Reset works
    r = await client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "brand-new-pass-1"},
    )
    assert r.status_code == 200

    # Old password dead, new one works
    assert (await login(client, email, PASSWORD)).status_code == 401
    assert (await login(client, email, "brand-new-pass-1")).status_code == 200

    # SINGLE-USE: the same token is now invalid (password fingerprint changed)
    r2 = await client.post(
        "/api/auth/reset-password",
        json={"token": token, "new_password": "another-pass-22"},
    )
    assert r2.status_code == 400


async def test_reset_password_garbage_token_rejected(client):
    r = await client.post(
        "/api/auth/reset-password",
        json={"token": "not-a-real-token", "new_password": "whatever-123"},
    )
    assert r.status_code == 400


# ── Email verification ────────────────────────────────────────────────────────

async def test_verify_email_flow(client):
    email = unique_email()
    reg = await register(client, email)
    user_id = reg.json()["user_id"]

    me = await client.get("/api/auth/me", headers=bearer(reg))
    assert me.json()["is_verified"] is False

    token = create_email_verify_token(user_id)
    r = await client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200

    me = await client.get("/api/auth/me", headers=bearer(reg))
    assert me.json()["is_verified"] is True


async def test_verify_email_bad_token_rejected(client):
    r = await client.post("/api/auth/verify-email", json={"token": "junk"})
    assert r.status_code == 400


# ── Razorpay webhook signature (pure unit) ───────────────────────────────────

def test_webhook_signature_roundtrip(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "whsec_test_123")
    body = b'{"event":"subscription.activated"}'
    good = hmac.new(b"whsec_test_123", body, hashlib.sha256).hexdigest()

    assert billing_service.verify_webhook_signature(body, good) is True
    assert billing_service.verify_webhook_signature(body, "tampered") is False
    assert billing_service.verify_webhook_signature(b"other-body", good) is False


def test_webhook_signature_rejected_when_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    assert billing_service.verify_webhook_signature(b"x", "anything") is False


# ── Billing disabled → graceful responses ─────────────────────────────────────

async def test_checkout_graceful_when_billing_disabled(client, monkeypatch):
    # Force the disabled path regardless of what the local .env says —
    # this test is about graceful degradation, not the live config.
    monkeypatch.setattr(settings, "BILLING_ENABLED", False)
    email = unique_email()
    reg = await register(client, email)
    r = await client.post(
        "/api/billing/checkout", json={"plan": "pro"}, headers=bearer(reg)
    )
    assert r.status_code == 200
    assert r.json()["billing_enabled"] is False
    assert r.json()["subscription_id"] is None
