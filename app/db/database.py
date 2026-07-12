from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings


# ── Declarative Base ──────────────────────────────────────────────────────────
# Imported from base.py to keep it separate from engine creation.
# alembic/env.py also imports from base.py directly (without touching engine).
from app.db.base import Base  # noqa: F401


# ── Engine ────────────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,          # logs every SQL statement in dev — turn off in prod
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,           # recycle dead connections automatically
)


# ── Session Factory ───────────────────────────────────────────────────────────
# expire_on_commit=False:
#   After commit(), SQLAlchemy normally expires all attributes, forcing a
#   SELECT on next access.  In async code this is dangerous because the
#   refresh must be awaited.  Setting this to False keeps the in-memory
#   state valid after commit, which is safe for our request-scoped sessions.

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ── FastAPI Dependency ────────────────────────────────────────────────────────
# Usage in a route:
#
#   from app.db.database import get_db
#
#   @router.get("/skills")
#   async def get_skills(db: AsyncSession = Depends(get_db)):
#       result = await db.execute(select(Skill))
#       return result.scalars().all()
#
# The `async with` block guarantees the session is always closed, even if
# an exception is raised inside the route handler.

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Startup / Shutdown ────────────────────────────────────────────────────────
# Called from main.py lifespan.  Creates all tables that don't exist yet
# (safe in dev; in production Alembic handles this instead).

async def init_db() -> None:
    """Create all tables. Only used in development / tests."""
    async with engine.begin() as conn:
        # Import models here (not at module level) to avoid import cycles
        from app.db import models  # noqa: F401 — registers models on Base.metadata
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose the engine connection pool on shutdown."""
    await engine.dispose()


# ── Test helper ───────────────────────────────────────────────────────────────
@asynccontextmanager
async def get_test_db():
    """
    Context-manager version for use in tests (not in FastAPI DI).
    Usage:
        async with get_test_db() as db:
            result = await db.execute(select(Skill))
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise