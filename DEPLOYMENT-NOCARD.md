# Production Deployment — No Credit Card, ₹0/month
### Koyeb (app) + Neon (Postgres) + Upstash (Redis)

None of these three ask for a card. The trade-offs vs. the Oracle VM path
(see DEPLOYMENT.md): one 512MB container runs API + worker together
(`start-combined.sh`), generated .docx files are **ephemeral** (gone on
redeploy — users should download promptly), and the DB/Redis are managed
free tiers with their own limits. Perfectly fine for a launch.

Koyeb provides HTTPS + a `*.koyeb.app` domain automatically — no Caddy needed.

---

## 1. Push the repo to GitHub (~5 min)

Koyeb deploys straight from GitHub:

```bash
# on your machine, in the project root
git remote add origin https://github.com/<you>/ats-ready.git   # create a PRIVATE repo first
git push -u origin master
```

## 2. Neon — free Postgres (~3 min)

1. **neon.tech** → sign up (GitHub login, no card) → create project
   (region: Singapore for India)
2. On the dashboard, open **Connection Details** and — important — select the
   **direct** connection (host WITHOUT `-pooler`). The pooled string runs
   PgBouncer in transaction mode, which breaks asyncpg's prepared statements.
3. From the one string Neon shows (`postgresql://USER:PASS@HOST/neondb`),
   derive our two URLs (note the different SSL parameter spellings):

```
DATABASE_URL=postgresql+asyncpg://USER:PASS@HOST/neondb?ssl=require
SYNC_DATABASE_URL=postgresql+psycopg2://USER:PASS@HOST/neondb?sslmode=require
```

Free-tier note: Neon autosuspends after ~5 min idle; the first request after
a quiet period adds ~1s of DB wake-up latency. Harmless.

## 3. Upstash — free Redis (~2 min)

1. **upstash.com** → sign up (no card) → Create Database (Regional,
   Singapore/closest)
2. Copy the **`rediss://`** connection URL (TLS) from the database page:

```
REDIS_URL=rediss://default:PASSWORD@HOST:6379
```

Free-tier budget: **500K commands/month** — that's why `ARQ_POLL_DELAY=10`
below is REQUIRED (the worker polls Redis; at the default 0.5s that's ~5M
commands/month, at 10s it's ~260K). Jobs start with up to 10s extra latency.

## 4. Koyeb — the app (~10 min)

1. **koyeb.com** → sign up with GitHub (no card on the free tier)
2. **Create Web Service** → GitHub → select your repo, branch `master`
3. Builder: **Dockerfile** (defaults are right — the Dockerfile's final
   stage is the production image with the React app baked in)
4. **Override the command**: `sh start-combined.sh`
   (runs migrations, then the ARQ worker + API in one container)
5. Instance type: **Free** (0.1 vCPU / 512MB) · Port: **8000** ·
   Health check: HTTP `/health`
6. Environment variables (mark secrets as Secret type):

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `JWT_SECRET` | `openssl rand -hex 32` output |
| `DATABASE_URL` | from step 2 (`+asyncpg`, `?ssl=require`) |
| `SYNC_DATABASE_URL` | from step 2 (`+psycopg2`, `?sslmode=require`) |
| `REDIS_URL` | from step 3 (`rediss://…`) |
| `ARQ_POLL_DELAY` | `10` ← required, see step 3 |
| `LLM_API_KEY` | your Groq key |
| `APIFY_API_TOKEN` | your Apify token |
| `FRONTEND_URL` | `https://<app-name>-<org>.koyeb.app` (shown at creation; update after if unsure) |
| `SMTP_HOST/PORT/USER/PASSWORD/SMTP_TLS/EMAIL_FROM` | Gmail app password or Brevo — same as DEPLOYMENT.md step 4 |
| `BILLING_ENABLED` + `RAZORPAY_*` | your Razorpay values when ready |

7. **Deploy**. First build ~5-8 min. The app is live at the `*.koyeb.app`
   URL with HTTPS included.

## 5. After it's live

- **Razorpay webhook** (finally has a real URL): dashboard → Settings →
  Webhooks → edit your webhook → URL
  `https://<app>.koyeb.app/api/webhooks/razorpay`, secret = a fresh
  `openssl rand -hex 24` (put the same value in Koyeb's
  `RAZORPAY_WEBHOOK_SECRET`), events: `subscription.activated/charged/
  cancelled/halted`.
- **Updates**: `git push` → Koyeb auto-rebuilds and redeploys.
- **Logs**: Koyeb dashboard → your service → Runtime logs (you'll see
  `[start-combined]` lines, then uvicorn + arq output interleaved).

## Known free-tier limits (accepted trade-offs)

| Limit | Impact |
|---|---|
| Ephemeral disk | Generated .docx files vanish on each redeploy/restart — fine for download-immediately usage |
| 512MB RAM | API (1 uvicorn worker) + ARQ worker fit, but heavy concurrency will OOM-restart — matches the 1-job-at-a-time Groq free tier anyway |
| Upstash 500K cmds/mo | Handled by `ARQ_POLL_DELAY=10` |
| Neon autosuspend | ~1s wake latency after idle periods |
| Groq 8K TPM | One generation at a time (jobs queue) — unchanged from dev |
