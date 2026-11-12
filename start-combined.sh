#!/bin/sh
# ──────────────────────────────────────────────────────────────────────────────
# Single-container entrypoint for free PaaS tiers (Koyeb/Render): one free
# service = one container, so the API and the ARQ worker share it here.
# Not used by docker-compose (dev or prod VM) — those run separate services.
#
# Usage: override the container command with  sh start-combined.sh
# Respects $PORT (PaaS-injected); defaults to 8000.
# ──────────────────────────────────────────────────────────────────────────────
set -e

echo "[start-combined] applying database migrations…"
alembic upgrade head

echo "[start-combined] starting ARQ worker (background, auto-restart)…"
# Restart the worker if it crashes, so queued jobs keep draining while the API
# stays up. 5s back-off avoids a tight crash loop.
(
  while true; do
    arq app.worker.tasks.WorkerSettings || echo "[start-combined] worker exited ($?), restarting in 5s"
    sleep 5
  done
) &
SUPERVISOR_PID=$!

# When the API exits, take the whole container down so the platform restarts it.
trap 'kill $SUPERVISOR_PID 2>/dev/null' EXIT

echo "[start-combined] starting API on port ${PORT:-8000}…"
exec uvicorn main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1 \
  --loop uvloop \
  --http httptools \
  --proxy-headers \
  --forwarded-allow-ips "*"
