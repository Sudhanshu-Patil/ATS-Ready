import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.database import get_db
from app.db.models import (
    Education, ExperienceBullet, JobApplication, PersonalInfo,
    Project, ProjectBullet, Skill, User, WorkExperience,
)
from app.models.schemas import (
    ATSBreakdown, GenerateResumeRequest, GenerateResumeResponse,
    JobStatusResponse, PersonalInfoUpdate, ProjectCreate, SkillCreate,
    SkillOut, WorkExperienceCreate,
)
from app.services.cache_service import cache_service
from app.services.storage_service import storage_service
from app.api.dependencies import get_current_user
from app.api.plan_limits import check_resume_limit

router = APIRouter()
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# ARQ Pool helper
# ─────────────────────────────────────────────────────────────────────────────

async def _get_arq_pool():
    """Create a one-shot ARQ connection to enqueue a job."""
    return await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))


# ─────────────────────────────────────────────────────────────────────────────
# Resume Generation
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/generate-resume", response_model=GenerateResumeResponse, status_code=202)
async def generate_resume(
    request: GenerateResumeRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(check_resume_limit),
):
    """
    Enqueue a resume generation job.

    Returns HTTP 202 Accepted immediately with a job_id.
    Poll GET /api/jobs/{job_id}/status to track progress.
    When status == "done", the full result including download_url is returned.
    """
    # Validate: must have URL or text
    if not request.jd_url and not request.jd_text:
        raise HTTPException(status_code=422, detail="Either jd_url or jd_text is required.")

    # Create the JobApplication row in "pending" state NOW so we have an ID
    job_app = JobApplication(
        user_id=user.id,
        jd_url=str(request.jd_url) if request.jd_url else None,
        status="pending",
    )
    db.add(job_app)
    await db.commit()
    await db.refresh(job_app)

    # Enqueue the background task
    arq_pool = await _get_arq_pool()
    arq_job = await arq_pool.enqueue_job(
        "generate_resume",
        job_app_id=str(job_app.id),
        user_id=str(user.id),
        jd_url=str(request.jd_url) if request.jd_url else None,
        jd_text=request.jd_text,
        emphasis=request.emphasis,
        _job_id=f"resume:{job_app.id}",   # deterministic ARQ job ID for dedup
    )
    await arq_pool.aclose()

    # Persist the ARQ job ID so we can look up status later
    job_app.arq_job_id = arq_job.job_id
    await db.commit()

    logger.info("Enqueued generation job %d (arq=%s) for user %d",
                job_app.id, arq_job.job_id, user.id)

    return GenerateResumeResponse(
        job_id=str(job_app.id),
        status="pending",
        message="Resume generation started. Poll /api/jobs/{job_id}/status for updates.",
    )


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Poll this endpoint every 2 seconds to track generation progress.

    Response shape:
      { status: "pending"|"running"|"done"|"failed",
        result: { ... full resume result when done ... },
        error:  "error message when failed" }
    """
    result = await db.execute(
        select(JobApplication).where(
            JobApplication.id == job_id,
            JobApplication.user_id == user.id,  # ownership check
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response: Dict[str, Any] = {
        "job_id":  str(job.id),
        "status":  job.status,
        "error":   job.error_message,
        "result":  None,
    }

    if job.status == "done" and job.resume_s3_key:
        download_url = storage_service.get_download_url(
            job.resume_s3_key,
            job.resume_filename or "resume.docx",
        )
        ats = job.ats_breakdown or {}
        response["result"] = {
            "job_id":         str(job.id),
            "job_title":      job.job_title,
            "company":        job.company,
            "ats_score":      job.ats_score,
            "ats_breakdown":  ats,
            "skills_matched": job.skills_matched or [],
            "skills_missing": job.skills_missing or [],
            "download_url":   download_url,
        }

    return response


@router.get("/download/{job_id}")
async def download_resume(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Redirect to a pre-signed S3 URL (or serve local file in dev mode).
    The signed URL is valid for DOWNLOAD_URL_EXPIRY seconds (default 1 hour).
    """
    result = await db.execute(
        select(JobApplication).where(
            JobApplication.id == job_id,
            JobApplication.user_id == user.id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.resume_s3_key:
        raise HTTPException(status_code=404, detail="Resume file not yet available")

    url = storage_service.get_download_url(
        job.resume_s3_key,
        job.resume_filename or "resume.docx",
    )

    # If it's a local path (dev mode), serve it directly
    if url.startswith("/outputs/"):
        from fastapi.responses import FileResponse
        local = settings.OUTPUT_DIR / Path(url).name
        if not local.exists():
            raise HTTPException(status_code=404, detail="File not found on disk")
        return FileResponse(str(local), media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ), filename=job.resume_filename or "resume.docx")

    # S3/R2 pre-signed URL — redirect
    return RedirectResponse(url=url, status_code=302)


# @router.get("/ats-score/{job_id}")
# async def get_ats_score(
#     job_id: str,
#     db: AsyncSession = Depends(get_db),
#     user: User = Depends(get_current_user),
# ):
#     result = await db.execute(
#         select(JobApplication).where(
#             JobApplication.id == job_id,
#             JobApplication.user_id == user.id,
#         )
#     )
#     job = result.scalar_one_or_none()
#     if not job:
#         raise HTTPException(status_code=404, detail="Job not found")
#     return {
#         "job_id":         str(job.id),
#         "job_title":      job.job_title,
#         "company":        job.company,
#         "ats_score":      job.ats_score,
#         "breakdown":      job.ats_breakdown,
#         "skills_matched": job.skills_matched,
#         "skills_missing": job.skills_missing,
#     }


# # ─────────────────────────────────────────────────────────────────────────────
# # Job Applications History
# # ─────────────────────────────────────────────────────────────────────────────

# @router.get("/jobs")
# async def list_jobs(
#     db: AsyncSession = Depends(get_db),
#     user: User = Depends(get_current_user),
#     limit: int = 50,
#     offset: int = 0,
# ):
#     result = await db.execute(
#         select(JobApplication)
#         .where(JobApplication.user_id == user.id)
#         .order_by(JobApplication.created_at.desc())
#         .limit(limit)
#         .offset(offset)
#     )
#     jobs = result.scalars().all()
#     return [
#         {
#             "id":           str(j.id),
#             "job_title":    j.job_title,
#             "company":      j.company,
#             "ats_score":    j.ats_score,
#             "status":       j.status,
#             "created_at":   str(j.created_at),
#             "download_url": f"/api/download/{j.id}",
#         }
#         for j in jobs
#     ]


# ─────────────────────────────────────────────────────────────────────────────
# Metabase: Personal Info
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/metabase/personal")
async def get_personal_info(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PersonalInfo).where(PersonalInfo.user_id == user.id)
    )
    info = result.scalar_one_or_none()
    if not info:
        raise HTTPException(status_code=404, detail="No personal info found")
    return info


