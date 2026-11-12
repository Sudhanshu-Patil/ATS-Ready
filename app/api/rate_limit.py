"""
app/api/rate_limit.py
──────────────────────
Per-IP rate limiting for auth endpoints (register/login/password-reset/
verification-email) — the classic brute-force / credential-stuffing /
email-bombing surface that had zero protection.

Backed by Redis so limits are shared across the api + worker processes and
survive restarts. Auto-disabled under pytest so the test suite's rapid-fire
register/login calls from a single synthetic client address never trip it.
Detected via sys.modules rather than the PYTEST_CURRENT_TEST env var — that
var is only set once a test starts *running*, but this module is imported
at collection time (conftest.py does `from main import app` up top), before
any test has started — so an env-var check would still see it as unset.
"""
import sys

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings

_DISABLED = "pytest" in sys.modules or not settings.RATE_LIMIT_ENABLED

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.REDIS_URL,
    enabled=not _DISABLED,
)


# ── Per-user limits for expensive endpoints ──────────────────────────────────
# slowapi keys on IP; these endpoints need a per-account budget (LLM tokens and
# Apify credit cost real money). Fixed window in Redis, shared by api replicas.
# Fails OPEN if Redis is down: an outage must not lock every user out.
from fastapi import Depends, HTTPException  # noqa: E402

from app.api.dependencies import get_current_user  # noqa: E402
from app.db.models import User  # noqa: E402
from app.services.cache_service import cache_service  # noqa: E402


def per_user_limit(name: str, limit: int, window_seconds: int = 60):
    async def _check(user: User = Depends(get_current_user)) -> None:
        if _DISABLED:
            return
        client = await cache_service.client()
        if client is None:
            return
        key = f"rl:{name}:{user.id}"
        try:
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, window_seconds)
        except Exception:
            return
        if count > limit:
            raise HTTPException(
                status_code=429,
                detail="You're going a little fast. Please wait a minute and try again.",
                headers={"Retry-After": str(window_seconds)},
            )
    return _check
