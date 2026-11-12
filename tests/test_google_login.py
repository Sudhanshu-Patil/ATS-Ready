"""Google sign-in: new accounts, returning users, safe linking, failure modes."""
import uuid

import pytest
from sqlalchemy import select

from app.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import User
from tests.conftest import unique_email
from tests.test_metabase_experience import bearer, register


@pytest.fixture(autouse=True)
def configured(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client.apps.googleusercontent.com")


def claims(email, sub=None, verified=True, name="G User"):
    return {"sub": sub or uuid.uuid4().hex, "email": email, "email_verified": verified, "name": name}


def stub_google(monkeypatch, result):
    def fake(credential):
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr("app.api.auth_routes.verify_google_id_token", fake)


async def google(client, token="tok"):
    return await client.post("/api/auth/google", json={"credential": token})


async def user_row(email):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(User).where(User.email == email))).scalar_one()


async def test_new_google_user_is_created_verified_and_logged_in(client, monkeypatch):
    email = unique_email()
    stub_google(monkeypatch, claims(email, sub="sub-new"))
    r = await google(client)
    assert r.status_code == 200 and r.json()["email"] == email and r.json()["plan"] == "free"
    assert r.json()["is_new"] is True
    assert "refresh_token" in r.cookies or "access_token" in r.cookies
    row = await user_row(email)
    assert row.google_id == "sub-new" and row.is_verified and row.hashed_password is None
    me = await client.get("/api/auth/me", headers=bearer(r))
    assert me.status_code == 200


async def test_returning_user_gets_the_same_account(client, monkeypatch):
    email = unique_email()
    c = claims(email)
    stub_google(monkeypatch, c)
    first = (await google(client)).json()
    second = (await google(client)).json()
    assert first["user_id"] == second["user_id"]
    assert first["is_new"] is True and second["is_new"] is False


async def test_links_to_existing_verified_password_account_keeping_password(client, monkeypatch):
    email = unique_email()
    reg = await register(client, email)
    async with AsyncSessionLocal() as db:                       # mark as verified
        u = (await db.execute(select(User).where(User.email == email))).scalar_one()
        u.is_verified = True
        await db.commit()
    stub_google(monkeypatch, claims(email, sub="sub-link"))
    r = await google(client)
    assert r.json()["user_id"] == reg.json()["user_id"]
    row = await user_row(email)
    assert row.google_id == "sub-link" and row.hashed_password            # password still works


async def test_linking_to_unverified_account_removes_squatter_password(client, monkeypatch):
    email = unique_email()
    await register(client, email)                                # registered, never verified
    stub_google(monkeypatch, claims(email))
    await google(client)
    row = await user_row(email)
    assert row.is_verified and row.hashed_password is None
    login = await client.post("/api/auth/login", data={"username": email, "password": "test-password-123"})
    assert login.status_code == 401


async def test_unverified_google_email_rejected(client, monkeypatch):
    stub_google(monkeypatch, claims(unique_email(), verified=False))
    assert (await google(client)).status_code == 401


async def test_invalid_token_rejected(client, monkeypatch):
    stub_google(monkeypatch, ValueError("bad signature"))
    assert (await google(client)).status_code == 401


async def test_not_configured_returns_503(client, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "")
    assert (await google(client)).status_code == 503
    assert (await client.get("/api/auth/config")).json() == {"google_client_id": None}


async def test_config_exposes_only_the_client_id(client):
    assert (await client.get("/api/auth/config")).json() == {
        "google_client_id": "test-client.apps.googleusercontent.com"}


async def test_google_only_user_cannot_change_password_without_one(client, monkeypatch):
    stub_google(monkeypatch, claims(unique_email()))
    r = await google(client)
    resp = await client.post("/api/auth/change-password", headers=bearer(r),
                             json={"current_password": "x", "new_password": "new-password-123"})
    assert resp.status_code == 400


async def test_real_verifier_rejects_garbage_and_wrong_config():
    from app.services.auth_service import verify_google_id_token
    with pytest.raises(ValueError):
        verify_google_id_token("not-a-jwt")
