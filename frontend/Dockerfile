##############################################################################
# frontend/Dockerfile — multi-stage build
#
# Stages:
#   development — Vite dev server with hot-reload (used by docker-compose)
#   build        — compiles static assets into ../app/static/dist
#
# Build production assets:
#   docker build --target build -t ats-ready-frontend:build .
##############################################################################

FROM node:20-alpine AS base
WORKDIR /app
COPY package*.json ./
RUN npm install


# ── Development ───────────────────────────────────────────────────────────────
FROM base AS development

# Source is mounted at runtime (docker-compose volume) — don't COPY here
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]


# ── Build (static assets for FastAPI to serve) ─────────────────────────────────
FROM base AS build
COPY . .
RUN npm run build
