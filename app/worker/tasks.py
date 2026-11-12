"""
app/worker/tasks.py
────────────────────
ARQ background job definitions.

WHY BACKGROUND JOBS?
  The full resume generation pipeline (scrape → AI parse → AI tailor →
  AI score → build docx → upload S3) takes 15–45 seconds.  Keeping the
  user waiting on a single HTTP request for that long is bad UX and will
  hit gateway timeouts on platforms like Railway / Render (default 30s).

  ARQ lets us:
    1. Return a job_id immediately (< 100ms response time)
    2. Process the pipeline in a worker process running in parallel
    3. Let the frontend poll /api/jobs/{id}/status every 2 seconds
    4. Show live progress via Server-Sent Events (optional enhancement)

HOW ARQ WORKS:
  - Jobs are pushed to Redis as JSON payloads.
  - One or more worker processes run `arq app.worker.tasks.WorkerSettings`.
  - Each worker picks up jobs, runs the async function, and stores results.
  - Failed jobs are retried up to MAX_TRIES times.

ADDING A NEW TASK:
  1. Define an `async def my_task(ctx, arg1, arg2)` function here.
  2. Add it to WorkerSettings.functions list at the bottom.
  3. Enqueue it from a route: `await pool.enqueue_job("my_task", arg1, arg2)`
"""
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.ai_agent import ai_agent
from app.db.database import AsyncSessionLocal
from app.db.models import JobApplication
from app.services.cache_service import cache_service
from app.services.compaction import local_ats_score
from app.services.metabase_service import metabase_service
from app.services.resume_builder import resume_builder
from app.services.scraper import ScraperError, RobotsBlocked, scraper_service
from app.services.storage_service import StorageError, storage_service
from app.config import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _update_job_status(
    db: AsyncSession,
    job_id: int,
    status: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Atomically update a JobApplication's status (and any extra fields)."""
    values: Dict[str, Any] = {"status": status, "updated_at": datetime.utcnow()}
    if extra:
        values.update(extra)
    await db.execute(
        update(JobApplication).where(JobApplication.id == job_id).values(**values)
    )
    await db.commit()
    logger.info("Job %s → status=%s", job_id, status)


# ─────────────────────────────────────────────────────────────────────────────
# Main task: generate_resume
# ─────────────────────────────────────────────────────────────────────────────

async def generate_resume(
    ctx: Dict,                    # ARQ injects this — contains pool, redis, etc.
    job_app_id,                   # ID of the JobApplication row created in the route
    user_id,
    jd_url: Optional[str],
    jd_text: Optional[str],
    emphasis: Optional[list],
) -> Dict[str, Any]:
    """
    Full resume generation pipeline as an ARQ background task.

    The JobApplication row is created by the API route BEFORE enqueuing this
    task, with status="pending".  We update it throughout the pipeline so the
    frontend can show live progress.

    Args:
        ctx         — ARQ context (we don't use it directly here).
        job_app_id  — PK of the JobApplication row to update.
        user_id     — Owner of this job application.
        jd_url      — URL to scrape (mutually exclusive with jd_text).
        jd_text     — Raw JD text (mutually exclusive with jd_url).
        emphasis    — Keywords the user asked the AI to prioritize.

    Returns:
        Dict with the final result (also persisted to the DB row).
    """
    job_app_id = uuid.UUID(str(job_app_id))
    user_id = uuid.UUID(str(user_id))
    async with AsyncSessionLocal() as db:
        try:
            # ── Mark running ──────────────────────────────────────────────────
            await _update_job_status(db, job_app_id, "running")

            # ── Step 1: Get JD text ───────────────────────────────────────────
            scrape_warning = ""
            if jd_url:
                # Check cache first
                cached_text = await cache_service.get_scraped_url(jd_url)
                if cached_text:
                    jd_text = cached_text
                    logger.info("Scrape cache HIT for %s", jd_url)
                else:
                    try:
                        jd_text, scrape_warning = await scraper_service.scrape(jd_url)
                        await cache_service.set_scraped_url(jd_url, jd_text)
                    except RobotsBlocked as exc:
                        raise ValueError(str(exc))
                    except ScraperError as exc:
                        raise ValueError(str(exc))

            if not jd_text or len(jd_text.strip()) < 100:
                raise ValueError("Job description is too short or empty.")

            # ── Step 2: Parse JD with AI ──────────────────────────────────────
            await _update_job_status(db, job_app_id, "running", {"jd_text": jd_text[:5000]})

            cached_parse = await cache_service.get_parsed_jd(jd_text)
            if cached_parse:
                from app.models.schemas import ParsedJD
                parsed_jd = ParsedJD(**cached_parse)
                logger.info("JD parse cache HIT")
            else:
                logger.info("Calling AI JD parser…")
                parsed_jd = ai_agent.parse_jd(jd_text)
                await cache_service.set_parsed_jd(jd_text, parsed_jd.model_dump())

            # Update job row with parsed JD info
            await _update_job_status(db, job_app_id, "running", {
                "job_title": parsed_jd.job_title,
                "company":   parsed_jd.company,
                "jd_parsed": parsed_jd.model_dump(),
            })

            # ── Step 3: Fetch candidate profile ───────────────────────────────
            cached_profile = await cache_service.get_profile(user_id)
            if cached_profile:
                profile = cached_profile
                logger.info("Profile cache HIT for user %s", user_id)
            else:
                profile = await metabase_service.get_full_profile_async(db, user_id)
                await cache_service.set_profile(user_id, profile)

            if not profile.get("personal"):
                raise ValueError(
                    "Profile incomplete — please fill in Personal Info in the Metabase first."
                )

            # ── Step 4: Tailor resume with AI ─────────────────────────────────
            logger.info("Calling AI resume tailor…")
            tailored = ai_agent.tailor_resume(parsed_jd, profile, emphasis)

            # ── Step 5: Score resume ──────────────────────────────────────────
            logger.info("Scoring resume…")
            try:
                score_data = ai_agent.score_resume(parsed_jd, tailored)
            except Exception as exc:
                logger.warning("ATS scoring failed (non-fatal): %s", exc)
                score_data = local_ats_score(parsed_jd.keywords, parsed_jd.required_skills, tailored)

            # ── Step 6: Build .docx ───────────────────────────────────────────
            company_slug = _slugify(parsed_jd.company or "company", 20)
            title_slug   = _slugify(parsed_jd.job_title or "role", 20)
            filename     = f"resume_{title_slug}_{company_slug}.docx"

            local_path = resume_builder.build(
                personal=profile["personal"],
                tailored=tailored,
                education=profile.get("education", []),
                filename=filename,
            )

            # ── Step 7: Upload to S3/R2 ───────────────────────────────────────
            try:
                s3_key = storage_service.upload_resume(local_path, user_id, filename)
            except StorageError as exc:
                logger.error("Storage upload failed: %s", exc)
                # Fall back to local path so user can still download
                s3_key = str(local_path)

            # ── Step 8: Persist final result ──────────────────────────────────
            await _update_job_status(db, job_app_id, "done", {
                "resume_s3_key":  s3_key,
                "resume_filename": filename,
                "ats_score":       score_data.get("total_score", 0),
                "ats_breakdown":   score_data,
                "skills_matched":  score_data.get("matched_skills", []),
                "skills_missing":  score_data.get("missing_skills", []),
            })

            result = {
                "job_id":         job_app_id,
                "status":         "done",
                "job_title":      parsed_jd.job_title,
                "company":        parsed_jd.company,
                "ats_score":      score_data.get("total_score", 0),
                "ats_breakdown":  score_data,
                "skills_matched": score_data.get("matched_skills", []),
                "skills_missing": score_data.get("missing_skills", []),
                "s3_key":         s3_key,
                "filename":       filename,
                "message":        f"✅ Resume generated! ATS Score: {score_data.get('total_score', 0):.1f}"
                                  + (f"\n{scrape_warning}" if scrape_warning else ""),
            }
            logger.info("Job %s completed — ATS score=%.1f", job_app_id, result["ats_score"])
            return result

        except Exception as exc:
            error_msg = str(exc)
            logger.error("Job %s FAILED: %s", job_app_id, error_msg, exc_info=True)
            await _update_job_status(db, job_app_id, "failed", {"error_message": error_msg})
            # Re-raise so ARQ records the failure and can retry
            raise


# ─────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────────

def _slugify(text: str, max_len: int) -> str:
    # Collapse any run of non-alphanumeric characters (spaces, slashes, dots,
    # plus signs, parens, ...) into a single underscore — job titles like
    # "AI/ML Engineer" or "C++ Developer" would otherwise leak characters
    # like "/" straight into a filesystem path, which pathlib silently
    # treats as a subdirectory that was never created, breaking the save.
    slug = re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')
    return (slug or 'untitled')[:max_len]


# ─────────────────────────────────────────────────────────────────────────────
# ARQ Worker Settings
# ─────────────────────────────────────────────────────────────────────────────

class WorkerSettings:
    """
    ARQ reads this class to configure the worker process.

    Start the worker with:
      arq app.worker.tasks.WorkerSettings

    Or in docker-compose:
      command: arq app.worker.tasks.WorkerSettings
    """
    from arq.connections import RedisSettings as _RS

    redis_settings = _RS.from_dsn(settings.REDIS_URL)

    # Every async function listed here becomes an enqueueable task
    functions = [generate_resume]

    # Max number of jobs this worker will run simultaneously
    max_jobs = settings.WORKER_CONCURRENCY

    # Queue poll interval — see ARQ_POLL_DELAY in config.py (metered free
    # Redis tiers need this raised to ~10s to stay inside command budgets)
    poll_delay = settings.ARQ_POLL_DELAY

    # Hard timeout: kill the job if it runs longer than this
    job_timeout = settings.JOB_TIMEOUT

    # Retry policy: retry up to 2 times with a 5-second delay
    max_tries = 2

    # Keep job results in Redis for 24 hours (for polling)
    keep_result = 86_400

    # Startup / shutdown hooks
    async def on_startup(ctx):
        logger.info("ARQ worker started (concurrency=%d)", settings.WORKER_CONCURRENCY)

    async def on_shutdown(ctx):
        await cache_service.close()
        logger.info("ARQ worker shut down cleanly")
