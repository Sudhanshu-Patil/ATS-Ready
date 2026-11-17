"""Credits: the ledger, unlocking a job, per-job caps, refunds, signup grants, referrals and payments."""
import asyncio
import hashlib
import hmac
import json
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import Application, CreditLedger, Payment, Referral, User
from app.services import applications, credits, pricing, razorpay_service
from tests.conftest import unique_email
from tests.test_ats_suggestions import JD_TEXT, _user_with_profile
from tests.test_metabase_experience import bearer, register

JD_A = JD_TEXT
JD_B = "We are hiring a data engineer to build Spark and Airflow pipelines on AWS for our analytics team. " * 3


@pytest.fixture(autouse=True)
def billing(monkeypatch):
    queued = []

    async def fake_enqueue(function, **kwargs):
        queued.append((function, kwargs))
    monkeypatch.setattr("app.api.content_routes.enqueue", fake_enqueue)
    monkeypatch.setattr("app.api.assistant_routes.enqueue", fake_enqueue)
    monkeypatch.setattr(settings, "BILLING_ENABLED", True)
    monkeypatch.setattr(settings, "LLM_FAKE", True)
    return queued


async def give(uid, job=0, resume=0, key=None):
    async with AsyncSessionLocal() as db:
        key = key or uuid.uuid4().hex
        if job:
            await credits.apply(db, uid, "job", job, "admin", f"t:{key}:j")
        if resume:
            await credits.apply(db, uid, "resume", resume, "admin", f"t:{key}:r")
        await db.commit()


async def balance(uid):
    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        return u.credits_job, u.credits_resume


async def new_app(uid, jd=JD_A):
    async with AsyncSessionLocal() as db:
        app = await applications.get_or_create(db, uid, source="resume", jd_text=jd)
        await db.commit()
        return app.id


async def unlock(uid, app_id, kind, amount=1):
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        app = await db.get(Application, app_id)
        await credits.ensure_unlocked(db, user, app, kind, amount)
        await db.commit()


async def usage(app_id):
    async with AsyncSessionLocal() as db:
        app = await db.get(Application, app_id)
        return app.unlock_level, dict(app.usage or {})


# ── who is who ───────────────────────────────────────────────────────────────

def test_gmail_aliases_are_one_person():
    c = credits.canonical_email
    assert c("A.B+x@Gmail.com") == c("ab@googlemail.com") == "ab@gmail.com"
    assert c("a+1@company.com") == "a@company.com"
    assert c("a.b@company.com") == "a.b@company.com"          # dots matter outside Gmail


# ── signup grant ─────────────────────────────────────────────────────────────

async def _register(client, email=None):
    email = email or unique_email()
    reg = await register(client, email)
    uid = uuid.UUID((await client.get("/api/auth/me", headers=bearer(reg))).json()["id"])
    return bearer(reg), uid, email


async def _verify(uid):
    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        u.is_verified = True
        await db.commit()


async def test_starter_credits_come_after_verification_once(client):
    h, uid, _ = await _register(client)
    assert await balance(uid) == (0, 0)
    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        assert not await credits.grant_signup(db, u)               # not verified: nothing
    await _verify(uid)
    for _ in range(3):                                             # visiting the page repeatedly changes nothing
        st = (await client.get("/api/billing/status", headers=h)).json()
    assert st["credits"] == {"job": pricing.SIGNUP_JOB_CREDITS, "resume": pricing.SIGNUP_RESUME_CREDITS}
    assert st["referral_code"] and st["referral_link"].endswith(st["referral_code"])
    assert await balance(uid) == (1, 2)


async def test_one_grant_per_person_not_per_alias_and_none_for_disposable_domains(client):
    tag = uuid.uuid4().hex[:8]
    h1, u1, _ = await _register(client, f"pat.{tag}@gmail.com")
    h2, u2, _ = await _register(client, f"p.a.t.{tag}+x@gmail.com")        # same Gmail person
    h3, u3, _ = await _register(client, f"x{tag}@mailinator.com")
    for u in (u1, u2, u3):
        await _verify(u)
    for h in (h1, h2, h3):
        await client.get("/api/billing/status", headers=h)
    assert await balance(u1) == (1, 2)
    assert await balance(u2) == (0, 0) and await balance(u3) == (0, 0)


