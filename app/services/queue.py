"""Enqueue arq jobs from API routes."""
from arq import create_pool
from arq.connections import RedisSettings

from app.config import settings


async def enqueue(function: str, **kwargs):
    """One-shot connection: enqueue `function` and return the arq job."""
    pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    try:
        return await pool.enqueue_job(function, **kwargs)
    finally:
        await pool.aclose()
