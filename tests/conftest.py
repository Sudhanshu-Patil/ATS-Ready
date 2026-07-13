"""
Test fixtures — integration tests against the real app + dev database.

Run inside the api container (DB/Redis reachable on the compose network):

    docker compose exec api pytest

Each test run registers throwaway users with unique emails and deletes them
afterward, so the dev database isn't polluted.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.db.database import AsyncSessionLocal
from app.db.models import User
from main import app

# Every email this run creates gets registered here and removed at teardown.
_created_emails: set[str] = set()


def unique_email() -> str:
    # Real TLD on purpose: pydantic's EmailStr (email-validator) rejects
    # special-use domains like .local/.test/example.com at the schema level.
    # No mail is ever sent — these rows are deleted at session teardown.
    email = f"pytest-{uuid.uuid4().hex[:12]}@atsready-tests.dev"
    _created_emails.add(email)
    return email


@pytest.fixture()
async def client():
    # ASGITransport calls the app in-process — no running server needed, but
    # DB access is real (the dev Postgres on the compose network).
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(scope="session", autouse=True)
async def _cleanup_test_users():
    yield
    if _created_emails:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(User).where(User.email.in_(_created_emails)))
            await db.commit()
