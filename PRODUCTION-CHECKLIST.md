# Production checklist

What to set up, what runs automatically, and how to recover. For the Render/Neon/Upstash walkthrough see
[DEPLOYMENT-NOCARD.md](DEPLOYMENT-NOCARD.md). Environment variable **names** are in [render.yaml](render.yaml)
and [.env.example](.env.example); values live only in the Render dashboard and GitHub secrets.

## Before the first production deploy

1. **Migrations**: the image runs `alembic upgrade head` at start. Current head: `0008`.
2. **Required env**: `ENVIRONMENT=production`, a strong `JWT_SECRET` (Render can generate one), real
   `DATABASE_URL` / `REDIS_URL` (the app refuses to boot with the dev password `secret`),
   `LLM_API_KEY`, `FRONTEND_URL`.
3. **Email**: set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_TLS=true`, `EMAIL_FROM`.
   Without SMTP, password-reset and verification emails are not sent (and in production their links are
   deliberately never written to the logs).
4. **Google sign-in**: Google Cloud Console → APIs & Services → Credentials → OAuth client ID (Web).
   Add your site URL and `http://localhost:5173` as authorised JavaScript origins. Set `GOOGLE_CLIENT_ID`.
   The button appears only when it is set.
5. **Admin page**: set `ADMIN_EMAILS` (comma-separated). Those accounts, once email-verified, see **Admin**
   in the sidebar (`/admin`).
6. **Legal**: read and edit the privacy policy and terms in `frontend/src/pages/Legal.jsx`. They are a draft,
   not legal advice, and need a real contact address.

## Monitoring and alerts (free tiers)

| What | How |
|---|---|
| Errors (backend) | Create a Sentry project, set `SENTRY_DSN`. Add an alert rule: "new issue" and "error count > 10 in 5 min" to your email. |
| Errors (browser) | A second Sentry project (JavaScript), set `SENTRY_FRONTEND_DSN`. It is served to the page at runtime; no rebuild. |
| Uptime | UptimeRobot (free): HTTP monitor on `https://<site>/health/ready`, 5-minute interval, email alert. |
| Smoke test | GitHub repo variable `SITE_URL`: the *Smoke test* workflow then checks the live site every 30 minutes (and on demand). |
| Spend | See below. Every cap also logs a `SPEND ALERT` error at 80%, which Sentry turns into an email. |
| Performance | Lighthouse CI budgets run on every push (see `frontend/lighthouserc.json`). Sentry traces sample 10%. |

## Spend caps (so a free tier cannot be exhausted or surprise-billed)

- `LLM_USER_DAILY_TOKEN_CAP` (default 120 000) and `LLM_DAILY_TOKEN_CAP` (default 600 000): tokens per UTC day.
  Past the cap, new work is refused with a clear message. Set to `0` to disable. Check Groq's console for your
  real daily limits and keep these below them.
- `APIFY_DAILY_RUN_CAP` (default 30): actor runs per day. Also set a **monthly usage limit in the Apify
  console** (Settings → Billing → Usage limits).
- Per-user request limits protect the expensive endpoints (resume, cover letter, interview prep, import,
  recommendations), and a user can have at most 3 jobs in flight.
- In the provider consoles turn on usage alerts: Render, Neon (storage/compute), Upstash (commands),
  PayPal (none needed in sandbox).

## Backups

- **First line**: Neon's point-in-time restore (free tier keeps a short history window): Neon console → Branches → Restore.
- **Second line**: the *Database backup* workflow runs nightly: `pg_dump`, encrypted with AES-256, kept as a
  30-day GitHub artifact. Add two repo secrets: `BACKUP_DATABASE_URL` (plain `postgresql://…` Neon URL) and
  `BACKUP_PASSPHRASE`. The repository is public, so the dump is unreadable without the passphrase.
- **Restore** (try it once, on a scratch database, before you need it):

  ```bash
  gh run download <run-id> -n db-backup-<run-id>
  openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE -in backup.dump.enc -out backup.dump
  pg_restore --clean --no-owner -d "$TARGET_DATABASE_URL" backup.dump
  ```

## Deploy and roll back

- Render deploys the branch set in the dashboard on every push. CI must be green first: backend tests, ruff,
  pip-audit, frontend lint/types/tests/build, Lighthouse, gitleaks, and the Playwright suite (Chromium, Firefox,
  WebKit, Pixel 7, iPhone 14, slow-network).
- The built frontend (`app/static/dist`) is **not committed**; the Dockerfile builds it.
- **Roll back**: Render → Deploys → pick the previous deploy → Rollback. Migrations are additive; to undo one,
  `alembic downgrade -1` against the database (take a backup first).
- After a deploy run the *Smoke test* workflow by hand.

## Routine

- Weekly: skim the Admin page (failure rate, token use) and Sentry.
- Monthly: merge Dependabot PRs; `pip-audit` and `npm audit` already gate CI.
- Before launch announcements: run `python -m evals.run_evals` (real model, a few minutes) and read the failures.

## Known limits (free tier)

- A full resume takes 1 to 2 minutes: Groq's free tier allows 8K tokens per minute per model and the app waits
  instead of failing. Set `LLM_TPM_BUDGET=0` for speed with more fallback to smaller models.
- Render's free instance sleeps after 15 minutes idle; the first request wakes it (about 30 seconds).
- SSRF protection for job-URL scraping validates the address before connecting. It does not pin the resolved IP
  for the connection itself, so a DNS-rebinding attacker with control of a domain could still race it.
