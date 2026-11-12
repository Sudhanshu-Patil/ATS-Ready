"""Session revocation, account export and deletion."""
from sqlalchemy import select

from app.db.database import AsyncSessionLocal
from app.db.models import User
from tests.conftest import unique_email
from tests.test_metabase_experience import bearer, register

PW = "test-password-123"


async def test_logout_all_invalidates_existing_tokens(client):
    r = await register(client, unique_email())
    h = bearer(r)
    assert (await client.get("/api/auth/me", headers=h)).status_code == 200
    assert (await client.post("/api/auth/logout-all", headers=h)).status_code == 200
    assert (await client.get("/api/auth/me", headers=h)).status_code == 401


async def test_change_password_signs_out_old_tokens_but_keeps_this_session(client):
    email = unique_email()
    r = await register(client, email)
    old = bearer(r)
    c = await client.post("/api/auth/change-password", headers=old,
                          json={"current_password": PW, "new_password": "brand-new-pass-1"})
    assert c.status_code == 200
    assert (await client.get("/api/auth/me", headers=old)).status_code == 401      # stale token
    assert (await client.post("/api/auth/refresh")).status_code == 200            # cookies were reissued


async def test_change_password_validates_body(client):
    r = await register(client, unique_email())
    bad = await client.post("/api/auth/change-password", headers=bearer(r),
                            json={"current_password": PW, "new_password": "short"})
    assert bad.status_code == 422
    assert (await client.patch("/api/auth/me", headers=bearer(r), json={"full_name": "x" * 300})).status_code == 422


async def test_export_has_data_and_no_secrets(client):
    email = unique_email()
    r = await register(client, email)
    await client.post("/api/metabase/skills", headers=bearer(r), json={"name": "Rust", "category": "Languages"})
    exp = await client.get("/api/auth/me/export", headers=bearer(r))
    assert exp.status_code == 200
    body = exp.json()
    assert body["account"]["email"] == email
    assert any(s["name"] == "Rust" for s in body["skills"])
    assert "hashed_password" not in exp.text and "token_version" not in exp.text


async def test_delete_requires_confirmation_then_removes_everything(client):
    email = unique_email()
    r = await register(client, email)
    h = bearer(r)
    await client.post("/api/metabase/skills", headers=h, json={"name": "Rust", "category": "Languages"})

    assert (await client.request("DELETE", "/api/auth/me", headers=h,
                                 json={"confirm_email": "wrong@x.com", "password": PW})).status_code == 400
    assert (await client.request("DELETE", "/api/auth/me", headers=h,
                                 json={"confirm_email": email, "password": "nope-nope-nope"})).status_code == 400

    ok = await client.request("DELETE", "/api/auth/me", headers=h,
                              json={"confirm_email": email.upper(), "password": PW})
    assert ok.status_code == 200
    assert (await client.get("/api/auth/me", headers=h)).status_code == 401
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(User).where(User.email == email))).scalar_one_or_none() is None
    login = await client.post("/api/auth/login", data={"username": email, "password": PW})
    assert login.status_code == 401
