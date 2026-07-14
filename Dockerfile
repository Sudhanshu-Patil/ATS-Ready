##############################################################################
# Dockerfile — multi-stage build
#
# Stages:
#   base        — common Python + system dependencies
#   development — base + dev tools, hot-reload ready
#   production  — base, no dev tools, runs as non-root user
#
# Build production image:
#   docker build --target production -t ats-ready:latest .
##############################################################################

# ── Base ─────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

# System dependencies:
#   gcc + libpq-dev — needed to compile psycopg2 from source
#   libxml2 + libxslt — needed by lxml (used by BeautifulSoup)
#   curl             — for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libxml2-dev \
    libxslt-dev \
    curl \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (Docker layer cache: only re-runs
# when requirements.txt changes, not on every source file change)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Create outputs directory
RUN mkdir -p /app/outputs


# ── Development ───────────────────────────────────────────────────────────────
FROM base AS development

# Dev extras: watchfiles for hot-reload, python-dotenv for CLI scripts.
# pytest/pytest-asyncio pinned here AND in .github/workflows/ci.yaml —
# keep both in sync so CI runs the same test-runner versions as dev.
RUN pip install --no-cache-dir watchfiles python-dotenv pytest==9.1.1 pytest-asyncio==1.4.0 httpx

# Mount source at runtime (docker-compose volume) — don't COPY here
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]


# ── Frontend build (assets baked into the production image) ──────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /fe
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
# vite.config.js outDir is ../app/static/dist → lands at /app/static/dist
RUN npm run build


# ── Production ────────────────────────────────────────────────────────────────
FROM base AS production

# Copy source code
COPY . .

# Built SPA — copied AFTER `COPY . .` so it wins over any stale local dist.
# main.py serves it (static mount + client-side-routing fallback).
COPY --from=frontend-build /app/static/dist ./app/static/dist

# Run as non-root for security
RUN addgroup --system appgroup \
 && adduser --system --ingroup appgroup appuser \
 && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

# Use 2 uvicorn workers per container.
# For horizontal scaling: run multiple containers behind a load balancer.
# Adjust --workers based on your container's CPU count (2 * CPUs + 1 is common).
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]


# ── Production (combined, single-container) ───────────────────────────────────
# LAST stage on purpose: platforms that build a Dockerfile without a target
# selector (Hugging Face Spaces) get this — API + ARQ worker + migrations in
# one container via start-combined.sh. docker-compose.prod.yaml is unaffected
# (it pins `target: production` explicitly).
FROM production AS production-combined
CMD ["sh", "start-combined.sh"]
