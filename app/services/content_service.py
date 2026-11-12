"""Shared setup for cover-letter / interview-prep generation (runs in the worker)."""
import asyncio
import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.ai_agent import ai_agent
from app.config import settings
from app.db.models import JobApplication
from app.models.schemas import ParsedJD
from app.services.cache_service import cache_service
from app.services.compaction import compact_profile, profile_as_tailored
from app.services.llm_client import LLMContextTooLarge, LLMUnavailable
from app.services.metabase_service import metabase_service

logger = logging.getLogger(__name__)


class ProfileIncomplete(Exception):
    pass


def friendly_error(exc: Exception) -> str:
    """User-facing failure text (stored on the row, shown in the queue panel)."""
    if isinstance(exc, LLMUnavailable):
        return "The AI service is busy right now. Please try again in a minute."
    if isinstance(exc, LLMContextTooLarge):
        return "That job description is too long. Please shorten it and try again."
    if isinstance(exc, ProfileIncomplete):
        return str(exc)
    return "Something went wrong while generating. Please try again."


async def build_context(
    jd_text: str,
    user_id: uuid.UUID,
    db: AsyncSession,
    job_app_id: Optional[str] = None,
):
    """Returns (profile, parsed_jd, tailored, job_app). Profile is shrunk locally
    to what this JD cares about; no extra LLM call."""
    cached = await cache_service.get_profile(str(user_id))
    if cached:
        profile = cached
    else:
        profile = await metabase_service.get_full_profile_async(db, user_id)
        await cache_service.set_profile(str(user_id), profile)

    if not profile.get("personal"):
        raise ProfileIncomplete("Profile incomplete — fill in Personal Info in Metabase first.")

    parsed_jd = None
    job_app = None
    if job_app_id:
        try:
            res = await db.execute(select(JobApplication).where(
                JobApplication.id == uuid.UUID(job_app_id), JobApplication.user_id == user_id))
            job_app = res.scalar_one_or_none()
            if job_app and job_app.jd_parsed:
                parsed_jd = ParsedJD(**job_app.jd_parsed)
        except Exception:
            logger.warning("Could not reuse job_app %s", job_app_id, exc_info=True)

    if not parsed_jd:
        cached_parse = await cache_service.get_parsed_jd(jd_text)
        if cached_parse:
            parsed_jd = ParsedJD(**cached_parse)
        else:
            parsed_jd = await asyncio.to_thread(ai_agent.parse_jd, jd_text)
            await cache_service.set_parsed_jd(jd_text, parsed_jd.model_dump())

    profile = compact_profile(
        profile,
        list(parsed_jd.keywords) + list(parsed_jd.required_skills),
        settings.LLM_PROFILE_MAX_CHARS // 2,
    )
    return profile, parsed_jd, profile_as_tailored(profile), job_app
