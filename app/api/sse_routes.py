"""
app/api/sse_routes.py
──────────────────────
Server-Sent Events endpoint for real-time resume generation progress.

WHY SSE INSTEAD OF POLLING?
  Polling (GET /jobs/{id}/status every 2s) works but:
  - Creates unnecessary DB queries (most return "running" with no change)
  - Adds latency — user waits up to 2s after job completes
  - Wastes bandwidth on mobile

  SSE keeps a single HTTP connection open and pushes updates the instant
  they happen. The browser's native EventSource API handles reconnection
  automatically if the connection drops.

HOW IT WORKS:
  1. Client opens: GET /api/jobs/{job_id}/stream
     (with Authorization: Bearer <token> header)
  2. Server polls the DB every 1.5s and sends an SSE event on each change
  3. When status == "done" or "failed", server sends final event and closes

FRONTEND USAGE:
  const source = new EventSource(
    `/api/jobs/${jobId}/stream`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  source.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.status === 'done') {
      showResult(data.result);
      source.close();
    }
  };
"""
import asyncio
import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.db.database import AsyncSessionLocal
from app.db.models import JobApplication, User
from app.services.storage_service import storage_service

sse_router = APIRouter()

# How often (seconds) to check the DB for status changes
POLL_INTERVAL = 1.5

# Maximum time (seconds) to keep the SSE connection open before closing
# (client will reconnect automatically via EventSource)
MAX_STREAM_DURATION = 120


async def _job_event_stream(
    job_id: uuid.UUID,
    user_id: uuid.UUID,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE-formatted strings.
    Polls the DB until the job reaches a terminal state.
    """
    elapsed = 0.0
    last_status = None

    while elapsed < MAX_STREAM_DURATION:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(JobApplication).where(
                    JobApplication.id == job_id,
                    JobApplication.user_id == user_id,
                )
            )
            job = result.scalar_one_or_none()

        if not job:
            yield _sse_event({"error": "Job not found"}, event="error")
            return

        # Only send an event if something changed
        if job.status != last_status:
            last_status = job.status
            payload = {
                "job_id": str(job.id),
                "status": job.status,
                "error":  job.error_message,
                "result": None,
            }

            if job.status == "done" and job.resume_s3_key:
                download_url = storage_service.get_download_url(
                    job.resume_s3_key,
                    job.resume_filename or "resume.docx",
                )
                payload["result"] = {
                    "job_id":         str(job.id),
                    "job_title":      job.job_title,
                    "company":        job.company,
                    "ats_score":      job.ats_score,
                    "ats_breakdown":  job.ats_breakdown or {},
                    "skills_matched": job.skills_matched or [],
                    "skills_missing": job.skills_missing or [],
                    "download_url":   download_url,
                }

            yield _sse_event(payload)

            # Terminal states — close the stream
            if job.status in ("done", "failed"):
                return

        await asyncio.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL

    # Timeout — tell client to reconnect
    yield _sse_event({"status": "timeout", "message": "Reconnect to continue polling"})


def _sse_event(data: dict, event: str = "message") -> str:
    """Format a dict as an SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@sse_router.get("/jobs/{job_id}/stream")
async def stream_job_status(
    job_id: str,
    user: User = Depends(get_current_user),
):
    """
    Stream real-time job status updates via Server-Sent Events.

    Connect once — receive updates as they happen, no polling needed.
    The stream closes automatically when the job completes or fails.

    Headers required:
      Authorization: Bearer <access_token>

    Event format:
      event: message
      data: {"job_id": "...", "status": "running"|"done"|"failed", "result": {...}}
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid job_id format")

    return StreamingResponse(
        _job_event_stream(job_uuid, user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Connection":       "keep-alive",
        },
    )
