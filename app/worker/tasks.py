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
import asyncio
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from arq import cron
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.ai_agent import ai_agent
from app.db.database import AsyncSessionLocal
from app.services import applications, assistant, credits, persona, suggestion_store
from app.services.ats_score import jd_terms as extract_terms
from app.services.ats_score import score_view, terms_owned, view_from_resume, view_from_text
from app.services.documents import fit_resume
from app.services.grounding import add_known_terms, enforce_letter, enforce_resume, source_text
from app.services.usage import mark_failed, tracked
from app.db.models import AssistantRequest, CoverLetter, InterviewPrep, JobApplication
from app.services.cache_service import cache_service
from app.services.content_service import build_context, friendly_error
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

@tracked("resume")
async def generate_resume(
    ctx: Dict,                    # ARQ injects this — contains pool, redis, etc.
    job_app_id,                   # ID of the JobApplication row created in the route
    user_id,
    jd_url: Optional[str],
    jd_text: Optional[str],
    emphasis: Optional[list],
    baseline_id: Optional[str] = None,       # the user's uploaded resume to compare against
    application_id: Optional[str] = None,    # the job this resume belongs to (credits and tracking)
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
        job_row = await db.get(JobApplication, job_app_id)
        job_asked_at = job_row.created_at if job_row else None      # when the user asked, for the timeline
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
            await _update_job_status(db, job_app_id, "running", {"jd_text": jd_text[:12000]})

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

            # Tracking: this job is now on the user's list, dated when they asked. Never fails the resume.
            await _track_job(db, user_id, source="resume", kind="resume", summary="Tailored a resume",
                             jd_text=jd_text, jd_url=jd_url, parsed_jd=parsed_jd, asked_at=job_asked_at,
                             application_id=application_id)

            # ── Step 4: What the user already has, and the suggestion list for this JD ──
            terms = extract_terms(parsed_jd)
            term_names = [t.term for t in terms]
            own_text = source_text(profile)
            baseline_text, baseline_name = "", ""
            if baseline_id:
                stored = await cache_service.get(f"baseline:{user_id}:{baseline_id}") or {}
                baseline_text, baseline_name = stored.get("text", ""), stored.get("filename", "")
            # Built once per job description, then reused by every later version (see suggestion_store).
            sugg = await suggestion_store.get_or_create(
                db, user_id, jd_text, parsed_jd.job_title, terms, own_text + "\n" + baseline_text)
            suggestion_store.apply_selected(sugg, emphasis or [])
            await db.commit()
            # Skills the user vouches for: ticked earlier or now, or already in the resume they uploaded.
            confirmed = list(dict.fromkeys(suggestion_store.applied_terms(sugg) + terms_owned(terms, baseline_text)))

            # ── Step 5: Tailor, then enforce that nothing was invented ────────
            logger.info("Calling AI resume tailor…")
            tailored = await asyncio.to_thread(ai_agent.tailor_resume, parsed_jd, profile, confirmed)
            tailored, corrections = enforce_resume(tailored, profile, term_names, confirmed)
            tailored, _added = add_known_terms(tailored, terms_owned(terms, own_text) + confirmed)

            # One page, always: measure the real layout, shrink fonts slightly, then trim the lowest-value
            # content until it fits. The same plan renders the DOCX now and the PDF later.
            fitted = await asyncio.to_thread(fit_resume, {
                "personal": profile["personal"], "tailored": tailored, "education": profile.get("education", [])})

            # Score what the user will actually download (deterministic: same input, same score).
            view = view_from_resume(fitted["personal"], fitted["tailored"], fitted["education"])
            score_data = score_view(view, terms)
            open_items = suggestion_store.open_items(sugg)
            score_data.update({
                "open_suggestions": open_items,
                "applied_terms": suggestion_store.applied_terms(sugg),
                "projected_score": (score_view(view, terms, [i["term"] for i in open_items])["total_score"]
                                    if open_items else score_data["total_score"]),
                "corrections": len(corrections),
            })
            if baseline_id and not baseline_text:
                score_data["baseline_expired"] = True        # held for 2 hours; the UI asks for it again
            if baseline_text:
                base = score_view(view_from_text(baseline_text), terms)
                score_data["baseline"] = {
                    "filename": baseline_name, "total_score": base["total_score"],
                    **{k: base[k] for k in ("keyword_score", "skills_score", "action_verb_score", "format_score")},
                    "missing_skills": base["missing_skills"][:12],
                }
                score_data["score_gain"] = round(score_data["total_score"] - base["total_score"], 1)

            # ── Step 6: Build .docx ───────────────────────────────────────────
            company_slug = _slugify(parsed_jd.company or "company", 20)
            title_slug   = _slugify(parsed_jd.job_title or "role", 20)
            filename     = f"resume_{title_slug}_{company_slug}.docx"

            local_path = resume_builder.build(
                personal=fitted["personal"],
                tailored=fitted["tailored"],
                education=fitted["education"],
                filename=filename,
                scale=fitted["scale"],
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
                "resume_data": fitted,
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
            await _credit_done(db, application_id)
            return result

        except Exception as exc:
            error_msg = str(exc)
            logger.error("Job %s FAILED: %s", job_app_id, error_msg, exc_info=True)
            await _update_job_status(db, job_app_id, "failed", {"error_message": error_msg})
            await _credit_release(db, application_id, "resume")
            # Re-raise so ARQ records the failure and can retry
            raise


# ─────────────────────────────────────────────────────────────────────────────
# Cover letter / interview prep tasks
# ─────────────────────────────────────────────────────────────────────────────

@tracked("cover_letter")
async def generate_cover_letter_task(ctx, letter_id, user_id, jd_text, job_app_id, tone,
                                     limit=None, limit_unit=None, company=None, company_skipped=False,
                                     application_id=None):
    """Fill in a pending CoverLetter row. Failures are recorded on the row (no
    arq retry: the user sees the error and can resubmit)."""
    async with AsyncSessionLocal() as db:
        row = await db.get(CoverLetter, uuid.UUID(letter_id))
        if row is None:
            return
        row.status = "running"
        await db.commit()
        try:
            profile, parsed_jd, tailored, job_app = await build_context(
                jd_text, uuid.UUID(user_id), db, job_app_id)
            # A letter addressed to "the company" is useless, so ask before writing. The user can name it, or choose
            # to go without (company_skipped). Status needs_input is shown as a popup until answered.
            if company and company.strip():
                parsed_jd.company = company.strip()[:200]
            elif company_skipped:
                parsed_jd.company = None
            elif applications.is_unclear_company(parsed_jd.company):
                row.status, row.job_title = "needs_input", parsed_jd.job_title
                await db.commit()
                return
            await _track_job(db, uuid.UUID(user_id), source="cover_letter", kind="cover_letter",
                             summary="Asked for a cover letter", jd_text=jd_text, jd_url=None, parsed_jd=parsed_jd,
                             asked_at=row.created_at, application_id=application_id)
            result = await asyncio.to_thread(
                ai_agent.generate_cover_letter, parsed_jd, profile, tailored, tone, limit_unit, limit)
            row.job_app_id = job_app.id if job_app else None
            row.job_title, row.company = parsed_jd.job_title, parsed_jd.company
            row.subject = result.get("subject")
            # Nothing the candidate did not say: drop sentences with invented figures or claimed tools.
            full_profile = (await cache_service.get_profile(user_id)
                            or await metabase_service.get_full_profile_async(db, uuid.UUID(user_id)))
            saved = await suggestion_store.load(db, uuid.UUID(user_id), jd_text)
            body, fixes = enforce_letter(
                result.get("body") or "", full_profile, jd_text, [t.term for t in extract_terms(parsed_jd)],
                suggestion_store.applied_terms(saved) if saved else [])
            if fixes:
                logger.info("Cover letter %s: %d unsupported sentence(s) removed", letter_id, len(fixes))
            row.body = body
            row.word_count = len(row.body.split())            # real count, not the model's estimate
            row.highlights = result.get("highlights", [])
            row.status = "done"
            await credits.succeeded(db, application_id)
        except Exception as exc:
            logger.error("Cover letter %s FAILED: %s", letter_id, exc, exc_info=True)
            await db.rollback()
            row.status, row.error = "failed", friendly_error(exc)
            await credits.release(db, application_id, "cover_letter")
            mark_failed()
        await db.commit()


@tracked("interview_prep")
async def generate_interview_prep_task(ctx, prep_id, user_id, jd_text, job_app_id, application_id=None):
    async with AsyncSessionLocal() as db:
        row = await db.get(InterviewPrep, uuid.UUID(prep_id))
        if row is None:
            return
        row.status = "running"
        await db.commit()
        try:
            profile, parsed_jd, tailored, job_app = await build_context(
                jd_text, uuid.UUID(user_id), db, job_app_id)
            await _track_job(db, uuid.UUID(user_id), source="interview_prep", kind="interview_prep",
                             summary="Prepared for the interview", jd_text=jd_text, jd_url=None, parsed_jd=parsed_jd,
                             asked_at=row.created_at, application_id=application_id)
            result = await asyncio.to_thread(
                ai_agent.generate_interview_prep, parsed_jd, profile, tailored)
            row.job_app_id = job_app.id if job_app else None
            row.job_title, row.company = parsed_jd.job_title, parsed_jd.company
            row.questions = result.get("questions", [])
            row.quick_tips = result.get("quick_tips", [])
            row.red_flags_to_avoid = result.get("red_flags_to_avoid", [])
            row.questions_to_ask = result.get("questions_to_ask", [])
            row.status = "done"
            await credits.succeeded(db, application_id)
        except Exception as exc:
            logger.error("Interview prep %s FAILED: %s", prep_id, exc, exc_info=True)
            await db.rollback()
            row.status, row.error = "failed", friendly_error(exc)
            await credits.release(db, application_id, "interview_prep")
            mark_failed()
        await db.commit()


async def _credit_done(db, application_id) -> None:
    """Credit bookkeeping must never break the feature it belongs to."""
    try:
        await credits.succeeded(db, credits.parse_uuid(application_id))
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("Could not record a successful run", exc_info=True)


async def _credit_release(db, application_id, kind) -> None:
    try:
        await credits.release(db, credits.parse_uuid(application_id), kind)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.warning("Could not give a failed run back", exc_info=True)


async def _track_job(db, user_id, *, source, kind, summary, jd_text, jd_url, parsed_jd, asked_at,
                     application_id=None) -> None:
    """Add this job to the user's application list, dated when THEY asked (not when the worker got to it).
    Company/role come from the job description's analysis; if the posting hides the company, the application is
    created anyway and the UI asks the user. Tracking must never break the feature it is attached to."""
    try:
        company = parsed_jd.company if not applications.is_unclear_company(parsed_jd.company) else None
        app = await applications.track(
            db, user_id, source=source, kind=kind, summary=summary, jd_text=jd_text, company=company,
            role=parsed_jd.job_title, job_url=jd_url, occurred_at=asked_at,
            application_id=credits.parse_uuid(application_id))
        await persona.record_target(db, user_id, parsed_jd.job_title, [t.term for t in extract_terms(parsed_jd)[:5]])
        await db.commit()
        logger.info("Tracked %s for user %s -> application %s (needs=%s)", source, user_id, app.id, app.needs)
    except Exception:
        await db.rollback()
        logger.warning("Application tracking failed (non-fatal)", exc_info=True)


@tracked("assistant")
async def generate_assistant_answers_task(ctx, request_id, user_id, only=None):
    """Answer the questions of one AssistantRequest. `only` re-runs just those question ids."""
    async with AsyncSessionLocal() as db:
        req = await db.get(AssistantRequest, uuid.UUID(request_id))
        if req is None:
            return
        req.status = "running"
        await db.commit()
        try:
            await assistant.process_request(db, req, only)
            await credits.succeeded(db, req.application_id)
        except Exception as exc:
            logger.error("Assistant request %s FAILED: %s", request_id, exc, exc_info=True)
            await db.rollback()
            req.status, req.error = "failed", friendly_error(exc)
            if only is None:                       # a partial re-run did not count its questions again
                await credits.release(db, req.application_id, "answers", len(req.questions or []))
            mark_failed()
        await db.commit()


# Longer than any legitimate queue wait or run (JOB_TIMEOUT is per run).
STALE_AFTER = timedelta(seconds=max(2 * settings.JOB_TIMEOUT, 900))


async def reap_stale_jobs(ctx):
    """Cron: rows stuck in pending/running (worker crash, lost job) -> failed,
    so the UI never spins forever and the per-user active cap frees up."""
    cutoff = datetime.utcnow() - STALE_AFTER
    async with AsyncSessionLocal() as db:
        for model, col, kind in ((JobApplication, "error_message", "resume"), (CoverLetter, "error", "cover_letter"),
                                 (InterviewPrep, "error", "interview_prep")):
            stale = model.status.in_(("pending", "running")) & (model.created_at < cutoff)
            jobs = (await db.execute(select(model.application_id).where(stale))).scalars().all()
            res = await db.execute(
                update(model).where(stale).values(status="failed", **{col: "Timed out. Please try again."})
            )
            if res.rowcount:
                logger.warning("Reaped %d stale %s rows", res.rowcount, model.__tablename__)
            for application_id in jobs:                       # a run that never finished gives its use back
                await credits.release(db, application_id, kind)
        await db.commit()


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
    functions = [generate_resume, generate_cover_letter_task, generate_interview_prep_task,
                 generate_assistant_answers_task]

    # Every 5 minutes: fail jobs stuck in pending/running
    cron_jobs = [cron(reap_stale_jobs, minute=set(range(0, 60, 5)), run_at_startup=True)]

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