# ── unlocking a job ──────────────────────────────────────────────────────────

async def test_a_resume_credit_unlocks_only_the_resume_a_job_credit_unlocks_everything(client):
    _, uid = await _user_with_profile(client)
    await give(uid, job=1, resume=1)
    app = await new_app(uid)
    await unlock(uid, app, "resume")
    assert await balance(uid) == (1, 0) and (await usage(app))[0] == "resume"
    await give(uid, job=0)
    async with AsyncSessionLocal() as db:                          # a cover letter needs the full unlock, and
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        user.credits_job = 0                                        # without a job credit it is refused
        await db.commit()
    with pytest.raises(HTTPException) as e:
        await unlock(uid, app, "cover_letter")
    assert e.value.status_code == 402
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        user.credits_job = 1
        await db.commit()
    # ...which spends the job credit and then covers every kind for this job
    await unlock(uid, app, "cover_letter")
    assert await balance(uid) == (0, 0) and (await usage(app))[0] == "full"
    for kind in ("answers", "interview_prep", "referral", "follow_up", "resume"):
        await unlock(uid, app, kind)
    assert await balance(uid) == (0, 0)                            # nothing more was charged


async def test_no_credit_means_402_and_nothing_changes(client):
    _, uid = await _user_with_profile(client)
    app = await new_app(uid)
    with pytest.raises(HTTPException) as e:
        await unlock(uid, app, "resume")
    assert e.value.status_code == 402 and e.value.detail["error"] == "no_credits"
    assert await usage(app) == ("none", {})


async def test_a_job_has_caps_per_kind(client):
    _, uid = await _user_with_profile(client)
    await give(uid, job=1)
    app = await new_app(uid)
    for _ in range(pricing.JOB_CAPS["cover_letter"]):
        await unlock(uid, app, "cover_letter")
    with pytest.raises(HTTPException) as e:
        await unlock(uid, app, "cover_letter")
    assert e.value.status_code == 429 and e.value.detail["error"] == "job_limit"
    with pytest.raises(HTTPException):
        await unlock(uid, app, "answers", pricing.JOB_CAPS["answers"] + 1)     # one batch cannot exceed the cap
    assert await balance(uid) == (0, 0)


async def test_the_same_job_is_paid_for_once_even_when_requests_overlap(client):
    _, uid = await _user_with_profile(client)
    await give(uid, job=1)
    app = await new_app(uid)
    results = await asyncio.gather(*[unlock(uid, app, "cover_letter") for _ in range(3)], return_exceptions=True)
    assert [r for r in results if isinstance(r, Exception)] == []
    assert await balance(uid) == (0, 0)                                          # one credit, three runs
    assert (await usage(app))[1]["cover_letter"] == 3


async def test_two_different_jobs_cannot_share_one_credit(client):
    _, uid = await _user_with_profile(client)
    await give(uid, job=1)
    a, b = await new_app(uid, JD_A), await new_app(uid, JD_B)
    results = await asyncio.gather(unlock(uid, a, "cover_letter"), unlock(uid, b, "cover_letter"),
                                   return_exceptions=True)
    assert sorted(type(r).__name__ for r in results) == ["HTTPException", "NoneType"]
    assert await balance(uid) == (0, 0)                                          # never below zero


async def test_a_failed_first_run_gives_the_credit_back_and_a_retry_pays_again(client):
    _, uid = await _user_with_profile(client)
    await give(uid, job=1)
    app = await new_app(uid)
    await unlock(uid, app, "cover_letter")
    assert await balance(uid) == (0, 0)
    async with AsyncSessionLocal() as db:
        await credits.release(db, app, "cover_letter")
        await db.commit()
    assert await balance(uid) == (1, 0) and await usage(app) == ("none", {"_unlocks": 1, "cover_letter": 0, "_paid": []})
    await unlock(uid, app, "cover_letter")                                       # the retry is charged afresh
    assert await balance(uid) == (0, 0)


