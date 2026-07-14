from tests.conftest import unique_email


async def register(client, email, password="test-password-123", full_name="Py Test"):
    return await client.post(
        "/api/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )


async def login(client, email, password="test-password-123"):
    return await client.post(
        "/api/auth/login",
        data={"username": email, "password": password},
    )


def bearer(resp):
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_experience_create_and_update_roundtrip(client):
    email = unique_email()
    reg = await register(client, email)
    headers = bearer(reg)

    create_resp = await client.post(
        "/api/metabase/experience",
        json={
            "company": "Acme",
            "role": "Engineer",
            "start_date": "Jan 2022",
            "description": "Led platform work",
            "bullets": [],
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    experience_id = create_resp.json()["id"]

    list_resp = await client.get("/api/metabase/experience", headers=headers)
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert len(data) == 1
    assert data[0]["description"] == "Led platform work"

    update_resp = await client.patch(
        f"/api/metabase/experience/{experience_id}",
        json={"description": "Led platform work and mentoring"},
        headers=headers,
    )
    assert update_resp.status_code == 200

    updated_resp = await client.get("/api/metabase/experience", headers=headers)
    assert updated_resp.status_code == 200
    assert updated_resp.json()[0]["description"] == "Led platform work and mentoring"


async def test_skill_create_and_update_roundtrip(client):
    email = unique_email()
    reg = await register(client, email)
    headers = bearer(reg)

    create_resp = await client.post(
        "/api/metabase/skills",
        json={
            "name": "Python",
            "category": "Programming Languages",
            "proficiency": "Advanced",
            "years_experience": 4,
            "keywords": ["async"],
            "is_primary": True,
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    skill_id = create_resp.json()["id"]

    list_resp = await client.get("/api/metabase/skills", headers=headers)
    assert list_resp.status_code == 200
    skills = list_resp.json()
    assert len(skills) == 1
    assert skills[0]["proficiency"] == "Advanced"

    update_resp = await client.patch(
        f"/api/metabase/skills/{skill_id}",
        json={"proficiency": "Expert", "years_experience": 5},
        headers=headers,
    )
    assert update_resp.status_code == 200

    updated_resp = await client.get("/api/metabase/skills", headers=headers)
    assert updated_resp.status_code == 200
    updated_skill = updated_resp.json()[0]
    assert updated_skill["proficiency"] == "Expert"
    assert updated_skill["years_experience"] == 5.0
