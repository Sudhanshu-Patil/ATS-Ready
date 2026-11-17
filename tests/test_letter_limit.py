"""A user-set word/character cap on cover letters is always respected."""
import json
import uuid

import pytest
from sqlalchemy import select

from app.agents.ai_agent import AIAgent
from app.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import CoverLetter
from app.models.schemas import ParsedJD
from app.services import letter_limit as ll
from tests.conftest import unique_email
from tests.test_metabase_experience import bearer, register

LETTER = (
    "I was excited to see the Backend Engineer role at Acme because I build reliable payment APIs. "
    "The team's focus on latency matches my work.\n\n"
    "At Northwind I cut p95 latency by 40 percent with caching. I also moved our services to Kubernetes. "
    "That work taught me to measure before optimising. It also made on-call calmer for everyone.\n\n"
    "I led a migration of three services to PostgreSQL. It finished a month early. The team now deploys daily.\n\n"
    "Thank you for your time. I would love to talk.\n\nBest regards,\nAsha"
)


@pytest.mark.parametrize("unit,limit", [("words", 120), ("words", 80), ("words", 50), ("chars", 600),
                                         ("chars", 400), ("chars", 250)])
def test_fit_to_limit_never_exceeds_and_keeps_open_and_close(unit, limit):
    out = ll.fit_to_limit(LETTER, unit, limit)
    assert ll.count(out, unit) <= limit
    assert out.startswith("I was excited")                      # the opening survives
    if limit >= 120 or unit == "chars" and limit >= 400:
        assert out.rstrip().endswith("Asha")                    # so does the sign-off


def test_a_letter_already_within_the_limit_is_untouched():
    assert ll.fit_to_limit(LETTER, "words", 500) == LETTER
    assert ll.fit_to_limit(LETTER, "chars", 5000) == LETTER


def test_characters_count_spaces_and_line_breaks():
    assert ll.count("ab cd\n\nef", "chars") == 9 and ll.count("ab cd\n\nef", "words") == 3


def test_limit_ranges_are_validated():
    ll.validate("words", 300)
    ll.validate("chars", 1500)
    for unit, n in [("words", 10), ("words", 5000), ("chars", 50), ("chars", 50000), ("pages", 1)]:
        with pytest.raises(ValueError):
            ll.validate(unit, n)


def test_prompt_line_states_the_hard_cap():
    assert "HARD LIMIT of 300 words" in ll.prompt_line("words", 300)
    assert "1500 characters" in ll.prompt_line("chars", 1500)
    assert "1-2 short paragraphs" in ll.prompt_line("words", 100)


def test_agent_enforces_the_cap_even_when_the_model_ignores_it(monkeypatch):
    agent = AIAgent.__new__(AIAgent)
    long_body = "\n\n".join(LETTER for _ in range(3))
    monkeypatch.setattr(agent, "_call", lambda *a, **k: json.dumps(
        {"subject": "Application", "body": long_body, "word_count": 999, "highlights": ["x"]}), raising=False)
    jd = ParsedJD(job_title="Backend Engineer", company="Acme", required_skills=["Python"])
    out = agent.generate_cover_letter(jd, {"personal": {"full_name": "Asha"}}, {}, "professional", "words", 150)
    assert len(out["body"].split()) <= 150 and out["word_count"] == len(out["body"].split())
    # no cap: the model's text is kept and the count is the real one, not the model's guess of 999
    free = agent.generate_cover_letter(jd, {"personal": {"full_name": "Asha"}}, {}, "professional")
    assert free["body"] == long_body and free["word_count"] == len(long_body.split())


@pytest.fixture(autouse=True)
def _fake(monkeypatch):
    queued = []

    async def fake_enqueue(function, **kwargs):
        queued.append((function, kwargs))
    monkeypatch.setattr("app.api.content_routes.enqueue", fake_enqueue)
    monkeypatch.setattr(settings, "BILLING_ENABLED", False)
    monkeypatch.setattr(settings, "LLM_FAKE", True)
    return queued


JD = "We are hiring a backend engineer to build Python and FastAPI services. " * 3


async def _user(client):
    h = bearer(await register(client, unique_email()))
    await client.post("/api/metabase/personal", headers=h, json={"full_name": "Pat", "email": "p@atsready-tests.dev"})
    return h


async def test_api_stores_the_limit_and_queues_it(client, _fake):
    h = await _user(client)
    r = await client.post("/api/cover-letter", headers=h, json={"jd_text": JD, "limit": 250, "limit_unit": "words"})
    assert r.status_code == 202
    kwargs = _fake[0][1]
    assert kwargs["limit"] == 250 and kwargs["limit_unit"] == "words"
    got = (await client.get("/api/cover-letters", headers=h)).json()[0]
    assert (got["length_limit"], got["limit_unit"]) == (250, "words")


async def test_api_rejects_nonsense_limits_and_no_limit_means_none(client, _fake):
    h = await _user(client)
    for body in ({"limit": 5}, {"limit": 100000}, {"limit": 300, "limit_unit": "pages"},
                 {"limit": 20, "limit_unit": "chars"}):
        assert (await client.post("/api/cover-letter", headers=h, json={"jd_text": JD, **body})).status_code == 422
    r = await client.post("/api/cover-letter", headers=h, json={"jd_text": JD})
    assert r.status_code == 202 and _fake[-1][1]["limit"] is None and _fake[-1][1]["limit_unit"] is None


async def test_retry_keeps_the_users_limit(client, _fake):
    h = await _user(client)
    cid = (await client.post("/api/cover-letter", headers=h,
                             json={"jd_text": JD, "limit": 1200, "limit_unit": "chars"})).json()["id"]
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(CoverLetter).where(CoverLetter.id == uuid.UUID(cid)))).scalar_one()
        row.status = "failed"
        await db.commit()
    _fake.clear()
    assert (await client.post(f"/api/cover-letters/{cid}/retry", headers=h)).status_code == 202
    assert _fake[0][1]["limit"] == 1200 and _fake[0][1]["limit_unit"] == "chars"
