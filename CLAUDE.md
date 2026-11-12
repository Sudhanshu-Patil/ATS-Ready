# ATS-Ready: guide for contributors and AI assistants

AI resume tailoring app: FastAPI + SQLAlchemy (async) + Postgres + Redis + arq worker, React/Vite/Tailwind/Zustand
frontend, Groq LLMs. Free-tier production (Render, Neon, Upstash). Read [PRODUCTION-CHECKLIST.md](PRODUCTION-CHECKLIST.md)
for operations.

## Commands

```bash
# Backend (use the venv: venv/Scripts/python on Windows)
pytest -q                                   # 150+ tests, needs local Postgres + Redis (docker compose up db redis)
ruff check app main.py tests scripts evals  # lint (config in ruff.toml)
alembic upgrade head                        # migrations (head: 0008)
uvicorn main:app --reload                   # API on :8000
arq app.worker.tasks.WorkerSettings         # worker (LLM jobs run here, one at a time)
python -m evals.run_evals                   # REAL model quality + prompt-injection evals (spends Groq quota)

# Frontend (cd frontend)
npm run dev | test | lint | typecheck | build
# E2E (cd e2e): needs API + worker + Vite running, LLM_FAKE=true RATE_LIMIT_ENABLED=false BILLING_ENABLED=false
npx playwright test                         # chromium full suite; firefox/webkit/pixel-7/iphone-14 run auth, a11y, account
```

Windows: the venv launcher spawns a child python that keeps the port. To stop a server, kill *all* matching
processes (PowerShell `Get-CimInstance Win32_Process`), not just the one you started.

## Map

- `app/api/` routes. Auth on every route is enforced by `tests/test_route_auth.py` (new public routes must be added to its allowlist).
  `activity_routes.py` (in-flight jobs, per-user cap of 3), `content_routes.py` (cover letter, interview prep), `admin_routes.py`.
- `app/agents/ai_agent.py` prompts and pipeline stages; every system prompt gets `INJECTION_GUARD`.
- `app/services/llm_client.py` provider access: fallback models, token-per-minute governor, `Retry-After`, 413 handling.
- `app/services/compaction.py` local (no-LLM) context shrinking, `ground_skills` (drops skills the candidate does not have).
- `app/services/job_recommendations.py` fetch + scoring of job suggestions; cold fetch runs in the background (`start_refresh`).
- `app/services/usage.py` token tally per run, daily spend caps, `UsageEvent` rows for the admin page.
- `app/services/scraper.py` job-URL scraping with an SSRF guard (`validate_public_url`).
- `app/worker/tasks.py` arq tasks (`@tracked` records usage; note `enqueue()` passes keyword arguments).
- `app/middleware.py` security headers/CSP, body-size limit, request id + access log.
- `frontend/src/store/activity.js` background-job tracking (polls only while work is active, wakes other tabs via BroadcastChannel).
- `frontend/src/lib/monitoring.ts` Sentry (DSN comes from `/api/auth/config` at runtime), `components/PageMeta.tsx` titles/robots/canonical.

## Conventions and gotchas

- Models: `User.id` etc. are UUIDs. `token_version` on `User` revokes sessions; JWTs carry `tv`.
- Config is `app/config.py` (`settings`). Production refuses weak secrets, `RATE_LIMIT_ENABLED=false`, `LLM_FAKE=true`.
- `LLM_FAKE=true` makes `AIAgent._call` return canned JSON (tests/CI/e2e). Never in production.
- Python f-strings: `{{...}}` inside an expression part builds a set of dicts (a past 500). Prompts use `{{` only in literal text.
- API 4xx `detail` may be a string, list or object; `frontend/src/api/client.js` flattens it to a string (React crashes on objects).
- The built SPA (`app/static/dist`) is not committed; the Dockerfile builds it. Check builds with `vite build --outDir <tmp>`.
- Dates: columns are naive UTC (`datetime.utcnow()`); never pass tz-aware values to asyncpg for them.
- Do not commit secrets or `.env`; gitleaks runs in CI. Privacy: never put user data in logs, Sentry, or outside-service requests.
- Brand orange `#FF6B35` fails AA with white text; buttons use `#C2410C`. Keep axe tests (`e2e/tests/a11y.spec.js`) green.

## Before you merge

CI runs backend (ruff, pip-audit, pytest), frontend (npm audit, lint, tsc, vitest, build), Lighthouse budgets, gitleaks and
the Playwright matrix. Run `python -m evals.run_evals` after changing prompts or compaction.

## Code graph

`graphify-out/GRAPH_REPORT.md` is a generated map of the code (code-only AST graph: god nodes, communities, surprising
links). Read it before broad refactors; regenerate with `/graphify . --update` (the large `graph.json` is git-ignored).
