"""Admin stats access, usage accounting and spend caps."""
import time

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import UsageEvent, User
from app.services import usage
from tests.conftest import unique_email
from tests.test_metabase_experience import bearer, register


async def make_admin(monkeypatch, client):
    email = unique_email()
    r = await register(client, email)
    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(User).where(User.email == email))).scalar_one()
        u.is_verified = True
        await db.commit()
    monkeypatch.setattr(settings, "ADMIN_EMAILS", f"someone@else.com, {email.upper()}")
    return r, email


async def test_admin_stats_only_for_allowlisted_verified_users(client, monkeypatch):
    normal = await register(client, unique_email())
    assert (await client.get("/api/admin/stats", headers=bearer(normal))).status_code == 404
    admin, _ = await make_admin(monkeypatch, client)
    r = await client.get("/api/admin/stats", headers=bearer(admin))
    assert r.status_code == 200
    body = r.json()
    assert body["users"]["total"] >= 2 and len(body["daily"]) == 14
    assert (await client.get("/api/auth/me", headers=bearer(admin))).json()["is_admin"] is True
    assert (await client.get("/api/auth/me", headers=bearer(normal))).json()["is_admin"] is False


async def test_unverified_allowlisted_user_is_not_admin(client, monkeypatch):
    email = unique_email()
    r = await register(client, email)
    monkeypatch.setattr(settings, "ADMIN_EMAILS", email)
    assert (await client.get("/api/admin/stats", headers=bearer(r))).status_code == 404


async def test_tally_records_tokens_and_event(client):
    r = await register(client, unique_email())
    uid = (await client.get("/api/auth/me", headers=bearer(r))).json()["id"]
    import uuid

    tally = usage.start_tally()
    usage.add_usage(1200)
    usage.add_usage(300)
    await usage.record_usage(uuid.UUID(uid), "resume", tally, time.monotonic() - 2, True)
    async with AsyncSessionLocal() as db:
        ev = (await db.execute(select(UsageEvent).where(UsageEvent.user_id == uuid.UUID(uid)))).scalar_one()
        assert (ev.tokens, ev.llm_calls, ev.ok, ev.kind) == (1500, 2, True, "resume")
        assert ev.duration_ms >= 2000


async def test_budget_caps_block_new_work(client, monkeypatch):
    import uuid
    from fastapi import HTTPException
    r = await register(client, unique_email())
    uid = uuid.UUID((await client.get("/api/auth/me", headers=bearer(r))).json()["id"])
    tally = usage.start_tally()
    usage.add_usage(1000)
    await usage.record_usage(uid, "resume", tally, time.monotonic(), True)

    async with AsyncSessionLocal() as db:
        await usage.ensure_budget(db, uid)                                    # under both caps
        monkeypatch.setattr(settings, "LLM_USER_DAILY_TOKEN_CAP", 500)
        with pytest.raises(HTTPException) as e:
            await usage.ensure_budget(db, uid)
        assert e.value.status_code == 429
        monkeypatch.setattr(settings, "LLM_USER_DAILY_TOKEN_CAP", 0)
        monkeypatch.setattr(settings, "LLM_DAILY_TOKEN_CAP", 500)
        with pytest.raises(HTTPException) as e:
            await usage.ensure_budget(db, uid)
        assert e.value.status_code == 503


async def test_request_id_header_is_set_and_echoed(client):
    r = await client.get("/health")
    assert len(r.headers["x-request-id"]) >= 8
    r2 = await client.get("/health", headers={"x-request-id": "abc123"})
    assert r2.headers["x-request-id"] == "abc123"


async def test_tracked_works_with_keyword_and_positional_args(client):
    import uuid
    r = await register(client, unique_email())
    uid = (await client.get("/api/auth/me", headers=bearer(r))).json()["id"]

    @usage.tracked("resume")
    async def task(ctx, row_id, user_id, extra=None):
        usage.add_usage(10)
        return "done"

    assert await task({}, row_id="r1", user_id=uid) == "done"          # how enqueue() calls it
    assert await task({}, "r2", uid) == "done"                         # positional
    async with AsyncSessionLocal() as db:
        n = len((await db.execute(select(UsageEvent).where(UsageEvent.user_id == uuid.UUID(uid)))).scalars().all())
    assert n == 2
