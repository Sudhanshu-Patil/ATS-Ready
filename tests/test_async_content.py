"""Cover letters / interview prep run as background jobs; /api/activity reports them."""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import update

from app.config import settings
from app.db.database import AsyncSessionLocal
from app.db.models import CoverLetter
from app.worker import tasks
from tests.conftest import unique_email
from tests.test_metabase_experience import bearer, register

JD = "We are hiring a backend engineer to build Python and FastAPI services. " * 3


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    queued = []

    async def fake_enqueue(function, **kwargs):
        queued.append((function, kwargs))

    monkeypatch.setattr("app.api.content_routes.enqueue", fake_enqueue)
    monkeypatch.setattr(settings, "BILLING_ENABLED", False)   # no plan gates
    monkeypatch.setattr(settings, "LLM_FAKE", True)
    return queued


async def user_with_profile(client):
    reg = await register(client, unique_email())
    h = bearer(reg)
    r = await client.post("/api/metabase/personal", headers=h, json={
        "full_name": "Pat Test", "email": "pat@atsready-tests.dev"})
    assert r.status_code == 200, r.text
    return h


async def test_cover_letter_post_is_202_and_enqueues(client, stub):
    h = await user_with_profile(client)
    r = await client.post("/api/cover-letter", headers=h, json={"jd_text": JD})
    assert r.status_code == 202 and r.json()["status"] == "pending"
    assert stub[0][0] == "generate_cover_letter_task"
    assert stub[0][1]["letter_id"] == r.json()["id"]

    act = (await client.get("/api/activity", headers=h)).json()
    assert [i["kind"] for i in act["active"]] == ["cover_letter"]
    assert act["active"][0]["position"] == 1


async def test_profile_required(client):
    reg = await register(client, unique_email())
    r = await client.post("/api/interview-prep", headers=bearer(reg), json={"jd_text": JD})
    assert r.status_code == 400


async def test_short_jd_rejected(client):
    h = await user_with_profile(client)
    r = await client.post("/api/cover-letter", headers=h, json={"jd_text": "too short"})
    assert r.status_code == 422


async def test_cap_of_three_active(client):
    h = await user_with_profile(client)
    for _ in range(3):
        assert (await client.post("/api/interview-prep", headers=h, json={"jd_text": JD})).status_code == 202
    r = await client.post("/api/cover-letter", headers=h, json={"jd_text": JD})
    assert r.status_code == 429


async def test_worker_fills_cover_letter(client):
    h = await user_with_profile(client)
    letter_id = (await client.post("/api/cover-letter", headers=h, json={"jd_text": JD})).json()["id"]

    await tasks.generate_cover_letter_task({}, letter_id, await _uid(client, h), JD, None, "professional")

    got = (await client.get(f"/api/cover-letters/{letter_id}", headers=h)).json()
    assert got["status"] == "done" and got["subject"] and got["body"]
    act = (await client.get("/api/activity", headers=h)).json()
    assert act["active"] == [] and act["recent"][0]["status"] == "done"


async def test_worker_fills_interview_prep(client):
    h = await user_with_profile(client)
    prep_id = (await client.post("/api/interview-prep", headers=h, json={"jd_text": JD})).json()["id"]
    await tasks.generate_interview_prep_task({}, prep_id, await _uid(client, h), JD, None)
    got = (await client.get(f"/api/interview-preps/{prep_id}", headers=h)).json()
    assert got["status"] == "done"


async def test_worker_failure_is_recorded_not_raised(client, monkeypatch):
    from app.services.llm_client import LLMUnavailable

    def boom(*a, **k):
        raise LLMUnavailable("down")

    monkeypatch.setattr(tasks.ai_agent, "generate_cover_letter", boom)
    h = await user_with_profile(client)
    letter_id = (await client.post("/api/cover-letter", headers=h, json={"jd_text": JD})).json()["id"]
    await tasks.generate_cover_letter_task({}, letter_id, await _uid(client, h), JD, None, "professional")

    got = (await client.get(f"/api/cover-letters/{letter_id}", headers=h)).json()
    assert got["status"] == "failed" and "busy" in got["error"]
    assert (await client.get("/api/activity", headers=h)).json()["recent"][0]["error"] == got["error"]


