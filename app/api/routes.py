"""
API Routes
----------
All endpoints for the Resume AI Agent.
"""
import logging
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.models import (
    get_db, JobApplication, Skill, Project, ProjectBullet,
    WorkExperience, ExperienceBullet, Education, PersonalInfo
)
from app.models.schemas import (
    GenerateResumeRequest, GenerateResumeResponse, ATSBreakdown,
    SkillCreate, SkillOut, ProjectCreate, ProjectOut,
    WorkExperienceCreate, WorkExperienceOut, PersonalInfoUpdate,
    JobApplicationOut,
)
from app.services.scraper import scraper_service, ScraperError, RobotsBlocked
from app.services.metabase_service import metabase_service
from app.services.resume_builder import resume_builder
from app.agents.ai_agent import ai_agent

router = APIRouter()
logger = logging.getLogger(__name__)


# ─── Resume Generation (Main Endpoint) ─────────────────────────────────────────

@router.post("/generate-resume", response_model=GenerateResumeResponse)
async def generate_resume(
    request: GenerateResumeRequest,
    db: Session = Depends(get_db),
):
    """
    Main endpoint. Provide a JD URL or text → get an ATS-optimized resume.
    
    Flow:
      1. Scrape JD URL (if provided) or use JD text
      2. AI parses JD into structured format
      3. Fetch candidate profile from metabase
      4. AI tailors resume content
      5. Score resume for ATS
      6. Generate .docx file
      7. Return download link + ATS report
    """
    scrape_warning = ""

    # ── Step 1: Get JD Text ────────────────────────────────────────────────────
    if request.jd_url:
        try:
            jd_text, scrape_warning = await scraper_service.scrape(request.jd_url)
        except RobotsBlocked as e:
            raise HTTPException(status_code=403, detail=str(e))
        except ScraperError as e:
            raise HTTPException(status_code=422, detail=str(e))
    else:
        jd_text = request.jd_text

    if not jd_text or len(jd_text.strip()) < 100:
        raise HTTPException(status_code=422, detail="Job description too short or empty.")

    # ── Step 2: AI Parse JD ────────────────────────────────────────────────────
    logger.info("Parsing JD with AI...")
    try:
        parsed_jd = ai_agent.parse_jd(jd_text)
    except Exception as e:
        logger.error(f"JD parsing failed: {e}")
        raise HTTPException(status_code=500, detail=f"AI JD parsing failed: {str(e)}")

    # ── Step 3: Fetch Candidate Profile ───────────────────────────────────────
    logger.info("Fetching candidate profile from metabase...")
    profile = metabase_service.get_full_profile(db)

    if not profile.get("personal"):
        raise HTTPException(
            status_code=400,
            detail="No personal info found. Run `python scripts/seed_metabase.py` first."
        )

    # ── Step 4: AI Tailor Resume ───────────────────────────────────────────────
    logger.info("Tailoring resume with AI...")
    try:
        tailored = ai_agent.tailor_resume(parsed_jd, profile, request.emphasis)
    except Exception as e:
        logger.error(f"Resume tailoring failed: {e}")
        raise HTTPException(status_code=500, detail=f"AI tailoring failed: {str(e)}")

    # ── Step 5: ATS Scoring ────────────────────────────────────────────────────
    logger.info("Scoring resume against JD...")
    try:
        score_data = ai_agent.score_resume(parsed_jd, tailored)
    except Exception as e:
        logger.warning(f"ATS scoring failed (non-fatal): {e}")
        score_data = {
            "total_score": 0,
            "keyword_score": 0,
            "skills_score": 0,
            "action_verb_score": 0,
            "format_score": 0,
            "matched_keywords": [],
            "missing_keywords": [],
            "matched_skills": [],
            "missing_skills": [],
            "suggestions": [],
        }

    # ── Step 6: Build DOCX ────────────────────────────────────────────────────
    logger.info("Building .docx resume...")
    company_slug = (parsed_jd.company or "company").lower().replace(" ", "_")[:20]
    title_slug = (parsed_jd.job_title or "role").lower().replace(" ", "_")[:20]
    filename = f"resume_{title_slug}_{company_slug}.docx"

    try:
        resume_path = resume_builder.build(
            personal=profile["personal"],
            tailored=tailored,
            education=profile.get("education", []),
            filename=filename,
        )
    except Exception as e:
        logger.error(f"DOCX build failed: {e}")
        raise HTTPException(status_code=500, detail=f"Resume generation failed: {str(e)}")

    # ── Step 7: Save to DB ────────────────────────────────────────────────────
    job_app = JobApplication(
        job_title=parsed_jd.job_title,
        company=parsed_jd.company,
        jd_url=request.jd_url,
        jd_text=jd_text[:5000],
        jd_parsed=parsed_jd.model_dump(),
        resume_path=str(resume_path),
        ats_score=score_data.get("total_score", 0),
        ats_breakdown=score_data,
        skills_matched=score_data.get("matched_skills", []),
        skills_missing=score_data.get("missing_skills", []),
    )
    db.add(job_app)
    db.commit()
    db.refresh(job_app)

    # ── Build Response ─────────────────────────────────────────────────────────
    message = f"✅ Resume generated!"
    if scrape_warning:
        message += f"\n{scrape_warning}"

    ats_breakdown = ATSBreakdown(
        total_score=score_data.get("total_score", 0),
        keyword_score=score_data.get("keyword_score", 0),
        skills_score=score_data.get("skills_score", 0),
        action_verb_score=score_data.get("action_verb_score", 0),
        format_score=score_data.get("format_score", 0),
        matched_keywords=score_data.get("matched_keywords", []),
        missing_keywords=score_data.get("missing_keywords", []),
        matched_skills=score_data.get("matched_skills", []),
        missing_skills=score_data.get("missing_skills", []),
        suggestions=score_data.get("suggestions", []),
    )

    return GenerateResumeResponse(
        job_id=job_app.id,
        job_title=parsed_jd.job_title,
        company=parsed_jd.company,
        ats_score=score_data.get("total_score", 0),
        ats_breakdown=ats_breakdown,
        resume_path=str(resume_path),
        download_url=f"/api/download/{job_app.id}",
        skills_matched=score_data.get("matched_skills", []),
        skills_missing=score_data.get("missing_skills", []),
        message=message,
    )


