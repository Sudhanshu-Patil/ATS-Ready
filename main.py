"""
main.py — Step 6 update
────────────────────────
Adds content_router for cover letters and interview prep.
"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.rate_limit import limiter
from app.config import settings
from app.db.database import close_db, init_db
from app.services.cache_service import cache_service

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer() if settings.is_development
        else structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
logging.basicConfig(level=logging.DEBUG if settings.DEBUG else logging.INFO)
logger = structlog.get_logger(__name__)

if settings.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        release=settings.APP_VERSION,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        integrations=[FastApiIntegration()],
        send_default_pii=False,
    )

DIST_DIR = Path(__file__).parent / "app" / "static" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting ATS-Ready", version=settings.APP_VERSION, env=settings.ENVIRONMENT)
    if settings.is_development:
        await init_db()
        logger.info("Database tables created/verified (dev mode)")
    else:
        from sqlalchemy import text
        from app.db.database import engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")
    if await cache_service.ping():
        logger.info("Redis connected and responsive")
    else:
        logger.warning("Redis unavailable — caching disabled")
    yield
    await cache_service.close()
    await close_db()
    logger.info("Shutdown complete")


app = FastAPI(
    title="ATS-Ready API",
    description="AI-powered resume tailoring, cover letters, and interview prep.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse(
        status_code=429,
        content={"detail": "Too many requests — please wait a moment and try again."},
    ),
)
app.add_middleware(SlowAPIMiddleware)

ALLOWED_ORIGINS = [settings.FRONTEND_URL]
if settings.is_development:
    ALLOWED_ORIGINS += ["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:8000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Serve generated resumes whenever local storage is in use (no S3/R2
# configured) — production without object storage still needs downloads
# to work, not just development.
if not settings.storage_use_s3:
    app.mount("/outputs", StaticFiles(directory=str(settings.OUTPUT_DIR)), name="outputs")

# ── API Routes ────────────────────────────────────────────────────────────────
from app.api.routes import router
from app.api.auth_routes import auth_router
from app.api.sse_routes import sse_router
from app.api.job_routes import job_router
from app.api.billing_routes import billing_router
from app.api.content_routes import content_router
from app.api.activity_routes import activity_router

app.include_router(auth_router,    prefix="/api")
app.include_router(router,         prefix="/api")
app.include_router(sse_router,     prefix="/api")
app.include_router(job_router,     prefix="/api")
app.include_router(billing_router, prefix="/api")
app.include_router(content_router, prefix="/api")
app.include_router(activity_router, prefix="/api")


@app.get("/health", tags=["System"])
async def health():
    return {"status": "ok", "version": settings.APP_VERSION}


# ── Serve React SPA ───────────────────────────────────────────────────────────
if DIST_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(DIST_DIR / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # Real files in dist (favicon.svg, robots.txt, …) are served as-is;
        # anything else falls through to index.html for client-side routing.
        # resolve() + prefix check guards against ../ path traversal.
        if full_path:
            candidate = (DIST_DIR / full_path).resolve()
            if candidate.is_file() and str(candidate).startswith(str(DIST_DIR.resolve())):
                return FileResponse(str(candidate))
        index = DIST_DIR / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return {"error": "Frontend not built. Run: cd frontend && npm run build"}
else:
    @app.get("/", include_in_schema=False)
    async def root():
        return {"message": "ATS-Ready API", "docs": "/docs"}
