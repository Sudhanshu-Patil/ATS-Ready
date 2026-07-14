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

echo "[start-combined] starting ARQ worker (background)…"
arq app.worker.tasks.WorkerSettings &
WORKER_PID=$!

# If either process dies, take the container down so the platform restarts it
# cleanly rather than running half a stack.
trap 'kill $WORKER_PID 2>/dev/null' EXIT

echo "[start-combined] starting API on port ${PORT:-8000}…"
exec uvicorn main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1 \
  --loop uvloop \
  --http httptools \
  --proxy-headers \
  --forwarded-allow-ips "*"