@router.get("/download/{job_id}")
async def download_resume(job_id: int, db: Session = Depends(get_db)):
    """Download the generated .docx resume."""
    job = db.query(JobApplication).filter(JobApplication.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job application not found")
    path = Path(job.resume_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resume file not found on disk")
    return FileResponse(
        path=str(path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.name,
    )


@router.get("/ats-score/{job_id}")
async def get_ats_score(job_id: int, db: Session = Depends(get_db)):
    """Get detailed ATS score breakdown for a previously generated resume."""
    job = db.query(JobApplication).filter(JobApplication.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.id,
        "job_title": job.job_title,
        "company": job.company,
        "ats_score": job.ats_score,
        "breakdown": job.ats_breakdown,
        "skills_matched": job.skills_matched,
        "skills_missing": job.skills_missing,
    }


# ─── Job Applications History ──────────────────────────────────────────────────

@router.get("/jobs", response_model=List[dict])
async def list_jobs(db: Session = Depends(get_db)):
    """List all previously generated resumes."""
    jobs = db.query(JobApplication).order_by(JobApplication.created_at.desc()).all()
    return [
        {
            "id": j.id,
            "job_title": j.job_title,
            "company": j.company,
            "ats_score": j.ats_score,
            "created_at": str(j.created_at),
            "download_url": f"/api/download/{j.id}",
        }
        for j in jobs
    ]


# ─── Metabase CRUD: Personal Info ─────────────────────────────────────────────

@router.get("/metabase/personal")
async def get_personal_info(db: Session = Depends(get_db)):
    info = db.query(PersonalInfo).first()
    if not info:
        raise HTTPException(status_code=404, detail="No personal info found")
    return info


@router.post("/metabase/personal")
async def upsert_personal_info(data: PersonalInfoUpdate, db: Session = Depends(get_db)):
    info = db.query(PersonalInfo).first()
    if info:
        for k, v in data.model_dump().items():
            setattr(info, k, v)
    else:
        info = PersonalInfo(**data.model_dump())
        db.add(info)
    db.commit()
    return {"message": "Personal info saved"}


# ─── Metabase CRUD: Skills ────────────────────────────────────────────────────

@router.get("/metabase/skills", response_model=List[SkillOut])
async def get_skills(db: Session = Depends(get_db)):
    return db.query(Skill).all()


@router.post("/metabase/skills", response_model=SkillOut)
async def add_skill(data: SkillCreate, db: Session = Depends(get_db)):
    # Check duplicate
    existing = db.query(Skill).filter(Skill.name == data.name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Skill '{data.name}' already exists")
    skill = Skill(**data.model_dump())
    db.add(skill)
    db.commit()
    db.refresh(skill)
    return skill


@router.delete("/metabase/skills/{skill_id}")
async def delete_skill(skill_id: int, db: Session = Depends(get_db)):
    skill = db.query(Skill).filter(Skill.id == skill_id).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    db.delete(skill)
    db.commit()
    return {"message": f"Skill '{skill.name}' deleted"}


# ─── Metabase CRUD: Projects ──────────────────────────────────────────────────

@router.get("/metabase/projects")
async def get_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).all()
    return [
        {
            "id": p.id,
            "title": p.title,
            "tech_stack": p.tech_stack,
            "is_featured": p.is_featured,
            "bullets_count": db.query(ProjectBullet).filter(ProjectBullet.project_id == p.id).count(),
        }
        for p in projects
    ]


@router.post("/metabase/projects")
async def add_project(data: ProjectCreate, db: Session = Depends(get_db)):
    bullets = data.bullets
    project_data = data.model_dump(exclude={"bullets"})
    project = Project(**project_data)
    db.add(project)
    db.flush()

    for b in bullets:
        bullet = ProjectBullet(project_id=project.id, **b.model_dump())
        db.add(bullet)

    db.commit()
    db.refresh(project)
    return {"message": "Project added", "id": project.id}


# ─── Metabase CRUD: Work Experience ──────────────────────────────────────────

@router.get("/metabase/experience")
async def get_experience(db: Session = Depends(get_db)):
    exps = db.query(WorkExperience).all()
    return [
        {
            "id": e.id,
            "company": e.company,
            "role": e.role,
            "start_date": e.start_date,
            "end_date": e.end_date,
            "is_current": e.is_current,
        }
        for e in exps
    ]


@router.post("/metabase/experience")
async def add_experience(data: WorkExperienceCreate, db: Session = Depends(get_db)):
    bullets = data.bullets
    exp_data = data.model_dump(exclude={"bullets"})
    exp = WorkExperience(**exp_data)
    db.add(exp)
    db.flush()

    for b in bullets:
        bullet = ExperienceBullet(experience_id=exp.id, **b.model_dump())
        db.add(bullet)

    db.commit()
    db.refresh(exp)
    return {"message": "Experience added", "id": exp.id}
