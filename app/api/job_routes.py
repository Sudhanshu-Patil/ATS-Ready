"""
app/api/job_routes.py
──────────────────────
Job management endpoints: retry failed jobs, delete jobs, paginated history.

Added in Step 3 to give users control over their job history and handle
the common case of a failed job (transient AI errors, network timeouts).
"""
import uuid
from typing import Any, Dict, Optional

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.activity_routes import ensure_capacity
from app.api.dependencies import get_current_user
from app.api.plan_limits import check_resume_limit
from app.config import settings
from app.db.database import get_db
from app.db.models import JobApplication, User
from app.services.storage_service import storage_service

job_router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_job_or_404(
    job_id: str, user: User, db: AsyncSession
) -> JobApplication:
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid job_id format")

    result = await db.execute(
        select(JobApplication).where(
            JobApplication.id == job_uuid,
            JobApplication.user_id == user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _job_summary(job: JobApplication) -> Dict[str, Any]:
    return {
        "id":           str(job.id),
        "job_title":    job.job_title,
        "company":      job.company,
        "ats_score":    job.ats_score,
        "status":       job.status,
        "error":        job.error_message,
        "created_at":   str(job.created_at),
        "download_url": f"/api/download/{job.id}" if job.resume_s3_key else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@job_router.get("/jobs")
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None),  # filter by status
):
    """
    Paginated job history with optional status filter.

    Query params:
      limit  — max results (default 20, max 100)
      offset — skip N results (for pagination)
      status — filter by "pending"|"running"|"done"|"failed"
    """
    query = (
        select(JobApplication)
        .where(JobApplication.user_id == user.id)
        .order_by(JobApplication.created_at.desc())
    )
    if status:
        query = query.where(JobApplication.status == status)

    # Get total count for pagination metadata
    count_query = select(func.count()).select_from(
        select(JobApplication)
        .where(JobApplication.user_id == user.id)
        .where(JobApplication.status == status if status else True)
        .subquery()
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    result = await db.execute(query.limit(limit).offset(offset))
    jobs = result.scalars().all()

    return {
        "total":  total,
        "limit":  limit,
        "offset": offset,
        "items":  [_job_summary(j) for j in jobs],
    }


@job_router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get full details of a single job including ATS breakdown."""
    job = await _get_job_or_404(job_id, user, db)

    download_url = None
    if job.resume_s3_key:
        download_url = storage_service.get_download_url(
            job.resume_s3_key,
            job.resume_filename or "resume.docx",
        )

    return {
        "id":             str(job.id),
        "job_title":      job.job_title,
        "company":        job.company,
        "status":         job.status,
        "error":          job.error_message,
        "ats_score":      job.ats_score,
        "ats_breakdown":  job.ats_breakdown,
        "skills_matched": job.skills_matched,
        "skills_missing": job.skills_missing,
        "download_url":   download_url,
        "created_at":     str(job.created_at),
        "updated_at":     str(job.updated_at),
    }


@job_router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(check_resume_limit),   # a retry spends quota like a new job
):
    """
    Retry a failed job.

    Only jobs with status="failed" can be retried.
    Re-enqueues the same JD text/URL with the original parameters.
    """
    job = await _get_job_or_404(job_id, user, db)

    if job.status != "failed":
        raise HTTPException(
            status_code=400,
            detail=f"Only failed jobs can be retried. This job has status='{job.status}'.",
        )
    await ensure_capacity(db, user.id)
    if not job.jd_text and not job.jd_url:
        raise HTTPException(
            status_code=400,
            detail="Cannot retry — original JD data was not stored.",
        )

    # Reset status to pending
    job.status = "pending"
    job.error_message = None
    await db.commit()

    # Re-enqueue
    arq_pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    await arq_pool.enqueue_job(
        "generate_resume",
        job_app_id=str(job.id),
        user_id=str(user.id),
        jd_url=job.jd_url,
        jd_text=job.jd_text,
        emphasis=None,
        _job_id=f"retry:{job.id}",
    )
    await arq_pool.aclose()

    return {"message": "Job queued for retry", "job_id": str(job.id)}


@job_router.delete("/jobs/{job_id}")
async def delete_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Delete a job and its associated resume file.

    Running jobs cannot be deleted — cancel them first by waiting for
    completion or letting them fail.
    """
    job = await _get_job_or_404(job_id, user, db)

    if job.status == "running":
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a running job. Wait for it to complete first.",
        )

    # Delete resume file from storage
    if job.resume_s3_key:
        storage_service.delete_resume(job.resume_s3_key)

    await db.delete(job)
    await db.commit()

    return {"message": "Job deleted"}


@job_router.delete("/jobs")
async def delete_all_failed_jobs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete all failed jobs for the current user. Useful for cleanup."""
    result = await db.execute(
        select(JobApplication).where(
            JobApplication.user_id == user.id,
            JobApplication.status == "failed",
        )
    )
    failed_jobs = result.scalars().all()

    count = 0
    for job in failed_jobs:
        if job.resume_s3_key:
            storage_service.delete_resume(job.resume_s3_key)
        await db.delete(job)
        count += 1

    await db.commit()
    return {"message": f"Deleted {count} failed jobs"}


@job_router.get("/stats")
async def get_user_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Summary statistics for the current user's job history.
    Used by the dashboard to show usage metrics.
    """
    result = await db.execute(
        select(
            func.count(JobApplication.id).label("total"),
            func.count(JobApplication.id).filter(JobApplication.status == "done").label("completed"),
            func.count(JobApplication.id).filter(JobApplication.status == "failed").label("failed"),
            func.avg(JobApplication.ats_score).label("avg_score"),
            func.max(JobApplication.ats_score).label("best_score"),
        ).where(JobApplication.user_id == user.id)
    )
    row = result.one()

    return {
        "total_resumes":    row.total or 0,
        "completed":        row.completed or 0,
        "failed":           row.failed or 0,
        "avg_ats_score":    round(row.avg_score or 0, 1),
        "best_ats_score":   round(row.best_score or 0, 1),
        "plan":             user.plan,
    }