@router.post("/metabase/personal")
async def upsert_personal_info(
    data: PersonalInfoUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PersonalInfo).where(PersonalInfo.user_id == user.id)
    )
    info = result.scalar_one_or_none()
    if info:
        for k, v in data.model_dump().items():
            setattr(info, k, v)
    else:
        info = PersonalInfo(user_id=user.id, **data.model_dump())
        db.add(info)
    await db.commit()
    await cache_service.invalidate_profile(user.id)
    return {"message": "Personal info saved"}


# ─────────────────────────────────────────────────────────────────────────────
# Metabase: Skills
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/metabase/skills", response_model=List[SkillOut])
async def get_skills(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Skill)
        .where(Skill.user_id == user.id)
        .order_by(Skill.is_primary.desc(), Skill.years_experience.desc())
    )
    return result.scalars().all()


@router.post("/metabase/skills", response_model=SkillOut)
async def add_skill(
    data: SkillCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    existing = await db.execute(
        select(Skill).where(Skill.user_id == user.id, Skill.name == data.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Skill '{data.name}' already exists")
    skill = Skill(user_id=user.id, **data.model_dump())
    db.add(skill)
    await db.commit()
    await db.refresh(skill)
    await cache_service.invalidate_profile(user.id)
    return skill


@router.delete("/metabase/skills/{skill_id}")
async def delete_skill(
    skill_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Skill).where(Skill.id == skill_id, Skill.user_id == user.id)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    await db.delete(skill)
    await db.commit()
    await cache_service.invalidate_profile(user.id)
    return {"message": f"Skill '{skill.name}' deleted"}


# ─────────────────────────────────────────────────────────────────────────────
# Metabase: Projects
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/metabase/projects")
async def get_projects(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Project)
        .where(Project.user_id == user.id)
        .order_by(Project.is_featured.desc())
    )
    projects = result.scalars().all()
    return [
        {
            "id":           str(p.id),
            "title":        p.title,
            "tech_stack":   p.tech_stack,
            "is_featured":  p.is_featured,
            "bullets_count": len(p.bullets),
        }
        for p in projects
    ]


@router.post("/metabase/projects")
async def add_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bullets = data.bullets
    project_data = data.model_dump(exclude={"bullets"})
    project = Project(user_id=user.id, **project_data)
    db.add(project)
    await db.flush()  # get project.id before adding bullets
    for b in bullets:
        db.add(ProjectBullet(project_id=project.id, **b.model_dump()))
    await db.commit()
    await db.refresh(project)
    await cache_service.invalidate_profile(user.id)
    return {"message": "Project added", "id": str(project.id)}


@router.delete("/metabase/projects/{project_id}")
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    await db.delete(project)
    await db.commit()
    await cache_service.invalidate_profile(user.id)
    return {"message": "Project deleted"}


# ─────────────────────────────────────────────────────────────────────────────
# Metabase: Work Experience
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/metabase/experience")
async def get_experience(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WorkExperience)
        .where(WorkExperience.user_id == user.id)
        .order_by(WorkExperience.is_current.desc(), WorkExperience.start_date.desc())
    )
    exps = result.scalars().all()
    return [
        {
            "id":         str(e.id),
            "company":    e.company,
            "role":       e.role,
            "start_date": e.start_date,
            "end_date":   e.end_date,
            "is_current": e.is_current,
        }
        for e in exps
    ]


@router.post("/metabase/experience")
async def add_experience(
    data: WorkExperienceCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bullets = data.bullets
    exp_data = data.model_dump(exclude={"bullets"})
    exp = WorkExperience(user_id=user.id, **exp_data)
    db.add(exp)
    await db.flush()
    for b in bullets:
        db.add(ExperienceBullet(experience_id=exp.id, **b.model_dump()))
    await db.commit()
    await db.refresh(exp)
    await cache_service.invalidate_profile(user.id)
    return {"message": "Experience added", "id": str(exp.id)}


@router.delete("/metabase/experience/{exp_id}")
async def delete_experience(
    exp_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(WorkExperience).where(
            WorkExperience.id == exp_id,
            WorkExperience.user_id == user.id,
        )
    )
    exp = result.scalar_one_or_none()
    if not exp:
        raise HTTPException(status_code=404, detail="Experience not found")
    await db.delete(exp)
    await db.commit()
    await cache_service.invalidate_profile(user.id)
    return {"message": "Experience deleted"}


# ─────────────────────────────────────────────────────────────────────────────
# Job Recommendations
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/recommendations")
async def get_recommendations(
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Return personalised job recommendations scored against the user's skills.

    Results are cached in Redis for 2 hours. Pass ?refresh=true to bust the
    cache and fetch fresh listings from all sources.

    Response: list of jobs sorted by match_score descending (only ≥60% matches).
    """
    from app.services.job_recommendations import get_recommendations_for_user
    jobs = await get_recommendations_for_user(user.id, db, refresh=refresh)
    return {
        "jobs":    jobs,
        "total":   len(jobs),
        "cached":  not refresh,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Health & Diagnostics
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/health/detailed")
async def detailed_health(db: AsyncSession = Depends(get_db)):
    """Extended health check — checks DB, Redis, and storage connectivity."""
    checks: Dict[str, Any] = {}

    # Database
    try:
        await db.execute(select(func.now()))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    # Redis / Cache
    checks["redis"] = "ok" if await cache_service.ping() else "unavailable"

    # Storage
    checks["storage"] = "s3" if settings.storage_use_s3 else "local"

    overall = "ok" if all(v == "ok" or v in ("s3", "local", "unavailable") for v in checks.values()) else "degraded"
    return {"status": overall, "checks": checks}
