"""Per-run LLM usage accounting, daily spend caps and the admin numbers.

The worker opens a tally (a ContextVar holding a dict) before a run. LLMClient
adds the tokens each call used; asyncio.to_thread copies the context, so threads
write into the same dict. At the end one UsageEvent row is stored.
"""
import functools
import logging
import time
from contextvars import ContextVar
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select

from app.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import UsageEvent

logger = logging.getLogger(__name__)

_tally: ContextVar[Optional[dict]] = ContextVar("llm_tally", default=None)


def start_tally() -> dict:
    t = {"tokens": 0, "calls": 0, "failed": False}
    _tally.set(t)
    return t


def add_usage(tokens: Optional[int]) -> None:
    """Called by LLMClient after every successful completion."""
    t = _tally.get()
    if t is not None:
        t["tokens"] += tokens or 0
        t["calls"] += 1


def mark_failed() -> None:
    t = _tally.get()
    if t is not None:
        t["failed"] = True


def _day_start() -> datetime:
    return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)


async def tokens_today(db, user_id=None) -> int:
    q = select(func.coalesce(func.sum(UsageEvent.tokens), 0)).where(UsageEvent.created_at >= _day_start())
    if user_id is not None:
        q = q.where(UsageEvent.user_id == user_id)
    return int((await db.execute(q)).scalar() or 0)


async def ensure_budget(db, user_id) -> None:
    """Refuse new LLM work once today's caps are used (0 disables a cap)."""
    if settings.LLM_USER_DAILY_TOKEN_CAP and await tokens_today(db, user_id) >= settings.LLM_USER_DAILY_TOKEN_CAP:
        raise HTTPException(status_code=429, detail="You've reached today's AI usage limit. It resets at midnight UTC.")
    if settings.LLM_DAILY_TOKEN_CAP and await tokens_today(db) >= settings.LLM_DAILY_TOKEN_CAP:
        raise HTTPException(status_code=503, detail="ATS-Ready has reached its daily AI capacity. Please try again tomorrow.")


async def record_usage(user_id, kind: str, tally: dict, started: float, ok: bool) -> None:
    """Store one event; never raises (accounting must not fail a finished job)."""
    try:
        async with AsyncSessionLocal() as db:
            before = await tokens_today(db) if settings.LLM_DAILY_TOKEN_CAP else 0
            db.add(UsageEvent(user_id=user_id, kind=kind, tokens=tally["tokens"], llm_calls=tally["calls"],
                              duration_ms=int((time.monotonic() - started) * 1000), ok=ok))
            await db.commit()
        cap = settings.LLM_DAILY_TOKEN_CAP
        if cap and before < 0.8 * cap <= before + tally["tokens"]:
            # Sentry (if configured) turns this error log into an alert.
            logger.error("SPEND ALERT: 80%% of the daily LLM token cap (%d) is used", cap)
    except Exception:
        logger.warning("Could not record usage event", exc_info=True)


def tracked(kind: str):
    """Decorator for arq tasks shaped (ctx, row_id, user_id, ...)."""
    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(ctx, *args, **kwargs):
            tally, started, ok = start_tally(), time.monotonic(), False
            try:
                result = await fn(ctx, *args, **kwargs)
                ok = not tally["failed"]
                return result
            finally:
                await record_usage(args[1], kind, tally, started, ok)
        return wrapper
    return deco
