"""GET /recommendations answers immediately; a cold fetch runs in the background."""
from app.services import job_recommendations as jr
from tests.conftest import unique_email
from tests.test_metabase_experience import bearer, register

JOBS = [{"title": "Backend Engineer", "company": "Acme", "match_score": 80}]


async def test_cold_cache_returns_pending_and_starts_one_fetch(client, monkeypatch):
    started = []

    async def peek(user_id, db, refresh=False): return None
    async def start(user_id, refresh=False): started.append(refresh)
    monkeypatch.setattr(jr, "peek_recommendations", peek)
    monkeypatch.setattr(jr, "start_refresh", start)

    h = bearer(await register(client, unique_email()))
    r = await client.get("/api/recommendations", headers=h)
    assert r.status_code == 200
    assert r.json() == {"jobs": [], "total": 0, "status": "pending"}
    assert started == [False]


async def test_warm_cache_is_ready_immediately(client, monkeypatch):
    async def peek(user_id, db, refresh=False): return JOBS
    async def start(user_id, refresh=False): raise AssertionError("must not refetch")
    monkeypatch.setattr(jr, "peek_recommendations", peek)
    monkeypatch.setattr(jr, "start_refresh", start)

    h = bearer(await register(client, unique_email()))
    r = (await client.get("/api/recommendations", headers=h)).json()
    assert r["status"] == "ready" and r["total"] == 1


async def test_start_refresh_runs_once_and_clears_its_lock(monkeypatch):
    import asyncio
    import uuid
    calls = []

    async def fake_get(user_id, db, refresh=False):
        calls.append(user_id)
        return []

    async def fake_profile(user_id, db):
        return jr.UserProfile(skills=["python"])

    monkeypatch.setattr(jr, "get_recommendations_for_user", fake_get)
    monkeypatch.setattr(jr, "load_user_profile", fake_profile)
    uid = uuid.uuid4()
    await jr.start_refresh(uid)
    await jr.start_refresh(uid)                  # second call while the first runs: ignored
    await asyncio.gather(*list(jr._background))
    assert calls == [uid]
    assert await jr.cache_service.get(f"job_recs_pending:{uid}") is None            # lock released
    assert await jr.cache_service.get(f"job_recs_empty:{uid}:{jr.UserProfile(skills=['python']).fingerprint()}")