async def test_reaper_fails_stale_rows_only(client):
    h = await user_with_profile(client)
    old = (await client.post("/api/cover-letter", headers=h, json={"jd_text": JD})).json()["id"]
    new = (await client.post("/api/cover-letter", headers=h, json={"jd_text": JD})).json()["id"]
    async with AsyncSessionLocal() as db:
        await db.execute(update(CoverLetter).where(CoverLetter.id == uuid.UUID(old))
                         .values(created_at=datetime.utcnow() - timedelta(hours=2)))
        await db.commit()

    await tasks.reap_stale_jobs({})

    assert (await client.get(f"/api/cover-letters/{old}", headers=h)).json()["status"] == "failed"
    assert (await client.get(f"/api/cover-letters/{new}", headers=h)).json()["status"] == "pending"


async def test_other_users_rows_hidden(client):
    a = await user_with_profile(client)
    b = await user_with_profile(client)
    letter_id = (await client.post("/api/cover-letter", headers=a, json={"jd_text": JD})).json()["id"]
    assert (await client.get(f"/api/cover-letters/{letter_id}", headers=b)).status_code == 404
    assert (await client.get("/api/activity", headers=b)).json() == {"active": [], "recent": []}


async def test_activity_requires_auth(client):
    assert (await client.get("/api/activity")).status_code == 401


async def _uid(client, headers):
    return (await client.get("/api/auth/me", headers=headers)).json()["id"]


async def _fail_row(model, row_id):
    async with AsyncSessionLocal() as db:
        await db.execute(update(model).where(model.id == uuid.UUID(row_id)).values(status="failed", error="boom"))
        await db.commit()


async def test_failed_cover_letter_and_prep_can_be_retried(client, stub):
    from app.db.models import InterviewPrep
    h = await user_with_profile(client)
    cl = (await client.post("/api/cover-letter", headers=h, json={"jd_text": JD, "tone": "enthusiastic"})).json()["id"]
    pr = (await client.post("/api/interview-prep", headers=h, json={"jd_text": JD})).json()["id"]

    # Not failed yet: retry is refused.
    assert (await client.post(f"/api/cover-letters/{cl}/retry", headers=h)).status_code == 409
    assert (await client.post(f"/api/interview-preps/{pr}/retry", headers=h)).status_code == 409

    await _fail_row(CoverLetter, cl)
    await _fail_row(InterviewPrep, pr)
    stub.clear()

    r1 = await client.post(f"/api/cover-letters/{cl}/retry", headers=h)
    r2 = await client.post(f"/api/interview-preps/{pr}/retry", headers=h)
    assert r1.status_code == 202 and r2.status_code == 202
    assert [f for f, _ in stub] == ["generate_cover_letter_task", "generate_interview_prep_task"]
    assert stub[0][1]["tone"] == "enthusiastic" and stub[0][1]["jd_text"].startswith("We are hiring")
    got = (await client.get(f"/api/cover-letters/{cl}", headers=h)).json()
    assert got["status"] == "pending" and got["error"] is None


async def test_retry_is_owner_only(client, stub):
    h = await user_with_profile(client)
    cl = (await client.post("/api/cover-letter", headers=h, json={"jd_text": JD})).json()["id"]
    await _fail_row(CoverLetter, cl)
    other = bearer(await register(client, unique_email()))
    assert (await client.post(f"/api/cover-letters/{cl}/retry", headers=other)).status_code == 404


