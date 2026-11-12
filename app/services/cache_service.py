"""
app/services/cache_service.py
──────────────────────────────
Redis caching layer.

WHAT WE CACHE AND WHY:
  1. Parsed JDs (24h TTL)
     The AI JD parser costs ~$0.01–0.03 per call.  Job postings are stable
     documents — the same URL or text will yield the same structured output.
     Caching by SHA-256 hash of the text cuts OpenAI spend by 40–60% in
     high-traffic periods when many users apply to the same popular JD.

  2. Scraped JD pages (6h TTL)
     HTTP scraping is slow (2–5s) and flaky.  Caching the raw scraped text
     means if two users submit the same URL within 6 hours, the second request
     is instant and doesn't risk being rate-limited by the target site.

  3. Candidate profile (5min TTL)
     Fetching the full profile (skills + experience + projects + education)
     hits 5 joined tables.  The profile rarely changes mid-session.  A short
     TTL keeps it fresh while avoiding repeated DB queries during bulk ops.

KEY NAMING CONVENTION:
  jd:parsed:{sha256}   — parsed JD result dict
  jd:scraped:{sha256}  — raw scraped JD text
  profile:{user_id}    — full candidate profile dict

All values are serialised as JSON strings.
"""
import hashlib
import json
import logging
from typing import Any, Optional

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, RedisError, TimeoutError

from app.config import settings

logger = logging.getLogger(__name__)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class CacheService:
    """
    Async Redis client wrapper.  All methods are safe to call even when Redis
    is unavailable — they log a warning and return None / do nothing, so the
    app degrades gracefully rather than crashing.

    Connection is lazy: the client is created on first use, not at import time.
    This lets tests override REDIS_URL before the client connects.
    """

    def __init__(self):
        self._client: Optional[Redis] = None

    # ── Connection ────────────────────────────────────────────────────────────

    async def client(self) -> Optional[Redis]:
        """
        Return the Redis client, creating it on first call.
        Returns None if Redis is unreachable (graceful degradation).
        """
        if self._client is None:
            try:
                self._client = aioredis.from_url(
                    settings.REDIS_URL,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                    retry_on_timeout=True,
                    max_connections=20,
                )
                # Verify connection
                await self._client.ping()
                logger.info("Redis connected: %s", settings.REDIS_URL.split("@")[-1])
            except (ConnectionError, TimeoutError, Exception) as exc:
                logger.warning("Redis unavailable (%s) — caching disabled", exc)
                self._client = None
        return self._client

    async def close(self) -> None:
        """Close the connection pool on app shutdown."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── Low-level get/set/delete ───────────────────────────────────────────────

    async def get(self, key: str) -> Optional[Any]:
        """Get a JSON value. Returns None on miss or Redis unavailable."""
        r = await self.client()
        if not r:
            return None
        try:
            raw = await r.get(key)
            return json.loads(raw) if raw is not None else None
        except (RedisError, json.JSONDecodeError) as exc:
            logger.warning("Cache GET failed for key %r: %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Set a JSON value with a TTL in seconds. Silently fails on error."""
        r = await self.client()
        if not r:
            return
        try:
            await r.set(key, json.dumps(value, default=str), ex=ttl)
        except (RedisError, TypeError) as exc:
            logger.warning("Cache SET failed for key %r: %s", key, exc)

    async def delete(self, key: str) -> None:
        """Delete a key. Silently fails on error."""
        r = await self.client()
        if not r:
            return
        try:
            await r.delete(key)
        except RedisError as exc:
            logger.warning("Cache DELETE failed for key %r: %s", key, exc)

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a glob pattern.
        Returns the number of deleted keys.
        Use sparingly — SCAN in a loop is O(N).
        """
        r = await self.client()
        if not r:
            return 0
        count = 0
        try:
            async for key in r.scan_iter(pattern, count=100):
                await r.delete(key)
                count += 1
        except RedisError as exc:
            logger.warning("Cache DELETE pattern %r failed: %s", pattern, exc)
        return count

    # ── Domain-specific helpers ────────────────────────────────────────────────

    # 1. Parsed JDs
    async def get_parsed_jd(self, jd_text: str) -> Optional[dict]:
        key = f"jd:parsed:{_sha256(jd_text)}"
        result = await self.get(key)
        if result:
            logger.debug("Cache HIT — parsed JD (hash=%s…)", key[-8:])
        return result

    async def set_parsed_jd(self, jd_text: str, result: dict) -> None:
        key = f"jd:parsed:{_sha256(jd_text)}"
        await self.set(key, result, ttl=settings.CACHE_JD_PARSE_TTL)
        logger.debug("Cache SET — parsed JD (hash=%s… ttl=%ds)", key[-8:], settings.CACHE_JD_PARSE_TTL)

    # 2. Scraped JD pages
    async def get_scraped_url(self, url: str) -> Optional[str]:
        key = f"jd:scraped:{_sha256(url)}"
        result = await self.get(key)
        if result:
            logger.debug("Cache HIT — scraped URL %s", url[:60])
        return result

    async def set_scraped_url(self, url: str, text: str) -> None:
        key = f"jd:scraped:{_sha256(url)}"
        await self.set(key, text, ttl=settings.CACHE_SCRAPED_URL_TTL)

    # 3. Candidate profile
    async def get_profile(self, user_id: int) -> Optional[dict]:
        key = f"profile:{user_id}"
        result = await self.get(key)
        if result:
            logger.debug("Cache HIT — profile user_id=%s", user_id)
        return result

    async def set_profile(self, user_id: int, profile: dict) -> None:
        key = f"profile:{user_id}"
        await self.set(key, profile, ttl=settings.CACHE_PROFILE_TTL)

    async def invalidate_profile(self, user_id: int) -> None:
        """
        Call this whenever the user modifies their metabase (skills, experience,
        projects, personal info).  Forces a fresh DB fetch on next generation.
        """
        await self.delete(f"profile:{user_id}")
        logger.debug("Cache INVALIDATED — profile user_id=%s", user_id)

    # ── Health check ──────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Returns True if Redis is reachable."""
        r = await self.client()
        if not r:
            return False
        try:
            return await r.ping()
        except RedisError:
            return False


# ── Singleton ─────────────────────────────────────────────────────────────────
cache_service = CacheService()