async def test_once_something_worked_a_later_failure_keeps_the_credit_spent(client):
    _, uid = await _user_with_profile(client)
    await give(uid, job=1)
    app = await new_app(uid)
    await unlock(uid, app, "cover_letter")
    async with AsyncSessionLocal() as db:
        await credits.succeeded(db, app)
        await db.commit()
    await unlock(uid, app, "cover_letter")
    async with AsyncSessionLocal() as db:
        await credits.release(db, app, "cover_letter")
        await db.commit()
    assert await balance(uid) == (0, 0)
    level, used = await usage(app)
    assert level == "full" and used["cover_letter"] == 1


async def test_the_ledger_never_applies_a_key_twice(client):
    _, uid = await _user_with_profile(client)
    async with AsyncSessionLocal() as db:
        assert await credits.apply(db, uid, "job", 5, "admin", f"once:{uid}")
        assert not await credits.apply(db, uid, "job", 5, "admin", f"once:{uid}")
        await db.commit()
        rows = (await db.execute(select(CreditLedger).where(CreditLedger.user_id == uid))).scalars().all()
    assert await balance(uid) == (5, 0) and len(rows) == 1 and rows[0].balance_after == 5


# ── routes: the posting decides the job ──────────────────────────────────────

async def test_cover_letter_route_charges_per_posting_not_per_click(client, billing):
    h, uid = await _user_with_profile(client)
    r = await client.post("/api/cover-letter", headers=h, json={"jd_text": JD_A})
    assert r.status_code == 402 and r.json()["detail"]["error"] == "no_credits" and not billing

    await give(uid, job=1)
    again = JD_A.replace(" ", "  ").upper()                    # same posting, different spacing and case
    assert (await client.post("/api/cover-letter", headers=h, json={"jd_text": JD_A})).status_code == 202
    assert (await client.post("/api/cover-letter", headers=h, json={"jd_text": again})).status_code == 202
    assert await balance(uid) == (0, 0)                        # one credit paid for both
    assert billing[-1][1]["application_id"] == billing[0][1]["application_id"]

    other = await client.post("/api/cover-letter", headers=h, json={"jd_text": JD_B})
    assert other.status_code == 402                            # a different posting is a different job
    assert (await client.post("/api/cover-letter", headers=h, json={"jd_text": JD_A})).status_code == 202
    over = await client.post("/api/cover-letter", headers=h, json={"jd_text": JD_A})
    assert over.status_code in (202, 429, 409)                 # the cap (or the 3 in-flight limit) stops it


async def test_failed_queue_gives_the_use_back(client, monkeypatch):
    h, uid = await _user_with_profile(client)
    await give(uid, job=1)

    async def down(*a, **k):
        raise RuntimeError("redis down")
    monkeypatch.setattr("app.api.content_routes.enqueue", down)
    r = await client.post("/api/cover-letter", headers=h, json={"jd_text": JD_A})
    assert r.status_code == 503
    assert await balance(uid) == (1, 0)                        # not charged for a job that never ran


async def test_assistant_questions_count_against_the_job_and_facts_do_not_rerun_for_nothing(client, billing):
    h, uid = await _user_with_profile(client)
    await give(uid, job=1)
    r = await client.post("/api/assistant/requests", headers=h, json={
        "client_request_id": uuid.uuid4().hex, "questions": ["Why this role?", "What is your notice period?"],
        "jd_text": JD_A, "track": False})                    # billing on: every answer belongs to a job
    assert r.status_code == 202 and r.json()["application_id"]
    assert await balance(uid) == (0, 0)
    assert (await usage(uuid.UUID(r.json()["application_id"])))[1]["answers"] == 2
    queued = len(billing)
    rid = r.json()["id"]
    ok = await client.post(f"/api/assistant/requests/{rid}/facts", headers=h,
                           json={"field": "notice_period", "value": "30 days"})
    assert ok.status_code == 202 and len(billing) == queued    # no question was waiting for it: nothing queued


