import pytest
from fastapi import HTTPException

from app.api import rate_limit


class FakeRedis:
    def __init__(self): self.n = {}
    async def incr(self, k): self.n[k] = self.n.get(k, 0) + 1; return self.n[k]
    async def expire(self, k, s): pass


class User:  # only .id is used
    id = "u1"


async def test_blocks_after_limit_then_fails_open(monkeypatch):
    redis = FakeRedis()

    async def client(): return redis
    monkeypatch.setattr(rate_limit, "_DISABLED", False)
    monkeypatch.setattr(rate_limit.cache_service, "client", client)
    check = rate_limit.per_user_limit("t", 2)
    await check(User()); await check(User())
    with pytest.raises(HTTPException) as e:
        await check(User())
    assert e.value.status_code == 429 and e.value.headers["Retry-After"] == "60"

    async def no_redis(): return None
    monkeypatch.setattr(rate_limit.cache_service, "client", no_redis)
    await check(User())          # Redis down: allowed