async def test_interview_prep_is_a_pro_feature(client, stub, monkeypatch):
    monkeypatch.setattr(settings, "BILLING_ENABLED", True)
    h = await user_with_profile(client)

    r = await client.post("/api/interview-prep", headers=h, json={"jd_text": JD})
    assert r.status_code == 402
    assert r.json()["detail"]["message"] == "Interview prep is a Pro feature."
    assert not stub                                              # nothing was queued

    from app.db.models import User
    from sqlalchemy import select
    async with AsyncSessionLocal() as db:
        me = (await client.get("/api/auth/me", headers=h)).json()["email"]
        u = (await db.execute(select(User).where(User.email == me))).scalar_one()
        u.plan = "pro"
        await db.commit()
    ok = await client.post("/api/interview-prep", headers=h, json={"jd_text": JD})
    assert ok.status_code == 202 and stub[0][0] == "generate_interview_prep_task"


async def test_generate_resume_without_a_profile_is_refused_up_front(client, stub):
    h = bearer(await register(client, unique_email()))             # no Personal Info saved
    r = await client.post("/api/generate-resume", headers=h, json={"jd_text": JD})
    assert r.status_code == 400
    assert "Personal Info" in r.json()["detail"]
    assert not stub
    jobs = (await client.get("/api/jobs", headers=h)).json()
    assert jobs["total"] == 0                                       # no doomed job row was created


# ── Documents: cover letter edit/download, resume PDF, referral message ───────

async def _done_letter(client, h):
    cl = (await client.post("/api/cover-letter", headers=h, json={"jd_text": JD})).json()["id"]
    async with AsyncSessionLocal() as db:
        await db.execute(update(CoverLetter).where(CoverLetter.id == uuid.UUID(cl)).values(
            status="done", subject="Application for Backend Engineer", body="Dear team,\n\nI build APIs.\n\nThanks",
            company="Acme", job_title="Backend Engineer"))
        await db.commit()
    return cl