# ── referrals ────────────────────────────────────────────────────────────────

async def test_referrer_is_rewarded_when_the_invited_person_starts_a_job(client):
    h1, ref, _ = await _register(client)
    async with AsyncSessionLocal() as db:
        referrer = (await db.execute(select(User).where(User.id == ref))).scalar_one()
        await credits.ensure_codes(db, referrer)
        await db.commit()
        code = referrer.referral_code
    reg = await client.post("/api/auth/register", json={
        "email": unique_email(), "password": "pw-for-tests-123", "full_name": "Invited", "ref": code})
    assert reg.status_code == 201
    invited = uuid.UUID(reg.json()["user_id"])
    async with AsyncSessionLocal() as db:
        link = (await db.execute(select(Referral).where(Referral.referee_id == invited))).scalar_one()
        assert link.referrer_id == ref and link.status == "pending"

    await give(invited, job=1)
    await _verify(invited)
    app = await new_app(invited)
    assert await balance(ref) == (0, 0)                        # not yet: nothing started
    await unlock(invited, app, "cover_letter")
    assert await balance(ref) == (pricing.REFERRAL_JOB_CREDITS, 0)
    async with AsyncSessionLocal() as db:                      # replay: still one reward
        invited_user = (await db.execute(select(User).where(User.id == invited))).scalar_one()
        await credits.reward_referral(db, invited_user)
        await db.commit()
    assert await balance(ref) == (1, 0)


async def test_nobody_is_rewarded_for_inviting_themselves_or_with_an_unknown_code(client):
    _, uid, email = await _register(client)
    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(User).where(User.id == uid))).scalar_one()
        await credits.ensure_codes(db, u)
        await db.commit()
        mine = u.referral_code
    own = await client.post("/api/auth/register", json={        # an alias of the same Gmail-style address
        "email": email.replace("@", "+me@"), "password": "pw-for-tests-123", "ref": mine})
    junk = await client.post("/api/auth/register", json={
        "email": unique_email(), "password": "pw-for-tests-123", "ref": "nope1234"})
    assert own.status_code == 201 and junk.status_code == 201
    async with AsyncSessionLocal() as db:
        n = (await db.execute(select(Referral).where(Referral.referrer_id == uid))).scalars().all()
    assert n == []


# ── payments ─────────────────────────────────────────────────────────────────

SECRET, WEBHOOK = "rzp_test_secret", "whsec_test"


@pytest.fixture
def razorpay(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_test_key")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_SECRET", SECRET)
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", WEBHOOK)

    async def fake_order(amount, receipt, notes):
        return {"id": "order_" + uuid.uuid4().hex[:14]}
    monkeypatch.setattr(razorpay_service, "create_order", fake_order)


def _sig(order, pay, secret=SECRET):
    return hmac.new(secret.encode(), f"{order}|{pay}".encode(), hashlib.sha256).hexdigest()


async def test_razorpay_checkout_verify_credits_once(client, razorpay):
    h, uid = await _user_with_profile(client)
    co = (await client.post("/api/billing/checkout", headers=h, json={"pack_id": "starter", "provider": "razorpay"})).json()
    assert co["amount"] == 4900 and co["currency"] == "INR" and co["key_id"] == "rzp_test_key"
    pay = "pay_" + uuid.uuid4().hex[:12]

    bad = await client.post("/api/billing/razorpay/verify", headers=h,
                            json={"order_id": co["order_id"], "payment_id": pay, "signature": "0" * 64})
    assert bad.status_code == 400 and await balance(uid) == (0, 0)

    body = {"order_id": co["order_id"], "payment_id": pay, "signature": _sig(co["order_id"], pay)}
    assert (await client.post("/api/billing/razorpay/verify", headers=h, json=body)).status_code == 200
    assert (await client.post("/api/billing/razorpay/verify", headers=h, json=body)).status_code == 200    # replay
    assert await balance(uid) == (6, 0)

    other = bearer(await register(client, unique_email()))      # someone else cannot redeem this order
    assert (await client.post("/api/billing/razorpay/verify", headers=other, json=body)).status_code == 400


