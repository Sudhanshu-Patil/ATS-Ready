# Production Deployment — No Credit Card, ₹0/month
### Hugging Face Spaces (app) + Neon (Postgres) + Upstash (Redis)

None of these ask for a card, ever. HF Docker Spaces free tier: **2 vCPU,
16 GB RAM**, HTTPS included at `https://<user>-<space>.hf.space`.

> Koyeb (this guide's previous target) was acquired by Mistral in Feb 2026
> and closed its free tier to new users. HF Spaces replaces it — with far
> more RAM.

Trade-offs vs. a VM (DEPLOYMENT.md): one container runs API + worker
(`start-combined.sh`, the Dockerfile's default final stage), the disk is
**ephemeral** (generated .docx files vanish on rebuild/restart — download
promptly), the Space **sleeps after ~48h without traffic** (next visitor
waits ~30-60s), and — important — **free public Spaces expose the source
code** in the Files tab. This repo contains no secrets (all credentials are
runtime env vars), but the code itself is browsable. For a portfolio project
that's usually a feature; if it's a dealbreaker, stop here and say so.

---

## 1. Neon (Postgres) + Upstash (Redis) — free, no card

Covered in the previous revision and **already done + verified** for this
project: Neon project created (Singapore), all migrations applied, Upstash
regional DB created. The two rules worth re-stating for posterity:

- Use Neon's **direct** hostname (strip `-pooler`) — their PgBouncer breaks
  asyncpg's prepared statements.
- The async and sync URLs spell SSL differently:
  `?ssl=require` (asyncpg) vs `?sslmode=require` (psycopg2).

## 2. Create the Space (~5 min)

1. **huggingface.co** → Sign Up (email only, no card)
2. Profile menu → **New Space**:
   - Name: `ats-ready`
   - SDK: **Docker** → *Blank* template
   - Hardware: **CPU basic · Free**
   - Visibility: **Public** (required — private Spaces block anonymous
     visitors from reaching the app)
3. Create a **write token**: Settings → Access Tokens → New token (type:
   Write). This is your git-push password.

## 3. Push the code

The Space is itself a git repo. From the project root:

```bash
git remote add hf https://huggingface.co/spaces/<your-hf-username>/ats-ready
git push hf master:main        # HF Spaces build from 'main'
# username = your HF username, password = the write token
```

HF reads the YAML front-matter at the top of README.md (`sdk: docker`,
`app_port: 8000`) and builds the Dockerfile. The **final stage is
`production-combined`** — migrations + ARQ worker + API in one container —
which is exactly what platforms without a build-target selector get.

## 4. Configure secrets (before the first build finishes)

Space page → **Settings → Variables and secrets** → add each as a **Secret**
(injected as env vars at runtime; never visible in the public repo):

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
| `FRONTEND_URL` | `https://<your-hf-username>-ats-ready.hf.space` |
| `SMTP_*` / `EMAIL_FROM` | Gmail app password or Brevo (optional at first — emails log until set) |
| `BILLING_ENABLED` + `RAZORPAY_*` | your Razorpay values (webhook secret: fresh random) |

Changing secrets triggers a restart automatically.

## 5. After it's live

- App: `https://<your-hf-username>-ats-ready.hf.space` — landing page,
  register, generate.
- **Razorpay webhook**: dashboard → Webhooks → URL
  `https://<user>-ats-ready.hf.space/api/webhooks/razorpay`, events
  `subscription.activated/charged/cancelled/halted`, secret matching
  `RAZORPAY_WEBHOOK_SECRET`.
- **Updates**: `git push hf master:main` (keep GitHub as the primary remote;
  push to both).
- **Logs**: Space page → the small "Logs" tab next to the App/Files tabs
  (build + runtime).

## Known free-tier limits

| Limit | Impact |
|---|---|
| Sleeps after ~48h idle | First visitor after a quiet spell waits ~30-60s |
| Ephemeral disk | .docx files vanish on rebuild — download-immediately usage |
| Public source | Code visible in the Space's Files tab (no secrets in repo) |
| Upstash 500K cmds/mo | Handled by `ARQ_POLL_DELAY=10` |
| Neon autosuspend | ~1s DB wake latency after idle |
| Groq 8K TPM | One generation at a time (jobs queue) |
