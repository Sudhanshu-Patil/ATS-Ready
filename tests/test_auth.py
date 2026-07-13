"""
Auth flow integration tests — register, login, profile update, password
change. These cover the endpoints the Settings page depends on (the ones
that were silently stubbed on the frontend until the production-readiness
pass).
"""
from tests.conftest import unique_email

PASSWORD = "test-password-123"


async def register(client, email, password=PASSWORD, full_name="Py Test"):
    return await client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )


async def login(client, email, password=PASSWORD):
    return await client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
    )


def bearer(resp):
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ── Register ──────────────────────────────────────────────────────────────────

async def test_register_returns_token_and_free_plan(client):
    r = await register(client, unique_email())
    assert r.status_code == 201
    body = r.json()
    assert body["access_token"]
    assert body["plan"] == "free"


async def test_register_duplicate_email_conflicts(client):
    email = unique_email()
    assert (await register(client, email)).status_code == 201
    assert (await register(client, email)).status_code == 409


async def test_register_short_password_rejected(client):
    r = await register(client, unique_email(), password="short")
    assert r.status_code == 422


# ── Login ─────────────────────────────────────────────────────────────────────

async def test_login_roundtrip(client):
    email = unique_email()
    await register(client, email)
    r = await login(client, email)
    assert r.status_code == 200
    assert r.json()["email"] == email


async def test_login_wrong_password_401(client):
    email = unique_email()
    await register(client, email)
    r = await login(client, email, password="wrong-password-99")
    assert r.status_code == 401


async def test_me_requires_auth(client):
    r = await client.get("/api/auth/me")
    assert r.status_code == 401


# ── Profile update (Settings → Account) ──────────────────────────────────────

async def test_patch_me_updates_full_name(client):
    email = unique_email()
    reg = await register(client, email, full_name="Before Rename")

    r = await client.patch(
        "/api/auth/me", json={"full_name": "After Rename"}, headers=bearer(reg)
    )
    assert r.status_code == 200

    me = await client.get("/api/auth/me", headers=bearer(reg))
    assert me.json()["full_name"] == "After Rename"


async def test_patch_me_ignores_disallowed_fields(client):
    email = unique_email()
    reg = await register(client, email)

    await client.patch(
        "/api/auth/me", json={"plan": "team", "email": "hax@evil.com"}, headers=bearer(reg)
    )
    me = await client.get("/api/auth/me", headers=bearer(reg))
    assert me.json()["plan"] == "free"
    assert me.json()["email"] == email


# ── Password change (Settings → Security) ────────────────────────────────────

async def test_change_password_full_flow(client):
    email = unique_email()
    reg = await register(client, email)

    # wrong current password → rejected
    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": "not-the-password", "new_password": "new-password-456"},
        headers=bearer(reg),
    )
    assert r.status_code == 400

    # correct current password → accepted
    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "new-password-456"},
        headers=bearer(reg),
    )
    assert r.status_code == 200

    # old password no longer works, new one does
    assert (await login(client, email, PASSWORD)).status_code == 401
    assert (await login(client, email, "new-password-456")).status_code == 200


async def test_change_password_rejects_short_new(client):
    email = unique_email()
    reg = await register(client, email)
    r = await client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "short"},
        headers=bearer(reg),
    )
    assert r.status_code == 400