async def test_webhook_credits_when_the_browser_never_returned_and_rejects_forgeries(client, razorpay):
    h, uid = await _user_with_profile(client)
    co = (await client.post("/api/billing/checkout", headers=h, json={"pack_id": "single", "provider": "razorpay"})).json()
    event = {"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_" + uuid.uuid4().hex[:12], "order_id": co["order_id"], "amount": 1000, "currency": "INR"}}}}
    raw = json.dumps(event).encode()
    sign = hmac.new(WEBHOOK.encode(), raw, hashlib.sha256).hexdigest()

    forged = await client.post("/api/billing/razorpay/webhook", content=raw, headers={"x-razorpay-signature": "bad"})
    assert forged.status_code == 400 and await balance(uid) == (0, 0)
    for _ in range(2):                                          # delivered twice, credited once
        ok = await client.post("/api/billing/razorpay/webhook", content=raw, headers={"x-razorpay-signature": sign})
        assert ok.status_code == 200
    assert await balance(uid) == (1, 0)

    wrong = json.loads(raw)
    wrong["payload"]["payment"]["entity"]["amount"] = 100       # paid less than the pack costs
    h2, uid2 = await _user_with_profile(client)
    co2 = (await client.post("/api/billing/checkout", headers=h2, json={"pack_id": "power", "provider": "razorpay"})).json()
    wrong["payload"]["payment"]["entity"]["order_id"] = co2["order_id"]
    raw2 = json.dumps(wrong).encode()
    await client.post("/api/billing/razorpay/webhook", content=raw2, headers={
        "x-razorpay-signature": hmac.new(WEBHOOK.encode(), raw2, hashlib.sha256).hexdigest()})
    assert await balance(uid2) == (0, 0)


async def test_paypal_is_usd_and_not_for_the_single_pack(client, monkeypatch):
    h, uid = await _user_with_profile(client)
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_ID", "x")
    monkeypatch.setattr(settings, "PAYPAL_CLIENT_SECRET", "y")
    seen = {}

    async def fake_create(custom_id, description, amount_cents, return_url):
        seen.update(custom=custom_id, cents=amount_cents)
        return {"order_id": "PP-" + uuid.uuid4().hex[:10], "approve_url": "https://paypal.example/approve"}

    async def fake_capture(order_id):
        return {"status": "COMPLETED", "purchase_units": [{"payments": {"captures": [
            {"id": "cap1", "status": "COMPLETED", "custom_id": str(uid)}]}}]}
    monkeypatch.setattr("app.services.billing_service.billing_service.create_order", fake_create)
    monkeypatch.setattr("app.services.billing_service.billing_service.capture_order", fake_capture)

    assert (await client.post("/api/billing/checkout", headers=h, json={"pack_id": "single", "provider": "paypal"})).status_code == 422
    co = (await client.post("/api/billing/checkout", headers=h, json={"pack_id": "hunt", "provider": "paypal"})).json()
    assert seen["cents"] == 599 and seen["custom"] == str(uid) and co["approve_url"]
    for _ in range(2):
        assert (await client.post("/api/billing/sync", headers=h, json={"order_id": co["order_id"]})).status_code == 200
    assert await balance(uid) == (15, 0)
    async with AsyncSessionLocal() as db:
        p = (await db.execute(select(Payment).where(Payment.user_id == uid))).scalar_one()
    assert p.status == "paid" and p.currency == "USD"


async def test_catalog_is_public_and_prices_are_in_rupees(client):
    r = await client.get("/api/billing/catalog")
    assert r.status_code == 200
    packs = {p["id"]: p for p in r.json()["packs"]}
    assert packs["single"]["inr"] == 1000 and packs["single"]["credits"] == 1
    assert packs["power"]["per_credit_inr"] < packs["starter"]["per_credit_inr"] < packs["single"]["per_credit_inr"]
    assert r.json()["signup"] == {"job": 1, "resume": 2}


