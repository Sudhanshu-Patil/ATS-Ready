import logging
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
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
    JobStatusResponse, PersonalInfoUpdate, ProjectCreate, ProjectUpdate,
    SkillCreate, SkillOut, SkillUpdate, WorkExperienceCreate, WorkExperienceUpdate,
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


@router.patch("/metabase/skills/{skill_id}", response_model=SkillOut)
async def update_skill(
    skill_id: str,
    data: SkillUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Skill).where(Skill.id == skill_id, Skill.user_id == user.id)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    updates = data.model_dump(exclude_unset=True)
    if updates.get("name"):
        existing = await db.execute(
            select(Skill).where(
                Skill.user_id == user.id,
                Skill.name == updates["name"],
                Skill.id != skill.id,
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail=f"Skill '{updates['name']}' already exists")

    for key, value in updates.items():
        setattr(skill, key, value)

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
            "id":                str(p.id),
            "title":             p.title,
            "description":       p.description,
            "short_description": p.short_description,
            "tech_stack":        p.tech_stack or [],
            "impact":            p.impact,
            "github_url":       p.github_url,
            "live_url":         p.live_url,
            "start_date":       p.start_date,
            "end_date":         p.end_date,
            "is_featured":      p.is_featured,
            "bullets_count":    len(p.bullets),
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


@router.patch("/metabase/projects/{project_id}")
async def update_project(
    project_id: str,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(project, key, value)

    await db.commit()
    await db.refresh(project)
    await cache_service.invalidate_profile(user.id)
    return {
        "message": "Project updated",
        "id": str(project.id),
        "title": project.title,
        "description": project.description,
        "short_description": project.short_description,
        "tech_stack": project.tech_stack or [],
        "impact": project.impact,
        "github_url": project.github_url,
        "live_url": project.live_url,
        "start_date": project.start_date,
        "end_date": project.end_date,
        "is_featured": project.is_featured,
    }


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
            "id":          str(e.id),
            "company":     e.company,
            "role":        e.role,
            "location":    e.location,
            "start_date":  e.start_date,
            "end_date":    e.end_date,
            "is_current":  e.is_current,
            "description": e.description,
            "tech_stack":  e.tech_stack or [],
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


@router.patch("/metabase/experience/{exp_id}")
async def update_experience(
    exp_id: str,
    data: WorkExperienceUpdate,
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

    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(exp, key, value)

    await db.commit()
    await db.refresh(exp)
    await cache_service.invalidate_profile(user.id)
    return {
        "message": "Experience updated",
        "id": str(exp.id),
        "company": exp.company,
        "role": exp.role,
        "location": exp.location,
        "start_date": exp.start_date,
        "end_date": exp.end_date,
        "is_current": exp.is_current,
        "description": exp.description,
        "tech_stack": exp.tech_stack or [],
    }


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
# Resume Import — upload an existing resume, AI-fill the metabase
# ─────────────────────────────────────────────────────────────────────────────

MAX_RESUME_UPLOAD_BYTES = 5 * 1024 * 1024  # 5MB


def _with_links(text: str, links: list) -> str:
    """Prepend the document's hyperlink URLs so the LLM can fill linkedin/github/portfolio."""
    unique = list(dict.fromkeys(links))
    # Prepended: the LLM prompt truncates long text, so trailing links could be lost
    return ("Links in document:\n" + "\n".join(unique) + "\n\n" if unique else "") + text


def _extract_resume_text(filename: str, data: bytes) -> str:
    """Extract plain text from an uploaded PDF or DOCX (sync — run in a thread)."""
    import io
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        # Link URLs live in annotations, not the text layer ("LinkedIn" is just a label)
        links = []
        for page in reader.pages:
            for a in page.get("/Annots") or []:
                uri = ((a.get_object().get("/A") or {}).get("/URI"))
                if uri:
                    links.append(str(uri))
        return _with_links(text, links)
    if name.endswith(".docx"):
        import docx
        doc = docx.Document(io.BytesIO(data))
        parts = [p.text for p in doc.paragraphs]
        # Resumes often lay content out in tables — include them
        for table in doc.tables:
            for row in table.rows:
                parts.extend(cell.text for cell in row.cells)
        # Hyperlink targets are relationships, not text. Contact links are often
        # in the header/footer, so scan those parts too.
        docparts = [doc.part] + [p.part for s in doc.sections for p in (s.header, s.footer)]
        links = [r.target_ref for part in docparts for r in part.rels.values()
                 if r.is_external and r.reltype.endswith("/hyperlink")]
        return _with_links("\n".join(parts), links)
    raise HTTPException(status_code=422, detail="Upload a .pdf or .docx file")


@router.post("/metabase/import-resume")
async def import_resume(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Import an existing resume: extract text (PDF/DOCX) → AI-parse into a
    structured profile → merge into the metabase.

    Merge is ADDITIVE and idempotent (same convention as the seed script):
    skills dedupe by name, experience by company+role, projects by title,
    education by institution. Personal fields only overwrite when the
    parsed value is non-empty — a sparse resume never blanks existing data.
    """
    import asyncio

    data = await file.read()
    if len(data) > MAX_RESUME_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 5MB)")

    text = await asyncio.to_thread(_extract_resume_text, file.filename, data)
    if len(text.strip()) < 200:
        raise HTTPException(
            status_code=422,
            detail="Couldn't extract readable text — is this a scanned/image PDF? "
                   "Try a text-based export of your resume.",
        )

    from app.agents.ai_agent import ai_agent
    # The LLM call is sync/blocking — keep it off the event loop
    try:
        parsed = await asyncio.to_thread(ai_agent.parse_resume, text)
    except Exception as exc:
        logger.error("Resume parse failed for user %s: %s", user.id, exc)
        raise HTTPException(status_code=502, detail="AI parsing failed — please try again")

    counts = {"skills": 0, "experience": 0, "projects": 0, "education": 0}

    # ── Personal (non-empty fields only) ─────────────────────────────────────
    personal = parsed.get("personal") or {}
    result = await db.execute(select(PersonalInfo).where(PersonalInfo.user_id == user.id))
    info = result.scalar_one_or_none()
    allowed = {"full_name", "email", "phone", "location", "linkedin",
               "github", "portfolio", "professional_summary"}
    cleaned = {k: v for k, v in personal.items() if k in allowed and v}
    if info:
        for k, v in cleaned.items():
            setattr(info, k, v)
    elif cleaned:
        db.add(PersonalInfo(user_id=user.id, **cleaned))

    # ── Skills (dedupe by name, case-insensitive) ────────────────────────────
    existing = await db.execute(select(Skill.name).where(Skill.user_id == user.id))
    have = {n.lower() for (n,) in existing.all()}
    for s in parsed.get("skills") or []:
        name = (s.get("name") or "").strip()
        if not name or name.lower() in have:
            continue
        have.add(name.lower())
        db.add(Skill(
            user_id=user.id,
            name=name[:100],
            category=(s.get("category") or "Other")[:100],
            proficiency=s.get("proficiency") if s.get("proficiency") in
                        ("Beginner", "Intermediate", "Advanced", "Expert") else "Intermediate",
            years_experience=float(s.get("years_experience") or 1.0),
            keywords=[],
            is_primary=bool(s.get("is_primary", False)),
        ))
        counts["skills"] += 1

    # ── Experience (dedupe by company+role) ──────────────────────────────────
    for e in parsed.get("experience") or []:
        company, role = (e.get("company") or "").strip(), (e.get("role") or "").strip()
        if not company or not role:
            continue
        dup = await db.execute(select(WorkExperience).where(
            WorkExperience.user_id == user.id,
            WorkExperience.company == company,
            WorkExperience.role == role,
        ))
        if dup.scalar_one_or_none():
            continue
        exp = WorkExperience(
            user_id=user.id, company=company[:200], role=role[:200],
            location=(e.get("location") or "")[:100] or None,
            start_date=(e.get("start_date") or "Unknown")[:20],
            end_date=(e.get("end_date") or "")[:20] or None,
            is_current=bool(e.get("is_current", False)),
            tech_stack=[],
        )
        db.add(exp)
        await db.flush()
        for b in (e.get("bullets") or [])[:10]:
            if b and b.strip():
                db.add(ExperienceBullet(experience_id=exp.id, bullet=b.strip(), keywords=[]))
        counts["experience"] += 1

    # ── Projects (dedupe by title) ────────────────────────────────────────────
    for p in parsed.get("projects") or []:
        title = (p.get("title") or "").strip()
        if not title:
            continue
        dup = await db.execute(select(Project).where(
            Project.user_id == user.id, Project.title == title,
        ))
        if dup.scalar_one_or_none():
            continue
        proj = Project(
            user_id=user.id, title=title[:200],
            description=(p.get("description") or title),
            tech_stack=[t for t in (p.get("tech_stack") or []) if t][:15],
            github_url=(p.get("github_url") or "")[:500] or None,
            is_featured=True,
        )
        db.add(proj)
        await db.flush()
        for b in (p.get("bullets") or [])[:6]:
            if b and b.strip():
                db.add(ProjectBullet(project_id=proj.id, bullet=b.strip(), keywords=[]))
        counts["projects"] += 1

    # ── Education (dedupe by institution) ─────────────────────────────────────
    for ed in parsed.get("education") or []:
        institution = (ed.get("institution") or "").strip()
        if not institution:
            continue
        dup = await db.execute(select(Education).where(
            Education.user_id == user.id, Education.institution == institution,
        ))
        if dup.scalar_one_or_none():
            continue
        db.add(Education(
            user_id=user.id, institution=institution[:200],
            degree=(ed.get("degree") or "Degree")[:200],
            field=(ed.get("field") or "")[:200] or "—",
            start_year=ed.get("start_year"),
            end_year=ed.get("end_year"),
            gpa=(str(ed.get("gpa"))[:10] if ed.get("gpa") else None),
            relevant_coursework=[],
        ))
        counts["education"] += 1

    await db.commit()
    await cache_service.invalidate_profile(user.id)
    logger.info("Resume import for user %s: %s", user.id, counts)
    return {
        "message": "Resume imported",
        "personal_updated": bool(cleaned),
        **counts,
    }


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

    Cached in Redis per profile version for 2 hours (editing skills, roles or
    location changes the key). ?refresh=true refetches, at most once every
    5 minutes per user.

    Response: list of jobs sorted by match_score descending (only ≥60% matches).
    """
    from app.services.job_recommendations import get_recommendations_for_user
    jobs = await get_recommendations_for_user(user.id, db, refresh=refresh)
    return {
        "jobs":    jobs,
        "total":   len(jobs),
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
