"""
app/config.py
─────────────
Central settings loaded from environment variables / .env file.
All sub-systems import `settings` from here — never read os.environ directly.
"""
from pathlib import Path
from typing import Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).parent.parent  # project root


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",           # silently ignore unknown env vars
        case_sensitive=False,
    )

    # ── App ───────────────────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    APP_VERSION: str = "1.0.0"

    # ── LLM (any OpenAI-compatible endpoint — currently Groq) ──────────────────
    LLM_API_KEY: str = ""
    MODEL: str = "openai/gpt-oss-120b"
    LLM_BASE_URL: str = "https://api.groq.com/openai/v1"
    # low/medium/high — gpt-oss reasoning depth. This app's tasks (structured
    # extraction, professional rewriting) don't need deep multi-step reasoning,
    # so "low" trades reasoning depth for speed/cost. Empty string omits the
    # param entirely (needed for providers/models that don't support it).
    LLM_REASONING_EFFORT: str = "low"
    # Returns canned JSON instead of calling the provider. For tests, Playwright
    # and CI only: no Groq quota is spent and runs are deterministic.
    # Tried in order when the main model is rate-limited or down (Groq limits
    # are per model). Comma-separated; empty disables fallback.
    LLM_FALLBACK_MODELS: str = "openai/gpt-oss-20b,qwen/qwen3.8-27b"
    LLM_TPM_BUDGET: int = 7500      # tokens/min per model; Groq free tier is 8K. 0 = off
    LLM_TIMEOUT: float = 60.0       # seconds per request
    LLM_ROUNDS: int = 3             # passes over all models before giving up
    LLM_PROFILE_MAX_CHARS: int = 9000   # compact_profile budget (~2.3K tokens)
    LLM_FAKE: bool = False
    # Per-IP limits on auth endpoints. Only the e2e suite turns this off (it
    # registers many accounts from one IP); production refuses to start without it.
    RATE_LIMIT_ENABLED: bool = True
    # Global cap on Apify actor runs per UTC day (protects the free-plan credit).
    APIFY_DAILY_RUN_CAP: int = 30

    # ── Database ──────────────────────────────────────────────────────────────
    # Async URL used by the app (asyncpg driver)
    DATABASE_URL: str = f"postgresql+asyncpg://atsready:secret@127.0.0.1:5432/atsready"

    # Sync URL used ONLY by Alembic CLI (psycopg2 driver).
    # Alembic cannot use asyncpg; this is kept separate intentionally.
    SYNC_DATABASE_URL: str = f"postgresql+psycopg2://atsready:secret@127.0.0.1:5432/atsready"

    # SQLAlchemy async pool settings
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30      # seconds to wait for a connection
    DB_POOL_RECYCLE: int = 1800    # recycle connections every 30 min

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://:secret@127.0.0.1:6379/0"

    # ── Apify (job recommendations — LinkedIn source) ───────────────────────────
    # Account-level token, works for any actor. Only genuinely free actors are
    # used (no pay-per-result/rental fee) — cost is limited to Apify's own
    # platform compute, covered by the free plan's $5/month credit.
    APIFY_API_TOKEN: str = ""

    # Cache TTLs (seconds)
    CACHE_JD_PARSE_TTL: int = 86_400       # 24 hours — same JD text = same parse
    CACHE_SCRAPED_URL_TTL: int = 21_600    # 6 hours  — scraped job pages
    CACHE_PROFILE_TTL: int = 300           # 5 min    — candidate profile

    # ── File Storage ─────────────────────────────────────────────────────────
    S3_ENDPOINT_URL: str = ""              # empty = use real AWS S3
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET_NAME: str = "ats-ready-resumes"
    S3_REGION: str = "auto"               # "auto" for R2, "us-east-1" for S3
    CDN_BASE_URL: str = ""                # base URL for public downloads

    # Signed URL expiry for private downloads (seconds)
    DOWNLOAD_URL_EXPIRY: int = 3_600      # 1 hour

    # Local temp dir — files are written here, uploaded to S3, then deleted.
    OUTPUT_DIR: Path = BASE_DIR / "outputs"

    # ── Background Jobs ───────────────────────────────────────────────────────
    JOB_TIMEOUT: int = 180          # max seconds a resume job can run (headroom
                                    # for LLM 429 retries with backoff)
    ARQ_POLL_DELAY: float = 0.5     # seconds between ARQ queue polls. Every
                                    # poll is a Redis command — on metered
                                    # free Redis (Upstash: 500K cmds/month)
                                    # 0.5s ≈ 5M/month and blows the budget.
                                    # Set 10 there (~260K/month); jobs then
                                    # start with up to 10s extra latency.
    WORKER_CONCURRENCY: int = 1     # simultaneous ARQ jobs per worker process.
                                    # 1 on purpose: each job makes 3 sequential
                                    # LLM calls, and free-tier providers (Groq:
                                    # 8K tokens/MINUTE) rate-limit per account —
                                    # concurrent jobs starve each other's token
                                    # bucket and both fail. Jobs queue instead.
                                    # Raise only on a paid LLM tier.

    # ── Resume Generation ─────────────────────────────────────────────────────
    MAX_SKILLS_IN_RESUME: int = 12
    MAX_PROJECTS_IN_RESUME: int = 4
    MAX_EXPERIENCE_BULLETS: int = 5

    # ── ATS Scoring Weights ───────────────────────────────────────────────────
    ATS_KEYWORD_WEIGHT: float = 0.40
    ATS_SKILLS_WEIGHT: float = 0.30
    ATS_ACTION_VERB_WEIGHT: float = 0.15
    ATS_FORMAT_WEIGHT: float = 0.15

    # ── Scraper ───────────────────────────────────────────────────────────────
    SCRAPE_TIMEOUT: int = 15
    SCRAPE_MAX_BYTES: int = 2_000_000     # stop reading a page after this much
    RESPECT_ROBOTS_TXT: bool = True

    # ── Auth (Step 2 — defined here so routes can import settings cleanly) ────
    JWT_SECRET: str = "change-me-use-openssl-rand-hex-32"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_EXPIRE_DAYS: int = 30
    FRONTEND_URL: str = "http://localhost:5173"

    # ── Email (password reset / verification) ─────────────────────────────────
    # Dev default targets the Mailpit container (docker-compose) — a local
    # SMTP catcher with a web UI at :8025. For production, point at any free
    # SMTP provider (Gmail app password, Brevo 300/day, …). If SMTP_HOST is
    # empty, emails are logged instead of sent — nothing breaks.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 1025
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_TLS: bool = False          # STARTTLS — true for real providers (587)
    EMAIL_FROM: str = "ATS-Ready <no-reply@ats-ready.local>"
    RESET_TOKEN_EXPIRE_MINUTES: int = 30

    # ── PayPal billing (sandbox by default) ───────────────────────────────────
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_API: str = "https://api-m.sandbox.paypal.com"  # live: https://api-m.paypal.com

    # ── Observability ─────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1
    
    # ── Billing ───────────────────────────────────────────────────────────────
    # Master switch — PayPal settings live in the PayPal section above.
    BILLING_ENABLED: bool = False

    # ── Derived helpers ───────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def storage_use_s3(self) -> bool:
        """True when S3/R2 credentials are configured."""
        return bool(self.S3_ACCESS_KEY_ID and self.S3_SECRET_ACCESS_KEY)

    # ── Validators ────────────────────────────────────────────────────────────
    @field_validator("OUTPUT_DIR", mode="before")
    @classmethod
    def ensure_output_dir(cls, v) -> Path:
        p = Path(v)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Fail fast at startup rather than run production with dev secrets."""
        if self.is_production:
            weak_jwt = (
                not self.JWT_SECRET
                or len(self.JWT_SECRET) < 32
                or self.JWT_SECRET == "change-me-use-openssl-rand-hex-32"
            )
            if weak_jwt:
                raise ValueError(
                    "ENVIRONMENT=production requires a strong JWT_SECRET "
                    "(>=32 chars). Generate one: openssl rand -hex 32"
                )
            if not self.RATE_LIMIT_ENABLED:
                raise ValueError("ENVIRONMENT=production requires RATE_LIMIT_ENABLED=true.")
            if self.LLM_FAKE:
                raise ValueError("ENVIRONMENT=production must not run with LLM_FAKE=true.")
            if ":secret@" in self.DATABASE_URL or ":secret@" in self.REDIS_URL:
                raise ValueError(
                    "ENVIRONMENT=production requires non-default DB/Redis "
                    "passwords (found the dev password 'secret' in a URL)."
                )
        return self

    @model_validator(mode="after")
    def validate_ats_weights(self) -> "Settings":
        total = (
            self.ATS_KEYWORD_WEIGHT
            + self.ATS_SKILLS_WEIGHT
            + self.ATS_ACTION_VERB_WEIGHT
            + self.ATS_FORMAT_WEIGHT
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"ATS weights must sum to 1.0, got {total:.3f}")
        return self


# ── Singleton — import this everywhere ────────────────────────────────────────
settings = Settings()