async def test_edit_cover_letter_then_download_uses_edited_text(client, stub):
    h = await user_with_profile(client)
    cl = await _done_letter(client, h)

    r = await client.patch(f"/api/cover-letters/{cl}", headers=h,
                           json={"subject": "New subject", "body": "Hello Sam,\n\nEdited by me.\n\nBest"})
    assert r.status_code == 200 and r.json()["word_count"] == 6
    assert (await client.get(f"/api/cover-letters/{cl}", headers=h)).json()["body"].startswith("Hello Sam")

    docx = await client.get(f"/api/cover-letters/{cl}/download?format=docx", headers=h)
    assert docx.status_code == 200 and docx.content[:2] == b"PK"            # a .docx is a zip
    assert "Acme_Backend_Engineer.docx" in docx.headers["content-disposition"]
    from io import BytesIO

    from docx import Document
    assert "Edited by me." in "\n".join(p.text for p in Document(BytesIO(docx.content)).paragraphs)

    pdf = await client.get(f"/api/cover-letters/{cl}/download?format=pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    assert (await client.get(f"/api/cover-letters/{cl}/download?format=exe", headers=h)).status_code == 422


async def test_cover_letter_edit_and_download_rules(client, stub):
    h = await user_with_profile(client)
    pending = (await client.post("/api/cover-letter", headers=h, json={"jd_text": JD})).json()["id"]
    assert (await client.patch(f"/api/cover-letters/{pending}", headers=h, json={"body": "x"})).status_code == 409
    assert (await client.get(f"/api/cover-letters/{pending}/download", headers=h)).status_code == 409
    done = await _done_letter(client, h)
    assert (await client.patch(f"/api/cover-letters/{done}", headers=h, json={"body": ""})).status_code == 422
    other = bearer(await register(client, unique_email()))
    assert (await client.patch(f"/api/cover-letters/{done}", headers=other, json={"body": "mine now"})).status_code == 404
    assert (await client.get(f"/api/cover-letters/{done}/download", headers=other)).status_code == 404


def test_resume_pdf_renders_from_stored_data():
    from io import BytesIO

    from pypdf import PdfReader

    from app.services.documents import resume_pdf
    data = {"personal": {"full_name": "Asha Verma", "email": "asha@example.com", "location": "Pune"},
            "tailored": {"professional_summary": "Backend engineer <b>& more</b>.",
                         "skills": [{"category": "Languages", "items": ["Python", "SQL"]}],
                         "work_experience": [{"role": "Engineer", "company": "Northwind", "start_date": "2022",
                                              "end_date": "Present", "bullets": ["Built FastAPI services – 2M req/day"]}],
                         "projects": [{"title": "Resume Tailor", "tech_stack": ["Python"], "bullets": ["Tailors resumes"]}]},
            "education": [{"degree": "B.E.", "field": "Computer", "institution": "SPPU", "end_year": "2022"}]}
    text = "\n".join(p.extract_text() for p in PdfReader(BytesIO(resume_pdf(data))).pages)
    for needle in ("Asha Verma", "TECHNICAL SKILLS", "Northwind", "Built FastAPI services", "Resume Tailor", "SPPU"):
        assert needle in text, needle
    assert "<b>& more</b>" in text                            # user text is drawn literally, never parsed as markup


async def test_resume_pdf_download_endpoint(client, stub):
    from app.db.models import JobApplication
    h = await user_with_profile(client)
    uid = uuid.UUID((await client.get("/api/auth/me", headers=h)).json()["id"])
    async with AsyncSessionLocal() as db:
        with_data = JobApplication(user_id=uid, status="done", job_title="Dev", resume_filename="resume_dev.docx",
                                   resume_s3_key="x", resume_data={"personal": {"full_name": "A"}, "tailored": {}, "education": []})
        without = JobApplication(user_id=uid, status="done", job_title="Old", resume_filename="old.docx", resume_s3_key="y")
        db.add_all([with_data, without])
        await db.commit()
        a, b = str(with_data.id), str(without.id)
    ok = await client.get(f"/api/download/{a}?format=pdf", headers=h)
    assert ok.status_code == 200 and ok.content[:5] == b"%PDF-" and "resume_dev.pdf" in ok.headers["content-disposition"]
    assert (await client.get(f"/api/download/{b}?format=pdf", headers=h)).status_code == 404
    jobs = {j["id"]: j for j in (await client.get("/api/jobs", headers=h)).json()["items"]}
    assert jobs[a]["pdf_url"] == f"/api/download/{a}?format=pdf" and jobs[b]["pdf_url"] is None


async def test_referral_message(client, stub, monkeypatch):
    h = await user_with_profile(client)
    r = await client.post("/api/referral-message", headers=h,
                          json={"person_name": "Sam Lee", "jd_text": JD, "job_url": "https://example.com/jobs/1"})
    assert r.status_code == 200
    assert set(r.json()) == {"connection_note", "message"} and len(r.json()["connection_note"]) <= 300

    assert (await client.post("/api/referral-message", headers=h, json={"person_name": "Sam"})).status_code == 422
    no_profile = bearer(await register(client, unique_email()))
    assert (await client.post("/api/referral-message", headers=no_profile, json={"jd_text": JD})).status_code == 400

    monkeypatch.setattr(settings, "BILLING_ENABLED", True)          # outreach is a Pro tool
    assert (await client.post("/api/referral-message", headers=h, json={"jd_text": JD})).status_code == 402


def test_referral_connection_note_is_capped_at_linkedins_limit(monkeypatch):
    import json

    from app.agents.ai_agent import AIAgent
    a = AIAgent.__new__(AIAgent)
    monkeypatch.setattr(a, "_call", lambda *args, **kw: json.dumps({"connection_note": "x" * 500, "message": "m"}), raising=False)
    out = a.generate_referral_message("Sam", "d" * 200, "", {"personal": {"full_name": "A"}})
    assert len(out["connection_note"]) <= 300