# ── one job, every tool: the posting is entered once ─────────────────────────

async def test_a_job_started_once_serves_every_tool_without_pasting_again(client, billing):
    h, uid = await _user_with_profile(client)
    await give(uid, job=1)
    job = (await client.post("/api/applications", headers=h, json={
        "jd_text": JD_A, "company": "Acme", "role": "Backend Engineer"})).json()
    assert job["unlock_level"] == "none" and job["has_jd"]

    # the cover letter and the interview prep need nothing but the job id; one credit pays for both
    cl = await client.post("/api/cover-letter", headers=h, json={"application_id": job["id"]})
    pr = await client.post("/api/interview-prep", headers=h, json={"application_id": job["id"]})
    assert cl.status_code == 202 and pr.status_code == 202
    assert cl.json()["application_id"] == pr.json()["application_id"] == job["id"]
    assert await balance(uid) == (0, 0)
    assert billing[0][1]["jd_text"].strip() == JD_A.strip()          # the saved posting, not something sent now

    detail = (await client.get(f"/api/applications/{job['id']}", headers=h)).json()
    assert detail["unlock_level"] == "full" and detail["usage"] == {"cover_letter": 1, "interview_prep": 1}
    assert detail["caps"]["cover_letter"] == 3
    assert [c["status"] for c in detail["artifacts"]["cover_letters"]] == ["pending"]
    assert len(detail["artifacts"]["interview_preps"]) == 1 and detail["artifacts"]["resumes"] == []

    # pasting the same posting elsewhere lands on the same job (no second charge)
    assert (await client.post("/api/cover-letter", headers=h, json={"jd_text": JD_A})).status_code == 202
    assert await balance(uid) == (0, 0)


async def test_nobody_can_use_someone_elses_job_or_an_unknown_one(client):
    h, uid = await _user_with_profile(client)
    job = (await client.post("/api/applications", headers=h, json={"jd_text": JD_A, "company": "Acme", "role": "Dev"})).json()
    h2, uid2 = await _user_with_profile(client)
    await give(uid2, job=1)
    assert (await client.post("/api/cover-letter", headers=h2, json={"application_id": job["id"]})).status_code == 404
    assert (await client.post("/api/cover-letter", headers=h2, json={"application_id": "not-a-uuid"})).status_code == 404
    assert (await client.get(f"/api/applications/{job['id']}", headers=h2)).status_code == 404
    assert await balance(uid2) == (1, 0)


async def test_a_job_without_a_saved_description_asks_for_one(client):
    h, uid = await _user_with_profile(client)
    await give(uid, job=1)
    job = (await client.post("/api/applications", headers=h, json={"company": "Zoho", "role": "Dev"})).json()
    r = await client.post("/api/cover-letter", headers=h, json={"application_id": job["id"]})
    assert r.status_code == 422 and await balance(uid) == (1, 0)


async def test_merging_two_records_of_one_job_keeps_what_was_paid_and_made(client, billing):
    h, uid = await _user_with_profile(client)
    await give(uid, job=1)
    a = (await client.post("/api/applications", headers=h, json={"jd_text": JD_A})).json()
    assert (await client.post("/api/cover-letter", headers=h, json={"application_id": a["id"]})).status_code == 202
    b = (await client.post("/api/applications", headers=h, json={"company": "Acme", "role": "Backend Engineer"})).json()
    assert (await client.patch(f"/api/applications/{a['id']}", headers=h, json={"company": "Acme", "role": "Backend Engineer"})).status_code == 200
    items = (await client.get("/api/applications", headers=h)).json()["items"]
    assert len(items) == 1
    keep = (await client.get(f"/api/applications/{items[0]['id']}", headers=h)).json()
    assert keep["unlock_level"] == "full" and len(keep["artifacts"]["cover_letters"]) == 1
    assert items[0]["id"] == a["id"]                       # the older record survives; the other one is gone
    assert (await client.get(f"/api/applications/{b['id']}", headers=h)).status_code == 404
