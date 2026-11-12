"""Account data export and permanent deletion (privacy: portability + erasure)."""
import asyncio
import datetime as dt
import decimal
import logging
import uuid

from sqlalchemy import select

from app.db import models as m
from app.services.cache_service import cache_service
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)

# Columns never exported (secrets / internals).
_HIDDEN = {"hashed_password", "token_version"}
# Tables holding a user_id, plus the two child tables reached through a parent.
_USER_TABLES = [m.PersonalInfo, m.Skill, m.Project, m.WorkExperience, m.Education,
                m.JobApplication, m.CoverLetter, m.InterviewPrep]


def _plain(value):
    if isinstance(value, (uuid.UUID, decimal.Decimal)):
        return str(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    return value


def _row(obj) -> dict:
    return {c.key: _plain(getattr(obj, c.key)) for c in obj.__table__.columns if c.key not in _HIDDEN}


async def export_user_data(db, user) -> dict:
    out = {"exported_at": dt.datetime.now(dt.timezone.utc).isoformat(), "account": _row(user)}
    for model in _USER_TABLES:
        rows = (await db.execute(select(model).where(model.user_id == user.id))).scalars().all()
        out[model.__tablename__] = [_row(r) for r in rows]
    for child, parent, fk in ((m.ProjectBullet, m.Project, "project_id"),
                              (m.ExperienceBullet, m.WorkExperience, "experience_id")):
        parent_ids = [p["id"] for p in out[parent.__tablename__]]
        rows = []
        if parent_ids:
            rows = (await db.execute(
                select(child).where(getattr(child, fk).in_([uuid.UUID(i) for i in parent_ids])))).scalars().all()
        out[child.__tablename__] = [_row(r) for r in rows]
    return out


async def delete_user_and_data(db, user) -> None:
    """Remove stored files, then the user row (FKs cascade to every table), then caches."""
    keys = [k for (k,) in (await db.execute(
        select(m.JobApplication.resume_s3_key).where(
            m.JobApplication.user_id == user.id, m.JobApplication.resume_s3_key.is_not(None)))).all()]
    user_id = user.id
    await db.delete(user)
    await db.commit()
    # Files go after the commit: a failed commit must not leave a user without their files.
    for key in keys:
        await asyncio.to_thread(storage_service.delete_resume, key)
    await cache_service.invalidate_profile(user_id)
    await cache_service.delete_pattern(f"job_recs:{user_id}:*")
    logger.info("Deleted account %s (%d stored files)", user_id, len(keys))
