# Production Deployment — Oracle Cloud Always Free (₹0/month)

The whole stack (`docker-compose.prod.yaml`) runs unchanged on one free VM:
Caddy (auto-HTTPS) → FastAPI (serves API + built React SPA) → worker,
Postgres, Redis — with persistent volumes for the DB and generated resumes.

---

## 1. Create the free VM (one-time, ~15 min)

1. Sign up at **cloud.oracle.com** → choose a home region close to you
   (Mumbai/Hyderabad for India). Card required for identity — never charged
   as long as you only create *Always Free* resources.
2. **Compute → Instances → Create instance**
   - Image: **Ubuntu 24.04**
   - Shape: **Ampere A1.Flex** (Always Free eligible) — pick **2 OCPU / 12 GB**
     (you're allowed up to 4/24; 2/12 is plenty and leaves room for a 2nd VM)
   - If "Out of capacity": retry later or script it — A1 capacity fluctuates.
   - Add your SSH public key. Note the **public IP** after creation.
3. **Open ports 80/443** — TWO layers, both required (classic Oracle gotcha):
   - *Cloud firewall*: VCN → your subnet → Security List → Add Ingress Rules:
     source `0.0.0.0/0`, TCP, destination ports `80,443`
   - *OS firewall*: Oracle's Ubuntu images ship restrictive iptables:
     ```bash
     sudo iptables -I INPUT 5 -p tcp --dport 80  -j ACCEPT
     sudo iptables -I INPUT 5 -p tcp --dport 443 -j ACCEPT
     sudo netfilter-persistent save
     ```

## 2. (Optional but recommended) Free domain → free HTTPS

1. **duckdns.org** → sign in → create a subdomain, e.g. `atsready.duckdns.org`
2. Point it at the VM's public IP (one field on their page)
3. That's it — Caddy handles the Let's Encrypt certificate automatically
   once `SITE_ADDRESS` is set (step 4). Skipping this = plain HTTP on the IP.

## 3. Install Docker & get the code onto the VM

```bash
ssh ubuntu@<PUBLIC_IP>
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu && exit   # re-ssh so the group applies
```

Code transfer — either:
- **GitHub (recommended)**: push this repo to a *private* GitHub repo locally
  (`git remote add origin ... && git push -u origin master`), then on the VM
  `git clone https://github.com/<you>/<repo>.git app && cd app`
  — updates later are just `git pull`.
- **Direct copy**: `scp -r` the project folder (exclude `venv/`,
  `frontend/node_modules/`, `outputs/`, `.env`).

## 4. Production .env (create fresh on the VM — never copy the dev one)

```bash
cp .env.example .env && nano .env
```

Required values:

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` *(compose also forces this)* |
| `JWT_SECRET` | fresh: `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | strong: `openssl rand -hex 16` |
| `REDIS_PASSWORD` | strong: `openssl rand -hex 16` |
| `LLM_API_KEY` | your Groq key |
| `APIFY_API_TOKEN` | your Apify token |
| `FRONTEND_URL` | `https://atsready.duckdns.org` — **critical**: used in every email link and by billing |
| `SITE_ADDRESS` | `atsready.duckdns.org` (or leave unset for HTTP-on-IP) |

Email (pick one, both free):
- **Gmail**: Google Account → Security → 2-Step Verification → App passwords
  → create one, then:
  `SMTP_HOST=smtp.gmail.com  SMTP_PORT=587  SMTP_TLS=true`
  `SMTP_USER=you@gmail.com  SMTP_PASSWORD=<app password>`
  `EMAIL_FROM=ATS-Ready <you@gmail.com>`
- **Brevo** (300/day): sign up → SMTP & API → SMTP keys →
  `SMTP_HOST=smtp-relay.brevo.com  SMTP_PORT=587  SMTP_TLS=true` + login/key.

Startup **fails fast** if JWT_SECRET is weak or any URL still contains the
dev password `secret` — that's the config guard working as intended.

## 5. Launch

```bash
docker compose -f docker-compose.prod.yaml up -d --build   # ~5-10 min first build
docker compose -f docker-compose.prod.yaml exec api alembic upgrade head
```

Open `https://<your-domain>` (or `http://<PUBLIC_IP>`) — landing page, register,
generate. Emails now go to real inboxes via your SMTP provider.

## 6. Razorpay live wiring (when ready to charge)

1. Dashboard (Test Mode first): Settings → API Keys → **Generate Key** — the
   secret is shown **once**; copy both immediately into `.env`
2. Subscriptions → Plans → create Pro/Team monthly → `RAZORPAY_PLAN_*` ids
3. Settings → Webhooks → Add:
   URL `https://<your-domain>/api/webhooks/razorpay`, a strong secret →
   `RAZORPAY_WEBHOOK_SECRET`, events: `subscription.activated`,
   `subscription.charged`, `subscription.cancelled`, `subscription.halted`
4. `BILLING_ENABLED=true` → recreate:
   `docker compose -f docker-compose.prod.yaml up -d --force-recreate api worker`
5. Verify with a [test card](https://razorpay.com/docs/payments/payments/test-card-details/)
   before completing KYC for Live Mode.

## 7. Operations

```bash
# Logs
docker compose -f docker-compose.prod.yaml logs -f api worker

# Deploy an update
git pull && docker compose -f docker-compose.prod.yaml up -d --build

# Nightly DB backup (crontab -e), keeps 7 days:
0 3 * * * docker compose -f /home/ubuntu/app/docker-compose.prod.yaml exec -T db pg_dump -U atsready atsready | gzip > /home/ubuntu/backups/db-$(date +\%u).sql.gz
```

**Troubleshooting**
- Site unreachable → 9 times out of 10 it's the iptables rules (step 1.3)
- Caddy cert errors → DuckDNS record must point at the VM *before* first start
  with a domain `SITE_ADDRESS`; check `docker compose ... logs caddy`
- App boots then dies → `logs api`; the production config guard names exactly
  which secret it refused
