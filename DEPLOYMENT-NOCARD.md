# Production Deployment — No Credit Card, ₹0/month
### Render (app) + Neon (Postgres) + Upstash (Redis)

Render's free tier requires **no credit card** (their policy: hit a limit →
suspended, never billed). Neon and Upstash never ask for one either.

> Platform history, July 2026: Oracle needs a card for identity checks,
> Koyeb closed its free tier after the Mistral acquisition, and Hugging Face
> moved Docker Spaces to paid plans. Render is the surviving no-card option
> for containers.

How it runs: Render builds our Dockerfile with no target selector, which
gives it the final `production-combined` stage — migrations + ARQ worker +
API in one container via `start-combined.sh` (which respects Render's
injected `$PORT`). Verified locally against the real Neon + Upstash.

Trade-offs: the free service **sleeps after 15 min without traffic** (next
visitor waits ~1 min while it wakes), the disk is **ephemeral** (generated
.docx files vanish on redeploy — download promptly), 512MB RAM (our combined
container measured 185MB — fits), and 750 free instance-hours/month (a
single always-provisioned service fits exactly).

---

## 1. Neon (Postgres) + Upstash (Redis) — already done ✓

Both created and verified for this project (Singapore region, migrations
applied). The two rules worth re-stating:

- Use Neon's **direct** hostname (strip `-pooler`) — their PgBouncer breaks
  asyncpg's prepared statements.
- The async and sync URLs spell SSL differently:
  `?ssl=require` (asyncpg) vs `?sslmode=require` (psycopg2).

## 2. Create the Render service (~10 min)

1. **render.com** → **Sign up with GitHub** (no card)
2. **New + → Web Service** → connect your GitHub → select the
   `ATS-Ready` repo (grant the Render GitHub App access to it — private is fine)
3. Configure:
   - Name: `ats-ready` (your URL becomes `https://ats-ready.onrender.com`,
     possibly with a suffix if the name is taken — note the final URL)
   - Region: **Singapore** (matches Neon/Upstash)
   - Branch: `master`
   - Runtime: **Docker** (auto-detected from the Dockerfile)
   - Instance type: **Free**
4. **Advanced** → Health Check Path: `/health`
5. Environment variables — add each (same values verified from this machine):

| Name | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `DEBUG` | `false` |
| `JWT_SECRET` | fresh `openssl rand -hex 32` |
| `DATABASE_URL` | the verified asyncpg URL (direct host, `?ssl=require`) |
| `SYNC_DATABASE_URL` | the verified psycopg2 URL (`?sslmode=require`) |
| `REDIS_URL` | the verified Upstash `rediss://…` URL |
| `ARQ_POLL_DELAY` | `10` (Upstash 500K cmds/month budget) |
| `LLM_API_KEY` | your Groq key |
| `MODEL` | `openai/gpt-oss-120b` |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` |
| `LLM_REASONING_EFFORT` | `low` |
| `APIFY_API_TOKEN` | your Apify token |
| `FRONTEND_URL` | `https://ats-ready.onrender.com` (correct after creation if the URL differs) |
| `SMTP_*` / `EMAIL_FROM` | Gmail app password or Brevo (optional at first — emails log until set) |
| `BILLING_ENABLED` + `RAZORPAY_*` | your Razorpay values (webhook secret: fresh random) |

6. **Deploy Web Service** — first build ~5-10 min. Watch the logs for
   `[start-combined]` lines: migrations → worker → API.

## 3. After it's live

- App: `https://ats-ready.onrender.com` — landing page, register, generate.
- If the final URL differs from what you set, update `FRONTEND_URL` in the
  service's Environment tab (auto-redeploys) — email links depend on it.
- **Razorpay webhook**: dashboard → Webhooks → URL
  `https://<app>.onrender.com/api/webhooks/razorpay`, events
  `subscription.activated/charged/cancelled/halted`, secret matching
  `RAZORPAY_WEBHOOK_SECRET`.
- **Updates**: `git push origin master` — Render auto-deploys on push.
- **Logs**: service page → Logs tab.

## One-time: Apify LinkedIn actor approval

The LinkedIn jobs source uses `forward_dinosaur/linkedin-job-scraper`, which
requests full Apify-account permissions — Apify blocks API runs (403) until
the account owner approves it once in the console (the approval URL is in
the 403 error payload). Approval is **per Apify account**, so approving it
once covers dev and production alike. Unapproved, the app degrades
gracefully: LinkedIn listings are simply absent.

## Known free-tier limits

| Limit | Impact |
|---|---|
| Sleeps after 15 min idle | Next visitor waits ~1 min for wake-up |
| Ephemeral disk | .docx files vanish on redeploy — download-immediately usage |
| 512MB RAM | Combined container measured 185MB — comfortable |
| Upstash 500K cmds/mo | Handled by `ARQ_POLL_DELAY=10` |
| Neon autosuspend | ~1s DB wake latency after idle |
| Groq 8K TPM | One generation at a time (jobs queue) |
